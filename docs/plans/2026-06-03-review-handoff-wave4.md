# video-dub-cli Review Handoff — Standalone Repo Wave 4

**Date:** 2026-06-03
**Branch:** `feature/standalone-repo-uv`
**Checkpoint commit:** `3feee15 test/integration: restore repo-contained harness`

---

## What was completed in this wave

This wave closed the repo-contained regression gap after the runtime-path consolidation.

### Delivered
- Restored hermetic integration coverage for repo-owned runtime paths
- Unified test-only runtime overrides across stages
- Extended runtime override coverage to TTS adapters, not just stage scripts
- Repaired stale integration fixtures that still assumed legacy `skills_dir` / fake CLI wiring
- Rebased the idempotency integration test onto the *current* recovery contract

### Key code changes
- `src/dub/runtime_paths.py`
  - Added `DUB_PIPELINE_SCRIPTS_DIR` override
  - Production default remains repo-owned `vendor/pipeline_scripts`
- `src/dub/tts_engines/omnivoice/__init__.py`
  - TTS wrapper resolution now goes through `runtime_paths.pipeline_scripts_dir()`
- `src/dub/tts_engines/voxcpme/__init__.py`
  - Same runtime-path override behavior as OmniVoice
- `tests/integration/conftest.py`
  - Rebuilt fake ASR/TTS/ref/remix/loudnorm fixture harness for repo-contained testing
- `tests/integration/test_6a_smoke.py`
- `tests/integration/test_6b_resume.py`
- `tests/integration/test_6c_idempotency.py`
- `tests/integration/test_6d_operator_flow.py`
- `tests/integration/test_6e_route_scenarios.py`
  - All updated to inject repo-contained test env overrides explicitly
- `tools/make_operator_qa_env.py`
  - Emits fake ASR fixture for operator QA environment

---

## Root causes fixed

### 1. Runtime-path drift
Earlier consolidation moved `stems`, `ref_audio`, and `assemble` to repo-owned script lookup, but TTS adapter resolution still pointed directly at repo vendored wrappers without honoring the test harness override. This caused integration tests to invoke real TTS wrappers and fail on missing heavy deps.

### 2. Integration harness stale assumptions
The test harness still encoded the pre-consolidation world:
- fake CLI placeholders
- fake script directory assumptions that no longer affected the product path
- outdated operator QA env wiring

### 3. Over-strict idempotency assertion
`test_6c_idempotency` assumed unaffected ref-audio files must keep identical mtimes after resume. That is no longer guaranteed by the current `RefAudioStage` contract, which may rebuild the stage when artifacts are incomplete. The test now checks recovery validity instead of obsolete implementation detail.

---

## Verification executed

### Targeted integration recovery batch
Command:
```bash
uv run pytest tests/integration/test_6a_smoke.py \
  tests/integration/test_6b_resume.py \
  tests/integration/test_6c_idempotency.py \
  tests/integration/test_6d_operator_flow.py \
  tests/integration/test_6e_route_scenarios.py -q
```

Result:
- `8 passed`

### Full regression
Command:
```bash
uv run pytest -q
```

Result:
- `170 passed in 125.12s`

---

## Current product truth after this wave

### Stable now
- Repo-owned pipeline-script lookup is the primary runtime contract
- TTS adapters respect the same runtime override channel as other repo-owned wrappers
- Integration suite can exercise EN/JA→ZH routing hermetically with fake backends
- Resume/recovery behavior is verified against the current stage semantics

### Still intentionally incomplete / non-productized
- Heavy runtime backends are still script-wrapper based, not fully in-process
- Operator-facing one-shot UX is functional but not yet fully simplified/documented as the final product surface
- Real-world bootstrap/prefetch ergonomics remain a productization concern, especially around first-run heavyweight dependencies

---

## Suggested next wave

Prioritize end-user productization rather than more migration plumbing.

Recommended lanes:
1. **Review handoff / docs truth pass**
   - align operator docs with the repo-contained runtime truth
2. **Single-command UX tightening**
   - sharpen `dub run` happy path and failure messaging
3. **Bootstrap / release surface**
   - make the first-time operator story predictable
4. **Canonical operator QA**
   - record one real supported scenario end-to-end

---

## Notes for reviewers

This commit intentionally focused on restoring test truth and repo-contained verification after the runtime-path migration. It did **not** attempt to redesign stage semantics or overfit tests to implementation details.

The most important review questions are:
- Is `DUB_PIPELINE_SCRIPTS_DIR` the right long-term test seam?
- Are TTS adapters now aligned with the same runtime-path contract as the other stages?
- Do the updated integration assertions test real product guarantees rather than incidental implementation details?
