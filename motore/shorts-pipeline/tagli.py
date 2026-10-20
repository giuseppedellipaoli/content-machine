"""Tagli DENTRO una clip: i buchi tolti dal parlato e il ribasamento dei tempi.

PERCHE' ESISTE
Le correzioni per clip (correzioni.py) spostano i BORDI del taglio: l'attacco,
lo stacco, il ritaglio verticale. Non sanno togliere niente in mezzo. «Leva
quella pausa», «leva quel "cioe'"» chiedono un'altra cosa: che un pezzo di
girato sparisca DA DENTRO lo short e che quello che viene dopo si richiuda.

Da quel momento una clip non e' piu' una finestra sola sul girato: e' un
ELENCO DI PEZZI con dei buchi in mezzo. E tutto quello che porta un tempo
dentro quella clip — le parole dei sottotitoli, le sillabe del karaoke, gli
eventi grafici del piano overlay — sta a un secondo diverso da prima.

QUESTO E' IL PEZZO CHE IL PROGETTO DA CUI ARRIVA LA FUNZIONE NON HA MAI
RISOLTO. Nelle loro specifiche il ribasamento dei tempi di parola dopo un
taglio e' un difetto DICHIARATO: tagliano e i tempi restano quelli di prima.
Non c'e' un esempio da copiare. Qui il ribasamento e' il centro del modulo,
non un dettaglio a valle: chiunque converta un tempo passa da queste
funzioni, e le prove in prova_tagli.py coprono i quattro casi che lo
rompono (una parola tolta in mezzo, due tagli di fila, un taglio dentro una
sillaba del karaoke, un taglio in testa e uno in coda).

DOVE VIVE IL FILE
Nel workspace locale, accanto a correzioni.json:

    build/tagli.json

Il worker lo scarica in build/tagli.json e lo passa a render.py con --tagli.
Se il file non c'e', non cambia niente: si fa esattamente quello che si
faceva prima, con gli stessi numeri e lo stesso identico video.

FORMATO

    {
      "versione": 1,
      "clip": {
        "short_02_i-tre-errori": {
          "buchi": [
            {"inizio": 12.34, "fine": 13.02,
             "motivo": "silenzio", "verifica_livello": true},
            {"inizio": 20.10, "fine": 21.44,
             "motivo": "parole", "parole": [34, 41], "verifica_livello": false}
          ],
          "firma_trascritto": "d61f777c3c084337",
          "soglia": {...},
          "aggiornata_il": "2026-08-17T..."
        }
      }
    }

I BUCHI SONO IN SECONDI DEL GIRATO, non della clip. E' la decisione che regge
tutto il resto, e il motivo e' lo stesso per cui gli indici di parola sono
globali (api/src/montaggio.js): un buco in secondi della clip si sposterebbe
tutto appena qualcuno chiede pad_inizio_s -2, e i tagli ESEGUONO senza
chiedere conferma. In secondi del girato un buco resta dov'e' anche se la
clip viene allungata, accorciata o rimontata — e combacia con i tempi delle
parole, che stanno nella stessa scala.

PERCHE' UN FILE SUO E NON UN CAMPO DI correzioni.json
Perche' correzioni.json ha una lista CHIUSA di campi (correzioni.py, _voce:
un campo in piu' fa fallire il passo) e una versione che dichiara «i tre
numeri sono scostamenti». Infilarci dentro i buchi avrebbe voluto dire o
allargare quella lista in tre implementazioni, o alzare la versione — che in
quel file vuol dire «i numeri di prima adesso significano un'altra cosa», e
non e' vero. Due file separati tengono anche due annullamenti separati:
«rimetti il riquadro com'era» non deve rimettere dentro le pause tolte.

IL LIVELLO SI VERIFICA QUI, NON A MONTE
Un buco con "verifica_livello": true e' un CANDIDATO: l'ha proposto chi
guardava solo il trascritto (l'API, che non ha ffmpeg), e qui si misura
davvero il livello audio sotto quel tratto prima di toglierlo. Sotto una
pausa fra due frasi puo' esserci un letto musicale o un ambiente rumoroso, e
in quel caso il tratto NON e' tempo morto: si lascia dov'e' e si dice. La
soglia e' RELATIVA al livello del parlato di quella registrazione, mai
assoluta: vedi silenzi.py. Un buco nato da «togli le parole dalla 34 alla
41» ha invece "verifica_livello": false e non si veta: il cliente ha nominato
le parole, e la musica sotto non e' una ragione per tenerle.

LA FIRMA DEL TRASCRITTO
'firma_trascritto' e' l'impronta della numerazione delle parole al momento in
cui i buchi sono stati calcolati (stessa funzione di api/src/montaggio.js,
firmaNumerazione: conteggio + tempi d'attacco). Se il girato viene
ritrascritto, quella firma cambia e gli indici di parola di quel taglio non
indicano piu' quelle parole: il passo si FERMA con un messaggio esplicito
invece di tagliare la frase sbagliata.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import fondamenta
from correzioni import normalizza_nome

# La versione del formato che questa pipeline sa leggere. Sale insieme al
# SIGNIFICATO dei numeri, non insieme al codice. Specchio: VERSIONE_TAGLI in
# api/src/tagli.js.
VERSIONE_ATTESA = 1

# I campi ammessi in un buco, lista chiusa come in correzioni.py: un campo
# battuto storto e' un errore, non un silenzio.
CAMPI_BUCO = ("inizio", "fine", "motivo", "parole", "verifica_livello")

# I campi ammessi in una voce di clip.
CAMPI_VOCE = ("buchi", "firma_trascritto", "soglia", "aggiornata_il")

# I motivi ammessi. Non e' decorazione: 'silenzio' e' cio' che si puo' vetare
# misurando il livello, 'parole' e' cio' che non si veta mai.
MOTIVI = ("silenzio", "parole")

# Tolleranza sui confronti fra secondi: sotto il millesimo si sta discutendo
# dell'arrotondamento, non del taglio. Stesso ruolo di EPS in correzioni.py.
EPS = 1e-9

# Quanto puo' durare al minimo un pezzo che resta. Sotto i due fotogrammi a
# 25 fps non e' piu' un pezzo di video: e' un artefatto che ffmpeg concatena
# producendo uno scatto. Un pezzo piu' corto di cosi' si assorbe nel buco
# accanto invece di finire nel montaggio.
PEZZO_MINIMO_S = 0.08

# Una parola la cui parte VISIBILE scende sotto questa soglia non entra nei
# sottotitoli. Non e' un giudizio di stile: il karaoke costruisce una riga di
# dialogo per parola, e una riga da 20 millisecondi lampeggia e basta —
# peggio, spinge in avanti tutte quelle dopo (build_ass tiene prev_end
# monotono). L'indice della parola NON sparisce: la numerazione sta nel
# trascritto e non si tocca. Sparisce la sua riga di sottotitolo.
PAROLA_VISIBILE_MINIMA_S = 0.05


class TaglioNonValido(ValueError):
    """Il file dei tagli e' scritto male: ci si ferma, non si indovina."""


# ------------------------------------------------------------------ lettura

def vuota() -> dict:
    """La voce che non taglia niente."""
    return {"buchi": [], "firma_trascritto": None, "soglia": None}


def _buco(nome: str, grezzo) -> dict:
    if not isinstance(grezzo, dict):
        raise TaglioNonValido(
            f"tagli: un buco di '{nome}' deve essere un oggetto con inizio e fine, "
            f"non {type(grezzo).__name__}")
    ignoti = sorted(k for k in grezzo if k not in CAMPI_BUCO)
    if ignoti:
        raise TaglioNonValido(
            f"tagli: un buco di '{nome}' ha campi che non esistono: {', '.join(ignoti)}. "
            f"Ammessi: {', '.join(CAMPI_BUCO)}")
    fuori = {}
    for campo in ("inizio", "fine"):
        valore = grezzo.get(campo)
        # bool e' sottoclasse di int in Python: True passerebbe per 1
        if isinstance(valore, bool) or not isinstance(valore, (int, float)):
            raise TaglioNonValido(
                f"tagli: '{nome}': '{campo}' deve essere un numero di secondi del "
                f"GIRATO, non {type(valore).__name__}")
        if not math.isfinite(float(valore)):
            raise TaglioNonValido(f"tagli: '{nome}': '{campo}' non e' un numero finito")
        fuori[campo] = float(valore)
    if fuori["fine"] <= fuori["inizio"] + EPS:
        raise TaglioNonValido(
            f"tagli: '{nome}': un buco deve finire dopo che comincia "
            f"({fuori['inizio']} -> {fuori['fine']})")
    if fuori["inizio"] < -EPS:
        raise TaglioNonValido(
            f"tagli: '{nome}': un buco non puo' cominciare prima di 0 "
            f"(i secondi sono quelli del girato)")
    motivo = grezzo.get("motivo", "silenzio")
    if motivo not in MOTIVI:
        raise TaglioNonValido(
            f"tagli: '{nome}': motivo {motivo!r} sconosciuto. Ammessi: {', '.join(MOTIVI)}")
    fuori["motivo"] = motivo
    parole = grezzo.get("parole")
    if parole is not None:
        if (not isinstance(parole, (list, tuple)) or len(parole) != 2
                or any(isinstance(p, bool) or not isinstance(p, int) for p in parole)):
            raise TaglioNonValido(
                f"tagli: '{nome}': 'parole' deve essere [prima, ultima], due indici interi")
        if parole[1] < parole[0]:
            raise TaglioNonValido(
                f"tagli: '{nome}': 'parole' rovesciato ({parole[0]} > {parole[1]})")
        fuori["parole"] = [int(parole[0]), int(parole[1])]
    else:
        fuori["parole"] = None
    verifica = grezzo.get("verifica_livello")
    if verifica is None:
        # Il valore di serie dipende dal motivo, e non e' un ripiego: un buco
        # nato da un silenzio si verifica, uno nato da parole nominate no.
        verifica = motivo == "silenzio"
    if not isinstance(verifica, bool):
        raise TaglioNonValido(
            f"tagli: '{nome}': 'verifica_livello' deve essere true o false")
    fuori["verifica_livello"] = verifica
    return fuori


def _voce(nome: str, grezza) -> dict:
    if not isinstance(grezza, dict):
        raise TaglioNonValido(
            f"tagli: la voce '{nome}' deve essere un oggetto con 'buchi', "
            f"non {type(grezza).__name__}")
    ignoti = sorted(k for k in grezza if k not in CAMPI_VOCE)
    if ignoti:
        raise TaglioNonValido(
            f"tagli: la voce '{nome}' ha campi che non esistono: {', '.join(ignoti)}. "
            f"Ammessi: {', '.join(CAMPI_VOCE)}")
    buchi = grezza.get("buchi", [])
    if not isinstance(buchi, list):
        raise TaglioNonValido(f"tagli: '{nome}': 'buchi' deve essere una lista")
    firma = grezza.get("firma_trascritto")
    if firma is not None and not isinstance(firma, str):
        raise TaglioNonValido(f"tagli: '{nome}': 'firma_trascritto' deve essere una stringa")
    return {
        "buchi": [_buco(nome, b) for b in buchi],
        "firma_trascritto": firma,
        "soglia": grezza.get("soglia"),
    }


def leggi(percorso) -> dict[str, dict]:
    """Legge il file dei tagli. File assente = nessun taglio ({})."""
    p = Path(percorso)
    if not p.exists():
        return {}
    testo = p.read_text(encoding="utf-8").strip()
    if testo == "":
        return {}
    try:
        doc = json.loads(testo)
    except json.JSONDecodeError as errore:
        raise TaglioNonValido(f"tagli: '{p}' non e' JSON valido: {errore}") from errore
    if not isinstance(doc, dict):
        raise TaglioNonValido(
            f"tagli: '{p}' deve contenere un oggetto, non {type(doc).__name__}")
    if "versione" not in doc:
        raise TaglioNonValido(
            f"tagli: '{p}' non dichiara il campo 'versione'. Questa pipeline legge "
            f"la {VERSIONE_ATTESA}, dove i buchi sono intervalli in SECONDI DEL "
            f"GIRATO tolti da dentro la clip. Un file che non dice con quale regola "
            f"e' stato scritto non si interpreta: aggiungi \"versione\": {VERSIONE_ATTESA}")
    if doc["versione"] != VERSIONE_ATTESA:
        raise TaglioNonValido(
            f"tagli: '{p}' e' di versione {doc['versione']!r}, questa pipeline legge "
            f"la {VERSIONE_ATTESA}")
    voci = doc.get("clip", {})
    if not isinstance(voci, dict):
        raise TaglioNonValido(
            "tagli: 'clip' deve essere un oggetto {nome_clip: taglio}")
    fuori: dict[str, dict] = {}
    for nome, voce in voci.items():
        chiave = normalizza_nome(nome)
        if chiave == "":
            raise TaglioNonValido(f"tagli: nome di clip vuoto ({nome!r})")
        if chiave in fuori:
            raise TaglioNonValido(
                f"tagli: la clip '{chiave}' compare due volte (nomi diversi, stessa "
                "clip): tienine una sola, o non si sa quale vince")
        fuori[chiave] = _voce(chiave, voce)
    return fuori


# ------------------------------------------------------------------- i pezzi

def unisci_buchi(buchi: list[dict]) -> list[dict]:
    """Buchi ordinati e fusi: due che si toccano sono un buco solo.

    Serve prima di qualunque conto. Due buchi sovrapposti — «togli i silenzi»
    e poi «togli quella frase», che il silenzio lo conteneva — darebbero un
    pezzo di durata negativa, e il video uscirebbe piu' corto di quanto si e'
    tolto senza che nessuno sappia perche'.

    'motivo' e 'verifica_livello' della fusione: se anche un solo pezzo del
    buco fuso non va verificato, non si verifica il tutto. E' la direzione
    prudente per il cliente — ha nominato delle parole, quelle vanno via.
    """
    ordinati = sorted(buchi, key=lambda b: (b["inizio"], b["fine"]))
    fusi: list[dict] = []
    for buco in ordinati:
        if fusi and buco["inizio"] <= fusi[-1]["fine"] + EPS:
            ultimo = fusi[-1]
            ultimo["fine"] = max(ultimo["fine"], buco["fine"])
            ultimo["verifica_livello"] = (
                ultimo["verifica_livello"] and buco.get("verifica_livello", True))
            if ultimo["motivo"] != buco.get("motivo", ultimo["motivo"]):
                ultimo["motivo"] = "parole" if "parole" in (
                    ultimo["motivo"], buco.get("motivo")) else ultimo["motivo"]
            continue
        fusi.append({
            "inizio": buco["inizio"],
            "fine": buco["fine"],
            "motivo": buco.get("motivo", "silenzio"),
            "parole": buco.get("parole"),
            "verifica_livello": buco.get("verifica_livello", True),
        })
    return fusi


def pezzi_da_buchi(inizio: float, fine: float, buchi: list[dict]) -> list[dict]:
    """I tratti di girato che RESTANO dentro la clip, in ordine.

    Ogni pezzo porta 'offset': quanto dura la clip PRIMA di lui. E' il numero
    che ribasa tutti i tempi a valle, ed e' l'unico posto in cui viene
    calcolato — chi ne fa una seconda copia prima o poi la fa diversa.

    Senza buchi torna un pezzo solo, [inizio, fine), offset 0: identico a
    quello che il montaggio ha sempre fatto.

    Un pezzo piu' corto di PEZZO_MINIMO_S non entra: si perde nel buco che lo
    circonda invece di produrre uno scatto nel concatenato.

    OGNI PEZZO DICHIARA QUALI DEI SUOI DUE BORDI SONO TAGLI ('taglia_inizio',
    'taglia_fine') e quali sono invece il bordo esterno della clip. Non e' un
    dettaglio contabile: un bordo di TAGLIO stringe le parole che ci cadono
    sopra (una sillaba mezza tolta non puo' restare accesa nel karaoke), un
    bordo ESTERNO no — li' il comportamento resta quello di sempre, dove una
    parola a cavallo dell'attacco tiene i suoi tempi e ci pensa ass_time a non
    andare sotto zero. Distinguerli e' cio' che rende una clip senza buchi
    identica fotogramma per fotogramma a come era prima di questo file.
    """
    inizio = float(inizio)
    fine = float(fine)
    pezzi: list[dict] = []
    corrente = inizio
    tagliato_a_sinistra = False
    for buco in unisci_buchi(buchi):
        # il buco si INTERSECA con la finestra: un buco fuori dal taglio non
        # toglie niente, e un buco a cavallo del bordo toglie solo la sua
        # parte dentro
        b0 = max(inizio, buco["inizio"])
        b1 = min(fine, buco["fine"])
        if b1 <= b0 + EPS:
            continue
        if b0 - corrente > PEZZO_MINIMO_S:
            pezzi.append({
                "inizio": corrente, "fine": b0,
                "taglia_inizio": tagliato_a_sinistra, "taglia_fine": True,
            })
        corrente = max(corrente, b1)
        tagliato_a_sinistra = True
    if fine - corrente > PEZZO_MINIMO_S:
        pezzi.append({
            "inizio": corrente, "fine": fine,
            "taglia_inizio": tagliato_a_sinistra, "taglia_fine": False,
        })
    scorso = 0.0
    for pezzo in pezzi:
        pezzo["offset"] = scorso
        scorso += pezzo["fine"] - pezzo["inizio"]
    return pezzi


def durata_pezzi(pezzi: list[dict]) -> float:
    return sum(p["fine"] - p["inizio"] for p in pezzi)


def tempo_nella_clip(pezzi: list[dict], t: float):
    """Da secondo del GIRATO a secondo della CLIP. None se e' stato tolto.

    None non e' un guasto: e' la risposta esatta. Ripiegare sul punto piu'
    vicino vorrebbe dire indicare, nella clip, un istante che nella clip non
    esiste — ed e' il modo in cui un evento grafico finisce sopra la frase
    sbagliata.

    Gemello esatto di tempoNellaClip in api/src/montaggio.js: se cambia una,
    cambia l'altra.
    """
    if t is None or not math.isfinite(float(t)):
        return None
    istante = float(t)
    for pezzo in pezzi:
        if pezzo["inizio"] - EPS <= istante <= pezzo["fine"] + EPS:
            dentro = min(max(istante, pezzo["inizio"]), pezzo["fine"])
            return pezzo["offset"] + (dentro - pezzo["inizio"])
    return None


def tempo_agganciato(pezzi: list[dict], t: float) -> tuple[float, bool]:
    """Come tempo_nella_clip, ma un istante tolto si AGGANCIA alla saldatura.

    Torna (secondo_della_clip, era_dentro). Serve solo ai tempi delle
    GRAFICHE: un evento che comincia dentro un buco deve comunque comparire, e
    il punto meno sorprendente e' la saldatura fra i due pezzi — cioe' l'inizio
    del primo pezzo che viene dopo. Per le PAROLE non vale: una parola tolta
    non si aggancia a niente, sparisce.

    Fuori dalla clip in testa -> 0. Fuori in coda -> la durata.
    """
    if t is None or not math.isfinite(float(t)):
        return 0.0, False
    dentro = tempo_nella_clip(pezzi, t)
    if dentro is not None:
        return dentro, True
    if not pezzi:
        return 0.0, False
    istante = float(t)
    if istante <= pezzi[0]["inizio"]:
        return 0.0, False
    for pezzo in pezzi:
        if istante < pezzo["inizio"]:
            return pezzo["offset"], False
    return durata_pezzi(pezzi), False


# ------------------------------------------------------- ribasare le parole

def ribasa_parole(parole: list[dict], pezzi: list[dict]) -> list[dict]:
    """Le parole che restano, coi tempi gia' in secondi della CLIP.

    Entrano parole nella forma del trascritto ({"w", "start", "end"}, secondi
    del GIRATO); escono nella stessa forma ma con 'start'/'end' in secondi
    della clip, piu' 'pezzo' (a quale tratto appartengono) e 'idx' se c'era.

    TRE REGOLE, e sono tutte e tre state pagate con un difetto:

    1. Una parola che sta INTERAMENTE dentro un buco sparisce. Ovvio a dirsi,
       e' la ragione del taglio.
    2. Una parola A CAVALLO DI UN TAGLIO si STRINGE sulla parte visibile. E'
       cio' che fa ffmpeg quando taglia, ed e' il caso «il taglio cade dentro
       una sillaba»: senza questa riga il karaoke illuminerebbe la parola per
       un tempo che nella clip non esiste piu', e tutte le righe dopo di lei
       slitterebbero in avanti (build_ass tiene prev_end monotono).
    3. Una parola STRETTA da un taglio fino a meno di
       PAROLA_VISIBILE_MINIMA_S esce dai sottotitoli. Il suo INDICE resta
       quello che era: la numerazione vive nel trascritto e nessun taglio la
       sposta.

    Le regole 2 e 3 valgono SOLO sui bordi di taglio, mai sui bordi esterni
    della clip: la' il comportamento resta quello di sempre, o una clip senza
    buchi non produrrebbe piu' gli stessi sottotitoli di prima.

    La regola di appartenenza (sovrapposizione a estremi esclusi) e' quella
    che il montaggio applica davvero in collect_words, copiata e non
    reinventata: e' cio' che fa combaciare questi tempi con i sottotitoli
    bruciati nel video.
    """
    fuori: list[dict] = []
    for numero, parola in enumerate(parole):
        inizio = parola.get("start")
        fine = parola.get("end")
        if not isinstance(inizio, (int, float)) or not isinstance(fine, (int, float)):
            continue
        for quale, pezzo in enumerate(pezzi):
            if not (fine > pezzo["inizio"] + EPS and inizio < pezzo["fine"] - EPS):
                continue
            visibile_da = float(inizio)
            visibile_a = float(fine)
            stretta = False
            if pezzo.get("taglia_inizio") and visibile_da < pezzo["inizio"]:
                visibile_da = pezzo["inizio"]
                stretta = True
            if pezzo.get("taglia_fine") and visibile_a > pezzo["fine"]:
                visibile_a = pezzo["fine"]
                stretta = True
            if stretta and visibile_a - visibile_da < PAROLA_VISIBILE_MINIMA_S - EPS:
                break
            nuova = dict(parola)
            nuova["start"] = pezzo["offset"] + (visibile_da - pezzo["inizio"])
            nuova["end"] = pezzo["offset"] + (visibile_a - pezzo["inizio"])
            # La durata VISIBILE, calcolata sui tempi del girato e non sulla
            # differenza dei due tempi ribasati. E' la stessa quantita' al
            # millesimo, ma non allo stesso bit: (a-c)-(b-c) non e' a-b in
            # virgola mobile, e da quella differenza dipende se una parola si
            # fonde con la precedente nei sottotitoli. Una clip senza buchi
            # deve produrre lo stesso identico file .ass di prima.
            nuova["durata_s"] = visibile_a - visibile_da
            nuova["pezzo"] = quale
            nuova.setdefault("idx", parola.get("idx", numero))
            fuori.append(nuova)
            break
    return fuori


def unisci_brevi(parole: list[dict], minimo_ms: float) -> list[dict]:
    """Fonde nei sottotitoli le parole troppo brevi, MAI a cavallo di un buco.

    E' collect_words di render.py, con una riga in piu': due parole di pezzi
    diversi non si fondono. Fonderle vorrebbe dire scrivere sullo schermo
    «e poi» dove nel video c'e' «e» seguito da un taglio, e la seconda meta'
    della riga starebbe li' prima di essere pronunciata.
    """
    fusi: list[dict] = []
    for parola in parole:
        durata = parola.get("durata_s")
        if durata is None:
            durata = parola["end"] - parola["start"]
        breve = durata * 1000 < minimo_ms
        if fusi and breve and fusi[-1].get("pezzo") == parola.get("pezzo"):
            fusi[-1]["w"] += " " + parola["w"]
            fusi[-1]["end"] = parola["end"]
            fusi[-1]["durata_s"] = fusi[-1]["end"] - fusi[-1]["start"]
        else:
            fusi.append(dict(parola))
    return fusi


# ------------------------------------------------- ribasare il piano grafico

# I campi che portano un istante dentro un evento del piano overlay
# (fx_plans.json, formato di componi_fx.py). 't0'/'t1' sono l'arco degli
# eventi temporizzati, 't' e' l'istante secco dello stamp.
CAMPI_TEMPO_EVENTO = ("t0", "t1", "t")

# I contenitori di voci temporizzate dentro un evento: le righe di una lista
# compaiono una alla volta, ognuna col suo secondo.
CAMPI_VOCI_EVENTO = ("items",)

# Sotto questa durata un evento grafico non e' piu' un evento: e' un lampo.
# E' la stessa soglia con cui componi_fx scarta un evento schiacciato dal
# successivo (0.8 s), ripetuta qui perche' un taglio puo' schiacciarlo dopo.
EVENTO_MINIMO_S = 0.8


def ribasa_piano(eventi: list[dict], pezzi: list[dict]) -> tuple[list[dict], list[dict]]:
    """Gli eventi grafici coi tempi rimessi nella clip tagliata.

    Entrano eventi coi tempi nella scala della clip PRIMA del taglio; escono
    con i tempi nella scala della clip DOPO, piu' l'elenco di quelli caduti.

    PERCHE' SERVE ANCHE SE IL PIANO SI RIFA'. Il piano lo ricompone componi_fx
    ancorando gli eventi a indici di parola, e li' la conversione passa dai
    pezzi (vedi componi_fx.py). Ma un taglio che tocca SOLO i tempi non deve
    costare una chiamata al modello e non deve poter cambiare i testi a
    schermo: «togli le pause» non e' «riscrivi le grafiche». Con questa
    funzione lo stesso piano si sposta di quello che serve e resta identico
    parola per parola.

    COSA SUCCEDE A UN EVENTO CHE CADE DENTRO UN BUCO:
      - il suo inizio si aggancia alla SALDATURA fra i due pezzi (il primo
        fotogramma ancora visibile dopo il buco);
      - la sua fine fa lo stesso;
      - se cosi' l'arco scende sotto EVENTO_MINIMO_S l'evento e' stato tolto
        insieme al parlato che accompagnava: si SCARTA e si dichiara, invece
        di lasciare a schermo un lampo agganciato a niente.
    Un evento senza tempi (il banner 'pill', che vale per tutta la clip) non
    si tocca: non ha niente da ribasare.
    """
    durata = durata_pezzi(pezzi)
    tenuti: list[dict] = []
    scartati: list[dict] = []
    for evento in eventi:
        nuovo = dict(evento)
        t0 = evento.get("t0")
        t1 = evento.get("t1")
        if isinstance(t0, (int, float)):
            nuovo["t0"] = fondamenta.arrotonda_decimale(
                min(durata, tempo_agganciato(pezzi, t0)[0]), 2)
        if isinstance(t1, (int, float)):
            nuovo["t1"] = fondamenta.arrotonda_decimale(
                min(durata, tempo_agganciato(pezzi, t1)[0]), 2)
        if isinstance(evento.get("t"), (int, float)):
            nuovo["t"] = fondamenta.arrotonda_decimale(
                min(durata, tempo_agganciato(pezzi, evento["t"])[0]), 2)
        for campo in CAMPI_VOCI_EVENTO:
            voci = evento.get(campo)
            if not isinstance(voci, list):
                continue
            nuove = []
            for voce in voci:
                if not isinstance(voce, dict) or not isinstance(voce.get("t"), (int, float)):
                    nuove.append(voce)
                    continue
                quando, dentro = tempo_agganciato(pezzi, voce["t"])
                # Una riga di lista il cui istante e' stato tolto non compare
                # piu': il parlato che la giustificava non c'e'. Tenerla sulla
                # saldatura la farebbe apparire insieme alla precedente.
                if not dentro:
                    continue
                nuova = dict(voce)
                nuova["t"] = fondamenta.arrotonda_decimale(min(durata, quando), 2)
                nuove.append(nuova)
            nuovo[campo] = nuove
        if (isinstance(t0, (int, float)) and isinstance(t1, (int, float))
                and isinstance(nuovo.get("t0"), (int, float))
                and isinstance(nuovo.get("t1"), (int, float))):
            durata_prima = float(t1) - float(t0)
            durata_dopo = nuovo["t1"] - nuovo["t0"]
            # Si scarta SOLO cio' che il taglio ha accorciato sotto il minimo,
            # mai un evento che era gia' corto per conto suo. La differenza non
            # e' teorica: componi_fx puo' aver prodotto un lampo voluto, e un
            # ribasamento che si mette a cancellare eventi che non ha toccato
            # cambierebbe la grafica di uno short a cui era stata solo tolta
            # una pausa dall'altra parte.
            if (durata_dopo < durata_prima - EPS
                    and durata_dopo < min(EVENTO_MINIMO_S, durata_prima) - EPS):
                scartati.append({
                    "type": evento.get("type"),
                    "t0": t0,
                    "t1": t1,
                    "motivo": "il taglio ha tolto il parlato su cui era ancorato: "
                              f"restava meno di {EVENTO_MINIMO_S:g}s a schermo",
                })
                continue
        tenuti.append(nuovo)
    tenuti.sort(key=lambda e: (e.get("t0") if isinstance(e.get("t0"), (int, float))
                              else e.get("t") if isinstance(e.get("t"), (int, float))
                              else -1))
    return tenuti, scartati


# --------------------------------------------------------- limiti e avvisi

def avviso(campo: str, chiesto, applicato, motivo: str) -> dict:
    """Un limite raggiunto, leggibile da una persona e da un programma.

    Stessa forma di correzioni.avviso: chi legge la cronologia di una clip
    trova le due cose scritte allo stesso modo.
    """
    return {"campo": campo, "chiesto": chiesto, "applicato": applicato, "motivo": motivo}


def entro_durata_minima(buchi: list[dict], inizio: float, fine: float,
                        min_clip_s: float) -> tuple[list[dict], list[dict], list[dict]]:
    """Toglie i buchi finche' la clip resta sopra la durata minima.

    Torna (tenuti, lasciati, avvisi).

    PERCHE' ESISTE. Sotto config.MIN_CLIP_S il montaggio SCARTA la clip
    (resolve_highlights): un taglio che la porta sotto quella soglia non
    produrrebbe uno short piu' corto, produrrebbe uno short in meno — e nessuno
    l'ha chiesto. E' la stessa regola di applica_pad in correzioni.py, e la
    stessa risposta: non si fallisce e non si tace, si applica il massimo
    possibile e si scrive un avviso.

    ORDINE, e conta: si tengono PRIMA i buchi piu' lunghi. Sono quelli che
    danno il guadagno vero (una pausa da due secondi vale venti pause da un
    decimo), e sono anche quelli che il cliente ha notato. A parita' di durata
    vince il piu' vicino all'inizio, cosi' l'esito non dipende dall'ordine in
    cui sono arrivati.
    """
    disponibile = float(fine) - float(inizio)
    tenuti: list[dict] = []
    lasciati: list[dict] = []
    avvisi: list[dict] = []
    for buco in sorted(unisci_buchi(buchi),
                       key=lambda b: (-(b["fine"] - b["inizio"]), b["inizio"])):
        dentro_da = max(float(inizio), buco["inizio"])
        dentro_a = min(float(fine), buco["fine"])
        quanto = max(0.0, dentro_a - dentro_da)
        if quanto <= EPS:
            # tutto fuori dal taglio: non toglie niente, e non consuma durata
            tenuti.append(buco)
            continue
        if disponibile - quanto < float(min_clip_s) - EPS:
            lasciati.append(buco)
            continue
        disponibile -= quanto
        tenuti.append(buco)
    if lasciati:
        avvisi.append(avviso(
            "durata", fondamenta.arrotonda_decimale(float(fine) - float(inizio)),
            fondamenta.arrotonda_decimale(disponibile),
            f"sotto la durata minima di {float(min_clip_s):.0f}s il montaggio scarta "
            f"la clip: {len(lasciati)} taglio/i non e' stato applicato"))
    return sorted(tenuti, key=lambda b: b["inizio"]), lasciati, avvisi


# --------------------------------------------------- firma della numerazione

def numera_parole(segmenti: list[dict]) -> list[dict]:
    """Le parole del girato nell'ordine, con l'indice GLOBALE 0-based.

    Contratto vincolante, scritto per esteso in api/src/montaggio.js: l'indice
    di una parola e' la sua posizione nella concatenazione ordinata di
    segments[].words[] di build/transcript.json. Si conta OGNI voce, anche
    quella senza tempi: non finira' mai dentro una clip, ma non fa scalare di
    uno tutte quelle dopo.
    """
    fuori: list[dict] = []
    for posizione, segmento in enumerate(segmenti or []):
        numero_segmento = segmento.get("id", posizione)
        for voce in segmento.get("words") or []:
            fuori.append({
                "idx": len(fuori),
                "w": voce.get("w", ""),
                "start": voce.get("start"),
                "end": voce.get("end"),
                "segmento": numero_segmento,
            })
    return fuori


def firma_numerazione(parole: list[dict]) -> str:
    """L'impronta dei CONFINI delle parole: conteggio piu' tempi d'attacco.

    Gemello esatto di firmaNumerazione in api/src/montaggio.js — stesso ordine,
    stesso separatore, stessi tre decimali, stessi 16 caratteri. E' cio' che
    permette di confrontare qui la firma scritta dall'API, e quindi di
    accorgersi che il girato e' stato ritrascritto PRIMA di tagliare le parole
    sbagliate. Non cambia quando si corregge un refuso, perche' fix_transcript
    tocca solo il testo.
    """
    impronta = hashlib.sha256()
    impronta.update(str(len(parole)).encode("utf-8"))
    for parola in parole:
        inizio = parola.get("start")
        impronta.update(b"|")
        if isinstance(inizio, (int, float)) and math.isfinite(float(inizio)):
            impronta.update(f"{float(inizio):.3f}".encode("utf-8"))
        else:
            impronta.update(b"-")
    return impronta.hexdigest()[:16]
