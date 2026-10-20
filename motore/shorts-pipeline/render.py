"""Stadio 3+4+5: risolve gli highlights scelti, calcola il crop 9:16, genera sottotitoli ASS karaoke e renderizza gli shorts.

Uso:
    py render.py VIDEO [--highlights build/highlights.json] [--no-subs]
                       [--correzioni build/correzioni.json] [--solo-clip NOME]

Input:
    build/<video>.transcript.json   (da transcribe.py)
    build/highlights.json           formato:
        {"highlights": [{"title": str, "seg_start_idx": int, "seg_end_idx": int,
                         "score": int, "hook_sentence": str, "virality_reason": str}]}
    Gli indici si riferiscono alla colonna [idx] di <video>.for_llm.txt.
    build/correzioni.json           facoltativo, formato in correzioni.py:
        ritaglio e taglio corretti per singola clip. Assente = niente cambia.
    build/tagli.json                facoltativo, formato in tagli.py:
        i BUCHI tolti da dentro una clip (pause, parole). Assente = niente
        cambia. I due file sono indipendenti: le correzioni spostano i bordi
        del taglio, i tagli tolgono materiale in mezzo.

Con i buchi una clip smette di essere una finestra sola sul girato e diventa
un ELENCO DI PEZZI. Da quel momento ogni tempo dentro la clip va RIBASATO:
i tempi delle parole nei sottotitoli, le sillabe del karaoke che ne
discendono, e — nel passo dopo — gli eventi del piano overlay. La matematica
sta tutta in tagli.py, e qui si usa: non se ne rifa' una seconda copia.

Output:
    out/short_NN_<slug>.mp4  +  out/short_NN_<slug>.json (metadati per il posting)

--solo-clip NOME rifa' una clip sola, lasciando le altre dove sono: out/ NON
si svuota e gli altri file non si toccano. Serve alla correzione mirata («nel
secondo short il volto e' tagliato»), che altrimenti costerebbe il rifacimento
di tutto il giro. Il NOME e' il nome base del file ('short_02_...'): si
accettano anche 'short_02_....mp4' e 'short_02_...-FX.mp4'.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import config
import correzioni
import fondamenta
import karaoke
import silenzi
import tagli

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Quanti secondi di girato si decodificano PRIMA del primo pezzo quando una
# clip e' fatta di piu' tratti. Con piu' pezzi non si puo' usare il taglio
# secco di ffmpeg: si passa da un filter_complex che ritaglia e riattacca, e
# quel filtro lavora sui tempi dell'ingresso gia' posizionato. Due secondi di
# margine coprono il salto al fotogramma chiave senza costringere ffmpeg a
# decodificare mezz'ora di girato per arrivare al minuto 30.
MARGINE_SEEK_S = 2.0


# ---------- resolve: indici -> tempi (anti-allucinazione timestamp) ----------

def resolve_highlights(hl_raw: list[dict], segments: list[dict], duration: float,
                      scarti: list[dict] | None = None) -> list[dict]:
    """I momenti proposti dal modello, filtrati e ripuliti dai doppioni.

    `scarti` raccoglie i momenti BUTTATI col loro motivo. Fin qui i motivi
    esistevano — «troppo corto», «doppione», «indici fuori range» — ma
    finivano solo a schermo, dove non li legge nessuno. Il cliente vedeva sei
    short al posto di otto e non aveva modo di sapere perche': l'unica domanda
    che poteva fare era «perche' sono solo sei?», e la risposta non c'era da
    nessuna parte.
    """
    def butta(titolo, motivo, dettaglio=""):
        print(f"  SCARTO ({motivo}{': ' + dettaglio if dettaglio else ''}): {titolo}")
        if scarti is not None:
            scarti.append({"titolo": titolo, "motivo": motivo, "dettaglio": dettaglio})

    resolved = []
    for h in hl_raw:
        try:
            i0, i1 = int(h["seg_start_idx"]), int(h["seg_end_idx"])
        except (KeyError, ValueError, TypeError):
            butta(h.get("title"), "indici mancanti")
            continue
        if not (0 <= i0 < len(segments)) or not (0 <= i1 < len(segments)) or i1 < i0:
            butta(h.get("title"), "indici fuori range", f"[{i0}-{i1}]")
            continue
        seg0, seg1 = segments[i0], segments[i1]
        start = (seg0["words"][0]["start"] if seg0["words"] else seg0["start"]) + config.PAD_START_S
        end = (seg1["words"][-1]["end"] if seg1["words"] else seg1["end"]) + config.PAD_END_S
        start, end = max(0.0, start), min(duration, end)
        dur = end - start
        if dur < config.MIN_CLIP_S:
            butta(h.get("title"), "troppo corto",
                  f"{dur:.0f}s, il minimo e' {config.MIN_CLIP_S:.0f}s")
            continue
        if dur > config.MAX_CLIP_S:
            print(f"  AVVISO: {h.get('title')} dura {dur:.0f}s (>{config.MAX_CLIP_S:.0f}s), tengo comunque")
        resolved.append({**h,
                         "start": fondamenta.arrotonda_decimale(start),
                         "end": fondamenta.arrotonda_decimale(end)})

    # dedupe simmetrico: overlap >50% di UNA delle due durate -> vince lo score
    resolved.sort(key=lambda h: -int(h.get("score", 0)))
    kept: list[dict] = []
    for h in resolved:
        dup = False
        for k in kept:
            ov = min(h["end"], k["end"]) - max(h["start"], k["start"])
            if ov > 0:
                if ov > config.DEDUPE_OVERLAP * min(h["end"] - h["start"], k["end"] - k["start"]):
                    dup = True
                    break
            if abs(h["start"] - k["start"]) + abs(h["end"] - k["end"]) < 15.0:
                dup = True
                break
        if dup:
            butta(h.get("title"), "doppione",
                  "si sovrappone a un momento gia' tenuto, con punteggio piu' alto")
        else:
            kept.append(h)
    kept.sort(key=lambda h: h["start"])
    return kept


# ---------- reframe: crop_x statico face-aware ----------

YUNET_MODEL = Path(os.environ.get("YUNET_MODEL_PATH", str(config.ROOT / "models" / "face_detection_yunet_2023mar.onnx")))


def compute_crop_x(video: Path, start: float, end: float, src_w: int, src_h: int,
                   ancora_x: float = 0.0, crop_w: int | None = None) -> tuple[int, dict]:
    """Dove mettere il ritaglio 9:16, con lo scostamento chiesto a mano.

    start/end sono gia' i tempi CORRETTI della clip: e' cosi' che i pad
    arrivano fin qui. Non e' un dettaglio — i volti vanno cercati nel pezzo di
    girato che finira' davvero nello short: se la clip e' stata allungata di
    due secondi all'attacco, quei due secondi devono pesare sulla mediana come
    tutti gli altri, o il ritaglio resta buono per un video che non esiste
    piu'.

    ancora_x sposta il ritaglio di una frazione della larghezza del girato
    (+0.08 = 8% a destra). Vale su TUTTI i rami, anche quando i volti non si
    trovano e il ritaglio finisce al centro: e' proprio li' che una persona ha
    piu' bisogno di poterlo spostare a mano.

    Torna (x, dettaglio): 'dettaglio' porta il valore che sarebbe uscito senza
    correzione, lo spostamento in pixel e gli avvisi sui limiti raggiunti.
    Con ancora_x = 0 il valore e' identico a quello di prima.
    """
    # La larghezza EFFETTIVA del ritaglio, non la costante: su un sorgente
    # piu' stretto di CROP_W i due numeri divergono, e collocare il ritaglio
    # con una larghezza che non e' la sua sbaglia sia il centro sia il limite.
    larghezza = int(crop_w) if crop_w else min(config.CROP_W, src_w)

    def esito(x_grezzo):
        return correzioni.applica_ancora_x(x_grezzo, ancora_x, src_w, larghezza)

    if not YUNET_MODEL.exists():
        print("    AVVISO: modello YuNet mancante, crop centrato")
        return esito((src_w - larghezza) // 2)
    try:
        import cv2
    except (ImportError, OSError) as error:
        print(f"    AVVISO: OpenCV non disponibile ({error}), crop centrato")
        return esito((src_w - larghezza) // 2)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return esito((src_w - larghezza) // 2)
    small_w, small_h = 960, int(src_h * 960 / src_w)
    detector = cv2.FaceDetectorYN.create(str(YUNET_MODEL), "", (small_w, small_h), 0.6)
    dur = end - start
    t0 = start + dur / 8  # evita frame di transizione all'attacco
    samples = [t0 + i * (end - t0) / 10 for i in range(11)]
    scale = small_w / src_w
    centers = []
    for t in samples:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        small = cv2.resize(frame, (small_w, small_h))
        _, faces = detector.detect(small)
        if faces is not None and len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])[:4]  # faccia più grande = speaker
            centers.append((x + w / 2) / scale)
    cap.release()

    if not centers:
        return esito((src_w - larghezza) // 2)
    centers.sort()
    median = centers[len(centers) // 2]
    import statistics
    if len(centers) > 2 and statistics.pstdev(centers) > 0.04 * src_w:
        print("    AVVISO: faccia si muove molto, crop statico potrebbe tagliarla")
    # meta' lontano da zero, mai il round di fabbrica (che e' a meta' pari):
    # con una mediana a .5 esatti i due danno due ritagli diversi di un pixel.
    x = fondamenta.arrotonda(median - larghezza / 2)
    return esito(x)


# ---------- sottotitoli: ASS karaoke word-level ----------

def collect_words(segments: list[dict], pezzi: list[dict]) -> list[dict]:
    """Le parole che restano dentro la clip, coi tempi GIA' in secondi di clip.

    Prima dei tagli questa funzione prendeva (segments, start, end) e tornava
    le parole coi tempi del GIRATO, che build_ass ribasava con clip_start.
    Adesso prende i PEZZI e ribasa qui, perche' con piu' di un pezzo la
    sottrazione di un solo numero non basta piu': fra un pezzo e l'altro c'e'
    un buco, e ogni parola dopo di lui sta a un secondo diverso.

    Con un pezzo solo il risultato e' identico a prima, bit per bit: la
    ribasatura vale w["start"] - inizio, la stessa sottrazione che faceva
    build_ass, e le parole a cavallo dei bordi ESTERNI non vengono strette
    (vedi tagli.pezzi_da_buchi). Chi chiama passa quindi clip_start = 0.

    La fusione delle parole troppo brevi (MIN_WORD_MS) resta, con l'unico
    vincolo nuovo: non si fondono due parole che stanno ai due lati di un
    taglio.
    """
    parole = tagli.ribasa_parole(tagli.numera_parole(segments), pezzi)
    return tagli.unisci_brevi(parole, config.MIN_WORD_MS)


def paginate(words: list[dict], clip_start: float = 0.0) -> list[list[dict]]:
    pages: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        chars = sum(len(x["w"]) + 1 for x in cur)
        gap = cur and (w["start"] - cur[-1]["end"] > config.PAGE_GAP_S)
        # Un TAGLIO chiude la pagina anche quando i due tempi si toccano: dopo
        # il buco il discorso riparte, e tenere le due meta' sulla stessa
        # pagina scriverebbe sullo schermo una frase che nel video non c'e'.
        # Senza buchi 'pezzo' vale 0 per tutte e questa riga non fa niente.
        cambio_pezzo = cur and cur[-1].get("pezzo") != w.get("pezzo")
        # la pagina è decisa dalla prima parola che ci sta dentro, non da questa:
        # così una pagina aperta dentro i 10s non cambia regola a metà
        dentro_hook = (cur[0]["start"] if cur else w["start"]) - clip_start < config.HOOK_FINO_A_S
        max_parole = config.MAX_WORDS_PER_PAGE_HOOK if dentro_hook else config.MAX_WORDS_PER_PAGE
        if cur and (len(cur) >= max_parole or chars + len(w["w"]) > config.MAX_CHARS_PER_PAGE
                    or gap or cambio_pezzo):
            pages.append(cur)
            cur = []
        cur.append(w)
    if cur:
        pages.append(cur)
    return pages


def ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def esc_ass(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def _intestazione_ass(family: str) -> str:
    """L'intestazione dello stile, una sola per tutte le strade.

    Era in mezzo a build_ass: e' stata staccata perche' la strada del karaoke
    deve usare LA STESSA, carattere per carattere. Due intestazioni gemelle
    scritte in due posti sono il modo in cui un giorno il corpo cambia da una
    parte sola e nessuno se ne accorge finche' non lo vede a video.
    """
    # I due margini laterali NON sono un numero a mano: discendono dal rapporto
    # massimo di larghezza del testo (fondamenta, voce 3), lo stesso numero che
    # deve valere nel predicato di spezzatura. Scriverli a mano qui e paginare
    # con un'altra regola e' esattamente il disallineamento che fa uscire i
    # sottotitoli dallo schermo.
    margine = config.MARGINE_TESTO_PX
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {config.OUT_W}
PlayResY: {config.OUT_H}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,{family},{config.FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,5,0,5,{margine},{margine},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


# Il bianco della voce PrimaryColour dello stile qui sopra, in RGB. E' il
# colore da cui parte ogni interpolazione del karaoke: se un giorno lo stile
# cambia, questo cambia con lui o le parole spente escono di un altro bianco.
BASE_KARAOKE = (255, 255, 255)


def build_ass_karaoke(words: list[dict], clip_start: float, family: str) -> str:
    """I sottotitoli con il karaoke: UNA riga Dialogue per pagina.

    La strada storica ne emette una per PAROLA, ognuna con l'intera pagina
    riscritta e una parola ingrandita. Funziona, ma ha due difetti che si
    vedono: il file cresce col quadrato delle parole, e ingrandire una parola
    cambia la larghezza della riga, quindi a ogni parola tutte le altre si
    spostano di qualche pixel. Qui la riga e' una sola e le parole si accendono
    dentro, con i tag `\\t` di ASS: niente riflusso, niente tremolio.

    I tre passi stanno in karaoke.py e si usano nell'ordine:
      1) le pagine diventano i PEZZI di testo e si allineano ai tempi di
         parola sul conteggio dei caratteri alfanumerici;
      2) le campate si agganciano al blocco, in fotogrammi relativi;
      3) gli stati per parola diventano tag ASS.

    La riga Dialogue comincia e finisce dove cominciava e finiva prima: il
    karaoke cambia che cosa c'e' DENTRO la riga, non quando le righe appaiono.
    """
    pagine = paginate(words, clip_start)
    if not pagine:
        return _intestazione_ass(family) + "\n"

    maiuscolo = config.UPPERCASE
    testi_pagina = []
    parole_visibili = []
    for pagina in pagine:
        testo, visibili = karaoke.pagina_a_blocco(pagina, maiuscolo)
        testi_pagina.append(testo)
        parole_visibili.append(visibili)

    # Passo 1. Le parole in ingresso sono TUTTE quelle della clip, in ordine:
    # e' l'allineamento a decidere quante ne tocca a ogni pagina, non la
    # paginazione a dettarlo. Con il testo non riscritto le due cose
    # coincidono; con un testo corretto a mano (fix_transcript) no, ed e'
    # esattamente li' che serve.
    parole_rel = [{"w": w["w"], "start": w["start"] - clip_start,
                   "end": w["end"] - clip_start} for w in words]
    blocchi = karaoke.allinea(
        testi_pagina, parole_rel,
        pagine[0][0]["start"] - clip_start, pagine[-1][-1]["end"] - clip_start)

    tinta = (karaoke.rgb_da_hex(config.KARAOKE_COLORE)
             if config.KARAOKE_COLORE else karaoke.rgb_da_ass(config.ROSSO_ASS))
    fps = karaoke.FPS_NOMINALE
    righe = []
    prev_end = 0.0
    for pi, pagina in enumerate(pagine):
        t_start = max(pagina[0]["start"] - clip_start, prev_end)
        t_end = pagina[-1]["end"] - clip_start + 0.15
        if pi + 1 < len(pagine):   # la coda non deve invadere la pagina dopo
            t_end = min(t_end, pagine[pi + 1][0]["start"] - clip_start)
        if t_end <= t_start:
            t_end = t_start + 0.05
        prev_end = t_end

        # Passo 2. La finestra e' la riga stessa: cosi' le campate escono in
        # fotogrammi relativi all'inizio del Dialogue, che e' l'origine dei
        # tempi dei tag `\t`.
        f0 = fondamenta.fotogramma(t_start, fps)
        f1 = max(f0 + 1, fondamenta.fotogramma(t_end, fps))
        finestra = karaoke.Finestra(fps=fps, frame_inizio=f0, frame_fine=f1)
        blocco = blocchi[pi] if pi < len(blocchi) else None
        campate_grezze = blocco.campate if blocco is not None else None
        _, durata, campate = karaoke.campate_nel_blocco(
            karaoke.Blocco(testi_pagina[pi], t_start, t_end, campate_grezze),
            finestra)

        testo = karaoke.testo_dialogue(
            config.KARAOKE_PRESET, parole_visibili[pi], campate, durata,
            config.KARAOKE_FOTOGRAMMI_PER_PAROLA, BASE_KARAOKE, tinta,
            fps=fps, altezza=config.OUT_H,
            posizione=(config.SUB_POS_X, config.SUB_POS_Y))
        if not testo:
            continue
        righe.append(
            f"Dialogue: 0,{ass_time(t_start)},{ass_time(t_end)},Word,,0,0,0,,{testo}")
    return _intestazione_ass(family) + "\n".join(righe) + "\n"


def build_ass(words: list[dict], clip_start: float, family: str) -> str:
    # Il bivio: col karaoke spento — cioe' senza il blocco 'karaoke' nel brand
    # kit, che e' il caso della produzione di oggi — non si entra nemmeno nel
    # codice nuovo e il file esce identico byte per byte a quello di sempre.
    # E' la condizione perche' la prova di regressione resti verde.
    if getattr(config, "KARAOKE_PRESET", "off") != "off":
        return build_ass_karaoke(words, clip_start, family)
    # L'intestazione e' quella di sempre, spostata in _intestazione_ass e
    # riusata da tutte e due le strade: la stringa prodotta e' identica
    # carattere per carattere, quindi il file non cambia di un byte.
    header = _intestazione_ass(family)
    lines = []
    pages = paginate(words, clip_start)
    prev_end = 0.0
    for pi, page in enumerate(pages):
        page_end = page[-1]["end"] - clip_start + 0.15
        if pi + 1 < len(pages):  # la coda non deve invadere la pagina successiva
            page_end = min(page_end, pages[pi + 1][0]["start"] - clip_start)
        for wi, w in enumerate(page):
            t_start = max(w["start"] - clip_start, prev_end)  # mai sovrapporre dialogue
            t_end = (page[wi + 1]["start"] - clip_start) if wi + 1 < len(page) else page_end
            if t_end <= t_start:
                t_end = t_start + 0.05
            prev_end = t_end
            parts = []
            for wj, other in enumerate(page):
                txt = esc_ass(other["w"].upper() if config.UPPERCASE else other["w"])
                if wj == wi:
                    parts.append(
                        f"{{\\c{config.ROSSO_ASS}\\t(0,80,\\fscx108\\fscy108)}}{txt}{{\\r}}"
                    )
                else:
                    parts.append(txt)
            text = " ".join(parts)
            lines.append(
                f"Dialogue: 0,{ass_time(t_start)},{ass_time(t_end)},Word,,0,0,0,,"
                f"{{\\pos({config.SUB_POS_X},{config.SUB_POS_Y})}}{text}"
            )
    return header + "\n".join(lines) + "\n"


# ---------- ffmpeg ----------

def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg fallito:\n{' '.join(cmd)}\n{r.stderr[-2000:]}")


def probe_size(video: Path) -> tuple[int, int]:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    )
    w, h = r.stdout.strip().split(",")[:2]
    return int(w), int(h)


#: Quanto puo' scostarsi la frequenza del girato da quella del kit prima che
#: valga la pena riscriverla. Mezzo fotogramma copre 29,97 contro 30 — che
#: nessuno vede — e lascia fuori 24 contro 30, che si vede eccome.
TOLLERANZA_FPS = 0.5


def probe_fps(video: Path) -> float | None:
    """I fotogrammi al secondo del sorgente. None se non si leggono.

    ffprobe li da' come frazione ('30/1', '30000/1001'): e' cosi' che si
    rappresenta 29,97 senza perdere un decimale per strada.
    """
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    )
    grezzo = r.stdout.strip()
    if "/" not in grezzo:
        return None
    sopra, sotto = grezzo.split("/", 1)
    try:
        numeratore, denominatore = float(sopra), float(sotto)
    except ValueError:
        return None
    return numeratore / denominatore if denominatore > 0 and numeratore > 0 else None


#: Quanto puo' scostarsi la durata misurata da quella pianificata prima che
#: valga la pena dirlo. Tre fotogrammi a 30 al secondo: sotto e' il normale
#: assestamento dei bordi dei GOP, sopra e' ffmpeg che ha fatto qualcosa di
#: diverso da quello che gli era stato chiesto.
SCARTO_DURATA_S = 0.1


def probe_durata(video: Path) -> float | None:
    """La durata VERA del file, letta dal file. None se non si legge."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    )
    grezzo = r.stdout.strip()
    try:
        valore = float(grezzo)
    except ValueError:
        return None
    return valore if valore > 0 else None


def argomenti_frequenza(fps_sorgente: float | None, fps_kit: int) -> list[str]:
    """`-r` SOLO quando serve davvero, e questo e' il punto.

    Senza `-r` l'uscita eredita la frequenza del girato: un girato in modalita'
    cinema produce uno short a 23,976, che e' una frequenza frazionaria — alcune
    piattaforme la rifiutano, altre la riproducono a scatti, e non lo dice
    nessuno: lo si scopre guardando il video dopo averlo pubblicato.

    Ma passarlo SEMPRE cambia i video che oggi vanno bene. MISURATO il
    21/08/2026 sul girato di collaudo-p3, gia' a 30 esatti: con `-r 30`
    l'uscita passa da 1561 a 1562 fotogrammi e da 52,033 a 52,067 s. Le
    immagini restano identiche — PSNR infinito su tutti e tre i canali — ma un
    fotogramma in piu' e' comunque un file diverso, e cambiare i byte di
    diciannove short gia' prodotti per un difetto che oggi non morde e' un
    prezzo che non vale la pena pagare.

    Quindi: si riscrive la frequenza solo quando quella del girato e'
    davvero un'altra. Sui sei girati veri di oggi, tutti a 30/1, questa
    funzione torna una lista vuota e non cambia niente.
    """
    if fps_sorgente is None:
        return []
    return [] if abs(fps_sorgente - fps_kit) <= TOLLERANZA_FPS else ["-r", str(fps_kit)]


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:40] or "short"


def comando_pezzi(video: Path, pezzi: list[dict], uscita: Path) -> list[str]:
    """Il comando che ritaglia i pezzi e li riattacca in un file solo.

    Con UN pezzo si resta sulla strada di sempre — `-ss` prima dell'ingresso,
    `-t` per la durata — che e' quella provata da anni e la piu' veloce: una
    clip senza buchi deve uscire identica a prima.

    Con PIU' pezzi non basta piu': `-ss/-t` sanno tagliare una finestra sola.
    Si passa a un filter_complex che per ogni pezzo prende video e audio con
    trim/atrim, li riporta a partire da zero con setpts/asetpts e poi li
    concatena. Un solo passaggio, una sola codifica: niente file intermedi da
    riattaccare e nessuna deriva fra le due tracce.

    Il `-ss` resta davanti all'ingresso anche qui, ma posizionato un po' prima
    del primo pezzo (MARGINE_SEEK_S): senza, ffmpeg decodificherebbe il girato
    dall'inizio per arrivare al minuto 30. I tempi del trim sono quindi
    RELATIVI a quel punto — con il salto accurato (predefinito) l'ingresso
    riparte esattamente da li' con i tempi azzerati.
    """
    if len(pezzi) == 1:
        pezzo = pezzi[0]
        return [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{pezzo['inizio']:.3f}", "-i", str(video),
            "-t", f"{pezzo['fine'] - pezzo['inizio']:.3f}",
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-avoid_negative_ts", "make_zero",
            str(uscita),
        ]

    base = max(0.0, pezzi[0]["inizio"] - MARGINE_SEEK_S)
    catene = []
    etichette = []
    for n, pezzo in enumerate(pezzi):
        da = pezzo["inizio"] - base
        a = pezzo["fine"] - base
        catene.append(f"[0:v]trim=start={da:.3f}:end={a:.3f},setpts=PTS-STARTPTS[v{n}]")
        catene.append(f"[0:a]atrim=start={da:.3f}:end={a:.3f},asetpts=PTS-STARTPTS[a{n}]")
        etichette.append(f"[v{n}][a{n}]")
    catene.append(f"{''.join(etichette)}concat=n={len(pezzi)}:v=1:a=1[v][a]")
    return [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{base:.3f}", "-i", str(video),
        "-filter_complex", ";".join(catene),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-avoid_negative_ts", "make_zero",
        str(uscita),
    ]


def risolvi_taglio(video: Path, voce: dict, parole: list[dict],
                   inizio: float, fine: float, nome: str) -> dict:
    """Da una voce di tagli.json ai BUCHI davvero applicabili a questa clip.

    Tre passaggi, in quest'ordine, e l'ordine conta:

      1. LA FIRMA. Se il girato e' stato ritrascritto dopo che i buchi sono
         stati calcolati, gli indici di parola di quel taglio non indicano piu'
         quelle parole. Non si taglia a indovinare: si FERMA il passo.
      2. IL LIVELLO. I buchi nati da una pausa sono CANDIDATI proposti da chi
         vedeva solo il trascritto. Qui c'e' l'audio: si misura, e quelli sotto
         cui c'e' musica o ambiente restano dov'erano (silenzi.py).
      3. LA DURATA MINIMA. Sotto config.MIN_CLIP_S il montaggio scarta la clip:
         si applicano i buchi finche' si sta sopra, e si dice quali sono
         rimasti fuori.

    Torna il blocco che finisce nel metadata: buchi applicati, vetati,
    lasciati, avvisi, soglia e misura. Nessun campo sparisce mai — «non lo so»
    e «zero» non devono avere la stessa faccia.
    """
    buchi = list(voce.get("buchi") or [])
    esito = {
        "buchi": [], "vetati": [], "lasciati": [], "avvisi": [],
        # Le pause vetate dal RILEVATORE DI PARLATO stanno in un elenco loro,
        # separato da quelle vetate dal livello. Fonderle sarebbe comodo e
        # sbagliato: a valle la parola «vetati» significa «sotto c'era musica
        # o ambiente», ed e' scritta cosi' in quattro posti (worker/motore.js,
        # ritorno.ts, clip.js, api.ts) piu' i campi livello_db/soglia_db che i
        # record del rilevatore non hanno. Al cliente verrebbe detto che una
        # pausa e' rimasta per la musica, quando invece e' rimasta perche' li'
        # dentro si parlava — cioe' gli si toglie l'unica cosa che gli dice
        # come rimediare.
        "vetati_rilevatore": [],
        # Il campo c'e' SEMPRE, anche sulle strade che escono prima: la regola
        # e' che nessun campo dell'esito sparisca, o chi legge non sa se il
        # controllo non ha trovato niente o non e' proprio girato.
        "rilevatore": None,
        "soglia": None,
        "durata_prima_s": fondamenta.arrotonda_decimale(fine - inizio),
        "durata_dopo_s": fondamenta.arrotonda_decimale(fine - inizio),
        "tolti_s": 0.0, "quante_pause": 0,
    }
    if not buchi:
        return esito

    # 1) la firma della numerazione
    attesa = voce.get("firma_trascritto")
    if attesa:
        adesso = tagli.firma_numerazione(parole)
        if adesso != attesa:
            raise tagli.TaglioNonValido(
                f"tagli: '{nome}' e' stato calcolato su una numerazione delle parole "
                f"diversa da quella di adesso (firma {attesa} contro {adesso}): il "
                "girato e' stato ritrascritto e gli indici di quel taglio non "
                "indicano piu' quelle parole. Rifai il taglio leggendo il montaggio "
                "aggiornato.")

    # 2) il livello audio, solo se c'e' almeno un buco da verificare
    if any(b.get("verifica_livello", True) for b in buchi):
        celle = silenzi.misura_livelli(video, inizio, fine)
        soglia = silenzi.soglia_relativa(celle, silenzi.parole_nella_finestra(parole, inizio, fine))
        esito["soglia"] = soglia
        buchi, vetati = silenzi.veta_per_livello(buchi, celle, soglia)
        esito["vetati"] = vetati

    # 2-bis) il rilevatore di parlato, sui buchi rimasti.
    #
    # Sta DOPO il livello e non prima: il livello costa una passata ffmpeg che
    # si fa comunque, il rilevatore costa una seconda decodifica piu'
    # l'inferenza, quindi conviene che lavori solo su quello che e'
    # sopravvissuto. E' SPENTO di fabbrica: senza MOTORE_RILEVATORE_PARLATO
    # torna i buchi intatti senza caricare niente e senza lanciare ffmpeg.
    #
    # Puo' solo TOGLIERE tagli, mai aggiungerne: quando trova parlato dentro
    # una pausa, quella pausa resta dov'e'. Gli short diventano semmai piu'
    # lunghi, mai piu' corti — che e' l'invariante gia' promessa al cliente in
    # api/src/tagli.js, dove 'tolti_s' e' dichiarato un MASSIMO.
    buchi, vetati_rilevatore, esito["rilevatore"] = silenzi.verifica_col_rilevatore(
        video, inizio, fine, buchi)
    esito["vetati_rilevatore"] = vetati_rilevatore

    # 3) la durata minima
    buchi, lasciati, avvisi = tagli.entro_durata_minima(
        buchi, inizio, fine, config.MIN_CLIP_S)
    esito["lasciati"] = lasciati
    esito["avvisi"] = avvisi
    esito["buchi"] = buchi
    return esito


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--highlights", default=str(config.BUILD_DIR / "highlights.json"))
    ap.add_argument("--no-subs", action="store_true")
    ap.add_argument("--correzioni",
                    help="build/correzioni.json: ritaglio e taglio corretti per "
                         "singola clip (formato in correzioni.py). Assente = "
                         "nessuna correzione, stesso video di prima.")
    ap.add_argument("--tagli",
                    help="build/tagli.json: i BUCHI tolti da dentro una clip — "
                         "pause e parole (formato in tagli.py). Assente = "
                         "nessun taglio, stesso video di prima.")
    ap.add_argument("--solo-clip",
                    help="rifa' SOLO questa clip (nome base, es. 'short_02_...'), "
                         "lasciando le altre dove sono")
    args = ap.parse_args()

    video = Path(args.video).resolve()
    transcript_path = config.BUILD_DIR / f"{video.stem}.transcript.json"
    data = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments, duration = data["segments"], data["duration"]
    hl_raw = json.loads(Path(args.highlights).read_text(encoding="utf-8"))["highlights"]

    family_txt = config.FONTS_DIR / "family.txt"
    family = family_txt.read_text(encoding="utf-8").strip() if family_txt.exists() else os.environ.get("FONT_FAMILY", "Arial")

    # Correzioni per clip (facoltative). Si leggono PRIMA di lavorare: un file
    # scritto male deve fermare il passo qui, non a meta' render.
    try:
        correzioni_clip = correzioni.leggi(args.correzioni) if args.correzioni else {}
    except correzioni.CorrezioneNonValida as errore:
        print(f"ERRORE: {errore}", file=sys.stderr)
        return 1
    # Tagli dentro la clip (facoltativi). Stessa disciplina: un file scritto
    # male ferma il passo qui, prima di toccare un fotogramma.
    try:
        tagli_clip = tagli.leggi(args.tagli) if args.tagli else {}
    except tagli.TaglioNonValido as errore:
        print(f"ERRORE: {errore}", file=sys.stderr)
        return 1
    # Le parole numerate una volta sola, con l'indice GLOBALE: e' la fonte
    # degli indici con cui i tagli nominano le parole, e la stessa da cui si
    # ricalcola la firma per accorgersi di una ritrascrizione.
    parole_girato = tagli.numera_parole(segments)
    solo = correzioni.normalizza_nome(args.solo_clip) if args.solo_clip else None

    config.OUT_DIR.mkdir(exist_ok=True)
    src_w, src_h = probe_size(video)
    # Il rettangolo da ritagliare perche' lo scaling NON deformi. Prima era
    # `min(CROP_W, src_w)` con SEMPRE tutta l'altezza: su un sorgente piu'
    # stretto di 9:16 il rettangolo usciva col rapporto sbagliato e lo scale
    # lo stirava (una registrazione schermo iPhone 1170x2532 ne usciva
    # deformata). Sui girati veri di oggi il risultato e' identico a prima:
    # 1920x1080 -> 608x1080, 478x850 -> 478x850.
    # La frequenza del girato: serve a decidere se riscriverla in uscita.
    # Si legge una volta sola, qui, invece che a ogni clip.
    fps_sorgente = probe_fps(video)
    crop_w, crop_h = fondamenta.rettangolo_di_ritaglio(
        src_w, src_h, config.OUT_W, config.OUT_H)
    # L'ancora verticale: centrata, e conta solo quando il ritaglio NON prende
    # tutta l'altezza (cioe' sui sorgenti stretti). Il centro e' la scelta
    # neutra — orizzontalmente il ritaglio insegue i volti, verticalmente no,
    # e inventare un'euristica non misurata sarebbe peggio che centrare.
    crop_y = fondamenta.lato_pari((src_h - crop_h) / 2) if crop_h < src_h else 0
    crop_y = max(0, min(crop_y, src_h - crop_h))

    print(f"Sorgente {src_w}x{src_h}. {len(hl_raw)} highlights proposti.")
    scarti: list[dict] = []
    highlights = resolve_highlights(hl_raw, segments, duration, scarti)
    print(f"{len(highlights)} highlights dopo resolve+dedupe.\n")
    # I momenti buttati, col motivo, in un file che il worker legge. Va scritto
    # SEMPRE, anche vuoto: un file che compare solo quando c'e' qualcosa da
    # dire obbliga chi legge a distinguere «nessuno scarto» da «questo render
    # e' di prima che il file esistesse», e quelle due cose non si somigliano.
    (config.BUILD_DIR / "scarti.json").write_text(
        json.dumps({"proposti": len(hl_raw), "tenuti": len(highlights),
                    "scartati": scarti}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    if correzioni_clip:
        print(f"Correzioni caricate per {len(correzioni_clip)} clip: "
              f"{', '.join(sorted(correzioni_clip))}\n")
    if tagli_clip:
        print(f"Tagli caricati per {len(tagli_clip)} clip: "
              f"{', '.join(sorted(tagli_clip))}\n")
    if solo:
        print(f"Rifaccio SOLO la clip '{solo}': le altre restano dove sono.\n")

    fatte = 0
    nomi_visti = []
    for n, h in enumerate(highlights, 1):
        slug = slugify(h.get("title", f"short-{n}"))
        name = f"short_{n:02d}_{slug}"
        nomi_visti.append(name)
        if solo is not None and name != solo:
            continue

        # Il taglio corretto. Senza correzione per questa clip non si passa
        # nemmeno da applica_pad: i tempi restano gli stessi oggetti di prima.
        correzione = correzioni_clip.get(name)
        inizio, fine = h["start"], h["end"]
        avvisi = []
        if correzione is not None:
            inizio, fine, avvisi = correzioni.applica_pad(
                h["start"], h["end"],
                correzione["pad_inizio_s"], correzione["pad_fine_s"],
                duration, config.MIN_CLIP_S)

        print(f"[{n}/{len(highlights)}] {h.get('title')} ({inizio:.1f}s-{fine:.1f}s)")
        if correzione is not None:
            # si dice per esteso COME sono stati letti i numeri: sono
            # scostamenti su quello che il montaggio aveva gia' deciso, non
            # posizioni assolute (vedi correzioni.py)
            print(f"    correzione, letta come SCOSTAMENTO: ancora_x "
                  f"{correzione['ancora_x']:+g} della larghezza, "
                  f"pad inizio {correzione['pad_inizio_s']:+g}s, "
                  f"pad fine {correzione['pad_fine_s']:+g}s "
                  f"(taglio di prima: {h['start']:.1f}s-{h['end']:.1f}s)")

        # I BUCHI dentro la clip. Si risolvono DOPO i pad — cioe' contro il
        # taglio vero, quello che finira' nel video — e prima di toccare
        # ffmpeg: la firma del trascritto e la durata minima devono fermare il
        # passo qui, non a meta' render.
        voce_taglio = tagli_clip.get(name)
        blocco_taglio = None
        pezzi = tagli.pezzi_da_buchi(inizio, fine, [])
        if voce_taglio is not None:
            blocco_taglio = risolvi_taglio(
                video, voce_taglio, parole_girato, inizio, fine, name)
            pezzi = tagli.pezzi_da_buchi(inizio, fine, blocco_taglio["buchi"])
            if not pezzi:
                raise RuntimeError(
                    f"tagli: '{name}' resterebbe senza nemmeno un pezzo di video: "
                    "i buchi coprono tutta la clip")
            durata_dopo = tagli.durata_pezzi(pezzi)
            blocco_taglio["durata_dopo_s"] = fondamenta.arrotonda_decimale(durata_dopo)
            blocco_taglio["tolti_s"] = fondamenta.arrotonda_decimale(
                (fine - inizio) - durata_dopo)
            blocco_taglio["quante_pause"] = len(blocco_taglio["buchi"])
            print(f"    taglio: {blocco_taglio['quante_pause']} buco/hi, "
                  f"-{blocco_taglio['tolti_s']:.2f}s "
                  f"({blocco_taglio['durata_prima_s']:.2f}s -> {durata_dopo:.2f}s)")
            if blocco_taglio["soglia"]:
                s = blocco_taglio["soglia"]
                print(f"    soglia del silenzio: {s['db']:.1f} dB ({s['tipo']}"
                      + (f", parlato a {s['livello_parlato_db']:.1f} dB"
                         if s["livello_parlato_db"] is not None else "") + ")")
            for vetato in blocco_taglio["vetati"]:
                print(f"    NON tolto {vetato['inizio']:.2f}-{vetato['fine']:.2f}s: "
                      f"{vetato['motivo_veto']}")
            for a in blocco_taglio["avvisi"]:
                print(f"    {correzioni.testo_avviso(a)}")

        print("    crop...")
        crop_x, dettaglio_crop = compute_crop_x(
            video, inizio, fine, src_w, src_h,
            correzione["ancora_x"] if correzione is not None else 0.0,
            crop_w=crop_w)
        avvisi = avvisi + dettaglio_crop["avvisi"]
        for a in avvisi:
            print(f"    {correzioni.testo_avviso(a)}")

        clip_mp4 = config.BUILD_DIR / f"{name}.mp4"
        run(comando_pezzi(video, pezzi, clip_mp4))

        vf = (f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
              f"scale={config.OUT_W}:{config.OUT_H}:flags=lanczos")
        if not args.no_subs:
            # I sottotitoli seguono il taglio corretto E i buchi: le parole
            # arrivano gia' RIBASATE in secondi della clip (collect_words passa
            # dai pezzi), quindi qui clip_start e' 0. Senza buchi il file .ass
            # e' identico a quello di prima, bit per bit.
            words = collect_words(segments, pezzi)
            ass_path = config.BUILD_DIR / f"{name}.ass"
            ass_path.write_text(build_ass(words, 0.0, family), encoding="utf-8")
            # Preserve the font directory when a job isolates BUILD_DIR elsewhere.
            try:
                font_directory = os.path.relpath(config.FONTS_DIR, config.BUILD_DIR)
            except ValueError:  # different Windows volumes
                font_directory = str(config.FONTS_DIR)
            font_directory = font_directory.replace("\\", "/").replace(":", "\\:").replace("'", "'\\''")
            vf += f",ass={name}.ass:fontsdir='{font_directory}'"

        # NIENTE LINEARIZZAZIONE IMPLICITA (fondamenta, voce 5). `crop`, `scale`
        # senza parametri di trasferimento e `ass` lavorano sui valori come
        # escono dal decodificatore, cioe' in gamma di visualizzazione: e' su
        # quei valori che sono scritte tutte le formule di colore del motore.
        # Basta uno zscale o un colorspace in mezzo perche' ogni potenza, ogni
        # sfocatura e ogni fusione diano un altro risultato — senza errori e
        # senza che si veda dove. Si controlla qui, dopo l'aggiunta dei
        # sottotitoli, cosi' la guardia copre la catena intera che finisce
        # davvero dentro ffmpeg.
        linearizzanti = fondamenta.catena_linearizza(vf)
        if linearizzanti:
            raise RuntimeError(
                f"catena colore: {', '.join(linearizzanti)} linearizza da solo. "
                "Il motore lavora in gamma di visualizzazione (Rec.709), unica "
                "eccezione dichiarata l'esposizione. Se il filtro serve davvero, "
                "aggiorna docs/fondamenta-numeriche.md prima di metterlo.")

        out_mp4 = config.OUT_DIR / f"{name}.mp4"
        print("    render...")
        r = subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", f"{name}.mp4", "-vf", vf,
                "-af", config.LOUDNORM,
                "-c:v", "libx264", "-preset", "medium", "-crf", str(config.CRF),
                *argomenti_frequenza(fps_sorgente, config.OUT_FPS),
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                str(out_mp4),
            ],
            capture_output=True, text=True, cwd=str(config.BUILD_DIR),
        )
        if r.returncode != 0:
            raise RuntimeError(f"render fallito: {r.stderr[-2000:]}")

        meta = {k: h.get(k) for k in ("title", "score", "hook_sentence", "virality_reason")}
        # 'start' e 'end' restano gli estremi ESTERNI del taglio, cioe' la
        # finestra di girato che la clip attraversa: e' con quelli che il
        # worker ritrova l'highlight (giro.js, tempiHighlight) e con quelli che
        # gli scostamenti si sommano. 'duration' invece e' la durata del file
        # prodotto, buchi compresi, perche' e' quella che si legge nel
        # calendario e quella su cui valida_canone giudica il piano degli
        # overlay.
        # LA DURATA SI MISURA SUL FILE, non si calcola.
        #
        # Fin qui 'duration' era la somma aritmetica dei pezzi tenuti, cioe' la
        # durata CHIESTA al montaggio — e il commento qui sopra la chiamava
        # «la durata VERA del file», che non era. E' il numero che il
        # calendario mostra, che la chat legge al cliente e su cui si decide la
        # programmazione: un valore calcolato presentato come misurato e'
        # l'unica bugia che il sistema diceva.
        #
        # Ora si legge dal file. Se il pianificato e il misurato divergono di
        # piu' di qualche fotogramma, lo si DICE invece di scegliere in
        # silenzio: quella divergenza significa che ffmpeg ha fatto qualcosa di
        # diverso da quello che gli era stato chiesto — un'uscita troncata, per
        # esempio — e oggi nessuno se ne accorgeva.
        durata_pianificata = tagli.durata_pezzi(pezzi)
        durata_misurata = probe_durata(out_mp4)
        if durata_misurata is None:
            print(f"    AVVISO: durata di '{name}' non leggibile dal file, "
                  f"resta quella pianificata ({durata_pianificata:.2f} s)")
        elif abs(durata_misurata - durata_pianificata) > SCARTO_DURATA_S:
            print(f"    AVVISO: '{name}' dura {durata_misurata:.2f} s, ne erano "
                  f"stati chiesti {durata_pianificata:.2f} "
                  f"({durata_misurata - durata_pianificata:+.2f} s): vale quella "
                  "misurata sul file")
        meta.update({"start": inizio, "end": fine,
                     "duration": fondamenta.arrotonda_decimale(
                         durata_pianificata if durata_misurata is None
                         else durata_misurata, 1),
                     # Il numero pianificato resta scritto accanto: serve a
                     # chi indaga uno scarto, e senza non si potrebbe piu'
                     # sapere cosa era stato chiesto.
                     "durata_pianificata_s": fondamenta.arrotonda_decimale(
                         durata_pianificata, 1),
                     "durata_misurata": durata_misurata is not None,
                     "crop_x": crop_x})
        # I PEZZI: i tratti di girato che restano dentro la clip, in ordine.
        # Si scrivono SEMPRE, anche quando sono uno solo, perche' sono il
        # riferimento con cui chi viene dopo converte un tempo — componi_fx per
        # ancorare le grafiche agli indici di parola, l'API per dire a che
        # secondo cade una frase. Un campo che compare solo qualche volta
        # obbliga ogni lettore a tenersi due strade.
        meta["pezzi"] = [{"inizio": fondamenta.arrotonda_decimale(p["inizio"]),
                          "fine": fondamenta.arrotonda_decimale(p["fine"])}
                         for p in pezzi]
        # Il blocco 'tagli' esiste SOLO se questa clip e' stata tagliata, come
        # 'correzioni': senza tagli il metadata resta quello di sempre piu' i
        # pezzi. Dentro c'e' la MISURA — quanto e' stato tolto, quante pause,
        # durata prima e dopo — ed e' quella che il worker trasforma in un
        # evento leggibile e la chat legge al cliente al posto di «fatto».
        if blocco_taglio is not None:
            meta["tagli"] = blocco_taglio
        # Il blocco 'correzioni' esiste SOLO se questa clip e' stata corretta:
        # senza correzioni il metadata resta identico a quello di sempre.
        # 'start_base'/'end_base' sono il taglio calcolato dagli indici di
        # segmento, ed e' quello con cui il worker ritrova quale highlight ha
        # prodotto quale mp4 (giro.js, tempiHighlight): senza, una clip
        # allungata non combacerebbe piu' con nessun highlight.
        if correzione is not None:
            meta["correzioni"] = {
                "chieste": dict(correzione),
                "start_base": h["start"],
                "end_base": h["end"],
                "crop_x_senza_correzione": dettaglio_crop["crop_x_senza_correzione"],
                "spostamento_px": dettaglio_crop["spostamento_px"],
                "avvisi": avvisi,
            }
        (config.OUT_DIR / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"    OK -> out/{out_mp4.name}")
        fatte += 1

    # Una clip chiesta per nome e mai trovata e' un errore, non un giro a
    # vuoto: senza questo controllo il worker caricherebbe in archivio il file
    # vecchio credendo di aver rifatto qualcosa.
    if solo is not None and fatte == 0:
        print(f"ERRORE: la clip '{solo}' non esiste in questo giro. "
              f"Ci sono: {', '.join(nomi_visti) or 'nessuna clip'}", file=sys.stderr)
        return 1

    # Correzioni scritte per clip che non esistono (nome sbagliato, oppure
    # highlight scartato o deduplicato dopo): non fanno fallire il giro, ma
    # non spariscono in silenzio — chi le ha scritte crede di aver corretto.
    orfane = sorted(set(correzioni_clip) - set(nomi_visti))
    if orfane:
        print(f"AVVISO: correzioni per clip che non esistono, ignorate: "
              f"{', '.join(orfane)}. Le clip di questo giro sono: "
              f"{', '.join(nomi_visti)}", file=sys.stderr)

    print("\nFatto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
