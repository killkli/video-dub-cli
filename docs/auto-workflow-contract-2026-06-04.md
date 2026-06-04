# Auto-Workflow Board Contract (T0 Gate, 2026-06-04)

## Goal

Establish the operator contract for the next wave of `video-dub-cli`: a single
command takes a video and dubs it end-to-end, with EN→ZH and JA→ZH supported
out of the box, while preserving the resumable artifact-driven pipeline that
the repo already ships.

This document is the durable planning note required by kanban task
`t_8dabffc5` (T0 gate). It is the contract that T1 (research audit) and T2
(QA acceptance criteria) will audit against.

## In-scope operator contract

The auto-workflow MUST satisfy all four points:

1. **One command, one input.**
   - Operator runs something of the form:
     - `dub en2zh <VIDEO>` for English → Chinese
     - `dub ja2zh <VIDEO>` for Japanese → Chinese
   - The command takes a single positional `VIDEO` and the rest of the
     pipeline runs without further flags.

2. **End-to-end default.**
   - The default invocation runs all six stages (stems, asr, ref_audio,
     translate, tts, assemble) and produces a dubbed output video under
     `project_dir/final/`.
   - The operator does not have to think about `paths.*`, `--source-lang`,
     `--target-lang`, or `translate-mode` for the common case.

3. **EN→ZH and JA→ZH symmetric.**
   - Both language flows use the same CLI surface, the same config schema,
     the same resume / status / doctor semantics, and the same artifact
     layout.
   - The only thing that differs is the ASR / translation prompt profile
     under `config/` — not a separate CLI sub-tool.

4. **Resumable artifact-driven workflow preserved.**
   - Auto-detection of already-completed stages remains.
   - `dub resume --project-dir <dir>` still works without re-running
     finished stages.
   - `dub status` still shows per-stage truth.
   - `dub doctor` still reports readiness for the auto path, not just the
     manual path.

## Explicitly out of scope for this wave

- New translation backends beyond Gemini (already canonical).
- New TTS voices / engines.
- Batch / queue / watch-folder workflows (single video is the contract).
- GUI / web frontend.
- Removing ffmpeg or Gemini-key prerequisites (out of scope per
  `docs/asr-tts-full-integration-plan-2026-06-04.md`).

## First-wave task graph

The board already has these children of T0. Names and roles:

```
t_8dabffc5  T0 (Gate)  — this note, contract locked           [default]
   ├── t_44e3238c  T1 (Research) — gap audit current vs one-shot
   │                  [kanban-research]
   └── t_41efef3e  T2 (QA)       — operator acceptance criteria
                   [kanban-qa]
```

Downstream of T1 and T2 (single convergent task, not yet on the board):

```
   └── t_6809c2a6  T3 (Impl/Docs) — first implementation slice
                       + README / QUICKSTART truth alignment
                       [default, on feature/standalone-repo-uv]
```

T3 will be created only after T1 and T2 land and agree on the first slice.
It is the only task expected to land code changes on
`feature/standalone-repo-uv` for this wave.

## First implementation slice (recommended target for T3)

The minimum honest cut that satisfies the contract above:

1. Make `dub en2zh <VIDEO>` and `dub ja2zh <VIDEO>` truly flag-free for the
   common operator case.
   - Default `--project-dir` = `<video-stem>.dub/` next to the input.
   - Default `--source-lang` / `--target-lang` derived from the subcommand.
   - Default `translate-mode` = `delegate` (the existing happy path).
   - No silent re-prompting when a stage's prerequisite is missing — fail
     fast through `dub doctor` output instead.

2. Promote `dub doctor` to the canonical pre-flight for the auto path.
   - It must say "ready for `dub en2zh`" / "ready for `dub ja2zh`" or list
     the exact missing piece.
   - It must work against the auto defaults, not just the legacy `dub run`
     path.

3. Realign README / QUICKSTART so the first screen of operator guidance is
   the one-shot command, not `dub run --config ...`.
   - `dub run` stays in the docs as the explicit-control escape hatch.
   - `dub resume` / `dub status` / `dub doctor` stay prominent for the
     resume / debug story.

4. Add a smoke test that proves the contract: a fake-backend run of
   `dub en2zh <sample.mp4>` lands a `project_dir/final/<name>.mp4` and
   reports success, with the resume path also tested.

## Verification this note must enable

T1 (research) should be able to point at this file and the existing CLI
help output and answer: "what does the current CLI already give us, and
what is still implicit?"

T2 (QA) should be able to point at this file and answer: "what does a
first-time operator have to know manually today, and what should the
auto-workflow collapse to?"

T3 (impl/docs) should be able to point at this file and the T1/T2 audits
and produce a diff that lands on `feature/standalone-repo-uv` without
re-deriving the contract.

## Risks and non-goals the contract deliberately accepts

- The auto path is opinionated; operators with exotic stage ordering keep
  `dub run` as the escape hatch. We are not collapsing `dub run` itself.
- The contract does not promise zero-flags forever — it promises a
  zero-flag **default**. Power users still have `dub run`.
- We do not yet promise batch / queue semantics.
