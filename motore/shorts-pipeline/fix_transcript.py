"""Corregge i refusi ricorrenti di whisper sull'italiano parlato, nel transcript word-level.

Sostituzioni sicure (match esatto, case-insensitive) + bigrammi per "le hai" -> "l'AI".
Applica in-place a build/<stem>.transcript.json e rigenera l'export for_llm.

Con --dizionario percorso.json i dizionari si leggono da file:
    {"single": {"refuso": "corretto"}, "bigrams": {"le hai": ["l'", "AI"]}}
Senza, non viene applicata alcuna sostituzione.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import config
from transcribe import write_llm_export

# No content-specific glossary is distributed. Supply --dizionario explicitly.
SINGLE = {}
BIGRAMS = {}


def fix_word(w: str, single: dict[str, str]) -> str:
    core = w.strip()
    m = re.match(r"^(\W*)(.*?)(\W*)$", core, re.DOTALL)
    pre, word, post = m.groups()
    rep = single.get(word.lower())
    if rep is None:
        return w
    if word.istitle():
        rep = rep[0].upper() + rep[1:]
    return pre + rep + post


def strip_key(w: str) -> str:
    return re.sub(r"^\W+|\W+$", "", w).lower()


def carica_dizionari(percorso: str | None) -> tuple[dict, dict]:
    """Dizionari attivi: dal file --dizionario, altrimenti vuoti.

    Le chiavi si abbassano SEMPRE a caricamento: strip_key() abbassa prima di
    confrontare, quindi una chiave con la maiuscola non combacia mai — la
    trappola muore qui, per entrambe le sorgenti.
    """
    if percorso:
        dati = json.loads(Path(percorso).read_text(encoding="utf-8"))
        single = dati.get("single", {})
        bigrams = {tuple(chiave.lower().split()): tuple(valore)
                   for chiave, valore in dati.get("bigrams", {}).items()}
    else:
        single = SINGLE
        bigrams = {tuple(parte.lower() for parte in chiave): valore
                   for chiave, valore in BIGRAMS.items()}
    return {chiave.lower(): valore for chiave, valore in single.items()}, bigrams


def main() -> int:
    ap = argparse.ArgumentParser(description="Corregge i refusi ricorrenti nel transcript word-level.")
    ap.add_argument("transcript", help="build/<stem>.transcript.json, corretto in-place")
    ap.add_argument("--dizionario",
                    help='JSON {"single": {...}, "bigrams": {"le hai": ["l\'", "AI"]}} '
                         "(default: dizionari cablati)")
    args = ap.parse_args()
    single, bigrams = carica_dizionari(args.dizionario)
    path = Path(args.transcript)
    data = json.loads(path.read_text(encoding="utf-8"))
    n_single = n_bi = 0
    for seg in data["segments"]:
        words = seg["words"]
        for i, w in enumerate(words):
            fixed = fix_word(w["w"], single)
            if fixed != w["w"]:
                w["w"] = fixed
                n_single += 1
        for i in range(len(words) - 1):
            key = (strip_key(words[i]["w"]), strip_key(words[i + 1]["w"]))
            if key in bigrams:
                a, b = bigrams[key]
                words[i]["w"], words[i + 1]["w"] = a, b
                n_bi += 1
        seg["text"] = " ".join(w["w"] for w in words)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    out_llm = path.with_name(path.name.replace(".transcript.json", ".for_llm.txt"))
    write_llm_export(data, out_llm)
    print(f"OK: {n_single} parole corrette, {n_bi} bigrammi ({path.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
