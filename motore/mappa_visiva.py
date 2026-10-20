"""Applica la mappa parola → elemento visivo del brand kit a un trascritto.

    py mappa_visiva.py trascritto.json                    # tabella leggibile
    py mappa_visiva.py trascritto.json --json proposte.json
    py mappa_visiva.py trascritto.json --kit clienti/acme/brand-kit.json
    py mappa_visiva.py trascritto.json --da 0 --a 120     # solo un tratto

Cosa fa: cerca nel parlato le cose elencate in `mappa_visiva.regole` del brand kit
e dice **quando** vanno mostrate e **cosa** va mostrato. Trasforma in dati la
regola d'oro di video-gfx/REFERENCE-FORMAT.md — «le grafiche trascrivono il parlato
chiave» — che finora viveva solo nella testa di chi scriveva la regia.

Cosa NON fa: non scrive in regia.json e non monta niente. Restituisce **proposte**,
in ordine di tempo, con il motivo accanto. La regia resta una decisione umana:
sessanta eventi automatici su un video da dieci minuti sarebbero uno schermo
affollato, che è esattamente ciò che il canone vieta.

Per il SaaS: il motore non cambia da cliente a cliente, questa mappa sì. È il
linguaggio visivo del cliente, e sta in un file che si può consegnare e discutere.
Si punta a un kit diverso con --kit.

Accetta trascritti in due forme: il JSON di shorts-pipeline (segments con words) e
un file SRT.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
KIT_PREDEFINITO = ROOT / "brand-kit.json"


def normalizza(t: str) -> str:
    """Solo minuscolo: gli accenti NON si tolgono.

    Toglierli faceva scattare la regola di "meta" (l'azienda) dentro "a metà".
    In italiano l'accento è spesso l'unica differenza fra due parole diverse.
    """
    return unicodedata.normalize("NFC", t.lower())


def parole_da_json(d: dict) -> list[tuple[float, str]]:
    if "segments" in d:
        return [(float(w["start"]), w["w"]) for s in d["segments"]
                for w in s.get("words", [])]
    if "words" in d:
        return [(float(w["start"]), w["w"]) for w in d["words"]]
    raise SystemExit("trascritto senza parole: atteso 'segments[].words' o 'words'")


def parole_da_srt(testo: str) -> list[tuple[float, str]]:
    """Fallback: dall'SRT si ricava il tempo della battuta, non della parola."""
    out: list[tuple[float, str]] = []
    for blocco in re.split(r"\n\s*\n", testo):
        m = re.search(r"(\d\d):(\d\d):(\d\d)[,.](\d+)\s*-->", blocco)
        if not m:
            continue
        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        righe = [r for r in blocco.splitlines() if "-->" not in r and not r.strip().isdigit()]
        for p in " ".join(righe).split():
            out.append((float(t), re.sub(r"<[^>]+>", "", p)))
    return out


def carica_parole(p: Path) -> list[tuple[float, str]]:
    if p.suffix.lower() == ".json":
        return parole_da_json(json.loads(p.read_text(encoding="utf-8")))
    return parole_da_srt(p.read_text(encoding="utf-8", errors="ignore"))


def cerca(parole: list[tuple[float, str]], regole: list[dict]) -> list[dict]:
    """Una passata sul parlato, un elenco di proposte con il secondo di attacco."""
    # testo unico + mappa carattere → indice di parola, per risalire al tempo
    pezzi, indice = [], []
    for i, (_, w) in enumerate(parole):
        n = normalizza(w)
        if not n:
            continue
        if pezzi:
            pezzi.append(" ")
            indice.append(i)
        pezzi.append(n)
        indice.extend([i] * len(n))
    testo = "".join(pezzi)

    proposte: list[dict] = []
    for regola in regole:
        modelli: list[str] = []
        for frase in regola.get("quando", []):
            modelli.append(r"\b" + re.escape(normalizza(frase)) + r"\b")
        for chiave in ("quando_regex",):
            if regola.get(chiave):
                modelli.append(normalizza(regola[chiave]))
        for modello in modelli:
            try:
                rx = re.compile(modello, re.M)
            except re.error as e:
                print(f"   regola ignorata, espressione non valida ({e}): {modello}")
                continue
            for m in rx.finditer(testo):
                if m.start() >= len(indice):
                    continue
                iw = indice[m.start()]
                proposte.append({
                    "t": round(parole[iw][0], 2),
                    "tipo": regola["tipo"],
                    "innesco": m.group(0)[:40],
                    "perche": regola.get("perche") or regola.get("perché", ""),
                    "priorita": regola.get("priorita", 3),
                    "contesto": " ".join(w for _, w in parole[max(0, iw - 4):iw + 6]),
                })
    proposte.sort(key=lambda x: (x["t"], x["priorita"]))
    return proposte


def dedup(proposte: list[dict], finestra: float = 4.0) -> list[dict]:
    """Un elemento alla volta: due proposte vicine dello stesso tipo sono una sola."""
    tenute: list[dict] = []
    for p in proposte:
        if any(q["tipo"] == p["tipo"] and abs(q["t"] - p["t"]) < finestra for q in tenute):
            continue
        tenute.append(p)
    return tenute


def main() -> int:
    ap = argparse.ArgumentParser(description="Proposte di elementi visivi dal parlato.")
    ap.add_argument("trascritto", help="file .json (word-level) o .srt")
    ap.add_argument("--kit", default=str(KIT_PREDEFINITO), help="brand kit da usare")
    ap.add_argument("--json", dest="uscita", help="scrive le proposte in un file JSON")
    ap.add_argument("--da", type=float, default=0.0)
    ap.add_argument("--a", type=float, default=float("inf"))
    ap.add_argument("--tutte", action="store_true",
                    help="non accorpare le proposte vicine dello stesso tipo")
    args = ap.parse_args()

    kit_p = Path(args.kit)
    if not kit_p.exists():
        raise SystemExit(f"brand kit non trovato: {kit_p}")
    kit = json.loads(kit_p.read_text(encoding="utf-8"))
    mappa = kit.get("mappa_visiva")
    if not mappa:
        raise SystemExit(f"{kit_p.name} non ha una sezione 'mappa_visiva'")

    tras_p = Path(args.trascritto)
    if not tras_p.exists():
        raise SystemExit(f"trascritto non trovato: {tras_p}")
    try:
        parole = carica_parole(tras_p)
    except json.JSONDecodeError as e:
        raise SystemExit(f"{tras_p.name} non è un JSON valido: {e}")
    if not parole:
        raise SystemExit(
            f"{tras_p.name} non contiene parole con i tempi. "
            "Serve un trascritto word-level (`segments[].words` o `words`) o un .srt")

    proposte = cerca(parole, mappa["regole"])
    proposte = [p for p in proposte if args.da <= p["t"] <= args.a]
    if not args.tutte:
        proposte = dedup(proposte)

    durata = parole[-1][0]
    print(f"kit: {kit_p}")
    print(f"parlato: {len(parole)} parole, {durata/60:.0f} min {durata%60:02.0f} s")
    print(f"proposte: {len(proposte)}"
          + (f" (una ogni {durata/len(proposte):.0f} s)" if proposte else ""))
    print()
    for p in proposte:
        m, s = divmod(int(p["t"]), 60)
        print(f"  {m:2d}:{s:02d}  {p['tipo']:<16} «{p['innesco']}»")
        print(f"         …{p['contesto']}…")
    print()
    print("Sono proposte, non una regia: l'elemento va scelto, non subìto.")
    print("Il canone dice un elemento alla volta, uno nuovo ogni 6-10 secondi.")

    if args.uscita:
        Path(args.uscita).write_text(
            json.dumps(proposte, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nscritte in {args.uscita}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
