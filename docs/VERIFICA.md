# Verification report — October 20, 2026

## Clean installation

A new directory was populated with tracked files only: no `.env`, venv, node_modules, generated media, or credentials from the original project. A fresh Python environment was installed from `requirements.lock.txt`; fresh Node dependencies were installed with `npm ci --ignore-scripts`. System tools were supplied through explicit local paths rather than private services.

Verified environment: Windows, Python 3.12.10, Node 24, FFmpeg/FFprobe 9.0.2, an existing Chrome installation, and Remotion 4.0.371. Linux/macOS are not yet verified end to end.

The generated sample followed the complete chain: prepare with SRT -> new isolated job -> native card/chart plan -> validation -> render -> synthesized SFX -> audio -> delivery -> complete decoding.

**Result: H.264/AAC MP4, 18.000 seconds, 1920×1080, 30 fps, technical QA 100/100.** The source contains synthetic movement and an audio tone; it is not customer footage or a speech-recognition test. The descriptive SRT is explicitly marked with estimated word timings. Card and chart frames were inspected. The hook/banner check did not apply to the long-form sample.

## Native checks

- Seven quick shorts suites passed. Corrections, karaoke, crop, silence, wrapping, and cuts account for 452 counted checks, plus image-input cases. Nine optional checks were skipped for unavailable VAD/font assets.
- A native synthetic 20-second short rendered at 1080×1920 / 30 fps with ASS active-word subtitles and the model-free center crop. Measured duration: 20.10 seconds; native padding/frame behavior should be checked on actual cuts.
- Two-section punch-in rendered with FFmpeg 9.
- 17 original FX conversion/rebasing checks passed.
- Three synthetic canonic-plan cases passed: valid plan accepted; out-of-event internal times and unknown type rejected.
- Two offline LLM exchange tests passed, covering matching responses, stale request hashes, and invalid schemas. The highlights CLI completed a request -> agent-written response -> validated export handoff without a package API call.
- TypeScript checks and Python parsing passed. Three agent skill entrypoints validated.

## Operational fixes

Personal paths were removed; cache/staging, system fonts, and existing-browser selection were made explicit. No model is bundled and no render implicitly installs dependencies. FFmpeg 9 filter arguments were updated, extra AAC re-encoding was avoided to preserve true peak, QA failures now propagate, and versioned block concatenation was corrected.

One initial 18-second render had a transient Remotion compositor error whose cause could not be established from the available logs. Repeated isolated-job and clean-copy renders succeeded. Complete local error logs and default concurrency 2 were added; `MOTORE_CONCURRENCY` changes the limit.

## Publication checks

A new Git history excludes local configuration, accounts, sessions, customer media, generated outputs, and original history. Working files and Git blobs were scanned for common secret formats and disallowed files. Sensitive original configuration values were also compared in memory against the delivery files, without printing or saving those values. No matches were found in that checked snapshot. No original access was revoked or changed.

## Presentation update

An English README and primary onboarding/agent instructions, contribution templates, an AI-generated cover, and a native rendered preview were added. The preview uses the actual card/flow/CTA components on a synthetic background, cropped for readability. It is a silent component demonstration, not a new full QA benchmark or an editorial-quality claim. Runtime behavior was not changed by this presentation update.

## Open limits

Local faster-whisper recognition is not certified on the tested PC: Windows blocked a CTranslate2 library with WinError 4551. Protections were not bypassed. The SRT/JSON import and rendering path is verified separately. Not every component/data/font/format combination has been rendered. A real customer-video editorial review remains to be done.
