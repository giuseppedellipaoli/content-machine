# Verifica del 20 ottobre 2026

## Installazione da copia pulita

Creata una cartella contenente **solo i file indicizzati da Git**: niente `.env`, venv, node_modules, build, media generati o accessi del progetto di partenza. Installati un nuovo venv da `requirements.lock.txt` e nuove dipendenze Node con `npm ci --ignore-scripts`. Gli strumenti di sistema sono stati forniti tramite i percorsi configurati per il collaudo, senza copiare account o servizi.

Ambiente provato: Windows, Python 3.12.10, Node 24, FFmpeg/FFprobe 9.0.2, Chrome già installato, Remotion 4.0.371. La portabilità dei percorsi è implementata; Linux e macOS non sono stati collaudati in questa sessione.

Dal campione generato da `tools/demo.py`: `prepare` con SRT -> workspace nuovo -> regia nativa card+minibars -> validazione -> render -> SFX sintetici -> audio -> consegna -> decodifica completa.

**Risultato: MP4 H.264/AAC, 18,000 secondi, 1920×1080, 30 fps, QA 100/100.** Il campione contiene movimento sintetico e tono audio: non è una registrazione cliente né una prova di riconoscimento vocale. L'SRT descrittivo è esplicitamente marcato con tempi di parola stimati. Verificati fotogrammi di card e grafico. Il controllo hook/banner non era applicabile al video lungo.

## Motore nativo

- Sette suite rapide della pipeline short riuscite: 452 verifiche contate tra correzioni, karaoke, ritaglio, silenzi, spezzatura e tagli, più i casi di ingresso immagini. Nove prove opzionali saltate per modello VAD/font assenti.
- Short nativo da sorgente sintetico di 20 secondi: 1080×1920, 30 fps, sottotitoli ASS con parola attiva, crop centrale senza YuNet. Durata rilevata 20,10 secondi: il comportamento del motore include margini/frame e va controllato sui tagli effettivi.
- Punch-in su due intervalli verificato con FFmpeg 9.
- 17 prove originali di conversione FX dopo tagli riuscite.
- Tre casi sintetici del canone: piano valido accettato; tempi interni fuori evento e tipo ignoto rifiutati.
- Due test dello scambio LLM: round-trip conforme accettato; risposta obsoleta e schema invalido rifiutati. Provata anche la CLI highlights completa: exit 2 con richiesta, risposta scritta dall'agente, seconda esecuzione con export valido; zero chiamate API dal pacchetto.
- Compilazione TypeScript e parsing Python riusciti; tre entrypoint di skill validati.

## Correzioni operative nell'estrazione

Percorsi personali sostituiti, cache/staging espliciti, font del sistema, modelli non inclusi, browser già installato. Gli script non installano dipendenze durante un render. Aggiornato il passaggio dei filtri per FFmpeg 9, che non accetta il vecchio `-filter_complex_script`. Evitata la seconda codifica AAC nella consegna per mantenere il true peak entro soglia. Errori QA propagati come esito negativo, blocchi versionati e concatenazione ricostruita correttamente.

Un primo render di 18 secondi ha avuto un errore transitorio del compositor Remotion, non attribuibile con certezza dai log disponibili. Le ripetizioni sul lavoro isolato e sulla copia pulita sono riuscite. Aggiunti log completi locali e concorrenza predefinita 2, configurabile con `MOTORE_CONCURRENCY`.

## Pulizia per la pubblicazione

Nuova storia Git; esclusi configurazioni locali, accessi, sessioni, media cliente, log, dati generati e cronologia originaria. Eseguita scansione dei file e dei blob Git per formati di segreti comuni, file non ammessi e riferimenti personali. Confrontati in memoria anche i valori sensibili della configurazione originale: nessuna corrispondenza nei file destinati alla consegna. I valori non sono stati stampati o salvati nel repository. Questo controllo non revoca né cambia alcun accesso originale.

## Limiti aperti

La trascrizione faster-whisper non è certificata su questo PC: Windows ha bloccato una libreria CTranslate2 con WinError 4551; le protezioni non sono state aggirate. Funziona il percorso collaudato con SRT/JSON. Non sono stati collaudati tutti i componenti grafici su ogni possibile combinazione di dati, font e formato. Il video reale di Marco non è stato usato: la valutazione editoriale con Francesca resta da fare.
