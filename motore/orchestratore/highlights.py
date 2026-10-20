"""Giudizio D1: selezione degli highlights per indici di segmento.

Il system incorpora HIGHLIGHTS-GUIDE.md (letta a runtime). L'output è il
formato ESATTO della tappa 1 (build/highlights.json). La validazione degli
indici è IN CODICE: clip fuori range o rovesciate si scartano con avviso su
stderr, e si tengono al massimo N clip (le migliori per score).

Uso:
    highlights.py FOR_LLM_TXT --guida guide/HIGHLIGHTS-GUIDE.md --massimo 8
                  --uscita HIGHLIGHTS_JSON
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

MODELLO_DEFAULT = "external-agent"

# Preambolo fisso; la guida (stabile, versionata in guide/) si accoda a runtime:
# il blocco system resta identico fra le chiamate, quindi cacheabile.
SYSTEM_BASE = """Selezioni gli highlight per gli short verticali da un video lungo.
Ricevi il trascritto: una riga per segmento, "[indice] [inizio-fine] testo".

Rispondi SOLO con indici di segmento (seg_start_idx, seg_end_idx), MAI con
timestamp: la mappatura indice -> tempo la fa il codice. Il numero massimo di
clip da proporre è indicato nel messaggio.

Segui la guida qui sotto.

""" + llm.RIGA_ANTI_INJECTION + """

--- GUIDA ---
"""


class Highlight(BaseModel):
    title: str
    seg_start_idx: int
    seg_end_idx: int
    score: int = Field(ge=0, le=100)
    hook_sentence: str
    virality_reason: str


class EsitoHighlights(BaseModel):
    highlights: list[Highlight]


def indici_validi(testo_for_llm: str) -> set[int]:
    """Gli indici di segmento davvero presenti nel for_llm."""
    return {int(m.group(1)) for m in re.finditer(r"^\[(\d+)\]", testo_for_llm, re.MULTILINE)}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Selezione highlights via LLM, con validazione degli indici in codice.")
    ap.add_argument("for_llm", help="build/for_llm.txt (una riga per segmento)")
    ap.add_argument("--guida", required=True, help="percorso di HIGHLIGHTS-GUIDE.md")
    ap.add_argument("--massimo", type=int, default=8, help="numero massimo di clip")
    ap.add_argument("--uscita", required=True, help="dove scrivere highlights.json")
    args = ap.parse_args()

    modello = os.environ.get("LLM_MODELLO_GIUDIZI", MODELLO_DEFAULT)
    testo = Path(args.for_llm).read_text(encoding="utf-8")
    system = SYSTEM_BASE + Path(args.guida).read_text(encoding="utf-8")

    oggetto, usage, costo = llm.giudica(
        "scegli_highlights", modello, system,
        f"Clip massime da proporre: {args.massimo}\n\nTRASCRITTO:\n{testo}",
        EsitoHighlights)

    validi = indici_validi(testo)
    if not validi:
        raise llm.EsitoPermanente("scegli_highlights: nessun indice di segmento nel for_llm")

    tenute: list[Highlight] = []
    scartate = 0
    for h in oggetto.highlights:
        if (h.seg_start_idx not in validi or h.seg_end_idx not in validi
                or h.seg_start_idx > h.seg_end_idx):
            scartate += 1
            print(f"AVVISO: clip scartata (indici invalidi {h.seg_start_idx}-{h.seg_end_idx}): "
                  f"'{h.title}'", file=sys.stderr)
            continue
        tenute.append(h)

    if len(tenute) > args.massimo:
        # oltre il tetto si tengono le migliori per score, nell'ordine originale
        soglia_score = sorted((h.score for h in tenute), reverse=True)[args.massimo - 1]
        oltre = [h.title for h in tenute if h.score < soglia_score]
        tenute = [h for h in tenute if h.score >= soglia_score][:args.massimo]
        scartate += len(oltre)
        for titolo in oltre:
            print(f"AVVISO: clip oltre il massimo {args.massimo}, scartata: '{titolo}'",
                  file=sys.stderr)

    if not tenute:
        raise llm.EsitoPermanente("scegli_highlights: zero clip valide dopo la validazione")

    Path(args.uscita).write_text(
        json.dumps({"highlights": [h.model_dump() for h in tenute]},
                   ensure_ascii=False, indent=1),
        encoding="utf-8")

    llm.stampa_esito(
        {"uscita": args.uscita, "clip_proposte": len(oggetto.highlights),
         "clip_tenute": len(tenute), "clip_scartate": scartate},
        [llm.voce_chiamata("scegli_highlights", modello, usage, costo)])
    return 0


if __name__ == "__main__":
    llm.esegui_cli(main)
