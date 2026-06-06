"""Phase 1A — UX quick wins batch (Commit 2): doctor / bootstrap messaging.

Locks in the new operator-facing contract that ``dub doctor`` and
``dub bootstrap`` must satisfy after the Phase 1A UX batch:

* ``dub doctor`` blocked-lane output includes a concrete ``doctor fix:``
  line for each failing gate, plus a closing ``doctor next:`` pointer.
* ``dub doctor`` success path includes a canonical ``uv run dub auto
  <VIDEO>`` invocation as the recommended next action.
* ``dub bootstrap`` ends with explicit ``bootstrap next:`` and
  ``bootstrap first-run:`` summary lines that tie bootstrap to
  ``dub doctor`` and the canonical smoke command.

These are focused regression tests for the Phase 1A plan's Commit 2
(``doctor/bootstrap messaging``). They intentionally avoid touching
the pre-existing one-shot / route / run / validate coverage in
``test_cli.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from dub.cli import main
from dub.config import DubConfig, PathsConfig
from dub.tts_engines.contract import TtsReadiness


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _patch_all_checks_ok(monkeypatch, import_ok: bool = True) -> None:
    """Force every top-level + backend gate to read OK / READY."""
    import dub.cli as cli_mod

    monkeypatch.setattr("dub.cli._auto_recover_missing_secrets", lambda: [])
    monkeypatch.setattr("dub.cli._which_status", lambda _name: (True, "/bin/fake"))
    monkeypatch.setattr("dub.cli._path_status", lambda _p: (True, "/fake/path"))
    monkeypatch.setattr("dub.cli._env_status", lambda *_names: (True, "GOOGLE_API_KEY"))
    monkeypatch.setattr(
        "dub.tts_engines.diagnostics.python_imports",
        lambda _name, interpreter=None: ("ok", "/fake/import/path.py") if import_ok else ("missing", "ModuleNotFoundError: nope"),
    )
    monkeypatch.setattr(
        "dub.cli.load_config",
        lambda _config_path=None: DubConfig(paths=PathsConfig(stems_python=Path(sys.executable))),
    )

    ready = TtsReadiness(backend="fake", ready=True, detail="fake-ready", checks=[])
    monkeypatch.setattr(cli_mod, "omnivoice_readiness", lambda _cfg: ready)
    monkeypatch.setattr(cli_mod, "voxcpme_readiness", lambda _cfg: ready)
    monkeypatch.setattr(cli_mod, "builtin_backends", lambda: ("omnivoice", "voxcpme"))


def test_dub_doctor_success_includes_canonical_next_command(runner, monkeypatch):
    """AC: ``dub doctor`` on a fully-ready host must end with a canonical
    ``uv run dub auto <VIDEO>`` pointer so a first-time operator does not
    have to guess whether to use ``uv run``, plain ``dub``, etc."""
    _patch_all_checks_ok(monkeypatch)

    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0, result.output
    # Existing contract — kept.
    assert "ready for `dub auto`, `dub en2zh`, `dub ja2zh`" in result.output
    # New contract — canonical invocation is included.
    assert "uv run dub auto <VIDEO>" in result.output


def test_dub_doctor_prints_remediation_lines_when_top_level_gate_missing(runner, monkeypatch):
    """AC: a missing top-level gate (e.g. ``gemini_api_key``) must surface
    a concrete ``doctor fix:`` line so the operator can act on it without
    reading the docs."""
    import dub.cli as cli_mod

    monkeypatch.setattr("dub.cli._auto_recover_missing_secrets", lambda: [])
    monkeypatch.setattr("dub.cli._which_status", lambda _name: (True, "/bin/fake"))
    monkeypatch.setattr("dub.cli._path_status", lambda _p: (True, "/fake/path"))
    # gemini gate forced to missing.
    monkeypatch.setattr("dub.cli._env_status", lambda *_names: (False, "GOOGLE_API_KEY"))
    monkeypatch.setattr(
        "dub.tts_engines.diagnostics.python_imports",
        lambda _name, interpreter=None: ("ok", "/fake/import/path.py"),
    )

    ready = TtsReadiness(backend="fake", ready=True, detail="fake-ready", checks=[])
    monkeypatch.setattr(cli_mod, "omnivoice_readiness", lambda _cfg: ready)
    monkeypatch.setattr(cli_mod, "voxcpme_readiness", lambda _cfg: ready)
    monkeypatch.setattr(cli_mod, "builtin_backends", lambda: ("omnivoice", "voxcpme"))

    result = runner.invoke(main, ["doctor"])
    assert result.exit_code != 0, result.output
    # Existing contract — kept.
    assert "gemini_api_key: MISSING" in result.output
    assert "doctor found missing prerequisites" in result.output
    # New contract — a concrete fix line for the missing gate.
    assert "doctor fix:" in result.output
    assert "GOOGLE_API_KEY" in result.output
    # And a closing "next" pointer so the operator knows what to do after the fix.
    assert "doctor next:" in result.output


def test_dub_doctor_prints_remediation_lines_when_backend_gate_blocked(runner, monkeypatch):
    """AC: a blocked TTS backend (e.g. ``voxcpme`` service down) must
    surface a concrete ``doctor fix:`` line that includes the
    backend-specific command (e.g. how to start the local server)."""
    import dub.cli as cli_mod

    monkeypatch.setattr("dub.cli._auto_recover_missing_secrets", lambda: [])
    monkeypatch.setattr("dub.cli._which_status", lambda _name: (True, "/bin/fake"))
    monkeypatch.setattr("dub.cli._path_status", lambda _p: (True, "/fake/path"))
    monkeypatch.setattr("dub.cli._env_status", lambda *_names: (True, "GOOGLE_API_KEY"))
    monkeypatch.setattr(
        "dub.tts_engines.diagnostics.python_imports",
        lambda _name, interpreter=None: ("ok", "/fake/import/path.py"),
    )

    # omnivoice ready, voxcpme blocked with a service gate failure.
    omni_ready = TtsReadiness(backend="omnivoice", ready=True, detail="ok", checks=[])
    vox_blocked = TtsReadiness(
        backend="voxcpme",
        ready=False,
        detail="service down",
        checks=[("service", "missing", "127.0.0.1:8808 unreachable")],
    )
    monkeypatch.setattr(cli_mod, "omnivoice_readiness", lambda _cfg: omni_ready)
    monkeypatch.setattr(cli_mod, "voxcpme_readiness", lambda _cfg: vox_blocked)
    monkeypatch.setattr(cli_mod, "builtin_backends", lambda: ("omnivoice", "voxcpme"))

    result = runner.invoke(main, ["doctor"])
    assert result.exit_code != 0, result.output
    # Lane summary still surfaces the blocked route.
    assert "blocked=`dub ja2zh`" in result.output
    # New contract: a concrete fix line for the voxcpme service gate.
    assert "doctor fix:" in result.output
    # The fix line must mention the local server start command.
    assert "dub.tts_engines.voxcpme.server" in result.output
    # And a closing "next" pointer.
    assert "doctor next:" in result.output


def test_dub_bootstrap_ends_with_explicit_next_step(runner):
    """AC: ``dub bootstrap`` must end with an explicit summary line
    that ties bootstrap → doctor → first smoke. This replaces the old
    "too informational" ending where the operator had to infer the
    canonical sequence themselves."""
    result = runner.invoke(main, ["bootstrap"])
    assert result.exit_code == 0, result.output
    # Existing contract — kept.
    assert "uv sync" in result.output
    assert "GOOGLE_API_KEY" in result.output
    # New contract — explicit "next" pointer.
    assert "bootstrap next:" in result.output
    assert "dub doctor" in result.output
    assert "dub auto" in result.output
    # And a first-run canonical sequence that includes stems bootstrap.
    assert "bootstrap first-run:" in result.output
    assert "uv sync --extra all" in result.output
    assert "uv sync --extra stems" not in result.output
    assert "dub bootstrap-stems" in result.output


def test_dub_doctor_prints_no_remediation_lines_when_all_gates_ok(runner, monkeypatch):
    """AC: a fully-OK doctor must NOT print ``doctor fix:`` lines —
    remediation is only for failing gates. This guards against
    accidentally over-eager remediation emission that would clutter
    the green path."""
    _patch_all_checks_ok(monkeypatch)

    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "doctor fix:" not in result.output
    # Success path still has the canonical "next" pointer.
    assert "doctor next:" in result.output


def test_dub_doctor_stems_readiness_checks_tqdm_gate(runner, monkeypatch):
    """Regression: stems readiness must probe every import gate the vendored
    runtime needs, including ``tqdm``, so doctor cannot print a false READY
    before stage 01_stems runs."""
    _patch_all_checks_ok(monkeypatch)

    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "stems:" in result.output
    assert "deps:demucs_mlx: OK" in result.output
    assert "deps:tqdm: OK" in result.output
