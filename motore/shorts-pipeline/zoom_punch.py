"""Punch-in dinamico per talking head 16:9 (sezioni retoriche → scala di zoom).

Uso:
    py zoom_punch.py VIDEO SECTIONS.json [OUTPUT]

SECTIONS.json:
    {"zoom_levels": {"normal": 1.0, "emphasis": 1.13, "critical": 1.28},
     "sections": [{"start": 0.0, "end": 4.0, "label": "normal"}, ...]}

Le sezioni devono essere continue e coprire tutto il video. L'audio passa
integro (-map 0:a): il punch non altera la timeline.
"""
from __future__ import annotations

import _bootstrap  # shared local paths, tools and cache

import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

import fondamenta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

YUNET = Path(os.environ.get("YUNET_MODEL_PATH", str(Path(__file__).parent / "models" / "face_detection_yunet_2023mar.onnx")))


def probe(video: Path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-show_entries", "format=duration", "-of", "json", str(video)],
        capture_output=True, text=True,
    )
    data = json.loads(r.stdout)
    s = data["streams"][0]
    return int(s["width"]), int(s["height"]), float(data["format"]["duration"])


def face_center(video: Path, w: int, h: int, dur: float) -> tuple[int, int]:
    if not YUNET.is_file():
        print("AVVISO: YuNet non installato, punch centrato")
        return w // 2, h // 2
    try:
        import cv2
    except (ImportError, OSError):
        print("AVVISO: OpenCV non disponibile, punch centrato")
        return w // 2, h // 2

    cap = cv2.VideoCapture(str(video))
    small_w, small_h = 960, int(h * 960 / w)
    det = cv2.FaceDetectorYN.create(str(YUNET), "", (small_w, small_h), 0.6)
    scale = small_w / w
    centers = []
    for i in range(10):
        cap.set(cv2.CAP_PROP_POS_MSEC, (dur * (i + 0.5) / 10) * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        small = cv2.resize(frame, (small_w, small_h))
        _, faces = det.detect(small)
        if faces is not None and len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])[:4]
            centers.append(((x + fw / 2) / scale, (y + fh / 2) / scale))
    cap.release()
    if not centers:
        return w // 2, h // 2
    xs = sorted(c[0] for c in centers)
    ys = sorted(c[1] for c in centers)
    mx, my = xs[len(xs) // 2], ys[len(ys) // 2]
    # scarta outlier oltre il 30% dal mediano
    good = [c for c in centers if abs(c[0] - mx) < 0.3 * w and abs(c[1] - my) < 0.3 * h]
    return (fondamenta.arrotonda(statistics.fmean(c[0] for c in good)),
            fondamenta.arrotonda(statistics.fmean(c[1] for c in good)))


def main() -> int:
    video = Path(sys.argv[1]).resolve()
    cfg = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else video.with_name(video.stem + "-zoom.mp4")

    w, h, dur = probe(video)
    fx, fy = face_center(video, w, h, dur)
    print(f"{w}x{h}, {dur:.1f}s, faccia a ({fx},{fy})")

    levels = cfg["zoom_levels"]
    parts, labels = [], []
    for i, sec in enumerate(cfg["sections"]):
        zoom = levels[sec["label"]]
        # PRIMA si arrotonda, POI si scende al pari: e' l'ordine della regola di
        # normalizzazione (docs/fondamenta-numeriche.md, voce 4). Troncando
        # prima, 1080/1,13 = 955,75 diventava 954 invece di 956, cioe' due
        # pixel di inquadratura persi e un rapporto d'aspetto leggermente
        # diverso da quello del video. Il pari e' obbligatorio per il
        # sottocampionamento 4:2:0, il minimo di 2 evita il ritaglio nullo.
        cw = max(2, fondamenta.arrotonda(w / zoom) // 2 * 2)
        ch = max(2, fondamenta.arrotonda(h / zoom) // 2 * 2)
        cx = max(0, min(fx - cw // 2, w - cw))
        cy = max(0, min(fy - ch // 2, h - ch))
        parts.append(
            f"[0:v]trim=start={sec['start']:.3f}:end={sec['end']:.3f},setpts=PTS-STARTPTS,"
            f"crop={cw}:{ch}:{cx}:{cy},scale={w}:{h}:flags=lanczos,setsar=1[v{i}]"
        )
        labels.append(f"[v{i}]")
    parts.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[outv]")

    fscript = video.parent / f"zoomfilter-{video.stem}.txt"
    fscript.write_text(";\n".join(parts) + "\n", encoding="utf-8")

    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
         "-filter_complex", fscript.read_text(encoding="utf-8"), "-map", "[outv]", "-map", "0:a",
         "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "copy", str(out)],
        capture_output=True, text=True,
    )
    fscript.unlink()
    if r.returncode != 0:
        print(r.stderr[-1500:])
        return 1
    dist = {}
    for s in cfg["sections"]:
        dist[s["label"]] = dist.get(s["label"], 0) + 1
    print(f"OK -> {out.name}  sezioni: {dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
