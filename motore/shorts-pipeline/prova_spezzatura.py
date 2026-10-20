"""Prove della catena dei sottotitoli: misura, spezzatura, sequenza.

Si esegue cosi', dalla cartella della pipeline:

    py prova_spezzatura.py

Non serve rete. La sezione A serve ffmpeg e i font del kit; senza, si salta da
sola e lo dice — le altre girano lo stesso.

PERCHE' QUESTO BANCO ESISTE, E PERCHE' PRIMA DEL COLLEGAMENTO.
`spezzatura.py` non e' agganciato a niente: `render.py` continua a spezzare le
righe contando le parole. Collegarlo CAMBIA I VIDEO PRODOTTI, perche' misurare
la larghezza vera sposta le pagine dei sottotitoli. Un cambiamento che si vede
non si accende senza prove, e queste sono la prima meta': la seconda e' un
confronto fotogramma contro fotogramma su uno short vero.

La prova che conta piu' di tutte e' la A1. La misura non e' un dettaglio
implementativo: e' il numero che decide dove va a capo una riga. Se e'
sbagliata del 25% — ed e' esattamente quello che succede a chi scala per
`unitsPerEm` invece che per `winAscent + winDescent` — il rapporto 0,88 delle
fondamenta diventa una bugia e le righe si spezzano un quarto troppo presto.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import spezzatura

PASSATE = 0
FALLITE: list[str] = []
SALTATE: list[str] = []


def prova(nome, ottenuto, atteso):
    global PASSATE
    if ottenuto == atteso:
        PASSATE += 1
        print(f"  ok   {nome}")
    else:
        FALLITE.append(nome)
        print(f"  NO   {nome}\n       atteso   {atteso!r}\n       ottenuto {ottenuto!r}")


def prova_quasi(nome, ottenuto, atteso, tolleranza=1e-6):
    global PASSATE
    if ottenuto is not None and abs(ottenuto - atteso) <= tolleranza:
        PASSATE += 1
        print(f"  ok   {nome}")
    else:
        FALLITE.append(nome)
        print(f"  NO   {nome}\n       atteso   {atteso} ±{tolleranza}\n       ottenuto {ottenuto}")


def salta(nome, motivo):
    SALTATE.append(nome)
    print(f"  --   {nome} SALTATA: {motivo}")


# ===========================================================================
print("A) la misura — il numero da cui dipende tutto il resto")
# ===========================================================================

def _font_del_kit() -> Path | None:
    """Only inspect the explicitly selected font or the prepared local directory."""
    selected = os.environ.get("FONT_PATH")
    if selected and Path(selected).is_file():
        return Path(selected)
    directory = Path(os.environ.get("SHORTS_FONTS_DIR", str(Path(__file__).resolve().parent / "fonts")))
    if directory.is_dir():
        return next((item for item in directory.iterdir() if item.suffix.lower() in (".ttf", ".otf")), None)
    return None


def _avanzata_con_libass(font: Path, testo: str, corpo: int) -> float | None:
    """L'avanzata VERA di `testo`, chiesta a libass dentro ffmpeg.

    Il trucco e' la sottrazione: si rende `X` e `XX` e si sottraggono le due
    estensioni d'inchiostro. Cosi' spariscono i margini, il contorno e tutto
    quello che non e' l'avanzata del glifo.
    """
    if shutil.which("ffmpeg") is None:
        return None
    larghezze = []
    for stringa in (testo, testo + testo):
        with tempfile.TemporaryDirectory() as tmp:
            ass = Path(tmp) / "p.ass"
            ass.write_text(
                "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n"
                "ScaledBorderAndShadow: yes\n\n"
                "[V4+ Styles]\n"
                "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,"
                "BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,"
                "BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
                f"Style: P,{font.stem},{corpo},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
                "0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n\n"
                "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
                f"Dialogue: 0,0:00:00.00,0:00:01.00,P,,0,0,0,,{{\\pos(0,0)}}{stringa}\n",
                encoding="utf-8")
            uscita = Path(tmp) / "f.png"
            esito = subprocess.run(
                ["ffmpeg", "-v", "error", "-f", "lavfi",
                 "-i", "color=c=black:s=1920x1080:d=1",
                 "-vf", f"subtitles={ass.as_posix()}:fontsdir={font.parent.as_posix()}",
                 "-frames:v", "1", "-y", str(uscita)],
                capture_output=True, text=True)
            if esito.returncode != 0 or not uscita.exists():
                return None
            crudo = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(uscita),
                 "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                capture_output=True)
            if crudo.returncode != 0:
                return None
            dati = crudo.stdout
            larghezza_img = 1920
            colonne_accese = set()
            for indice, valore in enumerate(dati):
                if valore > 40:
                    colonne_accese.add(indice % larghezza_img)
            if not colonne_accese:
                return None
            larghezze.append(max(colonne_accese) - min(colonne_accese) + 1)
    # inchiostro(XX) - inchiostro(X) = avanzata di X
    return float(larghezze[1] - larghezze[0])


_font = _font_del_kit()
if _font is None:
    salta("A1 — la misura combacia con libass", "font del kit non trovato")
    salta("A2 — scalare per unitsPerEm sovrastima", "font del kit non trovato")
else:
    CORPO = 72
    try:
        misura = spezzatura.MisuraTesto(_font, CORPO)
    except spezzatura.FontNonMisurabile as errore:
        misura = None
        salta("A1 — la misura combacia con libass", str(errore)[:60])
        salta("A2 — scalare per unitsPerEm sovrastima", str(errore)[:60])
    if misura is not None:
        vero = _avanzata_con_libass(_font, "M", CORPO)
        if vero is None:
            salta("A1 — la misura combacia con libass", "ffmpeg assente o senza libass")
        else:
            nostro = misura.larghezza("M")
            # La tolleranza e' la quantizzazione della misura stessa: si
            # contano PIXEL accesi, quindi un pixel di scarto e' il rumore di
            # fondo del metodo, non un errore del calcolo.
            prova_quasi(f"A1 — la misura combacia con libass (M a {CORPO}px)",
                        nostro, vero, tolleranza=2.0)

        # A2: la trappola dichiarata nel modulo. Con winAsc+winDesc = 1250 su
        # upem 1000, chi scala per upem misura 1,25 volte il vero.
        rapporto = misura.unita_per_corpo / 1000.0
        if abs(rapporto - 1.0) < 1e-9:
            salta("A2 — scalare per unitsPerEm sovrastima",
                  "questo font ha winAsc+winDesc = upem, la trappola non si vede")
        else:
            sbagliato = misura.larghezza("M") * rapporto
            prova(f"A2 — scalare per unitsPerEm misurerebbe di piu' ({rapporto:.3f}x)",
                  sbagliato > misura.larghezza("M"), True)

# ===========================================================================
print("\nB) la spezzatura — una sola rottura per livello, ricorsiva")
# ===========================================================================

# Un predicato finto: la 'larghezza' e' il numero di caratteri. Serve a provare
# la STRUTTURA della ricorsione senza tirarci dentro i font.
def accetta_fino_a(n):
    return lambda testo: len(testo) <= n


prova("B1 — se ci sta, un pezzo solo",
      spezzatura.spezza("ciao", accetta_fino_a(10)), ["ciao"])

prova("B2 — testo vuoto: nessun pezzo, non un pezzo vuoto",
      spezzatura.spezza("   ", accetta_fino_a(10)), [])

prova("B3 — si rompe prima sulle FRASI",
      spezzatura.spezza("Uno due. Tre quattro.", accetta_fino_a(12)),
      ["Uno due.", "Tre quattro."])

prova("B4 — poi sulle proposizioni, se le frasi non bastano",
      spezzatura.spezza("Uno due, tre quattro", accetta_fino_a(11)),
      ["Uno due,", "tre quattro"])

# Con un carattere in meno «tre quattro» (11) non ci sta piu' e si rompe
# ancora: e' la ricorsione, ed e' giusto che scenda di un altro livello.
prova("B4b — sotto il limite si scende di un altro livello",
      spezzatura.spezza("Uno due, tre quattro", accetta_fino_a(10)),
      ["Uno due,", "tre", "quattro"])

# La regola numero 4 di spezza(): una parola piu' lunga del limite NON si
# tronca. Meglio un blocco troppo largo che una parola tagliata a meta'.
prova("B5 — una parola piu' lunga del limite esce intera, non troncata",
      spezzatura.spezza("supercalifragilistico", accetta_fino_a(5)),
      ["supercalifragilistico"])

# ---- le due trappole della punteggiatura (SPEC/70 §8.5) ----
# Il taglio cade dopo il delimitatore SOLO se segue uno spazio semplice.
prova("B6 — «U.S.» non diventa «U.» + «S.»",
      spezzatura.spezza("U.S.A", accetta_fino_a(3)), ["U.S.A"])

prova("B7 — «3.14» non si spezza sul punto decimale",
      spezzatura.spezza("3.14", accetta_fino_a(2)), ["3.14"])

# ---- terminazione: nessuna ricorsione infinita ----
lungo = " ".join(["parola"] * 60)
pezzi = spezzatura.spezza(lungo, accetta_fino_a(20))
prova("B8 — un testo lungo termina e non perde niente",
      "".join(pezzi).replace(" ", ""), lungo.replace(" ", ""))
prova("B9 — ...e ogni pezzo rispetta il limite (nessuna parola lo supera)",
      all(len(p) <= 20 for p in pezzi), True)

# ===========================================================================
print("\nC) la sequenza — ordine, collisioni, buchi, tetti")
# ===========================================================================

def blocco(testo, inizio, fine):
    return {"testo": testo, "inizio": inizio, "fine": fine, "parole": []}


# L'ordinamento e' STABILE per (inizio, indice): a parita' di inizio vince
# l'ordine di trascrizione, che e' quello in cui le parole sono state dette.
fuori = spezzatura.pulisci_sequenza([
    blocco("b", 2.0, 3.0), blocco("a", 1.0, 2.0), blocco("c", 3.0, 4.0)
])
prova("C1 — riordina per inizio", [b["testo"] for b in fuori], ["a", "b", "c"])

fuori = spezzatura.pulisci_sequenza([
    blocco("primo", 0.0, 5.0), blocco("secondo", 0.0, 5.0)
])
prova("C2 — a parita' di inizio vince l'ordine di trascrizione",
      [b["testo"] for b in fuori], ["primo", "secondo"])

# LA PROVA CHE CONTA: dopo la pulizia non deve restare NESSUNA
# sovrapposizione. Il corpus dichiara che la sua guarda solo la coppia
# adiacente e che con blocchi lunghi e ravvicinati ne restano; qui no.
sovrapposti = [blocco(f"b{i}", i * 0.3, i * 0.3 + 4.0) for i in range(8)]
fuori = spezzatura.pulisci_sequenza(sovrapposti)
prova("C3 — dopo la pulizia zero sovrapposizioni, anche fitte e lunghe",
      spezzatura.sovrapposizioni(fuori), [])
prova("C4 — ...e nessun blocco e' sparito", len(fuori), len(sovrapposti))

# Un buco corto si chiude, uno lungo resta: e' la differenza fra un
# tremolio e una pausa voluta.
fuori = spezzatura.pulisci_sequenza(
    [blocco("a", 0.0, 1.0), blocco("b", 1.2, 2.2)], buco_max_s=0.5)
prova_quasi("C5 — un buco corto si chiude", fuori[0]["fine"], fuori[1]["inizio"])

fuori = spezzatura.pulisci_sequenza(
    [blocco("a", 0.0, 1.0), blocco("b", 4.0, 5.0)], buco_max_s=0.5)
prova("C6 — un buco lungo resta: e' una pausa, non un difetto",
      fuori[1]["inizio"] - fuori[0]["fine"] > 0.5, True)

# Il tetto di durata: nessun blocco resta a schermo piu' del massimo.
fuori = spezzatura.pulisci_sequenza([blocco("a", 0.0, 30.0)], durata_max_s=6.0)
prova("C7 — il tetto di durata si applica",
      fuori[0]["fine"] - fuori[0]["inizio"] <= 6.0 + 1e-9, True)

# La durata minima di lettura: un blocco lampo si allunga.
fuori = spezzatura.pulisci_sequenza([blocco("a", 0.0, 0.05)], durata_min_s=0.4)
prova("C8 — un blocco troppo breve si allunga fino al minimo di lettura",
      fuori[0]["fine"] - fuori[0]["inizio"] >= 0.4 - 1e-9, True)

# La fine della clip e' un muro: niente deve sporgere oltre.
fuori = spezzatura.pulisci_sequenza(
    [blocco("a", 9.0, 9.5)], durata_min_s=2.0, fine_clip_s=10.0)
prova("C9 — niente sporge oltre la fine della clip",
      fuori[0]["fine"] <= 10.0 + 1e-9, True)

prova("C10 — elenco vuoto: elenco vuoto, non un errore",
      spezzatura.pulisci_sequenza([]), [])

# ===========================================================================
print("\nD) il margine — la difesa contro il sottotitolo fuori dal fotogramma")
# ===========================================================================

# Il predicato spezza sulla larghezza A RIPOSO. Sopra quella il disegno
# aggiunge il contorno da entrambi i lati e il micro-pop della parola attiva:
# questa funzione rifa' il conto invece di darlo per buono.
# 950 + 0,08*200 + 2*5 = 976 nel caso peggiore; su 1080 restano 104 px, 52 per lato.
prova_quasi("D1 — il caso del kit avanza 52 px per lato",
            spezzatura.margine_residuo_px(1080, 950, 5, 0.08, 200), 52.0)

prova("D2 — se il conto va in negativo il sottotitolo ESCE, e si vede",
      spezzatura.margine_residuo_px(1080, 1080, 20, 0.5, 400) < 0, True)

# ===========================================================================
esito = 0 if not FALLITE else 1
print(f"\n{PASSATE} passate, {len(FALLITE)} fallite, {len(SALTATE)} saltate")
if FALLITE:
    print("FALLITE: " + ", ".join(FALLITE))
if SALTATE:
    print("SALTATE: " + ", ".join(SALTATE))
sys.exit(esito)
