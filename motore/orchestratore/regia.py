"""Giudizio del modulo lungo: la regia grafica del video, ancorata a indici di parola.

Il modello riceve il trascritto indicizzato (segmenti numerati, parole con
indice GLOBALE), le proposte di mappa_visiva (portano i secondi calcolati dal
codice: servono solo a capire DOVE il brand suggerisce un elemento) e la
durata. Propone eventi con SOLI indici di parola; IL CODICE converte
indici -> secondi (entrata 0.3 s prima della parola d'attacco, come da corpus:
la grafica risponde a una frase gia' cominciata), fa la riparazione geometrica
deterministica, compone il regia.json completo {fps, durSec, faceOrigin,
takes, punches, events} e fa girare valida_canone.py --regia: se il canone
non passa, exit 1 (il JSON coi costi si stampa comunque, decisione 5).

Uso:
    regia.py TRANSCRIPT --proposte PROPOSTE.json --takes TAKES.json
             --durata SECONDI --faccia "52% 37%" --uscita REGIA.json
             --corpus guide/CORPUS-REGIA.md --analogie guide/ANALOGIE.md
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Le costanti di fondazione e la regola di arrotondamento stanno in un posto
# solo: motore/shorts-pipeline/fondamenta.py (docs/fondamenta-numeriche.md).
# Non dipende dal brand kit, quindi la puo' importare anche l'orchestratore.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shorts-pipeline"))

from pydantic import BaseModel, Field

import fondamenta
import llm

MODELLO_DEFAULT = "external-agent"
# Opus 5 ragiona in adattivo e il thinking conta nel tetto dei token di
# uscita: la sonda del 15/08 ha misurato ~30k token di solo ragionamento su
# questo compito. 64000 lascia spazio a ragionamento + ~60 eventi di regia.
MAX_TOKENS = 64000

# Entrata: 0.3 s prima della parola d'attacco (dal contratto: la grafica
# risponde a una frase gia' cominciata). Uscita: le durate del corpus vanno
# da 2.3 a 22 s reali; +0.6 s dopo l'ultima parola lascia chiudere la frase
# e tiene gli attacchi corti sopra la soglia dei 2 s della riparazione.
MARGINE_T0 = 0.3
MARGINE_T1 = 0.6

DURATA_MINIMA = 2.0        # sotto, l'evento schiacciato si scarta
DISTACCO = 0.05            # aria fra un t1 e il t0 successivo
GAP_MINIMO_CANONE = 3.5    # stessa soglia di valida_canone: qui si ripara,
                           # li' si boccia — mai bocciare per colpa del codice
SCALA_PUNCH = 1.10         # fissa: lo scale non lo decide l'LLM
PUNCH_MAX_AL_MINUTO = 2

# I 17 tipi ammessi nelle regie generate (R3): il resto e' cablato nel TSX
# del video 01 o incoerente, e resta vietato finche' i componenti non
# saranno parametrizzati.
TIPI_AMMESSI = ("card", "qcard", "badge", "pills", "flow", "keyword",
                "minibars", "chat", "claim2", "arrow2", "avatar", "cols2",
                "network", "pipeline", "grid", "cta", "stamp")

# Campi obbligatori per tipo (tabella dei componenti del contratto): un
# evento a cui mancano si scarta con AVVISO, non boccia tutta la regia.
CAMPI_RICHIESTI = {
    "card": ("title",), "qcard": ("title",), "badge": ("title",),
    "pills": ("voci",), "flow": ("voci",), "keyword": ("title",),
    "chat": ("bubbles",),
    "claim2": ("voci",), "arrow2": ("title", "sub"),
    "avatar": ("title", "sub"), "cols2": ("left", "right"),
    "network": ("title", "voci"), "pipeline": ("voci",),
    "grid": ("voci",), "cta": ("voci",), "stamp": (),
}

# L'LLM manda UNA lista generica `voci`; la chiave del componente Remotion
# la determina il tipo. Un unico campo lista nello schema tiene piccola la
# grammatica dello structured output (con 7 campi lista separati la API
# rifiutava: "compiled grammar is too large").
DESTINAZIONE_VOCI = {
    "card": "rows", "qcard": "bullets", "pills": "pills", "flow": "steps",
    "claim2": "lines", "network": "nodes", "pipeline": "nodes",
    "grid": "cells", "cta": "rows",
}

# Le chiavi temporizzate del regia.json FINALE (per il clamp dentro [t0, t1]).
LISTE_TEMPORIZZATE = ("lines", "bullets", "pills", "steps", "nodes",
                      "cells", "rows")

SYSTEM_BASE = """Componi la regia grafica (overlay) di un video lungo orizzontale.
Ricevi il trascritto indicizzato: una riga per segmento, "seg N | indice:parola
...", con l'indice GLOBALE di parola nel video. Non conosci i tempi e non devi
inventarli: ogni evento e ogni voce interna si ancora a indici di parola, la
conversione in secondi la fa il codice. Le proposte della mappa visiva nel
messaggio portano dei secondi calcolati dal codice: usale come riferimento per
capire DOVE il brand suggerisce un elemento, ma la tua risposta resta a indici.

Il canone, distillato dal corpus qui sotto:
- le grafiche TRASCRIVONO il parlato chiave, non lo commentano: a schermo vanno
  le parole dette, condensate, mai la parafrasi di un presentatore;
- un elemento alla volta: mai due eventi a schermo nello stesso istante;
- si entra su una frase gia' cominciata: parola_da cade sulla parola chiave,
  non sull'inizio della frase;
- il payoff rosso sul punto d'arrivo: il rosso (tail.red, right.red, red su
  una voce) sta sulla conclusione; al massimo UN flag rosso per evento;
- enfasi *cosi'*: al massimo una coppia di asterischi per campo di testo;
- cadenza: un evento nuovo circa ogni 6-12 secondi di parlato, attacchi ad
  almeno 4 secondi l'uno dall'altro, mai piu' di 25 secondi senza niente a
  schermo;
- ogni evento copre una frase, non un capitolo: da parola_da a parola_a
  passano di norma fra 3 e 20 secondi di parlato;
- numeri a schermo SOLO se detti davvero nel parlato;
- diversita': avatar, network e arrow2 sono momenti forti, al massimo UNO
  ciascuno nell'intero video; mai due eventi con lo stesso tipo e lo stesso
  titolo;
- punch-zoom: elenco di parola_idx sul colpo, non sul discorso, al massimo 2
  al minuto (lo scale lo mette il codice);
- ancore SOLO su indici presenti nel trascritto ricevuto;
- le righe interne di un evento (righe di card, bullet di qcard, pill, passi
  di flow, righe di claim2, nodi di network/pipeline, celle di grid, righe di
  cta) vanno TUTTE nella lista generica `voci`: la chiave finale del
  componente la mette il codice in base al tipo;
- convenzioni: per network `title` e' il centro della rete; per arrow2
  `title` e' il punto di partenza e `sub` quello d'arrivo; la posizione a
  schermo non si sceglie (la mette il codice: overlay a sinistra, viso
  libero).

""" + llm.RIGA_ANTI_INJECTION + """

--- CORPUS DI REGIA ---
"""

SEPARATORE_ANALOGIE = """

--- ANALOGIE ---
"""


# ------------------------------------------------------ schema dell'LLM

class VoceTemporizzata(BaseModel):
    parola_idx: int
    text: str
    red: Optional[bool] = None


class Fumetto(BaseModel):
    parola_idx: int
    side: Literal["left", "right"]
    who: str
    text: str


class Colonna(BaseModel):
    label: str
    text: str
    red: Optional[bool] = None


class EventoRegia(BaseModel):
    """Un evento a SOLI indici: la validazione per-tipo la fa il codice."""
    # Lo structured output ha un tetto di complessità dello schema (l'API
    # rifiuta con "Schema is too complex" / "compiled grammar is too large"):
    # l'evento porta SOLO cio' che il codice non puo' decidere da solo.
    # Fuori dallo schema, per scelta: `pos` (SX sempre, ADX per lo stamp —
    # lo mette il codice), `enter`/`size`/`k` (i componenti hanno i loro
    # default), `minibars` (esigeva due modelli dedicati; resta valido per
    # le regie a mano), `cross`. Convenzioni sui campi restanti:
    # network -> `title` e' il centro della rete; arrow2 -> `title` e' il
    # "from", `sub` e' il "to". La conversione le applica.
    tipo: Literal["card", "qcard", "badge", "pills", "flow", "keyword",
                  "chat", "claim2", "arrow2", "avatar", "cols2",
                  "network", "pipeline", "grid", "cta", "stamp"]
    parola_da: int
    parola_a: int
    title: Optional[str] = None
    sub: Optional[str] = None
    # UNA lista generica: la chiave Remotion (rows/bullets/lines/...) la
    # determina il tipo via DESTINAZIONE_VOCI
    voci: Optional[list[VoceTemporizzata]] = None
    bubbles: Optional[list[Fumetto]] = None
    tail: Optional[VoceTemporizzata] = None
    left: Optional[Colonna] = None
    right: Optional[Colonna] = None


class RegiaProposta(BaseModel):
    eventi: list[EventoRegia]
    punches: list[int]  # parola_idx dei punch-zoom


# ------------------------------------------------- trascritto indicizzato

def mappa_parole(segmenti: list[dict]) -> dict[int, tuple[str, float, float]]:
    """Tutte le parole del video con indice globale: {idx: (testo, start, end)}."""
    mappa: dict[int, tuple[str, float, float]] = {}
    globale = 0
    for seg in segmenti:
        for w in seg.get("words", []):
            mappa[globale] = (w["w"], w["start"], w["end"])
            globale += 1
    return mappa


def trascritto_indicizzato(segmenti: list[dict]) -> str:
    """Una riga per segmento, parole numerate globalmente: "seg N | i:parola"."""
    righe = []
    globale = 0
    for n, seg in enumerate(segmenti):
        pezzi = []
        for w in seg.get("words", []):
            pezzi.append(f"{globale}:{w['w']}")
            globale += 1
        righe.append(f"seg {n} | " + " ".join(pezzi))
    return "\n".join(righe)


# ------------------------------------------------- conversione in secondi

def clampa(t: float, a: float, b: float) -> float:
    return fondamenta.arrotonda_decimale(min(b, max(a, t)), 2)


def converti_evento(ev: EventoRegia, mappa: dict, durata: float) -> dict | None:
    """Un evento a indici -> evento a secondi, o None (scartato con AVVISO)."""
    mancanti = [campo for campo in CAMPI_RICHIESTI[ev.tipo]
                if getattr(ev, campo) in (None, [], "")]
    if mancanti:
        print(f"AVVISO: evento {ev.tipo} scartato (campi obbligatori mancanti: "
              f"{', '.join(mancanti)})", file=sys.stderr)
        return None
    if (ev.parola_da not in mappa or ev.parola_a not in mappa
            or ev.parola_da > ev.parola_a):
        print(f"AVVISO: evento {ev.tipo} scartato (ancore invalide: "
              f"{ev.parola_da}-{ev.parola_a})", file=sys.stderr)
        return None

    t0 = fondamenta.arrotonda_decimale(max(0.0, mappa[ev.parola_da][1] - MARGINE_T0), 2)
    t1 = clampa(mappa[ev.parola_a][2] + MARGINE_T1, t0, durata)

    # pos la decide il codice: overlay sempre a sinistra (il viso sta al
    # centro-destra dell'inquadratura), lo stamp in alto a destra come nel
    # video 01. Le convenzioni dello schema si applicano qui: network usa
    # title come centro della rete, arrow2 usa title/sub come from/to.
    evento: dict = {"type": ev.tipo, "t0": t0, "t1": t1,
                    "pos": "ADX" if ev.tipo == "stamp" else "SX"}
    if ev.tipo == "network":
        evento["center"] = ev.title
    elif ev.tipo == "arrow2":
        evento["from"] = ev.title
        evento["to"] = ev.sub
    else:
        if ev.title is not None:
            evento["title"] = ev.title
        if ev.sub is not None:
            evento["sub"] = ev.sub

    def secondi(idx: int) -> float | None:
        """Il tempo di una voce interna, dentro [t0, t1]; None se fuori mappa."""
        if idx not in mappa:
            return None
        return clampa(mappa[idx][1], t0, t1)

    if ev.voci is not None:
        destinazione = DESTINAZIONE_VOCI.get(ev.tipo)
        if destinazione is None:
            print(f"AVVISO: {ev.tipo} non porta una lista di voci: ignorata",
                  file=sys.stderr)
        else:
            tenute = []
            for voce in ev.voci:
                t = secondi(voce.parola_idx)
                if t is None:
                    print(f"AVVISO: voce '{voce.text}' di {ev.tipo} scartata "
                          f"(parola_idx {voce.parola_idx} fuori trascritto)",
                          file=sys.stderr)
                    continue
                riga = {"t": t, "text": voce.text}
                if voce.red:
                    riga["red"] = True
                tenute.append(riga)
            if not tenute and "voci" in CAMPI_RICHIESTI[ev.tipo]:
                print(f"AVVISO: evento {ev.tipo} scartato (voci vuote dopo la "
                      "validazione)", file=sys.stderr)
                return None
            if tenute:
                evento[destinazione] = tenute

    if ev.bubbles is not None:
        fumetti = []
        for b in ev.bubbles:
            t = secondi(b.parola_idx)
            if t is None:
                print(f"AVVISO: fumetto '{b.text}' scartato (parola_idx "
                      f"{b.parola_idx} fuori trascritto)", file=sys.stderr)
                continue
            fumetti.append({"t": t, "side": b.side, "who": b.who, "text": b.text})
        if not fumetti:
            print("AVVISO: evento chat scartato (nessun fumetto valido)",
                  file=sys.stderr)
            return None
        evento["bubbles"] = fumetti

    if ev.tail is not None:
        t = secondi(ev.tail.parola_idx)
        if t is None:
            print(f"AVVISO: tail di {ev.tipo} scartata (parola_idx fuori "
                  "trascritto)", file=sys.stderr)
        else:
            coda = {"t": t, "text": ev.tail.text}
            if ev.tail.red:
                coda["red"] = True
            evento["tail"] = coda

    for campo in ("left", "right"):
        colonna = getattr(ev, campo)
        if colonna is not None:
            lato = {"label": colonna.label, "text": colonna.text}
            if colonna.red:
                lato["red"] = True
            evento[campo] = lato

    return evento


def clampa_voci(evento: dict) -> None:
    """Riporta tutti i tempi interni dentro [t0, t1] (dopo la riparazione
    geometrica il t1 puo' essersi accorciato, e il validatore esige le voci
    dentro l'intervallo)."""
    t0, t1 = evento["t0"], evento["t1"]
    for campo in (*LISTE_TEMPORIZZATE, "bubbles"):
        for voce in evento.get(campo) or []:
            voce["t"] = clampa(voce["t"], t0, t1)
    if "tail" in evento:
        evento["tail"]["t"] = clampa(evento["tail"]["t"], t0, t1)
    if "k" in evento:
        evento["k"] = {nome: clampa(t, t0, t1) for nome, t in evento["k"].items()}
    for barra in evento.get("bars") or []:
        barra["at"] = clampa(barra["at"], t0, t1)
    if "cross" in evento:
        evento["cross"] = clampa(evento["cross"], t0, t1)


def ripara_geometria(eventi: list[dict]) -> list[dict]:
    """Riparazione DETERMINISTICA: il canone "un elemento alla volta" si
    garantisce qui, in codice. Eventi ordinati per t0, gap sotto il minimo
    del canone risolti scartando l'evento successivo, sovrapposizioni
    clampate (t1 = t0 successivo - 0.05), eventi schiacciati sotto 2 s
    scartati con AVVISO, rossi in piu' spenti, id riassegnati progressivi.
    Ogni bocciatura del validatore che il codice puo' prevenire e' un giro
    di chiamata Opus risparmiato."""
    eventi.sort(key=lambda e: e["t0"])
    # cadenza minima del canone: due attacchi troppo vicini non si clampano
    # (diventerebbero schiacciati), si tiene il primo e si scarta il secondo
    distanziati: list[dict] = []
    for ev in eventi:
        if distanziati and ev["type"] != "stamp" \
                and ev["t0"] - distanziati[-1]["t0"] < GAP_MINIMO_CANONE:
            print(f"AVVISO: {ev['type']} a t0={ev['t0']} a meno di "
                  f"{GAP_MINIMO_CANONE}s dal precedente: scartato", file=sys.stderr)
            continue
        distanziati.append(ev)
    eventi = distanziati
    for prec, succ in zip(eventi, eventi[1:]):
        if prec["t1"] > succ["t0"] - DISTACCO:
            prec["t1"] = fondamenta.arrotonda_decimale(succ["t0"] - DISTACCO, 2)
    tenuti = []
    for ev in eventi:
        # lo stamp e' esente dal minimo: il validatore stesso lo esonera
        # dal vincolo t0 < t1
        if ev["type"] != "stamp" and ev["t1"] - ev["t0"] < DURATA_MINIMA:
            print(f"AVVISO: {ev['type']} a t0={ev['t0']} schiacciato sotto "
                  f"{DURATA_MINIMA}s: scartato", file=sys.stderr)
            continue
        clampa_voci(ev)
        spegni_rossi_in_piu(ev)
        tenuti.append(ev)
    for n, ev in enumerate(tenuti, start=1):
        ev["id"] = n
    # id in testa, come nel regia.json approvato del video 01
    return [{"id": ev.pop("id"), **ev} for ev in tenuti]


def spegni_rossi_in_piu(ev: dict) -> None:
    """Un solo flag rosso per evento: il primo (in ordine di documento) resta,
    gli altri si spengono con AVVISO. Deterministico, previene la bocciatura."""
    trovato = False

    def visita(valore):
        nonlocal trovato
        if isinstance(valore, dict):
            if valore.get("red"):
                if trovato:
                    valore["red"] = False
                    print(f"AVVISO: {ev['type']} a t0={ev.get('t0')}: flag rosso "
                          f"in piu' spento (uno per evento)", file=sys.stderr)
                else:
                    trovato = True
            for k, v in valore.items():
                if k != "red":
                    visita(v)
        elif isinstance(valore, list):
            for v in valore:
                visita(v)

    visita(ev)


def converti_punches(indici: list[int], mappa: dict, durata: float) -> list[dict]:
    """parola_idx -> {t, scale}: scale 1.10 fisso, massimo 2 al minuto
    (le eccedenti si scartano con AVVISO)."""
    tempi = []
    for idx in indici:
        if idx not in mappa:
            print(f"AVVISO: punch scartato (parola_idx {idx} fuori trascritto)",
                  file=sys.stderr)
            continue
        t = fondamenta.arrotonda_decimale(mappa[idx][1], 2)
        if not (0 <= t <= durata):
            print(f"AVVISO: punch a t={t} scartato (fuori dalla durata)",
                  file=sys.stderr)
            continue
        tempi.append(t)
    tempi.sort()
    punches: list[dict] = []
    for t in tempi:
        nel_minuto = [p for p in punches if t - p["t"] < 60.0]
        if len(nel_minuto) >= PUNCH_MAX_AL_MINUTO:
            print(f"AVVISO: punch a t={t} scartato (oltre "
                  f"{PUNCH_MAX_AL_MINUTO} al minuto)", file=sys.stderr)
            continue
        punches.append({"t": t, "scale": SCALA_PUNCH})
    return punches


def carica_takes(percorso: str) -> list[dict]:
    """takes.json del passo stacchi: lista di {start, end} (o di coppie
    [start, end], normalizzate)."""
    dati = json.loads(Path(percorso).read_text(encoding="utf-8"))
    if isinstance(dati, dict):
        dati = dati.get("takes", [])
    takes = []
    for take in dati:
        if isinstance(take, dict):
            takes.append({"start": take["start"], "end": take["end"]})
        else:
            takes.append({"start": take[0], "end": take[1]})
    if not takes:
        raise llm.EsitoPermanente(f"componi_regia: nessun take in {percorso}")
    return takes


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Regia del video lungo via LLM, tempi calcolati in codice, canone validato.")
    ap.add_argument("transcript", help="build/transcript.json (parole con tempi)")
    ap.add_argument("--proposte", required=True,
                    help="regia/proposte.json di mappa_visiva (riferimento, con i secondi)")
    ap.add_argument("--takes", required=True, help="regia/takes.json del passo stacchi")
    ap.add_argument("--durata", type=float, required=True,
                    help="durata del video in secondi (durSec)")
    ap.add_argument("--faccia", default="52% 37%",
                    help='faceOrigin CSS, es. "52%% 37%%"')
    ap.add_argument("--uscita", required=True, help="dove scrivere regia.json")
    ap.add_argument("--corpus", required=True, help="percorso di CORPUS-REGIA.md")
    ap.add_argument("--analogie", required=True, help="percorso di ANALOGIE.md")
    args = ap.parse_args()

    modello = os.environ.get("LLM_MODELLO_REGIA", MODELLO_DEFAULT)
    trascritto = json.loads(Path(args.transcript).read_text(encoding="utf-8"))
    mappa = mappa_parole(trascritto["segments"])
    if not mappa:
        raise llm.EsitoPermanente("componi_regia: il trascritto non contiene parole")
    takes = carica_takes(args.takes)
    proposte = Path(args.proposte).read_text(encoding="utf-8")

    # Un blocco system unico (regole + anti-injection + corpus + analogie):
    # llm.giudica mette il cache_control sull'unico blocco, quindi sull'ultimo.
    system = (SYSTEM_BASE + Path(args.corpus).read_text(encoding="utf-8")
              + SEPARATORE_ANALOGIE + Path(args.analogie).read_text(encoding="utf-8"))

    contenuto = (f"DURATA DEL VIDEO: {args.durata:.2f} secondi\n"
                 f"FACCIA (faceOrigin): {args.faccia}\n\n"
                 f"PROPOSTE DELLA MAPPA VISIVA (i secondi sono un riferimento, "
                 f"rispondi a indici):\n{proposte}\n\n"
                 f"TRASCRITTO INDICIZZATO (seg N | indice:parola):\n"
                 f"{trascritto_indicizzato(trascritto['segments'])}")

    piano, usage, costo = llm.giudica(
        "componi_regia", modello, system, contenuto, RegiaProposta,
        max_tokens=MAX_TOKENS, timeout_s=1800.0)

    eventi = [e for e in (converti_evento(ev, mappa, args.durata)
                          for ev in piano.eventi) if e is not None]
    if not eventi:
        raise llm.EsitoPermanente(
            "componi_regia: zero eventi validi dopo la conversione",
            passo="componi_regia", modello=modello, usage=usage, costo=costo)
    eventi = ripara_geometria(eventi)
    punches = converti_punches(piano.punches, mappa, args.durata)

    regia = {"fps": 30, "durSec": args.durata, "faceOrigin": args.faccia,
             "takes": takes, "punches": punches, "events": eventi}
    Path(args.uscita).write_text(json.dumps(regia, ensure_ascii=False, indent=1),
                                 encoding="utf-8")

    # Il canone si valida sempre, sul file appena scritto. Il validatore e'
    # deterministico: la chiave API non gli serve e non deve vederla.
    ambiente = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    esito = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "valida_canone.py"),
         "--regia", args.uscita, "--durata", f"{args.durata:.2f}"],
        capture_output=True, text=True, env=ambiente)
    if esito.returncode != 0:
        print("valida_canone bocciato sulla regia:", file=sys.stderr)
        print(esito.stderr, file=sys.stderr)
        # la regia bocciata si conserva accanto all'uscita: il worker cancella
        # il file d'uscita (giusto: non va riusato), ma senza una copia la
        # diagnosi della bocciatura non avrebbe materiale
        try:
            Path(args.uscita + ".bocciata.json").write_text(
                Path(args.uscita).read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass
        # la chiamata LLM e' stata pagata: il JSON con le chiamate si stampa
        # COMUNQUE prima di uscire 1, o il costo sparirebbe dal DB (decisione 5)
        llm.stampa_esito(
            {"valida_canone": "bocciato", "violazioni": esito.stderr[-2000:]},
            [llm.voce_chiamata("componi_regia", modello, usage, costo)])
        return 1

    llm.stampa_esito(
        {"uscita": args.uscita, "eventi": len(eventi),
         "eventi_proposti": len(piano.eventi), "punches": len(punches),
         "takes": len(takes), "durSec": args.durata, "valida_canone": "ok"},
        [llm.voce_chiamata("componi_regia", modello, usage, costo)])
    return 0


if __name__ == "__main__":
    llm.esegui_cli(main)
