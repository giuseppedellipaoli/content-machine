"""Giudizio D2a: piano FX di uno short, con ancore a indici di parola.

Il modello riceve le parole della clip con l'indice GLOBALE di parola e
propone gli eventi (pill senza ancore, gli altri ancorati a indici).
IL CODICE converte indici -> secondi relativi all'inizio della clip
(margine -0.1 su t0, +0.3 su t1), impone la cta finale con la parola chiave,
scrive fx_plans.json nel formato della tappa 1 e fa girare valida_canone.py:
se il canone non passa, exit 1.

Uso:
    componi_fx.py TRANSCRIPT_JSON HIGHLIGHTS_JSON --parola-chiave PAROLA
                  --guida guide/HOOK-GUIDE.md --uscita FX_PLANS_JSON
                  --nome-short NOME_FILE_MP4 [--indice-clip 0]
                  [--metadata OUT_STEM_JSON] [--nota "cosa non andava"]

--nota è la correzione chiesta dal pannello quando questo passo viene fatto
rifare: entra in testa al MESSAGGIO, sotto le regole del system (llm.py,
REGOLE_CORREZIONE). Tocca i CONTENUTI degli overlay (testi, scelta degli
eventi); la geometria resta del codice e il canone lo valida comunque
valida_canone.py, quindi una nota non può produrre un piano fuori canone.

Con --metadata (out/<stem>.json scritto da render.py) inizio e durata della
clip sono quelli REALI del video renderizzato (render.py applica il padding
PAD_START_S/PAD_END_S): senza, si derivano dalle parole e gli eventi
risulterebbero anticipati di ~0.2s.

I PEZZI. Dal momento in cui si puo' togliere una pausa o una frase da dentro
uno short, la clip non e' piu' una finestra sola sul girato: il metadata porta
'pezzi', i tratti che restano, e la conversione indice di parola -> secondo
della clip NON e' piu' una sottrazione. Passa da tagli.tempo_nella_clip, che
tiene conto dei buchi. Una parola tolta dal montaggio esce anche dalla mappa,
quindi un evento ancorato a lei viene scartato con un avviso invece di finire
sopra la frase sbagliata. Con un pezzo solo — cioe' su ogni clip mai tagliata
— i numeri sono identici a quelli di prima.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
# La matematica dei pezzi vive in un posto solo: motore/shorts-pipeline/tagli.py.
# Non dipende da config.py (niente brand kit da caricare) proprio perche' la
# possano usare anche i giudizi dell'orchestratore.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shorts-pipeline"))

from pydantic import BaseModel

import fondamenta
import llm
import tagli

MODELLO_DEFAULT = "external-agent"
TIPI_EVENTO = ("pill", "hook", "card", "counter", "list", "claim", "cta", "stamp")
MARGINE_T0 = 0.1
MARGINE_T1 = 0.3

SYSTEM_BASE = """Componi il piano degli eventi grafici (overlay) di uno short verticale.
Ricevi le parole della clip nel formato "indice:parola" (indice GLOBALE di
parola nel video). Non conosci i tempi e non devi inventarli: ogni evento si
ancora a indici di parola, la conversione in secondi la fa il codice.

Gli otto tipi di evento:
- pill: banner alto di apertura. SENZA ancore (tempi fissi nel codice).
  Solo text, 4-8 parole fra virgolette «». Segue la guida qui sotto: non
  ripete la voce, crea curiosità.
- hook: kicker + text + red, ancorato (parola_inizio_idx, parola_fine_idx).
- card: text + red, ancorata. Trascrive il parlato chiave, secca.
- counter: label + to (il numero di arrivo) + red come etichetta rossa,
  ancorato. Solo per numeri detti davvero nel parlato.
- list: header + items [{text, parola_idx}], ancorata; ogni voce appare
  sulla parola indicata.
- claim: text + red, ancorato (basta parola_inizio_idx).
- cta: kicker + text + red, ancorata. La cta FINALE chiede di scrivere nei
  commenti la parola chiave indicata nel messaggio (text = la parola).
- stamp: il timbro sul payoff, solo parola_inizio_idx.

Regole dure:
- un solo elemento rosso per evento;
- mai due eventi a schermo nello stesso istante (pill esclusa): le ancore
  di eventi diversi non si sovrappongono;
- niente numeri che non stanno nel parlato;
- ancore SOLO su indici presenti nell'elenco ricevuto.

""" + llm.RIGA_ANTI_INJECTION + """
""" + llm.REGOLE_CORREZIONE + """
--- GUIDA HOOK ---
"""


class VoceLista(BaseModel):
    text: str
    parola_idx: int


class EventoFx(BaseModel):
    type: Literal["pill", "hook", "card", "counter", "list", "claim", "cta", "stamp"]
    text: Optional[str] = None
    red: Optional[str] = None
    kicker: Optional[str] = None
    label: Optional[str] = None
    to: Optional[int] = None
    header: Optional[str] = None
    items: Optional[list[VoceLista]] = None
    parola_inizio_idx: Optional[int] = None
    parola_fine_idx: Optional[int] = None


class PianoFx(BaseModel):
    eventi: list[EventoFx]


def parole_della_clip(segmenti: list[dict], seg_start: int, seg_end: int,
                      pezzi: list[dict] | None = None):
    """Parole della clip con indice globale: {idx: (testo, start, end)}.

    Con 'pezzi' restano solo le parole che sono DAVVERO nel montaggio: una
    tolta da un taglio esce dalla mappa, e l'evento che ci si ancorava viene
    scartato con un avviso (converti). Senza pezzi il comportamento e' quello
    di sempre.
    """
    mappa: dict[int, tuple[str, float, float]] = {}
    globale = 0
    for seg in segmenti:
        for w in seg["words"]:
            if seg_start <= seg["id"] <= seg_end:
                dentro = pezzi is None or any(
                    w["end"] > p["inizio"] + tagli.EPS and w["start"] < p["fine"] - tagli.EPS
                    for p in pezzi)
                if dentro:
                    mappa[globale] = (w["w"], w["start"], w["end"])
            globale += 1
    return mappa


def secondi(mappa: dict, idx: int, pezzi: list[dict], fine: bool) -> float:
    """Indice di parola -> secondi della clip, coi margini del canone.

    La conversione passa dai PEZZI, non da una sottrazione: con un buco in
    mezzo, la parola dopo di lui sta a un secondo diverso da quello che darebbe
    start - inizio_clip. Con un pezzo solo i due conti coincidono.

    I margini si applicano DOPO la conversione, cioe' sulla timeline della clip:
    sono un anticipo e una coda a schermo, non uno spostamento nel girato.
    """
    _, start, end = mappa[idx]
    if fine:
        return fondamenta.arrotonda_decimale(
            tagli.tempo_agganciato(pezzi, end)[0] + MARGINE_T1, 2)
    return fondamenta.arrotonda_decimale(
        max(0.0, tagli.tempo_agganciato(pezzi, start)[0] - MARGINE_T0), 2)


def converti(piano: PianoFx, mappa: dict, pezzi: list[dict], durata: float,
             parola_chiave: str) -> list[dict]:
    """Eventi con ancore -> eventi con tempi (formato tappa 1)."""
    def campi_testo(ev: EventoFx, *nomi: str) -> dict:
        return {nome: getattr(ev, nome) for nome in nomi if getattr(ev, nome) is not None}

    pill: list[dict] = []
    temporizzati: list[dict] = []
    stamp: list[dict] = []
    for ev in piano.eventi:
        if ev.type == "pill":
            pill.append({"type": "pill", **campi_testo(ev, "text", "red")})
            continue
        indici = [i for i in (ev.parola_inizio_idx, ev.parola_fine_idx) if i is not None]
        if ev.items:
            indici += [voce.parola_idx for voce in ev.items]
        if ev.parola_inizio_idx is None or any(i not in mappa for i in indici):
            print(f"AVVISO: evento {ev.type} scartato (ancora mancante o fuori clip: "
                  f"{indici})", file=sys.stderr)
            continue
        if ev.type == "stamp":
            _, start, _ = mappa[ev.parola_inizio_idx]
            stamp.append({"type": "stamp",
                          "t": fondamenta.arrotonda_decimale(
                              min(durata, max(0.0, tagli.tempo_agganciato(pezzi, start)[0])), 2)})
            continue
        t0 = secondi(mappa, ev.parola_inizio_idx, pezzi, fine=False)
        fine_idx = ev.parola_fine_idx if ev.parola_fine_idx is not None else ev.parola_inizio_idx
        t1 = min(durata, secondi(mappa, fine_idx, pezzi, fine=True))
        if ev.type == "claim":
            # nel canone la claim ha solo t0 (resta a schermo fino al payoff)
            temporizzati.append({"type": "claim", "t0": t0, **campi_testo(ev, "text", "red")})
        elif ev.type == "counter":
            if ev.to is None:
                print("AVVISO: counter senza 'to' scartato", file=sys.stderr)
                continue
            evento = {"type": "counter", "t0": t0, "t1": t1, "to": ev.to,
                      **campi_testo(ev, "label")}
            if ev.red is not None:
                evento["redLabel"] = ev.red  # nel formato tappa 1 il rosso del counter
            temporizzati.append(evento)
        elif ev.type == "list":
            voci = [{"t": fondamenta.arrotonda_decimale(min(durata, max(0.0,
                tagli.tempo_agganciato(pezzi, mappa[v.parola_idx][1])[0])), 2),
                "text": v.text} for v in ev.items or []]
            temporizzati.append({"type": "list", "t0": t0, "t1": t1,
                                 **campi_testo(ev, "header"), "items": voci})
        else:  # hook, card, cta
            temporizzati.append({"type": ev.type, "t0": t0, "t1": t1,
                                 **campi_testo(ev, "kicker", "text", "red")})

    temporizzati.sort(key=lambda e: e["t0"])
    stamp.sort(key=lambda e: e["t"])

    def fine_effettiva(ev: dict) -> float:
        """La fine a schermo che valida_canone attribuisce all'evento:
        la claim resta fino al primo stamp successivo (o alla fine clip)."""
        if ev["type"] == "claim":
            successivi = [s["t"] for s in stamp if s["t"] > ev["t0"]]
            return min(successivi) if successivi else durata
        return ev.get("t1", ev["t0"])

    # Cta finale con la parola chiave: geometria DETERMINISTICA
    # anti-sovrapposizione. Il canone (cta ultima, mai due eventi a schermo)
    # non deve mai bocciare per colpa del codice.
    cta_presenti = [e for e in temporizzati if e["type"] == "cta"]
    if cta_presenti:
        cta = max(cta_presenti, key=lambda e: e["t0"])
        if parola_chiave.lower() not in (cta.get("text") or "").lower():
            print(f"AVVISO: la cta finale non conteneva '{parola_chiave}': testo sostituito",
                  file=sys.stderr)
            cta["text"] = parola_chiave
    else:
        cta = {"type": "cta", "kicker": "SCRIVI NEI COMMENTI",
               "text": parola_chiave, "red": "→ guida gratis"}
        print(f"AVVISO: cta assente dal piano, imposta in coda con '{parola_chiave}'",
              file=sys.stderr)

    altri = [e for e in temporizzati if e is not cta]

    # Una claim senza stamp successivo resterebbe a schermo fino a fine clip
    # e si sovrapporrebbe SEMPRE alla cta: si scarta prima che il canone bocci.
    tenuti = []
    for ev in altri:
        if ev["type"] == "claim" and not any(s["t"] > ev["t0"] for s in stamp):
            print(f"AVVISO: claim a t0={ev['t0']} senza stamp successivo scartata "
                  "(si sovrapporrebbe alla cta finale)", file=sys.stderr)
            continue
        tenuti.append(ev)

    # RIPARAZIONE GEOMETRICA deterministica: il canone "un elemento alla
    # volta" si garantisce QUI, in codice — l'LLM sceglie contenuti e ancore,
    # la geometria non deve mai bocciare il piano (lezione del primo giro:
    # ancore su parole contigue producono sovrapposizioni di ~0.3s).
    tenuti.sort(key=lambda e: e["t0"])
    # 1) una claim con ALTRI eventi dentro il suo arco (t0 -> stamp) copre
    #    tutto: si retrocede a card chiusa prima dell'evento successivo.
    for i, ev in enumerate(tenuti):
        if ev["type"] != "claim":
            continue
        fine_claim = fine_effettiva(ev)
        successivi = [e for e in tenuti[i + 1:] if e["t0"] < fine_claim]
        if successivi:
            ev["type"] = "card"
            ev["t1"] = fondamenta.arrotonda_decimale(successivi[0]["t0"] - 0.05, 2)
            print(f"AVVISO: claim a t0={ev['t0']} copriva altri eventi: "
                  f"retrocessa a card fino a t1={ev['t1']}", file=sys.stderr)
    # 2) clamp delle sovrapposizioni residue fra eventi consecutivi; chi
    #    resta schiacciato sotto 0.8s si scarta con avviso.
    riparati: list[dict] = []
    for ev in tenuti:
        while riparati:
            prec = riparati[-1]
            fine_prec = prec["t1"] if "t1" in prec else fine_effettiva(prec)
            if fine_prec <= ev["t0"] - 0.05:
                break
            nuovo_t1 = fondamenta.arrotonda_decimale(ev["t0"] - 0.05, 2)
            if "t1" in prec and nuovo_t1 - prec["t0"] >= 0.8:
                prec["t1"] = nuovo_t1
                break
            print(f"AVVISO: {prec['type']} a t0={prec['t0']} schiacciato dal "
                  f"successivo: scartato", file=sys.stderr)
            riparati.pop()
        riparati.append(ev)
    tenuti = riparati

    # La cta parte negli ultimi ~4 secondi, comunque dopo l'ultimo evento;
    # se la coda della clip e' gia' occupata, si fa spazio in codice.
    ultimo_fine = max((fine_effettiva(e) for e in tenuti), default=0.0)
    t0_cta = max(0.0, durata - 4.0, ultimo_fine + 0.1)
    if t0_cta > durata - 0.5:
        t0_cta = max(0.0, durata - 0.5)
    t0_cta = fondamenta.arrotonda_decimale(t0_cta, 2)

    finali = []
    for ev in tenuti:
        if ev["t0"] >= t0_cta:
            print(f"AVVISO: evento {ev['type']} a t0={ev['t0']} scartato per "
                  "far spazio alla cta finale", file=sys.stderr)
            continue
        if ev["type"] == "claim" and fine_effettiva(ev) > t0_cta - 0.05:
            print(f"AVVISO: claim a t0={ev['t0']} scartata (lo stamp che la chiude "
                  "arriva dopo l'inizio della cta finale)", file=sys.stderr)
            continue
        if ev.get("t1") is not None and ev["t1"] > t0_cta - 0.05:
            ev["t1"] = fondamenta.arrotonda_decimale(max(ev["t0"], t0_cta - 0.05), 2)
        finali.append(ev)

    cta["t0"] = t0_cta
    cta["t1"] = fondamenta.arrotonda_decimale(max(t0_cta + 0.1, durata - 0.1), 2)
    finali.append(cta)
    finali.sort(key=lambda e: e["t0"])

    return pill + finali + stamp


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Piano FX di uno short via LLM, tempi calcolati in codice, canone validato.")
    ap.add_argument("transcript", help="build/transcript.json (parole con tempi)")
    ap.add_argument("highlights", help="build/highlights.json (clip selezionate)")
    ap.add_argument("--parola-chiave", required=True, help="parola della cta finale")
    ap.add_argument("--guida", required=True, help="percorso di HOOK-GUIDE.md")
    ap.add_argument("--uscita", required=True, help="dove scrivere fx_plans.json")
    ap.add_argument("--nome-short", required=True, help="nome del file mp4 in out/")
    ap.add_argument("--indice-clip", type=int, default=0,
                    help="quale highlight usare (default: il primo)")
    ap.add_argument("--metadata",
                    help="out/<stem>.json di render.py: start/end REALI della clip "
                         "(col padding); senza, i tempi si derivano dalle parole")
    ap.add_argument("--nota", help="correzione chiesta a mano quando si fa rifare il passo")
    args = ap.parse_args()

    modello = os.environ.get("LLM_MODELLO_GIUDIZI", MODELLO_DEFAULT)
    trascritto = json.loads(Path(args.transcript).read_text(encoding="utf-8"))
    highlights = json.loads(Path(args.highlights).read_text(encoding="utf-8"))["highlights"]
    if not (0 <= args.indice_clip < len(highlights)):
        raise llm.EsitoPermanente(
            f"componi_fx: indice clip {args.indice_clip} fuori range (0-{len(highlights) - 1})")
    clip = highlights[args.indice_clip]

    if args.metadata:
        # geometria REALE dell'mp4: render.py applica PAD_START_S/PAD_END_S
        # (config.py della pipeline) e scrive start/end/duration/pezzi nel
        # metadata. 'pezzi' sono i tratti di girato rimasti dopo i tagli: su
        # una clip mai tagliata e' uno solo, [start, end], e tutto il resto si
        # comporta come prima.
        meta = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
        inizio_clip = float(meta["start"])
        elenco = meta.get("pezzi") or [{"inizio": inizio_clip, "fine": float(meta["end"])}]
        pezzi = tagli.pezzi_da_buchi(
            min(float(p["inizio"]) for p in elenco),
            max(float(p["fine"]) for p in elenco),
            [{"inizio": float(a["fine"]), "fine": float(b["inizio"]), "motivo": "silenzio"}
             for a, b in zip(elenco, elenco[1:])])
        durata = fondamenta.arrotonda_decimale(tagli.durata_pezzi(pezzi), 2)
    else:
        parole_tutte = parole_della_clip(
            trascritto["segments"], clip["seg_start_idx"], clip["seg_end_idx"])
        if not parole_tutte:
            raise llm.EsitoPermanente("componi_fx: la clip non contiene parole")
        inizio_clip = min(start for _, start, _ in parole_tutte.values())
        fine_clip = max(end for _, _, end in parole_tutte.values())
        durata = fondamenta.arrotonda_decimale(fine_clip - inizio_clip + MARGINE_T1, 2)
        pezzi = tagli.pezzi_da_buchi(inizio_clip, fine_clip + MARGINE_T1, [])
    mappa = parole_della_clip(trascritto["segments"], clip["seg_start_idx"],
                              clip["seg_end_idx"], pezzi)
    if not mappa:
        raise llm.EsitoPermanente("componi_fx: la clip non contiene parole")

    righe = " ".join(f"{i}:{mappa[i][0]}" for i in sorted(mappa))
    # La correzione apre il messaggio, prima dei dati della clip: il system la
    # riconosce dai delimitatori e sa che vale solo lì (llm.REGOLE_CORREZIONE).
    # 'title' e 'hook_sentence' arrivano da scegli_highlights QUANDO a scegliere
    # e' stato un modello. Quando non c'e' niente da scegliere — un girato gia'
    # corto, o un trascritto con un segmento solo — la clip la scrive il worker
    # su tutto il girato, senza nessun giudizio: il titolo e' il nome del file e
    # l'hook non esiste. Si legge quindi con .get e la riga si OMETTE se vuota,
    # invece di mandare al modello un «HOOK:» seguito dal nulla, che e' peggio
    # che non dirglielo: sembra un hook che non si e' riusciti a estrarre.
    intestazione = f"PAROLA CHIAVE DELLA CTA FINALE: {args.parola_chiave}\n"
    titolo = str(clip.get("title") or "").strip()
    if titolo:
        intestazione += f"TITOLO CLIP: {titolo}\n"
    gancio = str(clip.get("hook_sentence") or "").strip()
    if gancio:
        intestazione += f"HOOK: {gancio}\n"
    contenuto = (llm.blocco_nota(args.nota) + intestazione
                 + f"\nPAROLE DELLA CLIP (indice:parola):\n{righe}")
    system = SYSTEM_BASE + Path(args.guida).read_text(encoding="utf-8")

    piano, usage, costo = llm.giudica("componi_fx", modello, system, contenuto, PianoFx)

    eventi = converti(piano, mappa, pezzi, durata, args.parola_chiave.upper())
    piani = [{"src": f"out/{args.nome_short}", "events": eventi}]
    Path(args.uscita).write_text(json.dumps(piani, ensure_ascii=False, indent=1),
                                 encoding="utf-8")

    # Il canone si valida sempre, sul file appena scritto: se non passa, si
    # fallisce. Il validatore e' deterministico: la chiave API non gli serve
    # e non deve vederla.
    ambiente = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    esito = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "valida_canone.py"),
         "--fx", args.uscita, "--durata", f"{durata:.2f}",
         "--parola-chiave", args.parola_chiave],
        capture_output=True, text=True, env=ambiente)
    if esito.returncode != 0:
        print("valida_canone bocciato sul piano FX:", file=sys.stderr)
        print(esito.stderr, file=sys.stderr)
        # la chiamata LLM e' stata pagata: il JSON con le chiamate si stampa
        # COMUNQUE prima di uscire 1, o il costo sparirebbe dal DB (decisione 5)
        llm.stampa_esito(
            {"valida_canone": "bocciato", "violazioni": esito.stderr[-2000:]},
            [llm.voce_chiamata("componi_fx", modello, usage, costo)])
        return 1

    llm.stampa_esito(
        {"uscita": args.uscita, "src": piani[0]["src"], "eventi": len(eventi),
         "durata_clip": durata, "con_nota": llm.prepara_nota(args.nota) is not None,
         "valida_canone": "ok"},
        [llm.voce_chiamata("componi_fx", modello, usage, costo)])
    return 0


if __name__ == "__main__":
    llm.esegui_cli(main)
