"""Costruisce la traccia audio del MASTER: voce originale + sfx derivati da regia.json, loudnorm.

Uso: python build_audio.py [--voce percorso] [--profilo-sfx percorso.json]
Output: exports/master-audio.m4a

--voce: file con la traccia audio originale (obbligatorio).
--profilo-sfx: JSON che sostituisce volumi e mappe tipo->sfx cablati, con chiavi
  {"vol": {...}, "fs_payoff": {...}, "whoosh_types": [...], "thud_types": [...],
   "k_thud": [...], "k_silent": [...]} — tutte facoltative, le assenti restano cablate.
"""
import argparse
from runtime import FFMPEG
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
SFX = Path(os.environ.get("MOTORE_SFX", str(ROOT.parent / "shorts-pipeline" / "sfx")))
OUT = ROOT / "exports" / "master-audio.m4a"

WHOOSH, POP, THUD = SFX / "whoosh.wav", SFX / "pop.wav", SFX / "thud.wav"

VOL = {"whoosh": 0.50, "pop": 0.42, "thud": 0.55}

# payoff (thud) dentro le tavole full-screen: offset dal t0, in secondi
FS_PAYOFF = {}

WHOOSH_TYPES = {"card", "qcard", "cta", "avatar", "race", "six", "network", "pipeline",
                "minibars", "grid", "chat", "pills", "flow", "bigone", "crashdown", "crash0", "cols2", "arrow2"}
THUD_TYPES = {"keyword", "badge"}


# chiavi k che meritano un thud (payoff/parola forte); k "silenziosi" senza sfx; il resto → pop
K_THUD = {"claim", "crash", "red", "qui", "num", "schema"}
K_SILENT = {"sub", "label", "counter", "lbl", "sola", "fast", "slow", "s1", "s2", "s3", "r1", "r2", "r3"}


def derive(events):
    sfx = []  # (t, kind)
    for ev in events:
        t0 = ev["t0"]
        typ = ev["type"]
        if typ == "fs":
            sfx.append((t0, "whoosh"))
        elif typ in WHOOSH_TYPES or typ == "lista3":
            sfx.append((t0, "whoosh"))
        elif typ in THUD_TYPES:
            sfx.append((t0, "thud"))
        elif typ == "claim2":
            for ln in ev.get("lines", []):
                sfx.append((ln["t"], "thud"))
            continue
        elif typ == "stamp":
            sfx.append((t0 + 0.25, "thud"))
            continue
        # tempi word-level interni (k): payoff → thud, il resto → pop
        for kk, kv in (ev.get("k") or {}).items():
            if not isinstance(kv, (int, float)) or kk in K_SILENT:
                continue
            sfx.append((kv, "thud" if kk in K_THUD else "pop"))
        # elementi interni → pop
        for key in ("bullets", "rows", "pills", "steps", "nodes", "cells", "bubbles"):
            for item in ev.get(key, []) or []:
                sfx.append((item["t"], "pop"))
        for key in ("fork", "loop", "tail"):
            if isinstance(ev.get(key), dict) and "t" in ev[key]:
                sfx.append((ev[key]["t"], "pop"))
        if ev.get("stamp") and isinstance(ev["stamp"], dict):
            sfx.append((ev["stamp"]["t"], "thud"))
        if ev.get("cross"):
            sfx.append((ev["cross"], "pop"))
    # ordina + gap minimo 0.25s
    sfx.sort()
    out = []
    last = -10.0
    for t, kind in sfx:
        if t - last < 0.45:
            continue
        out.append((t, kind))
        last = t
    return out


def carica_profilo(percorso):
    """Applica il profilo sopra i valori cablati. I dizionari si FONDONO
    (le chiavi assenti restano quelle cablate: un profilo con solo
    {"vol": {"whoosh": 0.4}} non deve far perdere pop e thud); i set invece
    si sostituiscono per intero, perche' sono elenchi chiusi."""
    global VOL, FS_PAYOFF, WHOOSH_TYPES, THUD_TYPES, K_THUD, K_SILENT
    if not percorso:
        return
    profilo = json.loads(Path(percorso).read_text(encoding="utf-8"))
    VOL = {**VOL, **profilo.get("vol", {})}
    FS_PAYOFF = {**FS_PAYOFF, **profilo.get("fs_payoff", {})}
    WHOOSH_TYPES = set(profilo.get("whoosh_types", WHOOSH_TYPES))
    THUD_TYPES = set(profilo.get("thud_types", THUD_TYPES))
    K_THUD = set(profilo.get("k_thud", K_THUD))
    K_SILENT = set(profilo.get("k_silent", K_SILENT))


def main():
    ap = argparse.ArgumentParser(description="Traccia audio del master: voce + sfx da regia.json.")
    ap.add_argument("--voce", required=True,
                    help="file con la traccia audio originale (obbligatorio)")
    ap.add_argument("--profilo-sfx",
                    help="JSON con volumi e mappe tipo->sfx (default: i valori predefiniti)")
    ap.add_argument("--senza-sfx", action="store_true", help="conserva la voce senza aggiungere effetti")
    args = ap.parse_args()
    carica_profilo(args.profilo_sfx)

    regia = json.loads((ROOT / "src" / "data" / "regia.json").read_text(encoding="utf-8"))
    sfx = [] if args.senza_sfx else derive(regia["events"])
    print(f"{len(sfx)} eventi sfx ({len(sfx)/ (regia['durSec']/60):.1f}/min)")

    files = {"whoosh": WHOOSH, "pop": POP, "thud": THUD}
    missing = sorted({str(files[kind]) for _, kind in sfx if not files[kind].is_file()})
    if missing:
        raise SystemExit("SFX assenti: generare shorts-pipeline/gen_sfx.py oppure usare --senza-sfx. " + ", ".join(missing))
    inputs = ["-i", args.voce]
    filters = []
    labels = []
    for i, (t, kind) in enumerate(sfx, start=1):
        inputs += ["-i", str(files[kind])]
        ms = int(round(t * 1000))
        filters.append(f"[{i}:a]volume={VOL[kind]},adelay={ms}|{ms}[s{i}]")
        labels.append(f"[s{i}]")
    n = len(sfx) + 1
    filters.append(f"[0:a]{''.join(labels)}amix=inputs={n}:duration=first:normalize=0[mx]")
    filters.append("[mx]loudnorm=I=-14:TP=-1.5:LRA=11[out]")
    script = ROOT / "exports" / "audio-filter.txt"
    script.parent.mkdir(exist_ok=True)
    script.write_text(";\n".join(filters), encoding="utf-8")

    cmd = [FFMPEG, "-nostdin", "-hide_banner", "-y", *inputs,
           "-filter_complex", script.read_text(encoding="utf-8"),
           "-map", "[out]", "-t", str(regia["durSec"]), "-c:a", "aac", "-b:a", "192k", str(OUT)]
    print("ffmpeg con", n, "input...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        raise SystemExit(1)
    print("OK ->", OUT)


if __name__ == "__main__":
    main()
