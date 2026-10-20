"""Prove del rilevatore neurale di parlato — la terza fonte di silenzi.py.

    py prova_silenzi.py

SENZA RETE E SENZA CHIAVI. Il segnale se lo costruisce a mano — silenzio
digitale, tono puro, rumore bianco, tono modulato — invece di scaricare
campioni: un campione scaricato e' una prova che smette di girare il giorno in
cui la rete non c'e', ed e' esattamente il giorno in cui serve.

LE PROVE CHE CONTANO DI PIU' NON HANNO BISOGNO DEL MODELLO, ed e' voluto.
Quelle sono le prove del RIPIEGO: modello assente, modello rotto, ffmpeg che
non parte, interruttore spento. In tutti quei casi il taglio che gira oggi
deve uscire IDENTICO, ed e' il vincolo piu' importante di tutto il rilevatore.
Girano sempre, ovunque, anche su una macchina senza onnxruntime.

Le prove che il modello ce l'hanno per forza (l'inferenza vera, l'equivalenza
a blocchi, il giro completo su un file wav) si SALTANO quando il modello o
ffmpeg non ci sono, e la riga finale dice quante ne sono state saltate. Una
prova saltata non e' una prova passata e non deve sembrarlo.

UN'ONESTA' SUL SEGNALE «PARLATO». Il tono a 200 Hz modulato a 5 Hz non e' una
voce: e' un segnale sintetico che Silero CLASSIFICA come parlato (misurato il
21/08/2026: probabilita' mediana 0,895 contro 0,003 del silenzio, 0,001 del
tono puro e 0,035 del rumore bianco). Serve a provare l'impianto — che una
probabilita' alta diventi un segmento e che un segmento diventi un veto — non
la bravura del modello sul parlato italiano vero. Quella si misura sui giri
veri, e in fondo al risultato c'e' scritto su quali.

Esce 0 se tutte le prove eseguite passano, 1 alla prima che fallisce.
"""
from __future__ import annotations

import contextlib
import io
import math
import os
import shutil
import struct
import sys
import tempfile
import wave
from pathlib import Path

import silenzi

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FALLITE: list[str] = []
SALTATE: list[str] = []
PASSATE = 0


def prova(nome: str, ottenuto, atteso) -> None:
    global PASSATE
    if ottenuto == atteso:
        PASSATE += 1
        print(f"  ok   {nome}")
    else:
        FALLITE.append(nome)
        print(f"  NO   {nome}\n       atteso   {atteso}\n       ottenuto {ottenuto}")


def prova_vero(nome: str, condizione, dettaglio: str = "") -> None:
    global PASSATE
    if condizione:
        PASSATE += 1
        print(f"  ok   {nome}")
    else:
        FALLITE.append(nome)
        print(f"  NO   {nome}" + (f"\n       {dettaglio}" if dettaglio else ""))


def salta(nome: str, perche: str) -> None:
    SALTATE.append(nome)
    print(f"  --   {nome}  (saltata: {perche})")


def vicino(a, b, tolleranza=1e-6) -> bool:
    return abs(float(a) - float(b)) <= tolleranza


# --------------------------------------------------------------- materiale

DC = silenzi.DURATA_CELLA_S  # 0,032 s


def probabilita(*pezzi) -> list[float]:
    """Una sequenza di probabilita' scritta come (valore, quante celle).

    Si scrivono a mano apposta: il binarizzatore e' una funzione pura e la sua
    prova non deve dipendere da cosa un modello pensa oggi di un tono.
    """
    fuori: list[float] = []
    for valore, quante in pezzi:
        fuori.extend([float(valore)] * int(quante))
    return fuori


def buco(inizio: float, fine: float, verifica: bool = True) -> dict:
    return {"inizio": inizio, "fine": fine, "motivo": "silenzio",
            "parole": None, "verifica_livello": verifica}


def segnale(secondi: float, tipo: str, ampiezza: float = 0.3):
    """Il segnale costruito a mano, campione per campione. Niente numpy.

    Deve poter girare anche dove numpy non c'e': le prove del ripiego non
    devono dipendere da una libreria che il ripiego esiste per non richiedere.
    """
    sr = silenzi.FREQUENZA_ANALISI
    quanti = int(secondi * sr)
    if tipo == "silenzio":
        return [0.0] * quanti
    if tipo == "tono":
        return [ampiezza * math.sin(2 * math.pi * 440 * i / sr) for i in range(quanti)]
    if tipo == "rumore":
        # Un generatore congruenziale scritto qui: `random` cambia algoritmo
        # fra versioni di Python, e una prova che cambia risultato con
        # l'interprete non e' una prova.
        stato = 20260821
        fuori = []
        for _ in range(quanti):
            stato = (1103515245 * stato + 12345) % (1 << 31)
            fuori.append(ampiezza * (stato / (1 << 30) - 1.0))
        return fuori
    if tipo == "parlato":
        # Tono a 200 Hz modulato a 5 Hz: vedi l'onesta' in testa al file.
        return [ampiezza * math.sin(2 * math.pi * 200 * i / sr)
                * (0.5 + 0.5 * math.sin(2 * math.pi * 5 * i / sr))
                for i in range(quanti)]
    raise ValueError(f"segnale sconosciuto: {tipo}")


def scrivi_wav(cartella: Path, pezzi: list[tuple[float, str]]) -> Path:
    """Un wav a 16 kHz mono costruito dai pezzi chiesti. Solo stdlib."""
    campioni: list[float] = []
    for secondi, tipo in pezzi:
        campioni.extend(segnale(secondi, tipo))
    percorso = cartella / "finto.wav"
    with wave.open(str(percorso), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(silenzi.FREQUENZA_ANALISI)
        f.writeframes(b"".join(
            struct.pack("<h", max(-32768, min(32767, int(v * 32767))))
            for v in campioni))
    return percorso


def modello_disponibile() -> dict | None:
    """Il caricamento vero, o None se il modello qui non c'e'."""
    silenzi.dimentica_rilevatore()
    with contextlib.redirect_stderr(io.StringIO()):
        esito = silenzi.carica_rilevatore(riusa=False)
    return esito if esito["pronto"] else None


# ===========================================================================
print("\n— l'interruttore, e il fatto che di fabbrica e' spento")

prova("senza variabile il rilevatore e' spento", silenzi.rilevatore_acceso({}), False)
prova("variabile vuota, spento", silenzi.rilevatore_acceso({"MOTORE_RILEVATORE_PARLATO": ""}), False)
prova("variabile a 0, spento", silenzi.rilevatore_acceso({"MOTORE_RILEVATORE_PARLATO": "0"}), False)
prova("variabile a una parola qualunque, spento",
      silenzi.rilevatore_acceso({"MOTORE_RILEVATORE_PARLATO": "forse"}), False)
prova("variabile a 1, acceso", silenzi.rilevatore_acceso({"MOTORE_RILEVATORE_PARLATO": "1"}), True)
prova("scritto da una persona: 'si', con spazi e maiuscole, acceso",
      silenzi.rilevatore_acceso({"MOTORE_RILEVATORE_PARLATO": "  SI "}), True)
prova("e anche 'true'", silenzi.rilevatore_acceso({"MOTORE_RILEVATORE_PARLATO": "true"}), True)

# La prova che vale piu' delle altre sei: l'ambiente VERO di questa macchina.
# Se qualcuno un giorno accendesse il rilevatore di fabbrica, e' qui che si
# rompe, e si rompe con scritto perche'.
prova_vero("nell'ambiente di questa macchina il rilevatore risulta spento",
           not silenzi.rilevatore_acceso(),
           f"{silenzi.VARIABILE_INTERRUTTORE} vale "
           f"{os.environ.get(silenzi.VARIABILE_INTERRUTTORE)!r}: acceso di fabbrica "
           "i video cambiano, e questo non deve succedere per sbaglio")


# ===========================================================================
print("\n— dove si cerca il modello, e che non si va MAI a rete")

posti = silenzi.percorsi_modello({})
prova_vero("si cerca in almeno un posto", len(posti) >= 1, str(posti))
prova_vero("nessun posto e' un indirizzo di rete",
           not any(str(p).lower().startswith(("http://", "https://", "ftp://")) for p in posti),
           str(posti))
prova_vero("models/ accanto alla pipeline e' fra i posti",
           any(str(p).endswith(os.path.join("models", silenzi.NOME_MODELLO)) for p in posti),
           str(posti))
indicato = silenzi.percorsi_modello({silenzi.VARIABILE_MODELLO: "/un/posto/mio.onnx"})
prova("la variabile d'ambiente vince su tutto", indicato[0], "/un/posto/mio.onnx")


# ===========================================================================
print("\n— IL RIPIEGO: modello assente o rotto, e il taglio va avanti lo stesso")

vero_percorsi = silenzi.percorsi_modello
try:
    silenzi.percorsi_modello = lambda ambiente=None: ["/questo/non/esiste/mai.onnx"]
    silenzi.dimentica_rilevatore()
    errori = io.StringIO()
    with contextlib.redirect_stderr(errori):
        assente = silenzi.carica_rilevatore(riusa=False)
    prova("modello assente: non si solleva niente, si torna 'non pronto'", assente["pronto"], False)
    prova_vero("e c'e' scritto quale file manca",
               silenzi.NOME_MODELLO in (assente["motivo"] or ""), assente["motivo"])
    prova_vero("e c'e' scritto che il taglio va avanti come prima",
               "come prima" in (assente["motivo"] or ""), assente["motivo"])
    prova_vero("l'avviso finisce su stderr", "rilevatore-parlato" in errori.getvalue(),
               errori.getvalue())

    # Il fallimento si RICORDA: ritentare a ogni clip costa un errore per clip
    # e la risposta non cambia.
    silenzi.dimentica_rilevatore()
    with contextlib.redirect_stderr(io.StringIO()):
        primo = silenzi.carica_rilevatore()
        secondo = silenzi.carica_rilevatore()
    prova_vero("il fallimento si ricorda: la seconda chiamata torna lo stesso oggetto",
               primo is secondo)

    # E la prova che conta davvero: i buchi escono intatti.
    buchi = [buco(3.0, 4.0), buco(7.0, 8.5), buco(9.0, 9.6, verifica=False)]
    with contextlib.redirect_stderr(io.StringIO()):
        tenuti, vetati, diag = silenzi.verifica_col_rilevatore(
            "/un/video/che/non/esiste.mp4", 0.0, 10.0, buchi,
            ambiente={"MOTORE_RILEVATORE_PARLATO": "1"})
    prova("acceso ma senza modello: i buchi escono INTATTI", tenuti, buchi)
    prova("e non se ne veta nessuno", vetati, [])
    prova("la diagnostica dice che era acceso", diag["acceso"], True)
    prova("e che il modello non era disponibile", diag["disponibile"], False)
    prova_vero("con l'avviso dentro", len(diag["avvisi"]) == 1, str(diag["avvisi"]))
finally:
    silenzi.percorsi_modello = vero_percorsi
    silenzi.dimentica_rilevatore()

# Un file che c'e' ma non e' un modello: si carica? no. Si rompe il giro? no.
with tempfile.TemporaryDirectory() as tmp:
    finto = Path(tmp) / "rotto.onnx"
    finto.write_bytes(b"questo non e' un modello onnx, sono solo dei byte")
    silenzi.dimentica_rilevatore()
    with contextlib.redirect_stderr(io.StringIO()):
        rotto = silenzi.carica_rilevatore(
            ambiente={silenzi.VARIABILE_MODELLO: str(finto)}, riusa=False)
    prova("modello rotto: non pronto, e nessuna eccezione fuori", rotto["pronto"], False)
    prova_vero("con il motivo scritto per esteso", bool(rotto["motivo"]), str(rotto))
silenzi.dimentica_rilevatore()


# ===========================================================================
print("\n— SPENTO: non si carica niente, non si lancia ffmpeg, non cambia niente")

buchi = [buco(3.0, 4.0), buco(7.0, 8.5)]
tenuti, vetati, diag = silenzi.verifica_col_rilevatore(
    "/un/video/che/non/esiste.mp4", 0.0, 10.0, buchi, ambiente={})
prova("spento: i buchi escono intatti", tenuti, buchi)
prova("spento: nessun veto", vetati, [])
prova("spento: la diagnostica lo dice", diag["acceso"], False)
prova_vero("spento: nessun avviso, perche' non c'e' niente da avvisare",
           diag["avvisi"] == [], str(diag["avvisi"]))
prova("spento: il modello non e' stato nemmeno cercato", silenzi._CARICAMENTO, None)
prova_vero("spento: la lista tornata e' una copia, non quella di chi ha chiamato",
           tenuti is not buchi)


# ===========================================================================
print("\n— il binarizzatore: i cinque punti del contratto (SPEC/60 §12.1)")

prova("niente probabilita', niente segmenti", silenzi.binarizza([]), [])
prova("tutto sotto la soglia: nessun segmento",
      silenzi.binarizza(probabilita((0.1, 100))), [])

# 1) l'isteresi. Una probabilita' che sta in mezzo alle due soglie non fa
#    entrare in parlato, ma non ne fa nemmeno uscire.
in_mezzo = silenzi.binarizza(probabilita((0.42, 30)))
prova("in mezzo alle due soglie, da spento, si resta spenti", in_mezzo, [])
tiene = silenzi.binarizza(probabilita((0.9, 20), (0.42, 20), (0.9, 20)))
prova_vero("in mezzo alle due soglie, da acceso, si resta accesi: un solo segmento",
           len(tiene) == 1, str(tiene))
spegne = silenzi.binarizza(probabilita((0.9, 20), (0.2, 20), (0.9, 20)),
                           silenzio_minimo_s=0.0)
prova_vero("sotto la soglia di uscita si esce davvero: due segmenti",
           len(spegne) == 2, str(spegne))

# 2) la durata minima di parlato: un'accensione isolata non e' parlato.
lampo = silenzi.binarizza(probabilita((0.05, 20), (0.9, 3), (0.05, 20)))
prova("tre celle accese (0,096 s) non sono parlato", lampo, [])
abbastanza = silenzi.binarizza(probabilita((0.05, 20), (0.9, 10), (0.05, 20)))
prova_vero("dieci celle (0,32 s) lo sono", len(abbastanza) == 1, str(abbastanza))

# 3) la fusione: due segmenti separati da meno di 0,10 s sono lo stesso.
#    E' il caso vero delle occlusive dentro una parola.
occlusiva = silenzi.binarizza(probabilita((0.9, 10), (0.05, 2), (0.9, 10)))
prova_vero("un buco da 0,064 s dentro il parlato non lo spezza",
           len(occlusiva) == 1, str(occlusiva))
pausa_vera = silenzi.binarizza(probabilita((0.9, 10), (0.05, 20), (0.9, 10)))
prova_vero("un buco da 0,64 s si', lo spezza", len(pausa_vera) == 2, str(pausa_vera))

# La ragione per cui si fonde PRIMA e si scarta DOPO, provata sul caso che la
# motiva: cinque accensioni corte separate da buchi da occlusiva sono UNA
# frase, e nell'ordine scritto nel corpus sparirebbero tutte.
frase_a_pezzi = silenzi.binarizza(probabilita(*(((0.9, 4), (0.05, 2)) * 5)))
prova_vero("cinque accensioni da 0,128 s a 0,064 s di distanza sono UNA frase, non zero",
           len(frase_a_pezzi) == 1, str(frase_a_pezzi))

# 4) il padding simmetrico, e il fatto che non esce dai bordi.
uno = silenzi.binarizza(probabilita((0.05, 10), (0.9, 20), (0.05, 10)))
prova_vero("il padding allarga di 0,03 s dal lato dell'inizio",
           vicino(uno[0]["inizio"], 10 * DC - silenzi.PADDING_RILEVAMENTO_S, 1e-3), str(uno))
prova_vero("e di 0,03 s dal lato della fine",
           vicino(uno[0]["fine"], 30 * DC + silenzi.PADDING_RILEVAMENTO_S, 1e-3), str(uno))
al_bordo = silenzi.binarizza(probabilita((0.9, 20)))
prova_vero("in testa il padding non va sotto zero", al_bordo[0]["inizio"] >= 0.0, str(al_bordo))
prova_vero("in coda non va oltre K celle: (F18) le troncherebbe in silenzio",
           al_bordo[0]["fine"] <= 20 * DC + 1e-9, str(al_bordo))

# 5) monotoni e non sovrapposti, anche dopo che il padding li ha fatti toccare.
#    Il buco e' UNA cella (0,032 s) e la fusione qui e' disattivata a 0,01 s,
#    quindi al punto 2 restano due segmenti; e' il padding — 0,03 s per lato,
#    cioe' 0,06 s di buco chiuso contro 0,032 — a farli combaciare.
vicini = silenzi.binarizza(probabilita((0.9, 10), (0.05, 1), (0.9, 10)),
                           silenzio_minimo_s=0.01)
prova_vero("due segmenti che il padding fa toccare si rifondono",
           len(vicini) == 1, str(vicini))
tanti = silenzi.binarizza(probabilita(*(((0.9, 10), (0.05, 20)) * 6)))
prova_vero("i segmenti escono ordinati e senza sovrapposizioni",
           all(tanti[i]["fine"] <= tanti[i + 1]["inizio"] for i in range(len(tanti) - 1)),
           str(tanti))
prova_vero("e ognuno ha fine dopo inizio",
           all(s["fine"] > s["inizio"] for s in tanti), str(tanti))

# La griglia: la cella del rilevatore e' la cella di fondamenta.py, non un'altra.
prova("la finestra del rilevatore e' la cella condivisa",
      silenzi.FINESTRA_VAD, silenzi.CAMPIONI_CELLA)
prova("e la cella dura 0,032 s esatti", round(DC, 6), 0.032)


# ===========================================================================
print("\n— il veto: quanto parlato serve, e perche' CONTINUO e non totale")

parlato = [{"inizio": 1.0, "fine": 2.0}, {"inizio": 5.0, "fine": 6.0}]

prova("dentro una pausa vuota il rilevatore non trova niente",
      silenzi.parlato_dentro(buco(3.0, 4.0), parlato), 0.0)
prova("dentro una pausa piena trova tutto il tratto",
      round(silenzi.parlato_dentro(buco(1.2, 1.8), parlato), 6), 0.6)
prova("un segmento che sborda conta solo per la parte dentro",
      round(silenzi.parlato_dentro(buco(1.7, 3.0), parlato), 6), 0.3)

# Il caso che decide fra «continuo» e «totale»: due code da 0,15 s ai due
# bordi. Sommate farebbero 0,30 s e veterebbero; continue fanno 0,15 e no.
code = [{"inizio": 2.85, "fine": 3.15}, {"inizio": 3.85, "fine": 4.15}]
prova("due code ai bordi contano per la piu' lunga, non per la somma",
      round(silenzi.parlato_dentro(buco(3.0, 4.0), code), 6), 0.15)
tenuti, vetati = silenzi.veta_per_parlato([buco(3.0, 4.0)], code)
prova("e quindi la pausa fra due frasi NON si veta", len(tenuti), 1)
prova("nessun veto per le code", vetati, [])

frase = [{"inizio": 3.2, "fine": 3.9}]
tenuti, vetati = silenzi.veta_per_parlato([buco(3.0, 4.0)], frase)
prova("una frase di 0,70 s dentro la pausa la veta", len(vetati), 1)
prova("e la pausa non passa", tenuti, [])
prova_vero("il veto dice quanti secondi di parlato ha sentito",
           vetati[0]["parlato_s"] == 0.7, str(vetati[0]))
prova_vero("e lo spiega a parole",
           "si sta parlando" in vetati[0]["motivo_veto"], vetati[0]["motivo_veto"])

corta = [{"inizio": 3.4, "fine": 3.6}]  # 0,20 s: sotto il quarto di secondo
tenuti, vetati = silenzi.veta_per_parlato([buco(3.0, 4.0)], corta)
prova("0,20 s di parlato non bastano a vetare (la soglia e' 0,25)", vetati, [])
prova("e la pausa resta tagliabile", len(tenuti), 1)

# Un buco nato da parole nominate passa sempre: il cliente ha detto quali
# parole togliere, e la voce li' dentro e' il punto, non un'obiezione.
nominato = silenzi.buco_da_parole(
    [{"idx": 0, "start": 3.0, "end": 3.4}, {"idx": 1, "start": 3.5, "end": 3.9}], 0, 1)
tenuti, vetati = silenzi.veta_per_parlato([nominato], [{"inizio": 2.0, "fine": 5.0}])
prova("un buco da parole nominate non si veta mai, nemmeno pieno di voce",
      tenuti, [nominato])
prova("e infatti non finisce fra i vetati", vetati, [])

# L'invariante dichiarata al cliente: il rilevatore puo' solo TOGLIERE tagli.
tutti = [buco(0.5, 1.5), buco(3.0, 4.0), buco(5.5, 6.5), buco(8.0, 9.0)]
tenuti, vetati = silenzi.veta_per_parlato(tutti, parlato)
prova_vero("i tenuti sono un sottoinsieme dei buchi in ingresso",
           all(t in tutti for t in tenuti), str(tenuti))
prova("tenuti + vetati fanno esattamente i buchi di partenza",
      len(tenuti) + len(vetati), len(tutti))
prova_vero("nessun buco e' stato spostato",
           all(t["inizio"] in [b["inizio"] for b in tutti] for t in tenuti), str(tenuti))


# ===========================================================================
print("\n— la soglia calibrata sul rilevatore, per quando il trascritto non c'e'")

# E' il caso che il file dichiara in testa: qa_check lavora su uno short gia'
# fatto e non ha parole, quindi oggi finisce sempre sul ripiego assoluto.
celle = [{"t_inizio": i * DC, "t_fine": (i + 1) * DC,
          "db": -10.0 if 1.0 <= i * DC < 2.0 else -55.0} for i in range(100)]
senza_parole = silenzi.soglia_relativa(celle, [])
prova("senza trascritto la soglia e' il ripiego assoluto",
      senza_parole["tipo"], "ripiego_assoluto")
col_rilevatore = silenzi.soglia_relativa(
    celle, silenzi.parlato_come_parole([{"inizio": 1.0, "fine": 2.0}]))
prova("con i segmenti del rilevatore torna a essere relativa",
      col_rilevatore["tipo"], "relativa")
prova("e si calibra sul parlato di questa registrazione",
      col_rilevatore["livello_parlato_db"], -10.0)
prova("la soglia esce al tetto, perche' -10-12 = -22", col_rilevatore["db"], -22.0)


# ===========================================================================
print("\n— il comando ffmpeg: la stessa finestra e la stessa griglia dei livelli")

comando = silenzi.comando_campioni("g.mp4", 12.5, 3.0)
livelli = silenzi.comando_livelli("g.mp4", 12.5, 3.0)
prova("il seek e' identico a quello dei livelli",
      comando[comando.index("-ss") + 1], livelli[livelli.index("-ss") + 1])
prova("e la durata pure", comando[comando.index("-t") + 1], livelli[livelli.index("-t") + 1])
filtro = comando[comando.index("-af") + 1]
prova_vero("si porta a 16 kHz", f"sample_rates={silenzi.FREQUENZA_ANALISI}" in filtro, filtro)
prova_vero("e a mono", "channel_layouts=mono" in filtro, filtro)
prova_vero("esce float32 grezzo", "f32le" in comando, str(comando))
prova_vero("niente normalizzazione, niente pre-enfasi, niente filtri in piu'",
           not any(x in filtro for x in ("loudnorm", "dynaudnorm", "highpass",
                                         "lowpass", "volume", "acompressor")), filtro)
prova_vero("si legge una sola traccia audio, la prima", "0:a:0" in comando, str(comando))


# ===========================================================================
print("\n— l'inferenza vera (serve il modello)")

caricamento = modello_disponibile()
if caricamento is None:
    salta("il modello dice parlato dove c'e' parlato", "modello non installato qui")
    salta("il modello NON dice parlato su silenzio, tono e rumore", "modello non installato qui")
    salta("il blocco non cambia il risultato", "modello non installato qui")
else:
    print(f"       modello: {caricamento['percorso']}")
    try:
        import numpy
    except ImportError:
        numpy = None

    if numpy is None:
        salta("il modello dice parlato dove c'e' parlato", "numpy non installato qui")
        salta("il modello NON dice parlato su silenzio, tono e rumore", "numpy non installato qui")
        salta("il blocco non cambia il risultato", "numpy non installato qui")
    else:
        def prob(nome: str, secondi: float = 2.0, blocco: int = silenzi.BLOCCO_FINESTRE):
            return silenzi.probabilita_parlato(
                segnale(secondi, nome), caricamento["sessione"], blocco_finestre=blocco)

        p_parlato = prob("parlato")
        p_silenzio = prob("silenzio")
        p_tono = prob("tono")
        p_rumore = prob("rumore")

        def mediana(v):
            return sorted(v)[len(v) // 2]

        prova_vero("il modello dice parlato dove c'e' parlato",
                   mediana(p_parlato) >= silenzi.SOGLIA_ENTRATA,
                   f"mediana {mediana(p_parlato):.4f}")
        prova_vero("il modello NON dice parlato su silenzio, tono e rumore",
                   max(max(p_silenzio), max(p_tono), max(p_rumore)) < silenzi.SOGLIA_USCITA,
                   f"massimi: silenzio {max(p_silenzio):.4f}, tono {max(p_tono):.4f}, "
                   f"rumore {max(p_rumore):.4f}")

        # Il numero di celle e' quello dichiarato: ceil(M/512), ultima finestra
        # riempita di zeri e mai scartata.
        attese = (int(2.0 * silenzi.FREQUENZA_ANALISI) + silenzi.CAMPIONI_CELLA - 1) \
            // silenzi.CAMPIONI_CELLA
        prova("una cella per ogni 512 campioni, ultima compresa", len(p_parlato), attese)

        # La promessa scritta accanto a BLOCCO_FINESTRE: il blocco cambia la
        # memoria, non il risultato. Qui si verifica numericamente, su un
        # segnale lungo abbastanza da attraversare piu' blocchi.
        lungo_intero = silenzi.probabilita_parlato(
            segnale(40.0, "parlato"), caricamento["sessione"], blocco_finestre=10 ** 9)
        lungo_a_blocchi = silenzi.probabilita_parlato(
            segnale(40.0, "parlato"), caricamento["sessione"], blocco_finestre=137)
        prova_vero("il blocco non cambia il risultato: vettori identici",
                   lungo_intero == lungo_a_blocchi,
                   f"massimo scarto "
                   f"{max(abs(a - b) for a, b in zip(lungo_intero, lungo_a_blocchi)):.6f}")


# ===========================================================================
print("\n— il giro intero su un file (serve il modello E ffmpeg)")

ha_ffmpeg = shutil.which("ffmpeg") is not None
if caricamento is None or not ha_ffmpeg:
    perche = "modello non installato qui" if caricamento is None else "ffmpeg non nel PATH"
    salta("dal wav ai segmenti di parlato", perche)
    salta("la pausa vuota resta tagliabile", perche)
    salta("la pausa che contiene parlato viene vetata", perche)
    salta("un video che non si apre non rompe il giro", perche)
else:
    with tempfile.TemporaryDirectory() as tmp:
        # silenzio 1 s | parlato 2 s | silenzio 2 s | parlato 2 s | silenzio 1 s
        finto = scrivi_wav(Path(tmp), [(1.0, "silenzio"), (2.0, "parlato"),
                                       (2.0, "silenzio"), (2.0, "parlato"),
                                       (1.0, "silenzio")])
        esito = silenzi.segmenti_di_parlato(finto, 0.0, 8.0, caricamento=caricamento)
        prova("dal wav ai segmenti di parlato", esito["disponibile"], True)
        trovati = esito["segmenti"]
        prova_vero("due tratti di parlato, due segmenti", len(trovati) == 2, str(trovati))
        if len(trovati) == 2:
            prova_vero("il primo cade dentro 1,0-3,0 s",
                       0.9 <= trovati[0]["inizio"] <= 1.6 and 2.6 <= trovati[0]["fine"] <= 3.2,
                       str(trovati[0]))
            prova_vero("il secondo dentro 5,0-7,0 s",
                       4.9 <= trovati[1]["inizio"] <= 5.6 and 6.6 <= trovati[1]["fine"] <= 7.2,
                       str(trovati[1]))

        # La pausa vera in mezzo (3,2-4,8) e una pausa finta dentro il parlato
        # (1,4-2,6): il rilevatore deve trattarle in modo opposto.
        tenuti, vetati = silenzi.veta_per_parlato([buco(3.2, 4.8)], trovati)
        prova("la pausa vuota resta tagliabile", len(tenuti), 1)
        tenuti, vetati = silenzi.veta_per_parlato([buco(1.4, 2.6)], trovati)
        prova("la pausa che contiene parlato viene vetata", len(vetati), 1)

        # E il giro completo, acceso, su un video che non si apre: deve
        # ripiegare senza rompere niente.
        buchi = [buco(3.2, 4.8), buco(1.4, 2.6)]
        with contextlib.redirect_stderr(io.StringIO()):
            tenuti, vetati, diag = silenzi.verifica_col_rilevatore(
                Path(tmp) / "non-esiste.mp4", 0.0, 8.0, buchi,
                ambiente={"MOTORE_RILEVATORE_PARLATO": "1"})
        prova_vero("un video che non si apre non rompe il giro",
                   tenuti == buchi and vetati == [] and len(diag["avvisi"]) == 1,
                   str(diag))

        # Il giro completo che funziona davvero: acceso, modello, file vero.
        with contextlib.redirect_stderr(io.StringIO()):
            tenuti, vetati, diag = silenzi.verifica_col_rilevatore(
                finto, 0.0, 8.0, buchi, ambiente={"MOTORE_RILEVATORE_PARLATO": "1"})
        prova_vero("acceso e funzionante: veta la pausa piena e tiene quella vuota",
                   len(tenuti) == 1 and len(vetati) == 1
                   and vicino(tenuti[0]["inizio"], 3.2), str((tenuti, vetati)))
        prova("la diagnostica dice quanti segmenti ha visto", diag["segmenti"], len(trovati))
        prova_vero("e quante celle ha valutato", diag["finestre"] > 200, str(diag))

silenzi.dimentica_rilevatore()


print()
if FALLITE:
    print(f"{PASSATE} passate, {len(SALTATE)} saltate, {len(FALLITE)} FALLITE: "
          f"{', '.join(FALLITE)}")
    raise SystemExit(1)
if SALTATE:
    print(f"Tutte passate ({PASSATE}), ma {len(SALTATE)} SALTATE per mancanza di "
          f"modello o ffmpeg: {', '.join(SALTATE)}")
    raise SystemExit(0)
print(f"Tutte passate ({PASSATE}).")
