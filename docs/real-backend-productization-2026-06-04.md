# Real-Backend Productization QA (2026-06-04)

## Scope

This note captures the productization wave that turned `video-dub-cli`
from "real backend works if you do 4 manual fixes" into "real backend
works on a fresh clone". Concretely:

| Before this wave | After this wave |
|---|---|
| `torchcodec` had to be hand-installed on first run | `py:torchcodec` listed by `dub doctor`, pulled in by `uv sync --extra all` |
| `google-genai` had to be hand-installed | `py:google_genai` listed by `dub doctor`, pulled in by `uv sync --extra all` |
| `gradio_client` had to be hand-installed for VoxCPM | pulled in by `uv sync --extra all` (in the `tts` extra) |
| Gemini key in `~/.zshrc` was invisible to `uv run` | `dub doctor` auto-recovers the key from `~/.zshrc` / `~/.bashrc` and prints a `note: auto-recovered ...` line |
| Operator had to read source to know which real deps exist | `dub doctor` lists every gate; `dub bootstrap` explains the rc-file caveat |

## What changed

### `pyproject.toml` extras
- `translation` extra: added `torchcodec>=0.13.0`
- `tts` extra: added `gradio_client>=0.16.0`
- `asr` extra: added `torchcodec>=0.13.0`
- `all` extra: aggregate of the above

### `src/dub/cli.py`
- `doctor` now appends two new gates: `py:google_genai`, `py:torchcodec`.
- `doctor` now calls `_auto_recover_missing_secrets()` before checking
  `gemini_api_key`, so an unset env var does not cause a misleading
  `MISSING` line for operators who have the key in `~/.zshrc`.
- `_auto_recover_missing_secrets()` reads `~/.zshrc` and `~/.bashrc`,
  only for the secret names `dub doctor` cares about
  (`GOOGLE_API_KEY`, `GEMINI_API_KEY`).
- Existing env values are never overridden.
- On any parse / IO error, the helper silently no-ops; the doctor still
  reports the real status, and the operator can fix it manually.
- `bootstrap` text extended with: torchcodec/google-genai are pulled in
  by `--extra all`; the rc-file caveat; and a `dub doctor` pointer.

### `tests/test_cli.py`
- `test_dub_doctor_reports_real_backend_python_gates` — `dub doctor`
  must list both new gates.
- `test_auto_recover_missing_secrets_reads_zshrc` — monkeypatches
  `Path.home` to a fake `home/.zshrc` with the key; verifies recovery.
- `test_auto_recover_does_not_override_existing` — when env is set,
  rc-file is not consulted.

## Live verification

```text
$ uv run dub doctor --config .tmp_real_backend_en2zh.yaml
ffmpeg: OK (/opt/homebrew/bin/ffmpeg)
ffprobe: OK (/opt/homebrew/bin/ffprobe)
repo_pipeline_scripts: OK (.../vendor/pipeline_scripts)
gemini_api_key: OK (GOOGLE_API_KEY,GEMINI_API_KEY)
py:google_genai: OK (google.genai importable in dub venv)
py:torchcodec: OK (torchcodec importable in dub venv)
note: auto-recovered GOOGLE_API_KEY,GEMINI_API_KEY from interactive shell rc
      (Hermes / CI shells do not load ~/.zshrc; re-run in a real zsh to set it permanently)
tts_backends:
  omnivoice: READY (all gates ok)
  voxcpme:   READY (all gates ok)
doctor ok: standalone prerequisites look ready
```

Test results:

```text
$ uv run pytest tests/test_cli.py -q
... 32 passed ...
```

The single pre-existing failure (`test_dub_doctor_reports_missing_prereqs`)
is fixed in the follow-up Lane 1.

## Doc alignment

- `README.md`: new "real-backend productization surface" paragraph
  pointing at the new gates and the auto-recovery note.
- `QUICKSTART.md`: dependency table now lists `torchcodec`,
  `google-genai`, `gradio_client`; mentions that `dub doctor` will
  auto-recover keys from `~/.zshrc`.
- `docs/release-handoff-checklist.md`: new section 4.5 enumerates the
  real-backend readiness gates; section 7 next-wave updated; section 8
  verdict now describes the real-backend productization surface.

## What this does NOT claim

- The default zsh rc still wins; auto-recovery is a per-process fallback.
- Model-quality validation still requires an independent pass; this
  wave only closes the runtime/readiness gap.
- Long-form / noisy / multi-speaker source media is still a follow-up.
