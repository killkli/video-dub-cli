"""Tests for the vendored OmniVoice package contract.

The OmniVoice TTS backend now ships in this repo as:
- vendored runtime script: ``vendor/pipeline_scripts/dubbing_batch_tts.py``
- vendored minimal inference package: ``src/omnivoice``

This test pins the new contract:

  1. The script no longer requires ``DUB_OMNIVOICE_ROOT`` / ``OMNIVOICE_ROOT``.
  2. ``python vendor/pipeline_scripts/dubbing_batch_tts.py --help`` reaches
     argparse without an env-var gate failure.
  3. When the heavy OmniVoice deps are installed, the vendored package is
     importable from the repo's ``src`` tree.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
OMNIVOICE_SCRIPT = REPO_ROOT / "vendor" / "pipeline_scripts" / "dubbing_batch_tts.py"


def _has_omnivoice_runtime_stack() -> bool:
    try:
        import opencc  # noqa: F401
        import torch  # noqa: F401
        import torchaudio  # noqa: F401
        import transformers  # noqa: F401
        import accelerate  # noqa: F401
    except ImportError:
        return False
    return True


def _run_omnivoice_script_help(env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    if env:
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


def test_omnivoice_script_help_no_longer_requires_env_var() -> None:
    result = _run_omnivoice_script_help()
    assert result.returncode == 0, (
        f"expected argparse success, got {result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "DUB_OMNIVOICE_ROOT" not in result.stderr
    assert "OMNIVOICE_ROOT" not in result.stderr
    assert "--zh-srt" in result.stdout
    assert "--en-srt" in result.stdout
    assert "--ref-dir" in result.stdout


@pytest.mark.skipif(
    not _has_omnivoice_runtime_stack(),
    reason="vendored OmniVoice import test needs the full runtime stack "
    "(uv sync --extra tts-omnivoice --extra tts-vox or --extra all)",
)
def test_vendored_omnivoice_package_imports_from_repo_src() -> None:
    full_env = dict(os.environ)
    full_env["PYTHONPATH"] = str(REPO_ROOT / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from omnivoice.models.omnivoice import OmniVoice; print(OmniVoice.__name__)",
        ],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(REPO_ROOT),
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"vendored omnivoice import failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert result.stdout.strip() == "OmniVoice"
