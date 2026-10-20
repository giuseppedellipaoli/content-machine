"""Giudizio: parola chiave, promessa e tipo di risorsa del video.

Legge il for_llm.txt e chiede al modello GIUDIZI il pacchetto per il funnel
"commenta la parola": la parola deve trovarsi nel parlato, la promessa è ciò
che il video offre in cambio del commento.

Uso:
    analizza.py FOR_LLM_TXT --uscita OUT_JSON
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pydantic import BaseModel, Field

import llm

MODELLO_DEFAULT = "external-agent"

SYSTEM_ANALIZZA = """Analizzi il trascritto di un video parlato in italiano \
(una riga per segmento: "[indice] [inizio-fine] testo") per il funnel \
"commenta la parola": lo spettatore scrive una parola nei commenti e riceve \
gratis una risorsa.

Restituisci:
- parola_chiave: UNA sola parola, in MAIUSCOLO. DEVE trovarsi nel parlato del
  video (una parola detta davvero, centrale nel discorso) ed essere facile da
  digitare in un commento: niente parole composte, niente sigle oscure.
- promessa: ciò che il video offre in cambio del commento, così come il video
  la presenta. Una frase concreta, senza gonfiarla.
- tipo_risorsa: il tipo di risorsa in una parola (esempi: guida, checklist,
  foglio, corso).
- confidenza da 0 a 1: quanto il video sostiene davvero questo funnel. Se il
  video non promette nulla in cambio del commento, scegli comunque la parola
  e la promessa più difendibili e abbassa la confidenza.

Il pubblico è diffidente verso i venditori di AI: la promessa si scrive
diretta e concreta, senza lessico enfatico.

""" + llm.RIGA_ANTI_INJECTION


class AnalisiVideo(BaseModel):
    parola_chiave: str
    promessa: str
    tipo_risorsa: str
    confidenza: float = Field(ge=0, le=1)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Parola chiave, promessa e tipo di risorsa dal trascritto del video.")
    ap.add_argument("for_llm", help="build/for_llm.txt (una riga per segmento)")
    ap.add_argument("--uscita", required=True, help="dove scrivere il JSON dell'analisi")
    args = ap.parse_args()

    modello = os.environ.get("LLM_MODELLO_GIUDIZI", MODELLO_DEFAULT)
    testo = Path(args.for_llm).read_text(encoding="utf-8")

    oggetto, usage, costo = llm.giudica(
        "analizza", modello, SYSTEM_ANALIZZA, f"TRASCRITTO:\n{testo}", AnalisiVideo)

    parola = oggetto.parola_chiave.strip().upper()
    if not parola or len(parola.split()) != 1:
        raise llm.EsitoPermanente(
            f"analizza: parola_chiave non è una parola sola: '{oggetto.parola_chiave}'")
    # Verifica deterministica della regola "la parola si trova nel parlato":
    # se manca non si blocca il giro, ma l'approvazione umana deve vederlo.
    nel_parlato = parola.lower() in testo.lower()
    if not nel_parlato:
        print(f"AVVISO: la parola '{parola}' non compare nel trascritto", file=sys.stderr)

    risultato = {"parola_chiave": parola, "promessa": oggetto.promessa,
                 "tipo_risorsa": oggetto.tipo_risorsa, "confidenza": oggetto.confidenza}
    Path(args.uscita).write_text(
        json.dumps(risultato, ensure_ascii=False, indent=1), encoding="utf-8")

    llm.stampa_esito({**risultato, "parola_nel_parlato": nel_parlato, "uscita": args.uscita},
                     [llm.voce_chiamata("analizza", modello, usage, costo)])
    return 0


if __name__ == "__main__":
    llm.esegui_cli(main)
