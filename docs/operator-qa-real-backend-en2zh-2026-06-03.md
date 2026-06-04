# Real-Backend Operator QA — EN → ZH (2026-06-03)

## Scope

This note records a **real-backend** end-to-end verification of the common operator entrypoint:

```bash
uv run dub en2zh <video>
```

This run was not fake-backed. It used:

- real repo-owned ASR pipeline (`qwenasr_mlx_cli`)
- real Gemini translation
- real OmniVoice TTS route
- real ffmpeg final assembly

## Input sample

To avoid a false negative from the silent-ish `tests/fixtures/test_short.mp4`, a fresh English speech sample was generated on-host:

- macOS `say` voice: `Samantha`
- text: short English verification paragraph
- packaged as: `.tmp_real_backend_media/en_sample.mp4`
- media probe: 1280x720 H.264 video + mono AAC audio
- duration: ~7.566s

Direct real-ASR probe on this generated sample produced a non-empty SRT before the full pipeline run.

## Readiness gates proved before the run

`dub doctor --config .tmp_real_backend_en2zh.yaml` reached fully-ready state after fixing the following live blockers:

1. Gemini keys were present in `~/.zshrc` but not in the Hermes command shell by default.
2. `gradio_client` had to be installed into the repo `.venv` (for Vox readiness, though not needed for this EN run).
3. `torchcodec` had to be installed into the repo `.venv` because live ASR initially failed under `torchaudio 2.11.0`.
4. `google-genai` had to be installed into the repo `.venv` because Stage 4 initially failed with missing dependency.
5. OmniVoice route required `paths.omnivoice_python=/Users/johnchen/Dev/OmniVoice/.venv/bin/python3`.

## Canonical config used

`.tmp_real_backend_en2zh.yaml`

Key setting:

```yaml
paths:
  omnivoice_python: /Users/johnchen/Dev/OmniVoice/.venv/bin/python3
```

## Final successful run

```bash
uv run dub en2zh .tmp_real_backend_media/en_sample.mp4 \
  --project-dir .tmp_real_backend_runs/en2zh_real_speech_retry_20260603_103633 \
  --config .tmp_real_backend_en2zh.yaml \
  --yes
```

## Observed result

Run output showed all six stages completed:

- `01_stems: done`
- `02_asr: done`
- `03_ref_audio: done`
- `04_translate: done`
- `05_tts: done`
- `06_assemble: done`

Validation:

```bash
uv run dub validate --project-dir .tmp_real_backend_runs/en2zh_real_speech_retry_20260603_103633
```

returned:

- `validate ok`
- `stages=6`
- `mode=delegate`
- `translate_status=done`

Final artifact probe:

- file: `07_final/video_dubbed_stem.mp4`
- duration: `7.560000`
- size: `188194` bytes

## Evidence excerpts

### ASR output excerpt

```srt
1
00:00:00,034 --> 00:00:00,574
Hello.

2
00:00:00,738 --> 00:00:04,574
This is a real English speech sample for end-to-end dubbing verification.
```

### Chinese translation artifact exists

`05_translated_srt/video.zhtw.srt` was produced by the live Gemini route.

### TTS route evidence

See `.dub/05_tts.log` in the project directory. This run used the OmniVoice path configured via `paths.omnivoice_python`.

## Important failures discovered during this QA wave

This success came only after finding and proving several real blockers:

1. **ASR runtime blocker**
   - first failure: missing `torchcodec`
   - symptom: Stage 2 crashed under real torchaudio I/O

2. **Sample-quality false negative**
   - `tests/fixtures/test_short.mp4` has audio but produced an empty SRT under real qwenasr
   - conclusion: it is not a valid real-ASR verification sample

3. **Translator dependency blocker**
   - Stage 4 initially failed because `google-genai` was absent from the repo `.venv`

4. **Shell-env mismatch**
   - Gemini keys existed in `~/.zshrc`, but were not automatically visible inside the Hermes/`uv run` command shell
   - the QA run injected those export lines explicitly

## What this run proves

This single run proves that the alias-era operator entrypoint:

- `dub en2zh`

can complete end-to-end with real backends when:

- the repo `.venv` includes the missing runtime deps
- Gemini key exports are actually present in the invoked shell
- OmniVoice is pointed at a working Python environment
- the input video contains clear spoken English

## What this run does not prove

It does **not** yet prove:

- arbitrary real-world English videos work first try
- noisy / overlapping / long-form audio is stable
- the default shell environment handling is operator-safe without manual export injection
- README/bootstrap currently install every real-backend dependency automatically

## Follow-up

Next real-backend gate:

- `docs/operator-qa-real-backend-ja2zh-2026-06-03.md`
