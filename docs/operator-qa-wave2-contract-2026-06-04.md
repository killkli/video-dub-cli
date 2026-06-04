# Operator QA — Wave 2 Contract Check (2026-06-04)

**Date:** 2026-06-04  
**Branch:** `main`  
**HEAD at start:** `0d41a41` (`feat(cli): surface project/final/recovery paths in auto workflow [T14]`)

## Goal

QA the Wave 2 operator contract after T14 landed:

1. `dub auto --help`, `dub en2zh --help`, `dub ja2zh --help` remain truthful.
2. Common-path invocation behavior matches the implemented contract.
3. Project directory is discoverable without reading source.
4. Recovery path (`resume` / `status` / `validate`) is discoverable from CLI output.
5. Contract gaps are recorded as QA findings backed by real command output.

## Environment

- Repo: `/Users/johnchen/.hermes/projects/video-dub-cli`
- QA env builder: `tools/make_operator_qa_env.py`
- QA root: `/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa`
- Fixture video: `.tmp_operator_qa/test_short.mp4`
- Fake-backend seam used for this QA:
  - `DUB_ASR_TEST_FIXTURE_SRT=.tmp_operator_qa/fake-asr.srt`
  - `DUB_PIPELINE_SCRIPTS_DIR=.tmp_operator_qa/fake-skills`

## Commands executed

### 1. Build QA env

```bash
python3 tools/make_operator_qa_env.py
```

Result:

```text
/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa
```

### 2. Help-surface verification

```bash
uv run dub auto --help
uv run dub en2zh --help
uv run dub ja2zh --help
```

Observed contract:

- `dub auto` documents `--source-lang en|ja`
- all three commands document:
  - `Project directory (default: <video-stem>.dub/ next to the input video).`
- `en2zh` help says zero-flag invocation hard-codes `en→zh`
- `ja2zh` help says zero-flag invocation hard-codes `ja→zh`

## Pass findings

### PASS-1 — help text is truthful for the Wave 2 default-path contract

The help output for `auto`, `en2zh`, and `ja2zh` all explicitly states the `<video-stem>.dub/` default next to the input video.

### PASS-2 — recovery commands are now surfaced before expensive work

Real `en2zh` invocation prints the new T14 visibility block before preflight:

```text
run plan: project=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub final=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub/07_final/video_dubbed_stem.mp4
next: dub resume --project-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub
next: dub status --project-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub
next: dub validate --project-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub
```

This proves the operator can discover:

- project directory
- canonical final artifact path
- `resume`
- `status`
- `validate`

without reading source or docs.

## QA findings / contract gaps

### QF-1 — common-path `en2zh` fake-backend operator run is currently blocked by real OmniVoice readiness gate

Command executed:

```bash
env \
  DUB_ASR_TEST_FIXTURE_SRT=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/fake-asr.srt \
  DUB_PIPELINE_SCRIPTS_DIR=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/fake-skills \
  uv run dub en2zh /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.mp4 \
    --config /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/operator-config.yaml \
    --yes
```

Observed result:

```text
Error: preflight failed for source_lang=en project=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub — fix the following gate(s) and re-run, or run `dub doctor` for the full readiness report:
  - tts.omnivoice: missing: deps:omnivoice
```

Interpretation:

- T14 visibility contract is working.
- But the Wave 2 `en2zh` common path is **not QA-passable in the hermetic fake-backend operator env** anymore.
- The preflight gate now checks real OmniVoice importability before the fake wrapper path can exercise the rest of the pipeline.

### QF-2 — existing integration smoke `tests/integration/test_6d_operator_flow.py` is stale and now fails for the same reason

Command executed:

```bash
uv run pytest -q tests/integration/test_6d_operator_flow.py -m integration
```

Observed result:

```text
FAILED tests/integration/test_6d_operator_flow.py::test_6d_operator_flow
...
AssertionError: Error: preflight failed for source_lang=en project=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/op_proj_test — fix the following gate(s) and re-run, or run `dub doctor` for the full readiness report:
  - tts.omnivoice: missing: deps:omnivoice
```

Interpretation:

- This is a real regression in the fake-backend QA harness / contract, not a prose opinion.
- The previously-supported hermetic EN→ZH operator smoke no longer clears preflight.

### QF-3 — `doctor` truthfully reports lane readiness, but confirms only `ja2zh` is currently ready on this host

Command executed:

```bash
uv run dub doctor --config /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/operator-config.yaml
```

Observed lane summary:

```text
doctor lanes: ready=`dub ja2zh` ; blocked=`dub en2zh`
Error: doctor found missing prerequisites
```

Supporting backend evidence:

```text
omnivoice: BLOCKED (missing: deps:omnivoice)
voxcpme: READY (all gates ok)
```

Interpretation:

- `doctor` is now more truthful than the earlier generic wording.
- On this host + QA env, the supported lane is currently `ja2zh`, not `en2zh`.

### QF-4 — `ja2zh` clears preflight but still fails later because the fake VoxCPM path is no longer audio-contract-compatible

Command executed:

```bash
env \
  DUB_ASR_TEST_FIXTURE_SRT=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/fake-asr.srt \
  DUB_PIPELINE_SCRIPTS_DIR=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/fake-skills \
  uv run dub ja2zh /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.mp4 \
    --config /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/operator-config.yaml \
    --yes
```

Observed result:

- preflight succeeded
- pipeline reached `05_tts`
- stage failed

From `.tmp_operator_qa/test_short.dub/.dub/05_tts.log`:

```text
CMD: /Users/johnchen/.hermes/projects/video-dub-cli/.venv/bin/python3 /Users/johnchen/.hermes/projects/video-dub-cli/src/dub/tts_engines/voxcpme/runner.py --project-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub --zh-srt /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub/05_translated_srt/video.zhtw.srt --ja-srt /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub/03_asr/video.srt --ref-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub/04_ref_audio --out-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub/06_tts_wav
...
[1/1] line_1 FAIL: Audio denoising processing failed: Error opening <_io.BytesIO object at 0x1726dd440>: Error in WAV file. No 'data' chunk marker.
```

Interpretation:

- The fake ref-audio fixtures written by the QA harness are no longer sufficient for the current VoxCPM route.
- The route is wired, but the hermetic fake backend is stale relative to the new stage-05 audio expectations.

### QF-5 — `validate` can return `ok` on a project that never passed preflight and has no state

After the failed `en2zh` run above:

```bash
uv run dub status --project-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub
uv run dub validate --project-dir /Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub
```

Observed outputs:

```text
status: project=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub (no state)
```

```text
validate ok: project=/Users/johnchen/.hermes/projects/video-dub-cli/.tmp_operator_qa/test_short.dub stages=0 mode=unknown
```

Filesystem evidence shows the partially-created project contains only pre-stage artifacts and no final output:

- `01_raw_video/video.mp4`
- `02_stems/instrumental.wav`
- `02_stems/vocals.wav`
- `03_asr/video.srt`
- `04_ref_audio/line_1_ref.wav`
- `04_ref_audio/line_2_ref.wav`
- `05_translate/video.zhtw.srt`
- `05_translated_srt/video.zhtw.srt`
- `.dub/state.json`
- `.dub/05_tts.log`
- **no `07_final/video_dubbed_stem.mp4`**

Interpretation:

- `validate ok:` is currently too permissive for a preflight-failed or stage-failed project.
- This is an operator-truthfulness bug: `validate` sounds green even though the project is not actually deliverable.

## QA conclusion

**Wave 2 is only partially verified.**

What is verified:

1. help text is truthful for the `<video-stem>.dub/` default
2. T14 visibility improvement works: project/final/recovery paths are printed up front
3. `doctor` now truthfully reports lane-level readiness

What is **not** yet verified as passing:

1. hermetic `en2zh` common-path smoke
2. hermetic `ja2zh` common-path smoke through stage 05
3. `status` / `validate` truthfulness on failed / partial projects

## Recommended next actions

1. Fix the fake-backend QA harness so the supported EN→ZH hermetic flow can satisfy OmniVoice preflight, or explicitly exempt the test-only seam from the real import gate.
2. Update `tests/integration/test_6d_operator_flow.py` in the same wave so it matches the real supported QA contract.
3. Repair the fake VoxCPM fixtures / fake wrapper so stage 05 emits WAVs that satisfy the current downstream audio contract.
4. Tighten `validate` so a partial / failed project cannot print `validate ok:` when final deliverables are absent.
5. Only after those fixes, update docs/user-facing wording in T16.
