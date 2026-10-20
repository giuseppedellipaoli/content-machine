# Native shorts pipeline

This is the extracted original Python shorts engine, with its editing modules and regression tests. It runs locally and accepts editorial choices as JSON. Use Claude, Codex or another assistant to prepare those files; the renderer itself does not call an LLM, require an account or publish videos.

## What remains in the engine

- Transcript segment indices resolve to source timestamps, with start/end padding, minimum clip length, overlap removal and a rejection report.
- Portrait reframing uses the median face position across samples when an optional YuNet model and OpenCV are available. Without the model, the renderer keeps the manual horizontal offset and uses a center crop. Aspect-ratio calculations also support narrow sources without stretching.
- Native ASS subtitles retain word highlighting, page timing and configurable karaoke presets. Their accuracy depends on the supplied transcript. Imported SRT words have estimated timing, not forced alignment or a measured transcription.
- Per-clip `correzioni.json` adjusts crop and clip boundaries. `tagli.json` removes internal intervals and rebases retained words and overlay events onto the resulting timeline. `--solo-clip` rebuilds one named output.
- Silence detection, audio-level checks, optional local speech detection, subtitle measurement, image validation and technical QA remain separate modules.
- `zoom_punch.py` makes section-based punch-ins; `fx_build.py` composites native Remotion overlays and synthesized sound effects.

## Paths and tools

Run scripts from any directory using the project Python environment. They load `motore/runtime.py`, including the project's `.env`, tool directories and explicit local cache/temp directory. Configure `FFMPEG_PATH` and `FFPROBE_PATH` if the executables are absent from `PATH`.

The neutral editable kit is `motore/brand-kit.json`. The default working directories are `motore/shorts-pipeline/build`, `out` and `fonts`. `SHORTS_BUILD_DIR`, `SHORTS_OUT_DIR` and `SHORTS_FONTS_DIR` can isolate these directories for a job.

## Transcript and highlights

Use the main CLI's SRT import when a transcript is already available. The native transcript contains `source`, `mtime`, `language`, `duration` and `segments`, each with `id`, `start`, `end`, `text` and `words`. Every word uses `w`, `start` and `end`.

For optional local Whisper transcription:

```sh
python motore/shorts-pipeline/transcribe.py video.mp4 --model small --model-cache work/cache/whisper
```

This command loads local model files only. Allow a download explicitly with `--download-model`; `--model-cache` or `WHISPER_CACHE_DIR` determines the destination. `--device cpu`, `cuda` or `auto` selects execution. `WHISPER_LANG`, `WHISPER_MODEL` and `WHISPER_INITIAL_PROMPT` are optional user settings. No personal glossary is distributed. `fix_transcript.py --dizionario own-dictionary.json` applies an explicitly provided correction dictionary; the default dictionaries are empty.

Optional native dependencies may be unavailable or blocked by the operating system. The script reports the error and offers SRT import. Do not disable or bypass Windows execution protections.

Read [the highlights guide](../motore/shorts-pipeline/HIGHLIGHTS-GUIDE.md), write `highlights.json`, then render:

```sh
python motore/shorts-pipeline/render.py video.mp4 --highlights motore/shorts-pipeline/build/highlights.json
```

Use `--no-subs` to omit subtitles; `--correzioni`, `--tagli` and `--solo-clip` expose the original editing controls. Consult their module docstrings for versioned JSON schemas. The engine validates supplied indices and correction files before rendering.

## Fonts and optional models

No font or model binary is shipped. With no custom font, libass uses a system font family and its installed fallback. This helper records the default system family without copying a font:

```sh
python motore/shorts-pipeline/prepare_fonts.py
```

For a font you have the right to use, set `FONT_PATH` or pass `--font path/to/font.ttf`. FontTools converts supplied variable/WOFF fonts into a local static font for libass. `--family`/`FONT_FAMILY` and `--weight` are optional. Keep the original font's license; generated fonts are excluded from Git.

Set `YUNET_MODEL_PATH` to a separately installed compatible YuNet ONNX model to enable face-aware cropping. It is never downloaded automatically. Speech detection is off by default; opt in with `MOTORE_RILEVATORE_PARLATO=1` and a compatible local `MOTORE_MODELLO_VAD` path. Missing speech models retain the established non-model behavior and emit a warning.

## Native FX and punch-in

`fx_build.py` reads the original `fx_plans.json` array. Its default graphics project is the sibling `motore/video-gfx`; outputs go to `out/fx`. `MOTORE_GFX` and `MOTORE_DEST_FX` override these paths. Set `BROWSER_EXECUTABLE` to an existing supported browser and install the graphics project's dependencies through the documented explicit setup first. The script invokes only the installed Remotion CLI; it does not use npx to fetch packages or download a browser.

`gen_sfx.py` generates local synthetic WAV effects using NumPy. No recording or commercial sound library is included. The FFmpeg filter graph is passed as a direct argument, supporting current FFmpeg versions without the removed `-filter_complex_script` option.

## Verification

The original quick checks are `prova_correzioni.py`, `prova_ingresso_immagini.py`, `prova_karaoke.py`, `prova_ritaglio.py`, `prova_silenzi.py`, `prova_spezzatura.py` and `prova_tagli.py`. Run them with the project Python environment. Font/model-specific tests explicitly report skips when their optional assets are absent. `prova_regressione_render.py` is a heavier byte comparison against the committed `HEAD` renderer and requires a Git checkout with that baseline; it is not a substitute for the quick checks.

Extraction validation passed all seven quick suites. A separate generated 20-second recording with synthetic native word timestamps and a native highlight rendered to 1080×1920 at 30 fps, with ASS subtitles and the model-free center crop. Its measured duration was 20.10 seconds; the engine reported the 0.10-second difference from the requested timeline. A two-section 20-second punch-in also rendered through FFmpeg. The synthetic timestamps are test data, not speech recognition results. Font measurement and speech-model tests were skipped because those optional files were not supplied. Transcription was not validated as a working recognition path.

No original footage, client transcript, private font, model, account configuration, third-party reference corpus or generated build is part of this extraction.
