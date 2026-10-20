# Provenance and scope

Content Machine was extracted from the original GDP Studio video engine. The source checkout, configuration, accounts, and access permissions were preserved. This repository starts a new Git history rather than importing the original project's history.

## Retained components

- `motore/shorts-pipeline`: editing, crops, karaoke subtitles, corrections, cut-time algebra, silence handling, QA, synthetic SFX, overlay composition, and native checks.
- `motore/video-gfx`: generic native components, long-form master, short overlays, configurable theme, versioned rendering, audio, and delivery. Client-specific fullscreen scenes, old production data, and unverified font files were excluded.
- `motore/orchestratore`: schemas, prompts, and deterministic conversions for analysis, corrections, highlights, graphics plans, and FX. The old provider API transport was replaced with local request/response JSON exchange.
- `mappa_visiva.py`: transcript-based visual suggestions from a neutral editable brand kit.

## Portability changes

Relative/configurable paths, system fonts and browser, explicit cache/temp locations, no implicit downloads during rendering, model-free crop fallback, FFmpeg 9 compatibility, propagated QA errors, isolated workspaces, and agent instructions.

## Excluded

Hosted control plane, web dashboard, billing, database, PostgreSQL queue, private object storage, VPS deployment, SSH, social accounts, publishing, email integration, other clients' data, original logs, backups, sessions, credentials, and original Git history.

No third-party reference archives, reverse-engineering assets, original footage, private transcripts, model weights, or font binaries are redistributed. Dependencies install from their package registries and retain separate terms. Demonstration footage is generated, contains no people or customer data, and is labeled as synthetic. The cover is AI-generated brand artwork, not an engine screenshot.
