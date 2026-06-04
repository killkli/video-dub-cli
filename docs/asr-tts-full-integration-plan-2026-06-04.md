# ASR / TTS Full Integration Plan (2026-06-04)

## Goal

Make `video-dub-cli` runnable on another machine without separate ASR/TTS repo installs.
User-approved remaining external prerequisites:
- system tools: `ffmpeg`, `ffprobe`
- Gemini API key

Out of scope for this wave:
- remove ffmpeg / ffprobe dependency
- remove Gemini API key requirement

In scope for this wave:
- ASR must be repo-owned in install story and runtime path
- TTS must be repo-owned in install story and runtime path
- no second private source repo
- no "install backend manually somewhere else, then point config at it"

## Current grounded state

### ASR
- `src/dub/stages/asr.py` already runs **in-process** via vendored `qwenasr_mlx_cli`.
- Remaining coupling is mostly **install-story / docs drift**, not runtime path:
  - README and QUICKSTART still describe `qwenasr-mlx` as an external operator-installed CLI.
  - config keeps `paths.qwenasr_cli` as legacy compatibility.
- Therefore ASR integration target is:
  1. bless repo-owned in-process ASR as the canonical path,
  2. make extras/bootstrap/doctor reflect that,
  3. remove operator-facing dependence on external `qwenasr-mlx` docs.

### TTS
- `src/dub/stages/tts.py` now resolves to package-owned runners under
  `src/dub/tts_engines/{omnivoice,voxcpme}/runner.py`.
- Those runners still forward to repo-vendored heavy-lift scripts, so the
  runtime entrypoint is repo-owned but the backend implementation is not yet
  fully in-package.
- OmniVoice route still assumes a separate interpreter via
  `paths.omnivoice_python` fallback semantics.
- VoxCPM route still assumes a local service on `127.0.0.1:8808`.
- Therefore TTS remains the real hard lane.

## Decomposition

### Lane A — audit / truth pass
- write this plan
- align the repo's own description of current state

### Lane B — ASR productization completion
- doctor / bootstrap / docs must stop telling operators to separately install `qwenasr-mlx`
- extras and README should present vendored `qwenasr_mlx_cli` as canonical
- keep `paths.qwenasr_cli` only as explicit legacy compatibility, not active contract

### Lane C — TTS integration
Two sub-lanes:
1. OmniVoice: collapse the "second interpreter" story so the canonical path is the dub venv itself
2. VoxCPM: decide whether to keep local service as the supported product contract, or vendor/embed a direct client/runtime path

### Lane D — verification / truthfulness
- targeted tests
- fake-backend QA
- if feasible, one real-backend smoke on the new canonical path

## First execution slice (this round)

Do now:
1. land this plan
2. finish Lane B first, because it is mostly contract/productization work and already close to done
3. then start cutting TTS interpreter coupling

Do not claim yet:
- TTS is fully integrated
- fresh machine needs no backend bootstrap
- VoxCPM no longer needs a local service

## Success criteria for Lane B
- README no longer says `qwenasr-mlx` is the one remaining external runtime dep
- QUICKSTART no longer instructs operator to install `qwenasr-mlx` separately
- doctor / bootstrap describe ASR readiness in terms of vendored in-process backend deps, not external CLI discovery
- tests remain green

## Success criteria for Lane C
- canonical TTS path runs under repo/dub environment, not a second interpreter
- `paths.omnivoice_python` is demoted to legacy compatibility or removed from operator story
- docs truthfully state any still-required local inference service

## Risks
- TTS is coupled to large model/runtime assumptions and may require staged migration rather than one-step removal
- VoxCPM may remain a local-service contract even after full repo integration of wrappers and client deps
- removing legacy config fields too early will break tests and old configs
