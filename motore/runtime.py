"""Ambiente locale condiviso; nessun account, endpoint o servizio dell'autore."""
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def ensure_env():
    env_file=ROOT/'.env'
    if env_file.exists():
        for raw in env_file.read_text(encoding='utf-8-sig').splitlines():
            line=raw.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            key,value=line.split('=',1)
            if key.strip().replace('_','').isalnum():
                os.environ.setdefault(key.strip(),value.strip().strip('\"').strip("'"))
    cache=Path(os.getenv('CONTENT_MACHINE_CACHE') or ROOT/'work/cache').expanduser().resolve()
    temp=cache/'tmp'
    temp.mkdir(parents=True,exist_ok=True)
    for key,value in {'TEMP':temp,'TMP':temp,'TMPDIR':temp,'HF_HOME':cache/'huggingface',
                      'HF_HUB_CACHE':cache/'huggingface/hub','XDG_CACHE_HOME':cache,
                      'TORCH_HOME':cache/'torch','PYTHONPYCACHEPREFIX':cache/'pycache'}.items():
        os.environ[key]=str(value)
    os.environ['CONTENT_MACHINE_CACHE']=str(cache)
    tempfile.tempdir=str(temp)
    for variable in ('FFMPEG_PATH','FFPROBE_PATH','NODE_PATH'):
        value=os.getenv(variable)
        if value:
            folder=str(Path(value).expanduser().resolve().parent)
            os.environ['PATH']=folder+os.pathsep+os.environ.get('PATH','')
    return cache

def tool(name):
    variables={'ffmpeg':'FFMPEG_PATH','ffprobe':'FFPROBE_PATH','node':'NODE_PATH'}
    value=os.getenv(variables.get(name,''))
    result=shutil.which(value or name)
    if not result:
        raise RuntimeError(f'{name} non trovato: configurarlo nel PATH o nel proprio .env.')
    return result

ensure_env()
