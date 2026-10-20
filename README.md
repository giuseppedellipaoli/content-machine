# Content Machine

Motore video da usare direttamente con **Claude Code, Codex o qualsiasi LLM con accesso a file e terminale**. L'agente legge il brief e il trascritto, prepara il piano e invoca gli script. Non serve una nuova applicazione web.

Estratto dal motore originale di GDP Studio: **FFmpeg** per montaggio, crop e sottotitoli; **Remotion** per le animazioni; script Python per regia, audio ed export. Codice del progetto sotto **licenza MIT**. Le dipendenze hanno licenze proprie, incluso Remotion: [dettagli](THIRD_PARTY_NOTICES.md).

## Inizia

1. Installa le dipendenze seguendo [INSTALLAZIONE](docs/INSTALLAZIONE.md).
2. Apri il clone con il tuo agente e chiedigli di leggere `AGENTS.md`.
3. Fornisci il video e il brief. Un SRT o JSON temporizzato evita di installare un modello di trascrizione.

```sh
python tools/content_machine.py doctor
python tools/content_machine.py prepare /percorso/video.mp4 --job work/jobs/primo --srt /percorso/testo.srt --prompt "Monta il girato con grafica coerente"
```

L'agente segue la [skill comune](skills/content-machine/SKILL.md) e il [workflow](docs/WORKFLOW.md). Le entrypoint per Claude e Codex sono già incluse. I JSON possono essere scritti anche da un altro modello: il motore non impone un provider né contiene API key.

## Cosa c'è

- Video lungo: componenti grafici originali, regia temporizzata, tavola contatti, render a blocchi versionati, voce originale, SFX sintetici ed export.
- Short: scelta per indici di trascritto, crop verticale, sottotitoli ASS/karaoke, tagli interni con ribasamento dei tempi, overlay e QA.
- Prompt, schemi, guide e preset di brand neutri. Scambio request/response JSON locale per conservare i giudizi dell'agente fuori dal codice.
- Lavori isolati in `work/`, configurazione `.env.example`, installazione ripetibile e prove del motore.

## Confini

È un motore guidato dall'agente, non un pulsante che garantisce montaggio editoriale perfetto. La scelta dei tagli e degli inserti richiede la valutazione del video. Il ramo lungo nativo conserva la timeline originale; il ramo short gestisce tagli e karaoke. Inserti/musica ulteriori si compongono con asset propri tramite l'agente e gli strumenti del motore. Il repository non genera spot da zero, cerca stock o pubblica sui social.

Nessun account, token, cookie, accesso SSH, database, URL di servizio privato, media cliente o cronologia Git del progetto originario è incluso. Font e modelli non redistribuibili si installano separatamente. [Origine e perimetro](docs/ORIGINE.md) · [Risultati del collaudo](docs/VERIFICA.md).
