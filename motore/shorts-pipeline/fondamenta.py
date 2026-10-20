"""Le costanti di fondazione, in un posto solo.

Non c'e' un algoritmo qui dentro. Ci sono cinque decisioni che tutto il resto
del motore da' per buone, e le poche funzioni che le rendono impossibili da
applicare a meta'. Il documento che le motiva e' docs/fondamenta-numeriche.md:
qui sotto ogni voce ha il numero e il rimando, il perche' sta li'.

La regola che tiene insieme tutto: una costante di fondazione si scrive UNA
volta e si importa. Un secondo posto che ne tiene una copia e' il modo in cui
questi numeri si disallineano — e si disallineano in silenzio, senza errori,
cambiando i video prodotti.

    1. la cella audio          512 campioni a 16 kHz = 0,032 s esatti
    2. il fattore del testo    c = altezza_render / 1080
    3. la larghezza del testo  rapporto massimo 0,88, mai 1,0
    4. il tempo                fotogrammi interi, arrotondamento meta' lontano
                               da zero, mai troncamento
    5. il colore               nessuna linearizzazione, luma Rec.709
"""
from __future__ import annotations

import _bootstrap  # shared local paths, tools and cache

import math
from decimal import Decimal, ROUND_HALF_UP

# ---------------------------------------------------------------------------
# 1. La cella audio: la griglia condivisa da tutte le maschere
# ---------------------------------------------------------------------------
#
# 512 campioni a 16 kHz sono 0,032 s esatti. E' la risoluzione temporale con
# cui si misura il livello, con cui si decide dov'e' il parlato e con cui si
# convertono i secondi in celle. I due numeri devono restare accoppiati: e'
# `aformat=sample_rates=16000` + `asetnsamples=n=512` a imporlo nel comando
# ffmpeg, e cambiarne uno solo sposta ogni confine di ogni maschera.

CAMPIONI_CELLA = 512
FREQUENZA_ANALISI = 16000
DURATA_CELLA_S = CAMPIONI_CELLA / FREQUENZA_ANALISI  # 0,032


def celle_in(secondi: float) -> int:
    """Quante celle intere copre una durata. Aritmetica intera, non float.

    Il conteggio si fa sui CAMPIONI e non sui secondi apposta: `ceil(M/512)`
    calcolato come `(M + 511) // 512` non ha errore di rappresentazione, mentre
    `ceil(secondi / 0,032)` sbaglia l'ultima cella su durate lunghe.
    """
    campioni = arrotonda(float(secondi) * FREQUENZA_ANALISI)
    if campioni <= 0:
        return 0
    return (campioni + CAMPIONI_CELLA - 1) // CAMPIONI_CELLA


# ---------------------------------------------------------------------------
# 2. Il fattore del testo: c = altezza_render / 1080
# ---------------------------------------------------------------------------
#
# Ogni misura tipografica (corpo, spaziatura, interlinea, contorno, ombra,
# padding dello sfondo) si dichiara in punti di un canvas alto 1080 e si
# moltiplica per c una volta sola. Dipende SOLO dall'altezza: nessuna
# correzione di rapporto d'aspetto. Su un 1080x1920 c vale 1,7778.

ALTEZZA_CANVAS_RIFERIMENTO = 1080


def fattore_testo(altezza_render: float) -> float:
    """c = altezza_render / 1080. L'unico moltiplicatore tipografico."""
    return float(altezza_render) / ALTEZZA_CANVAS_RIFERIMENTO


def corpo_px(corpo_pt: float, altezza_render: float) -> int:
    """Un corpo dichiarato in punti di canvas 1080 -> pixel di questo render."""
    return arrotonda(float(corpo_pt) * fattore_testo(altezza_render))


# ---------------------------------------------------------------------------
# 3. Il rapporto massimo di larghezza del testo
# ---------------------------------------------------------------------------
#
# Non esiste in nessun documento del corpus: e' una scelta nostra, dentro
# l'intervallo che il documento 70 dichiara sensato (0,80-0,92) e con il suo
# divieto esplicito (mai 1,0). Il vincolo vero non e' il valore ma l'UNICITA':
# lo stesso numero deve valere nel predicato che decide dove spezzare le righe
# e nel calcolo del riquadro che le contiene. Se divergono, quello che il
# codice calcola e quello che si vede non coincidono, e i sottotitoli escono
# dallo schermo.

RAPPORTO_MAX_LARGHEZZA_TESTO = 0.88


def larghezza_max_testo_px(larghezza_render: float) -> int:
    """La larghezza utile per il testo, in pixel di questo render."""
    return arrotonda(float(larghezza_render) * RAPPORTO_MAX_LARGHEZZA_TESTO)


def margine_testo_px(larghezza_render: float) -> int:
    """Il margine laterale che discende dal rapporto. Simmetrico."""
    return arrotonda(
        (float(larghezza_render) - larghezza_max_testo_px(larghezza_render)) / 2)


# ---------------------------------------------------------------------------
# 4. Il tempo: fotogrammi interi, una sola conversione, meta' lontano da zero
# ---------------------------------------------------------------------------
#
# La regola di arrotondamento e' DECIMALE e a meta' lontano da zero, non quella
# di fabbrica di Python (`round`, che e' binaria e a meta' pari):
#
#     round(2.675, 2)              -> 2.67   (meta' pari sul valore binario)
#     arrotonda_decimale(2.675, 2) -> 2.68   (meta' lontano da zero, decimale)
#     round(0.5)                   -> 0      (meta' pari)
#     arrotonda(0.5)               -> 1      (meta' lontano da zero)
#
# Il troncamento non si usa MAI su un tempo: e' il difetto che il documento 73
# registra sul loro `secondsToFrame`, dove un valore che dovrebbe cadere su un
# fotogramma esatto cade sul precedente per errore binario.

CIFRE_PAYLOAD = 3  # le cifre con cui i tempi escono nei file che altri leggono


def _decimale(valore: float) -> Decimal:
    """Il valore come lo si legge, non come lo si memorizza.

    `repr` di un float da' la piu' corta stringa decimale che ci ritorna
    identica: e' quella la rappresentazione da arrotondare. Passando dal
    binario si arrotonderebbe 2,675 come 2,67499999999999982, cioe' si
    rifarebbe l'errore che questa funzione esiste per evitare.
    """
    v = float(valore)
    if not math.isfinite(v):
        raise ValueError(f"tempo non finito: {valore!r}")
    return Decimal(repr(v))


def arrotonda(valore: float) -> int:
    """All'intero piu' vicino, meta' lontano da zero. Mai troncamento."""
    return int(_decimale(valore).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def arrotonda_decimale(valore: float, cifre: int = CIFRE_PAYLOAD) -> float:
    """A `cifre` decimali, meta' lontano da zero, sul decimale e non sul binario."""
    passo = Decimal(1).scaleb(-int(cifre))
    return float(_decimale(valore).quantize(passo, rounding=ROUND_HALF_UP))


def fotogramma(secondi: float, fps: float) -> int:
    """secondi -> fotogramma intero. E' l'UNICA conversione al confine.

    Chi la chiama sta attraversando il confine fra il mondo in secondi (i tempi
    di whisper, i comandi del cliente) e il mondo in fotogrammi (il file
    prodotto). Va chiamata una volta sola per valore: convertire, tornare
    indietro e riconvertire e' il modo in cui un taglio si sposta di un
    fotogramma per volta finche' l'ultimo non e' piu' dove era stato chiesto.
    """
    if float(fps) <= 0:
        raise ValueError(f"fps non valida: {fps!r}")
    return arrotonda(float(secondi) * float(fps))


def secondi_di_fotogramma(indice: int, fps: float) -> float:
    """fotogramma intero -> secondi. Esatta: una divisione, nessun arrotondamento."""
    if float(fps) <= 0:
        raise ValueError(f"fps non valida: {fps!r}")
    return int(indice) / float(fps)


def su_fotogramma(secondi: float, fps: float) -> float:
    """Il tempo agganciato al fotogramma piu' vicino, riportato in secondi."""
    return secondi_di_fotogramma(fotogramma(secondi, fps), fps)


# ---------------------------------------------------------------------------
# 5. Il colore: nessuna linearizzazione implicita, luma Rec.709
# ---------------------------------------------------------------------------
#
# Tutto il colore lavora in gamma di visualizzazione (Rec.709 / sRGB), sui
# valori come escono dal decodificatore. Nessun passaggio in luce lineare, con
# una sola eccezione dichiarata: l'esposizione, che si avvolge esplicitamente
# in sRGB->lineare / lineare->sRGB. Il coefficiente di luma e' Rec.709 ovunque,
# applicato ai valori GAMMA-CODIFICATI: e' una luma percettiva approssimata, ed
# e' una scelta, non un errore.
#
# (Le scene 3D in Blender sono un mondo a parte e restano in luce lineare per
# costruzione: la conversione sta nel brand kit, in `colori._lineare_blender`,
# e non entra mai in questa catena.)

LUMA_709 = (0.2126, 0.7152, 0.0722)


def luma(rosso: float, verde: float, blu: float) -> float:
    """Y = 0,2126R + 0,7152G + 0,0722B sui valori gamma-codificati."""
    r, g, b = LUMA_709
    return r * float(rosso) + g * float(verde) + b * float(blu)


# I filtri ffmpeg che linearizzano da soli, o che possono farlo quando ricevono
# i parametri di trasferimento. Non c'e' niente di sbagliato in loro: c'e' che
# ogni potenza, ogni sfocatura e ogni fusione a schermo dell'intero corpus e'
# scritta su valori NON lineari, e uno solo di questi filtri in mezzo alla
# catena cambia il risultato di tutte senza dire niente.
FILTRI_CHE_LINEARIZZANO = ("zscale", "colorspace", "tonemap", "lut3d=interp=tetrahedral:")

# `scale` linearizza solo se gli si passano i parametri di trasferimento.
_PARAMETRI_DI_TRASFERIMENTO = ("in_color_matrix", "out_color_matrix",
                               "in_trc", "out_trc", "in_primaries", "out_primaries")


def catena_linearizza(catena: str) -> list[str]:
    """I punti di una catena di filtri ffmpeg che linearizzano. Vuota = a posto.

    Serve come guardia, non come divieto: se un giorno serve davvero uno di
    questi filtri, lo si mette e si aggiorna docs/fondamenta-numeriche.md
    dicendo che da quel punto in poi il colore e' lineare. Quello che non deve
    succedere e' che ci finisca senza che nessuno se ne accorga.
    """
    testo = str(catena)
    trovati = [nome for nome in FILTRI_CHE_LINEARIZZANO if nome in testo]
    trovati += [nome for nome in _PARAMETRI_DI_TRASFERIMENTO if nome in testo]
    return trovati


# ---------------------------------------------------------------- ritaglio 9:16

def lato_pari(valore: float) -> int:
    """Il lato piu' vicino, pari e almeno 2.

    I codec 4:2:0 sottocampionano il colore a meta' risoluzione su tutti e due
    gli assi: un lato dispari non e' rappresentabile e libx264 rifiuta di
    partire («width not divisible by 2»). Meglio saperlo qui che scoprirlo a
    render avviato.
    """
    return max(2, int(arrotonda(valore / 2)) * 2)


def _pari_per_difetto(valore: float) -> int:
    """Il piu' grande pari che NON supera il valore.

    Serve come TETTO, dove `lato_pari` non basta: quello arrotonda al piu'
    vicino e su un sorgente da 607 px restituisce 608, cioe' un ritaglio piu'
    largo del video. ffmpeg si ferma con «Invalid too big or non positive size
    for width», e il giro muore a render avviato.
    """
    return max(2, (int(valore) // 2) * 2)


def rettangolo_di_ritaglio(src_w: int, src_h: int,
                           out_w: int, out_h: int) -> tuple[int, int]:
    """Il rettangolo da ritagliare perche' lo scaling NON deformi.

    IL DIFETTO CHE QUESTA FUNZIONE CHIUDE, misurato il 18/08/2026.
    Prima il ritaglio prendeva `min(CROP_W, src_w)` di larghezza e SEMPRE
    tutta l'altezza del sorgente. Finche' il sorgente e' largo, funziona. Su
    un sorgente piu' STRETTO di 9:16 no: il rettangolo esce con un rapporto
    diverso da quello d'uscita, e lo scale successivo lo stira. Una
    registrazione dello schermo di un iPhone (1170x2532) ne usciva deformata.

    LA REGOLA, ed e' sul RAPPORTO, mai sull'altezza. Il rettangolo deve avere
    lo stesso rapporto dell'uscita:

        se il sorgente e' abbastanza largo  -> si tiene tutta l'altezza e si
                                               stringe la larghezza;
        se e' piu' stretto di 9:16          -> si tiene tutta la larghezza e
                                               si accorcia l'altezza.

    Scriverla sull'altezza («va bene solo se src_h vale 1080») sarebbe il
    contrario di giusto: boccerebbe tutti i girati di oggi, che sono 478x850,
    e lascerebbe passare 1080x1920, che e' il caso peggiore.

    SUI GIRATI VERI NON CAMBIA NIENTE, ed e' voluto:
        1920x1080 -> 608x1080  (identico a min(608, 1920) e altezza piena)
         478x850  -> 478x850   (identico a min(608, 478) e altezza piena)
    Cioe' i video prodotti finora restano byte per byte quelli che erano: si
    chiude un difetto latente senza toccare il presente.

    Torna (larghezza, altezza), tutte e due pari.
    """
    if src_w <= 0 or src_h <= 0 or out_w <= 0 or out_h <= 0:
        raise ValueError(
            f"rettangolo_di_ritaglio: misure non valide "
            f"({src_w}x{src_h} verso {out_w}x{out_h})")

    larghezza_a_piena_altezza = src_h * out_w / out_h
    if src_w >= larghezza_a_piena_altezza:
        # Sorgente largo: tutta l'altezza, larghezza stretta al rapporto.
        altezza = min(lato_pari(src_h), _pari_per_difetto(src_h))
        larghezza = min(lato_pari(larghezza_a_piena_altezza), _pari_per_difetto(src_w))
        return larghezza, altezza

    # Sorgente stretto: tutta la larghezza, altezza accorciata al rapporto.
    # La larghezza si CHIUDE PRIMA, e l'altezza si calcola su quella chiusa:
    # calcolarla sul sorgente darebbe un rapporto che non e' quello del
    # rettangolo che esce davvero.
    larghezza = min(lato_pari(src_w), _pari_per_difetto(src_w))
    altezza = min(lato_pari(larghezza * out_h / out_w), _pari_per_difetto(src_h))
    return larghezza, altezza
