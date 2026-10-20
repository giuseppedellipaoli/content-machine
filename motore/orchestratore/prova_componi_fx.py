"""Prove della geometria di componi_fx: indici di parola -> secondi della clip.

Deterministiche, senza rete e senza chiave: si prova SOLO la parte che il
codice decide da solo — la conversione delle ancore e la riparazione del
canone — non il giudizio del modello.

PERCHE' ADESSO. Da quando si puo' togliere una pausa o una frase da dentro
uno short, quella conversione non e' piu' una sottrazione: fra la parola 34 e
la parola 41 puo' esserci un buco, e un evento grafico ancorato dopo il buco
cade a un secondo diverso. E' il ribasamento dei tempi visto dal lato delle
GRAFICHE, ed e' il pezzo che il progetto da cui arriva questa funzione non ha
mai risolto: qui si verifica coi numeri.

Uso:
    py prova_componi_fx.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shorts-pipeline"))

import tagli  # noqa: E402
from componi_fx import EventoFx, PianoFx, VoceLista, converti, parole_della_clip  # noqa: E402

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


# Un trascritto piccolo: due segmenti, otto parole, con una pausa fra la 3 e
# la 4 (gli stessi tempi di prova_tagli.py, cosi' i numeri si confrontano).
SEGMENTI = [
    {"id": 0, "start": 0.0, "end": 6.0, "text": "",
     "words": [
         {"w": "uno", "start": 1.00, "end": 1.40},
         {"w": "due", "start": 1.45, "end": 1.90},
         {"w": "tre", "start": 2.00, "end": 2.50},
         {"w": "quattro", "start": 4.50, "end": 5.20},
     ]},
    {"id": 1, "start": 6.0, "end": 12.0, "text": "",
     "words": [
         {"w": "cinque", "start": 6.00, "end": 6.60},
         {"w": "sei", "start": 6.70, "end": 7.20},
         {"w": "sette", "start": 7.30, "end": 8.10},
         {"w": "otto", "start": 8.20, "end": 9.00},
     ]},
]

INTERO = tagli.pezzi_da_buchi(1.0, 9.0, [])
# lo stesso taglio, ma con la pausa 2.60-4.40 tolta da dentro (1,8 s)
TAGLIATO = tagli.pezzi_da_buchi(1.0, 9.0, [{"inizio": 2.60, "fine": 4.40, "motivo": "silenzio"}])


def piano(*eventi: EventoFx) -> PianoFx:
    return PianoFx(eventi=list(eventi))


print("\n--- la mappa delle parole ---")

mappa_intera = parole_della_clip(SEGMENTI, 0, 1, INTERO)
prova("senza tagli ci sono tutte le parole", sorted(mappa_intera), list(range(8)))
mappa_tagliata = parole_della_clip(SEGMENTI, 0, 1, TAGLIATO)
prova("i pezzi non tolgono parole che stanno fuori dal buco",
      sorted(mappa_tagliata), list(range(8)))
# un buco che copre davvero una parola la fa sparire dalla mappa, e con lei
# ogni evento che ci si ancorava
mappa_senza_quattro = parole_della_clip(
    SEGMENTI, 0, 1,
    tagli.pezzi_da_buchi(1.0, 9.0, [{"inizio": 4.45, "fine": 5.25, "motivo": "parole"}]))
prova("una parola tolta esce dalla mappa", sorted(mappa_senza_quattro),
      [0, 1, 2, 4, 5, 6, 7])
prova("senza pezzi la mappa e' quella di sempre",
      sorted(parole_della_clip(SEGMENTI, 0, 1)), list(range(8)))


print("\n--- la conversione: indici -> secondi della clip ---")

# hook sulla parola 0-2 (tutto prima del buco), card sulla 4-6 (tutto dopo).
eventi = piano(
    EventoFx(type="pill", text="banner"),
    EventoFx(type="hook", kicker="k", text="prima", parola_inizio_idx=0, parola_fine_idx=2),
    EventoFx(type="card", text="dopo", parola_inizio_idx=4, parola_fine_idx=6),
    EventoFx(type="stamp", parola_inizio_idx=7),
)

senza = converti(eventi, mappa_intera, INTERO, tagli.durata_pezzi(INTERO), "GUIDA")
con = converti(eventi, mappa_tagliata, TAGLIATO, tagli.durata_pezzi(TAGLIATO), "GUIDA")


def per_tipo(elenco):
    return {e["type"]: e for e in elenco}


a = per_tipo(senza)
b = per_tipo(con)

# hook: parola 0 attacca a 1.00 del girato = 0.00 della clip, meno il margine
# T0 di 0.1 -> 0 (non si va sotto zero). Non cambia col taglio: e' prima.
prova("l'evento prima del buco non si muove", (a["hook"]["t0"], a["hook"]["t1"]),
      (b["hook"]["t0"], b["hook"]["t1"]))
prova("e i suoi numeri sono quelli attesi", (a["hook"]["t0"], a["hook"]["t1"]), (0.0, 1.8))
# card: parola 4 attacca a 6.00 del girato.
#   senza taglio -> 6.00 - 1.00 - 0.1 = 4.9
#   con il taglio -> (6.00 - 1.00 - 1.8) - 0.1 = 3.1
prova("l'evento dopo il buco arretra della durata del buco",
      (a["card"]["t0"], b["card"]["t0"]), (4.9, 3.1))
prova("e anche la sua fine", (a["card"]["t1"], b["card"]["t1"]), (7.4, 5.6))
# stamp: parola 7 attacca a 8.20 -> 7.2 senza taglio, 5.4 col taglio
prova("lo stamp arretra della stessa quantita'", (a["stamp"]["t"], b["stamp"]["t"]), (7.2, 5.4))
prova("il banner senza ancore resta senza tempi", "t0" in a["pill"], False)

print("\n--- le voci di una lista seguono i pezzi ---")

lista = piano(
    EventoFx(type="pill", text="banner"),
    EventoFx(type="list", header="h", parola_inizio_idx=4, parola_fine_idx=7,
             items=[VoceLista(text="prima riga", parola_idx=4),
                    VoceLista(text="seconda riga", parola_idx=6)]),
)
voci_senza = per_tipo(converti(lista, mappa_intera, INTERO,
                               tagli.durata_pezzi(INTERO), "GUIDA"))["list"]["items"]
voci_con = per_tipo(converti(lista, mappa_tagliata, TAGLIATO,
                             tagli.durata_pezzi(TAGLIATO), "GUIDA"))["list"]["items"]
prova("le righe della lista senza taglio", [v["t"] for v in voci_senza], [5.0, 6.3])
prova("le righe della lista col taglio arretrano di 1,8 s",
      [v["t"] for v in voci_con], [3.2, 4.5])

print("\n--- un evento ancorato a una parola TOLTA si scarta ---")

pezzi_senza_quattro = tagli.pezzi_da_buchi(
    1.0, 9.0, [{"inizio": 4.45, "fine": 5.25, "motivo": "parole"}])
ancorato = piano(
    EventoFx(type="pill", text="banner"),
    EventoFx(type="card", text="sulla parola tolta", parola_inizio_idx=3, parola_fine_idx=3),
    EventoFx(type="hook", kicker="k", text="sopravvive",
             parola_inizio_idx=0, parola_fine_idx=2),
)
esito = converti(ancorato, mappa_senza_quattro, pezzi_senza_quattro,
                 tagli.durata_pezzi(pezzi_senza_quattro), "GUIDA")
tipi = [e["type"] for e in esito]
prova("l'evento sulla parola tolta non c'e' piu'", "card" in tipi, False)
prova("gli altri restano", sorted(set(tipi)), ["cta", "hook", "pill"])

print("\n--- nessun tempo esce dalla durata della clip tagliata ---")

durata_tagliata = tagli.durata_pezzi(TAGLIATO)
prova("tutti i t1 stanno dentro la durata",
      all(e.get("t1", 0) <= durata_tagliata + 1e-9 for e in con), True)
prova("tutti i t0 stanno dentro la durata",
      all(e.get("t0", 0) <= durata_tagliata + 1e-9 for e in con), True)
prova("la durata tagliata e' quella giusta", round(durata_tagliata, 3), 6.2)

print()
if FALLITE:
    print(f"{PASSATE} passate, {len(FALLITE)} FALLITE: {', '.join(FALLITE)}")
    raise SystemExit(1)
print(f"Tutte passate ({PASSATE}).")
