# Auto Workflow Full Development Plan

> **For Hermes:** this is the new execution contract for turning `video-dub-cli` from a route-aware operator CLI into a true one-video-in, Chinese-dub-out automatic workflow.

**Goal:** allow an operator to pass a single video to the CLI and have the workflow automatically determine whether the source is English or Japanese, choose the correct dubbing route, run the downstream pipeline end-to-end, and leave behind a truthful, resumable project tree with obvious recovery commands.

**Architecture:** keep the existing staged pipeline (`stems → asr → ref_audio → translate → tts → assemble`) and existing explicit commands (`run`, `en2zh`, `ja2zh`, `resume`, `status`, `validate`, `doctor`) as the stable substrate. Productize a new top-layer automatic contract around them: route detection, common-path UX, recovery visibility, and operator-grade verification.

**Tech stack:** Python 3.11+, Click CLI, pytest, existing `ProjectState`, `dub doctor` / `resume` / `validate`, Gemini translation helper, QwenASR-based pipeline artifacts, repo-owned vendor scripts.

---

## 1. Grounded baseline at plan start

Verified in `/Users/johnchen/.hermes/projects/video-dub-cli` on branch `feature/auto-workflow-kanban` after Wave 2 fixes:

- Current branch: `feature/auto-workflow-kanban`
- Baseline commit from previous wave: `35f271a`
- Existing operator entrypoints already present:
  - `dub auto <video>`
  - `dub en2zh <video>`
  - `dub ja2zh <video>`
  - `dub run <video> --source-lang ... --target-lang ...`
  - `dub resume --project-dir <dir>`
  - `dub status --project-dir <dir>`
  - `dub validate --project-dir <dir>`
  - `dub doctor`
- Current reality gap:
  - `dub auto` is **not yet fully automatic** for the user request.
  - It still relies on `--source-lang` or `defaults.source_lang`.
  - Therefore the product contract is still “route-aware one-command workflow,” not “single video input, auto-choose EN/JA route, then run everything.”

This new wave exists to close that gap truthfully.

---

## 2. Product target

The target operator experience is:

```bash
uv run dub auto /path/to/video.mp4
```

Expected behavior:

1. CLI inspects the input and determines the likely source route (`en` or `ja`) automatically.
2. CLI prints the chosen route and project directory before expensive stage work starts.
3. CLI runs the existing downstream pipeline without requiring the operator to think about route selection.
4. CLI ends with a clear summary:
   - chosen route
   - project directory
   - final artifact path
   - recovery commands (`resume`, `status`, `validate`)
5. Explicit controls (`--source-lang`, `en2zh`, `ja2zh`, `run`) remain available as escape hatches.

Non-goal: broad multilingual detection beyond English/Japanese.

---

## 3. Scope of this wave

### In scope

1. Define a truthful **auto route detection contract** for EN vs JA.
2. Implement a preflight route detector used by `dub auto`.
3. Ensure the detector fails loudly and explainably when confidence is too low.
4. Preserve explicit route commands and advanced controls.
5. Add tests for route detection, fallback, and operator messaging.
6. Verify end-to-end behavior with operator-grade commands.
7. Update README / QUICKSTART / runbook only after runtime truth is verified.

### Out of scope

1. Arbitrary multilingual routing beyond `en` / `ja`.
2. Replacing the existing stage architecture.
3. Changing TTS backend strategy (OmniVoice for EN source, VoxCPM for JA source).
4. General-purpose speech-language detection service integration unless needed by the narrow contract.

---

## 4. Deliverables

### D1. Automatic route detection for `dub auto`

`dub auto <video>` no longer requires the user to know or provide source language for normal EN/JA use.

Acceptance truth:
- if the source is clearly English, `dub auto` resolves to EN→ZH
- if the source is clearly Japanese, `dub auto` resolves to JA→ZH
- if confidence is ambiguous, CLI aborts early with a precise instruction to re-run with `--source-lang en|ja`

### D2. Operator-visible preflight contract

Before stage work starts, CLI prints:
- chosen route
- reason or detection basis
- project directory
- translate mode

Acceptance truth:
- the operator can understand what `dub auto` decided without opening source or config

### D3. Recovery-visible completion contract

After success, CLI prints:
- source route used
- project directory
- final artifact path
- `resume`, `status`, `validate` hints

Acceptance truth:
- the operator knows where to look next after either success or interruption

### D4. Regression coverage

Tests must cover:
- explicit override still wins (`--source-lang`)
- auto detection chooses `en` when detector says English
- auto detection chooses `ja` when detector says Japanese
- ambiguous detection fails early with clear operator message
- help/docs stay truthful

### D5. Docs aligned to runtime truth

Only after code + tests + smoke verification pass:
- README
- QUICKSTART / operator docs
- any help-text or plan docs that describe `dub auto`

---

## 5. Proposed implementation strategy

### Phase A — Detection contract design

Research the narrowest implementation that fits the current codebase with minimal blast radius.

Likely design:
1. Add a small route-detection helper near CLI/preflight code.
2. For `dub auto`, if `--source-lang` is provided, use it directly.
3. Else, run a lightweight detection step on the input video (or an extracted short sample / ASR snippet path if already cheap enough).
4. Map result to `en` or `ja` with a confidence threshold.
5. If unsupported or ambiguous, stop before stage 1 with an explicit error.

### Phase B — Wire `dub auto`

Update `dub auto` so its source-route resolution order becomes:
1. explicit `--source-lang`
2. auto detector
3. fail with instruction

Do **not** silently fall back to config defaults in the new automatic contract unless the user explicitly wants a pinned default route.

### Phase C — UX tightening

Preflight and completion output must always expose:
- route
- project dir
- output path / expected output path
- recovery commands

### Phase D — Verification

1. unit / CLI regression tests
2. targeted operator QA commands
3. if feasible, one hermetic smoke route with fake seams
4. doc updates after runtime truth is proven

---

## 6. Task graph (Kanban-ready)

### T0 — Baseline freeze and branch gate
**Status:** already completed in this session

Outputs:
- feature branch created: `feature/auto-workflow-kanban`
- prior Wave 2 fixes preserved
- new wave baseline captured in this plan

### T1 — Research: auto route detection contract
**Purpose:** inspect current `dub auto` resolution path and propose the narrowest truthful EN/JA detection design.

Must answer:
- where route detection should live
- whether to use lightweight probe / sample ASR / another helper
- what “ambiguous” means operationally
- what exact operator-visible message should appear

### T2 — Dev: add failing tests for auto route detection contract
**Purpose:** encode the new product contract before implementation.

Expected coverage:
- explicit override precedence
- auto English detection
- auto Japanese detection
- ambiguous detection failure
- operator-visible preflight summary contains route + project dir

### T3 — Dev: implement route detector + wire `dub auto`
**Purpose:** make `dub auto` actually automatic for EN/JA route selection.

Likely files:
- `src/dub/cli.py`
- possibly new helper module if extraction improves clarity
- `tests/test_cli.py`

**T3 outcome (recorded by T3 implementer, 2026-06-04):**

Land status on `feature/auto-workflow-kanban`:

- Commits added by T3:
  - `6e5b4ce` — `feat(cli): add AutoRouteDecision seam + precedence resolver [T3.1]`
  - `0af1deb` — `feat(cli): wire dub auto to precedence resolver + route_basis preflight [T3.2]`
- Verification (run on T3 implementer's machine):
  - `uv run --no-sync pytest tests/test_cli.py -k 'auto' -v` → **11/11 pass** (was 5/11 RED on T2 baseline; the 6 new T2 contract tests all flipped green in T3.2)
  - `uv run --no-sync pytest tests/test_cli.py` → **68/68 pass**, no regressions
  - `uv run --no-sync dub auto --help` → shows the new wave-3 precedence and re-run guidance
- What ships:
  - `AutoRouteDecision(source_lang, basis)` frozen dataclass on `dub.cli`
  - `_detect_auto_source_lang(video, cfg) -> AutoRouteDecision` real implementation (30s audio head-probe via ffmpeg + repo ASR + script-level classifier). Lazily imports `qwenasr_mlx_cli` so `en2zh` / `ja2zh` / `run` callers don't pay the cost.
  - `_resolve_auto_route(video, source_lang, cfg)` precedence wrapper: explicit `--source-lang` > detector > early `UserError`
  - `_normalize_explicit_source_lang` rejects unsupported explicit values with the new "Re-run with --source-lang en|ja" wording
  - `_run_preflight` and `_run_pipeline_command` accept an optional `route_basis` parameter; when set, the preflight line ends with ` route_basis=<basis>`. `en2zh` / `ja2zh` / `run` never pass one, so their preflight line shape is byte-identical to the pre-wave-3 contract.
  - `dub auto` body rewired: on `AutoRouteDecision.source_lang is None` it raises `click.ClickException` with `(basis: ...; supported: en, ja). Re-run with --source-lang en|ja.` — does NOT fall back to `cfg.defaults.source_lang`.
  - `dub auto --help` and command docstring updated to describe the auto-detect path. `en2zh` / `ja2zh` / `run` docstrings untouched.
- Old `_resolve_auto_source_lang(source_lang, cfg) -> str` removed (only consumer was the `auto` command; the new resolver replaces it).

T3 handoff to T4 (operator contract verification):
- The 6 new T2 contract tests (`test_dub_auto_explicit_source_lang_overrides_detector`, `test_dub_auto_detects_english_when_no_flag`, `test_dub_auto_detects_japanese_when_no_flag`, `test_dub_auto_fails_when_detection_is_ambiguous`, `test_dub_auto_fails_when_detection_raises`, `test_dub_auto_preflight_includes_route_basis_and_project_dir`) are the authoritative spec. T4 should treat them as the source of truth.
- For real-video manual smoke testing, T4 will need `ffmpeg` on `$PATH` AND the qwenasr_mlx_cli ASR backend installed (`uv sync --extra all` already covers this) AND a real video file. The repo's hermetic test suite does NOT exercise the real detector — it always monkeypatches `_detect_auto_source_lang`. T4's job is to close that gap with at least one end-to-end run.

### T4 — QA: operator contract verification
**Purpose:** verify that `dub auto` now behaves like a true one-video-in operator command instead of a route-aware wrapper.

Checks:
- no route flag needed on common path
- explicit route override still works
- ambiguous case blocks early with correct message
- completion / recovery summary remains truthful

### T5 — Docs: update operator-facing contract
**Purpose:** change docs only after T4 verifies runtime truth.

Likely files:
- `README.md`
- `QUICKSTART.md`
- any operator runbook mentioning `dub auto`

---

## 7. Execution rules

1. Keep existing explicit commands intact; `dub auto` is additive productization, not a breaking removal.
2. Every claim must be backed by real command output or test output.
3. Keep commits logically minimal.
4. Do not claim multilingual auto support beyond EN/JA.
5. If detection quality is insufficient, fail early and truthfully rather than silently guessing.

---

## 8. First implementation slice for this session

The first concrete slice to start immediately is:

### Slice S1 — establish the detection seam and failing tests

Why this slice first:
- it turns the user request into an executable contract
- it minimizes architecture guesswork
- it gives a stable target before touching runtime behavior

Expected work in S1:
1. inspect current `_resolve_auto_source_lang(...)` path
2. identify best seam for injectable detection helper
3. add failing tests that express the new behavior
4. implement only enough scaffolding to make the contract explicit

This is the first card to execute now.

---

## 9. Verification commands

Baseline:

```bash
git branch --show-current
git status --short
git rev-parse --short HEAD
```

CLI surface:

```bash
uv run dub --help
uv run dub auto --help
uv run dub en2zh --help
uv run dub ja2zh --help
```

Targeted tests:

```bash
uv run pytest tests/test_cli.py -q
```

Post-change operator QA:

```bash
uv run dub doctor
uv run dub auto <video>
uv run dub status --project-dir <dir>
uv run dub validate --project-dir <dir>
```

---

## 10. Completion criteria for this wave

This wave is complete only if all are true:

- `dub auto <video>` no longer depends on operator route knowledge for standard EN/JA inputs
- route choice is visible and explainable
- ambiguous cases fail early with a truthful recovery instruction
- explicit controls still work
- tests cover the contract
- docs match verified runtime behavior
