# Contributing to Content Machine

Thanks for helping make the engine easier to use and verify.

Useful work includes Linux/macOS verification, subtitle timing fixes, documented component examples, rendering portability, and clearer agent instructions. For a substantial change, open a focused issue first so the scope can be discussed.

## Set up

Follow [getting started](docs/getting-started.md). Use a virtual environment in your clone and the pinned dependencies. For development:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

From `motore/video-gfx`, run `npm run typecheck` after changing components. Native Python modules also include `prova_*.py` checks; run the suites relevant to your change. Some font/model checks require separately installed optional assets and explicitly report skips.

## Make a reviewable change

- Explain the concrete before/after behavior and how you checked it.
- Keep native JSON/CLI contracts stable, or document intentional changes.
- Use generated, licensed, shareable fixtures. Include a short example plan when a graphics bug depends on its data.
- A timing change needs a render that checks subtitles, graphics, audio, duration, and cuts. A successful command alone is not enough.
- Distinguish tested results, optional skips, and platforms you have not run.
- Preserve original footage and version outputs rather than overwriting the user's source.

## Keep private data out

Put footage, transcripts, plans for real jobs, request/response exchanges, logs, and outputs under ignored `work/`. Do not submit `.env`, model/agent credentials, customer media, session data, or fonts without redistribution rights. Redact logs before attaching them to an issue.

Before a commit:

```sh
python tools/audit_public.py
```

This is a basic local pattern check, not a guarantee that a file is safe to publish. Review the actual staged files too.

Project code is MIT licensed. Contributions must be yours to share under the project's license. Dependency and asset licenses remain separate; do not vendor Remotion, model weights, or other restricted assets into the repository.
