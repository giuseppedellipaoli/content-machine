"""Costruisce le versioni FX di tutti gli shorts: overlay Remotion (alpha) + SFX + mux.

Per ogni voce di fx_plans.json:
  1. ffprobe durata dello short
  2. render overlay OV-short con --props (eventi) in ProRes 4444 + alpha
  3. genera filter_complex: overlay video + adelay/amix degli SFX derivati dagli eventi
  4. mux -> out/fx/<nome>.mp4

Riprendibile: salta gli output già esistenti (cancella il file per rifarlo).
"""
from __future__ import annotations

import _bootstrap  # shared local paths, tools and cache

import json
import os
import subprocess
import sys
from pathlib import Path

import fondamenta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
# Percorsi locali, relativi alla copia della pipeline.
GFX = Path(os.environ.get("MOTORE_GFX", str(ROOT.parent / "video-gfx")))
SFX = ROOT / "sfx"
DEST = Path(os.environ.get("MOTORE_DEST_FX", str(ROOT / "out" / "fx")))
CHROME = os.environ.get("BROWSER_EXECUTABLE", "")

DEST.mkdir(parents=True, exist_ok=True)


def lancia_npx(argomenti: list[str], **kw) -> subprocess.CompletedProcess:
    """Use the installed project CLI and an explicitly configured browser.

    Never let npx or Remotion download a tool/browser implicitly.
    """
    if not CHROME or not Path(CHROME).is_file():
        raise RuntimeError("Imposta BROWSER_EXECUTABLE a un browser locale esistente. Nessun download automatico.")
    cli = GFX / "node_modules" / ".bin" / ("remotion.cmd" if sys.platform == "win32" else "remotion")
    if not cli.is_file():
        raise RuntimeError("Remotion non installato nel progetto video-gfx. Esegui il setup esplicito indicato nel README.")
    args = argomenti[1:] if argomenti and argomenti[0] == "remotion" else argomenti
    cmd = [str(cli), *args, f"--browser-executable={CHROME}", "--chrome-mode=chrome-for-testing"]
    return subprocess.run(cmd, **kw)


def probe_duration(p: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip())


def misura_video(p: Path) -> tuple[int, int]:
    """Larghezza e altezza vere di un file, lette dal file."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(p)],
        capture_output=True, text=True,
    )
    pezzi = r.stdout.strip().split("x")
    if len(pezzi) != 2:
        raise RuntimeError(f"ffprobe non ha dato le misure di {p.name}: {r.stdout!r} {r.stderr[-300:]}")
    return int(pezzi[0]), int(pezzi[1])


def controlla_misure(base: Path, overlay: Path) -> None:
    """La grafica e il video DEVONO avere la stessa misura. Altrimenti si ferma.

    IL GUASTO CHE QUESTO CONTROLLO INTERCETTA, misurato il 18/08/2026.
    Le misure dello short le decide il brand kit (config.py legge OUT_W/OUT_H
    da formati.short). Le misure della grafica NO: stanno INCHIODATE nel
    codice Remotion, in motore/video-gfx/src/Root.tsx, alla composizione
    OV-short. Nessuno confronta i due posti — sincronizza_brand.py verifica il
    kit contro config.py su undici grandezze, ma il lato Remotion contro
    niente — e qui sotto la grafica si sovrappone con `overlay=0:0`, che
    quando le misure non combaciano NON e' un errore: ffmpeg allinea in alto a
    sinistra, taglia quello che avanza ed esce con successo.

    Misurato davvero: base 1080x1350 con overlay 1080x1920 -> ffmpeg esito 0,
    artefatto 1080x1350, grafica tagliata. Nessun messaggio, da nessuna parte.

    E c'e' un secondo modo di caderci, peggiore: l'overlay si rirenderizza solo
    se il file non esiste. Cambiato il formato nel kit, una .mov rimasta da un
    giro precedente verrebbe riusata cosi' com'e'.

    Fermarsi qui costa un giro fallito con un messaggio che dice cosa fare.
    Non fermarsi costa un contenuto pubblicato con la grafica mozzata.
    """
    larghezza_base, altezza_base = misura_video(base)
    larghezza_ov, altezza_ov = misura_video(overlay)
    if (larghezza_base, altezza_base) != (larghezza_ov, altezza_ov):
        raise RuntimeError(
            f"la grafica non ha la misura del video: {overlay.name} e' "
            f"{larghezza_ov}x{altezza_ov}, mentre {base.name} e' "
            f"{larghezza_base}x{altezza_base}.\n"
            f"Le due misure vengono da posti diversi: quella del video dal "
            f"brand kit (formati.short), quella della grafica dal codice "
            f"Remotion in motore/video-gfx/src/Root.tsx (composizione "
            f"OV-short). Vanno allineate a mano.\n"
            f"Se hai appena cambiato il formato nel kit, cancella anche la "
            f"grafica gia' renderizzata ({overlay}): viene riusata quando "
            f"esiste, quindi resterebbe quella vecchia.")


def sfx_events(events: list[dict]) -> list[tuple[str, float, float]]:
    """(wav, secondi, volume) derivati dagli eventi grafici."""
    out: list[tuple[str, float, float]] = []
    for ev in events:
        t = ev.get("type")
        if t == "pill":
            out.append(("pop", 0.2, 0.6))
            out.append(("wipeout", 4.6, 0.4))
        if t in ("hook", "card", "list"):
            out.append(("whoosh", ev["t0"], 0.5))
            out.append(("wipeout", ev["t1"], 0.4))
        if t == "counter":
            out.append(("whoosh", ev["t0"], 0.5))
            out.append(("tickroll", ev["t0"] + 0.2, 0.5))
            out.append(("wipeout", ev["t1"], 0.4))
        if t == "list":
            for it in ev["items"]:
                out.append(("pop", it["t"], 0.45))
        if t == "claim":
            out.append(("whoosh", ev["t0"], 0.4))
        if t == "stamp":
            out.append(("thud", ev["t"] + 0.23, 0.9))
    return out


def build_one(plan: dict) -> None:
    src = ROOT / plan["src"]
    name = src.stem
    dest = DEST / f"{name}-FX.mp4"
    if dest.exists():
        print(f"SKIP (esiste): {dest.name}")
        return
    dur = probe_duration(src)
    print(f"== {name} ({dur:.1f}s)")

    # 1. overlay render
    props = ROOT / "build" / f"props-{name}.json"
    props.write_text(json.dumps({"events": plan["events"], "durSec": dur}, ensure_ascii=False), encoding="utf-8")
    ov = GFX / "exports" / f"ov-{name}.mov"
    if not ov.exists():
        print("   overlay...")
        r = lancia_npx(
            ["remotion", "render", "OV-short", str(ov),
             "--codec=prores", "--prores-profile=4444", "--image-format=png",
             "--pixel-format=yuva444p10le", f"--props={props}"],
            capture_output=True, text=True, cwd=str(GFX),
        )
        if r.returncode != 0:
            raise RuntimeError(f"remotion fallito per {name}:\n{r.stderr[-1500:]}")

    # La grafica deve avere la misura del video PRIMA di sovrapporla: dopo,
    # il danno e' gia' nei byte dell'artefatto e nessuno lo segnala.
    controlla_misure(src, ov)

    # 2. sfx filter
    fx = sfx_events(plan["events"])
    fx = [e for e in fx if e[1] * 1000 >= 0 and e[1] < dur]
    inputs: list[str] = []
    filters = ["[0:v][1:v]overlay=0:0:eof_action=pass[v]"]
    labels = []
    for i, (snd, t, vol) in enumerate(fx):
        inputs += ["-i", str(SFX / f"{snd}.wav")]
        # ARROTONDAMENTO, non troncamento. `int(4.6 * 1000)` vale 4599, non
        # 4600: 4,6 non e' rappresentabile in binario e il prodotto cade appena
        # sotto. Il taglio verso il basso spostava ogni effetto sonoro di un
        # millesimo indietro rispetto alla grafica che accompagna — sempre nella
        # stessa direzione, quindi non si compensa mai. Regola in
        # docs/fondamenta-numeriche.md, voce 4.
        ms = fondamenta.arrotonda(t * 1000)
        filters.append(f"[{i + 2}:a]adelay={ms}|{ms},volume={vol}[s{i}]")
        labels.append(f"[s{i}]")
    # Gli effetti si sommano alla voce senza normalizzare (`normalize=0`), altrimenti
    # il parlato si abbassa a ogni effetto in più. Ma la voce arriva già a -14 LUFS
    # con i picchi vicini al tetto: senza un limitatore dopo la somma, ogni effetto
    # spinge il true peak sopra lo zero e il suono distorce sui telefoni.
    # Misurato l'11/08/2026: 8 short FX su 12 erano oltre -1 dBTP, tre sopra 0.
    filters.append(f"[0:a]{''.join(labels)}amix=inputs={len(fx) + 1}:normalize=0[am]")
    # 0.85 ≈ -1.4 dBFS: il limitatore lavora sui campioni, ma il true peak si misura
    # fra un campione e l'altro e può stare sopra. Con -1.0 esatto si sforava di un
    # decimo e il cancello bocciava: serve un po' di margine.
    filters.append("[am]alimiter=limit=0.85:level=disabled[a]")
    fscript = ROOT / "build" / f"fxfilter-{name}.txt"
    fscript.write_text(";\n".join(filters) + "\n", encoding="utf-8")

    # 3. mux
    print("   mux...")
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-i", str(ov), *inputs,
         "-filter_complex", fscript.read_text(encoding="utf-8"), "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dest)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"mux fallito per {name}:\n{r.stderr[-1500:]}")
    print(f"   OK -> {dest}")


def main() -> int:
    plans = json.loads((ROOT / "fx_plans.json").read_text(encoding="utf-8"))
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for plan in plans:
        if only and only not in plan["src"]:
            continue
        build_one(plan)
    print("\nTutti fatti.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
