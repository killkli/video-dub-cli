# Phase 1 Quick Wins Plan — video-dub-cli

**Date:** 2026-06-06
**Branch baseline:** `feature/next-wave-audit-roadmap`
**Board:** `video-dub-cli-next-wave`
**Source tasks:**
- T0 `t_84399547` — branch gate
- T1 `t_d6b73a23` — runtime reliability audit
- T2 `t_8c195d16` — UX / CLI contract / onboarding audit
- T3 `t_2e8baa46` — feature expansion / integration audit
- T4 `t_cd84fc56` — roadmap synthesis

---

## 1. Purpose

This document records the Phase 1 implementation plan derived from the completed next-wave audits. The goal of Phase 1 is **not** to expand the product surface broadly. It is to remove the highest-friction operator pain on the existing product path while keeping scope tight, testable, and commit-clean.

Phase 1 focuses on:
1. UX quick wins on the current operator path
2. Reliability quick wins around truthfulness / recovery guidance
3. One narrow feature-integration slice that reduces operator error: translation batching / verification groundwork

---

## 2. Audit conclusions that drive Phase 1

### 2.1 Lane A — reliability audit
Verified from Kanban task summary and board records:
- The audit ranked the **top 5 runtime reliability gaps**.
- Focus areas were operator failure modes, resume/clean/recovery ergonomics, artifact/state truthfulness, and route-specific readiness behavior.
- Output status: complete.

Phase-1 interpretation:
- We should prioritize reliability fixes that improve **operator correctness** without requiring a major runtime rewrite.
- The most valuable reliability work in this wave is improving trust in doctor/bootstrap/recovery messaging and artifact truth surfaces.

### 2.2 Lane B — UX / onboarding audit
Verified from Kanban task summary and comment:
- 14 findings total.
- 8 quick wins.
- 7 deeper product changes.

Important quick-win findings explicitly reported by the audit:
1. README still referenced `docs/local-operator-handoff-2026-06-05.md`, which is no longer in repo.
2. `dub doctor` BLOCKED output does not include remediation commands.
3. `dub auto` success output is too machine-oriented and lacks a human-readable route explanation.
4. `dub bootstrap` is too informational and does not summarize readiness / next step clearly.
5. VoxCPM server startup is not surfaced clearly enough in the CLI journey.
6. `dub --help` exposes commands flatly, without a first-time operator path.

Phase-1 interpretation:
- We should batch the operator-facing quick wins first because they are small, testable, and directly improve trust.
- We should **not** try to solve all deeper command-hierarchy work in Phase 1.

### 2.3 Lane C — feature map
Verified from Kanban task summary:
- “Add now” priority leaned toward:
  - subtitle translation batching / verification
  - route policy controls
  - presets / templates
- “Integrate later / external boundary” items included:
  - long-form chunking / pre-cut automation
  - source ingestion
  - delivery / storage share integration

Phase-1 interpretation:
- Only one feature-integration slice should enter Phase 1: **translation batching / verification groundwork**.
- Route policy controls and presets are important, but can wait until after operator quick wins are complete.

### 2.4 Lane D — roadmap synthesis
Verified from Kanban task summary and comment:
- 4 workstreams: Reliability / UX & Docs / Feature Integrations / Future R&D
- 15 recommended cards
- 3-phase sequencing
- batching guidance exists for UX quick wins and feature integrations

Phase-1 interpretation:
- We should create a dedicated implementation batch for Phase 1 rather than mixing all roadmap items into a single broad card.

---

## 3. Phase 1 scope

### In scope

#### WS-1 / UX quick wins batch
1. Remove stale README references and align operator docs truth.
2. Improve `dub doctor` blocked output with concrete remediation hints.
3. Improve `dub bootstrap` summary so it points the operator to the next action.
4. Improve `dub auto` / route success output so it explains the chosen path in human-readable terms.
5. Improve top-level help / onboarding discoverability enough for first-time operators.

#### WS-2 / reliability quick wins
1. Tighten operator-facing truth surfaces around readiness/recovery.
2. Ensure recovery guidance is consistent across help text, runbook, and CLI output.
3. Add or update tests that lock the improved operator contract.

#### WS-3 / narrow feature-integration slice
1. Establish translation batching / verification groundwork.
2. Prefer contract / validation / documentation / test shape over ambitious runtime expansion.

### Explicitly out of scope for Phase 1
- Full command hierarchy redesign
- `dub config` command family
- `dub server` command family
- `dub init` / project template expansion beyond minimal groundwork
- long-form chunking automation
- source ingestion integration
- storage / delivery integration
- route-policy deep tuning for JA→ZH
- large refactors of TTS backend ownership

---

## 4. Recommended execution order

### Phase 1A — operator UX batch
Do first because it is the fastest way to reduce user friction and improve trust.

Targets:
- README / docs truth cleanup
- `dub doctor` remediation messaging
- `dub bootstrap` next-step summary
- human-readable route summary / success output
- minimal help text improvements

### Phase 1B — reliability contract batch
Do second because it should build on the clearer user-facing contract from 1A.

Targets:
- align recovery guidance across CLI / docs
- reinforce artifact/state truthfulness messaging
- add regression tests for the new operator contract

### Phase 1C — translation batching / verification groundwork
Do third because it is the first narrow feature integration worth productizing, but it is still more involved than the operator UX batch.

Targets:
- define the contract
- add validation / verification surfaces
- document the supported path
- only then consider deeper runtime wiring in a later phase

---

## 5. Planned Kanban implementation structure

### Card group A — UX quick wins batch
Single implementation card is acceptable **if** the task body includes explicit sub-commits and verification per logical unit.

Expected logical units:
- Commit 1: stale docs truth / broken reference cleanup
- Commit 2: doctor/bootstrap operator messaging improvements
- Commit 3: route-summary / help-text operator wording improvements

### Card group B — reliability quick wins
Separate implementation card plus QA card.

### Card group C — translation batching / verification groundwork
Separate implementation card plus QA / docs verification card.

### Final review / synthesis
A final QA or review card should depend on A + B + C.

---

## 6. Verification requirements

Every Phase 1 implementation card must include real verification, not only edits.

Minimum verification expectations:
- relevant focused pytest targets
- CLI help output checks where user-facing text changed
- `dub doctor` output capture where doctor messaging changed
- `git status --short` clean after each logical commit

For docs-only changes that alter operator behavior claims, verification must still include:
- confirm the referenced command/output actually exists
- confirm no stale path references remain

---

## 7. Commit discipline

Mandatory rule for Phase 1 workers:
- one commit per logical change
- verify immediately before each commit
- do not batch unrelated fixes together

Recommended commit pattern:
1. `docs(readme): remove stale handoff reference and align operator truth [P1A]`
2. `feat(doctor): add remediation hints for blocked lanes [P1A]`
3. `feat(cli): clarify bootstrap and route summary output [P1A]`
4. Later Phase 1B / 1C commits get their own refs, e.g. `[P1B]`, `[P1C]`

---

## 8. Deliverables to preserve

This plan file is the canonical Phase 1 planning record inside the repo.

Additional durable records should be added as the wave proceeds:
- implementation notes under `docs/plans/`
- QA evidence under `docs/` or `docs/audits/`
- Kanban summaries must name exact files changed and exact verification commands used

---

## 9. Immediate next step

Create Phase 1 implementation cards from this plan, starting with the **UX quick wins batch**.
