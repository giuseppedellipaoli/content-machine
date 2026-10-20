"""Prima e dopo: cosa cambierebbe collegando la catena dei sottotitoli.

    py confronta_spezzatura.py TRASCRITTO.json [--clip-inizio S] [--clip-fine S]

NON CAMBIA NIENTE. Legge un trascritto, impagina nei DUE modi, e stampa la
differenza. Serve a decidere con i numeri davanti invece che a intuito.

    OGGI    `render.py::paginate` chiude la pagina contando parole e caratteri.
            Un tetto di caratteri non e' una larghezza: «MMMMMMM» e «iiiiiii»
            contano sette e sullo schermo sono larghi il doppio l'uno
            dell'altro. Quindi il tetto e' tarato sul caso peggiore, e per
            tutto il resto del tempo lascia mezzo fotogramma vuoto.

    DOPO    `spezzatura.py::pagine_da_parole` misura la riga col font vero e
            la spezza quando supera il rapporto delle fondamenta (0,88).

La riga che conta nell'uscita e' **quante pagine di oggi sforano davvero**:
sono i sottotitoli che escono dal fotogramma adesso, in produzione, e che
nessuno ha mai contato.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import config
import fondamenta
import render
import spezzatura


def parole_dal_trascritto(documento: dict, da: float | None, a: float | None) -> list[dict]:
    """Le parole del trascritto, nella forma che usano tutte e due le strade."""
    parole: list[dict] = []
    for segmento in documento.get("segments", []):
        for parola in segmento.get("words", []) or []:
            inizio = parola.get("start")
            fine = parola.get("end")
            testo = (parola.get("word") or parola.get("w") or "").strip()
            if inizio is None or fine is None or not testo:
                continue
            if da is not None and fine < da:
                continue
            if a is not None and inizio > a:
                continue
            parole.append({"w": testo, "start": float(inizio), "end": float(fine)})
    return parole


def testo_pagina(pagina: list[dict]) -> str:
    return " ".join(p["w"] for p in pagina)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trascritto")
    ap.add_argument("--clip-inizio", type=float, default=None)
    ap.add_argument("--clip-fine", type=float, default=None)
    argomenti = ap.parse_args()

    documento = json.loads(Path(argomenti.trascritto).read_text(encoding="utf-8"))
    parole = parole_dal_trascritto(documento, argomenti.clip_inizio, argomenti.clip_fine)
    if not parole:
        print("nessuna parola temporizzata nel trascritto", file=sys.stderr)
        return 1

    inizio_clip = argomenti.clip_inizio if argomenti.clip_inizio is not None else 0.0

    # La misura, col font che libass carichera' davvero. La famiglia si legge
    # da family.txt come fa render.py: misurare un file diverso da quello
    # disegnato sposterebbe il disallineamento di un passo invece di toglierlo.
    corpo = float(config.FONT_SIZE)
    cartella = Path(config.FONTS_DIR)
    family_txt = cartella / "family.txt"
    family = family_txt.read_text(encoding="utf-8").strip() if family_txt.exists() else "Arial"
    try:
        misura = spezzatura.MisuraTesto.dal_kit(cartella, family, corpo)
    except spezzatura.FontNonMisurabile as errore:
        print(f"misura non disponibile: {errore}", file=sys.stderr)
        return 1

    larghezza_max = fondamenta.larghezza_max_testo_px(config.OUT_W)

    # --- OGGI ---
    pagine_oggi = render.paginate(parole, inizio_clip)
    # --- DOPO ---
    pagine_dopo, avvisi = spezzatura.pagine_da_parole(
        parole, misura, larghezza_max,
        gap_s=config.PAGE_GAP_S,
        hook_fino_a_s=config.HOOK_FINO_A_S,
        parole_hook=config.MAX_WORDS_PER_PAGE_HOOK,
        tetto_parole=config.MAX_WORDS_PER_PAGE,
        tetto_caratteri=config.MAX_CHARS_PER_PAGE,
        inizio_clip_s=inizio_clip)

    print(f"font      {misura.percorso.name}  corpo {corpo:g}px")
    print(f"larghezza massima  {larghezza_max:.1f}px su {config.OUT_W}px di fotogramma")
    print(f"parole    {len(parole)}")
    print()
    print(f"pagine OGGI  {len(pagine_oggi)}")
    print(f"pagine DOPO  {len(pagine_dopo)}")
    print()

    # IL NUMERO CHE CONTA: quante pagine di oggi escono dal fotogramma.
    sforano = []
    for indice, pagina in enumerate(pagine_oggi):
        testo = testo_pagina(pagina)
        larghezza = misura.larghezza(testo)
        if larghezza > larghezza_max:
            sforano.append((indice, testo, larghezza))

    if sforano:
        print(f"PAGINE CHE OGGI ESCONO DAL FOTOGRAMMA: {len(sforano)} su {len(pagine_oggi)}")
        for indice, testo, larghezza in sforano:
            eccesso = larghezza - larghezza_max
            print(f"  [{indice}] {larghezza:7.1f}px  (+{eccesso:.1f} oltre il limite)  «{testo}»")
    else:
        print(f"Nessuna pagina di oggi supera il limite (su {len(pagine_oggi)} controllate).")
    print()

    # E il verso opposto: quanto spazio lascia vuoto il metodo di oggi.
    larghezze = [misura.larghezza(testo_pagina(p)) for p in pagine_oggi]
    if larghezze:
        media = sum(larghezze) / len(larghezze)
        print(f"riempimento medio OGGI  {100 * media / larghezza_max:.0f}% della larghezza utile")
        # IL NUMERO DA GUARDARE PRIMA DI ALZARE I TETTI: non la media, ma la
        # pagina piu' larga che e' uscita davvero. E' quella che tocca il bordo
        # per prima quando qualcuno allarga `caratteri_per_pagina`.
        piu_larga = max(larghezze)
        indice_larga = larghezze.index(piu_larga)
        print(f"pagina PIU' LARGA oggi  {piu_larga:.1f}px = "
              f"{100 * piu_larga / larghezza_max:.0f}% del limite  "
              f"(margine {larghezza_max - piu_larga:.0f}px)")
        print(f"                        «{testo_pagina(pagine_oggi[indice_larga])}»")

    # La condizione sufficiente sui tetti: se passa, non serve guardare altro.
    tetti = spezzatura.tetti_sicuri(misura, config.MAX_CHARS_PER_PAGE, larghezza_max,
                                    contorno_px=5, fattore_pop=0.08)
    if tetti["sicuri"]:
        print(f"tetti DIMOSTRATI sicuri: con {tetti['tetto_caratteri']} caratteri "
              f"nessuna pagina puo' sforare, qualunque sia il testo.")
    else:
        print(f"tetti non dimostrabili a priori (il caso peggiore sarebbe "
              f"{tetti['tetto_caratteri']} volte «{tetti['carattere_piu_largo']}» = "
              f"{tetti['caso_peggiore_px']:.0f}px): vale il numero misurato qui sopra.")
    larghezze_dopo = [misura.larghezza(testo_pagina(p)) for p in pagine_dopo]
    if larghezze_dopo:
        media = sum(larghezze_dopo) / len(larghezze_dopo)
        print(f"riempimento medio DOPO  {100 * media / larghezza_max:.0f}% della larghezza utile")
    print()

    # Le pagine che cambiano davvero, affiancate.
    diverse = 0
    for indice in range(max(len(pagine_oggi), len(pagine_dopo))):
        a = testo_pagina(pagine_oggi[indice]) if indice < len(pagine_oggi) else "—"
        b = testo_pagina(pagine_dopo[indice]) if indice < len(pagine_dopo) else "—"
        if a != b:
            diverse += 1
            if diverse <= 12:
                print(f"  [{indice}] OGGI «{a}»")
                print(f"       DOPO «{b}»")
    if diverse > 12:
        print(f"  ... e altre {diverse - 12} pagine diverse (mostrate le prime 12)")
    print()
    print(f"pagine diverse  {diverse}")

    if avvisi:
        print()
        print("avvisi della strada nuova:")
        for avviso in avvisi:
            print(f"  - {avviso}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
