"""Validatore DETERMINISTICO del canone. Niente LLM.

Tre modi:
  valida_canone.py --fx FX_PLANS_JSON --durata SECONDI [--parola-chiave P]
      tipi solo negli 8 validi; un solo evento a schermo per istante (pill
      esclusa: è il banner alto; stamp escluso: non ha t0/t1; la claim
      occupa da t0 al primo stamp successivo, o alla fine clip); un solo
      rosso per evento; cta presente e ultima; eventi dentro la durata;
      con --parola-chiave, la cta finale deve contenerla nel text.

  valida_canone.py --pagina HTML --trascritto TRANSCRIPT_JSON [--guida MD]
      niente codice attivo nell'HTML GREZZO (<script>, attributi on*=,
      URI javascript:, <iframe>/<object>/<embed>); poi ogni numero della
      pagina deve comparire nel trascritto, salvo anni in date evidenti,
      numeri dentro attributi html, frasi condizionali ("se ", "nel caso"),
      numeri STRUTTURALI (ordinali di elenco, contatori decorativi: non
      sono affermazioni) e numeri prescritti dalla guida umana (--guida:
      footer, P.IVA, durata della chiamata — li ha scritti una persona).

  valida_canone.py --regia REGIA.json --durata SECONDI
      la regia del video lungo, sei famiglie di regole: struttura,
      vocabolario (tipi ammessi R3 e campi obbligatori per tipo), cadenza,
      rosso, diversità, più il contratto d'uscita invariato. Le soglie
      sono tarate sulla regia approvata del video 01: deve passare tutte
      le famiglie tranne il vocabolario R3 (che vale per le regie nuove).

Violazioni: elenco su stderr, exit 1. Su stdout un solo oggetto JSON.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html import unescape
from pathlib import Path

TIPI_EVENTO = ("pill", "hook", "card", "counter", "list", "claim", "cta", "stamp")
# Tipi che devono avere t0 e t1; claim ha solo t0, stamp solo t, pill niente.
TIPI_INTERVALLO = ("hook", "card", "counter", "list", "cta")
EPSILON = 0.05

MESI = ("gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto"
        "|settembre|ottobre|novembre|dicembre")
REGEX_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")
# Date evidenti: "8 agosto 2026", "agosto 2026", "11/08/2026", "© 2026".
REGEX_DATE = re.compile(
    rf"\b\d{{1,2}}\s+(?:{MESI})(?:\s+\d{{4}})?\b"
    rf"|\b(?:{MESI})\s+\d{{4}}\b"
    r"|\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b"
    r"|©\s*\d{4}", re.IGNORECASE)


# ------------------------------------------------------------------ modo fx

def valida_fx(percorso: str, durata: float, parola_chiave: str | None = None) -> list[str]:
    piani = json.loads(Path(percorso).read_text(encoding="utf-8"))
    violazioni: list[str] = []
    for piano in piani:
        src = piano.get("src", "?")
        eventi = piano.get("events", [])
        intervalli: list[tuple[float, float, str]] = []
        senza_stamp_e_pill = [e for e in eventi if e.get("type") not in ("stamp", "pill")]
        # i tempi degli stamp servono a chiudere l'intervallo delle claim:
        # "la claim resta a schermo fino al payoff"
        tempi_stamp = sorted(e["t"] for e in eventi
                             if e.get("type") == "stamp" and isinstance(e.get("t"), (int, float)))

        for n, ev in enumerate(eventi):
            tipo = ev.get("type")
            dove = f"{src} evento {n} ({tipo})"
            if tipo not in TIPI_EVENTO:
                violazioni.append(f"{dove}: tipo non valido")
                continue
            # un solo elemento rosso per evento (red oppure redLabel, non entrambi)
            if sum(1 for campo in ("red", "redLabel") if ev.get(campo)) > 1:
                violazioni.append(f"{dove}: più di un elemento rosso")
            if tipo == "pill":
                if any(campo in ev for campo in ("t0", "t1", "t")):
                    violazioni.append(f"{dove}: la pill non porta tempi (sono fissi)")
                continue
            if tipo == "stamp":
                t = ev.get("t")
                if not isinstance(t, (int, float)):
                    violazioni.append(f"{dove}: manca t")
                elif not (0 <= t <= durata + EPSILON):
                    violazioni.append(f"{dove}: t={t} fuori dalla durata {durata}")
                continue
            t0 = ev.get("t0")
            t1 = ev.get("t1")
            if not isinstance(t0, (int, float)):
                violazioni.append(f"{dove}: manca t0")
                continue
            if tipo in TIPI_INTERVALLO and not isinstance(t1, (int, float)):
                violazioni.append(f"{dove}: manca t1")
                continue
            if tipo == "claim":
                # la claim resta a schermo fino al primo stamp successivo
                # (o alla fine della clip): l'intervallo si estende fin li'
                fine = min(next((t for t in tempi_stamp if t > t0), durata), durata)
            else:
                fine = t1 if isinstance(t1, (int, float)) else t0
            if t0 < 0 or fine > durata + EPSILON:
                violazioni.append(f"{dove}: [{t0}, {fine}] fuori dalla durata {durata}")
            if fine < t0:
                violazioni.append(f"{dove}: t1 < t0")
            for voce in ev.get("items") or []:
                t = voce.get("t")
                if not isinstance(t, (int, float)) or not (0 <= t <= durata + EPSILON):
                    violazioni.append(f"{dove}: voce di lista con t fuori range: {voce}")
            intervalli.append((t0, fine, f"{tipo} n.{n}"))

        # massimo un evento a schermo per istante (pill e stamp esclusi)
        intervalli.sort()
        for (a0, a1, a), (b0, b1, b) in zip(intervalli, intervalli[1:]):
            if b0 < a1:
                violazioni.append(f"{src}: sovrapposizione fra {a} [{a0}-{a1}] "
                                  f"e {b} [{b0}-{b1}]")

        # cta presente e ultima (fra gli eventi a schermo; lo stamp può seguirla)
        if not any(e.get("type") == "cta" for e in eventi):
            violazioni.append(f"{src}: cta assente")
        elif senza_stamp_e_pill and senza_stamp_e_pill[-1].get("type") != "cta":
            violazioni.append(f"{src}: la cta non è l'ultimo evento a schermo")
        elif parola_chiave:
            # "cta finale con la parola chiave": verificabile solo se il
            # chiamante la passa (--parola-chiave)
            testo_cta = senza_stamp_e_pill[-1].get("text") or ""
            if parola_chiave.lower() not in testo_cta.lower():
                violazioni.append(f"{src}: la cta finale non contiene la parola "
                                  f"chiave '{parola_chiave}' (text: '{testo_cta}')")
    return violazioni


# -------------------------------------------------------------- modo pagina

def normalizza_numero(testo: str) -> str:
    """'5.000' e '5,000' e '5000' diventano la stessa chiave di confronto."""
    return re.sub(r"[.,]", "", testo)


def testo_visibile(html: str) -> str:
    """Il testo che il lettore vede: via script, style, commenti, tag e attributi.

    I tag di blocco diventano a capo, non spazio: cosi' due blocchi diversi
    non si incollano in un'unica "frase" e un contatore d'elenco resta
    riconoscibile come inizio della propria riga.
    """
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<\s*(?:br\s*/?|/p|/li|/h[1-6]|/div|/section|/article|/aside"
                  r"|/header|/footer|/figure|/figcaption|/blockquote|/tr)\s*>",
                  "\n", html, flags=re.I)
    return unescape(re.sub(r"<[^>]*>", " ", html))


def frase_condizionale(frase: str) -> bool:
    bassa = frase.strip().lower()
    return bassa.startswith("se ") or " se " in bassa or "nel caso" in bassa


PAROLE_ELENCO = re.compile(
    r"(?:obbligo|passo|punto|step|fase|parte|capitolo|sezione|giorno|n\.|nº|n°)\s*$",
    re.IGNORECASE)


def numero_strutturale(frase: str, m: re.Match) -> bool:
    """Ordinali e contatori di impaginazione: numerano, non affermano.

    Il divieto colpisce le QUANTITA' inventate ("35 milioni", "3%"): un
    ordinale d'elenco o un contatore decorativo non porta un'affermazione.
    Regole strette: solo 1-2 cifre, e solo in posizione di numerazione.
    """
    num = m.group(0)
    if not re.fullmatch(r"\d{1,2}", num):
        return False
    # "07", "01": contatore decorativo con zero davanti, mai una quantita'
    if num.startswith("0"):
        return True
    # il numero e' l'intera riga: folio o contatore isolato
    if frase.strip() == num:
        return True
    if int(num) > 20:
        return False
    prima = frase[:m.start()]
    dopo = frase[m.end():]
    # ordinale a inizio riga: "1 — Testo", "4 · Testo", "2) Testo", "3. Testo",
    # oppure contatore con etichetta maiuscola: "2 REGISTRO"
    if not prima.strip():
        if re.match(r"\s*[—–·:.)\]\-]", dopo):
            return True
        if re.match(r"\s+[A-ZÀ-Ú]{2,}(?:\s|$)", dopo):
            return True
    # ordinale dopo una parola d'elenco: "OBBLIGO 1", "passo 3"
    if PAROLE_ELENCO.search(prima):
        return True
    return False


# Codice attivo nell'HTML della pagina risorsa: la pagina e' statica, e
# testo_visibile() RIMUOVE script e attributi prima del controllo numeri,
# quindi questi controlli girano sull'HTML GREZZO.
CONTROLLI_CODICE_ATTIVO = (
    ("tag <script>", r"<\s*script\b"),
    ("attributo on*= (handler inline)", r"\son\w+\s*="),
    ("URI javascript:", r"javascript\s*:"),
    ("tag <iframe>/<object>/<embed>", r"<\s*(?:iframe|object|embed)\b"),
)


def valida_pagina(percorso_pagina: str, percorso_trascritto: str,
                  percorso_guida: str | None = None) -> list[str]:
    dati = json.loads(Path(percorso_trascritto).read_text(encoding="utf-8"))
    testo_trascritto = " ".join(s["text"] for s in dati["segments"])
    numeri_ammessi = {normalizza_numero(m.group(0))
                      for m in REGEX_NUMERO.finditer(testo_trascritto)}
    if percorso_guida:
        # i numeri scritti nella guida (footer, P.IVA, durata chiamata) li ha
        # prescritti una persona: non sono invenzioni dell'LLM
        testo_guida = Path(percorso_guida).read_text(encoding="utf-8")
        numeri_ammessi |= {normalizza_numero(m.group(0))
                           for m in REGEX_NUMERO.finditer(testo_guida)}

    html = Path(percorso_pagina).read_text(encoding="utf-8")
    violazioni: list[str] = []
    for descrizione, regex in CONTROLLI_CODICE_ATTIVO:
        if re.search(regex, html, re.IGNORECASE):
            violazioni.append(f"codice attivo nell'HTML: {descrizione}")

    testo = testo_visibile(html)
    for frase in re.split(r"(?<=[.!?])\s+|\n+", testo):
        frase = frase.strip()
        if not frase:
            continue
        ripulita = REGEX_DATE.sub(" ", frase)  # via gli anni delle date evidenti
        for m in REGEX_NUMERO.finditer(ripulita):
            if normalizza_numero(m.group(0)) in numeri_ammessi:
                continue
            if frase_condizionale(frase):
                continue
            if numero_strutturale(ripulita, m):
                continue
            estratto = frase if len(frase) <= 90 else frase[:87] + "..."
            violazioni.append(f"numero '{m.group(0)}' assente dal trascritto, "
                              f"nella frase: \"{estratto}\"")
    return violazioni


# --------------------------------------------------------------- modo regia

# Vocabolario R3: i tipi ammessi nelle regie generate. Tutto il resto
# (lista3, crash0, crashdown, six, bigone, race, ogni evento fs...) è vietato
# finché i componenti non saranno parametrizzati.
TIPI_REGIA = ("race", "bigone", "six", "crash0", "crashdown", "lista3", "card", "qcard", "badge", "pills", "flow", "keyword", "minibars",
              "chat", "claim2", "arrow2", "avatar", "cols2", "network",
              "pipeline", "grid", "cta", "stamp")
# Campi obbligatori per tipo. Le tuple con suffisso [] nel contratto sono
# liste: qui basta che il campo ci sia e, se è una lista, non sia vuoto.
CAMPI_REGIA = {
    "race": ("fast", "slow"), "bigone": ("sub",), "six": ("seed", "out"),
    "crash0": ("from", "label", "tail"), "crashdown": ("value", "sub"),
    "lista3": ("value", "k"),
    "card": ("title",), "qcard": ("title",), "badge": ("title",),
    "pills": ("pills",), "flow": ("steps",), "keyword": ("title",),
    "minibars": ("counter", "bars", "label"), "chat": ("bubbles",),
    "claim2": ("lines",), "arrow2": ("from", "to"), "avatar": ("title", "sub"),
    "cols2": ("left", "right"), "network": ("center", "nodes"),
    "pipeline": ("nodes",), "grid": ("cells",), "cta": ("rows",),
    "stamp": (),  # solo t0: t1 può mancare
}
POS_REGIA = ("SX", "ADX", "BSX", "TOP")
ENTER_REGIA = ("slide", "pop", "drop", "blur")
PUNCH_SCALE_MAX = 1.13
GAP_MINIMO = 3.5        # distanza minima fra t0 consecutivi (approvata: 3.6)
BUCO_MASSIMO = 30.0     # nessun tratto senza eventi più lungo di così (appr.: 26.0)
DENSITA_MIN, DENSITA_MAX = 6.0, 14.0  # durSec / n_eventi (approvata: 10.4)
TOLLERANZA_DURATA = 0.5  # scarto ammesso fra durSec nel file e --durata
# Tipi da momento forte: tetto per tipo tarato sulla regia approvata del
# video 01 (minibars ×1, avatar ×1, network ×2, arrow2 ×2): la taratura
# segue il fatto misurato, il principio del contratto resta.
MAX_MOMENTO_FORTE = {"minibars": 1, "avatar": 1, "network": 2, "arrow2": 2}


def _flag_rossi(valore) -> int:
    """Conta ricorsivamente i flag `red` veritieri dentro un evento
    (tail.red, right.red, red su riga/nodo/colonna...)."""
    totale = 0
    if isinstance(valore, dict):
        if valore.get("red"):
            totale += 1
        totale += sum(_flag_rossi(v) for k, v in valore.items() if k != "red")
    elif isinstance(valore, list):
        totale += sum(_flag_rossi(v) for v in valore)
    return totale


def _campi_testo(valore, percorso=""):
    """Tutte le stringhe dentro un evento, col loro percorso, per il
    conteggio dell'enfasi *…* campo per campo."""
    if isinstance(valore, dict):
        for k, v in valore.items():
            yield from _campi_testo(v, f"{percorso}.{k}" if percorso else k)
    elif isinstance(valore, list):
        for n, v in enumerate(valore):
            yield from _campi_testo(v, f"{percorso}[{n}]")
    elif isinstance(valore, str):
        yield percorso, valore


def _tempi_interni(valore, percorso=""):
    """I tempi delle voci temporizzate dentro un evento: `t` di {t, text},
    `at` delle barre di minibars, `cross` di qcard, i momenti del dict `k`."""
    if isinstance(valore, dict):
        for k, v in valore.items():
            qui = f"{percorso}.{k}" if percorso else k
            if k in ("t", "at", "cross") and isinstance(v, (int, float)):
                yield qui, v
            elif k == "k" and isinstance(v, dict):
                for nome, momento in v.items():
                    if isinstance(momento, (int, float)):
                        yield f"{qui}.{nome}", momento
            else:
                yield from _tempi_interni(v, qui)
    elif isinstance(valore, list):
        for n, v in enumerate(valore):
            yield from _tempi_interni(v, f"{percorso}[{n}]")


def _titolo_normalizzato(titolo: str) -> str:
    return " ".join(titolo.lower().replace("*", "").split())


def valida_regia(percorso: str, durata: float) -> list[str]:
    regia = json.loads(Path(percorso).read_text(encoding="utf-8"))
    violazioni: list[str] = []

    # --- famiglia 1: struttura ------------------------------------------
    if regia.get("fps") != 30:
        violazioni.append(f"fps={regia.get('fps')} invece di 30")
    dur_sec = regia.get("durSec")
    if not isinstance(dur_sec, (int, float)):
        violazioni.append("manca durSec")
        dur_sec = durata  # si prosegue coi controlli usando la durata data
    elif abs(dur_sec - durata) > TOLLERANZA_DURATA:
        violazioni.append(f"durSec={dur_sec} non torna con la durata data {durata}")
    if not regia.get("faceOrigin"):
        violazioni.append("manca faceOrigin")
    takes = regia.get("takes")
    if not isinstance(takes, list) or not takes:
        violazioni.append("takes assente o vuoto")
        takes = []
    punches = regia.get("punches")
    if not isinstance(punches, list):
        violazioni.append("punches non è una lista (può essere vuota, non mancare)")
        punches = []
    eventi = regia.get("events")
    if not isinstance(eventi, list) or not eventi:
        violazioni.append("events assente o vuoto")
        eventi = []

    for n, punch in enumerate(punches):
        t = punch.get("t")
        if not isinstance(t, (int, float)) or not (0 <= t <= dur_sec + EPSILON):
            violazioni.append(f"punch {n}: t={t} fuori da [0, {dur_sec}]")
        scala = punch.get("scale")
        if not isinstance(scala, (int, float)) or scala > PUNCH_SCALE_MAX + 1e-9:
            violazioni.append(f"punch {n}: scale={scala} sopra {PUNCH_SCALE_MAX}")
    for n, take in enumerate(takes):
        if not (isinstance(take.get("start"), (int, float))
                and isinstance(take.get("end"), (int, float))
                and 0 <= take["start"] < take["end"] <= dur_sec + EPSILON):
            violazioni.append(f"take {n}: intervallo non valido: {take}")

    visti: set = set()
    for e in eventi:
        ident = e.get("id")
        dove = f"evento {ident} ({e.get('type')})"
        if ident is None:
            violazioni.append(f"{dove}: manca id")
        elif ident in visti:
            violazioni.append(f"{dove}: id duplicato")
        visti.add(ident)

        tipo = e.get("type")
        t0, t1 = e.get("t0"), e.get("t1")
        if not isinstance(t0, (int, float)):
            violazioni.append(f"{dove}: manca t0")
            continue
        if tipo != "stamp":
            # t0 < t1 vale per tutti tranne lo stamp (che può non avere t1)
            if not isinstance(t1, (int, float)):
                violazioni.append(f"{dove}: manca t1")
                continue
            if not t0 < t1:
                violazioni.append(f"{dove}: t0={t0} non precede t1={t1}")
        fine = t1 if isinstance(t1, (int, float)) else t0
        if t0 < 0 or fine > dur_sec + EPSILON:
            violazioni.append(f"{dove}: [{t0}, {fine}] fuori da [0, {dur_sec}]")
        if e.get("pos") not in POS_REGIA:
            violazioni.append(f"{dove}: pos '{e.get('pos')}' non in {POS_REGIA}")
        if "enter" in e and e["enter"] not in ENTER_REGIA:
            violazioni.append(f"{dove}: enter '{e['enter']}' non in {ENTER_REGIA}")

        # --- famiglia 2: vocabolario e campi per tipo -------------------
        if tipo not in TIPI_REGIA:
            violazioni.append(f"{dove}: tipo vietato dal canone (R3)")
        else:
            for campo in CAMPI_REGIA[tipo]:
                valore = e.get(campo)
                if valore is None or (isinstance(valore, list) and not valore):
                    violazioni.append(f"{dove}: manca il campo obbligatorio '{campo}'")
        # le voci temporizzate stanno dentro l'intervallo dell'evento;
        # per lo stamp senza t1 il limite alto resta la durata
        limite = t1 if isinstance(t1, (int, float)) else dur_sec
        for chiavi_evento in (k for k in e if k not in ("id", "type", "pos", "enter", "t0", "t1")):
            # il valore si riavvolge in un dict con la sua chiave: i rami
            # "cross" (float nudo) e "k" (dict di momenti) scattano solo
            # vedendo la chiave, non il valore spacchettato
            for percorso_t, t in _tempi_interni({chiavi_evento: e[chiavi_evento]}):
                if not (t0 - EPSILON <= t <= limite + EPSILON):
                    violazioni.append(f"{dove}: voce temporizzata {percorso_t}={t} "
                                      f"fuori da [{t0}, {limite}]")

        # --- famiglia 4: rosso ed enfasi --------------------------------
        rossi = _flag_rossi(e)
        if rossi > 1:
            violazioni.append(f"{dove}: {rossi} flag rossi (al più uno per evento)")
        for percorso_txt, testo in _campi_testo(e):
            if testo.count("*") > 2:
                violazioni.append(f"{dove}: più di una coppia di enfasi *…* "
                                  f"nel campo {percorso_txt}")

    # --- famiglia 3: cadenza (sui soli eventi con t0 valido) ------------
    tempi = [e["t0"] for e in eventi if isinstance(e.get("t0"), (int, float))]
    if tempi != sorted(tempi):
        violazioni.append("gli eventi non sono ordinati per t0")
        tempi = sorted(tempi)
    for a, b in zip(tempi, tempi[1:]):
        if b - a < GAP_MINIMO - EPSILON:
            violazioni.append(f"cadenza: {b - a:.2f}s fra t0={a} e t0={b} "
                              f"(minimo {GAP_MINIMO}s)")
    if tempi:
        densita = dur_sec / len(tempi)
        if not (DENSITA_MIN <= densita <= DENSITA_MAX):
            violazioni.append(f"cadenza: densità media {densita:.1f}s per evento "
                              f"fuori da [{DENSITA_MIN}, {DENSITA_MAX}]")
        # buchi: dall'inizio al primo evento, fra eventi, dall'ultimo alla fine
        bordi = [0.0] + tempi + [dur_sec]
        for a, b in zip(bordi, bordi[1:]):
            if b - a > BUCO_MASSIMO + EPSILON:
                violazioni.append(f"cadenza: {b - a:.1f}s senza eventi "
                                  f"fra {a} e {b} (massimo {BUCO_MASSIMO}s)")

    # --- famiglia 5: diversità ------------------------------------------
    conta_tipi = {}
    for e in eventi:
        conta_tipi[e.get("type")] = conta_tipi.get(e.get("type"), 0) + 1
    for tipo, tetto in MAX_MOMENTO_FORTE.items():
        if conta_tipi.get(tipo, 0) > tetto:
            violazioni.append(f"diversità: {conta_tipi[tipo]} eventi '{tipo}' "
                              f"(al più {tetto} per video)")
    coppie: set = set()
    for e in eventi:
        titolo = e.get("title")
        if not isinstance(titolo, str):
            continue
        coppia = (e.get("type"), _titolo_normalizzato(titolo))
        if coppia in coppie:
            violazioni.append(f"diversità: due eventi con lo stesso "
                              f"(type, title): {coppia}")
        coppie.add(coppia)

    return violazioni


# ------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Validatore deterministico del canone: piano FX, pagina risorsa "
                    "o regia del video lungo.")
    ap.add_argument("--fx", help="fx_plans.json da validare")
    ap.add_argument("--durata", type=float,
                    help="durata in secondi (con --fx e con --regia)")
    ap.add_argument("--parola-chiave",
                    help="con --fx: la cta finale deve contenerla nel text")
    ap.add_argument("--pagina", help="pagina risorsa HTML da validare")
    ap.add_argument("--trascritto", help="transcript.json di riferimento (con --pagina)")
    ap.add_argument("--guida", help="guida umana della pagina: i suoi numeri sono ammessi")
    ap.add_argument("--regia", help="regia.json del video lungo da validare")
    args = ap.parse_args()

    if sum(1 for modo in (args.fx, args.pagina, args.regia) if modo) > 1:
        ap.error("un modo alla volta: --fx, --pagina oppure --regia")
    if args.fx:
        if args.durata is None:
            ap.error("--fx richiede --durata")
        violazioni = valida_fx(args.fx, args.durata, args.parola_chiave)
    elif args.pagina:
        if not args.trascritto:
            ap.error("--pagina richiede --trascritto")
        violazioni = valida_pagina(args.pagina, args.trascritto, args.guida)
    elif args.regia:
        if args.durata is None:
            ap.error("--regia richiede --durata")
        violazioni = valida_regia(args.regia, args.durata)
    else:
        ap.error("serve --fx FX_PLANS_JSON --durata S, --pagina HTML --trascritto T, "
                 "oppure --regia REGIA.json --durata S")
        return 2  # mai raggiunto: ap.error esce

    for v in violazioni:
        print(f"VIOLAZIONE: {v}", file=sys.stderr)
    print(json.dumps({"esito": {"valido": not violazioni, "violazioni": violazioni}},
                     ensure_ascii=False))
    return 1 if violazioni else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
