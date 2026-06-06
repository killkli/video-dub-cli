# Canonical Operator QA — Supported Single-Command Flow

> **Historical QA snapshot.** This file records a 2026-06-03 operator QA pass during the standalone feature-branch wave.
> Keep it as evidence of what was verified then; do not read its branch/runtime checkpoint lines as the current repo state.

**Date:** 2026-06-03  
**Branch at that time:** `feature/standalone-repo-uv`  
**Runtime checkpoint:** after `2a6bc06 feat(cli): tighten preflight and completion UX`

## Goal / supported scenario

This QA pass verifies the narrowest truthful operator-facing claim for the current CLI:

- a **single operator command** can complete end to end
- using the **repo-contained standalone runtime contract**
- on the **fake-backend operator QA environment**
- for **English → Chinese** with `translate-mode=delegate`

This pass verifies:
- CLI wiring
- stage orchestration
- project state persistence
- route selection
- canonical artifact creation
- `status` / `validate` operator surfaces
- final media artifact structural shape

This pass does **not** verify:
- real ASR quality
- real Gemini translation quality/cost/latency
- real OmniVoice / VoxCPM model quality
- production ML dependency stability

## Environment

- Repo: `/Users/johnchen/.hermes/projects/video-dub-cli`
- QA env builder: `tools/make_operator_qa_env.py`
- QA root: `.tmp_operator_qa/`
- Project used in this run: `.tmp_operator_qa/op_proj_canonical_qa`
- Fake runtime seam:
  - `DUB_ASR_TEST_FIXTURE_SRT=.tmp_operator_qa/fake-asr.srt`
  - `DUB_PIPELINE_SCRIPTS_DIR=.tmp_operator_qa/fake-skills`

These overrides are **test-only**. Normal operators should use the repo default runtime assets under `vendor/pipeline_scripts`.

## Exact commands used

### 1. Build the hermetic QA environment

```bash
python tools/make_operator_qa_env.py
```

### 2. Fresh end-to-end run

```bash
export DUB_ASR_TEST_FIXTURE_SRT=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/fake-asr.srt
export DUB_PIPELINE_SCRIPTS_DIR=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/fake-skills

dub en2zh \
  /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.mp4 \
  --project-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_canonical_qa \
  --config /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/operator-config.yaml \
  --yes
```

### 3. Operator follow-up commands

```bash
dub status --project-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_canonical_qa
dub validate --project-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_canonical_qa
ffprobe -v error -show_entries format=duration,size -of json /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_canonical_qa/07_final/video_dubbed_stem.mp4
```

## `run` output excerpt

```text
preflight: src=en tgt=zh project=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_canonical_qa mode=delegate route=translate=delegate provider=mock
[01_stems] done
[02_asr] done
[03_ref_audio] done
[04_translate] done
[05_tts] done
[06_assemble] done
run complete: project=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_canonical_qa final=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_canonical_qa/07_final/video_dubbed_stem.mp4
next: dub status --project-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_canonical_qa
next: dub validate --project-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_canonical_qa
```

## `status` output

```text
01_stems: done attempts=1
02_asr: done attempts=1
03_ref_audio: done attempts=1
04_translate: done attempts=1
05_tts: done attempts=1
06_assemble: done attempts=1
```

## `validate` output

```text
validate ok: project=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_canonical_qa stages=6 mode=delegate translate_status=done
```

## Final artifact probe

```json
{
  "format": {
    "duration": "30.000000",
    "size": "419255"
  }
}
```

Interpretation:
- final canonical artifact exists
- duration is structurally valid (`30.000000` seconds)
- file size is non-trivial (`419255` bytes)

## Artifact list produced

### Canonical project artifacts
- `03_asr/video.srt`
- `04_ref_audio/line_1_ref.wav`
- `04_ref_audio/line_2_ref.wav`
- `05_translated_srt/video.zhtw.srt`
- `06_tts_wav/line_1_tts.wav`
- `07_final/video_dubbed_stem.mp4`

### Compatibility / secondary artifacts
- `07_final/video_dubbed.mp4`

## State evidence

From `.dub/state.json`:
- `input.source_lang = "en"`
- `input.target_lang = "zh"`
- `input.translate_mode = "delegate"`
- all six stages recorded `status = "done"`
- `06_assemble.artifacts` contains:
  - `video_dubbed_stem.mp4`
  - `video_dubbed.mp4`

This proves the run did not merely exit 0; it persisted the intended route and stage completion state.

## Route evidence from logs

From `.dub/05_tts.log`:

```text
CMD: /usr/bin/python3 /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/fake-skills/dubbing_batch_tts.py --zh-srt /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_canonical_qa/05_translated_srt/video.zhtw.srt --en-srt /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_canonical_qa/03_asr/video.srt --ref-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_canonical_qa/04_ref_audio --out-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_canonical_qa/06_tts_wav
```

This confirms:
- delegate route selected the expected **English TTS wrapper contract**
- the canonical translated subtitle path was used
- the fake wrapper came from the shared test-only seam `DUB_PIPELINE_SCRIPTS_DIR`

## What can now be claimed

The project can truthfully claim the following:

1. `dub en2zh` is a valid single-command operator entrypoint for the supported contract.
2. The standalone repo-contained runtime works end to end without external clone-time path dependencies.
3. `dub status` and `dub validate` are viable operator follow-up commands after a run.
4. The CLI now prints a clearer preflight route summary:
   - source language
   - target language
   - project path
   - translate mode
   - provider / route detail
5. The CLI now prints a more useful completion summary:
   - canonical final output path
   - suggested `status` command
   - suggested `validate` command

## What must not be over-claimed

Do **not** claim any of the following from this QA pass:

1. Real ASR quality is production-verified.
2. Real Gemini translation quality/cost/latency is production-verified.
3. Real OmniVoice or VoxCPM synthesis quality is production-verified.
4. The fake-backend operator QA flow proves anything about real ML dependency installation pain.
5. This note proves every language pair or every translate mode is production-ready.

## Suggested handoff / next steps

1. Keep this note as the canonical support-boundary reference for the current single-command flow.
2. If the supported scenario expands beyond fake backends, add a second QA note clearly separated as **real-backend verification**.
3. If release packaging is the next milestone, link this note from README / QUICKSTART as the current proof artifact.
4. If future CLI UX changes alter preflight or completion wording, update this note and the matching test assertions in the same wave.
