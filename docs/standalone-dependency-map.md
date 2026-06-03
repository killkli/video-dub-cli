# Standalone Dependency Map

> Canonical inventory of every runtime dependency `video-dub-cli` carries
> on external repos, Hermes skills, `~/.hermes` paths, external Python
> interpreters, and non-Python system tools. Each hotspot is grounded
> in the actual source (not memory) and paired with a proposed target
> ownership and a migration note. Verification date: 2026-06-03.

## Goal

A new user can use `video-dub-cli` end-to-end via:

    git clone <repo>
    uv sync                       # or pip install -e ".[all]"
    uv run dub doctor             # readiness check
    uv run dub en2zh talk.mp4

without cloning any other source repo, without pointing config at a
Hermes skill directory, and without owning a separate Python venv per
backend. Anything that cannot be vendored stays an explicit, checked
prerequisite (system tool, model cache, API key) — never a hidden
`~/.hermes/...` path.

## Hotspot inventory

Each entry is named (file:section) so reviewers can re-verify without
reading the whole repo. Class abbreviations:

- **VENDOR** — move the code into this repo (module, script, or sub-package).
- **REPLACE-PYPI** — substitute a PyPI package for what today is a custom
  script or interpreter.
- **SYSTEM-DEP** — keep as a system/CLI tool, surface via `dub doctor`.
- **BOOTSTRAP** — first-run download/setup that does not belong in git.

---

### H1. `src/dub/config.py:14-21` — `PathsConfig` defaults pinned to a single user's home

- `qwenasr_cli` default = `~/.hermes/projects/qwenasr-mlx-cli/.venv/bin/qwenasr-mlx`
- `omnivoice_python` default = `~/Dev/OmniVoice/.venv/bin/python3`
- `skills_dir` default = `~/.hermes/skills/media/video-dubbing-pipeline/scripts`
- `translation_skill` default = `~/.hermes/skills/media/subtitle-translation/subtitle_translation.py`
- `dub_root` default = `Path.home() / ".hermes"` (config.py:21)

Why it matters: every default assumes the operator's home is laid out
the way John's machine is laid out. A second operator gets
`FileNotFoundError`-flavored failures at the first stage even though
they may have all real tools installed elsewhere.

Target ownership:
- `skills_dir` — **REMOVE from config schema** (active stages 1/3/6
  will be vendor-inlined by T3; see H3/H4/H7). Keep the field on the
  pydantic model for one release behind a `deprecated` flag, so
  external test fixtures (`tests/conftest.py:38-46`,
  `tests/test_assemble_stage.py:436-465`) keep passing during
  transition. The default must move to `None`, not `~/.hermes/...`.
- `translation_skill` — **REMOVE from active runtime** (the committed
  `TranslateStage` no longer shells out to it; see
  `src/dub/stages/translate.py:11-86`). Keep the field for one release
  with default `None`, then drop it.
- `qwenasr_cli` — **REPLACE-PYPI**: treat as a discovered external
  command (`shutil.which("qwenasr-mlx")` or `pipx run qwenasr-mlx`),
  not a hard path. Surface as `dub doctor` SYSTEM-DEP.
- `omnivoice_python` — **REPLACE-PYPI**: kill the "second Python
  interpreter" model entirely. The TTS stage should import the
  backend package in-process (see H6). Until then, fall back to
  `sys.executable` (the dub venv) with a clear doctor warning that
  OmniVoice's `torch` deps must be installed in that venv.
- `dub_root` — change default to `Path.home() / "video-dub-cli-runs"`
  (already in `DEFAULT_PATHS` at config.py:101, but the
  `PathsConfig` pydantic field default at config.py:21 still says
  `~/.hermes`). Make the canonical default match the runtime default.

Risk: dropping `skills_dir`/`translation_skill` is a hard contract
change. We can do it because no shipped stage uses either anymore
(`grep -rn 'skills_dir\|translation_skill' src/` confirms: every
remaining read is a config or test fixture, not an active stage call).
Tests will need fixture updates — see H10.

---

### H2. `src/dub/config.py:9` + `src/dub/state.py:11` — `pydantic` import missing from `pyproject.toml`

- `from pydantic import BaseModel, Field, ValidationError` in
  `config.py:9` and `state.py:11`.
- `pyproject.toml:8-15` declares: `click`, `rich`, `pyyaml`, `tenacity`,
  `loguru`. **No `pydantic`**.
- The previously built `src/video_dub_cli.egg-info/requires.txt:3` does
  list `pydantic>=2.6.0` — so the actual install set included pydantic
  transitively (loguru/tenacity may have pulled it, or a separate
  install line in the prior venv) but the explicit dep declaration is
  gone from `pyproject.toml`. That's a packaging bug, not a dependency
  on an external repo.

Target ownership: **REPLACE-PYPI** (add `pydantic>=2.6.0` to
`dependencies`). Trivial fix; T2 owns it.

---

### H3. `src/dub/stages/stems.py:20-47` — Stage 1 shells out to external `dubbing_stems.py`

- Wire: `python3 <skills_dir>/dubbing_stems.py <project_dir> video.mp4`
- Output contract: `02_stems/video.*.wav` (the stage globs that path at
  stems.py:51 and trusts whatever the script produced).
- `is_done()` only checks `02_stems/video.vocals.wav` mtime >
  raw mp4 mtime (stems.py:18). The canonical "vocals.wav +
  instrumental.wav" contract lives in `stages/base.py:96-107`
  (alternative `StemsStage`), which `subprocess` directly drives
  `ffprobe` + `ffmpeg lavfi` (base.py:51-69). The two `StemsStage`
  classes are not wired to the same registry.

Target ownership: **VENDOR**. Three options, ranked:

1. **Preferred**: keep the external-script contract but move the
   script into this repo as `src/dub/stages/_vendor/dubbing_stems.py`
   and resolve via `importlib.resources` instead of `skills_dir`. This
   is the smallest change that kills the `~/.hermes` default. Stage
   1 keeps the subprocess contract so existing operator scripts
   (Demucs flags, cache logic) carry over verbatim.
2. **Alternative**: promote the in-process ffmpeg-only `StemsStage`
   from `stages/base.py:96-107` to be the canonical one and demote
   the subprocess version. This loses Demucs vocal separation, which
   is what makes the real `02_stems/video.vocals.wav` actually
   separated rather than silence; do not pick this without redoing
   the demux story.
3. **Hybrid**: vendor the script AND plumb an optional "use real
   demucs" flag, so the operator can pick. T3 picks option 1 unless
   they find option 3 is also small.

The test in `tests/test_runner_smoke.py` does not assert a stems
subprocess command (it mocks all 6 stages indirectly), so
`tests/test_stems_stage.py` doesn't exist — the only real test of
this stage is end-to-end via `tests/integration/test_6a_smoke.py`,
which is fixture-driven, not script-name-driven.

---

### H4. `src/dub/stages/ref_audio.py:90-160` — Stage 3 shells out to external `dubbing_extract_ref.py`

- Wire: `python3 <skills_dir>/dubbing_extract_ref.py <video.mp4> <srt> <out_dir/>`
- The trailing `/` on the output dir is part of the contract
  (ref_audio.py:121; asserted in
  `tests/test_ref_audio_stage.py:152-153`).
- Output contract: `04_ref_audio/line_<i>_ref.wav` for every SRT cue
  index 1..N (ref_audio.py:142-146). `is_done()` cross-checks the
  SRT cue count against the on-disk ref wavs.

Target ownership: **VENDOR**. Same pattern as H3: move
`dubbing_extract_ref.py` into the repo, resolve via
`importlib.resources`. The script itself is a thin ffmpeg-slicer;
the "real" logic is ffmpeg flags, which we already document
(SYSTEM-DEP, see H8). Stage 3 module then does:

    script = importlib.resources.files("dub.stages._vendor") \
                .joinpath("dubbing_extract_ref.py")

instead of `config.paths.skills_dir / "dubbing_extract_ref.py"`.

Test impact: `tests/test_ref_audio_stage.py:148` asserts the
subprocess command includes `cfg.paths.skills_dir / "dubbing_extract_ref.py"`.
This test must be updated when we change the resolution source.
T3 owns the test update.

---

### H5. `src/dub/stages/asr.py:20-66` — Stage 2 shells out to `qwenasr-mlx`

- Wire: `<qwenasr_cli> transcribe <video.mp4> --output-format srt [--language <src>]`
- `qwenasr_cli` is a *binary* path (not a Python interpreter):
  `subprocess.run([str(cli), ...])` (asr.py:33). The default
  `~/.hermes/projects/qwenasr-mlx-cli/.venv/bin/qwenasr-mlx` is
  itself a console-script entry point generated by the
  `qwenasr-mlx-cli` repo at `pip install` time.

Target ownership: **SYSTEM-DEP / REPLACE-PYPI**. Two paths:

1. **Acceptable v1**: keep `qwenasr_cli` as a configurable external
   command. Default becomes `shutil.which("qwenasr-mlx")` (or
   `pipx run qwenasr-mlx`). `dub doctor` checks it exists and prints
   install instructions if missing. The T0/T1 contract holds:
   "users install qwenasr-mlx, we shell out to it."
2. **Preferred long-term**: if `qwenasr-mlx` is itself on PyPI
   (`pipx install qwenasr-mlx` or `pip install qwenasr-mlx`) we
   collapse the `qwenasr_cli` config to `extras_require` and call
   via `python -m qwenasr_mlx` from the dub venv. This drops the
   "another repo" story entirely.

The ASR stage in-process would need a Python ASR library (whisper,
mlx-whisper, etc.) that this repo does not currently depend on.
Wiring that up is a T5-style decision, not a packaging fix.

Test impact: `tests/test_asr_stage.py:36` asserts
`seen["cmd"][0] == str(cfg.paths.qwenasr_cli)`. Update the assertion
when the default resolution changes.

---

### H6. `src/dub/stages/tts.py:62-65, 282-294` — Stage 5 shells out to two external TTS scripts, with a separate Python interpreter

- Wire A (en → OmniVoice):
    `<omnivoice_python> <skills_dir>/dubbing_batch_tts.py
       --zh-srt <srt> --en-srt <srt>
       --ref-dir <dir> --out-dir <dir>`
  (`stages/tts.py:144-149`, route resolved at tts.py:62-65)
- Wire B (ja → VoxCPM):
    `<omnivoice_python> <skills_dir>/dubbing_batch_tts_vox.py
       --project-dir <p> --zh-srt <srt> --ja-srt <srt>
       --ref-dir <dir> --out-dir <dir>`
  (same place; the VoxCPM route is the only one that requires
  `--project-dir`).
- `omnivoice_python` is a *Python interpreter* path
  (stages/tts.py:282-285). The stage currently forces *both* routes
  through the OmniVoice venv interpreter, on the rationale that
  "VoxCPM doesn't import torch" — but the tts stage comment at
  tts.py:276-281 explicitly admits this is a shortcut that pins one
  interpreter. **Both backends need the same Python now.**

Target ownership: **VENDOR + REPLACE-PYPI**. This is the largest
open lane (T5's lane), and it has two layers:

- **Shell scripts (`dubbing_batch_tts.py`, `dubbing_batch_tts_vox.py`)**:
  these are real, substantive scripts. They have atomic-write
  contracts (`os.replace` after the recent P3-T7 fix), `--start/--end`
  support (added in the same fix), and per-cue error handling. They
  must be vendored as `src/dub/tts_engines/omnivoice/runner.py` and
  `src/dub/tts_engines/voxcpme/runner.py` (paths illustrative), and
  invoked via `python -m dub.tts_engines.omnivoice` from the dub
  venv.
- **The two engine packages themselves (`omnivoice`, `vox-cpm`)**:
  these are external PyPI / GitHub packages with non-trivial
  install stories (torch + MPS for OmniVoice, gradio_client for
  VoxCPM). Move them to optional extras:
    - `[tts-omnivoice]` extras: `torch`, `torchaudio`, plus a
      `omnivoice` PyPI pin (or vendored wrapper if not on PyPI).
    - `[tts-vox]` extras: `gradio-client`, `opencc-python-reimplemented`.
  The `dub doctor --tts` subcommand reports which extras are
  installed and which routes are usable.

The "second Python interpreter" assumption is the single biggest
remaining architectural debt in the pipeline. Killing it (running
both engines under `sys.executable`) is what unblocks removing
`omnivoice_python` from `PathsConfig`.

Test impact: `tests/test_tts_stage.py:51-54` constructs a config
with `cfg.paths.omnivoice_python = Path("/usr/bin/python3")`. Test
must be updated to construct a config without that field, or with
a sentinel that triggers the new "import engine in-process" path.

---

### H7. `src/dub/stages/assemble.py:102-220` — Stage 6 shells out to two external scripts

- Wire A: `python3 <skills_dir>/dubbing_assemble_loudnorm.py
             --video <mp4> --zh-srt <srt> --tts-dir <dir>
             --output <mp4> --save-normalized-wav <wav>`
  (assemble.py:134-141)
- Wire B: `python3 <skills_dir>/dubbing_remix.py
             --project-dir <p> --vocal-mix <wav> --output <stem.mp4>
             --vocal-gain <db> --inst-gain <db>`
  (assemble.py:189-196)
- Test: `tests/test_assemble_stage.py:194-200` asserts the exact
  remix CLI shape (12 elements, in that order) — that contract
  freezes the script's argv.

Target ownership: **VENDOR**. Same pattern as H3/H4. Move both
scripts into the repo. The loudnorm builder is ffmpeg-driven
(SYSTEM-DEP, see H8); the remix script is ffmpeg-driven plus
optional numpy/soundfile for normalization. The vendored versions
can be much shorter than the originals because most of the
behavior is ffmpeg filter graphs that we already document
elsewhere.

Test impact: `tests/test_assemble_stage.py:194, 444, 463` all
assert `cfg.paths.skills_dir / "dubbing_remix.py"` in the command.
These assertions need to be updated to point at the vendored
location.

---

### H8. System dependencies that must remain external

These are not Python and should not be vendored. They are
documented as prerequisites and checked by `dub doctor`:

- **`ffmpeg` / `ffprobe`** — used by:
    - `src/dub/stages/base.py:51-69` (`_video_duration`,
      `_ensure_silence_wav`)
    - `src/dub/project.py:37-43` (`get_duration_sec`)
    - inside all four vendored stage scripts (stems, ref_audio,
      assemble, remix) once they live in-repo
  Class: **SYSTEM-DEP**. `dub doctor` runs `ffmpeg -version` and
  `ffprobe -version`, fails readiness if either is missing.
- **Demucs (`python -m demucs`)** — needed by the real stems
  stage. Demucs's install story is `pip install demucs`, and the
  vendored `dubbing_stems.py` shells to it. Class:
  **REPLACE-PYPI + BOOTSTRAP**. If users install `demucs` into the
  dub venv (e.g. via the proposed `[tts-stems]` extra), this
  collapses to a single venv. Model weights for Demucs are
  downloaded on first run (huggingface cache) — that's the
  bootstrap half.
- **Model caches** (Demucs, OmniVoice, VoxCPM, whisper-mlx, etc.) —
  Class: **BOOTSTRAP**. Documented as "first run downloads
  ~X GB; use `dub bootstrap --all` to prefetch." Never in git.
- **API keys for translation** — `GOOGLE_API_KEY` /
  `GEMINI_API_KEY`. Class: **SYSTEM-DEP** (operator-provided
  secret). `dub doctor` checks the env var is set when
  `translation.provider == "gemini"`.
- **Apple Silicon / MPS** — only relevant if VoxCPM / OmniVoice
  require it. Class: **SYSTEM-DEP**. `dub doctor --tts` notes when
  MPS is unavailable and the operator is on Intel macOS.
- **Optional `yt-dlp`** — if/when the CLI grows a "dub this URL"
  flow. Today the README/QUICKSTART only mention local files, so
  this is **not a current dependency** and we list it only as a
  forward-looking optional install.

---

### H9. `src/dub/translator_gemini.py:62-84` — Translation env reads `~/.hermes/.env`

- Reads `os.environ[cfg.api_env_var]` first, then falls back to
  `Path.home() / ".hermes" / ".env"`. The `~/.hermes/.env` fallback
  is the only place this repo hard-codes a `~/.hermes` path that
  is not in `PathsConfig` defaults.
- The Gemini SDK itself (`google-genai`) is not in
  `pyproject.toml:8-15`, but is in
  `src/video_dub_cli.egg-info/requires.txt:9` as part of the
  `[translation]` extra. Same packaging-drift issue as H2.

Target ownership: **REPLACE-PYPI + REPLACE-ENV-COUPLING**.

- Add `python-dotenv` to base deps, load `.env` from the **current
  working directory** (CWD) first, then `~/.config/dub/.env` (XDG
  style), then `Path.home() / ".hermes" / ".env"` as a deprecated
  fallback. Print a one-line `DeprecationWarning` the first time
  the fallback is hit so operators know to migrate.
- Add `google-genai` and `httpx` to a `[translation]` extra
  (already present in egg-info; restore in `pyproject.toml`).
  The mock provider path in `translator_gemini.py:171-172` works
  without those packages, so unit tests do not need them.

---

### H10. Test coupling to legacy config fields

Multiple test files construct configs that still pass
`skills_dir`, `translation_skill`, and `omnivoice_python`:

- `tests/conftest.py:38-46` — `minimal_config_yaml` writes a config
  with all five path fields populated.
- `tests/test_config.py:42-80` — `test_paths_config_defaults` and
  friends pass all four required path fields explicitly.
- `tests/test_tts_stage.py:51-54` — `cfg.paths.omnivoice_python = Path("/usr/bin/python3")`.
- `tests/test_assemble_stage.py:436-465` — `cfg.paths.skills_dir = tmp_path / "empty-skills"`.

This coupling is OK as long as we keep the pydantic fields
populated. When we mark them `Optional` or remove them, every one
of these tests must be updated in the same change. T3 (and T5 for
TTS) own those updates — they cannot be done as a follow-up.

---

### H11. `pyproject.toml` extras contract (target shape)

Target shape after T2 (and T5's proposed additions):

    [project]
    dependencies = [
        "click>=8.1.7",
        "rich>=13.7.0",
        "pyyaml>=6.0.1",
        "pydantic>=2.6.0",       # missing today — H2
        "tenacity>=8.2.3",
        "loguru>=0.7.2",
        "python-dotenv>=1.0.0",  # new — H9
    ]

    [project.optional-dependencies]
    translation = [
        "httpx>=0.27.0",
        "google-genai>=1.0.0",
    ]
    asr = [
        "soundfile>=0.12.1",     # for whisper-mlx fallback, future-proofing
    ]
    stems = [
        "demucs>=4.0.0",         # real stem separation (was implicit)
    ]
    tts-omnivoice = [
        "torch>=2.0.0",
        "torchaudio>=2.0.0",
        # omnivoice itself once on PyPI
    ]
    tts-vox = [
        "gradio-client>=0.7.0",
        "opencc-python-reimplemented>=0.1.7",
    ]
    all = [every extra concatenated]
    dev = [
        "pytest>=8.0.0",
        "pytest-cov>=5.0.0",
        "mypy>=1.10.0",
        "ruff>=0.5.0",
    ]

Base = CLI/config/state/translation-mock + `dub doctor` +
`dub bootstrap --check`. The `dub run` happy path for *en → zh* in
mock-translation mode works on base alone. Real translation,
real ASR, real TTS, and real stem separation each require one or
more extras, which `dub doctor` reports.

---

## Remaining unavoidable system dependencies

After T1–T8 land, the only non-Python things a new operator must
install are:

1. Python 3.11+ (system package or pyenv)
2. `uv` (single static binary)
3. `ffmpeg` and `ffprobe` on `$PATH`
4. API key for the chosen translation provider, in env or in
   `~/.config/dub/.env` (with `~/.hermes/.env` as a deprecated fallback)
5. The extras matching the routes they want to run:
   - `[asr]` for the `qwenasr-mlx` route
   - `[stems]` for real Demucs stem separation
   - `[tts-omnivoice]` and/or `[tts-vox]` for real TTS

The `dub doctor` command must report on (1)–(5) explicitly. Anything
else, the operator has not been told to install.

## Migration risks / unknowns

### R1. TTS in-process import is the biggest open question
Both OmniVoice and VoxCPM have non-trivial Python entry points.
Killing the separate-`omnivoice_python` model requires either
(a) both packages being importable from a single venv, or (b) a
spawn-per-route pattern that uses the dub venv interpreter.
Today we are at (b) by accident. T5 must decide and prove the
chosen path with an integration test. Until that test passes,
ship the vendored scripts and keep the `omnivoice_python` field
populated as a transitional escape hatch.

### R2. Demucs install size and licensing
Demucs itself is large (multiple GB of model weights) and its
license is MIT but the weights are CC-BY-NC-SA. Operators who
want a clean-room "no source repo clones" experience will need
`dub bootstrap --stems` to pre-fetch weights with a clear license
acknowledgement. We should not pretend this is a "single `uv
sync`" experience for real stem separation.

### R3. `dub doctor` is a new public surface
Today there is no `dub doctor` command. The CLI surface in
`src/dub/cli.py` is `run`, `resume`, `status`, `clean`, `validate`.
Adding `doctor` and `bootstrap` is a T2 deliverable. If T2/T3/T4/T5
land without a working `dub doctor`, the truthfulness claim
"uv run dub doctor reports remaining prerequisites" cannot be
verified, and we should not claim "fully standalone" yet.

### R4. Test fixtures that point at fake `skills_dir`
Once `skills_dir` is removed from `PathsConfig`, the fixtures in
`tests/conftest.py` and `tests/integration/conftest.py` need to
either (a) construct configs without that field, or (b) write
fake scripts to `importlib.resources`-resolved locations. Option
(a) is cleaner; option (b) requires a fixture-only `tmp_path`
monkey-patch into the importlib resource tree. Pick one in T3 and
apply consistently.

### R5. `qwenasr-mlx` PyPI story is unknown
If `qwenasr-mlx` is not on PyPI and the project lives only on
GitHub/Codeberg, the "no extra repo clone" promise still requires
users to `pip install git+https://...` or `pipx install` from a
git URL. T2 should resolve this — either publish to PyPI, or
document the install command clearly in QUICKSTART as the one
exception to the "PyPI only" rule. Today this is the one
"still need a non-PyPI source" gap.

### R6. `~/.hermes/.env` fallback deprecation
The fallback in `translator_gemini.py:62-71` exists for backwards
compatibility with operators who set their API key there. Removing
it outright would break existing setups. Recommend: keep reading
from `~/.hermes/.env` for one release with a `DeprecationWarning`,
and add a `dub config migrate-env` command (T4 deliverable) that
copies the key into `~/.config/dub/.env` and unsets the legacy
path.

## Acceptance target for this wave

The standalone-repo-uv wave is successful when:

- `uv sync` in a fresh clone installs everything `dub run` needs
  for a real `en → zh` mock-translation pipeline.
- `uv run dub doctor` reports on Python, ffmpeg, qwenasr-mlx,
  demucs, OmniVoice / VoxCPM extras, and translation API keys —
  none of which require the operator to read a `~/.hermes`-flavored
  config.
- No active stage in the normal CLI path references
  `~/.hermes/skills/...` or `paths.skills_dir`.
- `pyproject.toml` declares the real runtime dep set (H2 fixed,
  H9 fixed, H11 landed).
- All migration risks in R1–R6 are either resolved or
  explicitly tracked as known-acceptable in the wave's handoff.

Out of scope for this wave:

- Re-licensing model weights.
- Changing the wire formats between stages (P3-T0 contract is
  frozen for the duration of the wave).
- Replacing Demucs with a different stem-separation backend.
- A GUI or web frontend.
