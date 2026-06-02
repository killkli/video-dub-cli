# video-dub-cli Kanban Development Plan

> **For Hermes:** this file is the executable backlog and acceptance contract for the next productization wave.

**Goal:** turn `video-dub-cli` from operator-grade CLI into a more trustworthy single-command workflow for video EN/JA → ZH conversion, with explicit scenario support, durable state, and verifiable end-to-end behavior.

**Current grounded state (2026-06-02):**
- branch before this plan: `main`
- latest docs commit: `28290b5 docs: align README with current operator workflow`
- CLI exists: `run / resume / status / clean / validate`
- translation stage has committed Gemini route
- README truthfulness was just corrected
- next missing work is productization surface + broader scenario verification

---

## Delivery principles

1. **One stable CLI entrypoint** remains `dub run`.
2. **Fail fast before expensive stages** whenever contract inputs are missing.
3. **State is the source of truth** for resume / validation behavior.
4. **Supported scenarios must be named explicitly**; no hidden magic assumptions.
5. **Every phase ends with executable verification**.
6. **Small commits only**; every commit should map to one logical improvement.

---

## Phase map

## Phase T0 — Branch + execution lane bootstrap
**Outcome:** all further work lands on a dedicated feature branch.

Acceptance:
- feature branch exists
- repo remains clean after branch switch

Suggested commit policy:
- no code commit required for pure branch bootstrap

---

## Phase 1 — Productization surface: preflight route summary
**Outcome:** operator can see, before stage execution starts, exactly which route the CLI will take.

Scope:
- print resolved route summary before pipeline run
- include source language, target language, translate mode, project dir, and whether translated SRT is external / existing / delegated
- make the summary truthful to actual config/runtime behavior

Acceptance:
- `dub run ... --help` unchanged unless intentionally improved
- run path prints one concise preflight summary
- summary distinguishes:
  - `delegate`
  - `use-existing`
  - `skip`
- tests cover the rendered route summary or equivalent internal contract

Verification:
- targeted pytest for CLI output
- operator smoke invocation using fake backends or dry contract path

Commit target:
- `feat(cli): add preflight route summary [S3][F1]`

---

## Phase 2 — Config and examples tightening
**Outcome:** happy-path scenarios have canonical config/examples.

Scope:
- add example config for delegate flow
- add example config for use-existing flow
- ensure examples align with current paths/field names
- remove or clarify any stale config keys that imply old translation path assumptions

Acceptance:
- examples directory contains current supported scenario configs
- README references match actual example filenames and semantics
- no stale example naming around removed/legacy assumptions

Verification:
- read-through verification of example files
- if config loader tests exist, extend them minimally

Commit target:
- `docs(config): add canonical example configs for supported flows [S3][F2]`

---

## Phase 3 — Validate contract hardening
**Outcome:** `dub validate` understands translated subtitle expectations when relevant.

Scope:
- validate presence/shape of translated SRT when stage state implies it should exist
- give explicit failure messages for mismatch between translate mode / artifacts / state
- do not overreach into unsupported deep media QA

Acceptance:
- validate distinguishes absent optional artifacts from required missing artifacts
- translated subtitle contract is checked when applicable
- tests cover success/failure cases

Verification:
- pytest for validation behavior

Commit target:
- `fix(validate): enforce translated subtitle artifact contract [S3][F3]`

---

## Phase 4 — Scenario coverage expansion
**Outcome:** supported scenarios are actually exercised in integration tests.

Scope:
- integration: fresh run with delegate/mock translate
- integration: fresh run with use-existing translated SRT
- integration: resume after interrupted/cleaned later stage with preserved config
- integration: ja→zh routing smoke with fake Vox route

Acceptance:
- tests pass locally
- each scenario asserts the specific route it intends to verify
- failures point to route mismatch or artifact mismatch clearly

Verification:
- targeted integration pytest selection

Commit target:
- `test(integration): expand supported scenario coverage [S4][F1]`

---

## Phase 5 — Real operator QA pass
**Outcome:** one fresh operator run confirms the intended single-command path for a supported scenario.

Scope:
- choose one supported scenario as the canonical operator QA path
- record exact invocation, outputs, and limits in docs/references
- explicitly document what still remains non-productized

Acceptance:
- reference note added under docs or skill references
- includes command, environment assumptions, and observed output
- does not over-claim unsupported scenarios

Verification:
- real command invocation output captured from tool run

Commit target:
- `docs(qa): record operator verification for supported single-command flow [S4][F2]`

---

## Immediate execution order

1. **T0** branch bootstrap
2. **Phase 1** preflight route summary
3. **Phase 2** config/examples tightening
4. **Phase 3** validate contract hardening
5. **Phase 4** integration expansion
6. **Phase 5** operator QA note

---

## This session execution target

This round should complete:
- Phase T0
- start Phase 1 implementation
- run focused verification for Phase 1 if code lands cleanly

---

## Notes for future Kanban dispatch

Available profiles observed on this machine:
- `default` (running)
- `kanban-orch` / `kanban-qa` / `kanban-research` / `kanban-writer` exist but gateways are currently stopped

Given current gateway state, the safest immediate execution path is:
- do T0 + Phase 1 directly in-session on a feature branch
- if later fan-out is desired, either start the kanban profile gateways or assign tasks to `default` explicitly
