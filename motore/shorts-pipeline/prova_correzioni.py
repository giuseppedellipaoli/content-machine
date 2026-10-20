"""Prova della matematica delle correzioni per clip (limiti e casi estremi).

Deterministica, senza rete, senza ffmpeg, senza brand kit: importa solo
correzioni.py, che apposta non dipende da config.py.

Uso:
    py prova_correzioni.py

Esce 0 se tutte le prove passano, 1 alla prima che fallisce (stampando cosa
si aspettava e cosa e' uscito).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import correzioni

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FALLITE: list[str] = []
PASSATE = 0

# Geometria vera della pipeline: 1920x1080 di sorgente, ritaglio 608 px.
SRC_W = 1920
CROP_W = 608
MASSIMO_X = SRC_W - CROP_W          # 1312
MIN_CLIP_S = 12.0


def prova(nome: str, ottenuto, atteso) -> None:
    global PASSATE
    if ottenuto == atteso:
        PASSATE += 1
        print(f"  ok   {nome}")
    else:
        FALLITE.append(nome)
        print(f"  NO   {nome}\n       atteso  {atteso}\n       ottenuto {ottenuto}")


def prova_solleva(nome: str, funzione, pezzo_atteso: str) -> None:
    global PASSATE
    try:
        funzione()
    except correzioni.CorrezioneNonValida as errore:
        if pezzo_atteso.lower() in str(errore).lower():
            PASSATE += 1
            print(f"  ok   {nome}")
        else:
            FALLITE.append(nome)
            print(f"  NO   {nome}\n       il messaggio non dice '{pezzo_atteso}': {errore}")
        return
    except Exception as errore:  # noqa: BLE001 — qui interessa proprio il tipo
        FALLITE.append(nome)
        print(f"  NO   {nome}\n       sollevato {type(errore).__name__} invece di CorrezioneNonValida")
        return
    FALLITE.append(nome)
    print(f"  NO   {nome}\n       non ha sollevato niente")


# ------------------------------------------------------- nomi delle clip

print("\nNomi delle clip (tutte le forme portano alla stessa chiave)")
for forma in ("short_02_x", "short_02_x.mp4", "out/short_02_x.mp4",
              "short_02_x-FX.mp4", "short_02_x.json", "short_02_x.ass",
              r"/workspace/out/short_02_x.mp4"):
    prova(f"normalizza '{forma}'", correzioni.normalizza_nome(forma), "short_02_x")
# un nome che contiene '-FX' senza esserne la coda non si tocca
prova("'-FX' a meta' nome resta", correzioni.normalizza_nome("short_02_-FX-cose.mp4"),
      "short_02_-FX-cose")


# ------------------------------------------------------ ritaglio: ancora_x

print("\nRitaglio verticale (src 1920, ritaglio 608, x ammessa 0..1312)")

x, dettaglio = correzioni.applica_ancora_x(656, 0.0, SRC_W, CROP_W)
prova("ancora 0 non sposta niente", (x, dettaglio["spostamento_px"], dettaglio["avvisi"]),
      (656, 0, []))

x, dettaglio = correzioni.applica_ancora_x(656, 0.08, SRC_W, CROP_W)
# 656 + 0.08*1920 = 656 + 153.6 = 809.6 -> 810
prova("+8% sposta di 154 px", (x, dettaglio["spostamento_px"]), (810, 154))

x, dettaglio = correzioni.applica_ancora_x(656, -0.08, SRC_W, CROP_W)
prova("-8% sposta a sinistra", (x, dettaglio["spostamento_px"]), (502, -154))

# oltre il bordo destro: si applica il massimo possibile e lo si dice
x, dettaglio = correzioni.applica_ancora_x(656, 0.90, SRC_W, CROP_W)
prova("oltre il bordo destro si ferma al bordo", x, MASSIMO_X)
prova("...e lo dice", len(dettaglio["avvisi"]), 1)
prova("...dicendo quanto ha applicato davvero",
      dettaglio["avvisi"][0]["applicato"], round((MASSIMO_X - 656) / SRC_W, 4))
prova("...e nel campo giusto", dettaglio["avvisi"][0]["campo"], "ancora_x")

x, dettaglio = correzioni.applica_ancora_x(656, -0.90, SRC_W, CROP_W)
prova("oltre il bordo sinistro si ferma a 0", (x, len(dettaglio["avvisi"])), (0, 1))

# esattamente sul bordo: nessun avviso, il limite non e' stato superato
x, dettaglio = correzioni.applica_ancora_x(0, (MASSIMO_X) / SRC_W, SRC_W, CROP_W)
prova("esattamente sul bordo non avvisa", (x, dettaglio["avvisi"]), (MASSIMO_X, []))

# ritaglio largo quanto il girato: non c'e' dove spostarsi
x, dettaglio = correzioni.applica_ancora_x(0, 0.20, 608, CROP_W)
prova("ritaglio largo quanto il girato: x resta 0", (x, len(dettaglio["avvisi"])), (0, 1))

# girato piu' stretto del ritaglio (caso rotto gia' oggi): x resta 0
x, dettaglio = correzioni.applica_ancora_x(-100, 0.0, 480, CROP_W)
prova("girato piu' stretto del ritaglio: x = 0", x, 0)

# valore assurdo: si applica il massimo, non si esplode
x, dettaglio = correzioni.applica_ancora_x(656, 1000.0, SRC_W, CROP_W)
prova("valore assurdo si ferma al bordo", (x, len(dettaglio["avvisi"])), (MASSIMO_X, 1))


# ------------------------------------------------------------ taglio: pad

print("\nTaglio (girato di 600 s, durata minima 12 s)")
DUR = 600.0

inizio, fine, avvisi = correzioni.applica_pad(100.0, 130.0, 0.0, 0.0, DUR, MIN_CLIP_S)
prova("pad nulli non spostano niente", (inizio, fine, avvisi), (100.0, 130.0, []))

inizio, fine, avvisi = correzioni.applica_pad(100.0, 130.0, -2.0, 1.5, DUR, MIN_CLIP_S)
prova("allunga davanti e dietro", (inizio, fine, avvisi), (98.0, 131.5, []))

inizio, fine, avvisi = correzioni.applica_pad(100.0, 130.0, 3.0, -2.5, DUR, MIN_CLIP_S)
prova("accorcia da tutte e due le parti", (inizio, fine, avvisi), (103.0, 127.5, []))

# oltre l'inizio del girato
inizio, fine, avvisi = correzioni.applica_pad(1.0, 40.0, -5.0, 0.0, DUR, MIN_CLIP_S)
prova("non si va prima di 0", (inizio, fine), (0.0, 40.0))
prova("...e lo dice sul campo giusto", (len(avvisi), avvisi[0]["campo"]), (1, "pad_inizio_s"))
prova("...dicendo che di 5 s ne ha applicato 1", avvisi[0]["applicato"], -1.0)

# oltre la fine del girato
inizio, fine, avvisi = correzioni.applica_pad(560.0, 598.0, 0.0, 10.0, DUR, MIN_CLIP_S)
prova("non si va oltre la fine", (inizio, fine), (560.0, 600.0))
prova("...e lo dice sul campo giusto", (len(avvisi), avvisi[0]["campo"]), (1, "pad_fine_s"))
prova("...dicendo che di 10 s ne ha applicato 2", avvisi[0]["applicato"], 2.0)

# entrambi i bordi in una volta
inizio, fine, avvisi = correzioni.applica_pad(2.0, 598.0, -10.0, 10.0, DUR, MIN_CLIP_S)
prova("tutti e due i bordi insieme", (inizio, fine, len(avvisi)), (0.0, 600.0, 2))

# durata minima: accorciando troppo si restituisce dalla coda
inizio, fine, avvisi = correzioni.applica_pad(100.0, 120.0, 15.0, 0.0, DUR, MIN_CLIP_S)
prova("sotto il minimo si riallunga la coda", (inizio, fine), (115.0, 127.0))
prova("...e lo dice", (len(avvisi), avvisi[0]["campo"]), (1, "durata"))
prova("...dicendo durata prima e dopo",
      (avvisi[0]["chiesto"], avvisi[0]["applicato"]), (5.0, 12.0))

# durata minima quando la coda non ha spazio: si prende dall'attacco
inizio, fine, avvisi = correzioni.applica_pad(580.0, 600.0, 15.0, 0.0, DUR, MIN_CLIP_S)
prova("coda contro la fine: si arretra l'attacco", (inizio, fine), (588.0, 600.0))

# accorciature che si incrociano (fine prima dell'inizio)
inizio, fine, avvisi = correzioni.applica_pad(100.0, 120.0, 15.0, -15.0, DUR, MIN_CLIP_S)
prova("taglio rovesciato: si ricostruisce la durata minima", (inizio, fine), (115.0, 127.0))
prova("...senza durata negativa", fine >= inizio, True)

# girato piu' corto della durata minima: si prende tutto e si dice
inizio, fine, avvisi = correzioni.applica_pad(1.0, 6.0, 0.0, 0.0, 8.0, MIN_CLIP_S)
prova("girato piu' corto del minimo: si prende tutto", (inizio, fine), (0.0, 8.0))
prova("...con due avvisi (riallungata + non raggiungibile)", len(avvisi), 2)
prova("...e l'ultimo dice quanto si e' arrivati", avvisi[-1]["applicato"], 8.0)

# clip gia' esattamente sul minimo: nessun avviso
inizio, fine, avvisi = correzioni.applica_pad(100.0, 112.0, 0.0, 0.0, DUR, MIN_CLIP_S)
prova("durata esattamente al minimo non avvisa", (inizio, fine, avvisi), (100.0, 112.0, []))

# arrotondamento al millesimo, come resolve_highlights
inizio, fine, avvisi = correzioni.applica_pad(100.0004, 130.0, 0.0001, 0.0, DUR, MIN_CLIP_S)
prova("arrotonda al millesimo", (inizio, fine), (100.001, 130.0))


# ---------------------------------------------------------- lettura file

print("\nLettura del file di correzioni")

with tempfile.TemporaryDirectory() as cartella:
    def scrivi(doc) -> Path:
        p = Path(cartella) / "correzioni.json"
        p.write_text(json.dumps(doc) if not isinstance(doc, str) else doc,
                     encoding="utf-8")
        return p

    def voci(clip) -> Path:
        """Un file di correzioni valido: versione corrente + queste voci.

        La versione si mette QUI e non in ogni prova apposta: cosi' il giorno
        che sale di nuovo si cambia un posto solo, e le prove sul contenuto
        non si mettono a parlare di versioni.
        """
        return scrivi({"versione": correzioni.VERSIONE_ATTESA, "clip": clip})

    prova("file assente = nessuna correzione",
          correzioni.leggi(Path(cartella) / "non-esiste.json"), {})
    prova("file vuoto = nessuna correzione", correzioni.leggi(scrivi("   ")), {})
    prova("senza voci = nessuna correzione", correzioni.leggi(voci({})), {})

    letto = correzioni.leggi(voci(
        {"short_01_a-b-FX.mp4": {"ancora_x": 0.1, "pad_fine_s": -0.5}}))
    prova("chiave normalizzata dal nome del -FX", sorted(letto), ["short_01_a-b"])
    prova("campi mancanti valgono zero", letto["short_01_a-b"],
          {"ancora_x": 0.1, "pad_inizio_s": 0.0, "pad_fine_s": -0.5})

    # forme scritte dall'API: null = nessuna correzione, 'aggiornata_il' e'
    # informativo e il montaggio lo ignora
    prova("null vale come campo assente",
          correzioni.leggi(voci({"x": {"ancora_x": None,
                                       "pad_fine_s": 1.0}}))["x"],
          {"ancora_x": 0.0, "pad_inizio_s": 0.0, "pad_fine_s": 1.0})
    prova("'aggiornata_il' accettato e ignorato",
          correzioni.leggi(voci({"x": {
              "ancora_x": 0.2, "aggiornata_il": "2026-08-17T10:00:00Z"}}))["x"],
          {"ancora_x": 0.2, "pad_inizio_s": 0.0, "pad_fine_s": 0.0})
    prova("voce tutta a null = nessuna correzione",
          correzioni.e_vuota(correzioni.leggi(voci({"x": {
              "ancora_x": None, "pad_inizio_s": None, "pad_fine_s": None}}))["x"]),
          True)
    prova("interi accettati come numeri",
          correzioni.leggi(voci({"x": {"pad_inizio_s": -2}}))["x"]["pad_inizio_s"],
          -2.0)

    prova("e_vuota su tutti zeri", correzioni.e_vuota(correzioni.vuota()), True)
    prova("e_vuota su None", correzioni.e_vuota(None), True)
    prova("e_vuota su una correzione vera",
          correzioni.e_vuota({"ancora_x": 0.1, "pad_inizio_s": 0.0, "pad_fine_s": 0.0}),
          False)

    # ---- la versione: il contratto sta qui, e i file vecchi si rifiutano ----
    prova("la versione letta e' la 2", correzioni.VERSIONE_ATTESA, 2)
    prova_solleva("versione 1 rifiutata (semantica opposta)",
                  lambda: correzioni.leggi(scrivi({
                      "versione": 1,
                      "clip": {"x": {"pad_inizio_s": -0.20}}})),
                  "versione 1")
    prova_solleva("...e dice che ora sono scostamenti",
                  lambda: correzioni.leggi(scrivi({"versione": 1, "clip": {}})),
                  "scostamenti")
    prova_solleva("versione assente rifiutata",
                  lambda: correzioni.leggi(scrivi({"clip": {"x": {}}})),
                  "non dichiara il campo 'versione'")
    prova_solleva("versione ignota",
                  lambda: correzioni.leggi(scrivi({"versione": 7, "clip": {}})),
                  "versione")

    prova_solleva("JSON rotto",
                  lambda: correzioni.leggi(scrivi("{ questo non e' json")),
                  "non e' json valido")
    prova_solleva("campo inventato",
                  lambda: correzioni.leggi(voci({"x": {"ancoraX": 0.1}})),
                  "campi che non esistono")
    prova_solleva("valore testuale",
                  lambda: correzioni.leggi(voci({"x": {"ancora_x": "0.1"}})),
                  "deve essere un numero")
    prova_solleva("booleano non e' un numero",
                  lambda: correzioni.leggi(voci({"x": {"ancora_x": True}})),
                  "deve essere un numero")
    prova_solleva("voce non oggetto",
                  lambda: correzioni.leggi(voci({"x": 3})),
                  "deve essere un oggetto")
    prova_solleva("'clip' non oggetto",
                  lambda: correzioni.leggi(voci([])),
                  "'clip' deve essere un oggetto")
    prova_solleva("stessa clip con due nomi",
                  lambda: correzioni.leggi(voci({
                      "short_01_a": {"ancora_x": 0.1},
                      "short_01_a-FX.mp4": {"ancora_x": 0.2}})),
                  "compare due volte")
    # NaN e Infinity: json.loads li accetta, noi no
    prova_solleva("NaN rifiutato",
                  lambda: correzioni.leggi(scrivi(
                      '{"versione": 2, "clip": {"x": {"ancora_x": NaN}}}')),
                  "numero finito")
    prova_solleva("Infinity rifiutato",
                  lambda: correzioni.leggi(scrivi(
                      '{"versione": 2, "clip": {"pad": {"pad_fine_s": Infinity}}}')),
                  "numero finito")


# ------------------------------------------------------------------ esito

print(f"\n{PASSATE} prove passate, {len(FALLITE)} fallite.")
if FALLITE:
    print("Fallite: " + ", ".join(FALLITE))
    sys.exit(1)
sys.exit(0)
