# Phase 1A — Doctor Remediation & Bootstrap Next-Step

**Date:** 2026-06-06
**Branch:** `feature/next-wave-audit-roadmap`
**Scope:** Phase 1A Commit 2 — doctor/bootstrap messaging `[P1A]`
**Driving audits:** Lane B (UX / onboarding) findings B-QW-2 and B-QW-3.

---

## What changed and why

The Lane B audit flagged two operator pain points the existing CLI did not
address:

1. **`dub doctor` BLOCKED output did not include remediation commands.**
   An operator who saw `doctor lanes: ready=\`dub en2zh\` ; blocked=\`dub ja2zh\``
   had to cross-reference `docs/operator-runbook.md` to figure out *why* the
   ja2zh lane was blocked and *what command* would unblock it. That is a
   high-friction dead end for first-time operators.
2. **`dub bootstrap` was a flat informational list with no clear "next step".**
   The 16-line body of guidance ran straight from `bootstrap:` lines into
   a single "run `dub doctor`" closer. A fresh operator had to mentally
   reconstruct the canonical first-run recipe from the body.

The fix for both is **a thin, contract-pinned summary surface** that the
operator can copy-paste verbatim. No new commands, no new flags, no new
configuration — just clearer text.

## Files changed

| File | Change |
| --- | --- |
| `src/dub/cli.py` | Added `_remediation_hint()` helper that maps known doctor gate keys (`ffmpeg`, `gemini_api_key`, `interpreter`, `deps:<mod>`, `service`, `wrapper`, `config`, `py:<mod>`) to concrete one-line fix commands. Wired the helper into the top-level `checks` loop and the per-backend `tts_backends` loop so every failing gate contributes a `doctor fix: ...` line. The new lines are dedup'd and emitted only when the run is not fully successful. Added two closing lines to `dub bootstrap` — `bootstrap next:` and `bootstrap first-run:` — that pin the canonical one-command operator path. |
| `tests/test_cli.py` | Added 6 focused tests: bootstrap next-step + first-run surface, standalone `dub-bootstrap` entrypoint also surfaces the summary, doctor emits `doctor fix:` lines on a VoxCPM `service` warn-block, doctor emits `dub bootstrap-<backend>` hint when an `interpreter` gate is missing, doctor success path stays free of spurious `doctor fix:` lines, and `_remediation_hint` degrades gracefully on unknown gates. |

## Verification

Performed before commit:

1. `uv run pytest tests/test_cli.py tests/test_doctor_bootstrap_standalone.py -q` →
   **83 passed** (was 77 before the new tests; 6 added in this commit).
2. `uv run dub doctor` → with the operator's real env, surfaces the
   `service: warn (127.0.0.1:8808 unreachable ...)` gate, the lane summary
   `doctor lanes: ready=\`dub en2zh\` ; blocked=\`dub ja2zh\``, the new fix
   line `doctor fix: start the local VoxCPM server with \`uv run python -m dub.tts_engines.voxcpme.server --port 8808\` (see docs/operator-runbook.md FR-10)`,
   and the new close `doctor next: re-run \`uv run dub doctor\` after the fix above lands; full failure list is in the lanes summary above`.
3. `uv run dub bootstrap` → body unchanged, new closing lines
   `bootstrap next: run \`uv run dub doctor\` to confirm every gate; once it prints \`doctor ok: ready for dub auto...\`, the canonical smoke is \`uv run dub auto <VIDEO>\``
   and `bootstrap first-run: \`uv sync --extra all\` -> \`uv run dub doctor\` -> \`uv run dub auto <VIDEO>\``.

## Operator contract pinned by the new tests

- Every failing top-level gate (`ffmpeg`, `ffprobe`, `repo_pipeline_scripts`,
  `gemini_api_key`, `py:<mod>`) yields a `doctor fix:` line.
- Every failing per-backend gate (`interpreter`, `deps:<mod>`, `service`,
  `wrapper`, `config`) yields a `doctor fix:` line tagged with the
  backend-specific `dub bootstrap-<backend>` recovery command where applicable.
- The success path does **not** emit `doctor fix:` lines — it keeps the
  canonical `ready for dub auto, dub en2zh, dub ja2zh` line and the
  `doctor next:` pointer.
- `dub bootstrap` always ends with both `bootstrap next:` (what to run
  after the body) and `bootstrap first-run:` (the 3-step recipe).
- The standalone `dub-bootstrap` console script mirrors the CLI behaviour.

## Deferred findings

- `dub auto` success output is still machine-oriented; the human-readable
  route explanation is being added under Phase 1A Commit 3.
- Top-level `dub --help` does not yet have a first-time operator path.
  Tracked under Phase 1A Commit 3.
- `tests/integration/test_6e_route_scenarios.py::test_6e_delegate_fresh_run_records_translated_subtitle_contract`
  fails on this host because `tests/integration/conftest.py` does not
  stub `dubbing_stems.py`. This is a pre-existing infrastructure gap,
  not a Phase 1A regression, and is not in scope for this batch.
