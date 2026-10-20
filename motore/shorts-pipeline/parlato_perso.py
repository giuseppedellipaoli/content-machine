"""Il parlato che il trascritto non ha scritto — e che quindi non ha sottotitoli.

    py parlato_perso.py VIDEO.mp4 TRASCRITTO.json [--json]

METODO. Confronta i livelli dei buchi nel trascritto con il parlato certo dello stesso file. Un buco vicino al livello del parlato va controllato manualmente. Non effettua una seconda trascrizione e non inventa parole mancanti.

COSA FA E COSA NON FA. Segnala e basta. Non tocca il trascritto e non rifa'
nessun sottotitolo: rimettere parole dentro cambierebbe i video prodotti, ed e'
una decisione, non una correzione automatica.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import silenzi

#: Quanto sotto il parlato deve stare un buco perche' sia una pausa credibile.
#: Sei dB sono un dimezzamento dell'ampiezza. Sopra questa soglia il buco suona
#: come il parlato che lo circonda, e va guardato.
SCARTO_SOSPETTO_DB = 6.0

#: Sotto questa durata un buco non si conta: fra una parola e l'altra ci sono
#: sempre frazioni di secondo, e contarle darebbe solo rumore.
DURATA_MINIMA_S = 0.50


def parole_temporizzate(documento: dict) -> list[dict]:
    fuori = []
    for segmento in documento.get("segments", []) or []:
        for parola in segmento.get("words", []) or []:
            if parola.get("start") is None or parola.get("end") is None:
                continue
            fuori.append({"start": float(parola["start"]), "end": float(parola["end"])})
    return sorted(fuori, key=lambda p: p["start"])


def buchi_fra_le_parole(parole: list[dict]) -> list[tuple[float, float]]:
    """Gli intervalli fra una parola e la successiva, sopra la durata minima.

    Il silenzio in testa e in coda al girato NON si conta: quello e' l'attacco
    e lo stacco della registrazione, non parlato perso.
    """
    return [(prima["end"], dopo["start"])
            for prima, dopo in zip(parole, parole[1:])
            if dopo["start"] - prima["end"] >= DURATA_MINIMA_S]


def analizza(video: Path, documento: dict) -> dict:
    """Torna sempre un esito leggibile, anche quando non si puo' misurare."""
    parole = parole_temporizzate(documento)
    if len(parole) < 2:
        return {"misurabile": False, "motivo": "trascritto senza parole temporizzate",
                "intervalli": [], "secondi": 0.0}

    durata = float(documento.get("duration") or parole[-1]["end"])
    celle = silenzi.misura_livelli(video, 0.0, durata)
    if not celle:
        return {"misurabile": False, "motivo": "livelli non misurabili",
                "intervalli": [], "secondi": 0.0}

    dentro = silenzi.celle_di_parlato(celle, parole)
    if not dentro:
        return {"misurabile": False, "motivo": "nessuna cella dentro le parole",
                "intervalli": [], "secondi": 0.0}
    livello_parlato = statistics.median([c["db"] for c in dentro])

    sospetti = []
    for a, b in buchi_fra_le_parole(parole):
        valori = [c["db"] for c in celle if c["t_inizio"] >= a and c["t_fine"] <= b]
        if not valori:
            continue
        mediana = statistics.median(valori)
        if mediana >= livello_parlato - SCARTO_SOSPETTO_DB:
            sospetti.append({
                "da_s": round(a, 2),
                "a_s": round(b, 2),
                "durata_s": round(b - a, 2),
                "livello_db": round(mediana, 2),
                # Col SEGNO e nel verso giusto: positivo = piu' forte del
                # parlato. Chiamarlo «sotto il parlato» con un valore negativo
                # faceva leggere «piu' debole» esattamente al contrario.
                "scarto_dal_parlato_db": round(mediana - livello_parlato, 2),
            })

    return {
        "misurabile": True,
        "durata_s": round(durata, 2),
        "parlato_mediano_db": round(livello_parlato, 2),
        "intervalli": sospetti,
        "secondi": round(sum(s["durata_s"] for s in sospetti), 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("trascritto")
    ap.add_argument("--json", action="store_true", help="esito in JSON su stdout")
    argomenti = ap.parse_args()

    documento = json.loads(Path(argomenti.trascritto).read_text(encoding="utf-8"))
    esito = analizza(Path(argomenti.video), documento)

    if argomenti.json:
        print(json.dumps(esito, ensure_ascii=False))
        return 0

    if not esito["misurabile"]:
        print(f"non misurabile: {esito['motivo']}")
        return 0
    if not esito["intervalli"]:
        print(f"Nessun parlato perso. Durata {esito['durata_s']}s, "
              f"parlato mediano {esito['parlato_mediano_db']} dBFS.")
        return 0

    print(f"PARLATO SENZA SOTTOTITOLI: {esito['secondi']}s "
          f"({100 * esito['secondi'] / esito['durata_s']:.1f}% del girato)")
    for voce in esito["intervalli"]:
        scarto = voce["scarto_dal_parlato_db"]
        verso = "piu' forte del parlato" if scarto >= 0 else "sotto il parlato"
        print(f"  {voce['da_s']:7.2f}s - {voce['a_s']:7.2f}s  ({voce['durata_s']:.2f}s)  "
              f"livello {voce['livello_db']} dBFS, {abs(scarto):.2f} dB {verso}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
