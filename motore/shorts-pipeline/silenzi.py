"""Il tempo morto dentro una clip: dove sta, e perche' la soglia e' RELATIVA.

PERCHE' LA SOGLIA NON PUO' ESSERE ASSOLUTA
Nel nostro qa_check.py il muto si misura con `silencedetect=n=-40dB`: una
soglia FISSA. Va bene per quello che fa li' — dire se uno short attacca con
mezzo secondo di niente — ma non regge come regola di TAGLIO, e la specifica
del progetto da cui arriva questa funzione scarta apertamente quell'approccio:
un taglio a soglia assoluta «taglierebbe dentro il letto musicale, dentro
l'ambiente rumoroso, e dentro i respiri che tengono in piedi la frase».

Il caso concreto: due frasi separate da tre secondi in cui non si parla, ma
sotto c'e' una base musicale a −18 dBFS. Con la soglia fissa a −40 quel tratto
non e' muto e non si taglia mai (e allora lo strumento non serve a niente). Con
una soglia fissa piu' alta, diciamo −20, si taglia — e si taglia DENTRO la
musica, che si sente saltare. Non esiste un numero fisso giusto per tutti i
girati: dipende da quanto forte parla chi parla, che cambia da registrazione a
registrazione e perfino da stanza a stanza.

LA SOGLIA STA DODICI DECIBEL SOTTO IL PARLATO DI QUESTA REGISTRAZIONE
Si misura il livello mediano delle celle in cui si sta parlando davvero — e le
sappiamo esattamente, perche' il trascritto porta i tempi di ogni parola — e la
soglia si mette SCARTO_DB sotto quel valore, dentro due limiti:

    soglia_dB = min( SOGLIA_MASSIMA_DB , max( SOGLIA_MINIMA_DB , L − SCARTO_DB ) )

Con un parlato a −8 dBFS la soglia esce a −22 (il limite alto), e la musica a
−18 non la raggiunge: la pausa NON e' tempo morto e resta dov'e'. Con un
parlato sommesso a −30 la soglia esce a −40 (il limite basso) e si continua a
tagliare solo il silenzio vero. E' la promessa «letti musicali e ambienti forti
non vengono mai tagliati», ed e' verificabile: prova_tagli.py la controlla coi
numeri di quell'esempio.

LA DECISIONE E' PER CORSA, NON PER CELLA, E PASSA DALLA MEDIANA
Una pausa non si marca a meta'. Si guarda la mediana del livello su tutta la
corsa: cosi' un colpo isolato — un click, un colpo di tosse, una sedia che
striscia — non salva una pausa che per il resto e' vuota, e nello stesso tempo
un rumore che occupa piu' di meta' della corsa la salva tutta. La mediana fa il
mestiere che altrove si farebbe con l'isteresi.

ATTENZIONE — LE FONTI SONO TRE, MA LA TERZA E' SPENTA DI FABBRICA.
Il rilevatore neurale (VAD) adesso c'e' ed e' provato: sta in fondo a questo
file, e prova_silenzi.py copre la sua strada. Ma e' dietro un interruttore
SPENTO — la variabile d'ambiente MOTORE_RILEVATORE_PARLATO — perche' accenderlo
cambia i video prodotti: tiene pause che oggi vengono tolte, quindi produce
short piu' lunghi. Spento, questo file si comporta esattamente come prima:
nessun modello caricato, nessun ffmpeg in piu', gli stessi identici tagli.

E c'e' un secondo motivo per cui oggi la terza fonte non tocca niente: NESSUNO
LA CHIAMA ANCORA. Il punto in cui dovrebbe entrare e' `risolvi_taglio` in
render.py, subito dopo `veta_per_livello`, e quel file non e' stato toccato.
Finche' quella chiamata non c'e', «tre fonti» e' due fonti piu' un motore
acceso in folle: funzionante, provato, e scollegato dalle ruote.

TRE FONTI, NON UNA. E RISPONDONO A TRE DOMANDE DIVERSE
La specifica da cui viene questa funzione ha un rilevatore di parlato sul
dispositivo e nient'altro. Noi ne avremo tre, e ognuna serve a una cosa sola:

    il TRASCRITTO   dice DOVE il cliente ha detto delle parole. E' la fonte
                    piu' precisa che abbiamo — porta i tempi di ogni parola —
                    ma vede solo cio' che whisper ha trascritto: una frase
                    sussurrata, un «mmh», una voce fuori campo non ci sono.
    il RILEVATORE   dice DOVE C'E' VOCE UMANA, trascritta o no. E' un modello
    NEURALE (VAD)   neurale, quindi distingue il parlato dal rumore forte —
                    cosa che nessuna soglia di livello puo' fare. Serve a due
                    cose: dare le celle di parlato su cui si calibra la soglia
                    (anche quando il trascritto non c'e', come in qa_check), e
                    VETARE una pausa dentro cui si sta parlando lo stesso.
    il LIVELLO      dice QUANTO FORTE e' quel che c'e' sotto una pausa. Serve
                    a una cosa sola: VETARE un taglio dove sotto c'e'
                    materiale sonoro che conta (musica, ambiente).

Le tre non si contraddicono mai, perche' non rispondono alla stessa domanda.
E le due verifiche — il rilevatore e il livello — possono solo TOGLIERE tagli,
mai aggiungerne: e' l'invariante gia' dichiarata al cliente in
api/src/tagli.js (semanticaTagli().misura, «'tolti_s' e' un MASSIMO»), e vale
ancora parola per parola dopo l'arrivo del rilevatore.
"""
from __future__ import annotations

import math
import os
import re
import subprocess
import sys

import fondamenta

# ------------------------------------------------------------- le costanti
#
# Sono tutte tarate, non scelte a occhio. Chi le cambia cambia il montaggio di
# ogni short: qui sotto c'e' scritto cosa succede se le si sposta.

# Quanto sotto il livello del parlato sta la soglia. Dodici decibel e' un
# quarto della scala utile e sono la distanza classica fra una voce e il fondo
# della stanza in cui e' stata registrata: piu' stretto (6 dB) e i respiri
# finiscono sopra soglia, quindi non si taglia niente; piu' largo (20 dB) e si
# taglia dentro il riverbero della coda delle frasi.
SCARTO_DB = 12.0

# Il tetto: non si chiama MAI silenzio qualcosa di piu' forte di −22 dBFS,
# per quanto forte sia il parlato. E' cio' che salva il letto musicale.
SOGLIA_MASSIMA_DB = -22.0

# Il pavimento: non si pretende MAI un silenzio piu' profondo di −40 dBFS, per
# quanto sommesso sia il parlato. Sotto quella soglia si sta chiedendo il
# silenzio digitale, che una registrazione vera non ha quasi mai.
SOGLIA_MINIMA_DB = -40.0

# Nessuna cella di parlato misurabile (clip senza parole, o trascritto muto):
# e' l'UNICA soglia assoluta del sistema, e si dichiara come tale nell'esito.
RIPIEGO_DB = -28.0

# La durata di una cella di analisi: 512 campioni a 16 kHz = 0,032 s esatti.
# NON si dichiara qui. E' la griglia condivisa da ogni maschera di parlato e di
# silenzio (docs/fondamenta-numeriche.md, voce 1) e vive in fondamenta.py: una
# seconda copia sarebbe il posto da cui si disallinea. I tre nomi restano
# esposti perche' li usa il comando ffmpeg qui sotto e li importa chi misura.
CAMPIONI_CELLA = fondamenta.CAMPIONI_CELLA
FREQUENZA_ANALISI = fondamenta.FREQUENZA_ANALISI
DURATA_CELLA_S = fondamenta.DURATA_CELLA_S

# Quanto deve durare una pausa perche' valga la pena toglierla. Mezzo secondo:
# sotto, quello che si guadagna e' qualche fotogramma e quello che si paga e'
# uno stacco udibile in mezzo a una frase. E' anche il valore di fabbrica del
# controllo «pausa minima» nella specifica da cui viene la funzione.
PAUSA_MINIMA_S = 0.5

# Quanta quiete si lascia sui due lati del parlato che sta intorno. I confini
# di parola di whisper non sono precisi al millisecondo e sbagliano quasi
# sempre nella stessa direzione: l'attacco arriva TARDI (la consonante iniziale
# resta fuori) e la coda arriva PRESTO. Tagliare a filo del tempo dichiarato
# vuol dire mangiarsi la 'p' di «pero'» e la coda di «gia'». Centocinquanta
# millisecondi coprono l'errore tipico senza rendere inutile il taglio.
MARGINE_PARLATO_S = 0.15

# Limiti su cosa si puo' chiedere. Una pausa minima sotto 0,25 s taglia dentro
# le esitazioni normali del parlato; sopra 3 s non toglie piu' niente.
PAUSA_MINIMA_MIN_S = 0.25
PAUSA_MINIMA_MAX_S = 3.0
MARGINE_MIN_S = 0.0
MARGINE_MAX_S = 0.5

# Quando si toglie una parola nominata («dalla 34 alla 41») il buco si allarga
# di questo tanto sui due lati, ma senza mai entrare nella parola vicina. Serve
# allo stesso difetto dei confini di whisper: togliere esattamente [inizio,
# fine] lascia in aria la consonante iniziale della parola tolta, ed e'
# proprio quel frammento a far sentire il taglio. Quaranta millisecondi sono
# circa un fotogramma a 25 fps.
RESPIRO_TAGLIO_S = 0.04

EPS = 1e-9

# ------------------------------------------- le costanti del rilevatore
#
# NON PIU' INERTI: da oggi le legge il rilevatore in fondo al file, e
# prova_silenzi.py le prova una per una. Restano scritte qui, sopra il codice
# che le usa, perche' la motivazione dei numeri si perde se si scrive dopo.
#
# NIENTE DI QUESTO E' SCRITTO NEL CORPUS, e va detto prima di leggere i numeri.
# SPEC/60 §5.7 e §12.1 dichiarano apertamente che soglia, isteresi, durata
# minima di parlato, durata minima di silenzio, fusione e padding «non sono
# contenuti nel sorgente assegnato»: vivono nella configurazione predefinita di
# Silero, che nel loro repository non c'e'. Il corpus dice solo COSA deve fare
# un binarizzatore compatibile (§12.1, cinque punti) e cosa NON deve fare —
# «non deve introdurre una dipendenza dal livello assoluto del segnale, quella
# responsabilita' e' di §6, che ha il vantaggio di calibrarsi sul file».
#
# Quindi i sei numeri qui sotto sono una scelta NOSTRA, e sono i valori di
# fabbrica di Silero a monte (soglia 0,5 / uscita 0,35 / parlato minimo 250 ms
# / silenzio minimo 100 ms / padding 30 ms). Non sono i valori di fabbrica di
# faster-whisper, che sono un'altra cosa: la' il VAD serve a spezzare l'audio
# in blocchi da dare a whisper, e per quel mestiere tiene 2 s di silenzio
# minimo e 400 ms di padding. Usarli qui vorrebbe dire non accorgersi mai di
# una pausa sotto i due secondi.

# La finestra del modello. E' la stessa cella di fondamenta.py, e deve
# restarlo: e' cio' che rende la maschera del parlato confrontabile con quella
# dei livelli. Se un giorno il modello dichiarasse una finestra diversa, la
# griglia condivisa si spezzerebbe in silenzio (SPEC/60 §5.3.1).
FINESTRA_VAD = fondamenta.CAMPIONI_CELLA
# I campioni della finestra precedente che il modello v6 riceve in testa a
# ogni finestra. Non e' sovrapposizione: e' contesto, e la prima finestra del
# file lo riceve a zero.
CONTESTO_VAD = 64

# L'isteresi a due soglie (§12.1, punto 1: «una soglia unica su una
# probabilita' rumorosa produce frammentazione»). Si ENTRA in parlato sopra
# 0,50 e si ESCE solo sotto 0,35: in mezzo si resta dove si era.
SOGLIA_ENTRATA = 0.5
SOGLIA_USCITA = 0.35

# Un'accensione isolata piu' corta di questo non e' parlato (§12.1, punto 2).
PARLATO_MINIMO_S = 0.25
# Due segmenti separati da meno di questo sono lo stesso segmento (§12.1,
# punto 3): dentro una frase le occlusive lasciano buchi di 50-80 ms, e senza
# la fusione ogni «p» spezzerebbe il parlato in due.
SILENZIO_MINIMO_S = 0.10
# Il padding della RILEVAZIONE, che non e' quello del taglio. SPEC/60 §5.7 lo
# dice esplicitamente: «il padding del pianificatore protegge i bordi del
# TAGLIO, non i bordi della RILEVAZIONE. Le due cose non vanno confuse».
# Questo qui sono 30 ms e serve a non tagliare la consonante iniziale al
# rilevatore; quello del taglio e' MARGINE_PARLATO_S = 0,15 s e sta piu' su.
PADDING_RILEVAMENTO_S = 0.03

# Quanto parlato deve trovare il rilevatore dentro una pausa candidata perche'
# quella pausa non sia una pausa. E' lo STESSO quarto di secondo che rende un
# segmento un segmento: sotto quella durata il rilevatore non chiama parlato
# nemmeno una sua accensione, quindi non puo' chiamarlo qui.
PARLATO_CHE_VETA_S = PARLATO_MINIMO_S

# Quante finestre per volta si danno al modello. Non cambia il risultato — lo
# stato ricorrente e il contesto passano da un blocco al successivo, e la prova
# lo verifica numericamente — cambia solo la memoria: 5000 finestre sono 160 s
# di audio e 11 MB di tensore, contro i 76 MB di un girato di venti minuti
# tenuto tutto insieme.
BLOCCO_FINESTRE = 5000

# La riga che ametadata stampa per ogni cella.
_RIGA_LIVELLO = re.compile(r"lavfi\.astats\.Overall\.RMS_level=(-?\d+(?:\.\d+)?|-?inf|nan)")


class MisuraNonRiuscita(RuntimeError):
    """Il livello audio non si e' potuto misurare: non si indovina, si dice."""


# ------------------------------------------------------------- la misura

def comando_livelli(video, inizio: float, durata: float) -> list[str]:
    """Il comando ffmpeg che stampa il livello RMS cella per cella.

    Separato dall'esecuzione apposta: cosi' la forma del comando si legge (e si
    prova) senza avere ffmpeg. Tutto in un filtro solo:
      - aformat  porta l'audio a mono 16 kHz, cosi' la cella dura esattamente
                 512/16000 s qualunque sia il formato del girato;
      - asetnsamples fissa la dimensione del blocco: senza, la lunghezza dei
                 frame la decide il decoder e le celle non sono confrontabili;
      - astats   con reset=1 calcola le statistiche di OGNI blocco, non
                 cumulative;
      - ametadata le stampa su stdout, una riga per cella.
    """
    return [
        "ffmpeg", "-v", "error", "-nostdin",
        "-ss", f"{float(inizio):.3f}", "-t", f"{float(durata):.3f}",
        "-i", str(video),
        "-map", "0:a:0",
        "-af",
        (f"aformat=sample_fmts=fltp:sample_rates={FREQUENZA_ANALISI}:channel_layouts=mono,"
         f"asetnsamples=n={CAMPIONI_CELLA}:p=0,"
         "astats=metadata=1:reset=1,"
         "ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-"),
        "-f", "null", "-",
    ]


def interpreta_livelli(testo: str, inizio: float) -> list[dict]:
    """Le righe di ametadata -> celle {t_inizio, t_fine, db} in secondi del GIRATO.

    Il silenzio digitale esce come '-inf': diventa SOGLIA_MINIMA_DB − 60, cioe'
    un numero finito e nettamente sotto qualunque soglia. Un float('-inf') vero
    passerebbe indenne per i confronti ma poi finirebbe dentro una mediana e in
    un JSON, dove non si puo' scrivere.
    """
    celle: list[dict] = []
    for trovato in _RIGA_LIVELLO.finditer(testo):
        grezzo = trovato.group(1)
        if grezzo == "nan":
            continue
        db = SOGLIA_MINIMA_DB - 60.0 if grezzo.endswith("inf") else float(grezzo)
        t0 = float(inizio) + len(celle) * DURATA_CELLA_S
        celle.append({"t_inizio": t0, "t_fine": t0 + DURATA_CELLA_S, "db": db})
    return celle


def misura_livelli(video, inizio: float, fine: float) -> list[dict]:
    """Misura il livello cella per cella nella finestra chiesta. Impura."""
    durata = float(fine) - float(inizio)
    if durata <= 0:
        return []
    esito = subprocess.run(comando_livelli(video, inizio, durata),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    if esito.returncode != 0:
        raise MisuraNonRiuscita(
            f"livelli audio non misurabili su '{video}': "
            f"{(esito.stderr or '').strip()[:300]}")
    celle = interpreta_livelli(esito.stdout or "", inizio)
    if not celle:
        raise MisuraNonRiuscita(
            f"livelli audio non misurabili su '{video}': ffmpeg non ha stampato "
            "nessuna cella (traccia audio assente?)")
    return celle


# --------------------------------------------------------------- la soglia

def mediana(valori: list[float]) -> float:
    """La mediana superiore, come nella specifica: l'elemento di indice ⌊m/2⌋.

    Superiore e non media dei due centrali: cosi' il valore restituito e'
    sempre uno dei valori misurati, e la soglia non finisce mai su un numero
    che nessuna cella ha davvero.
    """
    ordinati = sorted(valori)
    return ordinati[len(ordinati) // 2]


def celle_di_parlato(celle: list[dict], parole: list[dict]) -> list[dict]:
    """Le celle che cadono dentro una parola del trascritto.

    Sono queste — e non tutte le celle sopra una soglia — a definire «il
    livello del parlato»: il trascritto sa dove si parla, il livello no.
    """
    intervalli = [
        (float(p["start"]), float(p["end"]))
        for p in parole
        if isinstance(p.get("start"), (int, float)) and isinstance(p.get("end"), (int, float))
    ]
    if not intervalli:
        return []
    intervalli.sort()
    dentro = []
    for cella in celle:
        for a, b in intervalli:
            if a >= cella["t_fine"]:
                break
            if cella["t_inizio"] < b and cella["t_fine"] > a:
                dentro.append(cella)
                break
    return dentro


def soglia_relativa(celle: list[dict], parole: list[dict]) -> dict:
    """La soglia in dB, col suo perche' dentro.

    Torna { db, livello_parlato_db, celle_parlato, tipo }, dove 'tipo' e'
    'relativa' quando la soglia viene dal parlato di QUESTA registrazione e
    'ripiego_assoluto' quando il parlato non si e' potuto misurare. Il tipo si
    dichiara perche' e' la differenza fra una soglia che si adatta e un numero
    fisso: chi legge l'esito deve saperlo senza doverlo dedurre dai valori.
    """
    dentro = celle_di_parlato(celle, parole)
    if not dentro:
        return {
            "db": RIPIEGO_DB,
            "livello_parlato_db": None,
            "celle_parlato": 0,
            "tipo": "ripiego_assoluto",
        }
    livello = mediana([c["db"] for c in dentro])
    db = min(SOGLIA_MASSIMA_DB, max(SOGLIA_MINIMA_DB, livello - SCARTO_DB))
    return {
        "db": fondamenta.arrotonda_decimale(db, 2),
        "livello_parlato_db": fondamenta.arrotonda_decimale(livello, 2),
        "celle_parlato": len(dentro),
        "tipo": "relativa",
    }


# ----------------------------------------------------- le pause candidate

def parole_nella_finestra(parole: list[dict], inizio: float, fine: float) -> list[dict]:
    """Le parole che si sovrappongono al taglio, estremi esclusi.

    Stessa regola di appartenenza di collect_words in render.py e di
    paroleDentro in api/src/montaggio.js: copiata, non reinventata.
    """
    fuori = []
    for parola in parole:
        a, b = parola.get("start"), parola.get("end")
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            continue
        if float(b) > float(inizio) + EPS and float(a) < float(fine) - EPS:
            fuori.append(parola)
    return fuori


def pause_candidate(parole: list[dict], inizio: float, fine: float,
                    pausa_minima_s: float = PAUSA_MINIMA_S,
                    margine_s: float = MARGINE_PARLATO_S) -> list[dict]:
    """Le pause che si potrebbero togliere, lette dal SOLO trascritto.

    Sono CANDIDATE, non tagli: qui non si e' ancora guardato il livello audio.
    Chi ha ffmpeg (la pipeline) le passa poi da veta_per_livello; chi non ce
    l'ha (l'API) le scrive nel file dei tagli con "verifica_livello": true.

    ORDINE DELLE DUE REGOLE, e conta: prima si guarda se la corsa raggiunge la
    pausa minima, POI si toglie il margine. Al contrario una pausa di 0,55 s
    con margine 0,15 diventerebbe 0,25 e sparirebbe dai candidati anche se la
    pausa c'era eccome. E' l'ordine della specifica.

    IL MARGINE SI APPLICA ANCHE AI BORDI DELLA CLIP, e qui si diverge
    apertamente dalla specifica di origine, che ai bordi non lo mette. Da loro
    il bordo e' la fine del file: oltre non c'e' niente da proteggere. Da noi
    il bordo e' un taglio DENTRO un girato piu' lungo, e in testa c'e' per
    giunta un padding voluto (config.PAD_START_S anticipa l'attacco di 0,20 s
    perche' la prima parola non si tronchi). Togliere il margine in testa
    vorrebbe dire disfare quel padding con l'altra mano.
    """
    inizio = float(inizio)
    fine = float(fine)
    margine = float(margine_s)
    dentro = sorted(parole_nella_finestra(parole, inizio, fine),
                    key=lambda p: float(p["start"]))
    # I confini delle corse senza parlato: dal bordo alla prima parola, fra una
    # parola e la successiva, dall'ultima parola al bordo.
    corse: list[tuple[float, float]] = []
    corrente = inizio
    for parola in dentro:
        a = max(inizio, float(parola["start"]))
        if a - corrente > EPS:
            corse.append((corrente, a))
        corrente = max(corrente, min(fine, float(parola["end"])))
    if fine - corrente > EPS:
        corse.append((corrente, fine))

    candidate = []
    for a, b in corse:
        if b - a < float(pausa_minima_s) - EPS:
            continue
        da = a + margine
        a_ = b - margine
        if a_ - da <= EPS:
            continue
        candidate.append({
            "inizio": fondamenta.arrotonda_decimale(da),
            "fine": fondamenta.arrotonda_decimale(a_),
            "motivo": "silenzio",
            "parole": None,
            "verifica_livello": True,
        })
    return candidate


def veta_per_livello(buchi: list[dict], celle: list[dict],
                     soglia: dict) -> tuple[list[dict], list[dict]]:
    """Toglie dai buchi quelli sotto cui c'e' materiale sonoro che conta.

    Torna (tenuti, vetati). Un buco vetato porta il livello misurato e la
    soglia, cosi' chi legge la cronologia sa PERCHE' quella pausa e' rimasta al
    suo posto invece di leggere «non ho tolto niente».

    Si vetano solo i buchi con "verifica_livello": true. Un buco nato da parole
    nominate passa sempre: il cliente ha detto quali parole togliere, e la
    musica sotto non e' una ragione per tenerle.

    La decisione e' per CORSA e passa dalla MEDIANA (vedi in testa al file).
    Un buco per cui non si e' misurata nemmeno una cella non si veta: non
    sapere non e' una ragione per rifiutare un taglio che il cliente ha
    chiesto, ed e' un caso che capita solo sui buchi di durata quasi nulla.
    """
    tenuti: list[dict] = []
    vetati: list[dict] = []
    for buco in buchi:
        if not buco.get("verifica_livello", True):
            tenuti.append(buco)
            continue
        dentro = [c["db"] for c in celle
                  if c["t_inizio"] < buco["fine"] - EPS and c["t_fine"] > buco["inizio"] + EPS]
        if not dentro:
            tenuti.append(buco)
            continue
        livello = mediana(dentro)
        if livello <= soglia["db"] + EPS:
            tenuti.append(buco)
            continue
        vetati.append({
            **buco,
            "livello_db": fondamenta.arrotonda_decimale(livello, 2),
            "soglia_db": soglia["db"],
            "motivo_veto": (
                f"sotto questa pausa il livello e' {livello:.1f} dB, sopra la soglia "
                f"di {soglia['db']:.1f} dB ({soglia['tipo']}): non e' tempo morto, "
                "c'e' musica o ambiente. La lascio dov'e'"),
        })
    return tenuti, vetati


# ------------------------------------------------- il buco di due parole

def buco_da_parole(parole: list[dict], da: int, a: int) -> dict:
    """Il buco che toglie le parole dalla 'da' alla 'a', estremi compresi.

    Gli indici sono quelli GLOBALI del trascritto (contratto in
    api/src/montaggio.js): non si spostano quando la clip viene allungata o
    rimontata, ed e' per questo che si puo' dire «dalla parola 34 alla 41» in
    un turno e tagliarle in quello dopo.

    Il buco si allarga di RESPIRO_TAGLIO_S sui due lati ma non entra MAI nella
    parola vicina: se fra le due parole c'e' meno respiro di cosi', si prende
    quello che c'e'. Vedi la costante per il perche'.

    Solleva ValueError se gli indici non esistono o sono rovesciati: qui non si
    indovina, si taglia del video.
    """
    if a < da:
        raise ValueError(f"indici rovesciati: dalla {da} alla {a}")
    per_indice = {p.get("idx"): p for p in parole}
    for indice in (da, a):
        parola = per_indice.get(indice)
        if parola is None:
            raise ValueError(f"la parola {indice} non esiste nel trascritto")
        if not isinstance(parola.get("start"), (int, float)) \
                or not isinstance(parola.get("end"), (int, float)):
            raise ValueError(f"la parola {indice} non ha tempi: non si puo' tagliare")
    prima = per_indice[da]
    ultima = per_indice[a]
    precedente = per_indice.get(da - 1)
    successiva = per_indice.get(a + 1)
    inizio = float(prima["start"]) - RESPIRO_TAGLIO_S
    fine = float(ultima["end"]) + RESPIRO_TAGLIO_S
    if precedente is not None and isinstance(precedente.get("end"), (int, float)):
        inizio = max(inizio, float(precedente["end"]))
    if successiva is not None and isinstance(successiva.get("start"), (int, float)):
        fine = min(fine, float(successiva["start"]))
    inizio = max(0.0, min(inizio, float(prima["start"])))
    fine = max(fine, float(ultima["end"]))
    return {
        "inizio": fondamenta.arrotonda_decimale(inizio),
        "fine": fondamenta.arrotonda_decimale(fine),
        "motivo": "parole",
        "parole": [int(da), int(a)],
        "verifica_livello": False,
    }


def entro_limiti(pausa_minima_s, margine_s) -> tuple[float, float]:
    """I due parametri riportati dentro i limiti, senza fallire.

    Stessa disciplina di correzioni.applica_pad: una richiesta fuori scala non
    ferma il lavoro, si applica il massimo possibile. Qui il valore fuori
    limite arriva da un modello, e far fallire il taglio per un decimale
    vorrebbe dire perdere il comando del cliente.
    """
    def dentro(valore, minimo, massimo, difetto):
        if valore is None or isinstance(valore, bool) or not isinstance(valore, (int, float)):
            return difetto
        if not math.isfinite(float(valore)):
            return difetto
        return min(massimo, max(minimo, float(valore)))

    return (
        dentro(pausa_minima_s, PAUSA_MINIMA_MIN_S, PAUSA_MINIMA_MAX_S, PAUSA_MINIMA_S),
        dentro(margine_s, MARGINE_MIN_S, MARGINE_MAX_S, MARGINE_PARLATO_S),
    )


# ===========================================================================
#                     IL RILEVATORE NEURALE DI PARLATO
# ===========================================================================
#
# La terza fonte, quella che in testa al file e' descritta e che fino a oggi
# non c'era. Risponde alla domanda che le altre due non sanno formulare:
# DENTRO questa pausa si sta parlando lo stesso?
#
# IL PROBLEMA E' MISURATO, NON TEMUTO. Il 17/08/2026, sul girato di
# collaudo-p3, parlato_perso.py ha trovato 1,92 s (33,44-35,36) di audio al
# livello del parlato — 0,68 dB sotto la mediana delle frasi certe dello
# stesso file — con ZERO parole nel trascritto. In quel tratto:
#   - il TRASCRITTO dice «qui non si parla», e sbaglia;
#   - il LIVELLO dice «qui c'e' del suono forte», ma non sa se sia una voce,
#     una sedia o un condizionatore, quindi da solo non decide.
# Le due fonti di oggi, messe insieme, salvano quel tratto per caso: il veto
# per livello lo tiene perche' e' FORTE, non perche' e' PARLATO. Sulla stessa
# voce con il fondo piu' basso della soglia il veto non scatta e la frase
# sparisce dallo short.
#
# COSA CAMBIA NEI VIDEO, detto prima e non dopo. Il rilevatore puo' soltanto
# TOGLIERE tagli — e' l'invariante di api/src/tagli.js, «'tolti_s' e' un
# MASSIMO» — quindi acceso produce short piu' LUNGHI, mai piu' corti: la pausa
# che oggi verrebbe tolta e che invece contiene parlato non trascritto resta
# dov'e'. E' un cambiamento vero dei byte prodotti, quindi:
#   - si accende a mano, con MOTORE_RILEVATORE_PARLATO=1;
#   - di fabbrica e' SPENTO, e spento questo codice non gira nemmeno: niente
#     ffmpeg in piu', niente modello caricato, stessi identici tagli di ieri.
#
# QUALE MODELLO, E CON QUALE LICENZA. Silero VAD v6 in ONNX, eseguito con
# onnxruntime. Licenza MIT (github.com/snakers4/silero-vad, «Copyright (c)
# 2020-present Silero Team»), verificata il 21/08/2026 leggendo il file LICENSE
# del progetto: uso commerciale permesso, nessun obbligo di aprire il nostro
# codice. MIT anche faster-whisper e onnxruntime, che sono il modo in cui il
# file arriva sul worker. E' lo stesso criterio con cui altrove nel progetto e'
# stato SCARTATO madmom, i cui modelli sono CC BY-NC-SA: un modello non
# commerciale qui dentro non entra, per bravo che sia.
#
# NON SI SCARICA NIENTE. Il file del modello e' quello che faster-whisper si
# porta gia' dentro il pacchetto (1,2 MB) ed e' gia' installato nel venv del
# worker, perche' e' lui che trascrive. Un rilevatore che va a rete al primo
# giro e' un rilevatore che fallisce il giorno in cui la rete non c'e'.


# L'interruttore. Vedi sopra: acceso cambia i video, quindi si accende a mano.
VARIABILE_INTERRUTTORE = "MOTORE_RILEVATORE_PARLATO"

# Dove sta il file del modello, quando non e' in nessuno dei posti soliti.
VARIABILE_MODELLO = "MOTORE_MODELLO_VAD"

NOME_MODELLO = "silero_vad_v6.onnx"

# I valori che contano come «acceso». Piu' d'uno perche' questa variabile la
# scrive una persona dentro un file di ambiente, non un programma.
_VERI = {"1", "si", "sì", "on", "true", "vero"}

_CARTELLA_QUI = os.path.dirname(os.path.abspath(__file__))


def rilevatore_acceso(ambiente: dict | None = None) -> bool:
    """Se il rilevatore deve girare. Variabile assente o vuota = SPENTO."""
    valori = os.environ if ambiente is None else ambiente
    return str(valori.get(VARIABILE_INTERRUTTORE, "")).strip().lower() in _VERI


def percorsi_modello(ambiente: dict | None = None) -> list[str]:
    """I posti dove si cerca il modello, in ordine. Nessuno di questi e' la rete.

    1) la variabile d'ambiente, che vince su tutto: e' come si prova un modello
       diverso senza toccare il codice;
    2) models/ accanto alla pipeline, dove sta gia' il rilevatore di volti;
    3) gli assets di faster-whisper, che e' la copia che il worker ha davvero.

    Il pacchetto si cerca con find_spec e non con `import faster_whisper`: la
    seconda tira dentro ctranslate2 e i tokenizzatori — un secondo abbondante e
    qualche centinaio di MB — solo per sapere dove sta un file.
    """
    valori = os.environ if ambiente is None else ambiente
    trovati: list[str] = []
    indicato = str(valori.get(VARIABILE_MODELLO, "")).strip()
    if indicato:
        trovati.append(indicato)
    trovati.append(os.path.join(_CARTELLA_QUI, "models", NOME_MODELLO))
    try:
        import importlib.util

        spec = importlib.util.find_spec("faster_whisper")
        posti = list(getattr(spec, "submodule_search_locations", None) or []) if spec else []
        if posti:
            trovati.append(os.path.join(posti[0], "assets", NOME_MODELLO))
    except Exception:
        # Un pacchetto rotto non e' un motivo per non provare gli altri posti.
        pass
    return trovati


# La memoria del caricamento, riuscito o fallito. Il fallimento si ricorda come
# il successo (SPEC/60 §5.6, punto 7): ritentare a ogni clip costa un tracciato
# di errore per clip e la risposta non cambia — il file o c'e' o non c'e'.
_CARICAMENTO: dict | None = None


def _avvisa(testo: str) -> None:
    """L'avviso va su stderr, dove finiscono gli altri della pipeline.

    Non solleva e non ferma niente: e' un avviso, non un errore. Chi vuole
    trattarlo come un errore ha lo stesso testo dentro la diagnostica.
    """
    print(f"[rilevatore-parlato] {testo}", file=sys.stderr)


def carica_rilevatore(ambiente: dict | None = None, riusa: bool = True) -> dict:
    """Carica il modello UNA volta per processo. Non solleva MAI.

    Torna { pronto, motivo, percorso, sessione }: 'pronto' falso con il
    'motivo' scritto per esteso e' un esito legittimo, non un guasto. E' il
    vincolo piu' importante di tutto il rilevatore — un modello che manca non
    deve fermare un montaggio che senza di lui girava benissimo — ed e' per
    questo che qui si intercetta Exception e non un elenco di eccezioni note:
    onnxruntime, quando non trova le sue DLL, non solleva ImportError.

    'riusa' a falso serve solo alle prove, che devono poter ripercorrere la
    strada del fallimento senza ereditare la memoria del giro precedente.
    """
    global _CARICAMENTO
    if riusa and _CARICAMENTO is not None:
        return _CARICAMENTO

    esito = {"pronto": False, "motivo": None, "percorso": None, "sessione": None}
    candidati = percorsi_modello(ambiente)
    percorso = next((p for p in candidati if p and os.path.isfile(p)), None)
    if percorso is None:
        esito["motivo"] = (
            f"il modello '{NOME_MODELLO}' non si trova in nessuno di questi posti: "
            + ", ".join(f"'{p}'" for p in candidati)
            + f". Mettilo in {os.path.join(_CARTELLA_QUI, 'models')} oppure indica "
            f"il suo percorso in {VARIABILE_MODELLO}. Intanto il taglio va avanti "
            "con trascritto e livello, come prima")
    else:
        try:
            import onnxruntime

            opzioni = onnxruntime.SessionOptions()
            # Un thread solo, e non e' pigrizia: sul worker girano piu' clip in
            # parallelo, e un modello che si prende tutti i core li toglie a
            # ffmpeg, che e' il vero collo di bottiglia del giro.
            opzioni.inter_op_num_threads = 1
            opzioni.intra_op_num_threads = 1
            opzioni.log_severity_level = 4  # i suoi avvisi non sono nostri
            sessione = onnxruntime.InferenceSession(
                percorso, providers=["CPUExecutionProvider"], sess_options=opzioni)
            esito.update({"pronto": True, "percorso": percorso, "sessione": sessione})
        except Exception as guasto:
            esito["motivo"] = (
                f"il modello '{percorso}' non si e' caricato ({type(guasto).__name__}: "
                f"{str(guasto).strip()[:200]}). Il taglio va avanti con trascritto "
                "e livello, come prima")

    if esito["motivo"]:
        _avvisa(esito["motivo"])
    if riusa:
        _CARICAMENTO = esito
    return esito


def dimentica_rilevatore() -> None:
    """Butta via la memoria del caricamento. Serve alle prove, non al giro."""
    global _CARICAMENTO
    _CARICAMENTO = None


# ---------------------------------------------------- i campioni dal girato

def comando_campioni(video, inizio: float, durata: float) -> list[str]:
    """Il comando ffmpeg che tira fuori i campioni grezzi per il rilevatore.

    Separato dall'esecuzione come comando_livelli, e per la stessa ragione: la
    forma del comando si legge e si prova senza avere ffmpeg installato.

    STESSA FINESTRA E STESSA GRIGLIA DEI LIVELLI, e non e' un dettaglio di
    stile. Il '-ss'/'-t' e' identico a quello di comando_livelli e aformat
    porta a mono 16 kHz come li': cosi' la cella k del rilevatore e la cella k
    dei livelli sono lo STESSO tratto di audio. E' l'unica ragione per cui le
    due maschere si possono confrontare, e una griglia che si spezza si spezza
    in silenzio, senza errori (SPEC/60 §5.3.1).

    Niente pre-enfasi, niente rimozione della continua, niente normalizzazione,
    niente finestratura: i campioni entrano nel modello come escono dal
    decodificatore (SPEC/60 §5.5, punto 2). Il downmix a mono lo fa ffmpeg con
    la sua matrice — la specifica non ne dichiara una (SPEC/60 §12.5), quindi
    non ne imponiamo una nostra.
    """
    return [
        "ffmpeg", "-v", "error", "-nostdin",
        "-ss", f"{float(inizio):.3f}", "-t", f"{float(durata):.3f}",
        "-i", str(video),
        "-map", "0:a:0",
        "-af",
        (f"aformat=sample_fmts=flt:sample_rates={FREQUENZA_ANALISI}:"
         "channel_layouts=mono"),
        "-f", "f32le", "-",
    ]


def estrai_campioni(video, inizio: float, fine: float):
    """I campioni float32 mono a 16 kHz della finestra chiesta. Impura.

    Torna un vettore numpy. Solleva MisuraNonRiuscita se ffmpeg non ce la fa:
    chi chiama dal giro vero passa da verifica_col_rilevatore, che intercetta e
    ripiega sulle due fonti di sempre.
    """
    import numpy

    durata = float(fine) - float(inizio)
    if durata <= 0:
        return numpy.zeros(0, dtype=numpy.float32)
    esito = subprocess.run(comando_campioni(video, inizio, durata),
                           capture_output=True)
    if esito.returncode != 0:
        messaggio = (esito.stderr or b"").decode("utf-8", "replace").strip()[:300]
        raise MisuraNonRiuscita(
            f"campioni audio non estraibili da '{video}': {messaggio}")
    grezzi = esito.stdout or b""
    # Un troncone di byte non multiplo di 4 vorrebbe dire un campione a meta':
    # si scarta la coda invece di leggere spazzatura come se fosse audio.
    utili = len(grezzi) - (len(grezzi) % 4)
    return numpy.frombuffer(grezzi[:utili], dtype="<f4")


# ------------------------------------------------------------ l'inferenza

def probabilita_parlato(campioni, sessione,
                        blocco_finestre: int = BLOCCO_FINESTRE) -> list[float]:
    """Da campioni a UNA probabilita' di parlato per cella da 0,032 s.

    Il modello e' ricorrente: la probabilita' della finestra k dipende da tutte
    le finestre precedenti dello stesso audio (SPEC/60 §5.6, punto 9). Per
    questo lo stato (h, c) e il contesto attraversano il confine fra un blocco
    e il successivo, e per questo l'analisi NON e' divisibile: due meta'
    analizzate separatamente non danno lo stesso risultato dell'intero. Il
    blocco qui non divide l'analisi, divide solo l'allocazione — e
    prova_silenzi.py verifica che il vettore esca IDENTICO al variare di
    blocco_finestre.

    Le finestre non si sovrappongono e l'ultima si riempie di zeri fino a 512
    campioni: non si scarta mai (SPEC/60 §5.6, punto 9). Le celle sono quindi
    ceil(M/512), in aritmetica intera come in fondamenta.celle_in.
    """
    import numpy

    audio = numpy.ascontiguousarray(campioni, dtype=numpy.float32).ravel()
    quanti = int(audio.shape[0])
    if quanti <= 0:
        return []
    manca = (-quanti) % CAMPIONI_CELLA
    if manca:
        audio = numpy.concatenate([audio, numpy.zeros(manca, dtype=numpy.float32)])
    finestre = audio.reshape(-1, CAMPIONI_CELLA)

    stato_h = numpy.zeros((1, 1, 128), dtype=numpy.float32)
    stato_c = numpy.zeros((1, 1, 128), dtype=numpy.float32)
    passo = max(1, int(blocco_finestre))
    fuori: list[float] = []
    for da in range(0, finestre.shape[0], passo):
        pezzo = finestre[da:da + passo]
        # Il contesto della finestra k sono gli ultimi CONTESTO_VAD campioni
        # della finestra k-1. Si costruisce QUI, blocco per blocco, e non una
        # volta sola sull'intero file: costruirlo tutto insieme rifarebbe una
        # copia larga 576 colonne dell'audio intero, cioe' esattamente la
        # memoria che il blocco esiste per non allocare.
        contesto = numpy.zeros((pezzo.shape[0], CONTESTO_VAD), dtype=numpy.float32)
        if pezzo.shape[0] > 1:
            contesto[1:] = pezzo[:-1, -CONTESTO_VAD:]
        if da > 0:
            contesto[0] = finestre[da - 1, -CONTESTO_VAD:]
        ingresso = numpy.concatenate([contesto, pezzo], axis=1)
        uscita, stato_h, stato_c = sessione.run(
            None, {"input": ingresso, "h": stato_h, "c": stato_c})
        fuori.extend(float(v) for v in numpy.asarray(uscita).ravel())
    return fuori


# --------------------------------------------------------- la binarizzazione

def binarizza(probabilita, durata_cella_s: float = DURATA_CELLA_S,
              entrata: float = SOGLIA_ENTRATA, uscita: float = SOGLIA_USCITA,
              parlato_minimo_s: float = PARLATO_MINIMO_S,
              silenzio_minimo_s: float = SILENZIO_MINIMO_S,
              padding_s: float = PADDING_RILEVAMENTO_S) -> list[dict]:
    """Da una sequenza di probabilita' agli intervalli di parlato, in secondi.

    E' il pezzo che nel corpus NON C'E': SPEC/60 §5.7 e §12.1 dichiarano che
    soglia, isteresi, durate minime, fusione e padding vivono nella
    configurazione predefinita di Silero, assente dal loro repository. Il
    corpus dice solo cosa DEVE fare un binarizzatore compatibile — cinque punti
    — e questi sono quei cinque punti nell'ordine in cui vanno fatti.

    I tempi tornano RELATIVI all'inizio dell'audio analizzato, monotoni e non
    sovrapposti, e non superano mai K·0,032 s: oltre quel confine la loro (F18)
    li troncherebbe perdendo informazione senza dirlo.

    L'ORDINE FRA FUSIONE E DURATA MINIMA E' NOSTRO, e va contro la numerazione
    del corpus, che elenca prima la durata minima di parlato e poi la fusione.
    Si fonde PRIMA. Dentro una frase le occlusive lasciano buchi di 50-80 ms,
    quindi «pero'» arriva al binarizzatore come cinque accensioni da 0,12 s:
    scartando prima le accensioni corte si butterebbe via la frase intera, che
    dopo la fusione sarebbe un segmento solo lungo un secondo. Fondendo prima,
    al punto 2 restano da scartare solo le accensioni davvero isolate, che e'
    quello che il punto 2 vuole.

    Funzione PURA e senza numpy: si prova senza modello, senza ffmpeg e senza
    rete, ed e' il motivo per cui e' separata dall'inferenza.
    """
    valori = [float(p) for p in probabilita]
    if not valori:
        return []
    cella = float(durata_cella_s)
    fine_massima = len(valori) * cella

    # 1) l'isteresi a due soglie. Si ENTRA sopra 'entrata', si ESCE solo sotto
    #    'uscita', e in mezzo si resta dove si era: una soglia sola su una
    #    probabilita' rumorosa frammenta (§12.1, punto 1).
    acceso = False
    corse: list[list[int]] = []
    for indice, p in enumerate(valori):
        if not acceso and p >= entrata:
            acceso = True
            corse.append([indice, indice + 1])
        elif acceso and p < uscita:
            acceso = False
        elif acceso:
            corse[-1][1] = indice + 1

    segmenti = [{"inizio": lo * cella, "fine": hi * cella} for lo, hi in corse]

    # 2) la fusione: due segmenti separati da meno di silenzio_minimo_s sono lo
    #    stesso segmento (§12.1, punto 3).
    fusi: list[dict] = []
    for segmento in segmenti:
        if fusi and segmento["inizio"] - fusi[-1]["fine"] < float(silenzio_minimo_s) - EPS:
            fusi[-1]["fine"] = max(fusi[-1]["fine"], segmento["fine"])
        else:
            fusi.append(dict(segmento))

    # 3) le accensioni isolate troppo corte non sono parlato (§12.1, punto 2).
    lunghi = [s for s in fusi
              if s["fine"] - s["inizio"] >= float(parlato_minimo_s) - EPS]

    # 4) il padding simmetrico, per non troncare le consonanti ai bordi
    #    (§12.1, punto 4). E' il padding della RILEVAZIONE: quello del TAGLIO
    #    e' MARGINE_PARLATO_S e sta piu' su (SPEC/60 §5.7).
    imbottiti = [{"inizio": max(0.0, s["inizio"] - float(padding_s)),
                  "fine": min(fine_massima, s["fine"] + float(padding_s))}
                 for s in lunghi]

    # 5) il padding puo' aver fatto toccare due segmenti vicini: si rifondono,
    #    perche' il contratto dice monotoni e NON sovrapposti (§12.1, punto 5)
    #    e il codice a valle l'ordinamento lo da' per buono.
    fuori: list[dict] = []
    for segmento in imbottiti:
        if fuori and segmento["inizio"] <= fuori[-1]["fine"] + EPS:
            fuori[-1]["fine"] = max(fuori[-1]["fine"], segmento["fine"])
        else:
            fuori.append(dict(segmento))
    return [{"inizio": fondamenta.arrotonda_decimale(s["inizio"]),
             "fine": fondamenta.arrotonda_decimale(s["fine"])} for s in fuori]


# ------------------------------------------------------- dove c'e' la voce

def segmenti_di_parlato(video, inizio: float, fine: float,
                        caricamento: dict | None = None) -> dict:
    """Dove c'e' voce umana nella finestra chiesta, trascritta o no.

    Torna { disponibile, segmenti, finestre, motivo }, con i tempi in secondi
    del GIRATO — cioe' gia' spostati di 'inizio', come fa interpreta_livelli.

    'disponibile' falso NON e' un guasto: e' il caso normale in cui il modello
    non c'e'. Chi chiama continua con le due fonti di sempre.

    UN AVVERTIMENTO CHE VALE LA PENA SCRIVERE: il modello e' ricorrente, quindi
    le probabilita' dipendono da dove comincia l'audio che gli si da'. Qui gli
    si da' la FINESTRA DELLA CLIP e non il girato intero — la stessa che ffmpeg
    decodifica per i livelli — e questo vuol dire che le probabilita' di una
    clip non sono, cella per cella, quelle che uscirebbero analizzando il
    girato dall'inizio. E' una scelta: analizzare venti minuti per verificare
    tre pause di una clip da trenta secondi costerebbe quaranta volte tanto, e
    il rilevatore qui serve a vetare dentro quella finestra, non a produrre una
    maschera del girato.
    """
    if caricamento is None:
        caricamento = carica_rilevatore()
    if not caricamento.get("pronto"):
        return {"disponibile": False, "segmenti": [], "finestre": 0,
                "motivo": caricamento.get("motivo")}

    campioni = estrai_campioni(video, inizio, fine)
    if len(campioni) == 0:
        # Nessun campione: nessuna cella, nessun segmento, e si dice che si e'
        # guardato (SPEC/60 §5.6, punto 5). Non e' «non lo so»: e' «non c'e'».
        return {"disponibile": True, "segmenti": [], "finestre": 0, "motivo": None}

    probabilita = probabilita_parlato(campioni, caricamento["sessione"])
    base = float(inizio)
    segmenti = [{"inizio": fondamenta.arrotonda_decimale(base + s["inizio"]),
                 "fine": fondamenta.arrotonda_decimale(base + s["fine"])}
                for s in binarizza(probabilita)]
    return {"disponibile": True, "segmenti": segmenti,
            "finestre": len(probabilita), "motivo": None}


def parlato_dentro(buco: dict, segmenti: list[dict]) -> float:
    """Il piu' LUNGO tratto CONTINUO di parlato dentro il buco, in secondi.

    Continuo e non totale, e la differenza conta. Un buco puo' avere due code
    di parlato da 0,12 s attaccate ai suoi due bordi — la coda della frase di
    prima e l'attacco di quella dopo, allargate dal padding della rilevazione —
    e sommandole si arriverebbe a 0,24 s di «parlato dentro la pausa» che
    dentro la pausa non c'e'. Il piu' lungo tratto continuo non ci casca.

    Dove sbaglia, sbaglia dalla parte di NON vetare, cioe' verso il taglio che
    la pipeline fa gia' oggi: acceso il rilevatore, i video cambiano il meno
    possibile e solo dove c'e' davvero una frase.
    """
    piu_lungo = 0.0
    for segmento in segmenti:
        sovrapposto = (min(float(buco["fine"]), float(segmento["fine"]))
                       - max(float(buco["inizio"]), float(segmento["inizio"])))
        if sovrapposto > piu_lungo:
            piu_lungo = sovrapposto
    return piu_lungo


def veta_per_parlato(buchi: list[dict], segmenti: list[dict],
                     quanto_veta_s: float = PARLATO_CHE_VETA_S
                     ) -> tuple[list[dict], list[dict]]:
    """Toglie dai buchi quelli dentro cui il rilevatore sente parlare.

    Torna (tenuti, vetati), stessa forma e stessa disciplina di
    veta_per_livello: i tenuti sono un SOTTOINSIEME dei buchi in ingresso, mai
    di piu' e mai spostati. Il rilevatore puo' solo togliere tagli.

    Si vetano solo i buchi con "verifica_livello": true. Un buco nato da parole
    nominate passa sempre — il cliente ha detto quali parole togliere, e il
    fatto che li' dentro ci sia della voce e' esattamente il punto, non
    un'obiezione.
    """
    tenuti: list[dict] = []
    vetati: list[dict] = []
    for buco in buchi:
        if not buco.get("verifica_livello", True):
            tenuti.append(buco)
            continue
        quanto = parlato_dentro(buco, segmenti)
        if quanto < float(quanto_veta_s) - EPS:
            tenuti.append(buco)
            continue
        vetati.append({
            **buco,
            "parlato_s": fondamenta.arrotonda_decimale(quanto, 2),
            "motivo_veto": (
                f"dentro questa pausa il rilevatore sente {quanto:.2f} s di parlato "
                f"di fila, sopra i {float(quanto_veta_s):.2f} s che bastano a "
                "chiamarlo parlato: qui si sta parlando anche se il trascritto non "
                "ha scritto niente. La lascio dov'e'"),
        })
    return tenuti, vetati


def parlato_come_parole(segmenti: list[dict]) -> list[dict]:
    """I segmenti nella forma che soglia_relativa si aspetta: {start, end}.

    Serve al caso che il file dichiara in testa e che oggi non ha risposta:
    calibrare la soglia quando il trascritto NON c'e' (qa_check.py lavora su
    uno short gia' fatto, senza parole). Con questo, «il livello del parlato di
    questa registrazione» si puo' misurare anche li'.
    """
    return [{"start": float(s["inizio"]), "end": float(s["fine"])} for s in segmenti]


# ------------------------------------------------- l'unico punto di ingresso

def verifica_col_rilevatore(video, inizio: float, fine: float, buchi: list[dict],
                            ambiente: dict | None = None
                            ) -> tuple[list[dict], list[dict], dict]:
    """La terza verifica, chiavi in mano. Torna (tenuti, vetati, diagnostica).

    E' l'UNICA funzione che il giro vero deve chiamare, ed e' scritta perche'
    chiamarla non possa rompere niente:

      - SPENTA (di fabbrica) torna i buchi INTATTI e non lancia ffmpeg, non
        carica modelli, non costa niente: i video restano identici a ieri;
      - accesa ma senza modello, torna i buchi INTATTI e scrive perche';
      - accesa e con qualunque guasto in mezzo — ffmpeg che non parte, numpy
        che manca, il modello che sbaglia forma di tensore — torna i buchi
        INTATTI e mette il guasto negli avvisi.

    In tutti e tre i casi il montaggio va avanti esattamente come prima. Solo
    nel caso in cui tutto funziona i buchi possono DIMINUIRE, mai aumentare.

    Nella diagnostica nessun campo sparisce mai: «non lo so» e «zero» non
    devono avere la stessa faccia (stessa regola di risolvi_taglio in render.py).

    NESSUNO LA CHIAMA ANCORA. Il posto e' risolvi_taglio in render.py, dentro
    il passo 2, subito dopo veta_per_livello e prima della durata minima:

        buchi, vetati = silenzi.veta_per_livello(buchi, celle, soglia)
        esito["vetati"] = vetati
        buchi, vetati_vad, esito["rilevatore"] = silenzi.verifica_col_rilevatore(
            video, inizio, fine, buchi)
        esito["vetati"] += vetati_vad

    Va DOPO il livello e non prima, e non e' indifferente: il livello costa una
    passata di ffmpeg che si fa comunque, il rilevatore costa una seconda
    decodifica piu' l'inferenza. Mettendolo dopo, lavora solo sui buchi che il
    livello ha gia' lasciato passare, che sono quasi sempre pochi.
    """
    diagnostica = {
        "acceso": rilevatore_acceso(ambiente),
        "disponibile": False,
        "segmenti": None,
        "finestre": None,
        "parlato_s": None,
        "avvisi": [],
    }
    if not diagnostica["acceso"]:
        return list(buchi), [], diagnostica

    try:
        esito = segmenti_di_parlato(video, inizio, fine)
    except Exception as guasto:
        diagnostica["avvisi"].append(
            f"rilevatore di parlato saltato ({type(guasto).__name__}: "
            f"{str(guasto).strip()[:200]}): il taglio va avanti con trascritto e "
            "livello, come prima")
        _avvisa(diagnostica["avvisi"][-1])
        return list(buchi), [], diagnostica

    if not esito["disponibile"]:
        if esito.get("motivo"):
            diagnostica["avvisi"].append(esito["motivo"])
        return list(buchi), [], diagnostica

    segmenti = esito["segmenti"]
    diagnostica.update({
        "disponibile": True,
        "segmenti": len(segmenti),
        "finestre": esito["finestre"],
        "parlato_s": fondamenta.arrotonda_decimale(
            sum(s["fine"] - s["inizio"] for s in segmenti), 2),
    })
    tenuti, vetati = veta_per_parlato(buchi, segmenti)
    return tenuti, vetati, diagnostica
