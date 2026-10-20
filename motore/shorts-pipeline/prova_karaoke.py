"""Prove del karaoke: allineamento, campate, animazione, emissione ASS.

Deterministiche, senza rete e senza ffmpeg. Tre gruppi, uno per passo, piu'
il gruppo dell'emissione e quello della NON REGRESSIONE — che e' quello che
conta di piu': col karaoke spento il file dei sottotitoli deve uscire
identico a prima, carattere per carattere.

I valori attesi dei gruppi C non sono inventati: sono le prove di
accettazione T9 e T10 del documento 52 del corpus, riportate col loro numero.

Uso:
    py prova_karaoke.py

Esce 0 se tutte passano, 1 alla prima che fallisce (dicendo quale).
"""
from __future__ import annotations

import sys

import config
import karaoke
import render

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FALLITE: list[str] = []
PASSATE = 0


def prova(nome: str, ottenuto, atteso) -> None:
    global PASSATE
    if ottenuto == atteso:
        PASSATE += 1
        print(f"  ok   {nome}")
    else:
        FALLITE.append(nome)
        print(f"  NO   {nome}\n       atteso   {atteso!r}\n       ottenuto {ottenuto!r}")


def prova_quasi(nome: str, ottenuto: float, atteso: float, tol: float = 1e-4) -> None:
    global PASSATE
    if abs(float(ottenuto) - float(atteso)) <= tol:
        PASSATE += 1
        print(f"  ok   {nome}")
    else:
        FALLITE.append(nome)
        print(f"  NO   {nome}\n       atteso   {atteso}\n       ottenuto {ottenuto}")


def parola(testo: str, inizio: float, fine: float) -> dict:
    return {"w": testo, "start": inizio, "end": fine}


# ===========================================================================
print("\nA) passo 1 — allineamento fra testo spezzato e tempi di parola")
# ===========================================================================

PAROLE = [parola("Il", 0.0, 0.3), parola("mio", 0.3, 0.6),
          parola("nome", 0.6, 1.0), parola("e'", 1.0, 1.2),
          parola("Alex", 1.2, 2.0)]

blocchi = karaoke.allinea(["Il mio", "nome e' Alex"], PAROLE, 0.0, 2.0)
prova("due pezzi, due blocchi", len(blocchi), 2)
prova("primo blocco: due campate", len(blocchi[0].campate), 2)
prova("secondo blocco: tre campate", len(blocchi[1].campate), 3)
prova("il primo blocco comincia con la prima parola", blocchi[0].inizio, 0.0)
prova("il primo blocco finisce con la seconda parola", blocchi[0].fine, 0.6)
prova("il secondo blocco finisce con l'ultima parola", blocchi[1].fine, 2.0)
prova("gli indici delle campate ripartono da zero dentro il blocco",
      [c.indice for c in blocchi[1].campate], [0, 1, 2])

# --- il conteggio e' sugli ALFANUMERICI, non sui caratteri ---
prova("apostrofo: «l'AI» conta 3", karaoke.conta_alfanumerici("l'AI"), 3)
prova("numero col punto: «1.500» conta 4", karaoke.conta_alfanumerici("1.500"), 4)
prova("percentuale: «30%» conta 2", karaoke.conta_alfanumerici("30%"), 2)
prova("solo simboli: «...» conta 0", karaoke.conta_alfanumerici("..."), 0)
prova("solo simboli: «—» conta 0", karaoke.conta_alfanumerici("—"), 0)
prova("accenti: «perche'» conta 7", karaoke.conta_alfanumerici("perché"), 6)
prova("virgola staccata: «,» conta 0", karaoke.conta_alfanumerici(","), 0)

# --- raggruppamento diverso: il riconoscitore spezza dove il testo non spezza ---
RUN_SPEZZATE = [parola("l'", 0.0, 0.2), parola("AI", 0.2, 0.6),
                parola("serve", 0.6, 1.0)]
b = karaoke.allinea(["l'AI", "serve"], RUN_SPEZZATE, 0.0, 1.0)
prova("«l'AI» spezzato in due run: un blocco solo lo ricopre", len(b), 2)
prova("...e si prende TUTTE E DUE le run", len(b[0].campate), 2)
prova("...con inizio della prima e fine della seconda", (b[0].inizio, b[0].fine),
      (0.0, 0.6))
prova("la parola dopo non si perde", len(b[1].campate), 1)

# --- una run che raggruppa piu' parole del testo (sovra-consumo tollerato) ---
RUN_UNITE = [parola("nonlosapevo", 0.0, 1.0), parola("mai", 1.0, 1.3)]
b = karaoke.allinea(["non lo", "sapevo mai"], RUN_UNITE, 0.0, 1.3)
# Doc 70 §8.7 passo 3 e §«Sovra-consumo tollerato»: la condizione di
# continuazione e' «accumulato < voluto», quindi l'ULTIMA run consumata puo'
# sforare. Il blocco si estende oltre la sua ultima parola e va bene:
# «allineare a meta' run non avrebbe senso». La verifica di copertura del
# passo 4 confronta il NUMERO DI BLOCCHI col numero di testi — qui 2 e 2,
# quindi passa e NON si ripiega.
prova("una run che sfora nel pezzo dopo: sovra-consumo tollerato", len(b), 2)
prova("...il primo pezzo si prende tutta la run che sfora",
      (b[0].inizio, b[0].fine), (0.0, 1.0))
prova("...e il secondo si prende quello che resta",
      (b[1].inizio, b[1].fine), (1.0, 1.3))
prova("...le campate restano, non si azzerano",
      [len(x.campate) for x in b], [1, 1])

# --- IL NOSTRO MIGLIORAMENTO: il pezzo senza alfanumerici si salta ---
b = karaoke.allinea(["Il mio", "...", "nome e' Alex"], PAROLE, 0.0, 2.0)
prova("tre pezzi, tre blocchi (nel corpus qui crollava tutto)", len(b), 3)
prova("il pezzo «...» non ha campate", b[1].campate, None)
prova("MA il pezzo prima le tiene", len(b[0].campate), 2)
prova("E il pezzo dopo le tiene", len(b[2].campate), 3)
prova("il «...» sta nel buco fra le due run", (b[1].inizio, b[1].fine), (0.6, 0.6))
prova("...e non ruba tempo a chi viene dopo", b[2].inizio, 0.6)

b = karaoke.allinea(["...", "Il mio"], PAROLE, 0.0, 2.0)
prova("un «...» in testa parte dall'inizio del segmento", b[0].inizio, 0.0)
prova("...e non consuma nessuna run", len(b[1].campate), 2)

b = karaoke.allinea(["Il mio nome e' Alex", "..."], PAROLE, 0.0, 2.0)
prova("un «...» in coda si chiude sulla fine del segmento",
      (b[1].inizio, b[1].fine), (2.0, 2.0))

# --- run esaurite: si butta tutto e si ripiega (fedele al corpus) ---
b = karaoke.allinea(["Il mio", "nome e' Alex", "e faccio consulenza"],
                    PAROLE[:2], 0.0, 2.0)
prova("run finite prima dei pezzi: ripiego per TUTTI", [x.campate for x in b],
      [None, None, None])
prova("...e i blocchi restano tre", len(b), 3)

# --- nessuna parola temporizzata ---
b = karaoke.allinea(["uno", "due"], [], 0.0, 1.0)
prova("senza parole temporizzate: ripiego proporzionale", [x.campate for x in b],
      [None, None])
prova("...con la somma delle durate uguale allo span",
      round(b[-1].fine - b[0].inizio, 9), 1.0)

# --- parole senza tempi, o di sola punteggiatura, sono scartate dalle run ---
prova("una parola senza tempo non diventa una run",
      len(karaoke.run_temporizzate([{"w": "ciao", "start": 0.0}])), 0)
prova("una parola di sola punteggiatura non diventa una run",
      len(karaoke.run_temporizzate([parola(",", 0.0, 0.1)])), 0)

# ===========================================================================
print("\nB) passo 2 — campate agganciate al blocco")
# ===========================================================================

F = karaoke.Finestra(fps=30.0, frame_inizio=0, frame_fine=60)

prova("test di sovrapposizione STRETTO: chi tocca l'estremo destro e' fuori",
      karaoke.sovrapposto(2.0, 3.0, F), False)
prova("...e chi tocca l'estremo sinistro pure",
      karaoke.sovrapposto(-1.0, 0.0, F), False)
prova("chi sporge di un pelo dentro c'e'", karaoke.sovrapposto(1.9, 2.1, F), True)

prova("conversione autorevole: fuori campo a destra = niente",
      karaoke.converti_autorevole(2.0, F), None)
prova("conversione autorevole: prima del ritaglio = niente",
      karaoke.converti_autorevole(-0.1, F), None)
prova("conversione ausiliaria: prima del ritaglio AGGANCIA al primo frame",
      karaoke.converti_ausiliaria(-5.0, F), 0)
prova("conversione ausiliaria: estremo destro INCLUSO",
      karaoke.converti_ausiliaria(9.0, F), 60)

blocco = karaoke.Blocco("UNO DUE", 0.0, 1.0, (
    karaoke.Campata(0, "uno", 0.0, 0.4),
    karaoke.Campata(1, "due", 0.4, 1.0)))
inizio, durata, campate = karaoke.campate_nel_blocco(blocco, F)
prova("il blocco parte dal frame 0", inizio, 0)
prova("il blocco dura 30 frame", durata, 30)
prova("due campate sopravvivono", len(campate), 2)
prova("la prima e' [0,12)", (campate[0].inizio, campate[0].fine), (0, 12))
prova("la seconda e' [12,30)", (campate[1].inizio, campate[1].fine), (12, 30))

# doppio agganciamento: una parola che sporge oltre il blocco
lungo = karaoke.Blocco("UNO", 0.0, 0.5, (karaoke.Campata(0, "uno", 0.0, 1.5),))
_, durata, campate = karaoke.campate_nel_blocco(lungo, F)
prova("la campata che sporge si aggancia alla durata del blocco",
      (campate[0].inizio, campate[0].fine), (0, durata))

# elenco vuoto = ASSENZA
fuori_campo = karaoke.Blocco("UNO", 0.0, 0.5, (karaoke.Campata(0, "uno", 5.0, 6.0),))
_, _, campate = karaoke.campate_nel_blocco(fuori_campo, F)
prova("nessuna campata sopravvissuta = ASSENZA, non lista vuota", campate, None)
prova("...e None non e' []", campate == [], False)

senza = karaoke.Blocco("UNO", 0.0, 0.5, None)
prova("blocco senza campate: restano assenti",
      karaoke.campate_nel_blocco(senza, F)[2], None)

# --- LA TRAPPOLA: la parola si risolve per INDICE, mai per testo ---
b_maiuscolo = karaoke.Blocco("IL MIO", 0.0, 0.6, (
    karaoke.Campata(0, "Il", 0.0, 0.3), karaoke.Campata(1, "mio", 0.3, 0.6)))
prova("per indice la campata si trova", karaoke.risolvi_campata(b_maiuscolo, 1).testo,
      "mio")
parole_viste = b_maiuscolo.testo.split(" ")
per_testo = [c for c in b_maiuscolo.campate if c.testo == parole_viste[1]]
prova("per TESTO non si trova (il maiuscolo sta sul blocco, non sulle campate)",
      per_testo, [])
prova("indice fuori elenco: niente", karaoke.risolvi_campata(b_maiuscolo, 9), None)
prova("blocco senza campate: niente", karaoke.risolvi_campata(senza, 0), None)

# --- trappola 28: forzare il blocco a 1 frame distrugge le campate ---
campate_piene = (karaoke.CampataFrame(0, "uno", 0, 12),
                 karaoke.CampataFrame(1, "due", 12, 30))
prova("blocco schiacciato a 1 frame: resta al piu' la prima campata",
      karaoke.riallinea_campate(campate_piene, 0, 1),
      (karaoke.CampataFrame(0, "uno", 0, 1),))
# Doc 36 §271: si scarta la parola «se la fine non supera l'inizio», e gli
# intervalli diventano assenti SOLO «se non resta alcuna parola». Con
# scostamento 12 la prima collassa (12-12=0 sia inizio sia fine, scartata) ma
# la seconda parte esattamente dall'inizio del blocco e sopravvive limitata.
# Una campata resta, quindi l'assenza NON scatta.
prova("blocco schiacciato con scostamento: resta la campata che parte li'",
      karaoke.riallinea_campate(campate_piene, 12, 1),
      (karaoke.CampataFrame(1, "due", 0, 1),))
prova("blocco spostato oltre l'ultima campata: allora si', spariscono",
      karaoke.riallinea_campate(campate_piene, 30, 1), None)
prova("estensione senza scostamento: le campate non si toccano",
      karaoke.riallinea_campate(campate_piene, 0, 60), campate_piene)

# ===========================================================================
print("\nC) passo 3 — animazione per parola (prove T9 e T10 del corpus)")
# ===========================================================================

prova_quasi("smoothstep(0) = 0", karaoke.smoothstep(0.0), 0.0)
prova_quasi("smoothstep(0,5) = 0,5", karaoke.smoothstep(0.5), 0.5)
prova_quasi("smoothstep(1) = 1", karaoke.smoothstep(1.0), 1.0)
prova_quasi("smoothstep(1/6) = 0,0741", karaoke.smoothstep(1 / 6), 0.0741, 1e-4)

prova("rampa lineare: a rel = inizio vale 0", karaoke.lineare(0, 0, 6), 0.0)
prova("rampa lineare: a rel = inizio+durata vale 1", karaoke.lineare(6, 0, 6), 1.0)
prova_quasi("rampa lineare: il primo valore non nullo e' 1/durata",
            karaoke.lineare(1, 0, 6), 1 / 6)

# --- T9: curva temporale dell'ingresso, preset popIn, perWordFrames = 6 ---
s0 = karaoke.stato_blocco("popIn", 0, 6)
prova_quasi("T9 rel=0: scala 0,6", s0.scala, 0.6)
prova_quasi("T9 rel=0: opacita' 0", s0.opacita, 0.0)
s3 = karaoke.stato_blocco("popIn", 3, 6)
prova_quasi("T9 rel=3: scala 0,8", s3.scala, 0.8)
prova_quasi("T9 rel=3: opacita' 0,5", s3.opacita, 0.5)
s6 = karaoke.stato_blocco("popIn", 6, 6)
prova_quasi("T9 rel=6: scala 1", s6.scala, 1.0)
prova_quasi("T9 rel=6: opacita' 1", s6.opacita, 1.0)
prova_quasi("T9 rel=1: scala 0,6296", karaoke.stato_blocco("popIn", 1, 6).scala,
            0.6296, 1e-4)
prova_quasi("T9 oltre la rampa resta a 1", karaoke.stato_blocco("popIn", 40, 6).scala,
            1.0)

# --- T10: mantenimento dell'evidenziazione, highlightPop, perWordFrames = 6 ---
prova("T10 la rampa NON e' 6 ma min(6,4) = 4",
      karaoke.durata_rampa(0, 30, min(6, karaoke.MASSIMO_RAMPA_EVIDENZIAZIONE)), 4)
prova("T10 con perWordFrames = 2 la rampa diventa 2",
      karaoke.durata_rampa(0, 30, min(2, karaoke.MASSIMO_RAMPA_EVIDENZIAZIONE)), 2)
prova("T10 con perWordFrames = 40 la rampa resta 4",
      karaoke.durata_rampa(0, 30, min(40, karaoke.MASSIMO_RAMPA_EVIDENZIAZIONE)), 4)
prova("parola di 1 frame: rampa ASSENTE, effetto a gradino",
      karaoke.durata_rampa(0, 1, 4), None)
prova("parola di 3 frame: rampa accorciata a meta' della parola",
      karaoke.durata_rampa(0, 3, 4), 1)


def acceso(rel: float) -> float:
    return karaoke.evidenziazione_mantenuta(rel, 0, 30, 30, 60, 4)


prova_quasi("T10 rel=0 -> 0", acceso(0), 0.0)
prova_quasi("T10 rel=1 -> 0,15625", acceso(1), 0.15625)
prova_quasi("T10 rel=2 -> 0,5", acceso(2), 0.5)
prova_quasi("T10 rel=4 -> 1", acceso(4), 1.0)
prova_quasi("T10 rel=20 -> resta 1", acceso(20), 1.0)
prova_quasi("T10 rel=30 -> ancora 1", acceso(30), 1.0)
prova_quasi("T10 rel=32 -> 0,5", acceso(32), 0.5)
prova_quasi("T10 rel=34 -> 0 (spenta dalla rampa della SUCCESSIVA)", acceso(34), 0.0)
prova_quasi("T10 la seconda parola arriva a 1 a rel=34",
            karaoke.evidenziazione_mantenuta(34, 30, 60, None, None, 4), 1.0)
prova_quasi("T10 l'ULTIMA parola resta accesa fino alla fine",
            karaoke.evidenziazione_mantenuta(59, 30, 60, None, None, 4), 1.0)
prova_quasi("prima dell'inizio della parola: spenta",
            karaoke.evidenziazione_mantenuta(-1, 0, 30, None, None, 4), 0.0)

# --- rampa simmetrica di wordReveal/wordSlide: si spegne a fine parola ---
prova_quasi("simmetrica: fuori dalla parola vale 0",
            karaoke.rampa_attiva(31, 0, 30, 6), 0.0)
prova_quasi("simmetrica: a meta' parola vale 1", karaoke.rampa_attiva(15, 0, 30, 6), 1.0)
prova_quasi("simmetrica: risale e ridiscende simmetrica",
            karaoke.rampa_attiva(3, 0, 30, 6), karaoke.rampa_attiva(27, 0, 30, 6))

# --- stati per preset ---
c0 = karaoke.CampataFrame(0, "uno", 0, 30)
c1 = karaoke.CampataFrame(1, "due", 30, 60)
BIANCO, ROSSO = (255, 255, 255), (226, 35, 26)

st = karaoke.stato_parola("highlightPop", 4, c0, c1, 6, BIANCO, ROSSO)
prova_quasi("highlightPop a rampa piena: colore = rosso pieno", st.colore[0], 226.0)
prova("highlightPop non tocca l'opacita'", st.opacita, 1.0)
prova("highlightPop non produce blocco di sfondo", st.colore_sfondo, None)

st = karaoke.stato_parola("highlightBlock", 4, c0, c1, 6, BIANCO, ROSSO)
prova("highlightBlock lascia il testo del colore base", st.colore, BIANCO)
prova_quasi("highlightBlock accende l'alpha del blocco", st.colore_sfondo[3], 1.0)

st = karaoke.stato_parola("wordReveal", 0, c0, c1, 6, BIANCO, None)
prova_quasi("wordReveal a rel=0: invisibile", st.opacita, 0.0)
st = karaoke.stato_parola("wordReveal", 6, c0, c1, 6, BIANCO, None)
prova_quasi("wordReveal a rel=mano: opaca", st.opacita, 1.0)
prova("wordReveal senza tinta lascia il colore base", st.colore, BIANCO)

st = karaoke.stato_parola("wordSlide", 0, c0, c1, 6, BIANCO, None)
prova_quasi("wordSlide parte da mezzo corpo piu' in basso", st.dy, 0.5)
st = karaoke.stato_parola("wordSlide", 6, c0, c1, 6, BIANCO, None)
prova_quasi("wordSlide a rampa finita e' a posto", st.dy, 0.0)

st = karaoke.stato_parola("highlightPop", 4, c0, c1, 6, BIANCO, None)
prova("highlightPop senza tinta usa il giallo predefinito del corpus",
      tuple(round(v) for v in st.colore), karaoke.EVIDENZIAZIONE_PREDEFINITA)

# --- geometria: pivot, trasformazione, blocco di evidenziazione ---
prova("pivot verticale a 0,35 corpi sopra la linea di base",
      karaoke.pivot_parola(100.0, 200.0, 60.0, 80.0), (130.0, 228.0))
prova("scalatura attorno al pivot, POI traslazione non scalata",
      karaoke.trasforma_punto((130.0, 228.0), (130.0, 228.0), 2.0, 0.5, 80.0),
      (130.0, 188.0))
prova("a scala 1 e dy 0 il punto non si muove",
      karaoke.trasforma_punto((10.0, 20.0), (0.0, 0.0), 1.0, 0.0, 80.0), (10.0, 20.0))

bl = karaoke.blocco_evidenziazione(100.0, 200.0, 60.0, 100.0)
prova("blocco: padX 0,18 corpi per lato", bl.x, 100.0 - 18.0)
prova("blocco: larghezza = parola + 2 padX", bl.larghezza, 60.0 + 36.0)
prova("blocco: raggio 0,12 corpi", bl.raggio, 12.0)
prova("blocco: altezza = asc + disc + 2 padY", bl.altezza, 80.0 + 20.0 + 20.0)
prova("blocco: y scende del discendente piu' padY", bl.y, 200.0 - 20.0 - 10.0)
bl2 = karaoke.blocco_evidenziazione(0.0, 0.0, 10.0, 200.0)
prova("blocco: tutto in FRAZIONI DI CORPO, quindi raddoppia col corpo",
      (bl2.raggio, bl2.altezza), (24.0, 160.0 + 40.0 + 40.0))

# ===========================================================================
print("\nD) emissione ASS")
# ===========================================================================

prova("«&H001A23E2&» torna il rosso di brand", karaoke.rgb_da_ass("&H001A23E2&"),
      (226, 35, 26))
prova("«#e2231a» torna lo stesso rosso", karaoke.rgb_da_hex("#e2231a"), (226, 35, 26))
prova("e ci si torna", karaoke.ass_da_rgb((226, 35, 26)), "&H1A23E2&")
prova("opacita' piena = alpha 00", karaoke.ass_da_opacita(1.0), "&H00&")
prova("opacita' nulla = alpha FF", karaoke.ass_da_opacita(0.0), "&HFF&")
prova("il rosso del kit e quello del karaoke sono lo stesso numero",
      karaoke.rgb_da_ass(config.ROSSO_ASS), (226, 35, 26))

CAMPATE = (karaoke.CampataFrame(0, "il", 0, 12),
           karaoke.CampataFrame(1, "mio", 12, 30))
testo = karaoke.testo_dialogue("highlightPop", ["IL", "MIO"], CAMPATE, 30, 6,
                               BIANCO, ROSSO, fps=30.0,
                               posizione=(540, 1420))
prova("highlightPop: la riga porta le due parole", "IL" in testo and "MIO" in testo, True)
prova("highlightPop: la riga e' posizionata una volta sola", testo.count("\\pos("), 1)
prova("highlightPop: c'e' il rosso interpolato", "\\1c&H1A23E2&" in testo, True)
prova("highlightPop: le rampe sono spezzate in tratti",
      testo.count("\\t(") >= 2 * karaoke.SEGMENTI_RAMPA, True)
prova("highlightPop: nessuna scalatura, quindi nessun riflusso della riga",
      "\\fscx" in testo, False)

testo = karaoke.testo_dialogue("wordReveal", ["IL", "MIO"], CAMPATE, 30, 6,
                               BIANCO, None, fps=30.0, posizione=(540, 1420))
prova("wordReveal: ogni parola parte trasparente", testo.count("\\alpha&HFF&"), 2)
prova("wordReveal senza tinta: nessun cambio di colore", "\\1c" in testo, False)

testo = karaoke.testo_dialogue("popIn", ["IL", "MIO"], CAMPATE, 30, 6,
                               BIANCO, ROSSO, fps=30.0, posizione=(540, 1420))
prova("popIn: un solo gruppo di tag davanti alla riga", testo.count("{"), 1)
prova("popIn: parte da scala 60", "\\fscx60.0" in testo, True)

testo = karaoke.testo_dialogue("slideUp", ["IL", "MIO"], CAMPATE, 30, 6,
                               BIANCO, ROSSO, fps=30.0, altezza=1920,
                               posizione=(540, 1420))
prova("slideUp: usa \\move e non \\pos (non ci vanno tutti e due)",
      ("\\move(" in testo, "\\pos(" in testo), (True, False))
prova("slideUp: entra da 0,05 altezze di canvas piu' in basso",
      "\\move(540,1516,540,1420" in testo, True)

testo = karaoke.testo_dialogue("typewriter", ["IL", "MIO"], CAMPATE, 30, 6,
                               BIANCO, ROSSO, fps=30.0, posizione=(540, 1420))
prova("typewriter: un tag per carattere non spazio", testo.count("\\alpha&HFF&"), 5)

# I due preset che ASS non rende per intero. La scelta: NON si spengono, si
# degradano al piu' vicino che ASS sa disegnare — l'animazione di colore resta,
# si perdono solo le metriche (lo scorrimento, il riquadro). E il degrado si
# DICHIARA: un preset che esce diverso e tace e' indistinguibile da
# un'impostazione ignorata.
for degradato, vicino in (("wordSlide", "wordReveal"),
                          ("highlightBlock", "highlightPop")):
    testo = karaoke.testo_dialogue(degradato, ["IL", "MIO"], CAMPATE, 30, 6,
                                   BIANCO, ROSSO, fps=30.0, posizione=(540, 1420))
    atteso = karaoke.testo_dialogue(vicino, ["IL", "MIO"], CAMPATE, 30, 6,
                                    BIANCO, ROSSO, fps=30.0, posizione=(540, 1420))
    prova(f"{degradato}: esce identico a {vicino}, non fermo", testo, atteso)
    prova(f"{degradato}: l'animazione c'e' davvero", "\\t(" in testo, True)
    d = karaoke.degradazione(degradato)
    prova(f"{degradato}: il degrado e' DICHIARATO",
          (d["chiesto"], d["reso"]), (degradato, vicino))
    prova(f"{degradato}: e dice cosa si perde", bool(d["perso"]), True)

prova("un preset reso per intero non dichiara perdite",
      karaoke.degradazione("wordReveal"), None)

# La trappola che nessuno guardava: `none` non e' ne' di blocco ne' macchina da
# scrivere, quindi arrivava al ramo per parola e usciva ANIMATO come
# highlightPop. Chi chiede nessuna animazione deve vedere il testo fermo.
testo = karaoke.testo_dialogue("none", ["IL", "MIO"], CAMPATE, 30, 6,
                               BIANCO, ROSSO, fps=30.0, posizione=(540, 1420))
prova("none: nessun tag di animazione, testo fermo",
      ("\\t(" in testo, "IL MIO" in testo), (False, True))
testo = karaoke.testo_dialogue("preset-che-non-esiste", ["IL", "MIO"], CAMPATE,
                               30, 6, BIANCO, ROSSO, fps=30.0)
prova("un preset sconosciuto cade su none, non sull'evidenziazione",
      "\\t(" in testo, False)

# highlightBlock senza tinta esplicita: prima arrivava a misto(base, None, u).
testo = karaoke.testo_dialogue("highlightBlock", ["IL", "MIO"], CAMPATE, 30, 6,
                               BIANCO, None, fps=30.0)
prova("highlightBlock senza tinta usa quella predefinita, non esplode",
      "\\1c" in testo, True)

testo = karaoke.testo_dialogue("highlightPop", ["IL", "MIO"], None, 30, 6,
                               BIANCO, ROSSO, fps=30.0, posizione=(540, 1420))
prova("campate ASSENTI: il blocco esce fermo, non inventato",
      ("\\t(" in testo, "IL MIO" in testo), (False, True))
prova("nessuna parola: niente riga",
      karaoke.testo_dialogue("highlightPop", [], CAMPATE, 30, 6, BIANCO, ROSSO), "")

prova("le graffe non passano: sono la sintassi di ASS", karaoke.escapa("a{b}c"),
      "a(b)c")
prova("la barra rovescia nemmeno", karaoke.escapa("a\\Nb"), "aNb")

# ===========================================================================
print("\nE) NON regressione — col karaoke spento non cambia un byte")
# ===========================================================================

INTESTAZIONE_ATTESA = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {config.OUT_W}
PlayResY: {config.OUT_H}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,UserFont,{config.FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,5,0,5,{config.MARGINE_TESTO_PX},{config.MARGINE_TESTO_PX},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
prova("l'intestazione staccata e' identica a quella di sempre",
      render._intestazione_ass("UserFont"), INTESTAZIONE_ATTESA)

prova("il preset predefinito e' SPENTO", config.KARAOKE_PRESET, "off")

ass_spento = render.build_ass(PAROLE, 0.0, "UserFont")
prova("col karaoke spento si emette una riga per PAROLA, come sempre",
      ass_spento.count("Dialogue:"), len(PAROLE))
prova("...con il micro-pop di sempre", "\\fscx108\\fscy108" in ass_spento, True)

vecchio = config.KARAOKE_PRESET
try:
    config.KARAOKE_PRESET = "highlightPop"
    ass_acceso = render.build_ass(PAROLE, 0.0, "UserFont")
finally:
    config.KARAOKE_PRESET = vecchio
righe_acceso = ass_acceso.count("Dialogue:")
prova("col karaoke acceso si emette una riga per PAGINA, quindi meno righe",
      righe_acceso < len(PAROLE), True)
prova("...e la stessa intestazione", ass_acceso.startswith(INTESTAZIONE_ATTESA), True)
prova("...e nessun micro-pop, quindi nessun riflusso",
      "\\fscx" in ass_acceso, False)
prova("...e il rosso di brand dentro le rampe", "\\1c&H1A23E2&" in ass_acceso, True)
prova("le due strade partono dalle stesse pagine",
      len(render.paginate(PAROLE, 0.0)), righe_acceso)

print(f"\n{PASSATE} passate" + (f", FALLITE: {', '.join(FALLITE)}" if FALLITE
                                else ", nessuna fallita"))
sys.exit(1 if FALLITE else 0)
