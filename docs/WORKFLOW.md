# Uso con Claude, Codex o un altro LLM

Apri il clone con un agente che possa leggere file ed eseguire comandi. Non sono richiesti un provider specifico, server web o API key nel repository. Le due directory di skill sono entrypoint allo stesso procedimento. Un modello senza terminale può produrre gli stessi JSON; i comandi saranno eseguiti dall'utilizzatore.

Esempio di richiesta all'agente:

> Leggi AGENTS.md e usa Content Machine per montare il mio video /percorso/video.mp4. Crea un lavoro nuovo, scegli i punti importanti dal parlato, aggiungi grafica coerente e sottotitoli. Usa solo gli inserti che ti fornisco. Verifica l'export e mostrami il risultato.

## Preparare il girato

```sh
python tools/content_machine.py doctor
python tools/content_machine.py prepare /percorso/video.mp4 --job work/jobs/primo --prompt "Brief del montaggio" --srt /percorso/testo.srt
```

In alternativa a `--srt`, `--transcript` accetta il JSON nativo con `segments[].words[].{w,start,end}`. Senza entrambi serve faster-whisper installato e un modello preparato: vedi INSTALLAZIONE.md.

`prepare` crea una cartella nuova e normalizza una copia del girato a 1920×1080, 30 fps, H.264/AAC. Conserva l'audio, con bande se serve per non deformare l'immagine. Copia nella cartella di lavoro solo il motore ripulito e collega le dipendenze Node dello stesso clone. Nessun `.env`, account o media di un lavoro precedente viene copiato. Il girato originale non viene modificato. I link alle dipendenze non sono copie da cancellare ricorsivamente.

Con SRT i tempi delle parole sono stimati all'interno delle battute e marcati `estimated_from_srt`. Non usare quelle stime per tagliare sillabe o rivendicare precisione karaoke; scegliere i confini di battuta e rileggere i sottotitoli. Per precisione parola per parola usare la trascrizione nativa o un allineamento verificato.

## Video lungo

L'agente legge `work/jobs/primo/brief.md` e il trascritto in `motore/shorts-pipeline/build/`. Scrive la regia nel `motore/video-gfx/src/data/regia.json` DEL LAVORO, seguendo `RENDERER.md`.

```sh
python work/jobs/primo/motore/orchestratore/valida_canone.py --regia work/jobs/primo/motore/video-gfx/src/data/regia.json --durata DURATA_REALE
python work/jobs/primo/motore/video-gfx/render_regia.py --contatti
python tools/content_machine.py render-long --job work/jobs/primo
```

La tavola contatti controlla l'aspetto. Il render controlla il movimento. `render-long` richiama gli script originali: render per blocchi versionati, generatore SFX sintetici, audio originale con SFX e loudness, consegna MP4 con QA. Il finale è `work/jobs/primo/export/video.mp4`. La grafica lungo originale usa un canvas 1920×1080/30; il ramo short è verticale. Una bozza può essere generata direttamente con `render_regia.py --tutto --bozza`; non è un export finale conforme al formato pieno del QA.

Il ramo lungo nativo conserva la durata e la voce del girato normalizzato. Non ha ricerca stock, montaggio semantico illimitato o sottotitoli lungo integrati. Se il brief richiede tagli/inserzioni/musica/sottotitoli ulteriori, l'agente può comporre file forniti tramite FFmpeg o adattare i componenti nel lavoro isolato; deve aggiornare la timeline e verificare la sincronizzazione. Nessuna di queste scelte viene simulata da una regola locale chiamata AI.

## Short

Vedi `SHORTS.md`. L'agente seleziona indici di segmento in `highlights.json`; il motore originale risolve tempi, crop, parole e karaoke. `correzioni.json` e `tagli.json` permettono crop/tagli mirati e rimozioni interne con ribasamento degli effetti. `fx_build.py` aggiunge overlay Remotion e SFX. Il modello YuNet è opzionale e non distribuito: in sua assenza è disponibile il crop centrale, da controllare sul soggetto.

## Scambio JSON con qualsiasi LLM

I moduli originali `analizza`, `correggi`, `highlights`, `regia`, `componi_fx` conservano schemi e conversioni. Il trasporto API personale è stato sostituito da `orchestratore/llm.py`, che non importa SDK e non effettua richieste di rete.

Primo comando: genera `STEP.request.json` in `work/exchange/` e termina con **exit 2**, che significa attesa dell'agente. Il JSON contiene `system`, `input`, `schema` e `request_sha256`. L'agente scrive nella stessa cartella:

```json
{"request_sha256":"hash della richiesta corrente","output":{"campi":"conformi allo schema"}}
```

Il secondo avvio dello stesso comando valida la risposta e continua. Una risposta relativa a una richiesta vecchia viene rifiutata. `LLM_EXCHANGE_DIR` può isolare gli scambi per lavoro. Non committare i request/response: contengono il trascritto.

Esempio highlights (tutti i file sotto la cartella del lavoro):

```sh
python motore/orchestratore/highlights.py motore/shorts-pipeline/build/base-master30.for_llm.txt --guida motore/shorts-pipeline/HIGHLIGHTS-GUIDE.md --massimo 3 --uscita motore/shorts-pipeline/build/highlights.json
```

Per la regia avanzata `regia.py --help` descrive proposte, takes, durata e guide richieste. L'agente può anche scrivere direttamente la regia nativa e farla validare. Le scelte editoriali sono dell'agente e dell'utilizzatore; la conformità del JSON e dei timestamp è controllata dal codice.
