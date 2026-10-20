"""Configurazione pipeline shorts — brand Content Machine."""
import _bootstrap  # shared local paths, tools and cache

from pathlib import Path
import os

import fondamenta

ROOT = Path(__file__).parent
FONTS_DIR = Path(os.environ.get("SHORTS_FONTS_DIR", str(ROOT / "fonts"))).resolve()
BUILD_DIR = Path(os.environ.get("SHORTS_BUILD_DIR", str(ROOT / "build"))).resolve()
OUT_DIR = Path(os.environ.get("SHORTS_OUT_DIR", str(ROOT / "out"))).resolve()

# Whisper
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")  # small = veloce; "medium"/"large-v3" = più accurato
WHISPER_LANG = os.environ.get("WHISPER_LANG", "it")
# Glossario nomi/brand: aiuta whisper su termini propri (surrogato hotwords)
INITIAL_PROMPT = os.environ.get("WHISPER_INITIAL_PROMPT", "")

# Clip
MIN_CLIP_S = 12.0
MAX_CLIP_S = 180.0
PAD_START_S = -0.20   # anticipa l'attacco per non troncare la prima parola
PAD_END_S = 0.40      # coda dopo l'ultima parola
DEDUPE_OVERLAP = 0.50  # scarta se overlap > 50% (simmetrico, vince lo score)

# Output
CROP_W, CROP_H = 608, 1080   # 9:16 a piena altezza da 1920x1080 (pari!)

# --- Valori DI BRAND: arrivano dal brand-kit.json accanto alla pipeline ---
# (tappa 5, multi-cliente). Il kit sta un livello sopra questa cartella:
# il kit neutro distribuito e' personalizzabile dal proprietario.
# Kit assente o senza le sezioni
# attese = ERRORE ESPLICITO all'import: la pipeline non deve mai produrre
# il brand sbagliato dicendo che e' andato tutto bene.
import json as _json

_PERCORSO_KIT = ROOT.parent / "brand-kit.json"
if not _PERCORSO_KIT.exists():
    raise RuntimeError(
        f"brand-kit.json assente in {_PERCORSO_KIT}: la pipeline legge i valori "
        "di brand dal kit (tappa 5) e senza kit non parte. Nessun default.")
_KIT = _json.loads(_PERCORSO_KIT.read_text(encoding="utf-8"))
try:
    _S = _KIT["sottotitoli_short"]
    _F = _KIT["formati"]["short"]
    _A = _KIT["audio"]
    OUT_W, OUT_H = int(_F["larghezza"]), int(_F["altezza"])
    # I FOTOGRAMMI AL SECONDO DELL'USCITA, dal kit come le misure.
    #
    # Fin qui il kit li dichiarava e il render non li guardava: senza -r
    # l'uscita ereditava la frequenza del girato, qualunque fosse. Un girato
    # in modalita' cinema esce a 23,976, cioe' a una frequenza frazionaria che
    # alcune piattaforme rifiutano e altre riproducono a scatti — e non lo dice
    # nessuno, lo si scopre guardando il video dopo averlo pubblicato.
    #
    # Sui sei girati veri misurati il 21/08/2026 sono tutti 30/1 esatti,
    # quindi imporre 30 non cambia un fotogramma di quello che esce oggi.
    # Serve al girato che arrivera' domani.
    OUT_FPS = int(_F["fps"])
    ROSSO_ASS = _KIT["colori"]["_rosso_altri_formati"]["ass_libass_bgr"]
    # --- il corpo dei sottotitoli passa dal FATTORE DEL TESTO ---
    # c = altezza_render / 1080 e' l'unico moltiplicatore tipografico del
    # motore (docs/fondamenta-numeriche.md, voce 2). Il kit puo' dichiarare il
    # corpo in due modi: 'corpo_pt' in punti di un canvas alto 1080 — la forma
    # giusta, che sopravvive al cambio di formato — oppure 'corpo' in pixel del
    # render, che e' la forma storica. Nel secondo caso i punti si ricavano
    # dividendo per c, cosi' il numero applicato resta identico a quello di
    # sempre su 1080x1920 e diventa proporzionato su ogni altra altezza.
    FATTORE_TESTO = fondamenta.fattore_testo(OUT_H)
    if _S.get("corpo_pt") is not None:
        CORPO_PT = float(_S["corpo_pt"])
    else:
        CORPO_PT = float(_S["corpo"]) / FATTORE_TESTO
    FONT_SIZE = fondamenta.corpo_px(CORPO_PT, OUT_H)
    # --- il riquadro del testo passa dal RAPPORTO MASSIMO DI LARGHEZZA ---
    # Stesso numero del predicato di spezzatura (voce 3). Vive in fondamenta,
    # non qui: due copie sono il modo in cui i due lati si disallineano.
    LARGHEZZA_TESTO_PX = fondamenta.larghezza_max_testo_px(OUT_W)
    MARGINE_TESTO_PX = fondamenta.margine_testo_px(OUT_W)
    SUB_POS_X, SUB_POS_Y = int(_S["posizione"]["x"]), int(_S["posizione"]["y"])
    MAX_WORDS_PER_PAGE = int(_S["parole_per_pagina"])
    # Nei primi secondi tutto deve correre: pagine strette, poi si allarga.
    # Valore configurabile nel kit, senza promessa di risultati editoriali.
    MAX_WORDS_PER_PAGE_HOOK = int(_S["parole_per_pagina_primi_10s"])
    MAX_CHARS_PER_PAGE = int(_S["caratteri_per_pagina"])
    # LRA resta una costante della pipeline: il kit fissa loudness e true
    # peak (quelli controllati da sincronizza_brand --verifica)
    LOUDNORM = (f"loudnorm=I={_A['loudness_lufs']}"
                f":TP={_A['true_peak_dbtp']}:LRA=11")
    # --- il KARAOKE: acceso dal kit, spento se il kit non ne parla ---
    # Il blocco 'karaoke' e' FACOLTATIVO apposta. Assente, o con preset "off",
    # i sottotitoli restano quelli di sempre: una riga Dialogue per parola con
    # la parola attiva in rosso e il micro-pop. E' la strada su cui gira la
    # produzione e su cui la prova di regressione confronta i byte, quindi il
    # ripiego non e' pigrizia: e' la garanzia che accendere una funzione nuova
    # sia una DECISIONE, mai un effetto collaterale di un aggiornamento.
    _K = _S.get("karaoke") or {}
    KARAOKE_PRESET = str(_K.get("preset", "off"))
    KARAOKE_FOTOGRAMMI_PER_PAROLA = int(_K.get("fotogrammi_per_parola", 6))
    # Il colore dell'evidenziazione: se il kit non lo dice si usa il rosso di
    # brand, che e' gia' quello della parola attiva di oggi. Un secondo posto
    # dove scrivere il rosso e' il modo in cui i due si disallineano.
    KARAOKE_COLORE = _K.get("colore_evidenziazione")
except KeyError as _errore:
    raise RuntimeError(
        f"brand-kit.json incompleto ({_PERCORSO_KIT}): manca {_errore} — "
        "la pipeline non ripiega su valori di default.") from _errore
# --- fine valori di brand ---

CRF = 18
HOOK_FINO_A_S = 10.0
PAGE_GAP_S = 0.5             # gap tra parole che forza nuova pagina
MIN_WORD_MS = 60             # parole più corte si fondono con la successiva
UPPERCASE = True             # coerenza brand (display uppercase)
