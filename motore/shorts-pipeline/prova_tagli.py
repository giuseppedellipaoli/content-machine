"""Prove del taglio dentro una clip: i pezzi, il RIBASAMENTO, la soglia.

Deterministiche, senza rete e senza ffmpeg: si provano i moduli puri
(tagli.py, silenzi.py) e la costruzione dei sottotitoli di render.py, che e'
codice puro anche lei.

IL PESO STA SUL RIBASAMENTO, ed e' voluto. Il progetto da cui arriva questa
funzione non l'ha mai risolto — nelle loro specifiche i tempi di parola dopo
un taglio restano quelli di prima, ed e' un difetto dichiarato. Non c'e' un
esempio da copiare, quindi la verifica la facciamo qui, sui quattro casi che
lo rompono:

    A) una parola tolta in mezzo
    B) due tagli consecutivi
    C) un taglio che cade dentro una sillaba del karaoke
    D) un taglio all'inizio e uno alla fine

piu' la prova che vale piu' di tutte: SENZA buchi il file dei sottotitoli
deve uscire identico, carattere per carattere, a quello che usciva prima che
questo file esistesse.

Uso:
    py prova_tagli.py

Esce 0 se tutte passano, 1 alla prima che fallisce (dicendo quale).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import config
import render
import silenzi
import tagli

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FALLITE: list[str] = []
PASSATE = 0


def prova(nome: str, ottenuto, atteso) -> None:
    global PASSATE
    if ottenuto == atteso:
        PASSATE += 1
        print(f"  ok   {nome}")
    else:
        FALLITE.append(nome)
        print(f"  NO   {nome}\n       atteso   {atteso}\n       ottenuto {ottenuto}")


def prova_vero(nome: str, condizione, dettaglio: str = "") -> None:
    prova(nome, bool(condizione), True) if condizione else _fallisci(nome, dettaglio)


def _fallisci(nome: str, dettaglio: str) -> None:
    FALLITE.append(nome)
    print(f"  NO   {nome}" + (f"\n       {dettaglio}" if dettaglio else ""))


def prova_solleva(nome: str, funzione, pezzo_atteso: str, tipo=Exception) -> None:
    global PASSATE
    try:
        funzione()
    except tipo as errore:
        if pezzo_atteso.lower() in str(errore).lower():
            PASSATE += 1
            print(f"  ok   {nome}")
        else:
            _fallisci(nome, f"il messaggio non dice '{pezzo_atteso}': {errore}")
        return
    except Exception as errore:  # noqa: BLE001 — qui interessa proprio il tipo
        _fallisci(nome, f"sollevato {type(errore).__name__} invece di {tipo.__name__}")
        return
    _fallisci(nome, "non ha sollevato niente")


def vicino(a, b, tolleranza=1e-6) -> bool:
    return abs(float(a) - float(b)) <= tolleranza


def tempi(parole) -> list:
    return [(p["idx"], round(p["start"], 3), round(p["end"], 3)) for p in parole]


# ---------------------------------------------------------------- materiale
#
# Un trascritto piccolo con la forma vera di build/transcript.json. I tempi
# sono scelti per cadere sui casi che contano: una pausa lunga fra la 3 e la
# 4, una parola breve, e una parola che il taglio attraversa a meta'.

def trascritto():
    return [
        {"id": 0, "start": 0.0, "end": 6.0, "text": "uno due tre quattro",
         "words": [
             {"w": "uno", "start": 1.00, "end": 1.40},
             {"w": "due", "start": 1.45, "end": 1.90},
             {"w": "tre", "start": 2.00, "end": 2.50},
             # pausa di 2 secondi: il candidato al taglio
             {"w": "quattro", "start": 4.50, "end": 5.20},
         ]},
        {"id": 1, "start": 6.0, "end": 12.0, "text": "cinque sei sette otto",
         "words": [
             {"w": "cinque", "start": 6.00, "end": 6.60},
             {"w": "sei", "start": 6.70, "end": 7.20},
             {"w": "sette", "start": 7.30, "end": 8.10},
             {"w": "otto", "start": 8.20, "end": 9.00},
         ]},
    ]


def parole():
    return tagli.numera_parole(trascritto())


def celle_costanti(da: float, a: float, db: float) -> list[dict]:
    """Un tratto di livello piatto, cella per cella."""
    celle = []
    t = da
    while t < a - 1e-9:
        celle.append({"t_inizio": t, "t_fine": min(a, t + silenzi.DURATA_CELLA_S), "db": db})
        t += silenzi.DURATA_CELLA_S
    return celle


print("\n--- il file dei tagli: cosa si accetta e cosa no ---")

def scrivi(testo: str) -> Path:
    cartella = Path(tempfile.mkdtemp())
    percorso = cartella / "tagli.json"
    percorso.write_text(testo, encoding="utf-8")
    return percorso


prova("file assente = nessun taglio", tagli.leggi(Path(tempfile.mkdtemp()) / "no.json"), {})
prova("file vuoto = nessun taglio", tagli.leggi(scrivi("   ")), {})
prova_solleva("versione mancante",
              lambda: tagli.leggi(scrivi('{"clip": {}}')),
              "non dichiara il campo 'versione'", tagli.TaglioNonValido)
prova_solleva("versione ignota",
              lambda: tagli.leggi(scrivi('{"versione": 9, "clip": {}}')),
              "versione 9", tagli.TaglioNonValido)
prova_solleva("campo inventato dentro un buco",
              lambda: tagli.leggi(scrivi(
                  '{"versione": 1, "clip": {"short_01_x": {"buchi": '
                  '[{"inizio": 1, "fine": 2, "inzio": 3}]}}}')),
              "campi che non esistono", tagli.TaglioNonValido)
prova_solleva("buco rovesciato",
              lambda: tagli.leggi(scrivi(
                  '{"versione": 1, "clip": {"short_01_x": {"buchi": '
                  '[{"inizio": 5, "fine": 2}]}}}')),
              "deve finire dopo che comincia", tagli.TaglioNonValido)
prova_solleva("motivo sconosciuto",
              lambda: tagli.leggi(scrivi(
                  '{"versione": 1, "clip": {"short_01_x": {"buchi": '
                  '[{"inizio": 1, "fine": 2, "motivo": "boh"}]}}}')),
              "sconosciuto", tagli.TaglioNonValido)
prova_solleva("stessa clip con due nomi",
              lambda: tagli.leggi(scrivi(
                  '{"versione": 1, "clip": {"short_01_x": {"buchi": []}, '
                  '"out/short_01_x-FX.mp4": {"buchi": []}}}')),
              "compare due volte", tagli.TaglioNonValido)
letto = tagli.leggi(scrivi(
    '{"versione": 1, "clip": {"out/short_01_x-FX.mp4": {"buchi": '
    '[{"inizio": 2.5, "fine": 4.5}], "firma_trascritto": "abc"}}}'))
prova("il nome si riduce alla chiave unica", sorted(letto), ["short_01_x"])
prova("un buco di silenzio si verifica di serie",
      letto["short_01_x"]["buchi"][0]["verifica_livello"], True)
prova("un buco di parole non si verifica",
      tagli.leggi(scrivi(
          '{"versione": 1, "clip": {"short_01_x": {"buchi": '
          '[{"inizio": 1, "fine": 2, "motivo": "parole", "parole": [3, 5]}]}}}'
      ))["short_01_x"]["buchi"][0]["verifica_livello"], False)


print("\n--- i pezzi ---")

senza = tagli.pezzi_da_buchi(1.0, 9.0, [])
prova("nessun buco = un pezzo solo", [(p["inizio"], p["fine"], p["offset"]) for p in senza],
      [(1.0, 9.0, 0.0)])
prova("i bordi esterni non sono tagli",
      (senza[0]["taglia_inizio"], senza[0]["taglia_fine"]), (False, False))

# A) un buco in mezzo
uno = tagli.pezzi_da_buchi(1.0, 9.0, [{"inizio": 2.6, "fine": 4.4, "motivo": "silenzio"}])
prova("un buco in mezzo = due pezzi",
      [(p["inizio"], p["fine"], p["offset"]) for p in uno],
      [(1.0, 2.6, 0.0), (4.4, 9.0, 1.6)])
prova("il bordo interno e' dichiarato taglio",
      (uno[0]["taglia_fine"], uno[1]["taglia_inizio"]), (True, True))
prova("i bordi esterni restano esterni",
      (uno[0]["taglia_inizio"], uno[1]["taglia_fine"]), (False, False))
prova("durata dopo un buco", round(tagli.durata_pezzi(uno), 3), 6.2)

# B) due tagli consecutivi
due = tagli.pezzi_da_buchi(1.0, 9.0, [
    {"inizio": 2.6, "fine": 3.6, "motivo": "silenzio"},
    {"inizio": 6.0, "fine": 6.5, "motivo": "parole"},
])
prova("due tagli = tre pezzi, offset cumulativi",
      [(p["inizio"], p["fine"], round(p["offset"], 3)) for p in due],
      [(1.0, 2.6, 0.0), (3.6, 6.0, 1.6), (6.5, 9.0, 4.0)])
prova("durata dopo due tagli", round(tagli.durata_pezzi(due), 3), 6.5)

# D) un taglio in testa e uno in coda
testa_coda = tagli.pezzi_da_buchi(1.0, 9.0, [
    {"inizio": 0.5, "fine": 2.0, "motivo": "silenzio"},
    {"inizio": 8.5, "fine": 12.0, "motivo": "silenzio"},
])
prova("buchi a cavallo dei bordi: si intersecano col taglio",
      [(p["inizio"], p["fine"], p["offset"]) for p in testa_coda], [(2.0, 8.5, 0.0)])
prova("un buco in testa rende il bordo iniziale un taglio",
      (testa_coda[0]["taglia_inizio"], testa_coda[0]["taglia_fine"]), (True, True))

prova("buchi sovrapposti si fondono",
      [(p["inizio"], p["fine"]) for p in tagli.pezzi_da_buchi(0.0, 10.0, [
          {"inizio": 2.0, "fine": 5.0, "motivo": "silenzio"},
          {"inizio": 4.0, "fine": 6.0, "motivo": "parole"},
      ])], [(0.0, 2.0), (6.0, 10.0)])
prova("un buco tutto fuori dal taglio non toglie niente",
      [(p["inizio"], p["fine"]) for p in tagli.pezzi_da_buchi(5.0, 9.0, [
          {"inizio": 1.0, "fine": 2.0, "motivo": "silenzio"}])], [(5.0, 9.0)])
prova("un pezzo piu' corto di due fotogrammi si assorbe",
      [(p["inizio"], p["fine"]) for p in tagli.pezzi_da_buchi(0.0, 10.0, [
          {"inizio": 0.05, "fine": 4.0, "motivo": "silenzio"}])], [(4.0, 10.0)])

prova("tempo nella clip, primo pezzo", tagli.tempo_nella_clip(uno, 2.0), 1.0)
prova("tempo nella clip, secondo pezzo", round(tagli.tempo_nella_clip(uno, 5.4), 3), 2.6)
prova("un istante tolto non ha un tempo nella clip", tagli.tempo_nella_clip(uno, 3.5), None)
prova("un istante tolto si aggancia alla saldatura",
      tagli.tempo_agganciato(uno, 3.5), (1.6, False))


print("\n--- il ribasamento delle parole (il pezzo che loro non hanno risolto) ---")

# Senza buchi: i tempi devono valere ESATTAMENTE start - inizio.
ribasate = tagli.ribasa_parole(parole(), senza)
prova("senza buchi la ribasatura e' la sottrazione di sempre",
      all(p["start"] == p0["start"] - 1.0 and p["end"] == p0["end"] - 1.0
          for p, p0 in zip(ribasate, [x for x in parole() if x["start"] >= 1.0])), True)
prova("senza buchi ci sono tutte le parole dentro il taglio", len(ribasate), 8)

# A) una parola tolta in mezzo: la 3 ('quattro', 4.50-5.20).
buco_parola = silenzi.buco_da_parole(parole(), 3, 3)
prova("il buco di una parola prende il respiro senza entrare nella vicina",
      (buco_parola["inizio"], buco_parola["fine"]), (4.46, 5.24))
pezzi_parola = tagli.pezzi_da_buchi(1.0, 9.0, [buco_parola])
dopo = tagli.ribasa_parole(parole(), pezzi_parola)
prova("la parola tolta sparisce", [p["idx"] for p in dopo], [0, 1, 2, 4, 5, 6, 7])
prova("le parole prima del buco non si muovono",
      tempi([p for p in dopo if p["idx"] < 3]),
      [(0, 0.0, 0.4), (1, 0.45, 0.9), (2, 1.0, 1.5)])
# il buco dura 5.24-4.46 = 0.78 s: 'cinque' stava a 6.00-1.00 = 5.00 e va a 4.22
prova("le parole dopo il buco arretrano ESATTAMENTE della sua durata",
      tempi([p for p in dopo if p["idx"] == 4]), [(4, 4.22, 4.82)])
prova("l'ultima parola arretra della stessa quantita'",
      tempi([p for p in dopo if p["idx"] == 7]), [(7, 6.42, 7.22)])
prova("la durata della clip cala della durata del buco",
      round(tagli.durata_pezzi(pezzi_parola), 3), round(8.0 - 0.78, 3))

# B) due tagli consecutivi: si tolgono la 3 e poi la 5.
buco_a = silenzi.buco_da_parole(parole(), 3, 3)          # 4.46 - 5.24  (0.78)
buco_b = silenzi.buco_da_parole(parole(), 5, 5)          # 6.66 - 7.24  (0.58)
pezzi_due = tagli.pezzi_da_buchi(1.0, 9.0, [buco_a, buco_b])
dopo_due = tagli.ribasa_parole(parole(), pezzi_due)
prova("due tagli: spariscono tutte e due le parole",
      [p["idx"] for p in dopo_due], [0, 1, 2, 4, 6, 7])
prova("fra i due tagli si arretra solo del primo",
      tempi([p for p in dopo_due if p["idx"] == 4]), [(4, 4.22, 4.82)])
prova("dopo il secondo taglio si arretra della SOMMA dei due",
      tempi([p for p in dopo_due if p["idx"] == 6]),
      [(6, round(7.30 - 1.0 - 0.78 - 0.58, 3), round(8.10 - 1.0 - 0.78 - 0.58, 3))])
prova("l'ordine in cui arrivano i buchi non cambia il risultato",
      tempi(tagli.ribasa_parole(parole(), tagli.pezzi_da_buchi(1.0, 9.0, [buco_b, buco_a]))),
      tempi(dopo_due))

# C) un taglio che cade DENTRO una parola (la sillaba del karaoke).
#    'sette' sta a 7.30-8.10: si taglia da 7.70 in poi.
pezzi_sillaba = tagli.pezzi_da_buchi(1.0, 9.0, [
    {"inizio": 7.70, "fine": 8.30, "motivo": "silenzio", "verifica_livello": False}])
dopo_sillaba = tagli.ribasa_parole(parole(), pezzi_sillaba)
sette = [p for p in dopo_sillaba if p["idx"] == 6][0]
prova("la parola tagliata a meta' si stringe sulla parte visibile",
      (round(sette["start"], 3), round(sette["end"], 3)), (6.3, 6.7))
prova("la parte visibile non supera MAI la saldatura",
      round(sette["end"], 3), round(tagli.durata_pezzi([pezzi_sillaba[0]]), 3))
prova("la parola dopo il buco arretra della durata del buco",
      tempi([p for p in dopo_sillaba if p["idx"] == 7]), [(7, 6.7, 7.4)])
prova("'otto' attacca esattamente dove 'sette' finisce (nessun buco nei tempi)",
      round([p for p in dopo_sillaba if p["idx"] == 7][0]["start"], 6),
      round(sette["end"], 6))

# una parola ridotta a un'inezia esce dai sottotitoli ma non dalla numerazione
pezzi_briciola = tagli.pezzi_da_buchi(1.0, 9.0, [
    {"inizio": 7.33, "fine": 8.15, "motivo": "silenzio", "verifica_livello": False}])
dopo_briciola = tagli.ribasa_parole(parole(), pezzi_briciola)
prova("una parola ridotta sotto i 50 ms visibili esce dai sottotitoli",
      [p["idx"] for p in dopo_briciola], [0, 1, 2, 3, 4, 5, 7])
prova("gli indici delle altre non si spostano di uno",
      [p["idx"] for p in dopo_briciola][-1], 7)

# D) un taglio all'inizio e uno alla fine.
pezzi_bordi = tagli.pezzi_da_buchi(1.0, 9.0, [
    {"inizio": 1.0, "fine": 1.42, "motivo": "parole", "verifica_livello": False},
    {"inizio": 8.18, "fine": 9.0, "motivo": "parole", "verifica_livello": False},
])
dopo_bordi = tagli.ribasa_parole(parole(), pezzi_bordi)
prova("il taglio in testa toglie la prima parola e azzera l'attacco",
      [p["idx"] for p in dopo_bordi], [1, 2, 3, 4, 5, 6])
prova("la prima parola rimasta attacca a zero",
      round(dopo_bordi[0]["start"], 3), round(1.45 - 1.42, 3))
prova("il taglio in coda toglie l'ultima parola",
      7 in [p["idx"] for p in dopo_bordi], False)
prova("l'ultima parola rimasta finisce dentro la durata",
      round(dopo_bordi[-1]["end"], 3) <= round(tagli.durata_pezzi(pezzi_bordi), 3), True)

# le fusioni dei sottotitoli non attraversano un taglio
brevi = [
    {"idx": 0, "w": "a", "start": 0.0, "end": 0.02, "durata_s": 0.02, "pezzo": 0},
    {"idx": 1, "w": "b", "start": 0.02, "end": 0.04, "durata_s": 0.02, "pezzo": 0},
    {"idx": 2, "w": "c", "start": 0.04, "end": 0.06, "durata_s": 0.02, "pezzo": 1},
]
prova("due parole brevi dello stesso pezzo si fondono",
      [p["w"] for p in tagli.unisci_brevi(brevi, 60)], ["a b", "c"])


print("\n--- i sottotitoli veri (build_ass di render.py) ---")


def collect_words_di_prima(segments, start, end):
    """La collect_words com'era PRIMA dei tagli, per il confronto."""
    words = []
    for seg in segments:
        if seg["end"] < start or seg["start"] > end:
            continue
        for w in seg["words"]:
            if w["end"] <= start or w["start"] >= end:
                continue
            words.append(dict(w))
    merged = []
    for w in words:
        if merged and (w["end"] - w["start"]) * 1000 < config.MIN_WORD_MS:
            merged[-1]["w"] += " " + w["w"]
            merged[-1]["end"] = w["end"]
        else:
            merged.append(w)
    return merged


prima = render.build_ass(collect_words_di_prima(trascritto(), 1.0, 9.0), 1.0, "Arial")
adesso = render.build_ass(render.collect_words(trascritto(), senza), 0.0, "Arial")
prova("SENZA buchi il file .ass e' identico, carattere per carattere", adesso, prima)


def righe_dialogo(testo: str):
    """(inizio, fine) di ogni riga di dialogo, in secondi."""
    fuori = []
    for riga in testo.splitlines():
        if not riga.startswith("Dialogue:"):
            continue
        pezzi_riga = riga.split(",")
        def secondi(marca: str) -> float:
            ore, minuti, resto = marca.split(":")
            return int(ore) * 3600 + int(minuti) * 60 + float(resto)
        fuori.append((secondi(pezzi_riga[1]), secondi(pezzi_riga[2])))
    return fuori


ass_sillaba = render.build_ass(render.collect_words(trascritto(), pezzi_sillaba), 0.0, "Arial")
righe = righe_dialogo(ass_sillaba)
durata_sillaba = tagli.durata_pezzi(pezzi_sillaba)
prova("karaoke: nessuna riga comincia dopo la fine della clip",
      all(a <= durata_sillaba + 1e-6 for a, _ in righe), True)
prova("karaoke: i tempi restano monotoni attraverso il taglio",
      all(righe[n][0] <= righe[n + 1][0] + 1e-9 for n in range(len(righe) - 1)), True)
prova("karaoke: nessuna riga di durata nulla o negativa",
      all(b > a for a, b in righe), True)
pagine = render.paginate(render.collect_words(trascritto(), pezzi_due), 0.0)
prova("nessuna pagina di sottotitoli sta a cavallo di un taglio",
      all(len({p["pezzo"] for p in pagina}) == 1 for pagina in pagine), True)
prova("le parole dei due lati del taglio finiscono su pagine diverse",
      [[p["idx"] for p in pagina] for pagina in pagine], [[0, 1], [2], [4], [6, 7]])


print("\n--- la soglia: relativa al parlato, mai assoluta ---")

# T4 della specifica: voce a -8 dBFS, letto musicale continuo a -18.
celle_musica = celle_costanti(1.0, 2.5, -8.0) + celle_costanti(2.5, 4.5, -18.0) \
    + celle_costanti(4.5, 9.0, -8.0)
parlato_finto = [{"start": 1.0, "end": 2.5}, {"start": 4.5, "end": 9.0}]
soglia_musica = silenzi.soglia_relativa(celle_musica, parlato_finto)
prova("parlato a -8: la soglia si ferma al tetto di -22", soglia_musica["db"], -22.0)
prova("e dichiara di essere relativa", soglia_musica["tipo"], "relativa")
tenuti, vetati = silenzi.veta_per_livello(
    [{"inizio": 2.6, "fine": 4.4, "motivo": "silenzio", "verifica_livello": True}],
    celle_musica, soglia_musica)
prova("IL LETTO MUSICALE SOPRAVVIVE: la pausa non si taglia", (len(tenuti), len(vetati)), (0, 1))
prova("e il motivo dice il livello misurato e la soglia",
      ("-18.0" in vetati[0]["motivo_veto"] and "-22.0" in vetati[0]["motivo_veto"]), True)

# Lo stesso identico tratto, ma con il vero silenzio sotto: si taglia.
celle_silenzio = celle_costanti(1.0, 2.5, -8.0) + celle_costanti(2.5, 4.5, -55.0) \
    + celle_costanti(4.5, 9.0, -8.0)
tenuti2, vetati2 = silenzi.veta_per_livello(
    [{"inizio": 2.6, "fine": 4.4, "motivo": "silenzio", "verifica_livello": True}],
    celle_silenzio, silenzi.soglia_relativa(celle_silenzio, parlato_finto))
prova("con il silenzio vero sotto, la stessa pausa si taglia",
      (len(tenuti2), len(vetati2)), (1, 0))

# Parlato sommesso: la soglia scende ma si ferma al pavimento.
celle_piano = celle_costanti(1.0, 3.0, -30.0)
prova("parlato a -30: la soglia si ferma al pavimento di -40",
      silenzi.soglia_relativa(celle_piano, [{"start": 1.0, "end": 3.0}])["db"], -40.0)
# Parlato normale: la soglia sta 12 dB sotto, senza toccare i limiti.
celle_normale = celle_costanti(1.0, 3.0, -20.0)
prova("parlato a -20: la soglia sta 12 dB sotto, cioe' -32",
      silenzi.soglia_relativa(celle_normale, [{"start": 1.0, "end": 3.0}])["db"], -32.0)
senza_parlato = silenzi.soglia_relativa(celle_costanti(0.0, 2.0, -50.0), [])
prova("senza parlato misurabile si ripiega su -28", senza_parlato["db"], -28.0)
prova("e lo dichiara come ripiego assoluto", senza_parlato["tipo"], "ripiego_assoluto")

# La mediana: un colpo isolato non salva una pausa vuota.
celle_colpo = celle_costanti(2.5, 4.4, -55.0)
celle_colpo[10]["db"] = -3.0
celle_colpo[11]["db"] = -3.0
tenuti3, vetati3 = silenzi.veta_per_livello(
    [{"inizio": 2.5, "fine": 4.4, "motivo": "silenzio", "verifica_livello": True}],
    celle_costanti(1.0, 2.5, -8.0) + celle_colpo,
    {"db": -22.0, "tipo": "relativa"})
prova("un colpo isolato non salva la pausa (decide la mediana)", len(tenuti3), 1)
# Un rumore su piu' di meta' della corsa invece la salva.
celle_rumore = celle_costanti(2.5, 4.4, -18.0)
for n in range(10):
    celle_rumore[n]["db"] = -55.0
tenuti4, vetati4 = silenzi.veta_per_livello(
    [{"inizio": 2.5, "fine": 4.4, "motivo": "silenzio", "verifica_livello": True}],
    celle_rumore, {"db": -22.0, "tipo": "relativa"})
prova("un rumore su piu' di meta' della corsa la salva", len(vetati4), 1)
prova("un buco di parole non passa mai dal veto del livello",
      len(silenzi.veta_per_livello(
          [{"inizio": 2.5, "fine": 4.4, "motivo": "parole", "verifica_livello": False}],
          celle_rumore, {"db": -22.0, "tipo": "relativa"})[0]), 1)


print("\n--- le pause candidate lette dal trascritto ---")

candidate = silenzi.pause_candidate(parole(), 1.0, 9.0)
prova("solo le due corse sopra il mezzo secondo diventano candidate",
      [(c["inizio"], c["fine"]) for c in candidate], [(2.65, 4.35), (5.35, 5.85)])
prova("e il margine e' tolto dai due lati",
      round(candidate[0]["fine"] - candidate[0]["inizio"], 3),
      round(2.0 - 2 * silenzi.MARGINE_PARLATO_S, 3))
prova("le sette pause sotto il mezzo secondo restano dov'erano",
      len(candidate), 2)
prova("la pausa e' un candidato da verificare col livello",
      candidate[0]["verifica_livello"], True)
prova("con la pausa minima a 3 s non resta niente",
      silenzi.pause_candidate(parole(), 1.0, 9.0, pausa_minima_s=3.0), [])
# Il padding d'attacco (config.PAD_START_S = -0.20) non deve essere disfatto:
# in testa alla clip c'e' una corsa di 0,2 s, sotto la pausa minima.
prova("il padding d'attacco sopravvive: la testa non e' una pausa",
      all(c["inizio"] > 1.0 for c in silenzi.pause_candidate(parole(), 0.80, 9.0)), True)
prova("i limiti riportano dentro i valori fuori scala",
      silenzi.entro_limiti(0.01, 9.0), (0.25, 0.5))
prova("valori assenti = i valori di fabbrica",
      silenzi.entro_limiti(None, None), (0.5, 0.15))


print("\n--- togliere parole nominate ---")

buco_frase = silenzi.buco_da_parole(parole(), 4, 6)
prova("dalla 4 alla 6: il buco copre tutte e tre",
      (buco_frase["inizio"], buco_frase["fine"]), (5.96, 8.14))
prova("il buco non entra nella parola precedente",
      buco_frase["inizio"] >= 5.20, True)
prova("ne' in quella successiva", buco_frase["fine"] <= 8.20, True)
prova("porta con se' gli indici nominati", buco_frase["parole"], [4, 6])
prova_solleva("una parola che non esiste",
              lambda: silenzi.buco_da_parole(parole(), 4, 99),
              "non esiste nel trascritto", ValueError)
prova_solleva("indici rovesciati",
              lambda: silenzi.buco_da_parole(parole(), 6, 4),
              "rovesciati", ValueError)


print("\n--- la durata minima ---")

# Clip di 14 s, minimo 12: c'e' spazio per 2 s di tagli e non di piu'.
tenuti5, lasciati5, avvisi5 = tagli.entro_durata_minima([
    {"inizio": 1.0, "fine": 2.5, "motivo": "silenzio"},    # 1,5 s
    {"inizio": 5.0, "fine": 5.9, "motivo": "silenzio"},    # 0,9 s
    {"inizio": 9.0, "fine": 9.4, "motivo": "silenzio"},    # 0,4 s
], 0.0, 14.0, 12.0)
prova("si tengono prima i buchi piu' lunghi",
      [(b["inizio"], b["fine"]) for b in tenuti5], [(1.0, 2.5), (9.0, 9.4)])
prova("quelli che sforerebbero il minimo si dichiarano",
      [(b["inizio"], b["fine"]) for b in lasciati5], [(5.0, 5.9)])
prova("e l'avviso lo dice", "durata minima" in avvisi5[0]["motivo"], True)
prova("sotto il minimo non si taglia niente",
      tagli.entro_durata_minima([{"inizio": 1.0, "fine": 3.0, "motivo": "silenzio"}],
                                0.0, 12.5, 12.0)[0], [])


print("\n--- il ribasamento del piano degli overlay ---")

piano = [
    {"type": "pill", "text": "banner"},                                  # senza tempi
    {"type": "hook", "t0": 0.1, "t1": 0.55, "text": "tutto prima del buco"},
    {"type": "claim", "t0": 0.4, "t1": 1.4, "text": "meta' dentro il buco"},
    {"type": "card", "t0": 1.8, "t1": 3.2, "text": "tutto dentro il buco"},
    {"type": "list", "t0": 4.0, "t1": 6.0, "header": "dopo",
     "items": [{"t": 2.0, "text": "sparisce"}, {"t": 4.5, "text": "resta"}]},
    {"type": "stamp", "t": 5.0},
]
# clip 1-9 con un buco 1.6-4.4 del girato -> in secondi della clip: 0.6-3.4
pezzi_piano = tagli.pezzi_da_buchi(1.0, 9.0, [{"inizio": 1.6, "fine": 4.4, "motivo": "silenzio"}])
# i tempi del piano sono nella scala della clip PRIMA: qui si ribasano coi
# pezzi espressi nella stessa scala
pezzi_clip = tagli.pezzi_da_buchi(0.0, 8.0, [{"inizio": 0.6, "fine": 3.4, "motivo": "silenzio"}])
tenuto, scartato = tagli.ribasa_piano(piano, pezzi_clip)
per_tipo = {e["type"]: e for e in tenuto}
prova("il banner senza tempi resta com'e'", per_tipo["pill"], {"type": "pill", "text": "banner"})
prova("l'evento dentro il buco e quello schiacciato dal buco si scartano",
      sorted(e["type"] for e in scartato), ["card", "claim"])
prova("e il motivo dice che il parlato non c'e' piu'",
      "il taglio ha tolto il parlato" in scartato[0]["motivo"], True)
prova("l'evento tutto prima del taglio non si muove",
      (per_tipo["hook"]["t0"], per_tipo["hook"]["t1"]), (0.1, 0.55))
prova("l'evento dopo il taglio arretra di 2,8 s",
      (per_tipo["list"]["t0"], per_tipo["list"]["t1"]), (1.2, 3.2))
prova("lo stamp dopo il taglio arretra della stessa quantita'", per_tipo["stamp"]["t"], 2.2)
prova("la riga di lista finita nel buco sparisce",
      [v["text"] for v in per_tipo["list"]["items"]], ["resta"])
prova("la riga di lista rimasta e' ribasata", per_tipo["list"]["items"][0]["t"], 1.7)
prova("nessun tempo esce dalla durata nuova",
      all(e.get("t1", 0) <= tagli.durata_pezzi(pezzi_clip) + 1e-9 for e in tenuto), True)
prova("senza buchi il piano non cambia di una virgola",
      tagli.ribasa_piano(piano, tagli.pezzi_da_buchi(0.0, 8.0, []))[0], piano)


print("\n--- la firma della numerazione ---")

firma = tagli.firma_numerazione(parole())
refuso = trascritto()
refuso[0]["words"][0]["w"] = "UNO!"   # fix_transcript tocca solo il testo
prova("correggere un refuso NON cambia la firma",
      tagli.firma_numerazione(tagli.numera_parole(refuso)), firma)
ritrascritto = trascritto()
ritrascritto[0]["words"][0]["start"] = 1.01
prova("ritrascrivere il girato la cambia",
      tagli.firma_numerazione(tagli.numera_parole(ritrascritto)) != firma, True)
prova("la firma e' lunga 16 caratteri", len(firma), 16)
print(f"       (firma del trascritto di prova: {firma})")


print("\n--- il comando ffmpeg ---")

comando_uno = render.comando_pezzi(Path("g.mp4"), senza, Path("o.mp4"))
prova("con un pezzo solo si resta sul taglio secco di sempre",
      ("-ss" in comando_uno and "-t" in comando_uno
       and "-filter_complex" not in comando_uno), True)
prova("e i due numeri sono quelli del pezzo",
      (comando_uno[comando_uno.index("-ss") + 1], comando_uno[comando_uno.index("-t") + 1]),
      ("1.000", "8.000"))
comando_due = render.comando_pezzi(Path("g.mp4"), due, Path("o.mp4"))
filtro = comando_due[comando_due.index("-filter_complex") + 1]
prova("con piu' pezzi si passa dal filtro", "concat=n=3:v=1:a=1" in filtro, True)
prova("vicino all'inizio del girato il seek non va sotto zero",
      comando_due[comando_due.index("-ss") + 1], "0.000")
prova("e allora i tempi del trim sono quelli del girato",
      "trim=start=1.000:end=2.600" in filtro, True)
# Lontano dall'inizio il seek anticipa il primo pezzo, e i trim si spostano
# della stessa quantita': e' li' che si vede se le due cose restano accoppiate.
lontano = tagli.pezzi_da_buchi(600.0, 640.0, [{"inizio": 610.0, "fine": 612.0, "motivo": "silenzio"}])
comando_lontano = render.comando_pezzi(Path("g.mp4"), lontano, Path("o.mp4"))
filtro_lontano = comando_lontano[comando_lontano.index("-filter_complex") + 1]
prova("lontano dall'inizio il seek anticipa il primo pezzo del margine",
      comando_lontano[comando_lontano.index("-ss") + 1],
      f"{600.0 - render.MARGINE_SEEK_S:.3f}")
prova("i tempi del trim sono relativi al punto di seek",
      ("trim=start=2.000:end=12.000" in filtro_lontano
       and "trim=start=14.000:end=42.000" in filtro_lontano), True)


print()
if FALLITE:
    print(f"{PASSATE} passate, {len(FALLITE)} FALLITE: {', '.join(FALLITE)}")
    raise SystemExit(1)
print(f"Tutte passate ({PASSATE}).")
