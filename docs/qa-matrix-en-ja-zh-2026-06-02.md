# QA Matrix — EN/JA → ZH Operator Test Scenarios

**Date:** 2026-06-02
**Scope:** Contract 2 (artifact contract) + Contract 3 (failure-recovery contract) from `docs/plans/2026-06-02-phase4-productization-gate.md`
**References:**
- Operator QA record: `docs/operator-qa-supported-flow-2026-06-02.md`
- Release handoff checklist: `docs/release-handoff-checklist.md`
- State model: `src/dub/state.py` — `STAGE_NAMES = ["01_stems","02_asr","03_ref_audio","04_translate","05_tts","06_assemble"]`
- Config: `src/dub/config.py` — `TranslationConfig.mode ∈ {delegate, skip, use-existing}`

---

## Tier Definitions

| Tier | Purpose | When to run | Entry point |
|------|---------|-------------|-------------|
| **Smoke** | Verify CLI contract + stage wiring with fake backends | Every commit | `pytest tests/integration/test_6e_route_scenarios.py -q` |
| **Targeted** | Verify specific failure-recovery + edge cases | Before release | `pytest tests/ -k "fail_fast or recovery or resumab" -q` |
| **Full regression** | All unit + integration tests | Before merge | `pytest tests/ -q` |

---

## Matrix — Supported Scenarios

### Row 1: EN→ZH, delegate (fresh run)

**CLI invocation:**
```bash
dub run tests/fixtures/test_short.mp4 \
  --source-lang en \
  --target-lang zh \
  --project-dir /tmp/qa-row1-en-delegate \
  --config <fake-backend-config> \
  --yes
```

**State assertion:**
```
state.stages['01_stems'].status    == 'done'
state.stages['02_asr'].status      == 'done'
state.stages['03_ref_audio'].status == 'done'
state.stages['04_translate'].status == 'done'
state.stages['05_tts'].status      == 'done'
state.stages['06_assemble'].status  == 'done'
state.input['source_lang']         == 'en'
state.input['target_lang']         == 'zh'
state.input['translate_mode']      == 'delegate'
```

**Artifact assertions:**
- `01_raw_video/video.mp4` exists
- `02_stems/vocals.wav` exists
- `02_stems/instrumental.wav` exists
- `03_asr/video.srt` exists
- `04_ref_audio/line_1_ref.wav` exists
- `05_translated_srt/video.zhtw.srt` exists (canonical)
- `05_translate/video.zhtw.srt` exists (legacy sync)
- `06_tts_wav/line_1_tts.wav` exists, size > 1000 bytes
- `06_tts_wav/tts_normalized.wav` exists, size > 1000 bytes
- `07_final/video_dubbed_stem.mp4` exists

**ffprobe assertion:**
```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 \
  07_final/video_dubbed_stem.mp4
# Returns non-empty numeric string (e.g. "30.000000")
```

**validate assertion:**
```bash
dub validate --project-dir /tmp/qa-row1-en-delegate
# Exit code 0, output contains: "mode=delegate translate_status=done"
```

**Log evidence:**
- `.dub/05_tts.log` contains `--zh-srt` and `--en-srt` (OmniVoice contract)
- `.dub/06_assemble_remix.log` or `.dub/06_assemble_step1_tts.log` exists

**Regression entry point:**
```bash
pytest tests/integration/test_6e_route_scenarios.py::test_6e_delegate_fresh_run_records_translated_subtitle_contract -q
```

---

### Row 2: EN→ZH, use-existing (fresh run with external SRT)

**CLI invocation:**
```bash
dub run tests/fixtures/test_short.mp4 \
  --source-lang en \
  --target-lang zh \
  --project-dir /tmp/qa-row2-en-use-existing \
  --config <fake-backend-config> \
  --translate-mode use-existing \
  --translated-srt /path/to/external.zhtw.srt \
  --yes
```

Where `/path/to/external.zhtw.srt` contains at least one SRT cue.

**State assertion:**
```
state.input['translate_mode']      == 'use-existing'
state.input['translated_srt']      == '/path/to/external.zhtw.srt'
state.stages['04_translate'].status == 'done'
```

**Artifact assertions:**
- `05_translated_srt/video.zhtw.srt` exists, contents == external SRT contents
- `05_translate/video.zhtw.srt` exists, contents == external SRT contents
- All other artifact paths same as Row 1

**ffprobe assertion:** Same as Row 1.

**validate assertion:**
```bash
dub validate --project-dir /tmp/qa-row2-en-use-existing
# Exit code 0, output contains: "mode=use-existing translate_status=done"
```

**Log evidence:**
- `.dub/05_tts.log` contains `--zh-srt` pointing at `05_translated_srt/video.zhtw.srt`

**Regression entry point:**
```bash
pytest tests/integration/test_6e_route_scenarios.py::test_6e_use_existing_fresh_run_copies_external_srt_into_project -q
```

---

### Row 3: EN→ZH, skip (resume on existing project)

**CLI invocation (two-step):**
```bash
# Step 1: initial delegate run
dub run tests/fixtures/test_short.mp4 \
  --source-lang en --target-lang zh \
  --project-dir /tmp/qa-row3-en-skip \
  --config <fake-backend-config> \
  --yes

# Step 2: delete downstream, re-run with skip
rm -rf /tmp/qa-row3-en-skip/06_tts_wav
mkdir -p /tmp/qa-row3-en-skip/06_tts_wav

dub run tests/fixtures/test_short.mp4 \
  --source-lang en --target-lang zh \
  --project-dir /tmp/qa-row3-en-skip \
  --config <fake-backend-config> \
  --translate-mode skip \
  --yes
```

**State assertion:**
```
state.input['translate_mode']      == 'skip'
state.stages['04_translate'].status == 'done' | 'skipped'
```

**Artifact assertions:**
- `05_translated_srt/video.zhtw.srt` exists, contents UNCHANGED from step 1
- `06_tts_wav/line_1_tts.wav` exists (re-built by step 2)
- `07_final/video_dubbed_stem.mp4` exists

**ffprobe assertion:** Same as Row 1.

**validate assertion:**
```bash
dub validate --project-dir /tmp/qa-row3-en-skip
# Exit code 0, output contains: "mode=skip translate_status=skipped"
```

**Log evidence:**
- Preflight line contains: `route=translate=skip existing_project_srt=...05_translated_srt/video.zhtw.srt`

**Regression entry point:**
```bash
pytest tests/integration/test_6e_route_scenarios.py::test_6e_skip_resume_reuses_existing_project_translated_subtitle -q
```

---

### Row 4: JA→ZH, delegate (fresh run)

**CLI invocation:**
```bash
dub run tests/fixtures/test_short.mp4 \
  --source-lang ja \
  --target-lang zh \
  --project-dir /tmp/qa-row4-ja-delegate \
  --config <fake-backend-config> \
  --yes
```

**State assertion:**
```
state.input['source_lang']         == 'ja'
state.input['target_lang']         == 'zh'
state.input['translate_mode']      == 'delegate'
state.stages['04_translate'].status == 'done'
state.stages['05_tts'].status      == 'done'
state.stages['06_assemble'].status  == 'done'
```

**Artifact assertions:**
- `03_asr/video.srt` exists (source-language subtitles from ASR)
- `05_translated_srt/video.zhtw.srt` exists
- `06_tts_wav/line_1_tts.wav` exists, size > 1000 bytes
- `07_final/video_dubbed_stem.mp4` exists

**ffprobe assertion:** Same as Row 1.

**validate assertion:**
```bash
dub validate --project-dir /tmp/qa-row4-ja-delegate
# Exit code 0, output contains: "mode=delegate translate_status=done"
```

**Log evidence:**
- `.dub/05_tts.log` contains `--ja-srt` and `--project-dir` (VoxCPM script contract)
- `.dub/05_tts.log` contains the path to `03_asr/video.srt` as ref_text source

**Regression entry point:**
```bash
pytest tests/integration/test_6e_route_scenarios.py::test_6e_ja_route_uses_vox_script_contract -q
```

---

### Row 5: JA→ZH, use-existing (fresh run with external SRT)

**CLI invocation:**
```bash
dub run tests/fixtures/test_short.mp4 \
  --source-lang ja \
  --target-lang zh \
  --project-dir /tmp/qa-row5-ja-use-existing \
  --config <fake-backend-config> \
  --translate-mode use-existing \
  --translated-srt /path/to/external.zhtw.srt \
  --yes
```

**State assertion:**
```
state.input['source_lang']         == 'ja'
state.input['translate_mode']      == 'use-existing'
state.input['translated_srt']      == '/path/to/external.zhtw.srt'
state.stages['04_translate'].status == 'done'
```

**Artifact assertions:**
- `05_translated_srt/video.zhtw.srt` exists, contents == external SRT contents
- `05_translate/video.zhtw.srt` exists (legacy sync)
- `06_tts_wav/line_1_tts.wav` exists
- `07_final/video_dubbed_stem.mp4` exists

**ffprobe assertion:** Same as Row 1.

**validate assertion:**
```bash
dub validate --project-dir /tmp/qa-row5-ja-use-existing
# Exit code 0, output contains: "mode=use-existing translate_status=done"
```

**Log evidence:**
- `.dub/05_tts.log` contains `--ja-srt` (ja route TTS script contract)

**Regression entry point:**
```bash
pytest tests/integration/test_6e_route_scenarios.py -k "use_existing" -q
```

> **Note:** There is currently no dedicated `test_6e_ja_use_existing` test. The en→zh use-existing test (`test_6e_use_existing_fresh_run_copies_external_srt_into_project`) covers the core contract; the ja source_lang dimension is orthogonal. A dedicated test should be added if ja→zh use-existing is a distinct operator workflow.

---

## Failure-Recovery Scenarios

### FR-1: use-existing without --translated-srt → fail fast

**CLI invocation:**
```bash
dub run tests/fixtures/test_short.mp4 \
  --project-dir /tmp/qa-fr1 \
  --config <fake-backend-config> \
  --translate-mode use-existing \
  --yes
# Note: --translated-srt is omitted
```

**Expected behavior:** `dub run` exits non-zero immediately, before any stage starts.

**Exact message (snapshot):**
```
translate-mode=use-existing requires --translated-srt
```

**Regression entry point:**
```bash
pytest tests/test_cli.py::test_dub_run_use_existing_requires_translated_srt -q
```

---

### FR-2: use-existing with non-existent --translated-srt → fail fast

**CLI invocation:**
```bash
dub run tests/fixtures/test_short.mp4 \
  --project-dir /tmp/qa-fr2 \
  --config <fake-backend-config> \
  --translate-mode use-existing \
  --translated-srt /nonexistent/path.srt \
  --yes
```

**Expected behavior:** `dub run` exits non-zero immediately.

**Exact message (snapshot):**
```
translated SRT not found: /nonexistent/path.srt
```

**Regression entry point:**
```bash
pytest tests/test_cli.py::test_dub_run_use_existing_requires_translated_srt -q
# Note: this test covers the missing-flag case; a dedicated non-existent-path test
# should be added to test_cli.py for full snapshot coverage.
```

---

### FR-3: skip on fresh project → fail fast

**CLI invocation:**
```bash
dub run tests/fixtures/test_short.mp4 \
  --project-dir /tmp/qa-fr3 \
  --config <fake-backend-config> \
  --translate-mode skip \
  --yes
# Note: project_dir has no 05_translated_srt/video.zhtw.srt
```

**Expected behavior:** `dub run` exits non-zero immediately, before any stage starts.

**Exact message (snapshot):**
```
translate-mode=skip requires an existing translated subtitle at <project_dir>/05_translated_srt/video.zhtw.srt
```

**Regression entry point:**
```bash
pytest tests/test_cli.py::test_dub_run_skip_requires_existing_project_translated_srt -q
```

---

### FR-4: Stage 5 (TTS) OOM / partial failure → resume re-enters from stage 5

**Scenario:** The TTS stage fails mid-run (e.g. OOM kills the subprocess). The pipeline halts with `state.stages['05_tts'].status == 'failed'`. Running `dub resume` must re-enter at stage 5 and complete successfully.

**Reproduction steps:**
```bash
# 1. Run normally until stage 5 fails (simulate by killing)
# 2. Verify state:
dub status --project-dir /tmp/qa-fr4
# 05_tts: failed attempts=1

# 3. Resume
dub resume --project-dir /tmp/qa-fr4
# Stage 5 re-enters, completes, stages 5+6 run to done
```

**State assertion after resume:**
```
state.stages['05_tts'].status      == 'done'
state.stages['06_assemble'].status  == 'done'
state.stages['05_tts'].attempts     >= 2  (1 failed + 1 successful)
```

**Artifact assertion after resume:**
- `06_tts_wav/line_1_tts.wav` exists, size > 1000 bytes
- `07_final/video_dubbed_stem.mp4` exists

**Regression entry point:**
```bash
pytest tests/test_tts_stage_resumability.py -q
pytest tests/integration/test_6b_resume.py -q
```

---

### FR-5: Stage 6 (assemble) ffprobe failure → clean --stage 6 + resume

**Scenario:** The assemble stage fails (e.g. ffprobe reports corrupt output or the subprocess crashes). Operator cleans stage 6 artifacts and resumes.

**Reproduction steps:**
```bash
# 1. After stage 6 failure:
dub status --project-dir /tmp/qa-fr5
# 06_assemble: failed attempts=1

# 2. Clean only stage 6 artifacts
dub clean --project-dir /tmp/qa-fr5 --stage 6

# 3. Resume
dub resume --project-dir /tmp/qa-fr5
# Stage 6 re-runs, completes
```

**State assertion after resume:**
```
state.stages['06_assemble'].status == 'done'
```

**Artifact assertion:**
- `07_final/video_dubbed_stem.mp4` exists after clean (07_final/ is empty), then re-created by resume
- `01_raw_video/video.mp4` still exists (clean --stage 6 never removes it)

**Regression entry point:**
```bash
pytest tests/integration/test_6b_resume.py -q
# Note: a dedicated "clean --stage N + resume" test should be added for
# full snapshot coverage of this exact operator workflow.
```

---

## Per-Line TTS Recovery (22/32 bug fix)

The TTS stage includes built-in per-line recovery. If the initial TTS run produces partial artifacts (missing or undersized `line_<i>_tts.wav`), the stage automatically re-invokes the TTS script scoped to each missing cue via `--start N --end N`.

**Regression entry point:**
```bash
pytest tests/test_tts_stage_resumability.py::test_stage_recovers_from_22_of_32_partial_artifact_failure -q
pytest tests/test_tts_stage_resumability.py::test_stage_recovers_from_22_of_32_with_files_truly_absent -q
```

---

## Evidence Summary Table

| Scenario | Source | Mode | Key artifact | validate output | Regression test |
|----------|--------|------|-------------|-----------------|-----------------|
| Row 1 | en | delegate | `05_translated_srt/video.zhtw.srt` | `mode=delegate translate_status=done` | `test_6e_delegate_fresh_run` |
| Row 2 | en | use-existing | `05_translated_srt/video.zhtw.srt` == external | `mode=use-existing translate_status=done` | `test_6e_use_existing` |
| Row 3 | en | skip | `05_translated_srt/video.zhtw.srt` unchanged | `mode=skip translate_status=skipped` | `test_6e_skip_resume` |
| Row 4 | ja | delegate | `05_translated_srt/video.zhtw.srt` + `.dub/05_tts.log` has `--ja-srt` | `mode=delegate translate_status=done` | `test_6e_ja_route` |
| Row 5 | ja | use-existing | `05_translated_srt/video.zhtw.srt` == external | `mode=use-existing translate_status=done` | `test_6e_use_existing` (en test covers contract) |
| FR-1 | any | use-existing (no path) | N/A (fail fast) | N/A | `test_dub_run_use_existing_requires_translated_srt` |
| FR-2 | any | use-existing (bad path) | N/A (fail fast) | N/A | *(snapshot test needed)* |
| FR-3 | any | skip (fresh project) | N/A (fail fast) | N/A | `test_dub_run_skip_requires_existing_project_translated_srt` |
| FR-4 | any | delegate | `06_tts_wav/` rebuilt by resume | N/A | `test_tts_stage_resumability` |
| FR-5 | any | delegate | `07_final/` rebuilt after clean+resume | N/A | `test_6b_resume` |

---

## Smoke Test Entry Point (one command to rule them all)

```bash
# Run all route scenario integration tests (Rows 1-4) + CLI contract tests (FR-1, FR-3)
pytest tests/integration/test_6e_route_scenarios.py tests/test_cli.py -q
```

This single command covers Rows 1-4, FR-1, FR-3, and the basic CLI contract. It is the minimum gate for any change that touches the CLI, stages, or config.

---

## Gaps (known, not covered by existing tests)

1. **FR-2 snapshot test** — `test_cli.py` covers FR-1 (missing flag) but not FR-2 (non-existent path). A dedicated test should assert exact error message `translated SRT not found: <path>`.
2. **Row 5 (ja→zh use-existing) dedicated test** — The en→zh use-existing test covers the core contract; ja source_lang is orthogonal. Add a dedicated integration test if ja→zh use-existing is a distinct operator workflow.
3. **FR-5 (clean --stage 6 + resume) dedicated test** — The resume test suite covers re-entry but not the specific clean-then-resume operator pattern. Add if this is a common operator recovery flow.
4. **Real backend verification** — All matrix rows above use fake backends. Real backend QA is explicitly out of scope for P4 (see `docs/plans/2026-06-02-phase4-productization-gate.md`, "Known non-productized gaps").
