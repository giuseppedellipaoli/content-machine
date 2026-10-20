"""Render del video lungo: contact sheet, bozza, blocchi versionati, ri-render del pezzo toccato.

Automatizza il passo 4 di docs/RENDERER.md ("re-render solo chunk toccati"), che
finora si faceva a mano, e aggiunge il passo che mancava prima del render.

    py render_regia.py --stato               # cosa c'è già, con le versioni
    py render_regia.py --contatti            # UN fotogramma per evento, in una tavola sola
    py render_regia.py --contatti --evento 12 13 14
    py render_regia.py --tutto               # tutti i blocchi + concat (la prima volta)
    py render_regia.py --evento 12           # solo il/i blocco/hi che contengono l'evento 12
    py render_regia.py --da 120 --a 135      # spezzone esatto, per guardare un passaggio
    py render_regia.py --tutto --bozza       # integrale a metà risoluzione, per il MOVIMENTO

Tre strumenti, tre domande diverse:

  contatti   «l'aspetto è giusto?»   ~9 s per evento, nessun render di video
  bozza      «il movimento è giusto?» metà risoluzione, qualità bassa
  blocchi    «è finito?»              qualità piena

Il contact sheet va guardato **prima** di renderizzare: correggere un'immagine
ferma è veloce, correggere un video animato no.

**I blocchi non si sovrascrivono.** Un ri-render scrive `blocco_03_v2.mp4` e il
montaggio prende sempre l'ultima versione. Capita spesso di preferire la versione
di prima, e senza questo tornare indietro è un lavoro.

**Audio: non lo tocca.** Esce video muto. Il mux della voce, degli effetti e il
loudnorm restano dove sono (build_audio.py + montage-filter.txt), come da
docs/RENDERER.md passo 3.
"""
from __future__ import annotations

import argparse
import os
from runtime import FFMPEG, remotion
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
REGIA = ROOT / "src" / "data" / "regia.json"
BUILD = ROOT / "build"
BUNDLE = BUILD / "bundle"
FONT_ETICHETTE = Path(os.environ.get("FONT_PATH", ""))

COMPOSIZIONE = "master-full"
ENTRY = "src/index.ts"
BLOCCO_FRAME = 2800
PAD_S = 0.5           # margine attorno a un evento, per prendere entrata e uscita
DOPO_ENTRATA_S = 0.6  # l'entrata a molla dura ~27 frame: il fermo si prende dopo


def lancia_npx(argomenti: list[str], **kw) -> subprocess.CompletedProcess:
    return remotion(argomenti[1:] if argomenti[0] == 'remotion' else argomenti, **kw)


def salva_errore(esito, operazione: str) -> Path:
    BUILD.mkdir(parents=True, exist_ok=True)
    log = BUILD / 'render-error.log'
    log.write_text(f'{operazione}\nexit={esito.returncode}\n\n[stdout]\n{esito.stdout or ""}\n\n[stderr]\n{esito.stderr or ""}', encoding='utf-8')
    return log


def carica_regia() -> dict:
    return json.loads(REGIA.read_text(encoding="utf-8"))


def blocchi(tot_frame: int) -> list[tuple[int, int]]:
    """[(primo, ultimo)] inclusivi, come li vuole --frames di Remotion."""
    return [(i, min(i + BLOCCO_FRAME - 1, tot_frame - 1))
            for i in range(0, tot_frame, BLOCCO_FRAME)]


def evento(regia: dict, id_evento: int) -> dict:
    ev = next((e for e in regia["events"] if e.get("id") == id_evento), None)
    if ev is None:
        raise SystemExit(f"evento {id_evento} non esiste in regia.json")
    return ev


def blocchi_di_evento(regia: dict, id_evento: int) -> list[int]:
    """Indici dei blocchi toccati da un evento (può stare a cavallo di due)."""
    ev = evento(regia, id_evento)
    fps = regia["fps"]
    f0 = max(0, int((ev["t0"] - PAD_S) * fps))
    f1 = int((ev.get("t1", ev["t0"] + 3) + PAD_S) * fps)
    return list(range(f0 // BLOCCO_FRAME, min(f1, round(regia["durSec"] * fps) - 1) // BLOCCO_FRAME + 1))


def cartella(bozza: bool) -> Path:
    return BUILD / ("blocchi-bozza" if bozza else "blocchi")


# ---- versioni dei blocchi ------------------------------------------------

def versioni(dir_b: Path, i: int) -> list[Path]:
    """Tutte le versioni del blocco i, dalla più vecchia alla più nuova."""
    trovate = []
    for p in dir_b.glob(f"blocco_{i:02d}*.mp4"):
        m = re.fullmatch(rf"blocco_{i:02d}(?:_v(\d+))?", p.stem)
        if m:
            trovate.append((int(m.group(1) or 1), p))
    return [p for _, p in sorted(trovate)]


def ultima_versione(dir_b: Path, i: int) -> Path | None:
    v = versioni(dir_b, i)
    return v[-1] if v else None


def prossima_versione(dir_b: Path, i: int) -> Path:
    precedenti = versioni(dir_b, i)
    n = max((int(re.search(r"_v(\d+)$", p.stem).group(1)) if re.search(r"_v(\d+)$", p.stem) else 1 for p in precedenti), default=0)
    return dir_b / (f"blocco_{i:02d}.mp4" if n == 0 else f"blocco_{i:02d}_v{n + 1}.mp4")


# ---- render --------------------------------------------------------------

def rendi(primo: int, ultimo: int, dest: Path, bozza: bool) -> float:
    """Rende l'intervallo di fotogrammi in dest. Ritorna i secondi impiegati."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["remotion", "render", COMPOSIZIONE, str(dest),
           f"--frames={primo}-{ultimo}", "--muted"]
    if bozza:
        # metà lato, qualità bassa: il movimento si legge lo stesso e costa un quarto
        cmd += ["--scale=0.5", "--crf=30", "--jpeg-quality=60"]
    else:
        cmd += ["--crf=16"]
    t = time.time()
    r = lancia_npx(cmd, capture_output=True, text=True,
                   encoding="utf-8", errors="ignore", cwd=str(ROOT))
    if r.returncode != 0:
        log = salva_errore(r, f'render frames {primo}-{ultimo}')
        raise RuntimeError(f"remotion fallito su {primo}-{ultimo}; log completo: {log}\n{r.stderr[-1500:]}")
    return time.time() - t


def concatena(bozza: bool, attesi: list[tuple[int, int]]) -> Path | None:
    """Unisce l'ultima versione di ogni blocco, senza ricodificare."""
    dir_b = cartella(bozza)
    pezzi = [ultima_versione(dir_b, i) for i in range(len(attesi))]
    if any(p is None for p in pezzi):
        mancanti = [f"blocco_{i:02d}" for i, p in enumerate(pezzi) if p is None]
        print(f"   concat saltato: mancano {len(mancanti)} blocchi ({', '.join(mancanti[:3])}…)")
        return None
    lista = dir_b / "elenco.txt"
    # Paths relative to this manifest also work under project folders containing quotes.
    lista.write_text("".join(f"file '{p.name}'\n" for p in pezzi), encoding="utf-8")
    dest = BUILD / ("master-video-bozza.mp4" if bozza else "master-video.mp4")
    r = subprocess.run(
        [FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(dest)],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
    )
    if r.returncode != 0:
        raise RuntimeError(f"concat fallito:\n{r.stderr[-800:]}")
    print("   montato con: " + ", ".join(p.name for p in pezzi))
    return dest


# ---- contact sheet -------------------------------------------------------

def pacchetto() -> None:
    """Prepara il bundle una volta sola: senza, ogni fotogramma ricompila tutto."""
    # il bundle non apre Chrome: serve solo il nome giusto del binario npx
    r = remotion(["bundle", ENTRY, f"--out-dir={BUNDLE}"], browser=False,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="ignore", cwd=str(ROOT))
    if r.returncode != 0:
        log = salva_errore(r, 'bundle')
        raise RuntimeError(f"bundle fallito; log completo: {log}\n{r.stderr[-1000:]}")


def fermo(frame: int, dest: Path, scala: float) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = lancia_npx(
        ["remotion", "still", str(BUNDLE), COMPOSIZIONE, str(dest),
         f"--frame={frame}", f"--scale={scala}"],
        capture_output=True, text=True, encoding="utf-8", errors="ignore", cwd=str(ROOT))
    if r.returncode != 0:
        log = salva_errore(r, f'still frame {frame}')
        raise RuntimeError(f"still fallito al fotogramma {frame}; log completo: {log}\n{r.stderr[-800:]}")


def istante_rappresentativo(ev: dict) -> float:
    """Il secondo in cui l'evento è "pieno", non quello in cui comincia.

    Le tavole a schermo intero si costruiscono per momenti (il campo `k`): presa a
    t0 + mezzo secondo si fotografa una pagina ancora vuota. Con i momenti si va
    dopo l'ultimo; senza, basta lasciar finire l'entrata a molla.
    """
    momenti: list[float] = []
    k = ev.get("k")
    if isinstance(k, dict):
        momenti += [float(v) for v in k.values()]
    # Il contenuto di card, pills, grid, chat… è una lista di voci con il proprio
    # tempo: prese a t0 si fotografa un contenitore vuoto. Contano anche quelle,
    # e i campi singoli con un tempo dentro (coda, biforcazione, timbro).
    for campo in ("rows", "bullets", "pills", "lines", "cells", "nodes",
                  "steps", "bubbles", "bars", "checks"):
        v = ev.get(campo)
        if isinstance(v, list):
            momenti += [float(x["t"]) for x in v
                        if isinstance(x, dict) and isinstance(x.get("t"), (int, float))]
            if campo in ("rows", "bullets"):
                # Typewriter text needs more than a spring's entrance time.
                momenti += [float(x["t"]) + len(str(x.get("text", ""))) / 27
                            for x in v if isinstance(x, dict) and isinstance(x.get("t"), (int, float))]
    for campo in ("tail", "fork", "stamp", "loop"):
        v = ev.get(campo)
        if isinstance(v, dict) and isinstance(v.get("t"), (int, float)):
            momenti.append(float(v["t"]))
    if momenti:
        t = max(momenti) + 0.4
    else:
        t = ev["t0"] + DOPO_ENTRATA_S
    t1 = ev.get("t1")
    if t1 is not None:
        t = min(t, float(t1) - 0.15)
    return max(float(ev["t0"]), t)


def etichetta(ev: dict) -> str:
    """Riga sotto il fotogramma: chi è questo evento, in una riga sola."""
    titolo = ev.get("title") or ev.get("fs") or ev.get("text") or ""
    titolo = re.sub(r"[*_]", "", str(titolo))
    m, s = divmod(int(ev["t0"]), 60)
    return f"#{ev['id']:02d} {m:d}:{s:02d} {ev.get('type', '')} — {titolo}"[:64]


def contact_sheet(regia: dict, ids: list[int], scala: float = 0.25,
                  colonne: int = 5) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    if not ids:
        raise ValueError("Nessun evento nel piano: contact sheet non necessario.")

    fps = regia["fps"]
    tot = int(round(regia["durSec"] * fps))
    dir_f = BUILD / "contatti"
    dir_f.mkdir(parents=True, exist_ok=True)

    print(f"preparo il bundle…")
    pacchetto()

    immagini: list[tuple[Path, dict]] = []
    for n, ide in enumerate(ids, 1):
        ev = evento(regia, ide)
        f = min(tot - 1, int(istante_rappresentativo(ev) * fps))
        dest = dir_f / f"ev{ide:02d}.png"
        t = time.time()
        fermo(f, dest, scala)
        print(f"  [{n}/{len(ids)}] evento {ide:02d} — fotogramma {f} — {time.time()-t:.0f}s")
        immagini.append((dest, ev))

    prime = Image.open(immagini[0][0])
    w, h = prime.size
    alt_et = 34
    righe = (len(immagini) + colonne - 1) // colonne
    margine = 16
    foglio = Image.new("RGB",
                       (colonne * w + margine * (colonne + 1),
                        righe * (h + alt_et) + margine * (righe + 1)),
                       "#101010")
    dis = ImageDraw.Draw(foglio)
    try:
        font = ImageFont.truetype(str(FONT_ETICHETTE), 15)
    except Exception:
        font = ImageFont.load_default()

    for i, (p, ev) in enumerate(immagini):
        r, c = divmod(i, colonne)
        x = margine + c * (w + margine)
        y = margine + r * (h + alt_et + margine)
        foglio.paste(Image.open(p).convert("RGB"), (x, y))
        dis.text((x + 2, y + h + 8), etichetta(ev), font=font, fill="#ffffff")

    dest = BUILD / "contact-sheet.png"
    foglio.save(dest)
    return dest


# ---- stato ---------------------------------------------------------------

def stato(regia: dict, bozza: bool) -> None:
    tot = int(round(regia["durSec"] * regia["fps"]))
    bl = blocchi(tot)
    dir_b = cartella(bozza)
    print(f"{COMPOSIZIONE}: {tot} fotogrammi, {regia['durSec']:.1f}s, "
          f"{len(bl)} blocchi da {BLOCCO_FRAME}")
    print(f"cartella: {dir_b}")
    for i, (a, b) in enumerate(bl):
        vs = versioni(dir_b, i)
        segno = "ok " if vs else "-- "
        if vs:
            dim = f"{vs[-1].stat().st_size/1_000_000:.0f} MB"
            ver = f"{vs[-1].name}" + (f"  ({len(vs)} versioni)" if len(vs) > 1 else "")
        else:
            dim, ver = "da fare", ""
        ev = [e["id"] for e in regia["events"]
              if a <= int(e["t0"] * regia["fps"]) <= b]
        print(f"  {segno}blocco_{i:02d}  f{a}-{b}  {a/regia['fps']:6.1f}s-{b/regia['fps']:6.1f}s  "
              f"{dim:>8}  eventi {ev if ev else '—'}  {ver}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a blocchi del video lungo.")
    ap.add_argument("--tutto", action="store_true", help="rende tutti i blocchi mancanti")
    ap.add_argument("--evento", type=int, nargs="+", help="eventi su cui lavorare")
    ap.add_argument("--contatti", action="store_true",
                    help="un fotogramma per evento in una tavola sola, prima di renderizzare")
    ap.add_argument("--da", type=float, help="inizio spezzone in secondi")
    ap.add_argument("--a", type=float, help="fine spezzone in secondi")
    ap.add_argument("--bozza", action="store_true", help="metà risoluzione, qualità bassa")
    ap.add_argument("--forza", action="store_true",
                    help="rifà i blocchi già presenti creando una versione nuova")
    ap.add_argument("--stato", action="store_true", help="elenca i blocchi e si ferma")
    args = ap.parse_args()

    regia = carica_regia()
    fps = regia["fps"]
    tot = int(round(regia["durSec"] * fps))

    if fps != 30 or tot <= 0:
        raise SystemExit("Il motore nativo richiede fps=30 e durata positiva.")

    if args.contatti:
        ids = args.evento or [e["id"] for e in regia["events"]]
        print(f"contact sheet di {len(ids)} eventi (~9s l'uno)")
        dest = contact_sheet(regia, ids)
        print(f"\ntavola: {dest}")
        print("guardala prima di renderizzare: correggere un fermo costa niente.")
        return 0

    if args.stato or not (args.tutto or args.evento or args.da is not None):
        stato(regia, args.bozza)
        return 0

    if args.da is not None:
        if args.a is None:
            raise SystemExit("--da vuole anche --a")
        if not 0 <= args.da < args.a <= regia['durSec']:
            raise SystemExit("Intervallo non valido: serve 0 <= --da < --a <= durata.")
        f0, f1 = int(args.da * fps), min(int(args.a * fps), tot - 1)
        dest = BUILD / "spezzoni" / f"{int(args.da)}s-{int(args.a)}s{'-bozza' if args.bozza else ''}.mp4"
        print(f"spezzone {args.da:.1f}s-{args.a:.1f}s (f{f0}-{f1}) → {dest.name}")
        print(f"   fatto in {rendi(f0, f1, dest, args.bozza):.0f}s: {dest}")
        return 0

    bl = blocchi(tot)
    if args.tutto:
        indici = list(range(len(bl)))
    else:
        indici = sorted({i for ide in args.evento for i in blocchi_di_evento(regia, ide)})
        print(f"eventi {args.evento} → blocchi {indici}")

    dir_b = cartella(args.bozza)
    fatti = 0
    for i in indici:
        a, b = bl[i]
        if ultima_versione(dir_b, i) and not args.forza:
            print(f"  blocco_{i:02d} già presente, salto (--forza per farne una versione nuova)")
            continue
        dest = prossima_versione(dir_b, i)
        print(f"  {dest.stem}  f{a}-{b}  ({(b-a+1)/fps:.0f}s di video)…")
        print(f"     fatto in {rendi(a, b, dest, args.bozza)/60:.1f} min")
        fatti += 1

    if fatti or args.tutto:
        dest = concatena(args.bozza, bl)
        if dest:
            print(f"\nmontato: {dest}")
            print("audio non incluso: eseguire build_audio.py e consegna.py")
    else:
        print("niente da fare.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
