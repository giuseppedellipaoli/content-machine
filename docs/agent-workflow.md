# Agent workflow

The agent makes editorial decisions from the brief, footage, and transcript. Scripts validate plans and execute renders. Claude Code, Codex, and other coding agents share the same file-based interface.

## Entrypoints

- Common procedure: [`skills/content-machine/SKILL.md`](../skills/content-machine/SKILL.md).
- Repository instructions: [`AGENTS.md`](../AGENTS.md).
- Claude Code: [`CLAUDE.md`](../CLAUDE.md) and `.claude/skills/content-machine/`.
- Codex-compatible skill: `.agents/skills/content-machine/`.
- Other agents: read the common procedure directly. Models without terminal access can prepare JSON for a person to execute.

No provider SDK or credentials are needed by the orchestration adapter. Your chosen agent has its own access requirements and terms.

## Long-form

1. Run `doctor`, then `prepare` with a new job directory, footage, transcript, and brief.
2. Read the job's `brief.md` and `motore/shorts-pipeline/build/base-master30.for_llm.txt`.
3. Write the job's `motore/video-gfx/src/data/regia.json`, using actual transcript timings and supported component fields. Preserve meaning, leave room for the face, and use only claims supported by source material.
4. Validate and inspect a contact sheet:

```sh
python work/jobs/NAME/motore/orchestratore/valida_canone.py \
  --regia work/jobs/NAME/motore/video-gfx/src/data/regia.json \
  --durata ACTUAL_DURATION_SECONDS
python work/jobs/NAME/motore/video-gfx/render_regia.py --contatti
```

5. Render:

```sh
python tools/content_machine.py render-long --job work/jobs/NAME
```

The native path composes versioned video blocks, synthesized effects, original audio, delivery, and technical checks. It preserves the normalized source timeline. Extra cuts, inserts, music, or long-form subtitles need an explicit composition and correctly updated timings.

## Shorts

Follow [SHORTS.md](SHORTS.md). Write `highlights.json` using transcript **segment indices**. The engine resolves timestamps, applies crop/subtitle rules, and supports internal cuts with time rebasing. Overlay plans are separate JSON. Inspect face crop and word timing before treating a short as ready to publish.

## Provider-independent JSON exchange

`analizza`, `correggi`, `highlights`, `regia`, and `componi_fx` retain native prompts, schemas, and conversions. The `llm.py` adapter exchanges files instead of calling an API.

**First run:** a command writes `STEP.request.json` and exits with **2**. The request includes `system`, `input`, `schema`, and `request_sha256`. Read the actual request, then write `STEP.response.json` beside it:

```json
{
  "request_sha256": "copy the current request hash",
  "output": {"fields": "matching the actual request schema"}
}
```

**Second run:** repeat the same command. A stale hash or invalid schema is rejected; a valid response continues the pipeline. No background request is sent to an LLM API. `LLM_EXCHANGE_DIR` isolates exchanges per job. These files contain source material and should remain local.

Example from the job directory:

```sh
python motore/orchestratore/highlights.py \
  motore/shorts-pipeline/build/base-master30.for_llm.txt \
  --guida motore/shorts-pipeline/HIGHLIGHTS-GUIDE.md \
  --massimo 3 \
  --uscita motore/shorts-pipeline/build/highlights.json
```

Use `regia.py --help` for word-index-based conversion, or write native plans directly and validate them. See the [native component reference](RENDERER.md) for advanced fields. Native CLI flags and JSON identifiers are intentionally retained rather than translated.

## Before delivery

Inspect a contact sheet and beginning/middle/end frames. Listen for clipped words and audio problems. Check subtitles and the difference between measured word times and SRT estimates. Report the output file, technical checks, and remaining editorial limitations. A successful render is not editorial approval.
