# Getting started

Content Machine is a command-line video engine used by an AI coding agent. Install the tools once, open the clone with your agent, and keep each edit in its own job directory.

## Prerequisites

Python **3.12**, Node **22 or 24**, npm or pnpm, FFmpeg/FFprobe with **libx264 + libass**, and an existing **Chrome, Chromium, or Edge** installation. Use a clone and virtual environment on your chosen data drive. The package does not install a browser or system-wide tools.

## Windows

```powershell
./setup.ps1
Copy-Item .env.example .env
./.venv/Scripts/python.exe tools/content_machine.py doctor
```

The script installs pinned Python dependencies and locked Node dependencies. Installer cache and staging are placed in `work/cache` before downloads. Global environment settings are not changed.

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

Set `TMPDIR`, `PIP_CACHE_DIR`, and `npm_config_cache` before installation if caches should use a separate drive. At runtime, `CONTENT_MACHINE_CACHE` controls cache/temp files; the default is `work/cache`. The full clean-install render was verified on Windows; Linux and macOS are not yet verified end to end.

## Configure paths

Leave an entry blank when the executable is already in `PATH`; otherwise set your own absolute path in `.env`:

```dotenv
FFMPEG_PATH=
FFPROBE_PATH=
NODE_PATH=
CHROME_PATH=
FONT_PATH=
CONTENT_MACHINE_CACHE=
```

Use `.venv/Scripts/python.exe` on Windows or `.venv/bin/python` on Unix for subsequent commands, or activate the virtual environment first.

## First job

```sh
python tools/content_machine.py prepare /path/to/video.mp4 \
  --job work/jobs/first-edit \
  --srt /path/to/transcript.srt \
  --prompt "Highlight the spoken process and keep the original voice."
```

The destination must be new. Preparation copies sanitized engine code into the job, links Node dependencies from the same clone, and normalizes a copy of the footage to 1920×1080 / 30 fps. Aspect ratio and the original file are preserved. Give the job to your agent and follow the [agent workflow](agent-workflow.md).

## Transcripts

- **SRT:** cue timings are known; word timings within each cue are estimates, marked in the job. Avoid cutting inside cues using these estimates.
- **Native JSON:** `--transcript file.json` accepts `segments[].words[]` containing `w`, `start`, and `end`. Use verified timings for precise word effects.
- **Optional local transcription:** install separately, then explicitly authorize the model download:

```sh
python -m pip install -r requirements-transcription.txt
python motore/shorts-pipeline/transcribe.py /path/to/video.mp4 --model small --download-model
```

Without `--download-model`, the transcriber uses local models only. Models are not shipped; check the selected model's own license.

On the tested Windows machine, application control blocked a CTranslate2 DLL with **WinError 4551**. Protections were not bypassed. Use the tested SRT/JSON path or an administrator-approved environment if your machine has the same restriction. Installing dependencies alone does not establish that transcription works.

## Fonts, models, and output

System fonts work by default. `FONT_PATH` or `prepare_fonts.py --font` can select a font you have permission to use; binaries remain local. The optional YuNet model is not bundled. Set `YUNET_MODEL_PATH` to enable face-aware portrait cropping; otherwise review the center/manual crop. See [shorts](SHORTS.md).

Job data belongs in ignored `work/`. Final long-form output: `work/jobs/NAME/export/video.mp4`. Full Remotion errors are saved in the job's `motore/video-gfx/build/render-error.log`. Default rendering concurrency is 2; `MOTORE_CONCURRENCY=1..16` changes it. A JSON handoff exiting with code **2** is waiting for your agent, not an API failure.

No agent login is stored in the project. Claude, Codex, or another agent uses its own account outside this clone. Review the separate [dependency licenses](../THIRD_PARTY_NOTICES.md), especially Remotion, before commercial distribution.
