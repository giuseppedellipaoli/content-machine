# Selecting highlights

Read the native transcript export (`build/<video>.for_llm.txt`) with the assistant of your choice. Selection is editorial work, not a hidden service in the pipeline. No account or API key is required by the renderer.

Write a JSON object with a `highlights` array. Each entry uses the exact inclusive segment indices in the transcript:

```json
{
  "highlights": [
    {
      "title": "A complete idea",
      "seg_start_idx": 0,
      "seg_end_idx": 4,
      "score": 80,
      "hook_sentence": "An opening supported by the transcript",
      "virality_reason": "A clear and useful explanation"
    }
  ]
}
```

Keep each idea understandable without the surrounding recording. Do not invent quotes, facts or timestamps. The renderer resolves indices against the actual transcript, applies safe start/end padding, rejects clips shorter than the configured minimum and removes overlapping duplicate proposals. `score` ranks duplicate proposals; it is an editorial preference rather than a prediction of performance.

Review `build/scarti.json` for rejected selections. Exact word cuts and manual crop adjustments use the native `tagli.json` and `correzioni.json` schemas documented in their Python modules.
