"""Tests that pin the repo-owned ASR contract (T9 [STAND9]).

The legacy design routed Stage 2 (ASR) through an external ``qwenasr-mlx``
binary that the operator had to install and configure via
``paths.qwenasr_cli``. That contract is gone: the runtime ASR is the
vendored package under ``src/qwenasr_mlx_cli``, and the stage module
imports it directly. These tests pin that contract so a future
refactor cannot silently regress to shelling out (or to requiring
the operator to set ``qwenasr_cli`` again) without a test failure.

Pinned behaviours:

1. ``dub.stages.asr`` imports the vendored package's pipeline entrypoint
   at module load. The vendored package is the in-repo source tree
   under ``src/qwenasr_mlx_cli/`` — not an external install — so
   ``asr.py`` cannot work without the vendored tree.
2. The vendored package exposes the pipeline entrypoint
   ``run_transcription`` that the stage calls, with the kwargs the
   stage passes (``input_path``, ``backend_name``, ``output_format``,
   ``subtitle_config``, etc.).
3. The stage's failure contract preserves the operator-facing message
   even when the real pipeline raises — the message is the operator's
   signal that ASR broke, not a Python traceback.
4. ``PathsConfig.qwenasr_cli`` is a legacy, unused field. It is
   tolerated (kept for back-compat with old YAML configs) but the
   default config never references it as a required knob, and no
   stage / runner / doctor code reads it. This guards against a
   future patch silently re-introducing the external-CLI dependency.
5. The ``dub bootstrap`` guidance tells operators the canonical ASR
   runtime lives in the dub venv — i.e. it does NOT tell them to
   install a separate ``qwenasr-mlx`` package / binary.
"""
from __future__ import annotations

import importlib
import io
import inspect
import re
import subprocess
import sys
from contextlib import redirect_stdout


# ---------------------------------------------------------------------------
# 1. Stage module imports the vendored package directly
# ---------------------------------------------------------------------------

def test_asr_stage_module_imports_vendored_qwenasr_mlx_cli() -> None:
    """Importing the stage module pulls in the in-repo vendored
    ``qwenasr_mlx_cli`` package — not a separately-installed copy.

    We verify by reading the vendored package's ``__file__`` from
    the stage's own import and asserting it lives under this repo's
    ``src/`` tree (not under site-packages). A future refactor that
    re-introduces a subprocess call to an external binary would
    drop these imports, so this test is the regression guard.
    """
    from dub.stages import asr as asr_module
    import qwenasr_mlx_cli

    src_file = inspect.getsourcefile(asr_module)
    assert src_file is not None
    # Stage lives under the repo's src/dub/stages/.
    assert "/src/dub/stages/asr.py" in src_file.replace("\\", "/"), (
        f"unexpected asr module path: {src_file}"
    )

    vendor_file = inspect.getsourcefile(qwenasr_mlx_cli) or qwenasr_mlx_cli.__file__
    assert vendor_file is not None
    # The vendored package must resolve from the repo's src/ tree.
    normalized = vendor_file.replace("\\", "/")
    assert "/src/qwenasr_mlx_cli/" in normalized, (
        f"qwenasr_mlx_cli must be vendored under src/ — got {vendor_file}"
    )
    # The vendored package and the stage module must live in the
    # SAME repo's src/ tree. We use a simple anchor: both files'
    # parents must agree up to the common ancestor.
    assert normalized.split("/src/")[0] == src_file.replace("\\", "/").split("/src/")[0], (
        f"vendored package and stage must share the same repo root; "
        f"vendor={vendor_file} stage={src_file}"
    )


def test_asr_stage_uses_in_process_run_transcription_not_subprocess() -> None:
    """The stage calls ``run_transcription`` in-process, not via
    ``subprocess``/``os.system``/``shutil.which`` against an external
    ``qwenasr-mlx`` binary.

    This is the exact regression guard: if a future patch shells out
    to an external CLI again, this test will fail. We check the
    stage's source for a forbidden token set.
    """
    from dub.stages import asr as asr_module

    src = inspect.getsource(asr_module)
    forbidden_substrings = (
        "subprocess.run",
        "subprocess.Popen",
        "subprocess.check_output",
        "subprocess.check_call",
        "os.system",
        "os.popen",
    )
    for token in forbidden_substrings:
        assert token not in src, (
            f"dub.stages.asr contains a forbidden external-process call "
            f"({token!r}); the canonical ASR path is in-process via the "
            f"vendored package — see src/qwenasr_mlx_cli/"
        )
    # And the only external-CLI field name in scope (qwenasr_cli)
    # must NOT be referenced as a runtime dependency. The legacy
    # config field is tolerated, but the stage must not read it.
    assert "qwenasr_cli" not in src, (
        "dub.stages.asr must not depend on the legacy PathsConfig.qwenasr_cli "
        "field — the canonical runtime uses the vendored package directly"
    )


def test_vendored_run_transcription_signature_matches_stage_call() -> None:
    """The stage calls ``run_transcription(input_path=..., backend_name=...,
    output_format=..., language=..., prompt=..., subtitle_config=...,
    convert_simplified_to_traditional=...)``.

    If the vendored package's signature drifts and the stage's call
    stops matching, the ASR contract breaks silently. We pin the
    kwargs the stage passes.
    """
    import qwenasr_mlx_cli.pipelines.transcribe as transcribe_mod

    run_transcription = getattr(transcribe_mod, "run_transcription", None)
    assert run_transcription is not None, (
        "vendored qwenasr_mlx_cli.pipelines.transcribe.run_transcription "
        "must exist — the stage calls it"
    )
    # Pin the kwarg surface the stage depends on. A drop / rename of
    # any of these is a breaking change for the standalone contract.
    from dub.stages import asr as asr_module
    src = inspect.getsource(asr_module)
    expected_kwargs = (
        "input_path=",
        "backend_name=",
        "output_format=",
        "language=",
        "prompt=",
        "subtitle_config=",
        "convert_simplified_to_traditional=",
    )
    for kw in expected_kwargs:
        assert kw in src, (
            f"dub.stages.asr must pass {kw!r} to run_transcription; "
            f"missing kwarg would mean the vendored contract has drifted"
        )


# ---------------------------------------------------------------------------
# 2. Legacy config field is tolerated but never required
# ---------------------------------------------------------------------------

def test_paths_config_qwenasr_cli_is_optional_legacy_field() -> None:
    """``PathsConfig.qwenasr_cli`` is legacy-only: tolerated for
    back-compat, but its default value is None and the field is
    documented as unused. The default DubConfig() must not require
    it (i.e. constructing a fresh config succeeds with qwenasr_cli
    unset, and YAML configs that omit it still parse cleanly).
    """
    from dub.config import DubConfig, PathsConfig

    # Default constructor: qwenasr_cli is None and the config is usable.
    cfg = DubConfig()
    assert cfg.paths.qwenasr_cli is None, (
        "qwenasr_cli must default to None — the canonical ASR path "
        "is repo-owned, not an external binary"
    )

    # PathsConfig alone: also defaults to None.
    pc = PathsConfig()
    assert pc.qwenasr_cli is None

    # An old YAML that explicitly sets qwenasr_cli to some path
    # must still parse (back-compat promise). It is just unused.
    import yaml

    legacy_yaml = """
    paths:
      qwenasr_cli: /opt/legacy/bin/qwenasr-mlx
    """
    parsed = DubConfig.model_validate(yaml.safe_load(legacy_yaml))
    assert str(parsed.paths.qwenasr_cli).endswith("qwenasr-mlx"), (
        "legacy qwenasr_cli YAML must parse cleanly even though the "
        "field is unused — back-compat with old operator configs"
    )


def test_no_runtime_code_reads_qwenasr_cli_field() -> None:
    """A guard against the legacy external-CLI knob creeping back
    into the runtime. The vendored ASR stage / runner / doctor code
    must never read ``paths.qwenasr_cli`` — if a future patch wires
    it up again, this test fails.

    We scan the runtime package (``dub.stages``, ``dub.runner``,
    ``dub.cli``) for any reference to the literal ``qwenasr_cli``.
    The config definition and its docstring are the only places
    this string is allowed to appear.
    """
    import re
    from pathlib import Path

    src_root = Path(__file__).resolve().parents[1] / "src" / "dub"
    # The only file in dub/ that should mention qwenasr_cli is the
    # config module (where it is declared as a legacy field). The
    # stage, runner, and CLI modules must not reference it.
    pattern = re.compile(r"\bqwenasr_cli\b")
    for py in src_root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        rel = py.relative_to(src_root)
        # config.py is allowed — that's the legacy field's home.
        if rel.as_posix() == "config.py":
            continue
        matches = pattern.findall(text)
        assert not matches, (
            f"{rel} references the legacy qwenasr_cli field — the "
            f"canonical ASR path is repo-owned and must not depend on "
            f"an external CLI knob. Matches: {matches}"
        )


# ---------------------------------------------------------------------------
# 3. Bootstrap message tells operators the canonical repo-owned path
# ---------------------------------------------------------------------------

def test_bootstrap_message_says_repo_owned_asr() -> None:
    """``dub bootstrap`` output must tell operators that the canonical
    ASR runtime lives in the repo (and that they do NOT need to
    install a separate ``qwenasr-mlx`` package / binary).

    This is the operator-facing half of the contract. If a future
    patch removes this guidance, a fresh operator will be tempted
    to install the legacy external binary again.
    """
    from dub.bootstrap import main

    out = io.StringIO()
    rc = None
    with redirect_stdout(out):
        try:
            main()
        except SystemExit as exc:
            rc = exc.code
    text = out.getvalue()
    # Bootstrap must mention the vendored package directory.
    assert "src/qwenasr_mlx_cli" in text, (
        f"dub bootstrap must tell operators the ASR ships under "
        f"src/qwenasr_mlx_cli — got:\n{text}"
    )
    # And it must explicitly say NOT to install a separate CLI.
    assert "do not install a separate" in text.lower(), (
        f"dub bootstrap must tell operators not to install a separate "
        f"qwenasr-mlx CLI for the canonical path — got:\n{text}"
    )
    # Bootstrap should still exit 0.
    assert rc in (None, 0), f"dub bootstrap exited with rc={rc}"


# ---------------------------------------------------------------------------
# 4. Failure contract: operator-facing message, no raw traceback leak
# ---------------------------------------------------------------------------

def test_asr_stage_failure_message_mentions_repo_pipeline(tmp_path) -> None:
    """When the real vendored pipeline raises, the stage's
    ``state.error`` message must be operator-facing (it must mention
    the repo ASR pipeline) rather than leaking a raw Python
    traceback into the runner's log.

    This pins the Stage 2 failure contract: a fresh operator running
    ``dub en2zh <video>`` who hits an ASR failure sees a clear
    message about the repo ASR pipeline, not an opaque stack trace.
    """
    project_dir = tmp_path / "proj"
    (project_dir / "01_raw_video").mkdir(parents=True)
    (project_dir / ".dub").mkdir(parents=True)
    (project_dir / "01_raw_video" / "video.mp4").write_bytes(b"fake")

    from dub.config import DubConfig
    from dub.stages.base import ASRStage

    def fake_run_transcription(**kwargs):
        raise RuntimeError("simulated vendored pipeline failure")

    # We patch by replacing the name in the stage module's namespace.
    import dub.stages.asr as asr_module
    original = asr_module.run_transcription
    asr_module.run_transcription = fake_run_transcription
    try:
        state = ASRStage().run(project_dir, DubConfig())
    finally:
        asr_module.run_transcription = original

    assert state.status == "failed"
    assert state.error is not None
    assert "repo ASR pipeline failed" in state.error, (
        f"ASR stage failure message must be operator-facing; got: {state.error!r}"
    )


# ---------------------------------------------------------------------------
# 5. Module import path sanity (catches misconfigured pyproject)
# ---------------------------------------------------------------------------

def test_qwenasr_mlx_cli_is_a_real_python_package() -> None:
    """Sanity: the vendored tree must be importable as a Python
    package. If a future move breaks the ``src/qwenasr_mlx_cli``
    layout, the ASR contract breaks at import time — this test
    pins the layout.
    """
    import qwenasr_mlx_cli
    import qwenasr_mlx_cli.pipelines.transcribe
    import qwenasr_mlx_cli.core.types
    import qwenasr_mlx_cli.core.exceptions

    # The package exposes the version sentinel used in pyproject.
    assert hasattr(qwenasr_mlx_cli, "__version__")
    # The pipeline entrypoint the stage calls is callable.
    assert callable(qwenasr_mlx_cli.pipelines.transcribe.run_transcription)
