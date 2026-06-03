"""Tests for the standalone `dub-doctor` and `dub-bootstrap` script entrypoints.

These are the `[project.scripts]` declared in `pyproject.toml`; they must
resolve to a working `main()` callable and behave identically to the
`dub doctor` / `dub bootstrap` sub-commands.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout, redirect_stderr

import pytest


def test_dub_doctor_module_has_main():
    from dub.doctor import main

    assert callable(main)


def test_dub_bootstrap_module_has_main():
    from dub.bootstrap import main

    assert callable(main)


def test_dub_doctor_main_forwards_to_cli():
    """Calling dub.doctor.main() should run the diagnostic and exit.
    We don't assert a particular exit code because it depends on whether
    the host machine has every prereq installed."""
    from dub.doctor import main

    out = io.StringIO()
    err = io.StringIO()
    rc = None
    with redirect_stdout(out), redirect_stderr(err):
        try:
            main()
        except SystemExit as exc:
            rc = exc.code
    # Either it ran clean (rc None) or Click raised an error (rc != 0).
    assert rc is None or isinstance(rc, int)
    # Some output must have been produced (per-check OK/MISSING line).
    combined = out.getvalue() + err.getvalue()
    assert "ffmpeg" in combined


def test_dub_bootstrap_main_forwards_to_cli():
    """Bootstrap always exits 0 and prints guidance."""
    from dub.bootstrap import main

    out = io.StringIO()
    with redirect_stdout(out):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 0
    text = out.getvalue()
    assert "uv sync" in text
    assert "repo-owned pipeline scripts live under vendor/pipeline_scripts" in text
    assert "the only required external secret is GOOGLE_API_KEY / GEMINI_API_KEY" in text


def test_dub_bootstrap_module_runs_as_script():
    """`python -m dub.bootstrap` should work too (in addition to the
    `dub-bootstrap` console script declared in pyproject.toml)."""
    result = subprocess.run(
        [sys.executable, "-m", "dub.bootstrap"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "uv sync" in result.stdout


def test_dub_pyproject_declares_console_scripts():
    """pyproject.toml must register `dub`, `dub-doctor`, `dub-bootstrap`."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject.open("rb") as f:
        data = tomllib.load(f)
    scripts = data["project"]["scripts"]
    assert scripts["dub"] == "dub.cli:main"
    assert scripts["dub-doctor"] == "dub.doctor:main"
    assert scripts["dub-bootstrap"] == "dub.bootstrap:main"
