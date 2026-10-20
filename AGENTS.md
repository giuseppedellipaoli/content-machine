# Content Machine

This repository is a local video engine. The LLM agent is the orchestrator: use the native scripts and JSON contracts instead of building a new frontend, hosted backend, or social-account integration to perform an edit.

For video work, read `skills/content-machine/SKILL.md`. Installation: `docs/getting-started.md`. File contracts: `docs/agent-workflow.md`. Claude also reads `CLAUDE.md`; skill entrypoints are in `.agents/skills/` and `.claude/skills/`.

Keep footage, transcripts, real-job plans, request/response files, logs, and outputs under ignored `work/`. Never commit agent credentials, `.env`, sessions, customer media, or private service configuration. Agent authentication stays in the agent application. The LLM adapter exchanges local JSON files; it does not call a provider API or publish anything.

Preserve the native timestamp contracts, cut-time rebasing, transparent overlays, and original voice. Use the environment of the current clone. After relevant changes, run the appropriate checks and a real export when rendering behavior changes. Record each job's state in its own `job.json` or local report. Distinguish verified results, skips, and untested platforms.
