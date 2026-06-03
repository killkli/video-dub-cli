# TTS Backend Consolidation Plan

## Goal

Make `video-dub-cli` usable without cloning external source repos for TTS backends.

This does **not** require shipping model weights in git. It does require that the repo itself owns:

- backend selection contract
- readiness checks
- runtime adapters / wrapper scripts
- installation/bootstrap documentation

## Current coupling

### OmniVoice route

Current assumptions in runtime:

- stage code points at a separate interpreter via `paths.omnivoice_python`
- script path comes from external `skills_dir/dubbing_batch_tts.py`
- packaging story is implicit and local-machine-specific

### VoxCPM route

Current assumptions in runtime:

- external `skills_dir/dubbing_batch_tts_vox.py`
- local python env must already have `gradio-client` and `opencc`
- route may depend on local server/runtime conventions outside repo docs

## Proposed consolidation contract

### 1. Repo owns all dispatch logic

The repo should own:

- source-lang routing
- readiness probing
- command construction
- bootstrap guidance
- environment contract

This is already partially true in `src/dub/stages/tts.py`; the missing part is that the called scripts still live outside the repo.

### 2. Repo-local wrapper/adapters are the first safe milestone

Short-term safest path:

- vendor repo-local copies/adapters for current TTS scripts under repo control
- keep backend-specific heavy runtime assumptions explicit
- avoid breaking the tested shell-out contract immediately

This reduces source-repo dependence without forcing an early rewrite of all TTS internals.

### 3. Split dependency classes clearly

#### Base install

Should include only what is needed for:

- CLI
n- config/state
- translation path
- doctor/bootstrap
- non-TTS stages where feasible

#### Optional extras

Recommended extras:

- `vox`
  - `gradio-client`
  - `opencc-python-reimplemented`

- `tts-omni` or similar
  - only if OmniVoice can be installed through a stable package path
  - otherwise keep it as bootstrap/runtime contract, not base install

#### Bootstrap/runtime prerequisites

Likely still needed outside git:

- model weights / checkpoints
- local inference services if a route depends on one
- ffmpeg/ffprobe system tools

## OmniVoice recommendation

Current evidence suggests OmniVoice should **not** be treated as a guaranteed pure-PyPI dependency yet.

Recommended near-term strategy:

- preserve current shell-out shape
- move the callable wrapper script into this repo
- make `dub doctor` explicitly report OmniVoice readiness separately from generic python availability
- document the bootstrap steps needed to make OmniVoice route usable

If a stable pip/wheel install path is later confirmed, convert this into an optional extra.

## VoxCPM recommendation

VoxCPM route is a better fit for optional-extra + bootstrap:

- Python client deps can live in an extra (`vox`)
- local service readiness should be checked in `dub doctor`
- wrapper script should be repo-owned even if the service is external

## Doctor contract

`dub doctor` should eventually report at least these layers:

- base system tools:
  - ffmpeg
  - ffprobe
- ASR tool:
  - qwenasr command availability
- translation route:
  - Gemini API key present
- TTS route readiness:
  - OmniVoice wrapper present
  - OmniVoice runtime/interpreter/backend available
  - Vox route wrapper present
  - Vox python deps available
  - Vox service reachable if required

## First implementation slice for this wave

1. keep `src/dub/stages/tts.py` as the route controller
2. move all externally referenced TTS scripts under repo-owned vendor/adapters path
3. keep interpreter/runtime knobs configurable during transition
4. extend `dub doctor` in later slice to report per-backend readiness instead of only generic python presence

## Risks

- OmniVoice installability may remain environment-specific
- large model/runtime deps should not silently migrate into base install
- wrapper vendoring without clear bootstrap docs can still feel broken to users

## Success criteria for this lane

This lane is successful when:

- no TTS route requires cloning another source repo
- scripts/adapters invoked by runtime are committed in this repo
- docs state what is package-installed vs bootstrap-prepared vs system-level
- doctor/bootstrap messaging can explain why a route is not yet ready
