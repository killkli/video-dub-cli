# Real-Backend Operator QA — JA → ZH (2026-06-03)

## Scope

This note records a **real-backend** end-to-end verification of the alias operator entrypoint:

```bash
uv run dub ja2zh <video>
```

This run used:

- real repo-owned ASR pipeline (`qwenasr_mlx_cli`)
- real Gemini translation
- real VoxCPM route
- real ffmpeg final assembly

## Input sample

A fresh Japanese speech sample was generated on-host to ensure the input had clear spoken Japanese:

- macOS `say` voice: `Kyoko`
- packaged as: `.tmp_real_backend_media/ja_sample.mp4`
- media probe: 1280x720 H.264 video + mono AAC audio
- duration: ~10.827s

Direct real-ASR probe on this sample produced a non-empty Japanese SRT before the full pipeline run.

## Final successful run

```bash
uv run dub ja2zh .tmp_real_backend_media/ja_sample.mp4 \
  --project-dir .tmp_real_backend_runs/ja2zh_real_speech_20260603_103900 \
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
uv run dub validate --project-dir .tmp_real_backend_runs/ja2zh_real_speech_20260603_103900
```

returned:

- `validate ok`
- `stages=6`
- `mode=delegate`
- `translate_status=done`

Final artifact probe:

- file: `07_final/video_dubbed_stem.mp4`
- duration: `10.800000`
- size: `201992` bytes

## Evidence excerpts

### ASR output excerpt

```srt
1
00:00:00,066 --> 00:00:00,958
こんにちは。

2
00:00:01,122 --> 00:00:06,366
これはエンドツーエンドの吹き替え現象用の2本ゴロン声サンプルです。
```

Note: the middle line contains an ASR recognition error, but it is non-empty and route-valid for backend verification.

### Chinese translation artifact exists

`05_translated_srt/video.zhtw.srt` was produced by the live Gemini route.

### TTS route evidence

See `.dub/05_tts.log` in the project directory. This run used the VoxCPM wrapper route and completed 3/3 lines successfully.

## What this run proves

This run proves that the alias-era operator entrypoint:

- `dub ja2zh`

can complete end-to-end with real backends when the readiness gates are satisfied.

It also proves that the live JA route is not merely wired in tests — it exercised:

- real ASR on Japanese speech
- real Gemini translation to Chinese
- real VoxCPM synthesis
- real final assembly and validation

## What this run does not prove

It does **not** yet prove:

- arbitrary real-world Japanese videos work first try
- noisy / long / multi-speaker Japanese audio is stable
- ASR quality is acceptable for production without review
- shell env bootstrap is operator-safe by default

## Follow-up

Pair this with:

- `docs/operator-qa-real-backend-en2zh-2026-06-03.md`
- `docs/release-handoff-checklist.md`
