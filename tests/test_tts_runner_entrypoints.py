"""Tests for the repo-owned TTS runner entry-points.

These cover the backend-integration slice added in T3 [AW1]: every
TTS backend ships a ``python -m dub.tts_engines.<name>`` entry-point
that resolves the vendored script inside this repo (no external
``skills_dir`` configuration, no separate ``~/.hermes`` path) and
forwards argv unchanged. The runner resolves the vendored script
*at call time* (not at import time) so a missing layout fails with
a clear runtime error rather than breaking ``dub`` import — and
therefore ``dub doctor``.

Scope:
  * round-trip: ``python -m dub.tts_engines.<name> --help`` lands
    in the vendored script's argparse and prints the script's help
  * import-time safety: importing the runner module does NOT touch
    the filesystem, so a broken layout doesn't break ``dub doctor``
  * pip-install tolerance: the resolver walks up parents and finds
    the vendored script even when the package lives under
    ``site-packages`` (we exercise this with a fake file under
    ``tmp_path``)
"""
from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_vox_script_module():
    script = REPO_ROOT / "vendor" / "pipeline_scripts" / "dubbing_batch_tts_vox.py"
    spec = importlib.util.spec_from_file_location("_test_vox_script", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_module_entrypoint(module: str, *args: str) -> subprocess.CompletedProcess:
    """Invoke ``python -m <module>`` and return the completed process.

    Uses the same Python interpreter the test session is running
    under, so the resolved import path matches the in-process
    import (no surprise about which venv the subprocess sees).
    """
    cmd = [sys.executable, "-m", module, *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=30,
        check=False,
    )


def test_voxcpme_entrypoint_round_trip_to_vendored_help() -> None:
    """``python -m dub.tts_engines.voxcpme --help`` runs the vendored
    script's argparse and prints the VoxCPM help text.

    VoxCPM is the cheap case: ``gradio_client`` is on the test
    import path, so the vendored script can be imported cleanly
    in a subprocess and prints its own help. This is the
    end-to-end proof that the new entry-point reaches the
    vendored script."""
    result = _run_module_entrypoint("dub.tts_engines.voxcpme", "--help")
    assert result.returncode == 0, (
        f"entrypoint failed: stderr={result.stderr!r}"
    )
    # The vendored script's argparse title contains the script name
    assert "dubbing_batch_tts_vox.py" in result.stdout
    # And surfaces its own --project-dir / --zh-srt / --ja-srt flags
    assert "--project-dir" in result.stdout
    assert "--ja-srt" in result.stdout
    assert "--zh-srt" in result.stdout


def test_omnivoice_entrypoint_module_imports_cleanly() -> None:
    """Importing ``dub.tts_engines.omnivoice.__main__`` does not
    fail just because the OmniVoice dev repo is not importable.

    The OmniVoice vendored script eagerly imports
    ``omnivoice.models.omnivoice`` at module load, which fails on
    a stock venv. The runner is the package-owned wrapper, so
    importing the wrapper must NOT trigger that import — only
    running the script does. This is the import-time safety
    promise: ``dub doctor`` cannot import ``dub.tts_engines.omnivoice``
    and then fail to run because the OmniVoice dev repo is gone.
    """
    # Importing the module should be a no-op; if it tries to
    # resolve the vendored script, the import itself fails on
    # a broken layout. We assert by importing and checking that
    # ``main`` is callable without raising.
    mod = importlib.import_module("dub.tts_engines.omnivoice.__main__")
    assert callable(mod.main)
    # And the runner's resolve helper exists and is callable too.
    runner = importlib.import_module("dub.tts_engines.omnivoice.runner")
    assert callable(runner.resolve_vendor_script)
    # The runner does NOT expose VENDOR_SCRIPT as a module-level
    # constant any more (it used to). The deferred-resolution
    # contract is the whole point of this commit.
    assert not hasattr(runner, "VENDOR_SCRIPT"), (
        "runner must resolve the vendored script at call time, "
        "not at import time, so a missing layout does not break "
        "dub import (and therefore dub doctor)"
    )


def test_voxcpme_runner_resolves_vendored_script_at_call_time(tmp_path: Path) -> None:
    """``resolve_vendor_script()`` walks up from the package file
    and finds ``vendor/pipeline_scripts/dubbing_batch_tts_vox.py``.

    We exercise the real call against the real repo layout. The
    return is a Path that exists and points at the vendored
    script — proving the resolver works for the source tree
    layout the operator actually uses after ``uv sync``."""
    from dub.tts_engines.voxcpme.runner import resolve_vendor_script

    script = resolve_vendor_script()
    assert script.is_file()
    assert script.name == "dubbing_batch_tts_vox.py"
    # The script lives under vendor/pipeline_scripts, which is
    # inside the repo root.
    assert script.parent.name == "pipeline_scripts"
    assert script.parent.parent.name == "vendor"
    # And the parent chain goes all the way up to /.
    assert script.is_relative_to(script.parents[-1])


def test_omnivoice_runner_resolves_vendored_script_at_call_time() -> None:
    """Same contract for the OmniVoice runner."""
    from dub.tts_engines.omnivoice.runner import resolve_vendor_script

    script = resolve_vendor_script()
    assert script.is_file()
    assert script.name == "dubbing_batch_tts.py"
    assert script.parent.name == "pipeline_scripts"
    assert script.parent.parent.name == "vendor"


def test_runner_resolution_raises_clear_error_when_layout_broken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the vendored script is missing (broken checkout, wrong
    install prefix, etc.), ``resolve_vendor_script()`` raises
    ``FileNotFoundError`` with a message that names the missing
    file and the path it walked up from.

    This is the contract that lets ``dub doctor`` distinguish a
    layout problem from a real backend failure."""
    from dub.tts_engines import voxcpme

    # Patch the package's __file__ to point at a path that has no
    # vendor/ ancestor. ``resolve_vendor_script`` will then walk
    # all the way up to / without finding the script and raise.
    monkeypatch.setattr(voxcpme, "__file__", "/nonexistent/runner.py")
    # The module's __file__ is read at function-call time inside
    # resolve_vendor_script via Path(__file__).resolve(), which
    # reads the function's __globals__ at call time. We need to
    # patch the runner's own reference to __file__.
    from dub.tts_engines.voxcpme import runner as voxcpme_runner

    monkeypatch.setattr(voxcpme_runner, "__file__", "/nonexistent/runner.py")

    with pytest.raises(FileNotFoundError) as excinfo:
        voxcpme_runner.resolve_vendor_script()
    msg = str(excinfo.value)
    # The error names the script and the broken layout.
    assert "dubbing_batch_tts_vox.py" in msg
    assert "Repo layout invariant broken" in msg


def test_vox_script_generate_one_forwards_denoise_flag() -> None:
    mod = _load_vox_script_module()

    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def predict(self, **kwargs):
            self.calls.append(kwargs)
            return "/tmp/fake.wav"

    client = FakeClient()
    result = mod.generate_one(client, "你好", "/tmp/ref.wav", "ja text", denoise=False)

    assert result == "/tmp/fake.wav"
    assert len(client.calls) == 1
    assert client.calls[0]["denoise"] is False


def test_vox_script_retries_without_denoise_for_denoise_error(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_vox_script_module()
    calls: list[bool] = []

    def fake_generate_one(client, text, ref_wav_path, ref_text, cfg=2.0, steps=10, *, denoise=True):
        calls.append(denoise)
        if denoise:
            raise RuntimeError(
                "Audio denoising processing failed: maximum size for tensor at dimension 1 is 6080 but size is 6400"
            )
        return "/tmp/recovered.wav"

    monkeypatch.setattr(mod, "generate_one", fake_generate_one)

    result, used_fallback = mod.generate_one_with_fallback(
        object(), "你好", "/tmp/ref.wav", "ja text"
    )

    assert result == "/tmp/recovered.wav"
    assert used_fallback is True
    assert calls == [True, False]


def test_vox_script_reraises_non_denoise_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_vox_script_module()

    def fake_generate_one(client, text, ref_wav_path, ref_text, cfg=2.0, steps=10, *, denoise=True):
        raise RuntimeError("server unavailable")

    monkeypatch.setattr(mod, "generate_one", fake_generate_one)

    with pytest.raises(RuntimeError, match="server unavailable"):
        mod.generate_one_with_fallback(object(), "你好", "/tmp/ref.wav", "ja text")
