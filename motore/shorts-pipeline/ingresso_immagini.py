"""Immagini all'ingresso: HEIC/HEIF/TIFF/TIF/WEBP convertite in JPEG.

PERCHE' ESISTE QUESTO FILE. HEIC e' il formato fotografico predefinito
dell'iPhone. Oggi una foto scattata col telefono arriva nel sistema e o si
rompe, o torna un errore incomprensibile del servizio a valle — dopo che i
megabyte sono gia' stati trasferiti. E' il caso piu' banale e piu' frequente
di rottura all'ingresso di un prodotto web, e costa mezza giornata risolverlo.

COSA FA, E COSA DELIBERATAMENTE NON FA.
Converte il FORMATO. Non ridimensiona, se non glielo si chiede: le immagini di
riferimento servono a piena risoluzione, e la soglia dei 1568 pixel che si usa
altrove serve a contenere il contesto del modello, non la qualita' di
un'immagine. Il limite esiste come parametro, con valore predefinito «nessun
limite», cosi' chi ha un servizio schizzinoso lo impone e gli altri no.

L'ORIENTAMENTO EXIF VIENE APPLICATO AI PIXEL. E' la parte che nessuno ricorda
e che fa uscire tutte le foto verticali coricate: il JPEG prodotto e' gia'
diritto e non porta piu' il campo di orientamento.

DA DOVE VIENE. Corpus SPEC del progetto video fermo, documento 75
(PREPROCESSING-MEDIA) §4, voce 1.6 della raccolta. Loro convertono
{heic, heif, tiff}: mancano `tif` (variante a tre lettere, comunissima nelle
scansioni) e `webp` (che lo stesso progetto considera un'immagine valida
altrove). Le aggiungiamo, e la differenza sta scritta qui sotto.

Uso da riga di comando (torna una riga JSON su stdout):

    py ingresso_immagini.py FOTO.heic --destinazione fuori.jpg
    py ingresso_immagini.py FOTO.jpg --solo-verifica
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageOps

# L'insieme che fa scattare la conversione. Il giudizio e' SINTATTICO,
# sull'estensione in minuscolo, e va detto cosa comporta: un HEIC rinominato
# `.jpg` non viene convertito, e un JPEG rinominato `.tiff` viene convertito
# senza motivo. E' il compromesso voluto — leggere l'intestazione di ogni file
# costerebbe un accesso al disco per una domanda a cui l'estensione risponde
# bene nel 99% dei casi. Chi vuole il giudizio sul contenuto chiama comunque
# converti_in_jpeg, che e' indipendente dal predicato.
ESTENSIONI_DA_CONVERTIRE = frozenset({".heic", ".heif", ".tiff", ".tif", ".webp"})

# Qualita' JPEG. 0,92 sulla scala 0-1 dell'originale, cioe' 92 su quella di
# Pillow. E' il compromesso qualita'/peso gia' scelto: non si tocca senza un
# motivo, perche' cambia il peso di ogni immagine di riferimento.
QUALITA_JPEG = 92

# Colore su cui si appoggia una trasparenza. Il JPEG non ha canale alfa: un
# TIFF o un WEBP trasparente DEVE finire su qualcosa. Nell'originale la scelta
# era lasciata al comportamento predefinito del sistema, cioe' non era una
# scelta. Qui e' bianco, dichiarato: su nero le grafiche con testo scuro
# sparirebbero.
FONDO_TRASPARENZA = (255, 255, 255)


class ConversioneFallita(RuntimeError):
    """Conversione impossibile. Il messaggio nomina il file e il motivo vero."""


def serve_conversione(percorso: str | os.PathLike[str]) -> bool:
    """Vero se l'estensione appartiene all'insieme da convertire."""
    return Path(percorso).suffix.lower() in ESTENSIONI_DA_CONVERTIRE


def _registra_heif() -> bool:
    """Registra il lettore HEIC/HEIF in Pillow, se il pacchetto c'e'.

    Pillow da solo non legge HEIC. Serve pillow-heif. Se manca, un HEIC non si
    apre: si dice CHE COSA manca invece di lasciare risalire un
    `UnidentifiedImageError` che non spiega niente a nessuno.
    """
    try:
        import pillow_heif  # type: ignore
    except ImportError:
        return False
    pillow_heif.register_heif_opener()
    return True


def _apri(sorgente: Path) -> Image.Image:
    estensione = sorgente.suffix.lower()
    if estensione in {".heic", ".heif"} and not _registra_heif():
        raise ConversioneFallita(
            f"{sorgente.name}: per leggere HEIC/HEIF serve il pacchetto "
            "'pillow-heif' nel venv del motore (pip install pillow-heif). "
            "Senza, una foto dell'iPhone non entra.")
    try:
        immagine = Image.open(sorgente)
    except Exception as errore:  # PIL solleva tipi diversi per formati diversi
        raise ConversioneFallita(f"{sorgente.name}: non decodificabile ({errore})") from errore
    # Multipagina (TIFF di scansione, WEBP animato): si legge SOLO la pagina 0.
    # E' il comportamento dell'originale e va dichiarato, non scoperto.
    if getattr(immagine, "n_frames", 1) > 1:
        immagine.seek(0)
    return immagine


def _senza_alfa(immagine: Image.Image) -> Image.Image:
    if immagine.mode in {"RGBA", "LA"} or (immagine.mode == "P" and "transparency" in immagine.info):
        con_alfa = immagine.convert("RGBA")
        fondo = Image.new("RGB", con_alfa.size, FONDO_TRASPARENZA)
        fondo.paste(con_alfa, mask=con_alfa.split()[-1])
        return fondo
    if immagine.mode != "RGB":
        # TIFF a 16 bit per canale, scala di grigi, CMYK: il JPEG regge 8 bit
        # RGB e basta. La perdita e' del formato di destinazione, inevitabile.
        return immagine.convert("RGB")
    return immagine


def converti_in_jpeg(
    sorgente: str | os.PathLike[str],
    destinazione: str | os.PathLike[str] | None = None,
    qualita: int = QUALITA_JPEG,
    lato_lungo_max: int | None = None,
) -> dict:
    """Converte in JPEG e torna i dati del file prodotto.

    - orientamento EXIF applicato ai pixel (uscita gia' diritta);
    - profilo colore CONSERVATO: un HEIC Display P3 produce un JPEG Display P3,
      nessuna conversione a sRGB alle spalle di chi guarda;
    - EXIF, GPS e IPTC NON copiati: per un'immagine che va verso un servizio
      esterno e' la scelta giusta sulla riservatezza, e qui e' dichiarata
      invece di essere un effetto collaterale;
    - scrittura ATOMICA: si scrive accanto e si rinomina, cosi' nessuno legge
      mai un file mezzo scritto;
    - su errore il parziale viene RIMOSSO.
    """
    sorgente = Path(sorgente)
    if not sorgente.is_file():
        raise ConversioneFallita(f"{sorgente}: file inesistente")
    destinazione = Path(destinazione) if destinazione else sorgente.with_suffix(".jpg")
    if destinazione.resolve() == sorgente.resolve():
        raise ConversioneFallita(f"{sorgente.name}: destinazione uguale alla sorgente")

    parziale = destinazione.with_name(destinazione.name + ".parziale")
    try:
        with _apri(sorgente) as originale:
            # exif_transpose ruota e riflette i PIXEL secondo il campo EXIF e
            # toglie il campo: l'uscita e' diritta per chiunque la apra, anche
            # per chi l'orientamento non lo legge.
            diritta = ImageOps.exif_transpose(originale)
            profilo = diritta.info.get("icc_profile")
            piatta = _senza_alfa(diritta)
            if lato_lungo_max is not None and lato_lungo_max > 0:
                if max(piatta.size) > lato_lungo_max:
                    piatta.thumbnail((lato_lungo_max, lato_lungo_max), Image.LANCZOS)
            destinazione.parent.mkdir(parents=True, exist_ok=True)
            # subsampling 0 = 4:4:4, nessun sottocampionamento della crominanza.
            # Su un'immagine di riferimento il rosso del brand su fondo scuro
            # e' esattamente cio' che il 4:2:0 sporca per primo.
            opzioni: dict = {"quality": int(qualita), "subsampling": 0}
            if profilo:
                opzioni["icc_profile"] = profilo
            piatta.save(parziale, format="JPEG", **opzioni)
            larghezza, altezza = piatta.size
        os.replace(parziale, destinazione)
    except ConversioneFallita:
        _togli(parziale)
        raise
    except Exception as errore:
        _togli(parziale)
        raise ConversioneFallita(f"{sorgente.name}: conversione in JPEG fallita ({errore})") from errore

    return {
        "convertito": True,
        "sorgente": str(sorgente),
        "destinazione": str(destinazione),
        "larghezza": larghezza,
        "altezza": altezza,
        "byte": destinazione.stat().st_size,
    }


def _togli(percorso: Path) -> None:
    try:
        percorso.unlink(missing_ok=True)
    except OSError:
        # Se il parziale non si toglie non e' questo il guasto da raccontare.
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Converte in JPEG le immagini che i servizi a valle non decodificano.")
    ap.add_argument("sorgente")
    ap.add_argument("--destinazione", help="predefinito: la sorgente con estensione .jpg")
    ap.add_argument("--qualita", type=int, default=QUALITA_JPEG, help=f"0-100 (predefinito {QUALITA_JPEG})")
    ap.add_argument("--lato-lungo-max", type=int, default=None,
                    help="pixel del lato lungo. Assente = NESSUN ridimensionamento, che e' il comportamento voluto")
    ap.add_argument("--solo-verifica", action="store_true",
                    help="dice solo se la conversione serve, senza toccare niente")
    ap.add_argument("--converti-sempre", action="store_true",
                    help="converte anche se l'estensione non e' fra quelle da convertire")
    argomenti = ap.parse_args()

    sorgente = Path(argomenti.sorgente)
    serve = serve_conversione(sorgente)
    if argomenti.solo_verifica:
        print(json.dumps({"serve_conversione": serve, "sorgente": str(sorgente)}, ensure_ascii=False))
        return 0
    if not serve and not argomenti.converti_sempre:
        # «Nessun file prodotto» NON e' un errore: significa usa l'originale.
        print(json.dumps({"convertito": False, "motivo": "gia_conforme",
                          "sorgente": str(sorgente)}, ensure_ascii=False))
        return 0
    try:
        esito = converti_in_jpeg(sorgente, argomenti.destinazione, argomenti.qualita, argomenti.lato_lungo_max)
    except ConversioneFallita as errore:
        print(f"ERRORE: {errore}", file=sys.stderr)
        return 1
    print(json.dumps(esito, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
