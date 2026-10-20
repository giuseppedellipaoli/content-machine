"""Prove della conversione delle immagini all'ingresso.

Si esegue cosi', dalla cartella motore/shorts-pipeline:

    py prova_ingresso_immagini.py

Deterministiche, senza rete: i file di prova si generano con Pillow qui dentro.
NON importa config.py apposta — ingresso_immagini.py non dipende dal brand kit,
e la prova deve poter girare anche dove il kit non c'e'.

COSA SI PROVA, E PERCHE' PROPRIO QUESTO.
1. L'INSIEME delle estensioni. E' l'unico posto in cui la nostra versione e'
   piu' larga dell'originale (`tif` e `webp` in piu'), e se qualcuno un giorno
   lo restringe «per pulizia» torna il bug che ha fatto scrivere il modulo.
2. L'ORIENTAMENTO EXIF applicato ai PIXEL. E' la cosa che tutti dimenticano e
   che fa uscire le foto verticali coricate. Si prova con una foto larga a cui
   si mette il campo di rotazione: dopo la conversione deve essere ALTA.
3. Che le dimensioni NON cambino se non lo si chiede. La conversione cambia il
   formato, non la qualita': l'assenza di ridimensionamento e' una decisione,
   e va difesa da chi la scambia per una dimenticanza.
4. Che i metadati EXIF/GPS NON finiscano nel file che va verso un servizio
   esterno.

HEIC: qui NON si prova. Pillow da solo non legge HEIC e in questo ambiente
`pillow-heif` non e' installato (verificato). Si prova invece che il messaggio
d'errore nomini il pacchetto mancante, che e' la sola cosa che serve a chi
incontrera' il problema.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

import ingresso_immagini as ingresso

FALLITE: list[str] = []


def prova(nome: str, ottenuto, atteso) -> None:
    if ottenuto == atteso:
        print(f"  ok   {nome}")
    else:
        FALLITE.append(nome)
        print(f"  FAIL {nome}\n       ottenuto: {ottenuto!r}\n       atteso:   {atteso!r}")


def prova_vero(nome: str, condizione, dettaglio: str = "") -> None:
    if condizione:
        print(f"  ok   {nome}")
    else:
        FALLITE.append(nome)
        print(f"  FAIL {nome}" + (f"\n       {dettaglio}" if dettaglio else ""))


def immagine_rossa(larghezza: int, altezza: int) -> Image.Image:
    # Rosso del brand: se un giorno la conversione sbagliasse spazio colore, il
    # rosso e' il canale in cui si vede per primo.
    return Image.new("RGB", (larghezza, altezza), (226, 35, 26))


def prove_predicato() -> None:
    print("\n[1] quali estensioni fanno scattare la conversione")
    for nome in ["foto.heic", "FOTO.HEIC", "scan.heif", "scan.tiff", "scan.tif", "grafica.webp"]:
        prova_vero(f"serve conversione per {nome}", ingresso.serve_conversione(nome))
    for nome in ["foto.jpg", "foto.jpeg", "grafica.png", "video.mp4"]:
        prova_vero(f"NON serve per {nome}", not ingresso.serve_conversione(nome))

    # I due che l'originale non aveva. `tif` e' comunissimo nelle scansioni e
    # `webp` il progetto lo considera un'immagine valida altrove: senza, meta'
    # dei file passa e meta' si rompe, e la differenza e' tre lettere.
    prova_vero("il difetto dichiarato e corretto: tif e webp ci sono",
               {".tif", ".webp"} <= ingresso.ESTENSIONI_DA_CONVERTIRE)

    # Il giudizio e' SINTATTICO e va saputo: un HEIC rinominato .jpg non viene
    # convertito, un JPEG rinominato .tiff viene convertito per niente.
    prova_vero("il giudizio guarda il nome, non il contenuto (dichiarato)",
               not ingresso.serve_conversione("davvero-un-heic.jpg"))


def prove_conversione(lavoro: Path) -> None:
    print("\n[2] la conversione vera")
    sorgente = lavoro / "scansione.tiff"
    immagine_rossa(800, 600).save(sorgente, format="TIFF")

    esito = ingresso.converti_in_jpeg(sorgente)
    prodotto = Path(esito["destinazione"])
    prova("l uscita e accanto alla sorgente con estensione .jpg", prodotto.name, "scansione.jpg")
    prova_vero("il file esiste", prodotto.is_file())
    with Image.open(prodotto) as riletta:
        prova("il formato e JPEG", riletta.format, "JPEG")
        prova("le dimensioni NON cambiano", riletta.size, (800, 600))
    prova_vero("la sorgente e intatta", sorgente.is_file())
    prova_vero("nessun parziale rimasto",
               not (lavoro / "scansione.jpg.parziale").exists())

    print("\n[3] il ridimensionamento c'e' solo se lo si chiede")
    grande = lavoro / "grande.tiff"
    immagine_rossa(4000, 2000).save(grande, format="TIFF")
    senza = ingresso.converti_in_jpeg(grande, lavoro / "senza-limite.jpg")
    prova("senza limite le dimensioni restano quelle", (senza["larghezza"], senza["altezza"]), (4000, 2000))
    con = ingresso.converti_in_jpeg(grande, lavoro / "con-limite.jpg", lato_lungo_max=1000)
    prova("col limite scende il lato lungo", (con["larghezza"], con["altezza"]), (1000, 500))
    sotto = ingresso.converti_in_jpeg(sorgente, lavoro / "sotto-limite.jpg", lato_lungo_max=5000)
    prova("un limite piu alto del lato lungo non ingrandisce niente",
          (sotto["larghezza"], sotto["altezza"]), (800, 600))


def prove_orientamento(lavoro: Path) -> None:
    print("\n[4] l orientamento EXIF applicato ai PIXEL")
    # Un'immagine LARGA (900x300) con orientamento 6, che vuol dire «ruotala di
    # 90 gradi in senso orario per vederla giusta». Dopo la conversione deve
    # essere ALTA (300x900) e senza piu' il campo di orientamento.
    sorgente = lavoro / "coricata.webp"
    con_exif = immagine_rossa(900, 300)
    exif = Image.Exif()
    exif[274] = 6  # 274 = Orientation
    con_exif.save(sorgente, format="WEBP", exif=exif, lossless=True)

    with Image.open(sorgente) as riletta:
        letto = riletta.getexif().get(274)
    if letto != 6:
        # Se Pillow di questo ambiente non riscrive l'orientamento nel WEBP, la
        # prova non puo' dire niente: lo si dichiara invece di far finta.
        print(f"  SALTATA la prova sull orientamento: l ambiente non conserva il campo EXIF nel WEBP (letto {letto!r})")
        return

    esito = ingresso.converti_in_jpeg(sorgente, lavoro / "diritta.jpg")
    prova("i pixel sono ruotati: da 900x300 a 300x900",
          (esito["larghezza"], esito["altezza"]), (300, 900))
    with Image.open(esito["destinazione"]) as prodotta:
        orientamento = prodotta.getexif().get(274)
    prova_vero("nel file prodotto non resta il campo di orientamento",
               orientamento in (None, 1), f"orientamento letto: {orientamento!r}")


def prove_metadati(lavoro: Path) -> None:
    print("\n[5] EXIF, GPS e IPTC non viaggiano verso l esterno")
    sorgente = lavoro / "con-metadati.tiff"
    exif = Image.Exif()
    exif[271] = "MarcaFinta"        # Make
    exif[272] = "ModelloFinto"      # Model
    exif[306] = "2026:08:17 10:00:00"  # DateTime
    immagine_rossa(400, 300).save(sorgente, format="TIFF", exif=exif)

    esito = ingresso.converti_in_jpeg(sorgente, lavoro / "pulita.jpg")
    with Image.open(esito["destinazione"]) as prodotta:
        residui = dict(prodotta.getexif())
    prova_vero("nessun dato di camera nel file prodotto",
               271 not in residui and 272 not in residui and 306 not in residui,
               f"residui: {residui!r}")


def prove_trasparenza(lavoro: Path) -> None:
    print("\n[6] la trasparenza finisce su un fondo dichiarato, non a caso")
    sorgente = lavoro / "trasparente.webp"
    Image.new("RGBA", (100, 100), (226, 35, 26, 0)).save(sorgente, format="WEBP", lossless=True)
    esito = ingresso.converti_in_jpeg(sorgente, lavoro / "appoggiata.jpg")
    with Image.open(esito["destinazione"]) as prodotta:
        prova("il JPEG e senza canale alfa", prodotta.mode, "RGB")
        prova("il pieno trasparente finisce sul fondo bianco dichiarato",
              prodotta.convert("RGB").getpixel((50, 50)), ingresso.FONDO_TRASPARENZA)


def prove_errori(lavoro: Path) -> None:
    print("\n[7] gli errori dicono cosa e successo davvero")
    try:
        ingresso.converti_in_jpeg(lavoro / "non-esiste.tiff")
        FALLITE.append("un file inesistente deve sollevare")
        print("  FAIL un file inesistente deve sollevare")
    except ingresso.ConversioneFallita as errore:
        prova_vero("un file inesistente lo dice", "inesistente" in str(errore), str(errore))

    rotto = lavoro / "rotto.tiff"
    rotto.write_bytes(b"questo non e' un TIFF")
    try:
        ingresso.converti_in_jpeg(rotto)
        FALLITE.append("un file illeggibile deve sollevare")
        print("  FAIL un file illeggibile deve sollevare")
    except ingresso.ConversioneFallita as errore:
        prova_vero("un file illeggibile lo dice", "non decodificabile" in str(errore), str(errore))
    prova_vero("nessun parziale rimasto dopo un fallimento",
               not (lavoro / "rotto.jpg.parziale").exists())

    # HEIC senza pillow-heif: il messaggio deve NOMINARE il pacchetto mancante.
    # Un `UnidentifiedImageError` nudo non aiuta nessuno.
    try:
        import pillow_heif  # noqa: F401
        print("  SALTATA la prova sul messaggio HEIC: pillow-heif e installato in questo ambiente")
    except ImportError:
        finto_heic = lavoro / "foto.heic"
        finto_heic.write_bytes(b"non importa, non si arriva a decodificarlo")
        try:
            ingresso.converti_in_jpeg(finto_heic)
            FALLITE.append("un HEIC senza pillow-heif deve sollevare")
            print("  FAIL un HEIC senza pillow-heif deve sollevare")
        except ingresso.ConversioneFallita as errore:
            prova_vero("il messaggio HEIC nomina il pacchetto mancante",
                       "pillow-heif" in str(errore), str(errore))


def prove_riga_di_comando(lavoro: Path) -> None:
    print("\n[8] la riga di comando: «niente da fare» non e' un errore")
    gia_conforme = lavoro / "gia.jpg"
    immagine_rossa(200, 100).save(gia_conforme, format="JPEG")

    esito = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("ingresso_immagini.py")), str(gia_conforme)],
        capture_output=True, text=True, encoding="utf-8")
    prova("uscita 0 su un file gia conforme", esito.returncode, 0)
    risposta = json.loads(esito.stdout.strip())
    prova("dice che non ha convertito niente", risposta["convertito"], False)
    prova("e dice perche", risposta["motivo"], "gia_conforme")

    sorgente = lavoro / "da-convertire.tiff"
    immagine_rossa(300, 200).save(sorgente, format="TIFF")
    esito = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("ingresso_immagini.py")), str(sorgente),
         "--destinazione", str(lavoro / "cli.jpg")],
        capture_output=True, text=True, encoding="utf-8")
    prova("uscita 0 sulla conversione", esito.returncode, 0)
    risposta = json.loads(esito.stdout.strip())
    prova("dice che ha convertito", risposta["convertito"], True)
    prova("e dice le dimensioni", (risposta["larghezza"], risposta["altezza"]), (300, 200))
    prova_vero("il file c'e davvero", Path(risposta["destinazione"]).is_file())


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="prova-ingresso-") as cartella:
        lavoro = Path(cartella)
        prove_predicato()
        prove_conversione(lavoro)
        prove_orientamento(lavoro)
        prove_metadati(lavoro)
        prove_trasparenza(lavoro)
        prove_errori(lavoro)
        prove_riga_di_comando(lavoro)

    print()
    if FALLITE:
        print(f"FALLITE {len(FALLITE)}: " + ", ".join(FALLITE))
        return 1
    print("tutte le prove passate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
