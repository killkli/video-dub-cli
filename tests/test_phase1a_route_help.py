"""Phase 1A — UX quick wins batch (Commit 3): human-readable route summary
and top-level help discoverability.

Locks in the new operator-facing contract for the auto-workflow success
path and the ``dub --help`` first-time-operator path:

* ``_route_basis_human()`` covers the four documented branches (None,
  ``override:``, ``detected:``, ``ambiguous:``) plus a safe fallback for
  unknown basis tokens.
* ``_human_route_summary()`` echoes the operator-friendly labels
  (English / Japanese / Chinese (Traditional) / OmniVoice / VoxCPM /
  Gemini) and degrades gracefully on unknown tokens.
* The three translate modes (``delegate``, ``skip``, ``use-existing``)
  produce three distinguishable ``translation:`` fragments.
* ``dub --help`` surfaces the canonical three-step first-time recipe
  (uv sync --extra all / dub doctor / dub auto) on its own lines, with
  no line-collapsing regression, and still lists every productized
  command.
* On a successful run, the ``route:`` human summary is emitted after
  the machine-oriented ``preflight:`` line — not before, and not instead
  of it — so existing audits and downstream tooling keep working.

These are focused regression tests for the Phase 1A plan's Commit 3
(``route / help wording``). They intentionally avoid touching the
pre-existing one-shot / route / run / validate coverage in
``test_cli.py`` and the doctor / bootstrap contract locked in by
``test_phase1a_doctor_bootstrap.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from dub.cli import (
    _human_route_summary,
    _route_basis_human,
    main,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# _route_basis_human — the four documented branches plus the safe fallback
# ---------------------------------------------------------------------------


def test_route_basis_human_handles_no_basis_token():
    """AC: when the resolver is never exercised (e.g. a hard-coded
    ``en2zh`` / ``ja2zh`` call) the human summary should still produce
    a self-contained sentence rather than printing ``None`` or empty
    parens."""
    out = _route_basis_human(None)
    assert "explicit" in out
    assert "no detector ran" in out


def test_route_basis_human_handles_explicit_override():
    """AC: when the operator passed ``--source-lang``, the human line
    must call that out explicitly so the operator knows the route was
    pinned and not auto-detected."""
    out = _route_basis_human("override:explicit-flag")
    assert "explicit --source-lang flag" in out
    assert "override:explicit-flag" in out


def test_route_basis_human_handles_auto_detected():
    """AC: when ``dub auto`` auto-detected the language, the human line
    must call that out — not bury the result inside the machine
    ``preflight:`` line. The chosen wording is "picked from probe" (not
    "auto-detected") so it does not collide with the probe-progress
    contract on ``dub auto`` that pins the stderr prefix ``auto-detect:``."""
    out = _route_basis_human("detected:en-asr-head")
    assert "picked from probe" in out
    assert "detected:en-asr-head" in out


def test_route_basis_human_handles_ambiguous():
    """AC: when the resolver was ambiguous, the human line must call
    that out so the operator knows why the run did not silently fall
    back to the configured default source lang."""
    out = _route_basis_human("ambiguous:no-ffmpeg")
    assert "ambiguous" in out
    assert "ambiguous:no-ffmpeg" in out


def test_route_basis_human_falls_back_safely_on_unknown_basis():
    """AC: a future basis token we have not taught the helper about
    must not crash; it must still produce a non-empty operator-friendly
    line and include the raw basis for audit."""
    out = _route_basis_human("future:probe-flux")
    assert "future:probe-flux" in out
    assert out  # non-empty


# ---------------------------------------------------------------------------
# _human_route_summary — friendly labels and the three translate modes
# ---------------------------------------------------------------------------


def test_human_route_summary_uses_friendly_labels_on_happy_path():
    """AC: on the canonical ``dub auto <VIDEO>`` happy path, the
    operator-facing line must translate ISO codes to friendly language
    names and name the TTS backend + translation provider so a
    first-time operator can read it in one glance."""
    out = _human_route_summary(
        source_lang="en",
        target_lang="zh",
        backend_name="omnivoice",
        translate_mode="delegate",
        translation_provider="gemini",
        project_dir=Path("/tmp/x.dub"),
        route_basis="detected:en-asr-head",
    )
    assert "route: English -> Chinese (Traditional) via OmniVoice" in out
    assert "translation: Gemini" in out
    assert "project=/tmp/x.dub" in out
    # "picked from probe" is the implementation's chosen wording for the
    # detected branch — it intentionally avoids the literal substring
    # "auto-detect" so the line does not collide with the probe-progress
    # stderr contract.
    assert "picked from probe" in out


def test_human_route_summary_flags_skip_translate_mode():
    """AC: when the operator passes ``--translate-mode skip`` the
    human line must clearly say we are reusing the existing project
    SRT, not silently re-translating."""
    out = _human_route_summary(
        source_lang="ja",
        target_lang="zh",
        backend_name="voxcpme",
        translate_mode="skip",
        translation_provider="gemini",
        project_dir=Path("/tmp/y.dub"),
        route_basis="override:explicit-flag",
    )
    assert "Japanese -> Chinese (Traditional) via VoxCPM" in out
    assert "translation: skipped (using existing project SRT)" in out
    assert "project=/tmp/y.dub" in out


def test_human_route_summary_flags_use_existing_translate_mode():
    """AC: ``--translate-mode use-existing --translated-srt <f>`` is
    a distinct operator path and must not collapse into the same
    fragment as ``skip``."""
    out = _human_route_summary(
        source_lang="en",
        target_lang="zh",
        backend_name="omnivoice",
        translate_mode="use-existing",
        translation_provider="gemini",
        project_dir=Path("/tmp/z.dub"),
        route_basis="override:explicit-flag",
    )
    assert "translation: skipped (using external SRT)" in out


def test_human_route_summary_degrades_gracefully_on_unknown_backend():
    """AC: a future TTS backend the helper has not been taught about
    must not crash the success line. The raw token is echoed so
    operators can recognize the backend, but the rest of the line
    stays intact."""
    out = _human_route_summary(
        source_lang="en",
        target_lang="zh",
        backend_name="future-flux",
        translate_mode="delegate",
        translation_provider="gemini",
        project_dir=Path("/tmp/q.dub"),
        route_basis="override:explicit-flag",
    )
    assert "future-flux" in out
    assert "English -> Chinese (Traditional)" in out
    assert "project=/tmp/q.dub" in out


def test_human_route_summary_degrades_gracefully_on_unknown_translation_provider():
    """AC: a future translation provider the helper has not been
    taught about must still produce a self-contained line."""
    out = _human_route_summary(
        source_lang="en",
        target_lang="zh",
        backend_name="omnivoice",
        translate_mode="delegate",
        translation_provider="future-translator",
        project_dir=Path("/tmp/r.dub"),
        route_basis="override:explicit-flag",
    )
    assert "future-translator" in out


def test_human_route_summary_defaults_provider_to_gemini_when_unset():
    """AC: a ``None`` translation provider on the ``delegate`` path
    must still produce a self-contained ``translation:`` fragment and
    must not crash. The productized default is Gemini, so the human
    line should name it explicitly."""
    out = _human_route_summary(
        source_lang="en",
        target_lang="zh",
        backend_name="omnivoice",
        translate_mode="delegate",
        translation_provider=None,
        project_dir=Path("/tmp/s.dub"),
        route_basis="override:explicit-flag",
    )
    assert "translation: Gemini" in out


# ---------------------------------------------------------------------------
# dub --help — first-time-operator recipe stays readable + no command drift
# ---------------------------------------------------------------------------


def test_dub_help_surfaces_first_time_operator_recipe(runner):
    """AC: ``dub --help`` must include the canonical three-step
    first-time-operator recipe on its own lines so a first-time
    operator can read it without consulting the docs."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0, result.output
    assert "uv sync --extra all" in result.output
    assert "uv run dub doctor" in result.output
    assert "uv run dub auto" in result.output


def test_dub_help_recipe_lines_are_not_collapsed_into_one_garbled_line(runner):
    """AC: regression guard for a known Click gotcha — without a
    ``\\b`` blank-line-preserving marker in the docstring, Click joins
    adjacent indented lines into a single rewrapped paragraph and the
    ``uv run dub doctor`` and ``uv run dub auto <VIDEO>`` strings get
    glued onto the previous line. Each command must remain on its own
    rendered line."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    # Find every line that contains the first command of the recipe,
    # and assert none of those lines also contain any of the other two.
    first_cmd_lines = [
        line for line in lines
        if "uv sync --extra all" in line
    ]
    assert first_cmd_lines, "first-time recipe: missing 'uv sync --extra all' line"
    for line in first_cmd_lines:
        assert "uv run dub doctor" not in line, (
            f"first-time recipe: doctor line got merged into the "
            f"sync line: {line!r}"
        )
        assert "uv run dub auto" not in line, (
            f"first-time recipe: auto line got merged into the "
            f"sync line: {line!r}"
        )
    doctor_lines = [line for line in lines if "uv run dub doctor" in line]
    assert doctor_lines, "first-time recipe: missing 'uv run dub doctor' line"
    for line in doctor_lines:
        assert "uv run dub auto" not in line, (
            f"first-time recipe: auto line got merged into the "
            f"doctor line: {line!r}"
        )


def test_dub_help_recipe_points_to_durable_docs(runner):
    """AC: the recipe footer must hand the operator off to the durable
    operator docs (QUICKSTART.md + docs/operator-runbook.md) so they
    do not have to dig through repo internals to find more detail."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0, result.output
    assert "QUICKSTART.md" in result.output
    assert "docs/operator-runbook.md" in result.output


@pytest.mark.parametrize(
    "cmd",
    ["auto", "bootstrap", "doctor", "en2zh", "ja2zh",
     "resume", "status", "clean", "run", "validate"],
)
def test_dub_help_still_lists_every_productized_command(runner, cmd):
    """AC: adding the recipe must not hide or rename any of the
    productized commands. Operators who learned the command list
    from the previous help output must still find every command here.
    """
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0, result.output
    assert cmd in result.output, (
        f"dub --help dropped command {cmd!r} after the recipe addition"
    )


# ---------------------------------------------------------------------------
# End-to-end: the human route summary is echoed on the success path
# alongside the machine preflight line — not instead of it.
# ---------------------------------------------------------------------------


def test_dub_auto_success_emits_human_route_summary_after_preflight(
    runner, monkeypatch, tmp_path
):
    """AC: a successful ``dub auto`` run must emit the new human-readable
    ``route:`` line on its own line, *after* the existing machine
    ``preflight:`` line. Removing either one would break either the
    human-facing UX or the existing audit chain, so the test pins the
    order and the dual-emit contract."""
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"\x00")
    fake_project = tmp_path / "video.dub"
    fake_project.mkdir()

    captured: list[str] = []

    # Stub the auto-route resolver so we land on the success path
    # without exercising the 30s ASR head-probe or any ffmpeg probe.
    from dub.cli import AutoRouteDecision

    monkeypatch.setattr(
        "dub.cli._resolve_auto_route",
        lambda _video, _src, _cfg: AutoRouteDecision(
            source_lang="en", basis="detected:en-asr-head"
        ),
    )

    def _fake_preflight(project_dir, cfg, source_lang, route_basis=None):
        captured.append("preflight")
        return (
            f"preflight: src={source_lang} tgt=zh project={project_dir} "
            f"mode=delegate route=translate=delegate provider=gemini"
        )

    def _fake_human_route_summary(**_kw):
        captured.append("human_route")
        return (
            f"route: English -> Chinese (Traditional) via OmniVoice ; "
            f"translation: Gemini ; project={fake_project} ; "
            f"source language: auto-detected (basis=detected:en-asr-head)"
        )

    def _fake_bootstrap_state(project_dir, cfg):
        return None

    def _fake_refresh(project_dir, cfg):
        return None

    def _fake_run_pipeline(project_dir, cfg, yes=True):
        captured.append("run_pipeline")
        return None

    monkeypatch.setattr("dub.cli._run_preflight", _fake_preflight)
    monkeypatch.setattr("dub.cli._human_route_summary", _fake_human_route_summary)
    monkeypatch.setattr("dub.cli._bootstrap_state", _fake_bootstrap_state)
    monkeypatch.setattr(
        "dub.cli._refresh_runtime_input_state", _fake_refresh
    )
    monkeypatch.setattr("dub.cli.run_pipeline", _fake_run_pipeline)
    monkeypatch.setattr(
        "dub.cli._operator_paths_summary", lambda *_a, **_k: "operator-paths"
    )
    monkeypatch.setattr(
        "dub.cli._validate_run_contract", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        "dub.cli._default_auto_project_dir",
        lambda _v: fake_project,
    )

    # Make ``load_config`` return a stub with the attributes the
    # auto path reads (defaults.source_lang/target_lang + translation
    # + merge_cli_overrides).
    class _Cfg:
        class defaults:
            source_lang = "en"
            target_lang = "zh"

        class translation:
            mode = "delegate"
            provider = "gemini"

        @staticmethod
        def merge_cli_overrides(**_kw):
            return _Cfg

    monkeypatch.setattr("dub.cli.load_config", lambda _p: _Cfg)

    result = runner.invoke(main, ["auto", str(fake_video)])
    assert result.exit_code == 0, result.output

    # The order in the operator-facing run matters: preflight first
    # (machine), then the human route summary, then the stages.
    assert captured.index("preflight") < captured.index("human_route")
    assert captured.index("human_route") < captured.index("run_pipeline")

    # The captured human summary is also echoed in the operator-visible
    # stdout so it shows up in normal CLI output.
    assert "route: English -> Chinese (Traditional) via OmniVoice" in result.output
    # And the machine preflight line is still emitted (not replaced).
    assert "preflight:" in result.output
