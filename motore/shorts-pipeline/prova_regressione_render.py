"""Prova che le correzioni per clip non abbiano cambiato il montaggio di prima.

E' la prova che vale piu' di tutte le altre: su un girato sintetico, gli short
prodotti da render.py SENZA correzioni devono essere identici BYTE PER BYTE a
quelli prodotti dal render.py di HEAD (quello prima delle correzioni, ripreso
con `git show`). Poi verifica che una correzione tocchi solo la clip corretta,
che --solo-clip rifaccia una clip sola, e che gli errori si dicano invece di
passare in silenzio.

Uso:
    py prova_regressione_render.py [CARTELLA_DI_LAVORO]

Serve: ffmpeg/ffprobe nel PATH, opencv (cv2) importabile, git, e il repo con
almeno un commit che contenga motore/shorts-pipeline/render.py.
Dura qualche minuto: rende davvero quattro-cinque short 1080x1920.

Esce 0 se tutto torna, 1 al primo scarto (dicendo quale).
"""
from __future__ import annotations

import _bootstrap  # shared local paths, tools and cache

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import correzioni

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PIPELINE = Path(__file__).resolve().parent          # motore/shorts-pipeline
MOTORE = PIPELINE.parent                            # motore/
REPO = MOTORE.parent                                # radice del repo
RENDER_NEL_REPO = "motore/shorts-pipeline/render.py"
PY = sys.executable

LAVORO = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp(
    prefix="prova-render-"))
LAVORO.mkdir(parents=True, exist_ok=True)
print(f"cartella di lavoro: {LAVORO}")

GUASTI: list[str] = []


def controlla(nome: str, condizione: bool, dettaglio: str = "") -> None:
    if condizione:
        print(f"  ok   {nome}")
    else:
        GUASTI.append(nome)
        print(f"  NO   {nome}  {dettaglio}")


def sh(cmd, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", **kw)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def prepara(nome: str, render_sorgente: bytes | None) -> Path:
    """Copia della pipeline col brand kit accanto: la stessa forma che il
    worker prepara per ogni job (preparaSpazioLavoro in worker/src/motore.js)."""
    radice = LAVORO / nome
    if radice.exists():
        shutil.rmtree(radice)
    copia = radice / "shorts-pipeline"
    shutil.copytree(PIPELINE, copia,
                    ignore=shutil.ignore_patterns("build", "out", "__pycache__"))
    shutil.copy(MOTORE / "brand-kit.json", radice / "brand-kit.json")
    shutil.copy(MOTORE / "runtime.py", radice / "runtime.py")
    if render_sorgente is not None:
        (copia / "render.py").write_bytes(render_sorgente)
    (copia / "build").mkdir(exist_ok=True)
    (copia / "out").mkdir(exist_ok=True)
    return copia


# --------------------------------------------------- girato e trascritto finti

girato = LAVORO / "girato.mp4"
if not girato.exists():
    print("genero il girato sintetico (60 s, 1920x1080)...")
    r = sh(["ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=60",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=60",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(girato)])
    if r.returncode != 0:
        sys.exit(f"ffmpeg non ha generato il girato:\n{r.stderr[-1500:]}")

segmenti = []
for i in range(30):
    inizio = i * 2.0
    segmenti.append({
        "start": inizio, "end": inizio + 2.0,
        "words": [{"w": f"parola{i}{j}", "start": round(inizio + j * 0.5, 3),
                   "end": round(inizio + j * 0.5 + 0.45, 3)} for j in range(4)],
    })
TRASCRITTO = {"segments": segmenti, "duration": 60.0}
HIGHLIGHTS = {"highlights": [
    {"title": "Primo pezzo di prova", "seg_start_idx": 0, "seg_end_idx": 6,
     "score": 90, "hook_sentence": "il primo hook", "virality_reason": "prova"},
    {"title": "Secondo pezzo di prova", "seg_start_idx": 10, "seg_end_idx": 16,
     "score": 80, "hook_sentence": "il secondo hook", "virality_reason": "prova"},
]}


def semina(copia: Path) -> None:
    (copia / "build" / "girato.transcript.json").write_text(
        json.dumps(TRASCRITTO), encoding="utf-8")
    (copia / "build" / "highlights.json").write_text(
        json.dumps(HIGHLIGHTS), encoding="utf-8")


def gira(copia: Path, extra: list[str]) -> subprocess.CompletedProcess:
    return sh([PY, "render.py", str(girato),
               "--highlights", str(copia / "build" / "highlights.json"), *extra],
              cwd=str(copia))


# I campi che la tappa dei TAGLI ha aggiunto al metadata e che quindi non
# esistono nel render.py di HEAD. Il confronto byte per byte del .json li
# TOGLIE, ma non li ignora: subito dopo si verifica che dicano esattamente
# quello che devono dire (vedi 'controlla_pezzi'). Il video, invece, resta
# confrontato byte per byte senza nessuna indulgenza: e' quello il patto.
# I campi che il render di HEAD non scriveva. Si dichiarano qui, uno per uno,
# perche' la prova resti stretta su tutto il resto: un elenco che cresce e' un
# elenco di decisioni prese, mentre un confronto allentato e' una prova che
# non prova piu' niente.
#
#   pezzi                 i tratti di girato che restano dentro la clip
#   durata_pianificata_s  quanto era stato CHIESTO al montaggio: resta scritto
#                         accanto a 'duration', che adesso e' misurata sul
#                         file, cosi' chi indaga uno scarto ha tutti e due i
#                         numeri invece di uno solo
#   durata_misurata       se 'duration' viene davvero da ffprobe oppure e' il
#                         ripiego sul pianificato (file non leggibile)
CAMPI_NUOVI_METADATA = ("pezzi", "durata_pianificata_s", "durata_misurata")


def impronta_metadata(percorso: Path) -> str:
    """L'impronta di un out/<stem>.json SENZA i campi nuovi.

    Serve perche' il render di HEAD non li scriveva: confrontare i byte nudi
    farebbe fallire la prova per un campo dichiarativo in piu', e la prova
    verrebbe allentata a mano dal primo che la vede rossa. Cosi' invece resta
    stretta su tutto il resto, e i campi nuovi si controllano a parte.
    """
    documento = json.loads(percorso.read_text(encoding="utf-8"))
    for campo in CAMPI_NUOVI_METADATA:
        documento.pop(campo, None)
    return hashlib.sha256(
        json.dumps(documento, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def impronte(copia: Path) -> dict[str, str]:
    return {
        p.name: (impronta_metadata(p) if p.suffix == ".json" else sha(p))
        for p in sorted((copia / "out").iterdir())
    }


def scarto_metadata(prima: Path, dopo: Path, nome: str) -> str:
    """I campi del metadata che sono cambiati, scritti per esteso.

    Un'impronta diversa dice CHE qualcosa e' cambiato e non dice COSA: senza
    questo, chi vede la prova rossa su un .json ha davanti due sha256 e la
    tentazione di allentare il confronto. Con questo ha davanti il campo, il
    valore di prima e quello di adesso, e puo' decidere se era voluto. I byte
    del video restano confrontati senza nessuna indulgenza: quello e' il patto,
    e questa funzione non lo tocca.
    """
    a = json.loads((prima / "out" / nome).read_text(encoding="utf-8"))
    b = json.loads((dopo / "out" / nome).read_text(encoding="utf-8"))
    for campo in CAMPI_NUOVI_METADATA:
        a.pop(campo, None)
        b.pop(campo, None)
    righe = []
    for chiave in sorted(set(a) | set(b)):
        if a.get(chiave) != b.get(chiave):
            righe.append(f"{chiave}: {a.get(chiave)!r} -> {b.get(chiave)!r}")
    return "; ".join(righe) or "nessun campo diverso (differiscono solo i byte)"


def controlla_pezzi(copia: Path, nome_json: str) -> None:
    """Senza tagli i pezzi devono essere UNO e coincidere col taglio."""
    meta = json.loads((copia / "out" / nome_json).read_text(encoding="utf-8"))
    pezzi = meta.get("pezzi")
    ok = (isinstance(pezzi, list) and len(pezzi) == 1
          and abs(pezzi[0]["inizio"] - meta["start"]) < 1e-6
          and abs(pezzi[0]["fine"] - meta["end"]) < 1e-6)
    controlla(f"{nome_json}: un pezzo solo, uguale al taglio", ok, str(pezzi))
    controlla(f"{nome_json}: nessun blocco 'tagli' senza tagli", "tagli" not in meta)


# ------------------------------------------------------- A) il render di HEAD

print("\nA) render.py di HEAD, quello di prima delle correzioni")
vecchio = subprocess.run(["git", "show", f"HEAD:{RENDER_NEL_REPO}"],
                         capture_output=True, cwd=str(REPO)).stdout
if not vecchio:
    sys.exit(f"git show non ha restituito HEAD:{RENDER_NEL_REPO}")
pipe_a = prepara("prima", vecchio)
semina(pipe_a)
r = gira(pipe_a, [])
if r.returncode != 0:
    sys.exit(f"render.py di HEAD fallito:\n{r.stderr[-1500:]}")
imp_a = impronte(pipe_a)
print("   prodotti:", ", ".join(imp_a))

# ------------------------------------------------- B) il render nuovo, nudo

print("\nB) render.py di adesso, senza --correzioni: deve dare gli stessi byte")
pipe_b = prepara("adesso", None)
semina(pipe_b)
r = gira(pipe_b, [])
if r.returncode != 0:
    sys.exit(f"render.py nuovo fallito:\n{r.stderr[-1500:]}")
imp_b = impronte(pipe_b)
controlla("stessi file", sorted(imp_a) == sorted(imp_b), f"{sorted(imp_a)} vs {sorted(imp_b)}")
for nome in imp_a:
    uguale = imp_a.get(nome) == imp_b.get(nome)
    dettaglio = (f"{imp_a.get(nome)} vs {imp_b.get(nome)}" if not nome.endswith(".json")
                 else scarto_metadata(pipe_a, pipe_b, nome))
    controlla(f"{nome} identico byte per byte", uguale, dettaglio)
# E i campi nuovi del metadata dicono quello che devono: senza tagli, un pezzo
# solo che coincide col taglio. E' la contropartita del confronto qui sopra,
# che quei campi li toglie.
for nome in (n for n in imp_b if n.endswith(".json")):
    controlla_pezzi(pipe_b, nome)

# ------------------------------------- C) il render nuovo con correzioni vuote

print("\nC) con un file di correzioni SENZA voci: ancora gli stessi byte")
pipe_c = prepara("vuote", None)
semina(pipe_c)
corr_vuoto = pipe_c / "build" / "correzioni.json"
# La versione si prende dal modulo, mai battuta a mano: e' il numero che sale
# insieme al SIGNIFICATO dei tre campi, e una prova che se lo scrive per conto
# suo resta indietro proprio il giorno in cui la semantica cambia.
corr_vuoto.write_text(
    json.dumps({"versione": correzioni.VERSIONE_ATTESA, "clip": {}}), encoding="utf-8")
r = gira(pipe_c, ["--correzioni", str(corr_vuoto)])
if r.returncode != 0:
    sys.exit(f"render.py con correzioni vuote fallito:\n{r.stderr[-1500:]}")
imp_c = impronte(pipe_c)
for nome in imp_a:
    uguale = imp_a.get(nome) == imp_c.get(nome)
    dettaglio = "" if uguale or not nome.endswith(".json") else scarto_metadata(
        pipe_a, pipe_c, nome)
    controlla(f"{nome} ancora identico", uguale, dettaglio)

# ------------------------------------------- D) una correzione su UNA clip sola

bersaglio = Path(sorted(n for n in imp_a if n.endswith(".mp4"))[1]).stem
print(f"\nD) correzione su '{bersaglio}' con --solo-clip")
corr = pipe_c / "build" / "correzioni-vere.json"
corr.write_text(json.dumps({"versione": correzioni.VERSIONE_ATTESA, "clip": {
    # apposta col nome del -FX: e' quello che una persona ha davanti
    f"{bersaglio}-FX.mp4": {"ancora_x": 0.12, "pad_inizio_s": -1.5,
                            "pad_fine_s": 0.8, "aggiornata_il": "2026-08-17T10:00:00Z"}
}}), encoding="utf-8")
r = gira(pipe_c, ["--correzioni", str(corr), "--solo-clip", f"{bersaglio}-FX.mp4"])
if r.returncode != 0:
    sys.exit(f"render.py --solo-clip fallito:\n{r.stderr[-1500:]}")
imp_d = impronte(pipe_c)
for nome in (n for n in imp_a if not n.startswith(bersaglio)):
    controlla(f"{nome} NON toccato", imp_c.get(nome) == imp_d.get(nome))
controlla(f"{bersaglio}.mp4 cambiato",
          imp_c.get(f"{bersaglio}.mp4") != imp_d.get(f"{bersaglio}.mp4"))

meta = json.loads((pipe_c / "out" / f"{bersaglio}.json").read_text(encoding="utf-8"))
prima = json.loads((pipe_a / "out" / f"{bersaglio}.json").read_text(encoding="utf-8"))
controlla("il metadata porta il blocco correzioni", "correzioni" in meta)
controlla("attacco anticipato di 1,5 s", abs(meta["start"] - (prima["start"] - 1.5)) < 1e-6,
          f"{prima['start']} -> {meta['start']}")
controlla("coda allungata di 0,8 s", abs(meta["end"] - (prima["end"] + 0.8)) < 1e-6,
          f"{prima['end']} -> {meta['end']}")
controlla("il ritaglio si e' spostato a destra", meta["crop_x"] > prima["crop_x"],
          f"{prima['crop_x']} -> {meta['crop_x']}")
controlla("il taglio di prima resta scritto (serve a componi_fx)",
          meta["correzioni"]["start_base"] == prima["start"])
controlla("lo spostamento in pixel torna col conto",
          meta["correzioni"]["spostamento_px"]
          == meta["crop_x"] - meta["correzioni"]["crop_x_senza_correzione"])

# ---------------------------------------------- E) gli errori si devono dire

print("\nE) errori detti, non taciuti")
r = gira(pipe_c, ["--solo-clip", "short_99_non-esiste"])
controlla("clip inesistente esce != 0", r.returncode != 0, f"exit {r.returncode}")
controlla("...e dice quali clip ci sono", "short_" in r.stderr, r.stderr[-200:])

rotto = pipe_c / "build" / "correzioni-rotte.json"
# la versione c'e' apposta: senza, il file inciamperebbe sul controllo della
# versione e questa prova non arriverebbe mai a provare il campo inventato
rotto.write_text(
    json.dumps({"versione": correzioni.VERSIONE_ATTESA,
                "clip": {bersaglio: {"ancoraX": 0.1}}}),
    encoding="utf-8")
r = gira(pipe_c, ["--correzioni", str(rotto)])
controlla("campo inventato esce != 0", r.returncode != 0)
controlla("...e dice quali sono ammessi", "ancora_x" in r.stderr, r.stderr[-200:])

orfano = pipe_c / "build" / "correzioni-orfane.json"
orfano.write_text(
    json.dumps({"versione": correzioni.VERSIONE_ATTESA,
                "clip": {"short_77_mai-vista": {"ancora_x": 0.1}}}),
    encoding="utf-8")
r = gira(pipe_c, ["--correzioni", str(orfano), "--solo-clip", bersaglio])
controlla("correzione per una clip che non c'e': avvisa senza far fallire",
          r.returncode == 0 and "short_77_mai-vista" in r.stderr, r.stderr[-200:])

print(f"\n{'TUTTO OK' if not GUASTI else 'FALLITE: ' + ', '.join(GUASTI)}")
sys.exit(1 if GUASTI else 0)
