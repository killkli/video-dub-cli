# video-dub-cli Auto Workflow Full Development Plan

> **For Hermes:** Use this as the canonical plan for the new workstream: input one video, then run the full EN/JA → ZH workflow end-to-end from a single CLI entrypoint with real operator-grade checkpoints.

**Goal:** turn `video-dub-cli` into a single-command workflow where an operator can pass a video file and have the pipeline automatically run the required downstream steps for English→Chinese or Japanese→Chinese conversion, with clear preflight checks, resumable state, and truthful backend gating.

**Architecture:** keep the existing staged pipeline, but add a higher-level orchestration layer that chooses route, validates prerequisites, creates/uses project state consistently, and drives the full workflow through one stable operator entrypoint. Do not collapse proven stage boundaries; productize them.

**Tech Stack:** Python 3.11+, Click, Pydantic, pytest, existing `dub` stage runner, repo-owned qwenasr / translation / TTS adapters.

---

## Grounded current state (verified this session)

- Branch: `feature/standalone-repo-uv`
- VoxCPM vendor commit completed: `fbe78d9`
- `uv sync --extra all` works on fresh clone
- `uv run dub --help` works on fresh clone
- `uv run dub doctor` works on fresh clone
- Fresh clone `dub doctor` reports:
  - `voxcpme: READY`
  - `omnivoice: BLOCKED` unless separate bootstrap is done
- `dub bootstrap-voxcpm` works and writes `paths.voxcpme_python`
- Current board: `video-dub-cli-auto-workflow`
- Existing board state already covers early research / QA for first slice

---

## Product target

The supported operator stories should become:

1. `uv run dub en2zh <video>`
   - automatic project setup
   - ASR / translation / TTS / assemble / validate
   - resumable if interrupted

2. `uv run dub ja2zh <video>`
   - same as above, but routed to Japanese → Chinese contract
   - backend truthfulness surfaced by `dub doctor`

3. `uv run dub auto <video>`
   - new higher-level entrypoint
   - source language explicitly provided or auto-selected from config/default
   - chooses `en2zh` or `ja2zh` route without the operator having to remember lower-level mode details

---

## Non-goals for this wave

- no silent language auto-detection by ML unless already proven in repo
- no removal of the current staged/resumable architecture
- no fake success when TTS service/model is unavailable
- no collapsing OmniVoice + VoxCPM into one dependency environment

---

## Main gaps

### G1. No canonical top-level `auto` entrypoint
Current CLI exposes route-specific commands, but not a single productized entrypoint for operators who just want “take this video and convert it”.

### G2. Preflight is still fragmented
The operator can reach stage execution before all route-specific requirements are summarized in one place.

### G3. Project bootstrap is not yet framed as one coherent workflow contract
The code is resumable, but the operator story still feels like several expert commands instead of one obvious workflow.

### G4. Documentation and QA are not yet aligned to the final operator mental model
Docs mention pieces, but the user wants a direct CLI workflow with a complete development plan and implementation lane.

---

## Phase plan

## Phase 0 — Freeze current truth and establish branch/board guardrails
**Outcome:** new work proceeds on top of a verified baseline and does not mix with unrelated standalone-TTS work.

Tasks:
1. Record current verified contract in docs/plans and board comments.
2. Keep `feature/standalone-repo-uv` as the active integration branch unless a new feature branch is explicitly cut.
3. Treat `video-dub-cli-auto-workflow` as the canonical board for this wave.

## Phase 1 — Introduce canonical `dub auto` entrypoint
**Outcome:** one stable command exists for the operator.

Tasks:
1. Add `dub auto <video>` command.
2. Accept source language from explicit flag/config/defaults.
3. Resolve to `en2zh` or `ja2zh` route deterministically.
4. Print a short route summary before stage execution.
5. Add focused CLI tests.

## Phase 2 — Preflight + workflow contract hardening
**Outcome:** wrong invocations fail before expensive work begins.

Tasks:
1. Centralize route-specific preflight checks.
2. Fail fast on missing API key / ffmpeg / TTS route prerequisites.
3. Make `dub auto` and route-specific commands share the same preflight contract.
4. Add tests for failure and success paths.

## Phase 3 — Project bootstrap + state coherence
**Outcome:** input video → stable project state creation is fully coherent.

Tasks:
1. Ensure `auto` creates or reuses project dir consistently.
2. Ensure resume/status/validate still work unchanged.
3. Verify artifacts are registered in `ProjectState` at each stage boundary.
4. Add regression tests for new-project and resume flows.

## Phase 4 — Operator-facing docs and examples
**Outcome:** docs match the real supported workflow.

Tasks:
1. Update README with `dub auto` as the primary story.
2. Keep `en2zh` / `ja2zh` documented as explicit lower-level aliases.
3. Add examples for English, Japanese, resume, and route-specific bootstrap.
4. Update runbook / QA matrix / handoff checklist.

## Phase 5 — Real workflow QA gate
**Outcome:** the new entrypoint is proven on supported scenarios.

Tasks:
1. Fresh clone + `uv sync --extra all` + `dub auto` smoke path.
2. English route smoke.
3. Japanese route smoke.
4. Resume / validate / status smoke.
5. Confirm failure messaging remains truthful when backend is blocked.

---

## Task graph for implementation

### Lane A — CLI surface
- add `dub auto`
- route resolution
- summary output
- tests

### Lane B — Preflight contract
- unify backend prerequisite checks
- route-specific fail-fast
- tests

### Lane C — Docs and operator contract
- README
- QUICKSTART
- runbook
- QA matrix / release checklist

### Lane D — QA / verification
- fresh clone validation
- route smoke tests
- resume/status/validate checks

Dependencies:
- Lane A and B can start in parallel
- Lane C depends on A+B shape settling
- Lane D depends on A+B, and partially on C for final wording verification

---

## Verification commands

```bash
pytest -q tests/test_cli.py tests/test_tts_engines.py tests/test_tts_runner_entrypoints.py
pytest -q
uv run dub --help
uv run dub doctor
uv run dub auto --help
```

Fresh clone verification:

```bash
git clone <repo> /tmp/video-dub-cli-fresh
cd /tmp/video-dub-cli-fresh
uv sync --extra all
uv run dub --help
uv run dub doctor
uv run dub auto --help
```

---

## Commit plan

### Commit A
- add canonical `dub auto` command and route resolution
- message: `feat(cli): add canonical auto workflow entrypoint [AUTO-S1]`

### Commit B
- unify preflight and fail-fast checks
- message: `fix(cli): harden auto-workflow preflight contract [AUTO-S2]`

### Commit C
- docs / examples / runbook updates
- message: `docs(cli): document canonical auto workflow [AUTO-S3]`

### Commit D
- QA harness / regression tests / verification notes
- message: `test(cli): cover canonical auto workflow scenarios [AUTO-S4]`

---

## Acceptance criteria

The wave is complete only if all of the following are true:

- `uv run dub auto --help` exists and is truthful
- operator can provide one input video and trigger the full supported workflow from one command
- route selection is explicit and deterministic
- bad prerequisite states fail before expensive stage execution
- docs match real behavior
- fresh clone verification passes
- `status`, `resume`, and `validate` still work after the new surface is introduced
