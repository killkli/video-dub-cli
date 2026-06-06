# Phase 1A — Docs Truth Cleanup

**Date:** 2026-06-06
**Branch:** `feature/next-wave-audit-roadmap`
**Scope:** Phase 1A Commit 1 — docs truth cleanup `[P1A]`
**Driving audit:** Lane B (UX / onboarding) — finding B-QW-1.

---

## What changed and why

The Lane B onboarding audit flagged that `README.md` and `QUICKSTART.md` still
referenced `docs/local-operator-handoff-2026-06-05.md`, which had already
been removed from the repo. A dead reference like that is the worst kind of
operator-facing failure: the file looks helpful, but `docs/local-operator-handoff-2026-06-05.md`
would 404 for any new clone. The fix is to point operators at
`docs/operator-runbook.md`, which is the canonical, in-repo recovery guide
and **does** document the `voxcpme service` activation step that the old
handoff referenced.

## Files changed

| File | Change |
| --- | --- |
| `README.md` | Removed dead link in the "外部前置條件" block; replaced stale index entry in the "文件索引" block with the truthful `docs/operator-runbook.md` line. |
| `QUICKSTART.md` | Removed the trailing stale pointer to the deleted handoff doc. |

## Verification

Performed before commit:

1. `grep -rn "local-operator-handoff-2026-06-05" --include="*.md" --include="*.py" --include="*.toml" .` returns only one match — the audit-finding reference in `docs/plans/2026-06-06-phase1-quick-wins-plan.md` line 45, which describes why the cleanup was needed. The plan file is intentionally left untracked, and that line is itself an audit record, not a stale operator pointer.
2. `test -f docs/operator-runbook.md` → exists.
3. `grep -n "voxcpme\|127.0.0.1:8808\|service" docs/operator-runbook.md` → confirms the runbook covers the VoxCPM service activation that the deleted handoff used to describe.
4. No code paths or test assertions reference the removed doc, so the change is docs-only.

## Deferred findings

- `dub doctor` blocked-lane output does not yet include remediation commands.
  Tracked under Phase 1A Commit 2.
- `dub bootstrap` summary does not yet end with a clear "next step" pointer.
  Tracked under Phase 1A Commit 2.
- `dub auto` success output is still machine-oriented; the human-readable
  route explanation is being added under Phase 1A Commit 3.
- Top-level `dub --help` does not yet have a first-time operator path.
  Tracked under Phase 1A Commit 3.
- `tests/integration/test_6e_route_scenarios.py::test_6e_delegate_fresh_run_records_translated_subtitle_contract`
  fails on this host because `tests/integration/conftest.py` does not stub
  `dubbing_stems.py`. This is a pre-existing infrastructure gap, not a
  Phase 1A regression, and is not in scope for this batch.
