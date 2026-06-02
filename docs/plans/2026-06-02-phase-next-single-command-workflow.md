# video-dub-cli Next Phase Implementation Plan

> **For Hermes:** execute this plan incrementally; keep each change verifiable and commit in small logical units.

**Goal:** move `video-dub-cli` from operator-grade CLI toward a trustworthy single-command video language conversion workflow.

**Architecture:** tighten the operator contract before adding more backend complexity. First, make wrong invocations fail fast with explicit preflight checks and accurate docs. Then add higher-level UX/documentation and finally broaden end-to-end coverage across real modes (`delegate`, `use-existing`, resume paths, ja→zh routing).

**Tech Stack:** Python 3.11+, Click, Pydantic, pytest, existing stage runner.

---

## Current grounded state

Verified from repo/tool output on 2026-06-02:
- branch: `main`
- recent commits include translate-mode wiring and operator QA
- `dub run --help` exposes `--translate-mode` and `--translated-srt`
- targeted tests + operator integration pass
- repo working tree is clean after commit `3191b2b`

## Gaps blocking "just one command"

1. **Invocation contract is under-specified**
   - `--translate-mode use-existing` needs a translated SRT path.
   - `--translate-mode skip` only works when translated SRT already exists in project state.
   - today these mostly fail later in stage 4/5 instead of failing immediately.

2. **README over-promises**
   - top copy says one command fully auto-completes for any English video.
   - body still describes stubs / partly outdated stage contracts.
   - user cannot tell what is production-safe vs operator-safe.

3. **Higher-level UX missing**
   - no explicit preflight summary of chosen route.
   - no explicit supported-scenario matrix (fresh run vs resume vs external translated SRT).

4. **End-to-end mode coverage still narrow**
   - existing integration proves operator flow but not all translation mode combinations.

---

## Phase breakdown

### Phase A — Invocation contract hardening
**Outcome:** wrong `dub run` mode combinations fail before any expensive stage runs.

Tasks:
1. Add CLI preflight validator for translation mode.
2. Enforce `use-existing => translated_srt path exists`.
3. Enforce `skip => project already contains 05_translated_srt/video.zhtw.srt`.
4. Add focused CLI tests for both failure and success cases.
5. Verify with pytest.

### Phase B — Operator docs truthfulness
**Outcome:** README clearly states what is truly supported today.

Tasks:
1. Rewrite README header/status section to distinguish "available CLI" from "production complete".
2. Add translation-mode usage matrix.
3. Add examples for fresh run, resume, and `use-existing` translated SRT.
4. Remove stale wording that still implies stub-only stage implementations.

### Phase C — Single-command productization surface
**Outcome:** user sees one recommended happy-path command per scenario.

Tasks:
1. add preflight route summary in CLI output
2. add example config files for `delegate` and `use-existing`
3. add `validate` checks for translated subtitle contract when present

### Phase D — Real-world scenario verification
**Outcome:** confidence that CLI behaves correctly on supported scenarios.

Tasks:
1. integration: fresh run with delegate/mock translate
2. integration: fresh run with use-existing translated SRT
3. integration: resume after clean stage 5 with preserved config
4. integration: ja→zh routing smoke with fake Vox route

---

## This session scope

This session should complete **Phase A** and, if time remains, start **Phase B**.

## Verification commands

```bash
pytest -q tests/test_cli.py tests/test_translate_mode.py tests/test_config.py
pytest -q tests/integration/test_6d_operator_flow.py
```

## Commit strategy

### Commit 1
- contract hardening for translation-mode preflight
- tests for fail-fast behavior
- message: `fix(cli): fail fast on invalid translate mode usage [S2][F1]`

### Commit 2
- README truthfulness / usage matrix
- message: `docs(readme): clarify supported single-command scenarios [S2][F2]`
