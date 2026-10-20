"""Giudizio D4: correzione dei refusi whisper nel trascritto.

Chiede al modello REFUSI le correzioni sui segmenti, poi le classifica:
- confidenza >= soglia E stessa lunghezza (1 parola -> 1, o 2 -> 2)
  -> dizionario {"single": {...}, "bigrams": {...}} per fix_transcript.py;
- il resto -> revisioni.json (coda di revisione umana nel DB).

Uso:
    correggi.py TRANSCRIPT_JSON --glossario 'termini,separati' --soglia 0.8
                --uscita-dizionario DIZ_JSON --uscita-revisioni REV_JSON
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pydantic import BaseModel, Field

import llm

# Sonnet, non Haiku: il benchmark sul giro wa-0811 (docs/benchmark-correzioni.md,
# benchmark-sonnet.md, benchmark-opus.md) misura Haiku a recall 9% sui refusi
# veri; Sonnet e' il migliore provato (F1 0.258, precisione 0.611 a soglia 0.8)
# e Opus fa peggio al doppio del costo. La correzione resta un filtro: non
# sostituisce la coda di revisione umana.
MODELLO_DEFAULT = "external-agent"

# System FISSO (prompt caching): il glossario, che varia per tenant, sta nel messaggio.
SYSTEM_CORREGGI = """Sei il correttore delle trascrizioni automatiche (faster-whisper) \
di video parlati in italiano.

Ricevi i segmenti numerati di un trascritto e, nel messaggio, il glossario del
cliente: termini suoi (prodotti, persone, parole tecniche del mestiere) che
whisper storpia spesso.

Trova SOLO i refusi evidenti di trascrizione: parole che il parlante non può
aver detto, storpiature fonetiche tipiche di whisper sull'italiano (esempio:
"revertare" per "refertare", "le hai" per "l'AI"), termini del glossario
trascritti male.

Regole:
- NON riscrivere lo stile. Il parlato resta com'è, con le ripetizioni e le
  frasi storte. Solo errori di trascrizione evidenti.
- Niente correzioni di sola punteggiatura o di sole maiuscole.
- "sbagliato" è la sequenza esatta di parole come appare nel segmento;
  "giusto" è la sostituzione. Preferisci 1 parola -> 1 parola oppure
  2 parole -> 2 parole: sono le uniche applicabili in automatico.
- confidenza da 0 a 1: quanto sei sicuro che sia un refuso e non una scelta
  del parlante. In dubbio, bassa.
- Se non ci sono refusi, elenco vuoto.

""" + llm.RIGA_ANTI_INJECTION


class Correzione(BaseModel):
    segmento_idx: int
    sbagliato: str
    giusto: str
    confidenza: float = Field(ge=0, le=1)


class EsitoCorrezioni(BaseModel):
    correzioni: list[Correzione]


def contenuto_correggi(glossario: str, righe: list[str]) -> str:
    """Il messaggio utente, identico fra correggi.py e benchmark_correzioni.py."""
    return (f"GLOSSARIO DEL CLIENTE: {glossario or '(vuoto)'}\n\n"
            "SEGMENTI:\n" + "\n".join(righe))


def spoglia(parola: str) -> str:
    """Toglie la punteggiatura ai bordi e abbassa: e' la chiave che
    fix_transcript.py confronta (fix_word usa il core senza \\W ai bordi,
    i bigrammi passano da strip_key). Una chiave con la virgola non
    combacerebbe mai."""
    return re.sub(r"^\W+|\W+$", "", parola).lower()


def classifica(correzioni: list[Correzione], segmenti: list[dict], soglia: float):
    """Divide le correzioni fra dizionario applicabile e coda di revisione."""
    single: dict[str, str] = {}
    bigrams: dict[str, list[str]] = {}
    revisioni: list[dict] = []

    def in_revisione(c: Correzione, motivo: str) -> None:
        testo = segmenti[c.segmento_idx]["text"] if 0 <= c.segmento_idx < len(segmenti) else ""
        revisioni.append({"segmento_idx": c.segmento_idx, "testo_segmento": testo,
                          "sbagliato": c.sbagliato, "giusto": c.giusto,
                          "confidenza": c.confidenza, "motivo_esclusione": motivo})

    for c in correzioni:
        parole_sb = [spoglia(p) for p in c.sbagliato.split()]
        parole_gi = c.giusto.split()
        if not (0 <= c.segmento_idx < len(segmenti)):
            in_revisione(c, "segmento_idx fuori range")
            continue
        if c.sbagliato.lower() not in segmenti[c.segmento_idx]["text"].lower():
            in_revisione(c, "sbagliato non presente nel segmento")
            continue
        if c.confidenza < soglia:
            in_revisione(c, f"confidenza sotto soglia {soglia}")
            continue
        if any(p == "" for p in parole_sb) or not parole_sb:
            in_revisione(c, "parola vuota dopo lo strip della punteggiatura")
            continue
        if len(parole_sb) != len(parole_gi) or len(parole_sb) not in (1, 2):
            in_revisione(c, "cambia il numero di parole (editoriale, non 1->1 o 2->2)")
            continue
        chiave = " ".join(parole_sb)
        if len(parole_sb) == 1:
            if chiave in single and single[chiave] != c.giusto:
                in_revisione(c, "in conflitto con una correzione già a dizionario")
                continue
            single[chiave] = c.giusto
        else:
            if chiave in bigrams and bigrams[chiave] != parole_gi:
                in_revisione(c, "in conflitto con una correzione già a dizionario")
                continue
            bigrams[chiave] = parole_gi
    return single, bigrams, revisioni


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Correzioni LLM del trascritto: dizionario per fix_transcript.py + coda revisioni.")
    ap.add_argument("transcript", help="build/transcript.json (segmenti word-level)")
    ap.add_argument("--glossario", default="", help="termini del cliente, separati da virgola")
    ap.add_argument("--soglia", type=float, default=0.8, help="confidenza minima per il dizionario")
    ap.add_argument("--uscita-dizionario", required=True, help="dove scrivere il dizionario JSON")
    ap.add_argument("--uscita-revisioni", required=True, help="dove scrivere revisioni.json")
    args = ap.parse_args()

    modello = os.environ.get("LLM_MODELLO_REFUSI", MODELLO_DEFAULT)
    dati = json.loads(Path(args.transcript).read_text(encoding="utf-8"))
    segmenti = dati["segments"]
    righe = [f"[{s['id']}] {s['text']}" for s in segmenti]

    oggetto, usage, costo = llm.giudica(
        "correggi", modello, SYSTEM_CORREGGI,
        contenuto_correggi(args.glossario, righe), EsitoCorrezioni)

    single, bigrams, revisioni = classifica(oggetto.correzioni, segmenti, args.soglia)

    Path(args.uscita_dizionario).write_text(
        json.dumps({"single": single, "bigrams": bigrams}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    Path(args.uscita_revisioni).write_text(
        json.dumps(revisioni, ensure_ascii=False, indent=1), encoding="utf-8")

    llm.stampa_esito(
        {"dizionario": args.uscita_dizionario, "revisioni": args.uscita_revisioni,
         "totale_correzioni": len(oggetto.correzioni),
         "in_dizionario": len(single) + len(bigrams), "in_revisione": len(revisioni),
         "soglia": args.soglia},
        [llm.voce_chiamata("correggi", modello, usage, costo)])
    return 0


if __name__ == "__main__":
    llm.esegui_cli(main)
