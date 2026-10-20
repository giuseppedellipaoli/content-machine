"""Ultimo passo: video muto + traccia audio → il file che si consegna.

    py consegna.py regiav2                 # -> exports/regiav2.mp4
    py consegna.py regiav2 --bozza         # parte dal montaggio in bozza
    py consegna.py finale --dove exports

Finora questo passaggio era a mano, descritto a parole in docs/RENDERER.md. Metterlo
in uno script serve a due cose: non ripetere il giudizio ogni volta, e non ripetere
**gli errori** — la versione consegnata del primo video ha due difetti che nascono
proprio qui, e che il cancello di qualità ha trovato solo dopo:

- `yuvj420p` invece di `yuv420p`: è la variante a range pieno, e alcuni lettori
  sbagliano i livelli. Qui si forza il formato giusto.
- indice del file in coda (`faststart` mancante): il video parte solo a scaricamento
  finito. Su YouTube non si vede perché ricodifica lui, si vedrebbe servendolo da un
  sito o mandandolo a un cliente. Qui l'indice va in testa.

Alla fine passa il file al cancello di qualità: se non arriva a 95/100 lo dice, e non
lo si scopre dopo averlo mandato.
"""
from __future__ import annotations

import argparse
from runtime import FFMPEG, FFPROBE
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
BUILD = ROOT / "build"
EXPORTS = ROOT / "exports"
AUDIO = EXPORTS / "master-audio.m4a"


def durata(p: Path) -> float:
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def range_pieno(p: Path) -> bool:
    """Il video è a range pieno (`yuvj420p`), come esce da Remotion?

    Remotion cattura i fotogrammi come JPEG, quindi i blocchi escono a range pieno.
    Per la consegna serve il range televisivo, altrimenti alcuni lettori sbagliano
    i livelli — è il difetto che il primo video consegnato si porta dietro.

    Attenzione: **non basta cambiare l'etichetta**. Passare da pieno a televisivo
    senza convertire i valori sposta i livelli invece di sistemarli, e passare
    `-pix_fmt` insieme a `-c:v copy` non fa assolutamente niente: era il difetto
    della prima versione di questo script, trovato dal cancello di qualità.
    """
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=pix_fmt,color_range",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    t = (r.stdout or "").strip().lower()
    return "yuvj" in t or "pc" in t.split(",")


def main() -> int:
    ap = argparse.ArgumentParser(description="Monta video e audio nel file finale.")
    ap.add_argument("nome", help="nome del file finale, senza estensione")
    ap.add_argument("--bozza", action="store_true", help="parte dal montaggio in bozza")
    ap.add_argument("--dove", help="cartella di destinazione (default: exports/)")
    ap.add_argument("--senza-controllo", action="store_true",
                    help="salta il cancello di qualità")
    args = ap.parse_args()

    video = BUILD / ("master-video-bozza.mp4" if args.bozza else "master-video.mp4")
    if not video.exists():
        raise SystemExit(f"manca il video montato: {video}\n"
                         "  prima:  py render_regia.py --tutto")
    if not AUDIO.exists():
        raise SystemExit(f"manca la traccia audio: {AUDIO}\n"
                         "  prima:  py build_audio.py")

    dv, da = durata(video), durata(AUDIO)
    print(f"  video: {dv:.1f}s  ({video.name})")
    print(f"  audio: {da:.1f}s  ({AUDIO.name})")
    if abs(dv - da) > 0.5:
        raise SystemExit(f"Durate audio/video diverse di {abs(dv-da):.1f}s: correggere prima della consegna.")

    dest_dir = Path(args.dove).expanduser().resolve() if args.dove else EXPORTS
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{args.nome}.mp4"

    converti = range_pieno(video)
    if converti:
        print("  il video è a range pieno (yuvj420p): converto i livelli, non solo "
              "l'etichetta. Costa una ricodifica, ~3 minuti su un video da 10 minuti.")
    else:
        print("  range già televisivo: il video si copia senza ricodificare")

    print(f"  monto → {dest}")
    cmd = [FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(video), "-i", str(AUDIO),
           "-map", "0:v:0", "-map", "1:a:0"]
    if converti:
        cmd += ["-vf", "scale=in_range=full:out_range=limited",
                "-c:v", "libx264", "-crf", "15", "-preset", "medium",
                "-pix_fmt", "yuv420p", "-color_range", "tv"]
    else:
        cmd += ["-c:v", "copy"]
    # build_audio.py already encodes AAC; another lossy pass can overshoot true peak.
    cmd += ["-c:a", "copy",
            "-movflags", "+faststart",   # indice in testa, così parte subito
            "-shortest", str(dest)]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    if r.returncode != 0:
        raise SystemExit(f"montaggio fallito:\n{r.stderr[-1200:]}")

    mb = dest.stat().st_size / 1_048_576
    print(f"  fatto: {mb:.0f} MB, {durata(dest):.1f}s")

    if not args.senza_controllo:
        print("\n  cancello di qualità:")
        qa = ROOT.parent / "shorts-pipeline" / "qa_check.py"
        if qa.exists():
            # sys.executable: il python che sta girando, vale su Windows e sul worker Linux
            c = subprocess.run([sys.executable, str(qa), str(dest)], capture_output=True,
                               text=True, encoding="utf-8", errors="ignore",
                               cwd=str(qa.parent))
            if c.returncode != 0:
                print(c.stdout or c.stderr)
                return c.returncode
            for riga in (c.stdout or "").splitlines():
                if riga.strip():
                    print("   " + riga)
        else:
            raise SystemExit("qa_check.py assente: installare la pipeline o usare esplicitamente --senza-controllo.")

    print(f"\n{dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
