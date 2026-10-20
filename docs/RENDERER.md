# Motore grafico nativo

Questo pacchetto conserva la libreria Remotion originale, la regia a livello di parola, il render a blocchi versionati, la contact sheet, la composizione della voce originale con SFX e la consegna verificata. L'agente Claude, Codex o un altro LLM prepara i JSON nativi e usa gli script. Nessun frontend, backend, account o servizio dell'autore è richiesto. Nessuna API a pagamento è necessaria per il renderer.

## File estratti

`motore/video-gfx/src/scenes/RegiaComponents.tsx` conserva tutti i 23 tipi di overlay originali. `MasterFull.tsx` conserva il video originale come base, zoom leggero e punch sincronizzati; sono state escluse le tavole fullscreen legate a contenuti privati. `OverlayShort.tsx` conserva gli otto tipi verticali. `theme.tsx`, `Timbro.tsx` e `brand.ts` mantengono i meccanismi originali con testi neutri, font di sistema e marchio configurabile. La root contiene soltanto `master-full` e `OV-short`.

Gli script `render_regia.py`, `build_audio.py`, `consegna.py`, `sincronizza_brand.py` derivano dai rispettivi originali. Gli adattamenti eliminano percorsi personali, font/media privati, default su un girato specifico, tavole di clienti e servizi di pubblicazione. Il runtime esegue la CLI Remotion installata localmente tramite Node e passa sempre un browser di sistema esplicito. Non usa `npx` per installare pacchetti durante il render e non scarica browser.

## Comandi nativi

Eseguire nella cartella `motore/video-gfx` della copia di lavoro del job:

```sh
python sincronizza_brand.py
python sincronizza_brand.py --verifica
python render_regia.py --contatti
python render_regia.py --tutto
python render_regia.py --evento 2 --forza
python render_regia.py --da 2 --a 5 --bozza
python build_audio.py --voce /percorso/video-originale.mp4
python consegna.py finale --dove /percorso/export
```

`build_audio.py --voce` è obbligatorio. Gli SFX si generano con `python ../shorts-pipeline/gen_sfx.py`; `MOTORE_SFX` può indicare un'altra cartella autorizzata con `whoosh.wav`, `pop.wav`, `thud.wav`. Usare `--senza-sfx` per la sola voce normalizzata. `--profilo-sfx FILE.json` mantiene il contratto originale per volumi/mappe degli eventi. Gli SFX mancanti causano un errore esplicito.

Il render produce video muto in `build/master-video.mp4`; l'audio finisce in `exports/master-audio.m4a`. La consegna copia l'AAC già codificato evitando una seconda perdita di qualità, converte realmente i livelli video quando necessario e imposta faststart. Il QA sotto soglia produce un exit code nonzero; `--senza-controllo` è un'esclusione esplicita, non il comportamento predefinito. Differenze audio/video superiori a 0,5 s bloccano la consegna. Per un render in bozza usare anche `consegna.py --bozza` e considerare le dimensioni inferiori nel QA.

I blocchi esistenti vengono riusati. Dopo un cambio di regia/brand/base, usare `--forza` o una nuova copia isolata del job. Le versioni non vengono sovrascritte; `--tutto` ricrea anche il master quando tutti i blocchi sono già presenti. Non condividere la cartella `src/data`, `public` o `build` fra job concorrenti.

Il runtime importa l'ambiente condiviso `motore/runtime.py`, quindi i comandi diretti leggono il `.env` del progetto. Variabili: `NODE_PATH`, `FFMPEG_PATH`, `FFPROBE_PATH`, `REMOTION_BROWSER_EXECUTABLE` oppure `CHROME_PATH`, `CONTENT_MACHINE_CACHE`. Il browser può anche essere rilevato dal sistema. Cache, TEMP/TMP/TMPDIR seguono la configurazione; su questo PC progetto e cache sono su E:. I percorsi di sistema cercati per Chrome/Edge non sono percorsi personali.

I render usano due pagine concorrenti per limitare memoria e decodifiche simultanee; `MOTORE_CONCURRENCY=1..16` modifica il limite (`REMOTION_CONCURRENCY` è accettato come alias). Un errore di render/bundle/still conserva stdout e stderr completi in `build/render-error.log`, evitando che il solo frammento finale nasconda la causa. Il log resta nella copia locale del job ed è escluso dal repository.

## Piano lungo originale

`src/data/regia.json` contiene:

```json
{
  "fps": 30,
  "durSec": 8,
  "source": "base-master30.mp4",
  "faceOrigin": "70% 40%",
  "takes": [{"start": 0, "end": 8}],
  "punches": [{"t": 4, "scale": 1.1}],
  "events": [
    {"id": 1, "type": "card", "t0": 0.5, "t1": 3.5, "pos": "SX", "title": "Parole del video", "rows": [{"t": 1, "text": "Un punto chiave"}]}
  ]
}
```

Il motore nativo usa **30 fps**, 1920×1080 orizzontale e 1080×1920 verticale. Normalizzare prima il girato. `source` è relativo a `public/`; il default è `base-master30.mp4`. Tutti i tempi `t0`, `t1`, `t`, `k` sono secondi assoluti sulla timeline normalizzata. Non sono timestamp inventati dal modello: l'agente deve ricavarli dal trascritto. `takes` deve coprire tutta la durata; `punches` può essere vuoto. Gli eventi hanno `id` univoco e intervalli entro la durata. I tipi sconosciuti causano errore.

Le posizioni native sono `SX`, `ADX`, `BSX`, `TOP`. Testo con `*enfasi*` viene evidenziato col colore di accento nei componenti che usano `Rich`. Le liste temporizzate usano `{t,text,red?}` quando non indicato diversamente. Il file TSX resta il contratto completo dei campi avanzati.

| Tipo | Campi principali oltre a id/type/t0/t1/pos |
|---|---|
| card | title, sub?, sub2?, rows?, fork?, loop?, tail? |
| qcard | title, bullets?, checks?, cross?, tail?, redTitle? |
| badge | title, big?, enter? |
| pills | pills, label?, stamp?: {t,text} |
| flow | steps: [{t,text,x?}] |
| race | fast/slow: {label,value}, k.fast/k.slow?, tail? |
| keyword | title, k.red?, size? |
| minibars | counter: {target,prefix?,suffix?}, bars: [{at,h1,h2}], label, k.counter? |
| chat | bubbles: [{t,side,who,text}] |
| claim2 | lines: [{t,text,red?}], size? |
| bigone | value?, sub, k.sola? |
| arrow2 | from, to |
| avatar | title, sub, k.x? |
| cols2 | left/right: {label,text,red?}, k.dx? |
| network | center, nodes: [{t,text}] |
| pipeline | nodes: [{t,text,red?}], label? |
| six | seed, out, k.six?, k.out? |
| crash0 | from, unit?, label, tail, k.crash?, k.lbl? |
| crashdown | value, prefix?, unit?, sub, tail?: {t,text} |
| grid | cells: [{t,text,red?}], label? |
| cta | rows: [{t,text,red?}] |
| lista3 | value, title?, label?, k.hl, k.ore |
| stamp | text? (default OK), label? |

`bigone`, `crash0`, `crashdown`, `lista3` avevano numeri/testi di un lavoro precedente: sono ora parametri espliciti, senza riproporre dati privati. L'agente deve usare soltanto numeri pronunciati nel video o forniti dall'utilizzatore. I componenti `six` e `lista3` conservano la loro forma specializzata (sei tessere / evidenziazione di tre righe).

## Overlay short originale

La composizione `OV-short` è trasparente e riceve props `{events: [...], durSec: N}` da `fx_plans.json`. Tipi e campi:

| Tipo | Campi |
|---|---|
| pill | text; banner nativo 0,15–4,6 s |
| hook | t0, t1, text, kicker?, red? |
| card | t0, t1, text, red? |
| counter | t0, t1, to, label, redLabel? |
| list | t0, t1, header, items: [{t,text}] |
| claim | t0, text, red?; rimane fino alla fine |
| cta | t0, t1, text, kicker?, red? |
| stamp | t; timbro neutro |

`shorts-pipeline/fx_build.py` rende l'alfa ProRes 4444 e la compone con FFmpeg sopra lo short con voce/sottotitoli. Le guide e il piano dell'agente devono rispettare lo spazio per volto e sottotitoli; il renderer non comprende semanticamente il video.

## Licenze e asset

Il codice originale del proprietario è estratto e pubblicato secondo l'autorizzazione OSS del titolare; si applica la licenza del repository ai file di sua titolarità. Le dipendenze ufficiali npm conservano le proprie condizioni e non vengono vendorizzate come codice del progetto. Remotion 4.0.371 ha [termini propri](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md), distinti dalla licenza MIT di React e del repository. L'agente deve verificare l'idoneità dell'utilizzatore ai termini Remotion prima di un impiego commerciale/distribuzione; non viene acquistata alcuna licenza automaticamente.

Nessun font, logo, filmato cliente, trascritto privato, riferimento di account, credenziale o sessione originale è incluso. Non sono stati copiati asset ottenuti da reverse engineering. I font provengono dal sistema dell'utilizzatore; chi aggiunge font/immagini/video deve avere i relativi diritti. Gli SFX sono sintetizzati dal codice locale originale. I pacchetti e binari FFmpeg/Chrome usati restano dipendenze esterne con proprie licenze.

## Verifica eseguita

Il 20 ottobre 2026: compilazione TypeScript e Python riuscite; contact sheet nativa ispezionata; render integrale di un sorgente sintetico di 8 s; audio originale sintetico + tre SFX generati; consegna MP4 H.264/AAC, 1920×1080, 30 fps, durata 8,000 s, QA **100/100**. La verifica hook/banner era non applicabile al campione lungo. Eseguita anche una still `OV-short` con props native e la ricostruzione del master da blocchi già presenti.

Il test ha corretto incompatibilità reali: `-filter_complex_script` sostituito con `-filter_complex` per FFmpeg 9, percorsi di consegna relativi risolti prima del QA, copia AAC per evitare un secondo passaggio con picchi oltre soglia. Media sintetici, build, export, cache e dipendenze sono artefatti generati esclusi dal repository. Non è stata eseguita una campagna visiva di tutti i 23 tipi: i componenti avanzati richiedono una preview sul piano specifico prima dell'export finale.

Verificata anche una copia isolata di job con dipendenze collegate e un sorgente di 18 s: card + minibars, render a concorrenza predefinita precedente e nuovo render con concorrenza 2 entrambi riusciti; audio con SFX sintetici, consegna e QA 100/100, MP4 H.264/AAC 1920×1080/30 fps, 18,000 s. Un precedente errore transitorio del compositor non si è riprodotto: non è stata accertata la sua causa. Il nuovo log completo e il limite di concorrenza consentono diagnosi più affidabili e un carico di memoria più contenuto.
