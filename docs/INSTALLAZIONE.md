# Installazione locale

Requisiti: Python **3.12**, Node **22 o 24**, FFmpeg e FFprobe con libx264/libass, Chrome/Chromium/Edge già installato. Il progetto non installa browser, software di sistema o account. Clone, venv, cache e lavori devono stare sul disco dati scelto dall'utilizzatore.

## Windows PowerShell

```powershell
# Dalla radice del clone, su un disco con spazio per i video.
./setup.ps1
Copy-Item .env.example .env
# Compilare i percorsi propri in .env se i tool non sono nel PATH.
./.venv/Scripts/python.exe tools/content_machine.py doctor
```

## Linux / macOS

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
cd motore/video-gfx
npm ci
cd ../..
cp .env.example .env
.venv/bin/python tools/content_machine.py doctor
```

`requirements.lock.txt` fissa anche le dipendenze Python transitive del core. `npm ci` usa il lockfile incluso. In alternativa `pnpm install --frozen-lockfile` usa il lockfile pnpm. Le dipendenze Remotion sono fissate a 4.0.371. Nessuna cartella node_modules viene distribuita nel repository.

La cache runtime è `work/cache` del clone. `CONTENT_MACHINE_CACHE` la sposta su un proprio disco. TEMP/TMP/TMPDIR e cache dei modelli dei processi del motore puntano a quella cartella; gli script di setup impostano cache pip/npm e staging dentro il clone prima dei download. Le impostazioni globali del sistema non vengono cambiate.

## Trascrizione locale facoltativa

Con SRT o JSON temporizzato non serve alcun modello. Per trascrivere dal video:

```sh
python -m pip install -r requirements-transcription.txt
python motore/shorts-pipeline/transcribe.py /percorso/video.mp4 --model small --download-model
```

Il flag autorizza il download del modello scelto nella cache configurata. Le esecuzioni senza flag usano solo file già disponibili. Non sono incluse chiavi, sessioni o pesi nel repo. La licenza dei pesi scelti va verificata separatamente da quella della libreria.

Sul PC usato per la verifica del 20 ottobre 2026 Windows ha bloccato una DLL di CTranslate2 con **WinError 4551**. Le protezioni non sono state aggirate. La trascrizione locale su questo PC non è certificata da quel test; l'import SRT/JSON e il montaggio sono verificati separatamente. Se accade, usare un SRT/JSON ottenuto legittimamente o un ambiente supportato dall'amministratore.

## Font e rilevamento volto

Il motore usa font del sistema. `FONT_PATH`/`prepare_fonts.py --font` permettono di scegliere un font posseduto dall'utilizzatore; non condividere font senza la relativa licenza. Il modello YuNet può essere installato separatamente e indicato tramite `YUNET_MODEL_PATH`; non è incluso. Il crop centrale funziona senza il modello.

## Accessi LLM

Nessun login nel progetto: avvia il clone con il tuo Claude Code, Codex o altro agente e usa le skill. I relativi account/abbonamenti rimangono nella tua applicazione. Il trasporto LLM del motore usa solo file locali. Il repository non riutilizza servizi, database, SSH o storage dell'autore.

## Licenze

Il codice del progetto è MIT. Le dipendenze conservano i propri termini: Remotion ha una licenza specifica e può richiederne una commerciale in base al soggetto/uso. Nessuna licenza o sottoscrizione viene acquistata dall'installazione. Vedi `THIRD_PARTY_NOTICES.md` prima di distribuire un prodotto che includa i runtime.
