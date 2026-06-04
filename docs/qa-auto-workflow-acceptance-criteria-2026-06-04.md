# QA Acceptance Criteria for Auto-Workflow (T2, 2026-06-04)

**Branch:** `feature/standalone-repo-uv`
**Parent contract:** `docs/auto-workflow-contract-2026-06-04.md`
**Sibling audit (T1):** `docs/cli-one-shot-gap-analysis-2026-06-04.md`
**Status:** criteria defined, ready for T3 implementation

---

## What this document is

This is the QA definition of done for the first auto-workflow implementation
slice (T3). It names the exact acceptance criteria a first-time operator
experience must satisfy, derived from the T0 contract and the T1 gap audit.

T3 should be considered complete only when every criterion below is verified
by real CLI invocation or automated test.

---

## Files reviewed for this audit

| File | What was checked |
|---|---|
| `src/dub/cli.py` | CLI surface, en2zh/ja2zh wiring, doctor output, bootstrap text |
| `src/dub/config.py` | default values, legacy fields, merge_cli_overrides |
| `README.md` | first-screen operator guidance, command ordering |
| `QUICKSTART.md` | step-by-step happy-path walkthrough |
| `DESIGN.md` | architectural baseline (noted: stale, still references old structure) |
| `docs/auto-workflow-contract-2026-06-04.md` | T0 contract (source of truth for criteria) |
| `docs/cli-one-shot-gap-analysis-2026-06-04.md` | T1 gap audit |
| `docs/operator-runbook.md` | failure recovery procedures |
| `docs/operator-qa-canonical-flow-2026-06-03.md` | fake-backend canonical QA pass |
| `docs/operator-qa-real-backend-en2zh-2026-06-03.md` | real-backend EN2ZH QA |
| `docs/operator-qa-real-backend-ja2zh-2026-06-03.md` | real-backend JA2ZH QA |
| `examples/config_en2zh.yaml` | EN2ZH example config template |
| `examples/config_ja2zh.yaml` | JA2ZH example config template |
| `examples/config_delegate_en2zh.yaml` | canonical delegate example |
| `tests/test_cli.py` | existing CLI test coverage |
| `tests/test_runner_smoke.py` | runner smoke test |
| `tests/integration/test_6e_route_scenarios.py` | route scenario coverage |

CLI commands verified during audit:

```
uv run dub --help
uv run dub en2zh --help
uv run dub ja2zh --help
uv run dub run --help
uv run dub resume --help
uv run dub doctor
uv run dub bootstrap
uv run pytest tests/test_cli.py   # 33/33 passed
```

---

## Current state: what a first-time operator must still know manually

Based on the T1 audit and this QA pass, a first-time operator today must:

1. **Know which command to use.** The `--help` lists `en2zh`, `ja2zh`, and
   `run` as equal-weight commands. Nothing in the CLI surface or first-screen
   docs says "start here for your first run."

2. **Decide whether to prepare a config file.** QUICKSTART Step 1 tells the
   operator to `cp examples/config_delegate_en2zh.yaml ~/.config/dub/config.yaml`.
   This is a manual step that should not exist for the common case.

3. **Understand that `run` is not the primary command.** README and QUICKSTART
   show `run` alongside `en2zh`/`ja2zh` without clear hierarchy.

4. **Know where the output will land.** Project directory defaults to
   `cfg.paths.dub_root` (default: `~/video-dub-cli-runs/`). The operator
   must read config or docs to predict where `07_final/video_dubbed_stem.mp4`
   will appear.

5. **Interpret doctor output against the auto path.** Doctor says
   "standalone prerequisites look ready" — it does NOT say "ready for
   `dub en2zh`" / "ready for `dub ja2zh`" as the T0 contract requires.

6. **Know which TTS backend will be used.** Doctor reports readiness for all
   backends (omnivoice, voxcpme) but the auto-workflow should pick one
   automatically or tell the operator which one is active.

---

## Acceptance criteria for the auto-workflow (T3 must satisfy ALL)

### AC-1: Zero-flag one-shot for the common case

**Criterion:** `dub en2zh <VIDEO>` and `dub ja2zh <VIDEO>` complete end-to-end
with no `--config`, no `--project-dir`, no `--translate-mode`, and no
`--source-lang`/`--target-lang` flags.

**Verification:**
- A smoke test exercises `dub en2zh <sample.mp4>` (fake-backend) with zero
  flags beyond the positional VIDEO, and asserts success.
- Same for `dub ja2zh <sample.mp4>`.
- The operator never needs to create or copy a config file for the default
  case.

**Current gap:** en2zh/ja2zh already hard-code source/target lang, but still
expose `--config`, `--translate-mode`, `--vocal-gain`, etc. The contract does
not require *removing* those flags — only that the zero-flag invocation works.
This is already satisfied. **PASS.**

### AC-2: Obvious project location

**Criterion:** After a one-shot run, the operator can find the output without
reading config internals.

**Verification:**
- The completion message prints the exact path to `07_final/video_dubbed_stem.mp4`.
- Default `--project-dir` is derived from the video file name (e.g.
  `<video-stem>.dub/` next to the input, or a clearly documented convention).
- `dub status --project-dir <printed-path>` works.

**Current gap:** Completion message (`_completion_summary`) already prints the
final MP4 path and the project dir. Default project dir is created under
`cfg.paths.dub_root`. The operator can find the output. The T0 contract
suggests `<video-stem>.dub/` next to input; this is a UX improvement but not
a blocker since the path is printed. **PARTIAL — see recommendation.**

### AC-3: Doctor speaks the auto-workflow language

**Criterion:** `dub doctor` says "ready for `dub en2zh`" / "ready for `dub ja2zh`"
or lists the exact missing piece.

**Verification:**
- On a fully-configured host, `dub doctor` prints something like
  `doctor ok: ready for dub en2zh / dub ja2zh`.
- On a host missing a prerequisite, it prints the exact gate and what to do.

**Current gap:** Doctor currently says `doctor ok: standalone prerequisites
look ready` — generic, does not name the lane. **FAIL — requires fix.**

### AC-4: First-screen docs lead with the one-shot command

**Criterion:** README and QUICKSTART open with `dub en2zh <VIDEO>` /
`dub ja2zh <VIDEO>` as the primary guidance, not `dub run --config ...`.

**Verification:**
- The first code block in README shows the one-shot command.
- `dub run` is documented as an advanced/explicit-control escape hatch.
- No config-copy step appears in the quick-start path.

**Current gap:** README already opens with `uv run dub en2zh talk.mp4` (line 9).
QUICKSTART still has a "Step 1: Prepare config" with `cp examples/...`. The
config step is documented as optional but still appears in the numbered
sequence. **PARTIAL — config step should be secondary/optional note, not a
numbered step in the happy path.**

### AC-5: EN2ZH and JA2ZH symmetric

**Criterion:** Both flows use the same CLI surface, same config schema, same
resume/status/doctor/validate semantics, same artifact layout.

**Verification:**
- `dub en2zh --help` and `dub ja2zh --help` show identical option surface.
- `dub doctor` readiness covers both lanes.
- `dub status` / `dub validate` / `dub resume` work identically for both.

**Current gap:** en2zh and ja2zh share the same code path (`_run_pipeline_command`),
differing only in hardcoded source/target lang. Option surface is identical.
**PASS.**

### AC-6: Resumable artifact-driven workflow preserved

**Criterion:** Auto-detection of completed stages, `dub resume`, `dub status`,
`dub doctor`, `dub clean` all work as before.

**Verification:**
- `dub resume --project-dir <dir>` skips completed stages.
- `dub status --project-dir <dir>` shows per-stage truth.
- `dub clean --project-dir <dir>` removes stage artifacts.
- A smoke test proves the resume path works after a partial run.

**Current gap:** All of these already work. Tests exist for en2zh alias and
runner smoke. **PASS.**

### AC-7: Smoke test proves the contract

**Criterion:** An automated test runs the one-shot command from start to finish
and asserts the output contract.

**Verification:**
- Test runs `dub en2zh <fake-video.mp4>` with fake backends.
- Asserts that `project_dir/07_final/video_dubbed_stem.mp4` exists.
- Asserts that `dub status` shows all stages as `done`.
- Asserts that `dub resume` on the same project is a no-op (all stages done).

**Current gap:** `test_dub_en2zh_alias_sets_languages_and_completes` tests the
alias wiring but monkeypatches `run_pipeline` (does not run real stages).
`test_6e_en2zh_alias_runs_supported_fake_backend_flow` exercises the fake
backend but is integration-only. A unit-level smoke test that runs the full
fake-backend pipeline through en2zh without monkeypatching is missing.
**PARTIAL — needs a new or promoted smoke test.**

---

## Summary table

| ID | Criterion | Status | Action needed |
|---|---|---|---|
| AC-1 | Zero-flag one-shot | PASS | None |
| AC-2 | Obvious project location | PARTIAL | Document default path convention clearly; consider `<video-stem>.dub/` |
| AC-3 | Doctor speaks auto-workflow | FAIL | Update doctor success message to name the lane |
| AC-4 | First-screen docs lead with one-shot | PARTIAL | Demote config-copy step in QUICKSTART; ensure run is escape hatch |
| AC-5 | EN2ZH/JA2ZH symmetric | PASS | None |
| AC-6 | Resumable workflow preserved | PASS | None |
| AC-7 | Smoke test proves contract | PARTIAL | Add fake-backend en2zh smoke test without monkeypatching |

---

## Recommendations for T3

1. **Fix AC-3 first** (doctor message). This is the smallest, highest-signal
   change. A one-line edit to `cli.py` line 500 from
   `"doctor ok: standalone prerequisites look ready"` to something like
   `"doctor ok: ready for dub en2zh / dub ja2zh"`.

2. **Improve AC-4** (docs). Move the config-copy step from QUICKSTART numbered
   sequence into an "Advanced: custom config" sidebar. Ensure README first code
   block stays as `dub en2zh talk.mp4`.

3. **Add AC-7 smoke test.** Either promote the integration test to run in the
   default suite (with fake-backend env vars), or add a new
   `test_one_shot_contract.py` that exercises en2zh/ja2zh through the fake
   backend without monkeypatching `run_pipeline`.

4. **AC-2 is optional for first slice.** The completion message already prints
   the path. The `<video-stem>.dub/` convention is a nice-to-have, not a
   blocker.

---

## Docs/CLI truthfulness findings

During this audit, the following truthfulness issues were noted:

| Location | Issue | Severity |
|---|---|---|
| `DESIGN.md` | Still references old structure (`src/dub/doctor.py`, `src/dub/bootstrap.py`); these don't exist as separate files — doctor and bootstrap are in `cli.py` | Low (DESIGN.md is aspirational) |
| `QUICKSTART.md` line 40 | Says "dub run 真正跑媒體前要裝 ffmpeg" — should say "dub en2zh / dub ja2zh" for the auto-workflow framing | Medium (misleading first-screen) |
| `examples/config_en2zh.yaml` comment | Says "uv run dub run talk.mp4 --source-lang en --target-lang zh" — should show en2zh alias | Low (example file, rarely read) |
| `docs/operator-runbook.md` FR-3 recovery | Shows `uv run dub run <video>` as recovery option — should show `uv run dub en2zh <video>` first | Low |
| Doctor output | Does not name the lane-specific command | Medium (AC-3) |

All are non-blocking except AC-3, which is a required fix.

---

## Acceptance gate for T3

T3 is complete when:

1. `dub doctor` prints a lane-aware readiness message (AC-3).
2. QUICKSTART does not present config-copy as a required numbered step (AC-4).
3. A smoke test proves `dub en2zh <video>` works end-to-end without monkeypatching (AC-7).
4. All existing tests continue to pass.
5. No new legacy-compat fields are introduced in config schema.

The other criteria (AC-1, AC-5, AC-6) already pass and need no action.
