"""Correzioni per singola clip: dove sta il ritaglio verticale e dove si taglia.

PERCHE' ESISTE
Fino a oggi il ritaglio 9:16 era UN numero calcolato una volta sola da
compute_crop_x (mediana dei centri del volto su 11 campioni) e i due estremi
del taglio venivano da due costanti globali, PAD_START_S e PAD_END_S in
config.py. Se il ritaglio tagliava la fronte, o la clip partiva mezzo secondo
tardi, non esisteva nessun modo di correggerlo: l'unica risposta possibile era
rifiutare il cancello e rifare TUTTI gli short del giro. Questo modulo e' il
binario che permette di correggerne UNO.

DOVE VIVE IL FILE
Nel workspace locale, accanto agli altri artefatti:

    build/correzioni.json

Il worker lo scarica in build/correzioni.json e lo passa a render.py con
--correzioni. Se il file non c'e', non cambia niente: si fa esattamente quello
che si faceva prima, con gli stessi numeri.

FORMATO

    {
      "versione": 2,
      "clip": {
        "short_02_i-tre-errori": {
          "ancora_x": 0.08,       frazione della LARGHEZZA DEL GIRATO di cui
                                  spostare il ritaglio: +0.08 = 8% a destra,
                                  -0.08 = 8% a sinistra
          "pad_inizio_s": -1.5,   secondi da aggiungere all'attacco
                                  (negativo = parte piu' tardi, accorcia)
          "pad_fine_s": 0.4       secondi da aggiungere alla coda
                                  (negativo = finisce prima, accorcia)
        }
      }
    }

I campi mancanti — e i campi a null — valgono zero.

SIGNIFICATO DEI NUMERI, da leggere prima di scrivere il file: sono
SCOSTAMENTI su quello che il montaggio ha gia' calcolato, non valori
assoluti. Zero vuol dire «non correggere niente», ed e' per questo che un
file senza voci, o una voce a zero, ridanno esattamente il video di prima.

PERCHE' LA VERSIONE E' 2, E PERCHE' LA 1 SI RIFIUTA
La versione 1 e' esistita con gli stessi tre nomi di campo e un significato
OPPOSTO: erano posizioni assolute — 'ancora_x' era il punto del fotogramma
dove mettere il ritaglio, i due pad SOSTITUIVANO PAD_START_S e PAD_END_S. Gli
stessi identici numeri, letti con le due regole, danno due video diversi: con
la regola nuova un file vecchio che diceva «pad_inizio_s: -0.20» (cioe' «lascia
il default») anticiperebbe l'attacco di altri 0,20 s, e un «ancora_x: 0.5»
(«centrato») sposterebbe il ritaglio di mezza larghezza del girato.
Non c'e' modo di distinguere i due casi guardando i numeri: quindi non si
indovina e non si converte. Un file di versione 1 FERMA il passo con un
messaggio che dice cosa e' cambiato; chi lo trova riscrive gli scostamenti.
Per lo stesso motivo il campo 'versione' e' OBBLIGATORIO: un file che non
dichiara con quale regola e' stato scritto non si legge con nessuna delle due.

  ancora_x     parte dal ritaglio deciso dal rilevamento del volto e lo
               sposta. NON e' la posizione dell'ancora nel fotogramma: 0
               non vuol dire «al bordo sinistro», vuol dire «lascia dov'e'».
  pad_inizio_s parte dal taglio gia' calcolato — che comprende gia'
               PAD_START_S e PAD_END_S di config.py — e lo sposta. NON
               sostituisce quelle due costanti: scrivere -0.20 qui
               anticiperebbe l'attacco di altri 0,20 s.

La chiave e' il NOME BASE del file dello short
— 'short_02_i-tre-errori', cioe' out/short_02_i-tre-errori.mp4 senza cartella
ne' estensione. Si accettano anche le forme che girano altrove nel sistema
('short_02_i-tre-errori.mp4', e soprattutto 'short_02_i-tre-errori-FX.mp4',
che e' il nome con cui la clip compare in calendario e nel pannello) e si
riducono tutte alla stessa chiave: chi corregge ha in mano il nome del -FX,
non quello dell'mp4 intermedio.

I LIMITI, E COSA SUCCEDE QUANDO LA RICHIESTA LI SUPERA
Sono tutti limiti FISICI, nessuno inventato:

  - il ritaglio non puo' uscire dal fotogramma:
        0 <= crop_x <= larghezza_girato - larghezza_ritaglio
  - il taglio non puo' cominciare prima dell'inizio del girato ne' finire
    dopo la sua fine;
  - la clip non puo' scendere sotto la durata minima (config.MIN_CLIP_S):
    sotto quella soglia resolve_highlights scarterebbe la clip, e una
    correzione non deve MAI far sparire lo short che stava correggendo.

Quando una richiesta supera un limite non si fallisce e non si tace: si
applica il massimo possibile e si scrive un avviso. L'avviso finisce sia su
stdout sia dentro il metadata della clip (out/<nome>.json, campo
'correzioni.avvisi'), da dove il worker lo trasforma in un evento leggibile
nella cronologia del lavoro.

Il file scritto male e' un'altra cosa e si comporta in modo opposto: campo
sconosciuto, valore non numerico, versione ignota fanno FALLIRE il passo con
un messaggio che dice cosa e' ammesso. Un campo battuto storto ('ancoraX')
ignorato in silenzio lascerebbe il cliente davanti alla stessa clip di prima
senza capire perche'.

QUANDO SI APPLICANO
DOPO resolve_highlights, cioe' dopo la selezione e la deduplicazione degli
highlights. E' una scelta, non un dettaglio di implementazione: i nomi dei
file sono 'short_<progressivo>_<slug>' e il progressivo esce dall'ordine
della lista deduplicata. Se i pad entrassero prima, allungare una clip
potrebbe farla sovrapporre a un'altra, cambiare l'esito del dedupe e
rinominare file che intanto sono gia' in calendario e magari gia' pubblicati:
si correggerebbe uno short e ne sparirebbe un altro.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import fondamenta

# I tre campi ammessi in una voce, ed e' una lista chiusa: vedi sopra.
CAMPI = ("ancora_x", "pad_inizio_s", "pad_fine_s")

# Campi che chi scrive il file puo' aggiungere per se' e che il montaggio
# IGNORA: non entrano nel calcolo e non cambiano un fotogramma. Stanno in una
# lista esplicita, non in un «accetta tutto», cosi' un campo battuto storto
# resta un errore e non un silenzio. 'aggiornata_il' e' la marca temporale che
# l'API scrive sulla voce quando la salva.
CAMPI_INFORMATIVI = ("aggiornata_il",)

# La versione del formato che questa pipeline sa leggere. Sale insieme al
# SIGNIFICATO dei numeri, non insieme al codice: finche' i tre campi vogliono
# dire «scostamenti su quello che il montaggio ha gia' deciso», resta 2.
# Specchio: VERSIONE_CORREZIONI in worker/src/motore.js e la versione scritta
# dalla rotta correzioni dell'API. Se cambia, cambiano tutti e tre insieme.
VERSIONE_ATTESA = 2

# Le versioni che sono esistite con un significato diverso: si riconoscono per
# poter dire COSA e' cambiato invece di un generico «versione sconosciuta».
VERSIONI_VECCHIE = {
    1: ("i tre numeri erano POSIZIONI ASSOLUTE (ancora_x = dove mettere il "
        "ritaglio nel fotogramma, i due pad SOSTITUIVANO PAD_START_S e "
        "PAD_END_S di config.py); ora sono SCOSTAMENTI su quello che il "
        "montaggio ha gia' deciso, e 0 vuol dire «non toccare». Gli stessi "
        "numeri letti con le due regole danno due video diversi: riscrivi la "
        "voce come scostamento e metti \"versione\": 2"),
}

# Tolleranza sui confronti fra durate in secondi: sotto il millesimo si sta
# discutendo dell'errore di arrotondamento, non del taglio.
EPS = 1e-9


class CorrezioneNonValida(ValueError):
    """Il file di correzioni e' scritto male: ci si ferma, non si indovina."""


# ------------------------------------------------------------------ avvisi

def avviso(campo: str, chiesto: float, applicato: float, motivo: str) -> dict:
    """Un limite raggiunto, in forma leggibile da una persona e da un programma."""
    return {
        "campo": campo,
        "chiesto": fondamenta.arrotonda_decimale(chiesto, 4),
        "applicato": fondamenta.arrotonda_decimale(applicato, 4),
        "motivo": motivo,
    }


def testo_avviso(a: dict) -> str:
    return (f"LIMITE {a['campo']}: chiesto {a['chiesto']:+g}, "
            f"applicato {a['applicato']:+g} — {a['motivo']}")


# ------------------------------------------------------------------ lettura

def normalizza_nome(nome: str) -> str:
    """Riduce alla chiave unica le forme con cui una clip viene nominata.

    'out/short_02_x.mp4', 'short_02_x-FX.mp4', 'short_02_x.json' -> 'short_02_x'
    """
    base = Path(str(nome)).name
    for estensione in (".mp4", ".json", ".ass"):
        if base.lower().endswith(estensione):
            base = base[: -len(estensione)]
            break
    if base.endswith("-FX"):
        base = base[: -len("-FX")]
    return base


def vuota() -> dict:
    """La correzione che non corregge niente: tutti gli scostamenti a zero."""
    return {campo: 0.0 for campo in CAMPI}


def e_vuota(correzione: dict | None) -> bool:
    return correzione is None or all(correzione.get(c, 0.0) == 0.0 for c in CAMPI)


def _voce(nome: str, voce) -> dict:
    if not isinstance(voce, dict):
        raise CorrezioneNonValida(
            f"correzioni: la voce '{nome}' deve essere un oggetto con "
            f"{', '.join(CAMPI)}, non {type(voce).__name__}")
    ignoti = sorted(k for k in voce if k not in CAMPI and k not in CAMPI_INFORMATIVI)
    if ignoti:
        raise CorrezioneNonValida(
            f"correzioni: la voce '{nome}' ha campi che non esistono: "
            f"{', '.join(ignoti)}. Ammessi: {', '.join(CAMPI)}")
    pulita = vuota()
    for campo in CAMPI:
        if campo not in voce:
            continue
        valore = voce[campo]
        # null esplicito = «questa correzione non c'e'», che qui vuol dire
        # scostamento zero: il ritaglio torna a deciderlo il rilevamento del
        # volto e il taglio resta quello calcolato. Vale come il campo assente.
        if valore is None:
            continue
        # bool e' sottoclasse di int in Python: True passerebbe per 1
        if isinstance(valore, bool) or not isinstance(valore, (int, float)):
            raise CorrezioneNonValida(
                f"correzioni: '{nome}.{campo}' deve essere un numero, "
                f"non {type(valore).__name__}")
        if not math.isfinite(float(valore)):
            raise CorrezioneNonValida(
                f"correzioni: '{nome}.{campo}' non e' un numero finito")
        pulita[campo] = float(valore)
    return pulita


def leggi(percorso) -> dict[str, dict]:
    """Legge il file delle correzioni. File assente = nessuna correzione ({})."""
    p = Path(percorso)
    if not p.exists():
        return {}
    testo = p.read_text(encoding="utf-8").strip()
    if testo == "":
        return {}
    try:
        doc = json.loads(testo)
    except json.JSONDecodeError as errore:
        raise CorrezioneNonValida(
            f"correzioni: '{p}' non e' JSON valido: {errore}") from errore
    if not isinstance(doc, dict):
        raise CorrezioneNonValida(
            f"correzioni: '{p}' deve contenere un oggetto, non {type(doc).__name__}")
    if "versione" not in doc:
        raise CorrezioneNonValida(
            f"correzioni: '{p}' non dichiara il campo 'versione'. Questa "
            f"pipeline legge la {VERSIONE_ATTESA}, dove i tre numeri sono "
            "SCOSTAMENTI su quello che il montaggio ha gia' deciso (0 = non "
            "toccare). Un file che non dice con quale regola e' stato scritto "
            f"non si interpreta: aggiungi \"versione\": {VERSIONE_ATTESA}")
    versione = doc["versione"]
    if versione != VERSIONE_ATTESA:
        if versione in VERSIONI_VECCHIE:
            raise CorrezioneNonValida(
                f"correzioni: '{p}' e' di versione {versione}, scritto con la "
                f"semantica vecchia. {VERSIONI_VECCHIE[versione]}")
        raise CorrezioneNonValida(
            f"correzioni: versione {versione!r} sconosciuta (questa pipeline "
            f"legge la {VERSIONE_ATTESA})")
    voci = doc.get("clip", {})
    if not isinstance(voci, dict):
        raise CorrezioneNonValida(
            "correzioni: 'clip' deve essere un oggetto {nome_clip: correzione}")
    fuori: dict[str, dict] = {}
    for nome, voce in voci.items():
        chiave = normalizza_nome(nome)
        if chiave == "":
            raise CorrezioneNonValida(f"correzioni: nome di clip vuoto ({nome!r})")
        if chiave in fuori:
            raise CorrezioneNonValida(
                f"correzioni: la clip '{chiave}' compare due volte (nomi diversi, "
                "stessa clip): tienine una sola, o non si sa quale vince")
        fuori[chiave] = _voce(chiave, voce)
    return fuori


# ------------------------------------------------------- ritaglio verticale

def applica_ancora_x(x_base, ancora_x, src_w, crop_w) -> tuple[int, dict]:
    """Sposta il ritaglio verticale e lo riporta dentro il fotogramma.

    x_base   il ritaglio che il codice ha calcolato da solo (centri del volto,
             oppure il centro del fotogramma quando i volti non si trovano)
    ancora_x scostamento chiesto, in frazione della larghezza del GIRATO
    src_w    larghezza del girato in pixel
    crop_w   larghezza del ritaglio in pixel

    Torna (x, dettaglio). 'dettaglio' dice di quanto e' cambiato davvero:
      crop_x_senza_correzione  il valore che sarebbe uscito senza correzione
      spostamento_px           differenza fra i due, in pixel
      avvisi                   i limiti raggiunti (lista, vuota se nessuno)

    Con ancora_x = 0 il risultato e' identico a quello di prima, per
    costruzione: e' lo stesso taglio con lo stesso arrotondamento.
    """
    massimo = max(0, int(src_w) - int(crop_w))

    def dentro(v: float) -> int:
        return max(0, min(massimo, int(v)))

    # Arrotondamento a meta' lontano da zero, non quello di fabbrica (a meta'
    # pari): con un x_base a .5 esatti i due danno due ritagli diversi di un
    # pixel, e il ritaglio calcolato qui e quello scritto nel metadata devono
    # essere lo stesso numero (docs/fondamenta-numeriche.md, voce 4).
    senza = dentro(fondamenta.arrotonda(x_base))
    chiesto = fondamenta.arrotonda(float(x_base) + float(ancora_x) * float(src_w))
    applicato = dentro(chiesto)

    avvisi = []
    if float(ancora_x) != 0.0 and applicato != chiesto:
        ottenuto = (applicato - senza) / float(src_w) if src_w else 0.0
        avvisi.append(avviso(
            "ancora_x", ancora_x, ottenuto,
            f"il ritaglio sarebbe uscito dal fotogramma: x puo' stare solo "
            f"fra 0 e {massimo} px"))
    return applicato, {
        "crop_x_senza_correzione": senza,
        "spostamento_px": applicato - senza,
        "avvisi": avvisi,
    }


# ------------------------------------------------------------- taglio (pad)

def applica_pad(start_base, end_base, pad_inizio_s, pad_fine_s,
                durata, min_clip_s) -> tuple[float, float, list]:
    """Sposta attacco e coda del taglio restando dentro il girato.

    start_base / end_base  il taglio calcolato da resolve_highlights
    pad_inizio_s           secondi da aggiungere all'attacco (negativo accorcia)
    pad_fine_s             secondi da aggiungere alla coda   (negativo accorcia)
    durata                 durata del girato in secondi
    min_clip_s             durata minima ammessa per una clip

    Torna (inizio, fine, avvisi), con i secondi arrotondati al millesimo come
    fa resolve_highlights.

    Ordine delle regole, e conta:
      1. si applicano i due scostamenti;
      2. si riporta il taglio dentro il girato (0 .. durata);
      3. se cosi' la clip e' scesa sotto la durata minima si restituisce
         quello che serve, prendendolo PRIMA dalla coda e poi dall'attacco.
         La coda per prima perche' spostare l'attacco cambia la frase con cui
         lo short comincia — e l'attacco e' la cosa che chi guarda vede per
         prima. Se anche cosi' non si arriva al minimo (girato piu' corto
         della durata minima) si prende tutto quello che c'e' e lo si dice.
    """
    durata = float(durata)
    min_clip_s = float(min_clip_s)
    inizio_chiesto = float(start_base) + float(pad_inizio_s)
    fine_chiesta = float(end_base) + float(pad_fine_s)
    inizio, fine = inizio_chiesto, fine_chiesta
    avvisi: list[dict] = []

    # 1) dentro il girato
    if inizio < 0.0:
        avvisi.append(avviso(
            "pad_inizio_s", pad_inizio_s, float(pad_inizio_s) - inizio,
            "il girato comincia a 0: l'attacco non puo' andare piu' indietro"))
        inizio = 0.0
    if fine > durata:
        avvisi.append(avviso(
            "pad_fine_s", pad_fine_s, float(pad_fine_s) - (fine - durata),
            f"il girato finisce a {durata:.2f}s: la coda non puo' andare oltre"))
        fine = durata
    # taglio rovesciato (accorciature che si incrociano): si azzera la durata
    # e ci pensa la regola del minimo qui sotto a restituire i secondi
    if fine < inizio:
        fine = inizio
    if inizio > durata:
        inizio = durata
        fine = durata

    # 2) durata minima
    durata_grezza = fine - inizio
    if durata_grezza < min_clip_s - EPS:
        mancano = min_clip_s - durata_grezza
        aggiunta_coda = min(mancano, max(0.0, durata - fine))
        fine += aggiunta_coda
        mancano -= aggiunta_coda
        if mancano > EPS:
            aggiunta_attacco = min(mancano, max(0.0, inizio))
            inizio -= aggiunta_attacco
            mancano -= aggiunta_attacco
        avvisi.append(avviso(
            "durata", durata_grezza, fine - inizio,
            f"sotto la durata minima di {min_clip_s:.0f}s: la clip e' stata "
            "riallungata (prima la coda, poi l'attacco)"))
        if mancano > EPS:
            avvisi.append(avviso(
                "durata", min_clip_s, fine - inizio,
                f"il girato dura {durata:.2f}s in tutto: la durata minima di "
                f"{min_clip_s:.0f}s non e' raggiungibile"))

    return (fondamenta.arrotonda_decimale(inizio),
            fondamenta.arrotonda_decimale(fine), avvisi)
