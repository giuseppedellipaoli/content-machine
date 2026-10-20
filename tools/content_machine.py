"""CLI per gli agenti: prepara workspace isolati e invoca il motore originale."""
from __future__ import annotations
import argparse
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'motore'))
import runtime

def run(args,cwd=None):
    subprocess.run([str(x) for x in args],cwd=cwd,check=True)

def probe(video):
    data=json.loads(subprocess.check_output([runtime.tool('ffprobe'),'-v','error','-show_format','-show_streams','-of','json',str(video)],encoding='utf-8'))
    stream=next(s for s in data['streams'] if s['codec_type']=='video')
    return {'duration':float(data['format']['duration']),'width':stream['width'],'height':stream['height'],
            'audio':any(s['codec_type']=='audio' for s in data['streams'])}

def job_path(value):
    folder=Path(value).expanduser().resolve()
    if not (folder/'job.json').is_file():raise ValueError('Cartella priva di job.json: usare prima prepare.')
    return folder

def read_job(folder):return json.loads((folder/'job.json').read_text(encoding='utf-8'))

def save_job(folder,data):
    (folder/'job.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

def import_srt(path,source):
    text=Path(path).read_text(encoding='utf-8-sig')
    def at(s):
        h,m,second,ms=re.split('[:,.]',s)
        return int(h)*3600+int(m)*60+int(second)+int(ms)/1000
    pattern=r'(\d{2,}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2,}:\d{2}:\d{2}[,.]\d{3})[^\n]*\n(.*?)(?=\n\s*\n|\Z)'
    segments=[]
    for match in re.finditer(pattern,text.strip(),re.S):
        start,end=at(match[1]),at(match[2])
        content=re.sub(r'<[^>]+>','',' '.join(match[3].split()))
        if not content or end<=start:continue
        # SRT non contiene tempi di parola: flag esplicito e tempi stimati.
        # L'agente deve evitare tagli interni alla battuta con questo input.
        tokens=content.split()
        words=[{'w':word,'start':round(start+(end-start)*i/len(tokens),3),
                'end':round(start+(end-start)*(i+1)/len(tokens),3)} for i,word in enumerate(tokens)]
        segments.append({'id':len(segments),'start':start,'end':end,'text':content,'words':words})
    if not segments:raise ValueError('SRT senza battute valide.')
    duration=probe(source)['duration']
    if any(s['start']<0 or s['end']>duration+.1 for s in segments):raise ValueError('SRT fuori durata del video.')
    return {'source':str(source),'mtime':source.stat().st_mtime,'language':'it','duration':duration,
            'word_timestamps':'estimated_from_srt','segments':segments}

def link_dependencies(target):
    installed=ROOT/'motore/video-gfx/node_modules'
    if not installed.is_dir():return
    link=target/'video-gfx/node_modules'
    if os.name=='nt':
        # Crea una junction verso le dipendenze dello STESSO clone, non servizi esterni.
        script="New-Item -ItemType Junction -Path $args[0] -Target $args[1] | Out-Null"
        # -Command arg binding non è uniforme fra PowerShell5/7: usare stringhe letterali escaper.
        quote=lambda s:"'"+str(s).replace("'","''")+"'"
        command=f'New-Item -ItemType Junction -Path {quote(link)} -Target {quote(installed)} | Out-Null'
        run(['powershell','-NoProfile','-Command',command])
    else:link.symlink_to(installed,target_is_directory=True)

def prepare(args):
    source=Path(args.video).expanduser().resolve()
    if not source.is_file():raise ValueError('Video sorgente assente.')
    folder=Path(args.job).expanduser().resolve()
    if folder.exists():raise ValueError('La cartella del lavoro esiste già: scegliere un nome nuovo.')
    # Nessuna copia .git/.env/cache. Gli originali cliente restano fuori dal repository.
    folder.mkdir(parents=True)
    shutil.copytree(ROOT/'motore',folder/'motore',ignore=shutil.ignore_patterns(
        'node_modules','build','out','exports','__pycache__','.cache','.env','*.pyc','fonts','sfx',
        '*.mp4','*.mov','*.mkv','*.webm','*.wav','*.mp3','*.m4a','*.onnx'))
    link_dependencies(folder/'motore')
    public=folder/'motore/video-gfx/public'
    public.mkdir(parents=True,exist_ok=True)
    base=public/'base-master30.mp4'
    info=probe(source)
    command=[runtime.tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-i',str(source)]
    if not info['audio']:command+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
    command+=['-map','0:v:0','-map','0:a:0' if info['audio'] else '1:a:0',
              '-vf','scale=1920:1080:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30',
              '-t',str(info['duration']),'-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',
              '-c:a','aac','-ar','48000','-ac','2','-movflags','+faststart',str(base)]
    run(command)
    build=folder/'motore/shorts-pipeline/build'
    build.mkdir(parents=True,exist_ok=True)
    if args.srt:
        transcript=import_srt(args.srt,base)
    elif args.transcript:
        transcript=json.loads(Path(args.transcript).read_text(encoding='utf-8'))
        if not isinstance(transcript.get('segments'),list):raise ValueError('Transcript senza segments[].')
        transcript.update(source=str(base),mtime=base.stat().st_mtime,duration=probe(base)['duration'])
    else:
        script=folder/'motore/shorts-pipeline/transcribe.py'
        run([sys.executable,script,base],cwd=script.parent)
        transcript=json.loads((build/'base-master30.transcript.json').read_text(encoding='utf-8'))
    (build/'base-master30.transcript.json').write_text(json.dumps(transcript,ensure_ascii=False,indent=2),encoding='utf-8')
    (build/'base-master30.for_llm.txt').write_text('\n'.join(f'[{i}] [{s["start"]:.3f}s-{s["end"]:.3f}s] {s["text"]}' for i,s in enumerate(transcript['segments'])),encoding='utf-8')
    regia={'fps':30,'durSec':probe(base)['duration'],'faceOrigin':'50% 40%',
           'takes':[{'start':0,'end':probe(base)['duration']}],'punches':[],'events':[]}
    (folder/'motore/video-gfx/src/data/regia.json').write_text(json.dumps(regia,indent=2),encoding='utf-8')
    (folder/'brief.md').write_text(args.prompt or 'Montare il girato con grafica coerente e sottotitoli dove richiesti.',encoding='utf-8')
    job={'source':'motore/video-gfx/public/base-master30.mp4','transcript':'motore/shorts-pipeline/build/base-master30.transcript.json',
         'duration':regia['durSec'],'status':'prepared','word_timestamps':transcript.get('word_timestamps','source_word_level')}
    save_job(folder,job)
    print(json.dumps({'job':str(folder),**job},ensure_ascii=False,indent=2))

def render_long(args):
    folder=job_path(args.job)
    gfx=folder/'motore/video-gfx'
    regia=gfx/'src/data/regia.json'
    duration=read_job(folder)['duration']
    run([sys.executable,folder/'motore/orchestratore/valida_canone.py','--regia',regia,'--durata',str(duration)])
    run([sys.executable,gfx/'render_regia.py','--tutto','--forza'],cwd=gfx)
    run([sys.executable,folder/'motore/shorts-pipeline/gen_sfx.py'])
    os.environ['MOTORE_SFX']=str(folder/'motore/shorts-pipeline/sfx')
    run([sys.executable,gfx/'build_audio.py','--voce',gfx/'public/base-master30.mp4'],cwd=gfx)
    output=folder/'export'
    output.mkdir(exist_ok=True)
    run([sys.executable,gfx/'consegna.py','video','--dove',output],cwd=gfx)
    video=output/'video.mp4'
    if not video.exists():raise ValueError('Il motore non ha creato export/video.mp4.')
    verify(video,duration)
    job=read_job(folder);job.update(status='exported',output='export/video.mp4');save_job(folder,job)

def verify(video,expected=None):
    info=probe(video)
    if expected is not None and abs(info['duration']-expected)>.5:raise ValueError('Durata finale diversa dal girato.')
    run([runtime.tool('ffmpeg'),'-v','error','-i',video,'-f','null','-'])
    print(json.dumps({'verified':True,**info}))

def doctor(args):
    result={}
    for name in ('ffmpeg','ffprobe','node'):
        try:result[name]=runtime.tool(name)
        except RuntimeError:result[name]=None
    result['python']=sys.version.split()[0]
    result['remotion_installed']=(ROOT/'motore/video-gfx/node_modules').is_dir()
    for module in ('PIL','numpy','cv2','pydantic'):
        result[module]=bool(importlib.util.find_spec(module))
    result['cache']=str(runtime.ensure_env())
    print(json.dumps(result,indent=2))
    if any(result[name] is None for name in ('ffmpeg','ffprobe','node')):return 1
    return 0

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('doctor');p.set_defaults(func=doctor)
    p=sub.add_parser('prepare');p.add_argument('video');p.add_argument('--job',required=True);p.add_argument('--srt');p.add_argument('--transcript');p.add_argument('--prompt',default='');p.set_defaults(func=prepare)
    p=sub.add_parser('render-long');p.add_argument('--job',required=True);p.set_defaults(func=render_long)
    p=sub.add_parser('verify');p.add_argument('video',type=Path);p.set_defaults(func=lambda a:verify(a.video))
    args=parser.parse_args()
    try:return args.func(args) or 0
    except (ValueError,RuntimeError,OSError,subprocess.CalledProcessError) as error:
        print(f'ERRORE: {error}',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
