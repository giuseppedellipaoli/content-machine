"""Il karaoke: i sottotitoli che si accendono parola per parola.

Tre passi, in quest'ordine, ed e' l'ordine a renderli corretti:

    1. ALLINEAMENTO  fra il testo gia' spezzato in pezzi e i tempi di parola.
       Consumo greedy sul conteggio dei caratteri ALFANUMERICI, mai sulle
       parole. Ripiego proporzionale quando l'allineamento non copre.
    2. CAMPATE        agganciate al blocco: test di sovrapposizione stretto,
       doppio agganciamento, elenco vuoto = ASSENZA (None), non lista vuota.
    3. ANIMAZIONE     per parola: rampe attenuate con smoothstep, pivot a 0,35
       corpi, evidenziazione mantenuta fino alla parola successiva.

Le fonti sono i documenti 70 (sezioni 8.7, 8.8, 10.2-10.6) e 52 (sezione 9)
del corpus; i numeri di formula fra parentesi rimandano li'. Le costanti di
fondazione — arrotondamento a meta' lontano da zero, fattore del testo,
nessuna linearizzazione del colore — arrivano da `fondamenta`: qui non se ne
riscrive nemmeno una.


CHE COSA ESCE DAVVERO DA QUESTO MODULO, E CHE COSA NO
-----------------------------------------------------
Oggi i sottotitoli sono file ASS renderizzati da libass dentro ffmpeg. La
scelta e' stata: **karaoke ASS**, non rasterizzazione in Python. Il motivo e'
che esce oggi, non aggiunge dipendenze, non costa un fotogramma in piu' di
render, e riusa la catena colore gia' provata.

Il prezzo, dichiarato voce per voce:

    resa in ASS         preset             cosa si perde
    ------------------  -----------------  --------------------------------
    fedele              none               niente
    fedele              popIn              niente (la scala e' di blocco e
                                           l'ancora \\an5 e' gia' il centro)
    quasi fedele        slideUp            lo spostamento e' LINEARE: \\move
                                           e' l'unico modo di muovere una
                                           riga e non accetta attenuazione.
                                           L'opacita' resta attenuata.
    fedele              wordReveal         niente
    fedele              highlightPop       niente
    quasi fedele        typewriter         niente cursore lampeggiante
    DEGRADATO a         wordSlide          lo spostamento verticale per
    wordReveal                             PAROLA vuole un \\pos per parola,
                                           che vuole le metriche del testo.
                                           Il colore resta quello giusto.
    DEGRADATO a         highlightBlock     il riquadro arrotondato dietro la
    highlightPop                           parola vuole il rettangolo della
                                           parola, cioe' le stesse metriche.
                                           L'evidenziazione resta.

    I due DEGRADATI escono con l'animazione del preset piu' vicino, non fermi:
    quello che ASS non sa fare sono le METRICHE (dove cade ogni parola), non
    il colore. Spegnere tutto per un riquadro mancante toglierebbe anche la
    parola che si accende. Il degrado non e' silenzioso: `degradazione()` dice
    cosa e' stato chiesto, cosa esce e cosa non arriva — stessa regola degli
    avvisi delle correzioni.

    In tutti i preset la curva `smoothstep` non e' quella che valuta libass:
    `\\t` interpola LINEARMENTE (il parametro di accelerazione e' una potenza,
    non `t^2(3-2t)`). La rampa viene quindi emessa come SEGMENTI_RAMPA tratti
    lineari che campionano smoothstep: la curva vista e' quella giusta a meno
    dell'errore di campionamento, ma la forma chiusa non e' quella calcolata.

Il contorno a DUE PASSATE del corpus (sottofondo di solo tratto a spessore
doppio, poi riempimento opaco, giunzione arrotondata, contorno e riempimento
in UN solo livello di trasparenza cosi' l'ombra si applica una volta sola)
non si perde: e' esattamente quello che libass fa di suo con `Outline` e
`Shadow` nello stile, disegnando ombra -> bordo -> riempimento una volta per
riga. Non c'e' niente da riprodurre a mano, e non va riprodotto a mano.

COSA SERVIREBBE PER LA STRADA (b), la rasterizzazione in Python:
    - una libreria di shaping vera (uharfbuzz) piu' un rasterizzatore
      (skia-python o Pillow con FreeType) per avere le PENNE, cioe' la x e la
      larghezza di ogni parola dentro la riga gia' impaginata;
    - un ciclo per fotogramma che compone il raster sul video con `overlay`
      invece di `ass`, e quindi una cache del raster per firma di stile;
    - metriche di font ALLINEATE a quelle di libass, o i sottotitoli si
      spostano rispetto a quelli di oggi anche a preset spento;
    - un nuovo riferimento per la prova di regressione: quella di oggi
      confronta i byte contro il render precedente, e la strada (b) li cambia
      tutti per costruzione.
    Stima onesta: e' un lavoro a se', non una rifinitura di questo.
"""
from __future__ import annotations

import math
from typing import Callable, NamedTuple, Sequence

import fondamenta

# ---------------------------------------------------------------------------
# Le costanti del corpus. Numerate come li' (C.. = tabella 18 del doc 52).
# ---------------------------------------------------------------------------

PRESET = (
    "none", "popIn", "slideUp", "typewriter",
    "wordReveal", "wordSlide", "highlightPop", "highlightBlock",
)
#: I preset che questo emettitore ASS rende PER INTERO, senza perdere niente.
#: Gli altri si rendono lo stesso, ma degradati: vedi DEGRADAZIONI.
PRESET_RESI = ("none", "popIn", "typewriter", "wordReveal", "highlightPop")

#: Cosa si perde, preset per preset, passando per ASS.
#: chiesto -> (preset con cui esce davvero, cosa non arriva).
#:
#: La scelta di fondo: si degrada al preset PIU' VICINO che ASS sa disegnare,
#: e NON si spegne l'animazione. Il colore di ogni preset per parola ASS lo
#: sa fare; quello che non sa fare sono le METRICHE — dove cade ogni singola
#: parola sullo schermo — perche' libass le calcola dentro di se' e non le
#: espone. Spegnere tutto per una scala o un riquadro mancante toglierebbe
#: anche la parola che si accende, che e' il 90% di quello che si vede.
DEGRADAZIONI = {
    "wordSlide": ("wordReveal", "lo scorrimento verticale di ogni parola"),
    "highlightBlock": ("highlightPop", "il riquadro arrotondato dietro la parola"),
    "slideUp": ("slideUp", "l'attenuazione dell'entrata: \\move e' lineare"),
}
PRESET_PER_PAROLA = ("wordReveal", "wordSlide", "highlightPop", "highlightBlock")
PRESET_DI_BLOCCO = ("popIn", "slideUp")


def degradazione(preset: str) -> dict | None:
    """Cosa perde questo preset passando per ASS. None se non perde niente.

    Si DICHIARA invece di tacere. Un preset che esce diverso da come e' stato
    chiesto, e non lo dice, e' indistinguibile da un'impostazione ignorata: il
    cliente vede che ha scelto «wordSlide», vede una cosa che non scorre, e
    conclude che l'app non lo ascolta. E' la stessa regola degli avvisi delle
    correzioni — si applica il massimo possibile e si avvisa.
    """
    voce = DEGRADAZIONI.get(preset)
    if voce is None:
        return None
    reso, perso = voce
    return {"chiesto": preset, "reso": reso, "perso": perso}


def testo_degradazione(d: dict) -> str:
    return (f"ANIMAZIONE {d['chiesto']}: resa come {d['reso']} — "
            f"non arriva {d['perso']}")


FOTOGRAMMI_PER_PAROLA_PREDEFINITO = 6          # C61
EVIDENZIAZIONE_PREDEFINITA = (255, 217, 0)     # C62, (1; 0,85; 0) in 0-255
SCALA_INIZIALE_POPIN = 0.6                     # C63
AMPIEZZA_SCALA_POPIN = 0.4                     # C64
AMPIEZZA_SLIDEUP = 0.05                        # C65, altezze di canvas
AMPIEZZA_WORDSLIDE = 0.5                       # C66, corpi
MASSIMO_RAMPA_EVIDENZIAZIONE = 4               # C67
DIVISORE_SPAN_RAMPA = 2                        # C68
FOTOGRAMMI_TENUTA_MACCHINA = 18                # C70
SOGLIA_ALPHA_BLOCCO = 0.001                    # C74
PAD_X_BLOCCO = 0.18                            # C76, corpi
PAD_Y_BLOCCO = 0.10                            # C77, corpi
RAGGIO_BLOCCO = 0.12                           # C78, corpi
ASCENDENTE_RIPIEGO = 0.8                       # C79, corpi
DISCENDENTE_RIPIEGO = 0.2                      # C80, corpi
PIVOT_VERTICALE = 0.35                         # C81, corpi sopra la linea base

#: In quanti tratti lineari si spezza una rampa per campionare `smoothstep`.
#: Non e' del corpus: e' il prezzo dichiarato della strada ASS. Con 4 tratti
#: lo scarto massimo dalla curva vera e' sotto 0,02 — invisibile su un colore
#: e su una scala, e costa quattro tag invece di uno.
SEGMENTI_RAMPA = 4

#: La griglia di fotogrammi su cui sono espresse le rampe. NON e' la frequenza
#: del video prodotto: i tempi che finiscono nel file ASS sono in millisecondi
#: assoluti, quindi una rampa di 6 fotogrammi dura 200 ms qualunque sia la
#: frequenza del render. Serve solo a dare un significato al numero "6".
FPS_NOMINALE = 30.0


# ===========================================================================
# PASSO 1 — allineamento fra testo spezzato e tempi di parola   (doc 70, 8.7)
# ===========================================================================

class Run(NamedTuple):
    """Una parola temporizzata come esce dal riconoscitore."""
    testo: str
    alfanumerici: int
    inizio: float
    fine: float


class Campata(NamedTuple):
    """La campata di UNA parola dentro un blocco.

    `indice` e' la posizione della parola nel blocco, ed e' l'unico modo
    lecito di risolverla. Vedi `risolvi_campata`.
    """
    indice: int
    testo: str
    inizio: float
    fine: float


class Blocco(NamedTuple):
    """Un pezzo di testo con i suoi tempi e, se ci sono, le sue campate.

    `campate` e' None — ASSENZA — quando non c'e' temporizzazione per parola.
    Non e' una lista vuota, e la differenza conta: chi consuma l'animazione
    legge l'assenza come «nessun karaoke possibile qui» e disegna il blocco
    fermo, mentre una lista vuota lo farebbe passare per un blocco animato
    senza parole (doc 70, 10.6).
    """
    testo: str
    inizio: float
    fine: float
    campate: tuple[Campata, ...] | None


def conta_alfanumerici(testo: str) -> int:
    """Quante lettere o cifre Unicode ci sono. Punteggiatura e simboli: zero.

    E' il conteggio su cui si allinea, e non e' un dettaglio di comodo. Le run
    del riconoscitore non cadono sui confini di parola del testo: le
    contrazioni («l'AI»), i numeri col separatore («1.500»), la punteggiatura
    staccata raggruppano diversamente. La sequenza dei soli caratteri
    alfanumerici invece COINCIDE fra testo e run comunque siano raggruppati,
    ed e' quello che rende il consumo greedy affidabile.
    """
    return sum(1 for c in str(testo) if c.isalnum())


def run_temporizzate(parole: Sequence[dict]) -> list[Run]:
    """Le parole utilizzabili, in ordine. Scarta quelle senza tempi e quelle
    con zero alfanumerici (doc 70, 8.7 passo 1).

    Accetta la forma della pipeline (`{"w":..., "start":..., "end":...}`) e
    quella del corpus (`{"testo":..., "inizio":..., "fine":...}`).
    """
    fuori: list[Run] = []
    for p in parole:
        testo = p.get("w", p.get("testo"))
        inizio = p.get("start", p.get("inizio"))
        fine = p.get("end", p.get("fine"))
        if testo is None or inizio is None or fine is None:
            continue
        n = conta_alfanumerici(testo)
        if n == 0:
            continue
        fuori.append(Run(str(testo).strip(), n, float(inizio), float(fine)))
    return fuori


def distribuzione_proporzionale(pezzi: Sequence[str], inizio: float,
                                fine: float) -> list[Blocco]:
    """Il ripiego: si spartisce l'intervallo sui caratteri (doc 70, 8.8).

    Schiena contro schiena, nessun buco, e i blocchi escono SENZA campate:
    su questa strada il karaoke non e' possibile e va detto, non simulato.
    """
    if not pezzi:
        return []
    pesi = [max(len(t), 1) for t in pezzi]
    totale = sum(pesi)
    campata = max(float(fine) - float(inizio), 0.0)
    fuori: list[Blocco] = []
    cursore = float(inizio)
    for testo, peso in zip(pezzi, pesi):
        durata = campata * peso / totale
        fuori.append(Blocco(testo, cursore, cursore + durata, None))
        cursore += durata
    return fuori


def allinea(pezzi: Sequence[str], parole: Sequence[dict], inizio: float,
            fine: float) -> list[Blocco]:
    """Dai pezzi di testo ai blocchi temporizzati, con le campate di parola.

    Consumo greedy sul conteggio alfanumerici (doc 70, 8.7 passo 3): per ogni
    pezzo si consumano run finche' l'accumulato e' STRETTAMENTE MINORE del
    voluto. L'ultima run puo' quindi sforare — e' voluto: agganciarsi a meta'
    run non vorrebbe dire niente.

    IL NOSTRO MIGLIORAMENTO, DICHIARATO. Nel corpus un pezzo senza caratteri
    alfanumerici — un «...» o un «—» isolato da una rottura su delimitatore —
    ha «voluto» zero, quindi la condizione di continuazione e' falsa alla
    prima valutazione, nessuna run viene consumata, il ciclo si INTERROMPE e
    l'intero segmento ricade sulla distribuzione proporzionale: tutte le
    campate di tutti i pezzi spariscono, non solo quelle del pezzo colpevole
    (doc 70, 8.7 e trappola 27). Qui invece quel pezzo si SALTA: gli si da'
    il buco fra la run precedente e la successiva, campate assenti, e il
    ciclo prosegue. Gli altri pezzi tengono il loro karaoke.

    Resta invece fedele l'altra uscita anticipata: se le run finiscono mentre
    restano pezzi da temporizzare, la copertura non torna e si butta tutto.
    Li' il ripiego e' giusto, perche' i blocchi gia' costruiti sarebbero
    allineati a un testo che non e' quello che si vede.
    """
    if not pezzi:
        return []
    run = run_temporizzate(parole)
    if not run:
        return distribuzione_proporzionale(pezzi, inizio, fine)

    fuori: list[Blocco] = []
    i = 0                       # indice sulle run
    ultima_fine = float(inizio)  # dove si e' fermata l'ultima run consumata
    for testo in pezzi:
        voluto = conta_alfanumerici(testo)
        if voluto == 0:
            # Il pezzo senza alfanumerici: sta nel buco, non consuma niente,
            # non ferma il ciclo. Se non c'e' una run dopo, il buco si chiude
            # sulla fine del segmento.
            prossimo = run[i].inizio if i < len(run) else float(fine)
            fuori.append(Blocco(str(testo), ultima_fine,
                                max(ultima_fine, prossimo), None))
            continue
        accumulato = 0
        prima: Run | None = None
        ultima: Run | None = None
        campate: list[Campata] = []
        while i < len(run) and accumulato < voluto:
            corrente = run[i]
            if prima is None:
                prima = corrente
            ultima = corrente
            campate.append(Campata(len(campate), corrente.testo,
                                   corrente.inizio, corrente.fine))
            accumulato += corrente.alfanumerici
            i += 1
        if prima is None or ultima is None:
            break               # run esaurite: la copertura fallira'
        ultima_fine = ultima.fine
        fuori.append(Blocco(str(testo), prima.inizio, ultima.fine,
                            tuple(campate) if campate else None))

    if len(fuori) != len(pezzi):
        return distribuzione_proporzionale(pezzi, inizio, fine)
    return fuori


def risolvi_campata(blocco: Blocco, indice: int) -> Campata | None:
    """La campata numero `indice` del blocco. UNICO modo lecito di trovarla.

    LA TRAPPOLA, dichiarata. Il maiuscolo (o il minuscolo) si applica al testo
    DEL BLOCCO e non a quello delle campate: il blocco viene ricostruito
    conservando inizio, fine ed elenco identici, e i testi delle campate NON
    vengono convertiti (doc 70, 11.3 e 21.8). Chi cercasse la campata
    confrontando il suo testo con la parola letta nel blocco non la
    troverebbe mai, con UPPERCASE acceso — che e' il nostro caso di brand.
    Si risolve per posizione, e basta.
    """
    if blocco.campate is None:
        return None
    if 0 <= int(indice) < len(blocco.campate):
        return blocco.campate[int(indice)]
    return None


# ===========================================================================
# PASSO 2 — campate agganciate al blocco                     (doc 70, 10.2-10.6)
# ===========================================================================

class Finestra(NamedTuple):
    """La finestra di clip su cui si mappano i tempi sorgente.

    Nella pipeline degli short le parole arrivano gia' RIBASATE in secondi di
    clip (render.collect_words passa dai pezzi), la velocita' e' 1 e il
    ritaglio e' 0: la mappatura si riduce a `secondi x fps` agganciato. La
    forma generale resta comunque scritta, perche' e' quella corretta e
    perche' un domani la clip potrebbe avere velocita' diversa da 1.
    """
    fps: float
    frame_inizio: int
    frame_fine: int              # semiaperto
    inizio_ritaglio: float = 0.0  # in frame sorgente
    velocita: float = 1.0

    @property
    def visibile_inizio_sorgente(self) -> float:
        return float(self.inizio_ritaglio)

    @property
    def visibile_fine_sorgente(self) -> float:
        durata = int(self.frame_fine) - int(self.frame_inizio)
        return float(self.inizio_ritaglio) + durata * max(float(self.velocita), 0.0001)


def sovrapposto(inizio_s: float, fine_s: float, f: Finestra) -> bool:
    """Test di sovrapposizione STRETTO (doc 70, 10.2).

    `fine x fps > visibile_inizio` E `inizio x fps < visibile_fine`. Un blocco
    che tocca esattamente un estremo e' ESCLUSO: non e' una svista, e' quello
    che tiene fuori i blocchi a durata nulla incollati al bordo.
    """
    return (float(fine_s) * f.fps > f.visibile_inizio_sorgente
            and float(inizio_s) * f.fps < f.visibile_fine_sorgente)


def converti_autorevole(secondi: float, f: Finestra) -> int | None:
    """secondi sorgente -> frame di timeline, oppure NIENTE (doc 70, 10.3).

    E' la conversione della clip, quella che RIFIUTA i tempi fuori campo.
    L'arrotondamento e' quello di fondazione: meta' lontano da zero, mai
    troncamento.
    """
    frame_sorgente = float(secondi) * f.fps
    scostamento = frame_sorgente - float(f.inizio_ritaglio)
    if scostamento < 0:
        return None
    frame = fondamenta.arrotonda(
        f.frame_inizio + scostamento / max(float(f.velocita), 0.0001))
    if frame < f.frame_inizio or frame >= f.frame_fine:
        return None
    return frame


def converti_ausiliaria(secondi: float, f: Finestra) -> int:
    """Come sopra ma NON restituisce mai niente: aggancia (doc 70, 10.4).

    Estremo destro INCLUSO, al contrario del test della conversione
    autorevole che lo esclude, e nessun rifiuto per scostamento negativo: un
    tempo prima del ritaglio da' semplicemente il primo frame. L'asimmetria
    fra le due funzioni e' reale e il corpus la registra come discrepanza
    (doc 70, 21.7): si riproduce perche' e' quella che tiene le campate
    dentro il blocco invece di farle sparire.
    """
    frame_sorgente = float(secondi) * f.fps
    scostamento = frame_sorgente - float(f.inizio_ritaglio)
    frame = fondamenta.arrotonda(
        f.frame_inizio + scostamento / max(float(f.velocita), 0.0001))
    return max(f.frame_inizio, min(f.frame_fine, frame))


class CampataFrame(NamedTuple):
    """Una campata gia' portata in fotogrammi RELATIVI all'inizio del blocco."""
    indice: int
    testo: str
    inizio: int
    fine: int


def campate_nel_blocco(blocco: Blocco, f: Finestra) -> tuple[
        int, int, tuple[CampataFrame, ...] | None]:
    """Il blocco in fotogrammi, con le sue campate relative (doc 70, 10.5-10.6).

    Torna (frame_inizio, durata, campate). `campate` e' None se non ne
    sopravvive nessuna: ASSENZA, non lista vuota.

    Il doppio agganciamento e' quello che impedisce a una campata di sporgere
    dal blocco:

        inizio_relativo = min( max(0, inizio_parola - inizio_blocco), durata )
        fine_relativa   = min( max(inizio_relativo, fine_parola - inizio_blocco), durata )

    e la campata si scarta se `fine <= inizio` — cioe' se dopo
    l'agganciamento non le resta nemmeno un fotogramma da occupare.
    """
    grezzo_inizio = converti_autorevole(blocco.inizio, f)
    grezzo_fine = converti_autorevole(blocco.fine, f)
    inizio = f.frame_inizio if grezzo_inizio is None else grezzo_inizio
    fine = f.frame_fine if grezzo_fine is None else grezzo_fine
    durata = max(1, min(f.frame_fine, fine) - max(f.frame_inizio, inizio))

    if blocco.campate is None:
        return inizio, durata, None

    fuori: list[CampataFrame] = []
    for campata in blocco.campate:
        if not sovrapposto(campata.inizio, campata.fine, f):
            continue
        parola_inizio = converti_ausiliaria(campata.inizio, f)
        parola_fine = converti_ausiliaria(campata.fine, f)
        rel_inizio = min(max(0, parola_inizio - inizio), durata)
        rel_fine = min(max(rel_inizio, parola_fine - inizio), durata)
        if rel_fine <= rel_inizio:
            continue
        # L'indice e' quello di ORIGINE, non la posizione nella lista filtrata:
        # e' il numero con cui la parola si ritrova nel testo del blocco anche
        # dopo che qualche campata e' stata scartata.
        fuori.append(CampataFrame(campata.indice, campata.testo,
                                  rel_inizio, rel_fine))
    return inizio, durata, (tuple(fuori) if fuori else None)


def riallinea_campate(campate: tuple[CampataFrame, ...] | None, scostamento: int,
                      durata: int) -> tuple[CampataFrame, ...] | None:
    """Le campate dopo un ridimensionamento del blocco (doc 70, 12.7).

    Serve quando la risoluzione delle sovrapposizioni accorcia un blocco: le
    campate si spostano di `scostamento`, si riagganciano alla nuova durata e
    quelle che non ci stanno piu' si scartano. Con scostamento zero — il caso
    della semplice estensione — non cambia niente salvo l'agganciamento.

    TRAPPOLA REGISTRATA dal corpus (trappola 28): forzare un blocco a 1
    fotogramma per risolvere una sovrapposizione distrugge quasi sempre le
    sue campate, e il blocco perde il karaoke. Non e' un difetto di questa
    funzione, e' la conseguenza aritmetica: va saputa, non aggirata di
    nascosto.
    """
    if campate is None:
        return None
    fuori: list[CampataFrame] = []
    for c in campate:
        inizio = min(max(0, c.inizio - int(scostamento)), int(durata))
        fine = min(max(inizio, c.fine - int(scostamento)), int(durata))
        if fine <= inizio:
            continue
        fuori.append(CampataFrame(c.indice, c.testo, inizio, fine))
    return tuple(fuori) if fuori else None


# ===========================================================================
# PASSO 3 — animazione per parola                                (doc 52, 9.4)
# ===========================================================================

def lineare(rel: float, inizio: float, durata: float) -> float:
    """Rampa lineare grezza (F82-F84).

    Le due guardie sono ASIMMETRICHE apposta: a `rel = inizio` vale 0, a
    `rel = inizio + durata` vale 1. Il primo valore non nullo cade al
    fotogramma `inizio + 1`, non a `inizio`.
    """
    if rel <= inizio:
        return 0.0
    if rel >= inizio + durata:
        return 1.0
    return (float(rel) - float(inizio)) / float(durata)


def smoothstep(t: float) -> float:
    """t^2 (3 - 2t), senza agganciamento (F85).

    Nessun clamp: tutte le chiamate garantiscono gia' t in [0,1] per
    costruzione. Metterne uno qui nasconderebbe l'errore di chi non lo fa.
    """
    return float(t) * float(t) * (3.0 - 2.0 * float(t))


def progresso(rel: float, inizio: float, durata: float) -> float:
    """La rampa attenuata (F86)."""
    return smoothstep(lineare(rel, inizio, durata))


def durata_rampa(inizio: int, fine: int, massimo: int) -> int | None:
    """Quanto dura la rampa dentro una parola (F87, F88). None = a gradino.

    Per una parola lunga 0 o 1 fotogramma la rampa e' ASSENTE e l'effetto e'
    istantaneo; per le altre si accorcia a meta' della durata della parola,
    cosi' l'effetto arriva comunque a valore pieno prima che la parola finisca.
    La divisione e' intera.
    """
    span = int(fine) - int(inizio)
    if span <= 1:
        return None
    return min(max(1, int(massimo)), max(1, span // DIVISORE_SPAN_RAMPA))


def rampa_attiva(rel: float, inizio: int, fine: int, massimo: int) -> float:
    """Rampa SIMMETRICA: entra e esce dentro la parola (F89-F91).

    E' quella di `wordReveal` e `wordSlide`: la tinta si spegne alla fine
    della parola. Fuori dall'intervallo della parola vale zero.
    """
    if rel < inizio or rel >= fine:
        return 0.0
    r = durata_rampa(inizio, fine, massimo)
    if r is None:
        return 1.0
    salita = smoothstep(min(1.0, (float(rel) - inizio) / r))
    discesa = smoothstep(min(1.0, (fine - float(rel)) / r))
    return min(salita, discesa)


def evidenziazione_mantenuta(rel: float, inizio: int, fine: int,
                             inizio_succ: int | None, fine_succ: int | None,
                             massimo: int) -> float:
    """Rampa MANTENUTA: entra sulla parola, esce quando entra la successiva
    (F92-F97).

    E' quella di `highlightPop` e `highlightBlock`, e la differenza dalla
    simmetrica e' tutta qui: l'ultima parola di un blocco resta evidenziata
    fino alla fine della clip, perche' non c'e' una successiva che la spenga.
    """
    if rel < inizio:
        return 0.0
    r = durata_rampa(inizio, fine, massimo)
    salita = 1.0 if r is None else smoothstep(min(1.0, (float(rel) - inizio) / r))
    if inizio_succ is None or rel < inizio_succ:
        return salita
    r_succ = durata_rampa(inizio_succ, fine_succ if fine_succ is not None
                          else inizio_succ, massimo)
    if r_succ is None:
        return 0.0
    discesa = smoothstep(1.0 - min(1.0, (float(rel) - inizio_succ) / r_succ))
    return min(salita, discesa)


def misto(a, b, t: float):
    """Interpolazione lineare per canale, con t agganciato a [0,1] (F98).

    IN sRGB NON LINEARE, sui valori come sono. Nessuna linearizzazione: e' la
    voce 5 delle fondamenta, e vale anche qui dentro.
    """
    t = max(0.0, min(1.0, float(t)))
    if isinstance(a, (int, float)):
        return float(a) + (float(b) - float(a)) * t
    return tuple(float(x) + (float(y) - float(x)) * t for x, y in zip(a, b))


class StatoParola(NamedTuple):
    """Che aspetto ha una parola a un dato fotogramma."""
    opacita: float
    scala: float
    dy: float                     # in CORPI del carattere, non in pixel
    colore: tuple[float, float, float]
    colore_sfondo: tuple[float, float, float, float] | None


def stato_parola(preset: str, rel: float, campata: CampataFrame,
                 campata_succ: CampataFrame | None, mano: int,
                 base: tuple[float, float, float],
                 evidenziazione: tuple[float, float, float] | None) -> StatoParola:
    """Lo stato di UNA parola al fotogramma `rel` (doc 52, 9.4, tabella stati).

    `mano` e' `perWordFrames`. Attenzione al punto che si sbaglia sempre: la
    rampa dei due preset di evidenziazione NON dura `mano`, dura
    `min(mano, 4)` (F100), ulteriormente accorciata a meta' della parola. Col
    valore predefinito 6 la rampa di evidenziazione dura 4 fotogrammi, non 6.
    """
    mano = max(1, int(mano))
    succ_inizio = campata_succ.inizio if campata_succ is not None else None
    succ_fine = campata_succ.fine if campata_succ is not None else None

    if preset in ("wordReveal", "wordSlide"):
        t = progresso(rel, campata.inizio, mano)                       # F99
        if evidenziazione is None:
            colore = base
        else:
            colore = misto(base, evidenziazione,
                           rampa_attiva(rel, campata.inizio, campata.fine, mano))
        dy = AMPIEZZA_WORDSLIDE * (1.0 - t) if preset == "wordSlide" else 0.0
        return StatoParola(t, 1.0, dy, colore, None)

    if preset in ("highlightPop", "highlightBlock"):
        acceso = evidenziazione_mantenuta(                             # F100
            rel, campata.inizio, campata.fine, succ_inizio, succ_fine,
            min(mano, MASSIMO_RAMPA_EVIDENZIAZIONE))
        tinta = evidenziazione if evidenziazione is not None else EVIDENZIAZIONE_PREDEFINITA
        if preset == "highlightPop":
            return StatoParola(1.0, 1.0, 0.0, misto(base, tinta, acceso), None)
        return StatoParola(1.0, 1.0, 0.0, base,
                           (tinta[0], tinta[1], tinta[2], acceso))

    return StatoParola(1.0, 1.0, 0.0, base, None)


class StatoBlocco(NamedTuple):
    """Che aspetto ha l'INTERO blocco a un dato fotogramma."""
    opacita: float
    scala: float
    dy_canvas: float              # in ALTEZZE DI CANVAS, non in corpi


def stato_blocco(preset: str, rel: float, mano: int) -> StatoBlocco:
    """Lo stato dei due preset che animano il blocco intero (doc 52, 9.7).

    `popIn` parte da scala 0,6 e sale di 0,4; `slideUp` entra dal basso di
    0,05 altezze di canvas. Un'unita' sola, nessuno sfasamento: non c'e'
    niente da allineare alle parole.
    """
    mano = max(1, int(mano))
    t = progresso(rel, 0, mano)
    if preset == "popIn":
        return StatoBlocco(t, SCALA_INIZIALE_POPIN + AMPIEZZA_SCALA_POPIN * t, 0.0)
    if preset == "slideUp":
        return StatoBlocco(t, 1.0, AMPIEZZA_SLIDEUP * (1.0 - t))
    return StatoBlocco(1.0, 1.0, 0.0)


def pivot_parola(penna_x: float, penna_y: float, larghezza: float,
                 corpo_px: float) -> tuple[float, float]:
    """Il punto attorno a cui la parola si scala (F102, F103).

    Verticalmente sta a 0,35 CORPI sopra la linea di base: e'
    l'approssimazione del centro ottico (x-height piu' meta' ascendente), non
    il centro geometrico del rettangolo. Scalare attorno al centro geometrico
    fa «saltare» la parola verso il basso, ed e' l'errore che questa costante
    esiste per evitare.
    """
    return (float(penna_x) + float(larghezza) / 2.0,
            float(penna_y) + float(corpo_px) * PIVOT_VERTICALE)


def trasforma_punto(punto: tuple[float, float], pivot: tuple[float, float],
                    scala: float, dy: float, corpo_px: float) -> tuple[float, float]:
    """Scalatura attorno al pivot, POI traslazione non scalata (F104).

    L'ordine conta: se si traslasse prima, lo spostamento verrebbe moltiplicato
    per la scala e una parola che entra con scala 0,6 salirebbe di meno di una
    che entra a scala piena.
    """
    px, py = pivot
    x = float(scala) * (punto[0] - px) + px
    y = float(scala) * (punto[1] - py) + py - float(dy) * float(corpo_px)
    return (x, y)


class BloccoEvidenziazione(NamedTuple):
    x: float
    y: float
    larghezza: float
    altezza: float
    raggio: float


def blocco_evidenziazione(penna_x: float, penna_y: float, larghezza: float,
                          corpo_px: float, ascendente: float | None = None,
                          discendente: float | None = None) -> BloccoEvidenziazione:
    """Il riquadro arrotondato dietro la parola (F105-F113).

    Tutto in FRAZIONI DI CORPO, mai in pixel assoluti: padX 0,18 · padY 0,10 ·
    raggio 0,12. E' cosi' che il riquadro resta proporzionato quando il corpo
    cambia — e il corpo cambia a ogni formato, perche' passa dal fattore del
    testo delle fondamenta.

    Il raggio NON e' limitato a meta' del lato minore, al contrario del
    riquadro di sfondo globale: su una parola cortissima la forma degenera in
    una capsula, che e' un tracciato valido e va lasciato degenerare.

    ATTENZIONE: questa geometria oggi non ha una resa in ASS (serve la penna,
    cioe' le metriche del testo). Sta qui perche' e' la formula giusta e
    perche' il giorno in cui si rasterizza in Python e' gia' scritta.
    """
    corpo = float(corpo_px)
    asc = corpo * ASCENDENTE_RIPIEGO if ascendente is None else float(ascendente)
    disc = corpo * DISCENDENTE_RIPIEGO if discendente is None else abs(float(discendente))
    pad_x = corpo * PAD_X_BLOCCO
    pad_y = corpo * PAD_Y_BLOCCO
    return BloccoEvidenziazione(
        x=float(penna_x) - pad_x,
        y=float(penna_y) - disc - pad_y,
        larghezza=float(larghezza) + 2 * pad_x,
        altezza=asc + disc + 2 * pad_y,
        raggio=corpo * RAGGIO_BLOCCO,
    )


# ===========================================================================
# EMISSIONE ASS
# ===========================================================================

def rgb_da_ass(colore: str) -> tuple[int, int, int]:
    """«&H001A23E2&» -> (226, 35, 26). ASS scrive BGR, non RGB.

    Serve a NON avere una seconda copia del rosso di brand: il valore vive nel
    brand kit in forma ASS, si legge da li' e si riporta in RGB solo per
    poterlo interpolare.
    """
    cifre = str(colore).strip().strip("&").lstrip("Hh")
    cifre = cifre[-6:].rjust(6, "0")
    bb, gg, rr = int(cifre[0:2], 16), int(cifre[2:4], 16), int(cifre[4:6], 16)
    return (rr, gg, bb)


def rgb_da_hex(colore: str) -> tuple[int, int, int]:
    """«#e2231a» -> (226, 35, 26)."""
    c = str(colore).strip().lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def ass_da_rgb(rgb: Sequence[float]) -> str:
    """(226, 35, 26) -> «&H1A23E2&». Arrotondamento di fondazione."""
    r, g, b = (max(0, min(255, fondamenta.arrotonda(v))) for v in rgb[:3])
    return f"&H{b:02X}{g:02X}{r:02X}&"


def ass_da_opacita(opacita: float) -> str:
    """1,0 -> «&H00&» (opaco), 0,0 -> «&HFF&» (trasparente)."""
    a = max(0, min(255, fondamenta.arrotonda((1.0 - float(opacita)) * 255.0)))
    return f"&H{a:02X}&"


def _ms(fotogrammi: float, fps: float) -> int:
    """Fotogrammi -> millisecondi relativi all'inizio della riga.

    Una sola conversione, con l'arrotondamento di fondazione. `\\t` di ASS
    vuole interi in millisecondi e non conosce i fotogrammi.
    """
    return max(0, fondamenta.arrotonda(float(fotogrammi) * 1000.0 / float(fps)))


def _rampa(formato: Callable[[float], str], f_inizio: float, f_durata: float | None,
           fps: float, invertita: bool = False,
           segmenti: int = SEGMENTI_RAMPA) -> str:
    """La rampa attenuata, spezzata in tratti lineari per libass.

    `formato(u)` costruisce il tag per il valore della rampa a `u` in [0,1].
    Con `invertita` la rampa va da 1 a 0 seguendo smoothstep specchiata, che
    e' esattamente la discesa dell'evidenziazione mantenuta (F96).

    Rampa assente (durata None o nulla) = GRADINO: un solo `\\t` di un
    millisecondo, che e' il modo di dire «istantaneo» in ASS.
    """
    if f_durata is None or f_durata <= 0:
        istante = _ms(f_inizio, fps)
        return f"\\t({istante},{istante + 1},{formato(0.0 if invertita else 1.0)})"
    tratti = []
    for k in range(1, int(segmenti) + 1):
        ta = _ms(f_inizio + f_durata * (k - 1) / segmenti, fps)
        tb = _ms(f_inizio + f_durata * k / segmenti, fps)
        if tb <= ta:
            tb = ta + 1
        frazione = k / segmenti
        u = smoothstep(1.0 - frazione) if invertita else smoothstep(frazione)
        tratti.append(f"\\t({ta},{tb},{formato(u)})")
    return "".join(tratti)


def escapa(testo: str) -> str:
    """Le graffe e la barra rovescia sono la sintassi di ASS: via."""
    return str(testo).replace("\\", "").replace("{", "(").replace("}", ")")


def testo_dialogue(preset: str, parole: Sequence[str],
                   campate: tuple[CampataFrame, ...] | None,
                   durata: int, mano: int,
                   base: tuple[float, float, float],
                   evidenziazione: tuple[float, float, float] | None,
                   fps: float = FPS_NOMINALE,
                   altezza: int | None = None,
                   posizione: tuple[int, int] | None = None) -> str:
    """Il campo Text di UN Dialogue: una pagina intera, animata dentro.

    Una riga sola per pagina invece di una per parola. E' il guadagno vero
    della strada ASS: il file crolla di dimensione, e soprattutto non c'e' piu'
    il riflusso della riga a ogni parola — riemettere l'intera pagina con una
    parola ingrandita cambia la larghezza totale e sposta di qualche pixel
    tutte le altre, che e' il tremolio che si vede oggi.

    `parole` e' l'elenco dei testi GIA' trasformati (maiuscolo compreso);
    `campate` porta i tempi ed e' allineata per INDICE, mai per testo.
    Restituisce stringa vuota se non c'e' niente da disegnare.
    """
    if not parole:
        return ""
    preset = str(preset)
    if preset not in PRESET:
        preset = "none"
    # Il degrado si LEGGE dalla tabella invece di essere riscritto qui: se la
    # tabella dice che `wordSlide` esce come `wordReveal`, da questa riga in
    # poi il preset E' `wordReveal`. Cosi' la tabella dichiarata al cliente e
    # il codice che disegna non possono divergere — e non serve un ramo
    # `else` che raccolga gli avanzi.
    voce_degrado = DEGRADAZIONI.get(preset)
    if voce_degrado is not None:
        preset = voce_degrado[0]

    per_indice: dict[int, CampataFrame] = {}
    ordinate: list[CampataFrame] = []
    if campate is not None:
        ordinate = sorted(campate, key=lambda c: (c.inizio, c.indice))
        per_indice = {c.indice: c for c in campate}
    successiva = {c.indice: (ordinate[n + 1] if n + 1 < len(ordinate) else None)
                  for n, c in enumerate(ordinate)}

    prefisso = ""
    if posizione is not None:
        prefisso += f"\\pos({posizione[0]},{posizione[1]})"

    # --- preset di BLOCCO: un solo gruppo di tag davanti a tutta la riga ---
    if preset in PRESET_DI_BLOCCO:
        mano_b = max(1, int(mano))
        if preset == "popIn":
            scala = _rampa(
                lambda u: (f"\\fscx{100 * (SCALA_INIZIALE_POPIN + AMPIEZZA_SCALA_POPIN * u):.1f}"
                           f"\\fscy{100 * (SCALA_INIZIALE_POPIN + AMPIEZZA_SCALA_POPIN * u):.1f}"),
                0, mano_b, fps)
            alfa = _rampa(lambda u: f"\\alpha{ass_da_opacita(u)}", 0, mano_b, fps)
            iniziale = (f"\\fscx{100 * SCALA_INIZIALE_POPIN:.1f}"
                        f"\\fscy{100 * SCALA_INIZIALE_POPIN:.1f}\\alpha&HFF&")
            return "{" + prefisso + iniziale + scala + alfa + "}" + " ".join(
                escapa(p) for p in parole)
        # slideUp: la posizione la muove \move, che e' LINEARE — dichiarato in
        # testa al file. Solo l'opacita' resta attenuata.
        alfa = _rampa(lambda u: f"\\alpha{ass_da_opacita(u)}", 0, mano_b, fps)
        movimento = ""
        if posizione is not None and altezza:
            salto = fondamenta.arrotonda(float(altezza) * AMPIEZZA_SLIDEUP)
            movimento = (f"\\move({posizione[0]},{posizione[1] + salto},"
                         f"{posizione[0]},{posizione[1]},0,{_ms(mano_b, fps)})")
            prefisso = ""   # \move sostituisce \pos, non ci vanno tutti e due
        return "{" + prefisso + movimento + "\\alpha&HFF&" + alfa + "}" + " ".join(
            escapa(p) for p in parole)

    # --- macchina da scrivere: per CARATTERE, curva lineare, niente cursore ---
    if preset == "typewriter":
        pezzi = [prefisso] if prefisso else []
        testo = " ".join(escapa(p) for p in parole)
        n = max(1, len([c for c in testo if not c.isspace()]))
        passo = max(0.0, float(durata)) / n
        fuori = ("{" + "".join(pezzi) + "}") if pezzi else ""
        visti = 0
        for carattere in testo:
            if carattere.isspace():
                fuori += carattere
                continue
            istante = _ms(visti * passo, fps)
            fuori += ("{\\alpha&HFF&\\t(" + str(istante) + "," + str(istante + 1)
                      + ",\\alpha&H00&)}" + carattere)
            visti += 1
        return fuori

    # --- preset PER PAROLA ---
    # `none` arriva fin qui — non e' ne' di blocco ne' macchina da scrivere — e
    # senza questa guardia finiva nel ramo dell'evidenziazione qui sotto: chi
    # chiedeva NESSUNA animazione si vedeva le parole accendersi una a una.
    if preset not in PRESET_PER_PAROLA:
        return ("{" + prefisso + "}" if prefisso else "") + " ".join(
            escapa(p) for p in parole)

    if not per_indice:
        # Nessuna temporizzazione: il blocco resta fermo. E' l'assenza del
        # passo 2 che arriva fin qui, e va disegnata come «niente karaoke»,
        # non inventata con una spartizione uniforme.
        return ("{" + prefisso + "}" if prefisso else "") + " ".join(
            escapa(p) for p in parole)

    fuori = ("{" + prefisso + "}") if prefisso else ""
    mano = max(1, int(mano))
    tinta = evidenziazione
    # I DUE preset a evidenziazione mantenuta, non solo `highlightPop`: e' il
    # raggruppamento che usa gia' `stato_parola`. Lasciare fuori
    # `highlightBlock` significava arrivare a `misto(base, None, u)` ogni volta
    # che il preset veniva chiesto senza tinta esplicita.
    if preset in ("highlightPop", "highlightBlock") and tinta is None:
        tinta = EVIDENZIAZIONE_PREDEFINITA

    for indice, parola in enumerate(parole):
        if indice:
            fuori += " "
        campata = per_indice.get(indice)
        if campata is None:
            fuori += escapa(parola)
            continue
        tag = ""
        # `wordSlide` STA QUI, con `wordReveal`, e non nel ramo di sotto: e' il
        # raggruppamento di `stato_parola` (rampa simmetrica, la tinta si
        # spegne a fine parola). Mandarlo al ramo dell'evidenziazione
        # mantenuta gli dava il colore di un preset che non e' stato chiesto —
        # tinta accesa fino alla parola dopo — e la differenza si vede.
        # Di `wordSlide` si perde lo scorrimento verticale, non il colore:
        # vedi DEGRADAZIONI.
        if preset in ("wordReveal", "wordSlide"):
            tag += "\\alpha&HFF&"
            tag += _rampa(lambda u: f"\\alpha{ass_da_opacita(u)}",
                          campata.inizio, mano, fps)
            if tinta is not None:
                r = durata_rampa(campata.inizio, campata.fine, mano)
                tag += f"\\1c{ass_da_rgb(base)}"
                tag += _rampa(lambda u: f"\\1c{ass_da_rgb(misto(base, tinta, u))}",
                              campata.inizio, r, fps)
                tag += _rampa(lambda u: f"\\1c{ass_da_rgb(misto(base, tinta, u))}",
                              campata.fine - (r or 0), r, fps, invertita=True)
        else:   # highlightPop
            massimo = min(mano, MASSIMO_RAMPA_EVIDENZIAZIONE)
            r = durata_rampa(campata.inizio, campata.fine, massimo)
            tag += f"\\1c{ass_da_rgb(base)}"
            tag += _rampa(lambda u: f"\\1c{ass_da_rgb(misto(base, tinta, u))}",
                          campata.inizio, r, fps)
            prossima = successiva.get(indice)
            if prossima is not None:
                r_succ = durata_rampa(prossima.inizio, prossima.fine, massimo)
                tag += _rampa(lambda u: f"\\1c{ass_da_rgb(misto(base, tinta, u))}",
                              prossima.inizio, r_succ, fps, invertita=True)
            # Senza parola successiva l'ultima resta accesa fino alla fine
            # della pagina: e' la regola dell'evidenziazione mantenuta (F94),
            # non una dimenticanza.
        fuori += "{" + tag + "}" + escapa(parola) + "{\\r}"
    return fuori


def pagina_a_blocco(parole: Sequence[dict], maiuscolo: bool = False) -> tuple[
        str, list[str]]:
    """Da una pagina di parole al testo del blocco e ai suoi pezzi.

    Il maiuscolo si applica QUI, al testo che si vede, e non tocca i testi
    delle campate: e' il motivo per cui le campate si risolvono per indice.
    """
    pezzi = [str(p.get("w", p.get("testo", ""))) for p in parole]
    visibili = [p.upper() for p in pezzi] if maiuscolo else list(pezzi)
    return " ".join(visibili), visibili
