# Phase 1B — State-Aware Recovery Guidance Contract

**Date:** 2026-06-06
**Branch:** `feature/next-wave-audit-roadmap`
**Scope:** Phase 1B — reliability quick wins (recovery / readiness truth surfaces)
**Driving audits:** Lane A (runtime reliability) — recovery/clean/resume ergonomics and artifact/state truthfulness gaps. Lane B (UX) — operator friction on `dub status` / `dub clean` / `dub validate` no-state and no-source branches.

---

## What changed and why

Phase 1A tightened the **forward** operator path (`dub doctor`,
`dub bootstrap`, `dub auto` route summary, `dub --help`). Phase 1B
tightens the **recovery** path: the surfaces an operator sees when
something has already gone wrong, or when they are coming back to a
project that is in an unknown state.

The pre-P1B recovery contract had three operator-friction problems:

1. **`dub status` on a project with no `.dub/state.json` produced a single
   `(no state)` line and stopped.** The operator had to read the runbook
   to know whether to run `dub auto`, `dub en2zh`, or `dub ja2zh`.
2. **`dub status` on a project with a failed stage produced only
   `01_stems: failed attempts=N` style lines.** No recipe for *what to
   do next* — the operator had to know that `dub clean --stage N` +
   `dub resume` is the recovery path.
3. **`dub clean` and `dub validate` failure paths were terminal.** The
   operator got `clean complete: project=...` and assumed they were
   done. They were not — `dub resume` was still required. `dub validate`
   raised `ClickException` with no recovery hint at all.

The fix is a single state-aware helper,
`_project_recovery_plan(project_dir, current=...)`, that emits a
copy-paste-able `next: ...` / `see: ...` block. It is wired into every
recovery / truth surface — `dub status` (both no-state and
state-present), `dub clean` (always), `dub resume` (no-source branch),
and `dub validate` (every failure branch, even the ones that raise
`ClickException`).

The recovery block is anchored to a stable runbook heading
(`docs/operator-runbook.md#2-什麼時候用-resume-什麼時候用-clean`) so the
CLI and the runbook cannot silently drift apart. The anchor is locked
on both sides — see `test_p1b_recovery_anchor_matches_runbook_heading`
in `tests/test_cli.py`.

## Files changed

| File | Change |
| --- | --- |
| `src/dub/cli.py` | Added `_OPERATOR_RUNBOOK_RECOVERY_SECTION` (stable runbook anchor). Added `_load_project_state_safely()` (defensive state loader: missing or malformed `.dub/state.json` → `None`, no spurious stack traces). Added `_project_recovery_plan()` (state-aware multi-line `next: / see:` block: no-state → smoke commands; failed stage → `dub clean --stage N` + `dub resume`; complete → `dub validate`; always ends with runbook anchor). Replaced `_recovery_hints()` body with a one-liner wrapping `_project_recovery_plan()`. Wired the helper into `status` (no-state and state-present), `clean` (always), `resume` (no-source), and `validate` (all four failure branches: missing state, failed stage, missing final artifact, translated-subtitle contract violation). |
| `tests/test_cli.py` | Updated 2 existing assertions on `test_dub_run_prints_preflight_route_summary` and `test_dub_resume_restores_use_existing_route_from_state` to match the new state-aware pointer format. Added 8 new regression tests under the `p1b` prefix. |

## Recovery plan branching

The new helper covers four branches, keyed on what `load_state()`
returns and what the project filesystem looks like:

| State | Recovery block emitted |
| --- | --- |
| No `.dub/state.json` | `next: re-create the project with `uv run dub auto <VIDEO> --project-dir X` (or `dub en2zh` / `dub ja2zh`); the path above has no .dub/state.json` |
| A stage has `status=failed` | `next: a stage failed (failed_stages=NAME); recover with `uv run dub clean --project-dir X --stage N` then `uv run dub resume --project-dir X`` (N = highest-numbered failed stage) |
| No failed stage, no final mp4 | `next: continue the pipeline with `uv run dub resume --project-dir X` (or re-run from the failing stage with `dub clean --stage N` + `dub resume`)` |
| No failed stage, `07_final/video_dubbed_stem.mp4` exists with size > 0 | `next: project is complete; final artifact is `X`. verify with `uv run dub validate --project-dir X`` |
| Any of the above | `next: see `docs/operator-runbook.md#2-什麼時候用-resume-什麼時候用-clean` for the canonical resume / clean decision matrix` |

The `current=` keyword argument lets the calling command suppress
recommending the command the operator just ran — e.g. `dub resume`'s
no-source branch points at `dub auto` / `dub en2zh` / `dub ja2zh` but
not at `dub resume`, and `dub clean` recommends `dub resume` but not
another `dub clean`.

## Verification

Performed before commit:

1. `source .venv/bin/activate && python -m pytest tests/test_cli.py -q`
   → **81 passed** (was 73 before the new tests; 8 added in this
   commit). Pre-existing failures in
   `tests/test_omnivoice_root_env_var.py`,
   `tests/test_tts_runner_entrypoints.py`, and
   `tests/integration/test_6a_smoke.py` are environmental (missing
   `gradio_client` for VoxCPM, missing `dubbing_stems.py` stub in
   integration conftest) and reproduce on commit `ac25ca6` (pre-P1B).
   Not in scope for P1B.
2. `source .venv/bin/activate && python -m pytest tests/test_cli.py -k
   p1b -v` → **8 passed** in 0.13s.
3. Smoke `uv run dub status --project-dir <tmp>` on a directory with
   only `.dub/` present → emits `(no state)`, the re-create recipe
   naming `dub auto` / `dub en2zh` / `dub ja2zh`, and the runbook
   anchor.
4. Smoke `uv run dub resume --project-dir <tmp>` on a directory with
   `01_raw_video/` but no `video.mp4` → emits `(no source video)`, the
   re-create recipe, and the runbook anchor.

## Operator contract pinned by the new tests

- `dub status` on a no-state project always recommends the three
  smoke commands and pins the runbook anchor.
- `dub status` on a project with a failed stage always names the
  *highest-numbered* failed stage in the `dub clean --stage N`
  recommendation and pins the runbook anchor.
- `dub status` on a complete project (final mp4 present) recommends
  `dub validate`, not `dub resume`, and pins the runbook anchor.
- `dub clean` always emits a recovery plan so the operator knows
  they still need to run `dub resume` afterwards.
- `dub resume` on a no-source project emits the re-create recipe,
  not the legacy `(no source video)` dead end.
- `dub validate` failure branches all emit the recovery plan
  *before* raising `ClickException` (recovery text is in
  `result.output` even when `exit_code != 0`).
- The CLI's runbook anchor must point at a section heading that
  literally exists in `docs/operator-runbook.md` (the
  `test_p1b_recovery_anchor_matches_runbook_heading` test reads the
  runbook off disk and asserts the heading is present).

## Out of scope for P1B

- Phase 1C (translation batching / verification groundwork) — a
  separate implementation card, not started per operator sequencing.
- The `current=` branch suppression logic was implemented to be
  safe-by-default (it only affects the recipe wording, never the
  runbook anchor). The suppression is conservative — only the
  calling command's own recipe is removed, not its complementary
  recovery command.
- No CLI flags were added. The contract is purely about what
  *existing* commands print.

## Follow-ups noted (not done)

- The `_project_recovery_plan` helper currently lives in `cli.py`.
  If a non-CLI surface (e.g. a TUI or a JSON output mode) ever
  needs the same block, factor it out into a `dub.recovery_plan`
  module. No need yet.
- The state-loader's broad `except Exception` is defensive against
  malformed `state.json`; the long-term fix is to schema-validate
  `state.json` on load and surface a structured error. That is a
  separate concern from the recovery-pointer contract and is
  tracked under reliability follow-up.
