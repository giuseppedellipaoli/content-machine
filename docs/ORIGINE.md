# Origine e perimetro

Il codice proviene dal motore originale di GDP Studio. Il checkout di partenza è stato letto senza modificare sorgenti, configurazioni o accessi. Il pacchetto ha una nuova storia Git e non include quella del progetto originario.

Componenti conservati:

- `motore/shorts-pipeline`: montaggio e crop, sottotitoli karaoke, correzioni, algebra dei tagli, silenzi, QA, generazione SFX, overlay e prove del motore.
- `motore/video-gfx`: componenti generici originali, master e overlay short, tema parametrico, render a blocchi, audio e consegna. Sono stati eliminati scene specifiche di clienti, fullscreen con affermazioni cablate, dati di produzioni precedenti e font non verificati.
- `motore/orchestratore`: schemi, prompt e conversioni per analisi, correzioni, highlight, regia e FX; validatore deterministico. Il vecchio trasporto API è sostituito da file request/response per qualsiasi agente.
- `mappa_visiva.py`: proposte dal trascritto usando un brand kit neutro.

Adattamenti per l'autonomia: percorsi relativi/env, browser e font del proprio sistema, cache nel clone o disco scelto, assenza di download impliciti nei render, fallback senza modello volto, supporto FFmpeg 9, errori QA propagati, workspace isolati e istruzioni per agenti.

Esclusi: pannello web, API SaaS, billing, database, coda PostgreSQL, storage del servizio, deploy VPS, SSH, account social, pubblicazione, email, dati di altri clienti, log, backup, sessioni e credenziali. Il primo prototipo web sperimentale non appartiene a questo repository.

Non sono distribuiti archivi di applicazioni terze, materiale da directory `reference`, asset di reverse engineering, modelli, font o media originali. Le dipendenze si installano dai loro package registry ufficiali e conservano i propri termini. Il campione di collaudo viene generato da codice e FFmpeg; non contiene volti o dati cliente.
