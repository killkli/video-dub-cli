# video-dub-cli Next Wave Productization Plan

> **For Hermes:** Use this as the execution contract for the next productization round after standalone runtime recovery.

**Goal:** turn the now-verified repo-contained pipeline into a clearer single-command operator workflow for EN/JA→ZH dubbing.

**Architecture:** keep `dub run` as the canonical entrypoint, keep project state as truth, and improve the operator experience by tightening preflight/doctor/bootstrap/docs/release surfaces rather than reopening stage internals.

**Tech Stack:** Click CLI, repo-owned pipeline wrappers, project state machine, pytest integration suite, uv packaging.

---

## Grounded baseline

As of `3feee15 test/integration: restore repo-contained harness`:
- full pytest suite passes (`170 passed`)
- repo-contained runtime overrides are aligned across stems/ref/tts/assemble paths
- integration route coverage is restored for:
  - delegate translate
  - use-existing translated SRT
  - resume flow
  - ja→zh fake Vox route
  - operator QA harness

This means the next wave should emphasize **product surface quality**, not more runtime rescue unless new evidence appears.

---

## Priority lanes

### Lane A — Review handoff / docs truth pass
**Outcome:** operator-facing docs match the current repo-contained runtime truth.

Scope:
- review `docs/operator-runbook.md`
- review `docs/qa-standalone-matrix.md`
- remove stale references implying old `skills_dir`-driven behavior where no longer true
- explicitly document test-only overrides as test harness seams, not operator setup requirements

Acceptance:
- docs describe current TTS runtime path truth
- docs distinguish production defaults from test-only overrides
- no misleading legacy setup guidance remains

Verification:
- grep/read-through against current code paths
- optional targeted doc note update diff review

Suggested commit:
- `docs(runtime): align operator docs with repo-contained runtime truth [NW1][DOCS]`

---

### Lane B — One-shot CLI UX tightening
**Outcome:** first-time operator can understand what `dub run` is about to do and why it failed.

Scope:
- inspect current preflight summary and run-failure messages
- identify any ambiguous or overly internal messages
- tighten wording around:
  - translate mode
n  - external translated subtitle usage
  - repo-owned prerequisite failures
  - route/backend failure attribution
- keep behavior truthful; do not add fake simplification

Acceptance:
- `dub run` output is concise but scenario-explicit
- route/backend failures point at actionable missing piece
- CLI tests cover new wording where important

Verification:
- targeted pytest for CLI output
- at least one smoke invocation with fake harness

Suggested commit:
- `feat(cli): tighten one-shot operator messaging [NW1][CLI]`

---

### Lane C — Bootstrap / doctor / first-run ergonomics
**Outcome:** first-time setup path is explicit about what is repo-contained vs still external.

Scope:
- inspect current `dub doctor` and `dub bootstrap`
- confirm all reported checks are still the ones that matter after runtime consolidation
- improve guidance text if it still over-emphasizes old path assumptions
- decide whether first-run prefetch/bootstrap gaps need an explicit note or command refinement

Acceptance:
- doctor output names the right gates
- bootstrap text matches current product truth
- first-run external requirements are explicit and minimal

Verification:
- targeted doctor/bootstrap tests
- command output inspection via tool runs

Suggested commit:
- `fix(doctor): align readiness guidance with repo-contained runtime [NW1][BOOT]`

---

### Lane D — Canonical operator QA run note
**Outcome:** one real supported path is documented as the canonical single-command workflow.

Scope:
- choose one supported scenario:
  - likely `en -> zh`, `delegate`, default route
- run the real operator flow if environment permits
- if heavyweight backend availability blocks the full real run, document the exact blocker truthfully and record the highest-confidence verified path instead
- save a durable QA note with command, assumptions, and observed outputs

Acceptance:
- QA note names exact invocation
- QA note distinguishes real-runtime verification from hermetic fake-backend verification
- unsupported / unverified claims are explicitly excluded

Verification:
- real tool output, not inferred prose

Suggested commit:
- `docs(qa): record canonical operator verification path [NW1][QA]`

---

## Recommended execution order

1. Lane A — docs truth pass
2. Lane C — doctor/bootstrap alignment
3. Lane B — one-shot CLI UX tightening
4. Lane D — canonical operator QA note

Reasoning:
- A and C stabilize truth before messaging polish
- B should reflect the post-doc/post-doctor product surface
- D should document the final shaped experience, not an intermediate one

---

## Suggested Kanban decomposition

If dispatched through Kanban, split into these cards:

1. `review docs/runtime truth` — assignee: docs/research-capable profile
2. `tighten doctor/bootstrap guidance` — assignee: implementation profile
3. `tighten one-shot cli messaging` — assignee: implementation profile
4. `record canonical operator QA path` — assignee: QA/writer profile, parents on 2 and 3

If staying in-session, Lane A is the safest immediate next action.

---

## Immediate next-action recommendation

**Start with Lane A: docs truth pass.**
It is low-risk, grounded by the completed runtime consolidation, and reduces future confusion before more UX work lands.
