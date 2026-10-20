"""Cancello di qualità sugli short esportati — soglia 95/100.

Uso:
    py qa_check.py                      # controlla tutto quello che c'è in out/
    py qa_check.py out/short_01_*.mp4   # controlla file specifici
    py qa_check.py --json               # esito in JSON, per farlo leggere a un altro script

Esce con codice 1 se anche un solo file sta sotto la soglia: si può mettere in
catena dopo render.py senza guardare l'output a occhio.

Controlla quello che si può misurare da fuori, senza aprire il video: formato,
loudness, frame neri, congelamenti, attacco muto, compressione, e la
sovrapposizione fra hook parlato e banner scritto (regola in HOOK-GUIDE.md).
Non giudica il montaggio: quello resta un giudizio umano.
"""
from __future__ import annotations

import _bootstrap  # shared local paths, tools and cache

import argparse
import glob
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from config import OUT_DIR, OUT_W, OUT_H, ROOT

SOGLIA = 95.0
BRAND_KIT = ROOT.parent / "brand-kit.json"

# Tolleranze. Vengono dai target già usati in render.py (LOUDNORM in config.py):
# se si cambia il target lì, vanno cambiate anche qui.
LUFS_TARGET = -14.0
LUFS_TOLLERANZA = 1.0
TRUE_PEAK_MAX = -1.0          # dBTP, headroom per i transcodifica delle piattaforme
BITRATE_MIN = 2_500_000       # bit/s: sotto si vede la compressione sui movimenti
SILENZIO_ATTACCO_MAX = 0.35   # s di muto tollerati in apertura
DURATA_MAX_CONSIGLIATA = 90.0 # s: oltre, non è più uno short

# Parole senza peso: due frasi che condividono solo queste non si somigliano.
STOPWORD = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "a", "da", "in",
    "con", "su", "per", "tra", "fra", "e", "ed", "o", "ma", "che", "chi", "cui",
    "non", "ci", "si", "ti", "mi", "vi", "ne", "del", "dello", "della", "dei",
    "degli", "delle", "al", "allo", "alla", "ai", "agli", "alle", "dal", "dalla",
    "nel", "nella", "nei", "negli", "nelle", "sul", "sulla", "è", "e'", "sono",
    "ho", "hai", "ha", "hanno", "come", "quando", "più", "piu", "meno", "anche",
    "se", "poi", "già", "gia", "ogni", "tutto", "tutti", "questa", "questo",
}


def ffprobe(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe fallito: {r.stderr.strip()[:200]}")
    return json.loads(r.stdout)


def ffmpeg_filtro(path: Path, filtro: str, audio: bool) -> str:
    """Esegue un filtro di analisi e restituisce lo stderr (dove ffmpeg scrive i report)."""
    flag = "-af" if audio else "-vf"
    r = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(path), flag, filtro,
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
    )
    return r.stderr or ""


def normalizza(testo: str) -> set[str]:
    """Parole significative, senza accenti né punteggiatura: per confrontare due frasi."""
    t = unicodedata.normalize("NFD", testo.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    parole = re.findall(r"[a-z0-9']+", t)
    return {p for p in parole if p not in STOPWORD and len(p) > 2}


def somiglianza(a: str, b: str) -> float:
    """Quanto del banner è già nella frase parlata (0 = niente in comune, 1 = identici)."""
    pa, pb = normalizza(a), normalizza(b)
    if not pa or not pb:
        return 0.0
    return len(pa & pb) / len(pa | pb)


def piano_dello_short(nome_file: str) -> dict | None:
    """Ritrova la voce di fx_plans.json che corrisponde a questo output."""
    piano = ROOT / "fx_plans.json"
    if not piano.exists():
        return None
    for voce in json.loads(piano.read_text(encoding="utf-8")):
        if Path(voce.get("src", "")).stem in nome_file:
            return voce
    return None


#: Quanto puo' scostarsi la frequenza vera da quella dichiarata nel kit.
#: Mezzo fotogramma copre le frequenze frazionarie che arrotondano a quella
#: giusta (30000/1001 = 29,97 contro 30) senza lasciar passare un 24 dichiarato
#: come 30, che e' lo scarto che si vede a occhio.
TOLLERANZA_FPS = 0.5


def frequenza(video: dict) -> float | None:
    """I fotogrammi al secondo veri, dalla frazione che ffprobe restituisce.

    ffprobe da' 'r_frame_rate' come frazione ('30/1', '30000/1001'): e' cosi'
    che si rappresenta 29,97 senza perderci un decimale per strada. Torna None
    quando il campo non c'e' o non e' interpretabile: «non lo so» e' un esito,
    e vale piu' di un numero inventato.
    """
    for chiave in ("r_frame_rate", "avg_frame_rate"):
        grezzo = str(video.get(chiave) or "").strip()
        if "/" not in grezzo:
            continue
        sopra, sotto = grezzo.split("/", 1)
        try:
            numeratore, denominatore = float(sopra), float(sotto)
        except ValueError:
            continue
        if denominatore > 0 and numeratore > 0:
            return numeratore / denominatore
    return None


def formato_atteso(w: int, h: int) -> dict:
    """Le regole cambiano fra short verticale e video lungo: le prende dal brand kit.

    Senza questo, il video lungo veniva bocciato per 'risoluzione sbagliata' e
    'troppo lungo' — regole degli short applicate a un formato che non è quello.
    """
    verticale = h > w
    if BRAND_KIT.exists():
        f = json.loads(BRAND_KIT.read_text(encoding="utf-8"))["formati"]
        d = f["short"] if verticale else f["long_form"]
        return {"nome": "short" if verticale else "long form",
                "w": d["larghezza"], "h": d["altezza"], "fps": d["fps"],
                "verticale": verticale}
    return {"nome": "short" if verticale else "long form",
            "w": OUT_W if verticale else OUT_H, "h": OUT_H if verticale else OUT_W,
            "fps": 30, "verticale": verticale}


#: Gli estremi oltre i quali il soggetto non si vede piu'. Non sono una soglia
#: di gusto: sotto 35 su 255 un volto e' una macchia scura, sopra 225 e' una
#: macchia bianca. In mezzo c'e' tutto il territorio delle scelte di ripresa,
#: e li' un controllo automatico non ha voce in capitolo.
LUMA_MIN_SOGGETTO = 35
LUMA_MAX_SOGGETTO = 225

#: Ogni quanti fotogrammi campionare. Uno al secondo su un video a 30: basta
#: per una mediana stabile e costa una frazione del tempo di una passata.
PASSO_CAMPIONE = 30


def luminanza_centrale(path: Path, larghezza: int, altezza: int) -> float | None:
    """La luminanza mediana della fascia centrale, dove sta il volto.

    Si ritaglia meta' larghezza e un terzo di altezza attorno al centro: in un
    9:16 col ritaglio face-aware il volto e' li'. Non e' rilevamento del volto
    ed e' voluto — cv2 su ogni fotogramma costerebbe piu' di tutto il resto del
    controllo, e per distinguere «buio» da «esposto» la fascia basta.

    None quando non si legge: «non lo so» e' un esito, e vale piu' di un numero
    inventato.
    """
    larghezza_ritaglio = max(2, (larghezza // 2) // 2 * 2)
    altezza_ritaglio = max(2, (altezza // 3) // 2 * 2)
    x = max(0, (larghezza - larghezza_ritaglio) // 2)
    y = max(0, (altezza - altezza_ritaglio) // 2)
    filtro = (f"select=not(mod(n\\,{PASSO_CAMPIONE}))"
              f",crop={larghezza_ritaglio}:{altezza_ritaglio}:{x}:{y}"
              ",signalstats,metadata=print:file=-")
    esito_ff = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vf", filtro, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    valori = []
    for riga in esito_ff.stdout.splitlines():
        if "YAVG=" not in riga:
            continue
        try:
            valori.append(float(riga.split("YAVG=", 1)[1].strip()))
        except ValueError:
            continue
    if not valori:
        return None
    valori.sort()
    meta_ = len(valori) // 2
    return valori[meta_] if len(valori) % 2 else (valori[meta_ - 1] + valori[meta_]) / 2


def controlla(path: Path) -> dict:
    """Restituisce punteggio, righe di esito e problemi bloccanti per un file."""
    esiti: list[tuple[str, bool | None, str]] = []   # (nome, passato, dettaglio)

    def esito(nome, passato, dettaglio=""):
        esiti.append((nome, passato, dettaglio))

    info = ffprobe(path)
    fmt = info["format"]
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    durata = float(fmt.get("duration", 0.0))

    # --- formato ---------------------------------------------------------
    fmt_atteso = {"nome": "sconosciuto", "verticale": True}
    if video is None:
        esito("traccia video", False, "assente")
    else:
        w, h = video["width"], video["height"]
        fmt_atteso = formato_atteso(w, h)
        esito("risoluzione", (w, h) == (fmt_atteso["w"], fmt_atteso["h"]),
              f"{w}x{h}, atteso {fmt_atteso['w']}x{fmt_atteso['h']} ({fmt_atteso['nome']})")
        esito("pix_fmt", video.get("pix_fmt") == "yuv420p",
              f"{video.get('pix_fmt')} — fuori da yuv420p alcune app sbagliano i livelli")
        # La FREQUENZA DEI FOTOGRAMMI. Il kit la dichiara e fin qui nessuno la
        # guardava: la parola «fps» non compariva in nessun esito, pur essendo
        # letta da formato_atteso. render.py non passa mai -r, quindi la
        # frequenza dell'uscita e' quella del girato, qualunque essa sia.
        #
        # Un girato in modalita' cinema esce a 23,976 fotogrammi al secondo,
        # cioe' a una frequenza frazionaria che alcune piattaforme rifiutano e
        # altre riproducono a scatti. Non lascia messaggi d'errore: lo si
        # scopre guardando il video, cioe' dopo aver pubblicato.
        #
        # Misurato il 21/08/2026 su sei girati veri: tutti e sei a 30/1
        # esatti, e gli short escono a 30/1. Oggi quindi non morde. Il
        # controllo c'e' perche' il giorno che mordera' nessun altro se ne
        # accorgerebbe.
        fps_visto = frequenza(video)
        fps_atteso = float(fmt_atteso["fps"])
        esito("fotogrammi al secondo",
              None if fps_visto is None else abs(fps_visto - fps_atteso) <= TOLLERANZA_FPS,
              "non leggibile" if fps_visto is None else
              f"{fps_visto:.3f}, atteso {fps_atteso:.0f} ({fmt_atteso['nome']})")
        br = int(video.get("bit_rate") or 0) or int(
            (int(fmt.get("bit_rate") or 0)) * 0.92)
        esito("bitrate video", br >= BITRATE_MIN,
              f"{br/1_000_000:.1f} Mb/s, minimo {BITRATE_MIN/1_000_000:.1f}")

    esito("traccia audio", audio is not None, "assente" if audio is None else "presente")
    if fmt_atteso["verticale"]:
        esito("durata", 0 < durata <= DURATA_MAX_CONSIGLIATA,
              f"{durata:.1f}s, consigliato entro {DURATA_MAX_CONSIGLIATA:.0f}s")
    else:
        esito("durata", durata > 0, f"{durata:.1f}s (nessun tetto sul video lungo)")

    # moov all'inizio: senza faststart il video parte solo a scaricamento finito
    with path.open("rb") as f:
        testa = f.read(4_000_000)
    pos_moov, pos_mdat = testa.find(b"moov"), testa.find(b"mdat")
    esito("faststart", pos_moov != -1 and (pos_mdat == -1 or pos_moov < pos_mdat),
          "moov dopo mdat: manca -movflags +faststart" if pos_moov == -1 or
          (pos_mdat != -1 and pos_moov > pos_mdat) else "moov in testa")

    # --- audio -----------------------------------------------------------
    if audio is not None:
        log = ffmpeg_filtro(path, "ebur128=peak=true", audio=True)
        m_i = re.findall(r"^\s*I:\s*(-?\d+\.?\d*)\s*LUFS", log, re.M)
        m_p = re.findall(r"^\s*Peak:\s*(-?\d+\.?\d*)\s*dBFS", log, re.M)
        if m_i:
            lufs = float(m_i[-1])
            esito("loudness", abs(lufs - LUFS_TARGET) <= LUFS_TOLLERANZA,
                  f"{lufs:.1f} LUFS, target {LUFS_TARGET:.0f} ±{LUFS_TOLLERANZA:.0f}")
        else:
            esito("loudness", None, "non misurabile")
        if m_p:
            peak = float(m_p[-1])
            esito("true peak", peak <= TRUE_PEAK_MAX,
                  f"{peak:.1f} dBTP, massimo {TRUE_PEAK_MAX:.0f}")

        log_sil = ffmpeg_filtro(path, "silencedetect=n=-40dB:d=0.25", audio=True)
        inizi = [float(x) for x in re.findall(r"silence_start:\s*(-?\d+\.?\d*)", log_sil)]
        fini = [float(x) for x in re.findall(r"silence_end:\s*(\d+\.?\d*)", log_sil)]
        muto_iniziale = fini[0] if (inizi and inizi[0] <= 0.05 and fini) else 0.0
        esito("attacco", muto_iniziale <= SILENZIO_ATTACCO_MAX,
              f"{muto_iniziale:.2f}s di muto in apertura, massimo {SILENZIO_ATTACCO_MAX}")

    # --- video -----------------------------------------------------------
    log_v = ffmpeg_filtro(
        path, "blackdetect=d=0.15:pic_th=0.97,freezedetect=n=-60dB:d=1.5", audio=False)
    neri = re.findall(r"black_start:(\d+\.?\d*)", log_v)
    esito("frame neri", not neri,
          f"{len(neri)} tratto/i nero/i (primo a {neri[0]}s)" if neri else "nessuno")
    freeze = re.findall(r"freeze_start:\s*(\d+\.?\d*)", log_v)
    esito("immagine ferma", not freeze,
          f"{len(freeze)} congelamento/i (primo a {freeze[0]}s)" if freeze else "nessuno")

    # --- esposizione del SOGGETTO, non dell'inquadratura -----------------
    #
    # QUELLO CHE QUESTO CONTROLLO NON FA, e va detto prima di cosa fa.
    # Non giudica se il video e' «bello». Non misura il contrasto fra soggetto
    # e sfondo, e c'e' un motivo misurato: il 21/08/2026 su sei short veri il
    # centro risultava fino a 44 punti piu' scuro dell'inquadratura, e
    # sembrava controluce. Guardando il fotogramma non lo era affatto — il
    # volto era esposto bene, era il CIELO a bruciare a 255 e a tirare su la
    # media. Un controllo costruito su quello scarto avrebbe bocciato tre
    # short su sei perfettamente pubblicabili.
    #
    # QUELLO CHE FA: misura la luminanza mediana della fascia centrale, dove
    # il ritaglio face-aware ha gia' messo il volto, e la riporta SEMPRE. Ma
    # boccia solo agli estremi indiscutibili — un soggetto praticamente nero o
    # praticamente bianco — perche' li' non c'e' niente da interpretare.
    #
    # I SEI SHORT VERI stanno fra 112 e 140 su 255, cioe' tutti comodamente in
    # mezzo. Su questo materiale il controllo non ha niente da dire, ed e'
    # giusto cosi': serve al giorno che qualcuno riprende al buio.
    centro = luminanza_centrale(path, w, h) if video is not None else None
    if centro is None:
        esito("esposizione del soggetto", None, "non misurabile")
    else:
        esito("esposizione del soggetto",
              LUMA_MIN_SOGGETTO <= centro <= LUMA_MAX_SOGGETTO,
              f"{centro:.0f} su 255"
              + ("" if LUMA_MIN_SOGGETTO <= centro <= LUMA_MAX_SOGGETTO
                 else f" — fuori da {LUMA_MIN_SOGGETTO}-{LUMA_MAX_SOGGETTO}, "
                      + ("troppo buio" if centro < LUMA_MIN_SOGGETTO else "bruciato")))

    # --- hook: il banner non deve ripetere la voce (HOOK-GUIDE.md) -------
    meta = path.with_suffix(".json")
    piano = piano_dello_short(path.stem)
    parlato = ""
    if meta.exists():
        parlato = json.loads(meta.read_text(encoding="utf-8")).get("hook_sentence", "")
    banner = ""
    if piano:
        banner = next((e.get("text", "") for e in piano.get("events", [])
                       if e.get("type") == "pill"), "")
    if parlato and banner:
        s = somiglianza(banner, parlato)
        esito("hook non ripetuto", s < 0.30,
              f"sovrapposizione {s:.0%} fra banner e parlato, massimo 30%")
    else:
        esito("hook non ripetuto", None, "manca il metadata o la pill: non verificabile")

    verificati = [e for e in esiti if e[1] is not None]
    passati = [e for e in verificati if e[1]]
    punteggio = 100.0 * len(passati) / len(verificati) if verificati else 0.0
    return {
        "file": path.name,
        "punteggio": round(punteggio, 1),
        "passa": punteggio >= SOGLIA,
        "esiti": [{"controllo": n, "esito": p, "dettaglio": d} for n, p, d in esiti],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Cancello di qualità sugli short (95/100).")
    ap.add_argument("file", nargs="*", help="file .mp4 (default: tutti quelli in out/)")
    ap.add_argument("--json", action="store_true", help="esito in JSON")
    args = ap.parse_args()

    percorsi: list[Path] = []
    for arg in args.file:
        percorsi += [Path(p) for p in glob.glob(arg)]
    if not percorsi:
        percorsi = sorted(OUT_DIR.glob("*.mp4"))
    percorsi = [p for p in percorsi if p.suffix.lower() == ".mp4" and p.exists()]

    if not percorsi:
        print("Nessun file da controllare.")
        return 1

    rapporti = []
    for p in percorsi:
        try:
            rapporti.append(controlla(p))
        except Exception as e:  # un file rotto non deve fermare il lotto
            rapporti.append({"file": p.name, "punteggio": 0.0, "passa": False,
                             "esiti": [{"controllo": "lettura", "esito": False,
                                        "dettaglio": str(e)[:200]}]})

    if args.json:
        print(json.dumps(rapporti, ensure_ascii=False, indent=1))
    else:
        for r in rapporti:
            segno = "OK  " if r["passa"] else "NO  "
            print(f"\n{segno} {r['file']} — {r['punteggio']:.0f}/100")
            for e in r["esiti"]:
                if e["esito"] is True:
                    continue  # si stampa solo quello che non va: il resto è rumore
                marca = "  ?" if e["esito"] is None else "  x"
                print(f"{marca} {e['controllo']}: {e['dettaglio']}")
        bocciati = [r for r in rapporti if not r["passa"]]
        print(f"\n{len(rapporti) - len(bocciati)}/{len(rapporti)} passano la soglia "
              f"di {SOGLIA:.0f}/100.")

    return 1 if any(not r["passa"] for r in rapporti) else 0


if __name__ == "__main__":
    sys.exit(main())
