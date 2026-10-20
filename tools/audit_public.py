"""Controllo locale dei file Git e dei blob storici. Stampa posizioni, mai valori."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

RULES={
    'private-key':rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    'github-token':rb'\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})\b',
    'api-secret':rb'\bsk-(?:ant-[A-Za-z0-9_-]{20,}|proj-[A-Za-z0-9_-]{20,}|[A-Za-z0-9]{32,})\b',
    'aws-key':rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'credential-url':rb'https?://[^\s/@:]{1,100}:[^\s/@]{3,100}@',
    'token-assignment':rb'(?im)^\s*(?:export\s+)?(?:[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY))\s*=\s*[\"\']?[A-Za-z0-9_+/.-]{16,}',
}
FORBIDDEN_EXT={'.mp4','.mov','.mkv','.webm','.wav','.mp3','.m4a','.onnx','.p12','.pfx','.pem','.key','.pyc'}

def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args])

def findings(name,data):
    result=[]
    for rule,pattern in RULES.items():
        for match in re.finditer(pattern,data):
            result.append({'path':name,'rule':rule,'line':data[:match.start()].count(b'\n')+1})
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument('--history',action='store_true')
    args=ap.parse_args()
    root=Path(args.root).resolve()
    files=git(root,'ls-files','-z').decode().split('\0')
    problems=[]
    for name in filter(None,files):
        path=Path(name)
        if path.suffix.lower() in FORBIDDEN_EXT or path.name=='.env' or any(p in {'node_modules','.venv','work','__pycache__'} for p in path.parts):
            problems.append({'path':name,'rule':'generated-or-private-file'})
        problems.extend(findings(name,(root/name).read_bytes()))
    blobs=0
    if args.history:
        listing=git(root,'rev-list','--objects','--all').decode().splitlines()
        for line in listing:
            oid,_,name=line.partition(' ')
            if git(root,'cat-file','-t',oid).strip()!=b'blob':continue
            blobs+=1
            problems.extend(findings('history:'+name,git(root,'cat-file','blob',oid)))
    print(json.dumps({'tracked_files':len(list(filter(None,files))),'history_blobs':blobs,'findings':problems},indent=2))
    return 1 if problems else 0

if __name__=='__main__':raise SystemExit(main())
