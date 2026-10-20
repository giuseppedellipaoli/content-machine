"""Stadio 1+2: trascrive con faster-whisper (word timestamps) ed esporta il transcript per la selezione.

Uso:
    py transcribe.py VIDEO [--model small|medium|large-v3] [--lang it]

Output (in build/):
    <video>.transcript.json     - segmenti + parole con timestamp (per render.py)
    <video>.for_llm.txt         - una riga per segmento: "[idx] [12.3s-45.6s] testo"
                                  -> Claude legge QUESTO e scrive highlights.json con gli INDICI
Cache: se transcript.json esiste ed è più recente del video, salta la trascrizione.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # fix charmap Windows


def fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--model", default=config.WHISPER_MODEL)
    ap.add_argument("--lang", default=config.WHISPER_LANG)
    ap.add_argument("--download-model", action="store_true",
                    help="Allow this run to download a Whisper model into the explicit local cache")
    ap.add_argument("--model-cache", default=os.environ.get("WHISPER_CACHE_DIR", str(Path(os.environ.get("CONTENT_MACHINE_CACHE", str(config.ROOT.parent.parent / "work" / "cache"))) / "whisper")))
    ap.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = ap.parse_args()

    video = Path(args.video).resolve()
    if not video.exists():
        print(f"File non trovato: {video}", file=sys.stderr)
        return 1

    config.BUILD_DIR.mkdir(parents=True, exist_ok=True)
    out_json = config.BUILD_DIR / f"{video.stem}.transcript.json"
    out_llm = config.BUILD_DIR / f"{video.stem}.for_llm.txt"

    # cache keyed su path completo + mtime
    if out_json.exists():
        try:
            cached = json.loads(out_json.read_text(encoding="utf-8"))
            if cached.get("source") == str(video) and cached.get("mtime") == video.stat().st_mtime:
                print(f"Cache valida: {out_json.name} ({len(cached['segments'])} segmenti)")
                write_llm_export(cached, out_llm)
                return 0
        except (json.JSONDecodeError, KeyError):
            out_json.unlink()

    try:
        from faster_whisper import WhisperModel
        import ctranslate2
    except (ImportError, OSError) as error:
        print(f"Local Whisper runtime unavailable: {error}\n"
              "Use an SRT transcript import instead. Windows execution protections "
              "must not be bypassed.", file=sys.stderr)
        return 1

    print(f"Carico modello {args.model}...")
    cache = Path(args.model_cache).expanduser().resolve()
    cache.mkdir(parents=True, exist_ok=True)
    device = args.device
    if device == "auto":
        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    try:
        model = WhisperModel(args.model, device=device,
                             compute_type="float16" if device == "cuda" else "int8",
                             cpu_threads=os.cpu_count(), download_root=str(cache),
                             local_files_only=not args.download_model)
    except Exception as error:
        print(f"Cannot load local Whisper model: {error}\n"
              f"Cache: {cache}. Downloads are disabled unless --download-model is explicit. "
              "You can import an SRT transcript without Whisper.", file=sys.stderr)
        return 1
    print(f"Device: {device}. Trascrivo {video.name}...")

    segments, info = model.transcribe(
        str(video),
        language=args.lang,
        word_timestamps=True,
        beam_size=5,
        condition_on_previous_text=False,  # anti-loop allucinazioni
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        initial_prompt=config.INITIAL_PROMPT or None,
    )

    seg_list = []
    for i, seg in enumerate(segments):
        words = [
            {"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
            for w in (seg.words or [])
            if w.word.strip()
        ]
        seg_list.append(
            {"id": i, "start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip(), "words": words}
        )
        print(f"  [{i}] [{fmt_ts(seg.start)}] {seg.text.strip()[:75]}")

    data = {
        "source": str(video),
        "mtime": video.stat().st_mtime,
        "language": info.language,
        "duration": round(info.duration, 3),
        "segments": seg_list,
    }
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    write_llm_export(data, out_llm)
    print(f"\nOK: {out_json.name} ({len(seg_list)} segmenti, {fmt_ts(info.duration)})")
    return 0


def write_llm_export(data: dict, out_llm: Path) -> None:
    lines = [
        f"[{s['id']}] [{s['start']:.1f}s-{s['end']:.1f}s] {s['text']}"
        for s in data["segments"]
    ]
    out_llm.write_text("\n".join(lines), encoding="utf-8")
    print(f"Export per selezione: {out_llm.name}")


if __name__ == "__main__":
    raise SystemExit(main())
