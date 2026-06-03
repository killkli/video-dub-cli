# video-dub-cli Phase 4 — Productization Plan & Linear Gate

> **For Hermes:** this is the executable plan for P4. It does NOT introduce new stage logic. It locks down operator-facing contracts (CLI / artifacts / failure recovery / operator UX) and gates the wave behind them.

**Goal:** turn `dub run` into a trustworthy single-command video EN/JA → ZH workflow that an operator can drive from README / `--help` alone, with explicit contract guarantees, and an explicit list of what remains un-productized.

**In scope for P4:**

- finalize CLI / artifact / failure-recovery / operator-UX contracts
- align research findings (provider / route / coupling weaknesses) with the contracts
- write QA matrix and regression gates for en→zh and ja→zh
- formalize README / QUICKSTART / runbook against the contracts
- close the loop with a final integration smoke

**Out of scope for P4:**

- new stage implementations
- new external skills / backends
- real-model quality benchmarking

---

## Grounded state (2026-06-02)

From the repo working tree on `feature/video-dub-cli-phase-next-productization`:

- CLI: `run` / `resume` / `status` / `clean` / `validate` all wired to real implementations
- 6 stages: `01_stems` / `02_asr` / `03_ref_audio` / `04_translate` / `05_tts` / `06_assemble`, all real-wired (last commits: `13743a8` tts contract gate, `89cf225` real-smoke blockers)
- translate modes: `delegate` / `use-existing` / `skip`, all with preflight fail-fast
- preflight route summary printed at run start
- canonical translated subtitle path: `05_translated_srt/video.zhtw.srt`
- legacy sync path: `05_translate/video.zhtw.srt` (compatibility only)
- `dub validate` enforces translated-subtitle contract
- `dub resume` restores `source_lang` / `target_lang` / `translate_mode` from state (per uncommitted diff in working tree)
- Gemini route: now accepts labeled `[index] text` output and falls back to plain lines (`translator_gemini._parse_labeled_translation_lines`)
- operator QA record: `docs/operator-qa-canonical-flow-2026-06-03.md` (en→zh, fake backend; alias-era canonical note)
- release / handoff checklist: `docs/release-handoff-checklist.md`

Uncommitted changes in working tree (must not be lost when P4 cards promote):

```
M src/dub/cli.py                    # _restore_cfg_from_state_inputs + resume_cmd wiring
M src/dub/translator_gemini.py      # labeled-line parser + stricter prompt
M tests/test_cli.py                 # resume-restores-source-lang test
M tests/test_translator_gemini.py   # labeled-output + missing-index tests
M tests/test_tts_stage.py           # 22/32 shape reproducers
```

These uncommitted changes belong to the P3 debug wave (`t_caacbec7`). The P4-T1 / P4-T5 cards must commit them as a precondition before doing P4 work, or the orchestrator must commit them at the end if no other card picks them up.

---

## P4 Task Graph

```
P4-T0 (orch — this card)
  ├── P4-T1 (Dev, default)     — CLI contract 收斂
  ├── P4-T2 (QA, kanban-qa)    — operator QA matrix
  ├── P4-T3 (Research, kanban-research) — provider / route 盤點
  │      ↓
  │   P4-T4 (Writer, kanban-writer) — README / QUICKSTART / runbook 正式化
  │      ↓
  └── P4-T5 (Dev, default)     — 收尾整合
```

Dependency rules:

- T0 unblocks T1, T2, T3 the moment the body contracts below are written and the plan is on disk.
- T1, T2, T3 can run in parallel.
- T4 cannot start until T3 has at least a `coupling-weaknesses` finding written to a comment or scratch file, AND T2 has at least an `evidence matrix` comment written.
- T5 cannot start until T1, T2, T3, T4 are all `done`. It is the integration / commit sweep.

---

## Contract 1 — CLI 契約

The `dub` CLI is the only operator-facing surface. P4-T1 owns this contract.

**Surface area (frozen):**

```
dub run VIDEO [options]
  --source-lang / --src         (en | ja)         default: config.defaults.source_lang
  --target-lang / --tgt         (zh | zhtw)       default: config.defaults.target_lang
  --project-dir                 path             default: /path/to/dub-root/dub-<topic>-<ts>/
  --config                      path             default: /path/to/config.yaml
  --translate-mode              delegate|skip|use-existing   default: delegate
  --translated-srt              path             required iff --translate-mode use-existing
  --vocal-gain                  float dB
  --inst-gain                   float dB
  --keep-fulltrack              flag
  --yes / -y                    flag

dub resume --project-dir DIR [--config PATH]
dub status --project-dir DIR
dub clean --project-dir DIR [--stage N] [--keep-source / --remove-source]
dub validate --project-dir DIR
```

**Behavior contract (frozen):**

1. `dub run` MUST print a single `preflight: ...` line before any stage starts. The line MUST include: `src`, `tgt`, `project`, `mode`, `route`.
2. `dub run` MUST fail fast (no stage execution) when:
   - `--translate-mode use-existing` is passed without `--translated-srt`
   - `--translated-srt` points to a non-existent file
   - `--translate-mode skip` is used on a project that does NOT already contain `05_translated_srt/video.zhtw.srt`
3. `dub resume` MUST restore `source_lang`, `target_lang`, `translate_mode`, `translated_srt` from `.dub/state.json` so a follow-on run with no CLI flags produces the same route. (P3 uncommitted patch already implements this; P4-T1 must commit it as a precondition.)
4. `dub status` MUST be read-only and never mutate state.
5. `dub clean` MUST never delete `01_raw_video/video.mp4` unless `--remove-source` is explicitly passed.
6. `dub validate` MUST enforce the translated-subtitle contract when the project state implies it is required.

**Acceptance for P4-T1:**

- a new `tests/test_cli.py` case asserts the preflight summary text format
- a new test asserts `dub resume` re-applies state-derived route on a fresh invocation
- existing preflight / fail-fast / validate tests still pass
- the uncommitted working-tree changes (`cli.py` / `translator_gemini.py` / related tests) are committed as precondition commits
- no CLI flag is added; no flag is renamed

---

## Contract 2 — 產物契約

**Project directory layout (frozen):**

```
<project_dir>/
├── 01_raw_video/
│   └── video.mp4                      (source, never mutated)
├── 02_stems/
│   ├── vocals.wav
│   └── instrumental.wav
├── 03_asr/
│   └── video.srt                      (source-language subtitles)
├── 04_ref_audio/
│   ├── line_1_ref.wav
│   ├── line_2_ref.wav
│   └── ...
├── 05_translate/                       (legacy sync path — compatibility)
│   └── video.zhtw.srt
├── 05_translated_srt/                  (CANONICAL)
│   └── video.zhtw.srt
├── 06_tts_wav/
│   ├── line_1_tts.wav
│   ├── line_2_tts.wav
│   ├── ...
│   └── tts_normalized.wav
├── 07_final/
│   ├── video_dubbed_stem.mp4          (always produced)
│   └── video_dubbed.mp4               (only if --keep-fulltrack)
└── .dub/
    ├── state.json
    └── <stage>.log
```

**State contract (frozen, must not change in P4):**

- `state.input` carries `video_path`, `video_sha256`, `duration_sec`, `source_lang`, `target_lang`, `translate_mode`, `translated_srt`
- `state.stages` is keyed by `01_stems` / `02_asr` / `03_ref_audio` / `04_translate` / `05_tts` / `06_assemble`
- each stage carries `status` ∈ {`pending`, `running`, `done`, `failed`}, `attempts`, and `output_dir`

**Acceptance for P4-T2:**

- the QA matrix in `docs/qa-matrix-en-ja-zh-2026-06-02.md` enumerates which artifacts must exist for each scenario (en→zh delegate, en→zh use-existing, en→zh skip-resume, ja→zh delegate, ja→zh use-existing) and at which stage they appear
- the matrix names the exact evidence path on disk for each row, e.g. `state.stages['03_ref_audio'].status == 'done'` AND `04_ref_audio/line_1_ref.wav` exists
- the matrix names one regression entry point per scenario, e.g. `pytest tests/integration/test_6e_route_scenarios.py -k ja_delegate -q`

---

## Contract 3 — 失敗恢復契約

**Per-stage behavior (frozen):**

1. Each stage is independently retryable. Default: 3 attempts with exponential backoff (handled by `dub.retry`).
2. On `failed`, the stage writes a `<stage>.log` line into `.dub/` describing the last error.
3. `dub resume` MUST skip any `done` stage and re-enter any `failed` / `pending` stage.
4. If `--translate-mode skip` is used on a fresh project, `dub run` MUST fail fast with the exact message: `translate-mode=skip requires an existing translated subtitle at <path>`.
5. If `--translate-mode use-existing --translated-srt /missing/path.srt` is passed, `dub run` MUST fail fast with: `translated SRT not found: /missing/path.srt`.

**Acceptance for P4-T2 / P4-T5:**

- a regression test kills stage 5 mid-run, asserts `dub resume` re-enters from stage 5 and reaches stage 6
- a regression test asserts the exact fail-fast message strings above (snapshot test)
- the release handoff checklist is updated to include the regression entry points

---

## Contract 4 — Operator UX 契約

**README / QUICKSTART / runbook contract (P4-T4 owns):**

1. README MUST list the three supported scenarios (`delegate`, `use-existing`, `skip`) in a matrix with the exact one-line command for each, and the exact limitation for `skip`.
2. README MUST link to `docs/operator-qa-canonical-flow-2026-06-03.md` so an operator can see a real run record.
3. QUICKSTART MUST walk a fresh operator through: copy example config → run `dub run <video>` → read `status` / `validate` → locate final MP4.
4. A new `docs/operator-runbook.md` MUST enumerate:
   - how to read `state.json`
   - how to read `<stage>.log`
   - when to use `resume` vs `clean --stage N`
   - how to recover from the four most common failure modes (use-existing without path, skip on fresh project, stage 5 OOM, stage 6 ffprobe failure)
5. None of the three documents may over-claim "fully productized for any source video". The release/handoff template is the source of truth for what is and is not productized.

**Acceptance for P4-T4:**

- a follow-on operator reading only README + QUICKSTART + runbook can complete the supported single-command flow without opening source code
- every CLI example in docs has a one-line match in the real `dub --help` output

---

## Linear Gate (P4-T5 final integration)

P4-T5 will be `blocked` until all of T1/T2/T3/T4 are `done`. Once unblocked, P4-T5 MUST:

1. Run the full integration suite: `pytest tests/ -q`
2. Run the targeted operator smoke (`python3 tools/make_operator_qa_env.py` + `dub run ... --yes`) and capture the result.
3. Verify that the uncommitted P3 working-tree changes are committed (P4-T1 should have done this; P4-T5 confirms).
4. Add a final P4 summary commit / tag, e.g. `docs(plan): P4 productization wave complete [P4]`.
5. Surface any new blocker explicitly in the task summary — do not silently fold it into the next wave.

---

## Verification commands (canonical)

```bash
# Unit + integration suite
pytest tests/ -q

# Targeted operator smoke (fake backend)
python3 tools/make_operator_qa_env.py
dub run .tmp_operator_qa/test_short.mp4 \
  --source-lang en --target-lang zh \
  --project-dir .tmp_operator_qa/op_p4_smoke \
  --config .tmp_operator_qa/operator-config.yaml \
  --yes
dub status --project-dir .tmp_operator_qa/op_p4_smoke
dub validate --project-dir .tmp_operator_qa/op_p4_smoke

# Real ja→zh smoke (already verified in t_caacbec7)
dub run <ja-source.mp4> --src ja --tgt zh --yes
```

---

## Known non-productized gaps (carried over from P3)

P4 will NOT close these. They are listed here so P4-T2 / T4 do not over-claim.

- Real ASR / TTS / translation quality has NOT been measured against human-reviewed ground truth.
- "Any source video succeeds on first try" is NOT productized; only the supported scenarios above are.
- External skill availability (qwenasr-mlx-cli, OmniVoice, VoxCPM, Gemini API) is the operator's responsibility.
- Multi-language source / target matrix is not promised.

If a P4 card discovers a new blocker that the existing release/handoff checklist already covers, log it as a follow-up kanban task with `kanban_create` and link it back to the discovering card. Do not silently extend scope.
