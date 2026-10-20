# Native renderer example

[`native-showcase.json`](native-showcase.json) is an 18-second synthetic plan using the engine's actual `card`, `flow`, and `cta` components. All text is demonstration copy. No statistics, customer footage, voice, or external stock is used.

The README GIF was rendered from this plan over a dark generated grid, cropped around the graphic area, then encoded as an animated preview. It demonstrates the native components and timing, not automated editorial decisions or speech recognition. The GIF is silent; full MP4/audio export is a separate pipeline step.

## Try the plan locally

After installation, use the project's Python environment:

```sh
python tools/demo.py
python tools/content_machine.py prepare work/demo-input/demo.mp4 \
  --job work/jobs/showcase \
  --srt work/demo-input/demo.srt \
  --prompt "Use the supplied synthetic component demonstration plan."
```

Copy the example into the job. On PowerShell:

```powershell
Copy-Item examples/native-showcase.json work/jobs/showcase/motore/video-gfx/src/data/regia.json
```

On Unix:

```sh
cp examples/native-showcase.json work/jobs/showcase/motore/video-gfx/src/data/regia.json
```

Validate, inspect, and render:

```sh
python work/jobs/showcase/motore/orchestratore/valida_canone.py \
  --regia work/jobs/showcase/motore/video-gfx/src/data/regia.json --durata 18
python work/jobs/showcase/motore/video-gfx/render_regia.py --contatti
python tools/content_machine.py render-long --job work/jobs/showcase
```

`tools/demo.py` generates a moving technical test pattern and a descriptive SRT, not spoken footage. This is a reproducible input with no model download. For the dark README background, the source was generated with this FFmpeg video filter instead:

```text
color=c=0x111820:s=1920x1080:r=30
drawgrid=w=120:h=120:t=1:c=white@0.05,noise=alls=1:allf=t
```

Native inputs and outputs remain under `work/`. Change the job name rather than overwriting an existing job. Your own footage can replace the synthetic source, but the plan must be adapted to its duration, meaning, and transcript timings.
