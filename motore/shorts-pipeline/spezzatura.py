"""La catena dei sottotitoli: dove si spezza una riga, e quando sta a schermo.

NON VA COLLEGATO. Misurato, non supposto — vedi docs/spezzatura-verdetto.md.

Le prove ci sono (`prova_spezzatura.py`, 24 verdi) e il confronto sul prima e
dopo pure (`confronta_spezzatura.py`). Il confronto dice che collegare questa
catena PEGGIORA i sottotitoli con lo stile che vendiamo:

    su un trascritto vero, 195 parole, corpo 84 px, larghezza utile 950 px
        oggi                77 pagine, riempimento medio 45%, 0 fuori campo
        con questa catena   95 pagine, riempimento medio 36%, 0 fuori campo

Diciotto pagine in piu', riempite meno: piu' cambi a schermo, cioe' piu'
lampeggio, per risolvere un problema che non abbiamo. NESSUNA pagina esce dal
fotogramma oggi.

Il motivo e' che i tetti del kit sono 4 parole e 18 CARATTERI per pagina: a
corpo 84 px diciotto caratteri non si avvicinano ai 950 disponibili, quindi il
vincolo che morde e' il conteggio e la larghezza non entra mai in gioco. E' lo
stile voluto — una frase alla volta, poche parole grandi.

QUELLO CHE RESTA BUONO E' LA MISURA, e serve come GUARDIA, non come regola di
rottura: la domanda utile non e' «dove spezzo» ma «qualche sottotitolo esce
dal fotogramma?». Prima di alzare i tetti nel brand kit, si lancia
`confronta_spezzatura.py` e si guarda quella riga.

Se un giorno lo stile cambia verso righe lunghe e piene, il verdetto va
rifatto: cambierebbe la premessa, non questo codice.

Quattro pezzi, nell'ordine in cui i dati li attraversano.

    1. MISURA      quanto e' larga davvero una riga, con lo stesso font e la
                   stessa scala con cui libass la disegnera'.
    2. SPEZZATURA  una sola rottura per livello, ricorsiva: prima i confini di
                   frase, poi quelli di proposizione, poi il punto mediano.
    3. PAGINE      dai pezzi di testo alle parole temporizzate che li compongono
                   (il karaoke ha bisogno delle parole, non delle stringhe).
    4. SEQUENZA    ordinamento stabile, sovrapposizioni, buchi corti, tetto di
                   durata, durata minima di lettura.

Il criterio di rottura NON e' un tetto di parole ne' di caratteri: e' la
larghezza renderizzata, misurata con la stessa funzione che poi brucia il testo
nel fotogramma, contro il rapporto massimo delle fondamenta (voce 3, 0,88).
E' l'unico modo perche' il numero che decide dove andare a capo e il numero che
dimensiona il riquadro siano davvero lo stesso numero — e per cui i sottotitoli
non escano mai dallo schermo.

Da dove viene: SPEC/70-TRASCRIZIONE-E-SOTTOTITOLI.md, sezioni 8 (costruzione dei
blocchi), 11.4-11.5 (predicato di adattamento e riquadro), 12 (buchi e
sovrapposizioni), 16 (tabella delle costanti), 21.1 / 21.11 / 21.12 (le parti
che il corpus dichiara mancanti). Dove noi ci discostiamo, il commento lo dice.

Questo modulo NON importa config: prende i numeri da chi lo chiama. Cosi' si
prova senza brand kit, e le costanti di fondazione restano in un posto solo.
"""
from __future__ import annotations

import math
import unicodedata
from pathlib import Path

import fondamenta

# ---------------------------------------------------------------------------
# Gli insiemi di pulizia. Sono DUE e non sono intercambiabili
# ---------------------------------------------------------------------------
#
# SPEC/70 §8.4 lo mette come nota normativa: confonderli cambia il risultato.
# L'insieme "spazi" e' la categoria Unicode Zs piu' la tabulazione, e NON
# contiene gli a capo: un ritorno a carrello ai bordi sopravvive e rende una
# stringa non vuota. Lo spazio unificatore invece viene rimosso da entrambi.
# `str.strip()` di Python toglie tutti e due gli insiemi insieme, quindi qui si
# scrivono per esteso e si passa sempre l'insieme giusto.

SPAZI = "".join(chr(c) for c in (
    0x09, 0x20, 0xA0, 0x1680, *range(0x2000, 0x200B), 0x202F, 0x205F, 0x3000))
SPAZI_E_ACAPO = SPAZI + "".join(chr(c) for c in (
    0x0A, 0x0B, 0x0C, 0x0D, 0x85, 0x2028, 0x2029))

# I due livelli di delimitatore, nell'ordine in cui si tentano (SPEC/70 §8.5,
# costanti 31 e 32 della tabella §16).
DELIMITATORI_FRASE = ".!?"
DELIMITATORI_PROPOSIZIONE = ",;:"

# ---------------------------------------------------------------------------
# I numeri che il corpus NON ha, e che quindi scegliamo noi
# ---------------------------------------------------------------------------
#
# SPEC/70 §21.11 e §21.12 li dichiarano assenti nel sorgente di partenza: non
# c'e' tetto di durata del blocco, non c'e' limite di righe, non c'e' controllo
# di velocita' di lettura. Il corpus dice pero' cosa dicono le linee guida
# tipiche, e questi sono i valori che prendiamo da li'. Sono nostri, e stanno
# scritti qui una volta sola.

# Caratteri al secondo per l'italiano. L'intervallo consigliato e' 15-20: 17 sta
# in mezzo. Serve come PAVIMENTO di leggibilita': un blocco resta a schermo
# almeno il tempo di leggerlo, quando c'e' spazio libero per farlo.
CPS_ITALIANO = 17.0

# Durata minima di un blocco. Il corpus ne ha una di UN FOTOGRAMMA (§16, voce
# 38): a 30 fps sono 33 millesimi, cioe' un lampo che nessuno legge. E' un
# difetto, non una scelta, e non lo ereditiamo.
DURATA_MINIMA_S = 0.4

# Tetto di durata. Il corpus non ne ha (§21.11) e registra che le linee guida
# tipiche stanno sui 6-7 secondi. Oltre, il sottotitolo e' fermo mentre la voce
# e' gia' altrove.
DURATA_MASSIMA_S = 6.0

# Buco massimo colmabile fra due blocchi consecutivi. Questo il corpus ce l'ha:
# 0,5 s di predefinito, dominio 0,0-2,0 (§12.1, voci 43-44). Sotto questa
# soglia il blocco precedente si allunga fino a TOCCARE il successivo, e il
# lampeggio fra una pagina e l'altra sparisce.
BUCO_MASSIMO_S = 0.5

# Righe per blocco. Il corpus non ha il concetto (§21.12). In verticale il
# massimo praticabile e' 2: oltre, il sottotitolo copre l'inquadratura. Le
# nostre pagine sono per costruzione di UNA riga — questo numero serve a
# riconoscere e SEGNALARE il caso in cui una parola sola non ci sta comunque.
RIGHE_MAX = 2

# Il quanto temporale. Non e' il fotogramma: e' il centesimo di secondo, che e'
# la risoluzione con cui i tempi finiscono davvero scritti nel file ASS
# (`h:mm:ss.cc`). Agganciare al fotogramma qui aggiungerebbe una seconda
# quantizzazione sopra a quella del formato, senza guadagnarci niente.
QUANTO_S = 0.01

_EPS = 1e-9


# ===========================================================================
# 1. LA MISURA
# ===========================================================================

class FontNonMisurabile(RuntimeError):
    """Il font del kit non si trova o non si legge: non si tira a indovinare."""


class MisuraTesto:
    """Quanto e' larga una riga, negli stessi pixel in cui libass la disegna.

    LA TRAPPOLA CHE COSTA PIU' DI TUTTE: libass NON scala il corpo su
    `unitsPerEm`. Il `Fontsize` dello stile ASS finisce in una richiesta
    FreeType di tipo REAL_DIM, dove la dimensione chiesta e' l'altezza
    ascendente+discendente della `hhea`, e libass la premoltiplica per
    `(hhea.asc - hhea.desc) / (OS/2.winAsc + OS/2.winDesc)`. I due fattori si
    semplificano e resta:

        pixel per unita' di font  =  corpo / (winAscent + winDescent)

    Sul font del kit (User Font SemiBold, upem 1000, winAsc+winDesc 1250)
    fa 0,0672 invece di 0,084: chi scala per `upem` misura il **25% in piu'**
    del vero. Un predicato costruito su quella misura spezzerebbe le righe un
    quarto troppo presto, e il rapporto 0,88 sarebbe una bugia.

    Verificato contro libass davvero, non a memoria: rendendo `X` e `XX` con
    ffmpeg e sottraendo le due estensioni d'inchiostro si ottiene l'avanzata
    esatta di `X`. Su nove stringhe di prova lo scarto massimo e' 0,98 px, cioe'
    dentro la quantizzazione della misura stessa.

    Cosa questa misura NON contiene, e perche' va bene:

    - **la crenatura.** libass, nella build di ffmpeg che usiamo, non applica la
      funzione `kern` del GPOS: `AV TAVA` misurato da' 298 px e la somma delle
      avanzate 298,23. Se una build diversa la applicasse, le righe uscirebbero
      un filo piu' strette di quanto misurato — cioe' si spezzerebbe un filo
      prima del necessario. E' il verso sicuro.
    - **il contorno** (Outline 5) e **il micro-pop** della parola attiva
      (`\\fscx108`). Insieme valgono al massimo ~30 px su una riga da 950, e il
      margine laterale totale e' 130 px: restano dentro il fotogramma. Il conto
      sta in `margine_residuo_px()`, che lo rifa' invece di fidarsi.
    """

    def __init__(self, percorso: Path, corpo_px: float, spaziatura_px: float = 0.0):
        try:
            from fontTools.ttLib import TTFont
        except ImportError as errore:  # pragma: no cover - dipendenza del venv
            raise FontNonMisurabile(
                "fontTools non e' importabile: la spezzatura dei sottotitoli "
                "misura il testo col font vero e senza non parte. E' nel venv "
                "del worker (tappa 1) insieme a Pillow e opencv."
            ) from errore

        self.percorso = Path(percorso)
        self.corpo_px = float(corpo_px)
        self.spaziatura_px = float(spaziatura_px)
        self.caratteri_mancanti: set[str] = set()

        try:
            font = TTFont(str(self.percorso), lazy=True)
        except Exception as errore:
            raise FontNonMisurabile(
                f"font non leggibile: {self.percorso} ({errore})") from errore

        testa = font["head"]
        hhea = font["hhea"] if "hhea" in font else None
        os2 = font["OS/2"] if "OS/2" in font else None

        alt_hhea = (hhea.ascent - hhea.descent) if hhea else 0
        alt_win = ((os2.usWinAscent + os2.usWinDescent) if os2 else 0)
        if alt_hhea and alt_win:
            unita_per_corpo = alt_win          # il caso normale, e quello del kit
        elif alt_hhea:
            unita_per_corpo = alt_hhea         # senza OS/2 libass non premoltiplica
        else:
            unita_per_corpo = testa.unitsPerEm  # ultimo ripiego
        self.unita_per_corpo = unita_per_corpo
        self.px_per_unita = self.corpo_px / unita_per_corpo

        self._hmtx = font["hmtx"]
        self._cmap = font.getBestCmap()
        ordine = font.getGlyphOrder()
        self._notdef = ".notdef" if ".notdef" in ordine else ordine[0]
        self._cache: dict[str, float] = {}

    # -- costruzione dal kit -------------------------------------------------

    @classmethod
    def dal_kit(cls, cartella_font: Path, family: str, corpo_px: float,
                spaziatura_px: float = 0.0) -> "MisuraTesto":
        """Il file di font che porta ESATTAMENTE il nome di famiglia del kit.

        Non si prende il primo .ttf che capita: `family.txt` e lo stile ASS
        nominano una famiglia, e libass carichera' quella. Misurare un file
        diverso da quello disegnato e' di nuovo il disallineamento fra i due
        lati, solo spostato di un passo.
        """
        cartella = Path(cartella_font)
        if not cartella.is_dir():
            raise FontNonMisurabile(
                f"cartella dei font assente: {cartella}. I sottotitoli si "
                "spezzano sulla larghezza misurata col font vero: senza font "
                "non c'e' misura, e il ripiego silenzioso su Arial resta "
                "vietato. Rigenerala con prepare_fonts.py.")
        candidati = sorted(p for p in cartella.iterdir()
                           if p.suffix.lower() in (".ttf", ".otf"))
        if not candidati:
            raise FontNonMisurabile(
                f"nessun .ttf/.otf in {cartella}: vedi prepare_fonts.py.")
        atteso = _normalizza_family(family)
        visti = []
        for percorso in candidati:
            nomi = _famiglie_del_font(percorso)
            visti.append(f"{percorso.name} -> {', '.join(sorted(nomi)) or '?'}")
            if atteso in {_normalizza_family(n) for n in nomi}:
                return cls(percorso, corpo_px, spaziatura_px)
        raise FontNonMisurabile(
            f"in {cartella} nessun font si chiama '{family}' (quello che lo "
            f"stile ASS chiede a libass). Trovati: {'; '.join(visti)}.")

    # -- la misura vera ------------------------------------------------------

    def larghezza(self, testo: str) -> float:
        """La larghezza di avanzamento della riga, in pixel del render."""
        memorizzata = self._cache.get(testo)
        if memorizzata is not None:
            return memorizzata
        unita = 0
        for carattere in testo:
            nome = self._cmap.get(ord(carattere))
            if nome is None:
                self.caratteri_mancanti.add(carattere)
                nome = self._notdef
            unita += self._hmtx[nome][0]
        valore = unita * self.px_per_unita + self.spaziatura_px * len(testo)
        self._cache[testo] = valore
        return valore

    def carattere_piu_largo(self, alfabeto: str | None = None) -> tuple[str, float]:
        """Il carattere piu' largo fra quelli che possono finire in un sottotitolo.

        Serve al caso peggiore: se la pagina piu' larga POSSIBILE ci sta, non
        serve controllare nessuna pagina vera. Si restringe a un alfabeto
        plausibile invece di scorrere tutta la cmap, perche' un font contiene
        glifi enormi (simboli, ideogrammi) che in un sottotitolo italiano non
        compaiono mai e che renderebbero il caso peggiore assurdo.
        """
        if alfabeto is None:
            alfabeto = (
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "abcdefghijklmnopqrstuvwxyz"
                "0123456789"
                "ÀÁÈÉÌÍÒÓÙÚàáèéìíòóùú"
                " .,;:!?'\"()-–—%€/"
            )
        migliore, larghezza = "", 0.0
        for carattere in alfabeto:
            attuale = self.larghezza(carattere)
            if attuale > larghezza:
                migliore, larghezza = carattere, attuale
        return migliore, larghezza

    def righe_necessarie(self, testo: str, larghezza_max: float) -> int:
        """Quante righe servirebbero a questo testo. 1 = ci sta, come deve."""
        if larghezza_max <= 0:
            return 1
        return max(1, math.ceil(self.larghezza(testo) / larghezza_max - _EPS))


def _normalizza_family(nome: str) -> str:
    return " ".join(str(nome).split()).casefold()


def _famiglie_del_font(percorso: Path) -> set[str]:
    from fontTools.ttLib import TTFont
    try:
        font = TTFont(str(percorso), lazy=True)
        tabella = font["name"]
    except Exception:
        return set()
    fuori = set()
    for voce in tabella.names:
        if voce.nameID in (1, 16):  # famiglia, e famiglia tipografica
            try:
                fuori.add(voce.toUnicode())
            except Exception:
                continue
    return fuori


def tetti_sicuri(misura: "MisuraTesto", tetto_caratteri: int, larghezza_max: float,
                 contorno_px: float = 0.0, fattore_pop: float = 0.0) -> dict:
    """Una condizione SUFFICIENTE di sicurezza. Non necessaria — e va detto.

    Calcola la pagina piu' larga che i tetti PERMETTONO: `tetto_caratteri`
    copie del carattere piu' largo dell'alfabeto plausibile, piu' il contorno
    e il micro-pop.

        'sicuri': True   -> nessuna pagina puo' sforare, MAI, con nessun testo.
                            E' una dimostrazione, e costa una moltiplicazione.
        'sicuri': False  -> NON dimostrato, e quasi sempre NON vuol dire
                            "sfora". Col kit di oggi il caso peggiore e'
                            diciotto segni di percentuale — testo che in un
                            sottotitolo italiano non esiste. Qui si passa a
                            guardare le pagine VERE con confronta_spezzatura.py,
                            che su un girato reale dice 0 pagine fuori campo.

    Non usare 'tetto_massimo_sicuro' per abbassare i tetti: e' il tetto che
    reggerebbe una pagina di soli caratteri larghissimi, e seguirlo
    stringerebbe i sottotitoli per un caso che non capita.

    Nasce dal verdetto di docs/spezzatura-verdetto.md: la catena nuova non si
    collega perche' i tetti in caratteri mordono molto prima della larghezza.
    Quella conclusione vale finche' i tetti restano quelli, e alzarli e' una
    riga nel brand kit. Questa funzione e' il primo filtro che se ne accorge.
    """
    carattere, larghezza_carattere = misura.carattere_piu_largo()
    tetto = max(1, int(tetto_caratteri))
    peggiore = larghezza_carattere * tetto
    peggiore += fattore_pop * larghezza_carattere      # il micro-pop, su una parola
    peggiore += 2 * float(contorno_px)
    return {
        "sicuri": peggiore <= larghezza_max,
        "carattere_piu_largo": carattere,
        "larghezza_carattere_px": round(larghezza_carattere, 2),
        "tetto_caratteri": tetto,
        "caso_peggiore_px": round(peggiore, 2),
        "larghezza_max_px": round(float(larghezza_max), 2),
        # Quanti caratteri di quel carattere ci starebbero: e' il numero da
        # confrontare col tetto quando si vuole alzarlo.
        "tetto_massimo_sicuro": int(
            max(0.0, larghezza_max - 2 * float(contorno_px))
            // max(1e-9, larghezza_carattere * (1 + fattore_pop / max(1, tetto)))
        ),
    }


def margine_residuo_px(larghezza_render: float, larghezza_max: float,
                       contorno_px: float, fattore_pop: float,
                       larghezza_parola_max: float) -> float:
    """Quanto fotogramma avanza a destra e a sinistra nel caso PEGGIORE.

    Il predicato spezza sulla larghezza a riposo; sopra quella il disegno
    aggiunge il contorno su entrambi i lati e il micro-pop della parola attiva.
    Questa funzione rifa' il conto invece di darlo per buono: se torna un numero
    negativo, il sottotitolo esce dal fotogramma e il rapporto va abbassato.
    """
    peggiore = larghezza_max + fattore_pop * larghezza_parola_max + 2 * contorno_px
    return (float(larghezza_render) - peggiore) / 2


# ===========================================================================
# 2. LA SPEZZATURA
# ===========================================================================

def predicato(misura: MisuraTesto, larghezza_max: float,
              tetto_parole: int | None = None,
              tetto_caratteri: int | None = None):
    """Il predicato composito di accettazione (SPEC/70 §8.3).

    Un testo e' accettabile se e solo se valgono TUTTE e tre: ci sta in
    larghezza, non supera il tetto di parole, non supera quello di caratteri.
    I tetti assenti sono neutri; quelli presenti si forzano a un minimo di 1,
    cosi' uno zero non rende il predicato inammissibile (voci 35 e 36).
    """
    parole_max = max(1, int(tetto_parole)) if tetto_parole else None
    caratteri_max = max(1, int(tetto_caratteri)) if tetto_caratteri else None

    def accetta(testo: str) -> bool:
        if misura.larghezza(testo) > larghezza_max:
            return False
        if parole_max is not None and len([p for p in testo.split() if p]) > parole_max:
            return False
        if caratteri_max is not None and len(testo) > caratteri_max:
            return False
        return True

    return accetta


def _rompi_su_delimitatori(testo: str, delimitatori: str) -> list[str] | None:
    """Una rottura sui delimitatori dati. None = non c'e' punto di rottura.

    Il taglio cade DOPO il delimitatore, quindi la punteggiatura resta attaccata
    al pezzo che la precede — e solo se il carattere successivo e' uno SPAZIO
    SEMPLICE o la fine della stringa. E' quella condizione, e solo quella, che
    salva `U.S.` dal diventare `U.` + `S.` e `3.14` dal diventare `3.` + `14`.
    Il controllo e' sullo spazio semplice e NON sulla classe degli spazi: uno
    spazio unificatore dopo il punto non apre un confine (SPEC/70 §8.5).
    """
    pezzi: list[str] = []
    buffer: list[str] = []
    ultimo = len(testo) - 1
    for indice, carattere in enumerate(testo):
        buffer.append(carattere)
        successivo = testo[indice + 1] if indice < ultimo else None
        confine = successivo is None or successivo == " "
        if carattere in delimitatori and confine:
            pezzo = "".join(buffer).strip(SPAZI)
            if pezzo:
                pezzi.append(pezzo)
            buffer = []
    coda = "".join(buffer).strip(SPAZI)
    if coda:
        pezzi.append(coda)
    return pezzi if len(pezzi) > 1 else None


def _rompi_a_meta(testo: str) -> list[str] | None:
    """Il punto mediano fra le parole. None = una parola sola, non si spezza.

    L'indice e' il numero di parole diviso 2, divisione INTERA: con 5 parole
    il pezzo sinistro ne ha 2 e il destro 3 — il sinistro e' il piu' corto.
    """
    parole = [p for p in testo.split(" ") if p]
    if len(parole) <= 1:
        return None
    meta = len(parole) // 2
    return [" ".join(parole[:meta]), " ".join(parole[meta:])]


def spezza(testo: str, accetta) -> list[str]:
    """Suddivisione ricorsiva: UNA sola rottura per livello (SPEC/70 §8.4).

    1. si ripulisce con l'insieme "spazi" — non con "spazi e a capo";
    2. se il predicato accetta il testo intero, un pezzo solo: caso base;
    3. altrimenti una sola rottura, coi tre livelli di priorita' in ordine;
    4. se la rottura non ha prodotto niente, si restituisce il testo COSI'
       COM'E' anche se eccede: una parola piu' lunga del limite non si tronca
       mai — meglio un blocco troppo largo che una parola tagliata a meta';
    5. altrimenti si ricorre su ciascun pezzo e si concatena in ordine.

    Termina sempre: ogni rottura riuscita da' almeno due pezzi strettamente piu'
    corti, e il caso a un pezzo si ferma subito.
    """
    pulito = testo.strip(SPAZI)
    if not pulito:
        return []
    if accetta(pulito):
        return [pulito]
    pezzi = (_rompi_su_delimitatori(pulito, DELIMITATORI_FRASE)
             or _rompi_su_delimitatori(pulito, DELIMITATORI_PROPOSIZIONE)
             or _rompi_a_meta(pulito))
    if not pezzi:
        return [pulito]
    fuori: list[str] = []
    for pezzo in pezzi:
        fuori.extend(spezza(pezzo, accetta))
    return fuori


# ===========================================================================
# 3. DAI PEZZI DI TESTO ALLE PAROLE TEMPORIZZATE
# ===========================================================================

def _alfanumerici(testo: str) -> int:
    """Quante lettere e cifre. Punteggiatura, spazi e simboli non contano.

    E' l'invariante che allinea i pezzi alle parole anche quando i due
    raggruppamenti non coincidono (SPEC/70 §8.7): la sequenza dei caratteri
    alfanumerici e' la stessa da tutte e due le parti, comunque la si spezzi.
    """
    return sum(1 for c in testo if unicodedata.category(c)[0] in ("L", "N"))


def _riallinea(pezzi: list[str], parole: list[dict], testo_di) -> list[list[dict]] | None:
    """A ogni pezzo le parole che lo compongono. None = copertura incompleta.

    Consumo greedy sul conteggio degli alfanumerici, come SPEC/70 §8.7, MENO
    i suoi due difetti dichiarati: li' un pezzo con zero alfanumerici — per
    esempio un `...` isolato da una rottura — fa fallire la temporizzazione
    dell'INTERO segmento e azzera tutte le campate di parola, non solo la sua.
    Qui un pezzo del genere consuma la parola che gli spetta e basta.
    """
    corse = [(parola, _alfanumerici(testo_di(parola))) for parola in parole]
    fuori: list[list[dict]] = []
    indice = 0
    for pezzo in pezzi:
        voluto = _alfanumerici(pezzo)
        prese: list[dict] = []
        accumulato = 0
        while indice < len(corse) and (accumulato < voluto or not prese):
            parola, quante = corse[indice]
            prese.append(parola)
            accumulato += quante
            indice += 1
            if voluto == 0:  # pezzo senza alfanumerici: una parola e si esce
                break
        if not prese:
            return None
        fuori.append(prese)
    if len(fuori) != len(pezzi) or indice != len(corse):
        return None  # sono avanzate parole, o ne sono mancate: non si indovina
    return fuori


def _greedy_larghezza(parole: list[dict], accetta, testo_di) -> list[list[dict]]:
    """Il ripiego: si accumulano parole finche' la riga ci sta.

    Non produce le rotture belle (non conosce la punteggiatura), ma non perde
    mai una parola e non esce mai dallo schermo. Serve solo se il riallineamento
    fallisce, cosa che con parole giuntate da spazi singoli non dovrebbe
    succedere — e se succede, chi chiama lo dice invece di far finta.
    """
    pagine: list[list[dict]] = []
    corrente: list[dict] = []
    for parola in parole:
        candidata = corrente + [parola]
        testo = " ".join(testo_di(p) for p in candidata)
        if corrente and not accetta(testo):
            pagine.append(corrente)
            corrente = [parola]
        else:
            corrente = candidata
    if corrente:
        pagine.append(corrente)
    return pagine


def segmenta(parole: list[dict], *, gap_s: float, hook_fino_a_s: float | None,
             inizio_clip_s: float = 0.0) -> list[list[dict]]:
    """I confini DURI, quelli che non dipendono dalla larghezza.

    Tre, e nessuno e' negoziabile:

    - **la pausa**: oltre `gap_s` fra la fine di una parola e l'inizio della
      successiva il discorso si e' fermato, e la pagina si chiude;
    - **il taglio**: due parole ai due lati di un buco tolto non vanno sulla
      stessa pagina, anche quando i tempi si toccano — scriverebbero a schermo
      una frase che nel video non c'e';
    - **la soglia dell'aggancio**: dentro i primi secondi le pagine sono piu'
      strette (piu' scatti = piu' ritenzione, HOOK-GUIDE.md). Facendone un
      confine duro nessuna pagina sta a cavallo della soglia, e la regola non
      cambia mai a meta' pagina.
    """
    segmenti: list[list[dict]] = []
    corrente: list[dict] = []
    for parola in parole:
        if corrente:
            precedente = corrente[-1]
            pausa = parola["start"] - precedente["end"] > gap_s
            cambio_pezzo = precedente.get("pezzo") != parola.get("pezzo")
            soglia = (hook_fino_a_s is not None
                      and (precedente["start"] - inizio_clip_s) < hook_fino_a_s
                      <= (parola["start"] - inizio_clip_s))
            if pausa or cambio_pezzo or soglia:
                segmenti.append(corrente)
                corrente = []
        corrente.append(parola)
    if corrente:
        segmenti.append(corrente)
    return segmenti


def pagine_da_parole(parole: list[dict], misura: MisuraTesto, larghezza_max: float, *,
                     gap_s: float, hook_fino_a_s: float | None = None,
                     parole_hook: int | None = None,
                     tetto_parole: int | None = None,
                     tetto_caratteri: int | None = None,
                     inizio_clip_s: float = 0.0,
                     testo_di=lambda p: p["w"]) -> tuple[list[list[dict]], list[str]]:
    """Le pagine di sottotitolo, come elenchi delle parole che le compongono.

    Torna `(pagine, avvisi)`. Gli avvisi non fanno fallire niente: dicono i due
    casi che vale la pena sapere — una riga che non ci sta comunque perche' e'
    una parola sola troppo lunga, e un riallineamento fallito che ha costretto
    al ripiego greedy.
    """
    avvisi: list[str] = []
    pagine: list[list[dict]] = []
    for segmento in segmenta(parole, gap_s=gap_s, hook_fino_a_s=hook_fino_a_s,
                             inizio_clip_s=inizio_clip_s):
        dentro_hook = (hook_fino_a_s is not None
                       and (segmento[0]["start"] - inizio_clip_s) < hook_fino_a_s)
        limite_parole = parole_hook if (dentro_hook and parole_hook) else tetto_parole
        accetta = predicato(misura, larghezza_max, limite_parole, tetto_caratteri)

        testo = " ".join(testo_di(parola) for parola in segmento)
        pezzi = spezza(testo, accetta)
        gruppi = _riallinea(pezzi, segmento, testo_di) if pezzi else []
        if gruppi is None:
            avvisi.append(
                f"riallineamento fallito su «{testo[:60]}»: pagine costruite "
                "col ripiego greedy, senza rotture sulla punteggiatura")
            gruppi = _greedy_larghezza(segmento, accetta, testo_di)
        pagine.extend(gruppi)

    for pagina in pagine:
        testo = " ".join(testo_di(parola) for parola in pagina)
        righe = misura.righe_necessarie(testo, larghezza_max)
        if righe > 1:
            avvisi.append(
                f"«{testo}» misura {misura.larghezza(testo):.0f} px contro un "
                f"limite di {larghezza_max:.0f}: servirebbero {righe} righe"
                + (" (oltre il massimo di "
                   f"{RIGHE_MAX})" if righe > RIGHE_MAX else "")
                + ". E' una parola sola piu' lunga del limite: non si tronca.")
    if misura.caratteri_mancanti:
        mancanti = "".join(sorted(misura.caratteri_mancanti))
        avvisi.append(
            f"caratteri assenti dal font e misurati col glifo di ripiego: "
            f"«{mancanti}». La larghezza vera la decidera' il font di sistema "
            "che libass mettera' al loro posto.")
    return pagine, avvisi


# ===========================================================================
# 4. LA SEQUENZA
# ===========================================================================

def _sposta_preservando_fine(blocco: dict, nuovo_inizio: float) -> None:
    """Sposta in avanti l'inizio tenendo ferma la fine (SPEC/70 §12.5)."""
    fine_originale = blocco["fine"]
    blocco["inizio"] = nuovo_inizio
    blocco["fine"] = (fine_originale if fine_originale > nuovo_inizio + _EPS
                      else nuovo_inizio + QUANTO_S)


def pulisci_sequenza(blocchi: list[dict], *,
                     buco_max_s: float = BUCO_MASSIMO_S,
                     durata_min_s: float = DURATA_MINIMA_S,
                     durata_max_s: float = DURATA_MASSIMA_S,
                     cps: float = CPS_ITALIANO,
                     fine_clip_s: float | None = None) -> list[dict]:
    """Ordina, risolve le sovrapposizioni, chiude i buchi corti, poi i tetti.

    L'ORDINE E' OBBLIGATO (SPEC/70 §12.3): prima le collisioni, poi i buchi.
    Al contrario, estendere per primo creerebbe sovrapposizioni che poi
    andrebbero ri-risolte, e la seconda passata cancellerebbe le decisioni della
    prima.

    Dove facciamo meglio del corpus. Il corpus dichiara (§12.4, nota comune ai
    tre casi) che la risoluzione guarda soltanto la COPPIA ADIACENTE, e che con
    blocchi lunghi e ravvicinati restano sovrapposizioni non corrette. Qui il
    confronto e' sempre contro l'ultimo blocco GIA' EMESSO, non contro il
    vicino grezzo: cosi' uno spostamento in avanti che invade il blocco dopo
    viene visto al passo successivo invece di passare inosservato. In coda a
    ogni passo c'e' un aggancio duro che rende la sovrapposizione residua
    impossibile per costruzione, non improbabile.

    L'ordinamento e' STABILE per (inizio, indice d'ingresso): a parita' di
    inizio vince l'ordine di trascrizione, che e' quello in cui le parole sono
    state dette.
    """
    if not blocchi:
        return []

    ordinati = sorted(range(len(blocchi)),
                      key=lambda i: (blocchi[i]["inizio"], i))
    lavoro = []
    for indice in ordinati:
        blocco = dict(blocchi[indice])
        blocco["_durata_originale"] = blocco["fine"] - blocco["inizio"]
        lavoro.append(blocco)

    # --- passata 1: le sovrapposizioni, tre casi mutuamente esclusivi -------
    fuori: list[dict] = []
    for corrente in lavoro:
        if fuori:
            precedente = fuori[-1]
            if corrente["inizio"] < precedente["fine"] - _EPS:
                sovrapposizione = precedente["fine"] - corrente["inizio"]
                if corrente["inizio"] <= precedente["inizio"] + _EPS:
                    # CASO 1 — i due inizi collassano, o l'ordine di
                    # trascrizione contraddice i tempi. Il precedente si riduce
                    # al minimo e il corrente parte da li', tenendo la sua fine.
                    precedente["fine"] = precedente["inizio"] + QUANTO_S
                    _sposta_preservando_fine(corrente, precedente["fine"])
                elif (sovrapposizione <= QUANTO_S + _EPS
                      and precedente["_durata_originale"] < corrente["_durata_originale"]):
                    # CASO 2 — collisione da arrotondamento di un quanto solo:
                    # la "possiede" il blocco piu' corto, che accorciandosi
                    # perderebbe proporzionalmente di piu'. Il precedente non si
                    # tocca, si sposta il corrente.
                    _sposta_preservando_fine(corrente, precedente["fine"])
                else:
                    # CASO 3 — tutto il resto: il precedente si accorcia fino a
                    # toccare l'inizio del corrente, che e' autorevole.
                    if corrente["inizio"] > precedente["inizio"] + _EPS:
                        precedente["fine"] = corrente["inizio"]
            # l'aggancio duro: dopo i tre casi nessun blocco puo' iniziare prima
            # della fine di quello prima. E' l'invariante, non una speranza.
            if corrente["inizio"] < precedente["fine"]:
                corrente["inizio"] = precedente["fine"]
            if corrente["fine"] < corrente["inizio"] + QUANTO_S:
                corrente["fine"] = corrente["inizio"] + QUANTO_S
        fuori.append(corrente)

    # --- passata 2: i buchi corti si chiudono -------------------------------
    for prima, dopo in zip(fuori, fuori[1:]):
        buco = dopo["inizio"] - prima["fine"]
        if 0 < buco <= buco_max_s + _EPS:
            prima["fine"] = dopo["inizio"]

    # --- passata 3: il tetto di durata --------------------------------------
    for blocco in fuori:
        if blocco["fine"] - blocco["inizio"] > durata_max_s:
            blocco["fine"] = blocco["inizio"] + durata_max_s

    # --- passata 4: il pavimento di leggibilita' ----------------------------
    # Un blocco resta a schermo almeno il tempo di leggerlo: il piu' grande fra
    # la durata minima e caratteri/CPS. Si allunga SOLO dentro tempo libero —
    # mai fino a sovrapporsi al successivo, che qui e' gia' autorevole.
    for indice, blocco in enumerate(fuori):
        caratteri = len(blocco.get("testo") or "")
        voluta = min(max(durata_min_s, caratteri / cps if cps > 0 else 0.0),
                     durata_max_s)
        if indice + 1 < len(fuori):
            limite = fuori[indice + 1]["inizio"]
        elif fine_clip_s is not None:
            limite = fine_clip_s
        else:
            limite = math.inf
        blocco["fine"] = max(blocco["fine"], min(blocco["inizio"] + voluta, limite))

    for blocco in fuori:
        blocco.pop("_durata_originale", None)
        blocco["inizio"] = fondamenta.arrotonda_decimale(blocco["inizio"], 3)
        blocco["fine"] = fondamenta.arrotonda_decimale(blocco["fine"], 3)
    return fuori


def sovrapposizioni(blocchi: list[dict]) -> list[tuple[int, int]]:
    """Le coppie che si sovrappongono ancora. Vuota = la sequenza e' pulita.

    Non guarda solo le coppie adiacenti: e' proprio il limite che il corpus
    dichiara, ed e' quello che questa funzione esiste per smentire.
    """
    fuori = []
    for i in range(len(blocchi)):
        for j in range(i + 1, len(blocchi)):
            a, b = blocchi[i], blocchi[j]
            if min(a["fine"], b["fine"]) - max(a["inizio"], b["inizio"]) > _EPS:
                fuori.append((i, j))
    return fuori
