"""Genera un campione sintetico ripetibile, senza media di terzi o clienti."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'motore'))
import runtime

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dir',default=str(ROOT/'work/demo-input'))
    args=ap.parse_args()
    folder=Path(args.dir).resolve()
    folder.mkdir(parents=True,exist_ok=True)
    video=folder/'demo.mp4'
    if video.exists():raise SystemExit('Demo già esistente: scegliere una cartella nuova.')
    subprocess.run([runtime.tool('ffmpeg'),'-hide_banner','-loglevel','error',
                    '-f','lavfi','-i','testsrc2=s=1920x1080:r=30',
                    '-f','lavfi','-i','sine=frequency=330:sample_rate=48000',
                    '-t','18','-c:v','libx264','-preset','veryfast','-crf','18',
                    '-pix_fmt','yuv420p','-c:a','aac','-af','loudnorm=I=-14:TP=-1.5:LRA=11',
                    '-movflags','+faststart',str(video)],check=True)
    (folder/'demo.srt').write_text('''1
00:00:00,200 --> 00:00:05,800
Questo è un campione sintetico con tono di prova, senza una voce registrata.

2
00:00:06,100 --> 00:00:11,800
Il motore aggiunge grafica, sottotitoli ed effetti al girato originale.

3
00:00:12,100 --> 00:00:17,800
I dati di questa dimostrazione sono fittizi e non appartengono a clienti.
''',encoding='utf-8')
    print(json.dumps({'video':str(video),'srt':str(folder/'demo.srt'),
                      'note':'Sorgente audiovisiva sintetica; SRT descrittivo, non trascrizione di parlato.'},ensure_ascii=False))

if __name__=='__main__':main()
