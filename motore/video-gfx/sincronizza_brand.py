"""Genera src/brand.ts da ../brand-kit.json — il montatore legge i valori di brand da lì.

    py sincronizza_brand.py            # rigenera src/brand.ts
    py sincronizza_brand.py --verifica # controlla che sia allineato, non scrive (esce 1 se no)

Perché passare da un file generato invece di importare il JSON direttamente:
`brand-kit.json` sta fuori dalla radice di questo progetto e fuori da `include`
del tsconfig. Un file .ts generato entra nel bundle senza toccare la
configurazione, e resta leggibile a chi apre il progetto.

Da rilanciare ogni volta che si cambia brand-kit.json. `--verifica` serve a
scoprire la divergenza invece di subirla: due motori che disegnano lo stesso
rosso in due modi diversi è il guasto che questo file esiste per evitare.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
KIT_PREDEFINITO = ROOT.parent / "brand-kit.json"
DEST = ROOT / "src" / "brand.ts"


def leggi_kit_da_argomenti(argv: list[str]) -> Path:
    """Accetta sia `--kit=percorso` sia `--kit percorso`.

    Prima accettava solo la forma con l'uguale: scritta con lo spazio, l'argomento
    veniva ignorato in silenzio e si generava il brand SBAGLIATO dicendo che era
    andato tutto bene. Per uno strumento multi-cliente è il guasto peggiore
    possibile, quindi ora una `--kit` senza percorso è un errore, non un default.
    """
    for i, a in enumerate(argv):
        if a.startswith("--kit="):
            valore = a.split("=", 1)[1]
            if not valore:
                raise SystemExit("--kit= senza percorso")
            return Path(valore)
        if a == "--kit":
            if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
                raise SystemExit("--kit vuole un percorso subito dopo")
            return Path(argv[i + 1])
    return KIT_PREDEFINITO


def leggi_pipeline_da_argomenti(argv: list[str]) -> Path:
    """`--pipeline DIR`: la shorts-pipeline da verificare (tappa 5).

    Nel multi-cliente la verifica va fatta contro la COPIA PER-JOB della
    pipeline (che legge il kit del tenant), non contro il checkout
    condiviso col kit del repo. Stessa regola del --kit: un --pipeline
    senza percorso è un errore, mai un default silenzioso.
    """
    for i, a in enumerate(argv):
        if a.startswith("--pipeline="):
            valore = a.split("=", 1)[1]
            if not valore:
                raise SystemExit("--pipeline= senza percorso")
            return Path(valore)
        if a == "--pipeline":
            if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
                raise SystemExit("--pipeline vuole un percorso subito dopo")
            return Path(argv[i + 1])
    return ROOT.parent / "shorts-pipeline"


KIT = leggi_kit_da_argomenti(sys.argv[1:])
PIPELINE = leggi_pipeline_da_argomenti(sys.argv[1:])


def genera() -> str:
    kit = json.loads(KIT.read_text(encoding="utf-8"))
    colori = {k: v for k, v in kit["colori"].items() if not k.startswith("_")}
    car = kit["caratteri"]
    mov = kit["movimento"]

    righe = [
        "// GENERATO da ../../brand-kit.json — non modificare a mano.",
        "// Rigenera con:  py sincronizza_brand.py",
        "",
        "// Niente `as const` qui: stringerebbe i tipi a letterali, e le firme che",
        "// hanno un colore come valore di default smetterebbero di accettarne altri.",
        "export const COLORI: Record<string, string> = {",
        *[f"  {json.dumps(k)}: {json.dumps(v)}," for k, v in colori.items()],
        "};",
        "",
        "export const FAMIGLIE: Record<string, string> = {",
        f"  display: {json.dumps(car['display']['famiglia'])},",
        f"  testo: {json.dumps(car['testo']['famiglia'])},",
        f"  dati: {json.dumps(car['dati']['famiglia'])},",
        "};",
        "",
        "// bezier delle due sole curve ammesse dal canone",
        f"export const BEZIER_RIVISTA = {json.dumps(mov['easing_principale']['bezier'])} as const;",
        f"export const BEZIER_WIPE = {json.dumps(mov['easing_tendina']['bezier'])} as const;",
        "",
    ]
    return "\n".join(righe)


def verifica_shorts() -> list[str]:
    """Confronta brand-kit.json con shorts-pipeline/config.py.

    La pipeline short non legge il brand kit (sono due mondi, python e ffmpeg):
    tiene i suoi valori. Qui non li cambiamo, li confrontiamo — così la deriva
    si scopre invece di subirla.
    """
    conf_dir = PIPELINE
    if not (conf_dir / "config.py").exists():
        return [f"config.py non trovato in {conf_dir}"]
    sys.path.insert(0, str(conf_dir))
    try:
        import config  # type: ignore
    finally:
        sys.path.pop(0)

    kit = json.loads(KIT.read_text(encoding="utf-8"))
    s, f = kit["sottotitoli_short"], kit["formati"]["short"]
    coppie = [
        ("corpo sottotitoli", s["corpo"], config.FONT_SIZE),
        ("parole per pagina", s["parole_per_pagina"], config.MAX_WORDS_PER_PAGE),
        ("parole per pagina nei primi 10s",
         s["parole_per_pagina_primi_10s"], config.MAX_WORDS_PER_PAGE_HOOK),
        ("caratteri per pagina", s["caratteri_per_pagina"], config.MAX_CHARS_PER_PAGE),
        ("posizione x", s["posizione"]["x"], config.SUB_POS_X),
        ("posizione y", s["posizione"]["y"], config.SUB_POS_Y),
        ("rosso in formato ASS",
         kit["colori"]["_rosso_altri_formati"]["ass_libass_bgr"], config.ROSSO_ASS),
        ("larghezza short", f["larghezza"], config.OUT_W),
        ("altezza short", f["altezza"], config.OUT_H),
    ]

    # loudnorm è una stringa di filtro: "loudnorm=I=-14:TP=-1.5:LRA=11"
    parti = dict(p.split("=", 1) for p in config.LOUDNORM.replace("loudnorm=", "").split(":"))
    coppie += [
        ("loudness LUFS", float(kit["audio"]["loudness_lufs"]), float(parti.get("I", "nan"))),
        ("true peak dBTP", float(kit["audio"]["true_peak_dbtp"]), float(parti.get("TP", "nan"))),
    ]
    return [f"{nome}: brand-kit dice {atteso!r}, config.py dice {trovato!r}"
            for nome, atteso, trovato in coppie if str(atteso) != str(trovato)]




def main() -> int:
    if not KIT.exists():
        raise SystemExit(f"manca {KIT}")
    nuovo = genera()
    attuale = DEST.read_text(encoding="utf-8") if DEST.exists() else ""

    if "--verifica" in sys.argv:
        problemi = [] if nuovo == attuale else [
            f"{DEST.name} non corrisponde a brand-kit.json "
            f"(rilancia senza --verifica per riallineare)"]
        problemi += verifica_shorts()
        if not problemi:
            print("allineato: montatore e pipeline short "
                  "corrispondono a brand-kit.json")
            return 0
        print("DIVERGENZE:")
        for p in problemi:
            print(f"   - {p}")
        return 1

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(nuovo, encoding="utf-8")
    print(f"scritto {DEST}" + ("" if nuovo != attuale else " (nessuna differenza)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
