"""Tests for the OmniVoice ``DUB_OMNIVOICE_ROOT`` env-var contract.

The OmniVoice TTS backend ships in this repo as
``vendor/pipeline_scripts/dubbing_batch_tts.py``. The script needs
the OmniVoice dev repo on ``sys.path`` (because the ``omnivoice``
package is not on PyPI yet) — that is a documented bootstrap step,
not a hidden repo coupling. This test pins the contract:

  1. ``DUB_OMNIVOICE_ROOT`` is the canonical env var the script
     reads (with ``OMNIVOICE_ROOT`` as a legacy alias for backwards
     compatibility).
  2. If neither env var is set, the script exits with a clear
     error (no silent hard-coded fallback to one developer's
     machine).
  3. If the env var points at a path that does not look like a
     valid OmniVoice checkout, the script exits with a clear
     error that names the bad path and the missing marker file.

The test runs the script as a subprocess so we exercise the real
import-time guard without polluting the test interpreter's
``sys.path``.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
OMNIVOICE_SCRIPT = (
    REPO_ROOT / "vendor" / "pipeline_scripts" / "dubbing_batch_tts.py"
)


def _has_opencc() -> bool:
    """``opencc`` is part of the dub ``[tts]`` / ``[tts-vox]`` extras.
    The legacy-env-var test below needs the full OmniVoice stack
    importable, so we skip it when ``opencc`` is not installed (e.g.
    the operator has only synced ``[tts-omnivoice]``).
    """
    try:
        import opencc  # noqa: F401
    except ImportError:
        return False
    return True


def _has_torch() -> bool:
    """``torch`` is part of the dub ``[tts-omnivoice]`` extra. The
    legacy-env-var test below exercises the OmniVoice script's full
    import path, which needs torch; we skip when it is not present.
    """
    try:
        import torch  # noqa: F401
    except ImportError:
        return False
    return True


def _run_omnivoice_script(env: dict[str, str]) -> subprocess.CompletedProcess:
    """Invoke the OmniVoice vendored script and capture its exit / stderr.

    The script exits with code 2 when ``DUB_OMNIVOICE_ROOT`` is unset
    or points at an invalid path — this is by design (a clear
    contract failure beats a confusing ``ModuleNotFoundError`` from
    inside ``omnivoice.models.omnivoice``). We strip the heavy
    model-stack env vars so the test does not depend on torch /
    OmniVoice being installed.
    """
    # Start from a clean env: unset the legacy OMNIVOICE_ROOT and
    # DUB_OMNIVOICE_ROOT (the test passes only the env it wants).
    full_env = {k: v for k, v in os.environ.items()
                if k not in ("DUB_OMNIVOICE_ROOT", "OMNIVOICE_ROOT")}
    full_env.update(env)
    full_env["PYTHONPATH"] = str(REPO_ROOT / "src")
    return subprocess.run(
        [sys.executable, str(OMNIVOICE_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(REPO_ROOT),
        timeout=30,
        check=False,
    )


def test_dub_omnivoice_root_unset_exits_with_clear_error() -> None:
    """No env var → the script refuses to run with code 2 and
    a stderr message that names the missing variable and points
    the operator at ``dub bootstrap``.

    This is the contract fix: the script used to silently insert
    a hard-coded ``/Users/johnchen/Dev/OmniVoice`` path that would
    only work on one developer's machine. A clear exit-with-error
    beats a confusing import failure on someone else's box.
    """
    result = _run_omnivoice_script(env={})
    assert result.returncode == 2, (
        f"expected exit 2 (contract failure), got {result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "DUB_OMNIVOICE_ROOT" in result.stderr
    # The message points the operator at the next step.
    assert "dub bootstrap" in result.stderr


@pytest.mark.skipif(
    not (_has_opencc() and _has_torch()),
    reason="legacy OMNIVOICE_ROOT alias test needs full OmniVoice stack "
    "(uv sync --extra tts-omnivoice --extra tts-vox)",
)
def test_legacy_omnivoice_root_alias_still_works() -> None:
    """The legacy ``OMNIVOICE_ROOT`` env var is still accepted so
    existing operator shell scripts do not break.

    Today the script does not actually need the package to be
    importable — argparse runs before the OmniVoice model loads —
    so we can probe the alias path with a valid fake checkout
    (anything that contains ``omnivoice/models/omnivoice.py``
    that exports a stub ``OmniVoice`` class). The test just
    confirms argparse runs to completion (exit 0) when the env
    var is set, regardless of whether the model itself can load.
    The deep model load is exercised by the real TTS pipeline,
    not by this unit test."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        fake_checkout = Path(tmp) / "OmniVoice"
        marker_dir = fake_checkout / "omnivoice" / "models"
        marker_dir.mkdir(parents=True)
        # Provide a stub OmniVoice class so the import in the
        # script succeeds. The class body is empty — argparse
        # runs before any code touches it.
        (marker_dir / "omnivoice.py").write_text(
            "class OmniVoice:\n"
            "    @staticmethod\n"
            "    def from_pretrained(*args, **kwargs):\n"
            "        raise RuntimeError('stub for env-var probe test')\n"
        )
        result = _run_omnivoice_script(env={"OMNIVOICE_ROOT": str(fake_checkout)})
    # The script reads the env var, validates the path, imports
    # the stub, and falls into argparse (which prints help and
    # exits 0). We do NOT require the model to load — that is a
    # runtime concern, not a contract concern.
    assert result.returncode == 0, (
        f"OMNIVOICE_ROOT alias should still be honoured; got {result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_invalid_omnivoice_root_exits_with_path_named() -> None:
    """If the env var points at a path that does not look like a
    valid OmniVoice checkout, the script exits with code 2 and
    names both the bad path and the marker file the operator
    should expect to see there.

    This is the operator-ergonomics layer: an empty / wrong /
    typo'd path produces a clear error rather than a confusing
    ``ModuleNotFoundError`` from deep inside the OmniVoice package.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        bad_path = Path(tmp) / "not-omnivoice"
        bad_path.mkdir()
        result = _run_omnivoice_script(env={"DUB_OMNIVOICE_ROOT": str(bad_path)})
    assert result.returncode == 2
    assert str(bad_path) in result.stderr
    assert "omnivoice/models/omnivoice.py" in result.stderr
