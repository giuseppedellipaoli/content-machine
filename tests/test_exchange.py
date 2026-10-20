"""Contratto offline: schema e firma evitano risposte LLM riciclate per errore."""
import importlib.util
import json
import sys
from pathlib import Path
import pytest
from pydantic import BaseModel

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('exchange',ROOT/'motore/orchestratore/llm.py')
exchange=importlib.util.module_from_spec(spec)
spec.loader.exec_module(exchange)

class Answer(BaseModel):
    title:str

def test_request_response_and_stale_input(tmp_path,monkeypatch):
    monkeypatch.setenv('LLM_EXCHANGE_DIR',str(tmp_path))
    with pytest.raises(exchange.InAttesaLLM):
        exchange.giudica('test','any-model','Regole','Trascritto A',Answer)
    request=json.loads((tmp_path/'test.request.json').read_text(encoding='utf-8'))
    assert request['schema']['required']==['title']
    (tmp_path/'test.response.json').write_text(json.dumps({'request_sha256':request['request_sha256'],'output':{'title':'Scelta editoriale'}}),encoding='utf-8')
    result,usage,cost=exchange.giudica('test','another-model','Regole','Trascritto A',Answer)
    assert result.title=='Scelta editoriale'
    with pytest.raises(exchange.InAttesaLLM):
        exchange.giudica('test','another-model','Regole','Trascritto B',Answer)

def test_invalid_schema_is_rejected(tmp_path,monkeypatch):
    monkeypatch.setenv('LLM_EXCHANGE_DIR',str(tmp_path))
    with pytest.raises(exchange.InAttesaLLM):
        exchange.giudica('test','model','Regole','Input',Answer)
    request=json.loads((tmp_path/'test.request.json').read_text(encoding='utf-8'))
    (tmp_path/'test.response.json').write_text(json.dumps({'request_sha256':request['request_sha256'],'output':{}}),encoding='utf-8')
    with pytest.raises(exchange.EsitoPermanente):
        exchange.giudica('test','model','Regole','Input',Answer)
