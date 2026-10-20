# Content Machine

Questo repository contiene il motore video e i suoi comandi. L'agente LLM è l'orchestratore: non avviare un nuovo frontend, backend SaaS o integrazioni con account social per montare un video.

Per lavori video leggi `skills/content-machine/SKILL.md`. Installazione in `docs/INSTALLAZIONE.md`, contratti in `docs/WORKFLOW.md`. Claude legge anche `CLAUDE.md`; le entrypoint per skill sono in `.agents/skills/` e `.claude/skills/`.

Input, piani e output dei lavori stanno in `work/`, esclusa da Git. Non aggiungere media cliente, `.env`, token, sessioni o chiavi al repository. Gli accessi dell'agente rimangono nella sua applicazione, non in questo progetto. Nessuna pubblicazione o chiamata API viene eseguita dai comandi LLM: scambiano file JSON locali.

Il codice in `motore/` è estratto dalla fabbrica originale; preservare i contratti di timestamp, ribasamento dopo tagli, canale alpha degli overlay e voce originale. Dopo modifiche eseguire le prove pertinenti e almeno un export quando cambia il rendering. Scrivere lo stato del singolo lavoro nel suo `job.json` o rapporto locale.
