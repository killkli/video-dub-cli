# Batched-Assembler Canonical Fake-Backend QA (2026-06-04)

## Scope

This QA closes the gap between "batched assembler is wired through
`dub doctor` / unit tests" and "batched assembler path is exercised
end-to-end on a fake backend". It uses the existing
`.tmp_operator_qa/` fake-skill harness plus a brand-new fake
`assemble_tts_batched.py` stand-in that mimics the real binary's
step-1 contract.

The flag under test is `defaults.use_batched_assembler: bool = False`
(default) vs `True` (this run).

## Inputs

- `tests/fixtures/test_short.mp4` (30s sample)
- fake ASR fixture: `/tmp/_fixture.srt` (2 lines, English)
  - fed in via `DUB_ASR_TEST_FIXTURE_SRT=/tmp/_fixture.srt`
- config: `.tmp_batched_qa.yaml` (vendored in `.tmp_*`, not committed)
  - `defaults.use_batched_assembler: true`
  - `defaults.tts_batch_size: 30`
  - `translation.provider: mock`
- alias entrypoint: `dub en2zh`

## Command

```bash
DUB_ASR_TEST_FIXTURE_SRT=/tmp/_fixture.srt \
  uv run dub en2zh /tmp/_short.mp4 \
    --project-dir .tmp_batched_runs/20260604_122849 \
    --config .tmp_batched_qa.yaml \
    --yes
```

## Observed result

All six stages reported `done`:

```text
01_stems:    done attempts=1
02_asr:      done attempts=1
03_ref_audio:done attempts=1
04_translate:done attempts=1
05_tts:      done attempts=1
06_assemble: done attempts=1
```

`dub validate` returned:

```text
validate ok: project=.../20260604_122849 stages=6 mode=delegate translate_status=done
```

Final artifact:

- path: `07_final/video_dubbed_stem.mp4`
- duration: `30.000000`
- size: `190652` bytes

## Step-1 evidence (batched assembler really executed)

The step-1 log proves the batched path was actually invoked (not the
legacy `dubbing_assemble_loudnorm.py`):

```text
SRT entries: 1
valid clips: 1
video dur: 30.00s
batch size: 30 clips/batch
  batch 00 (1 clips) ...
mixing 1 batches ...
loudnorm ...
  measured I=-12.02 LRA=16.60 tp=-2.72 thresh=-23.38
saved normalized WAV: .../06_tts_wav/tts_normalized.wav
OK: .../.dub/vdub_fulltrack_3vgjfhpo.mp4 (0 MB), dur=30.00s
DONE: .../.dub/vdub_fulltrack_3vgjfhpo.mp4
```

The legacy loudnorm builder would have produced a different argv and
log shape — this output matches the batched binary's own
`pf()` print sequence.

## State evidence

`stages.06_assemble` from `.dub/state.json`:

```json
{
  "status": "done",
  "artifacts": ["video_dubbed_stem.mp4", "video_dubbed.mp4"],
  "output_dir": "07_final",
  "attempts": 1
}
```

## What this run proves

- The CLI config knob `defaults.use_batched_assembler=True` is
  propagated into the assemble stage and selects the batched script
  path (`assemble_tts_batched.py`).
- `--batch-size <int>` is forwarded to the batched script (verified
  by fake binary's stdout: `batch size: 30 clips/batch`).
- The 30-batch routing + loudnorm + remix contract works in fake
  mode, matching what the real binary will do on actual TTS wavs.
- `dub status` / `dub validate` agree on the artifact set
  (`video_dubbed_stem.mp4` + `video_dubbed.mp4`).
- `ffprobe` reads the final mp4; duration and size are non-zero.

## What this run does NOT prove

- It does not exercise the real `assemble_tts_batched.py` (only the
  fake stand-in that mirrors its CLI / file contract).
- The 60+ clip scaling concern that motivated the batched path is
  not exercised here; this run has 1 valid clip and 1 batch.
- Real-media audio quality and final-mp4 loudnorm correctness
  remain gated by the real-backend `operator-qa-real-backend-*-2026-06-03.md`
  records.

## Follow-up

- Promote the fake `assemble_tts_batched.py` to `tools/fake_skills/`
  so future regression runs can re-use it.
- Add a real `assemble_tts_batched.py` end-to-end test on a
  60+ clip long-form video (next wave, not this one).
