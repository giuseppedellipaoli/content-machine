"""Prove del canone su una regia sintetica, senza produzioni precedenti."""
import copy
import json
import tempfile
from pathlib import Path
import valida_canone

sample=Path(__file__).resolve().parents[1]/"video-gfx/src/data/regia.json"
plan=json.loads(sample.read_text(encoding="utf-8"))
with tempfile.TemporaryDirectory() as tmp:
 target=Path(tmp)/"regia.json"
 target.write_text(json.dumps(plan),encoding="utf-8")
 problems=valida_canone.valida_regia(str(target),plan["durSec"])
 assert not problems,problems
 bad=copy.deepcopy(plan)
 bad["events"][0]["k"]={"fuori":plan["events"][0]["t1"]+10}
 target.write_text(json.dumps(bad),encoding="utf-8")
 problems=valida_canone.valida_regia(str(target),plan["durSec"])
 assert any("fuori" in message for message in problems),problems
 bad=copy.deepcopy(plan)
 bad["events"][0]["type"]="tipo_inesistente"
 target.write_text(json.dumps(bad),encoding="utf-8")
 assert valida_canone.valida_regia(str(target),plan["durSec"])
print("Canone: tre casi sintetici passati (valido, tempi fuori, tipo ignoto).")
