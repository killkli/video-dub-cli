from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from dub.config import DubConfig
from dub.runtime_paths import pipeline_script
from dub.stages.stems import StemsStage


def test_stems_is_done_accepts_actual_video_mp4_vocals_filename(tmp_path):
    proj = tmp_path / "proj"
    raw = proj / "01_raw_video"
    stems = proj / "02_stems"
    raw.mkdir(parents=True)
    stems.mkdir(parents=True)
    video = raw / "video.mp4"
    video.write_bytes(b"raw-video")
    produced = stems / "video.mp4.vocals.wav"
    produced.write_bytes(b"stem-audio")
    produced.touch()

    assert StemsStage().is_done(proj) is True


def test_stems_is_done_false_for_legacy_wrong_filename_only(tmp_path):
    proj = tmp_path / "proj"
    raw = proj / "01_raw_video"
    stems = proj / "02_stems"
    raw.mkdir(parents=True)
    stems.mkdir(parents=True)
    video = raw / "video.mp4"
    video.write_bytes(b"raw-video")
    wrong = stems / "video.vocals.wav"
    wrong.write_bytes(b"stem-audio")
    wrong.touch()

    assert StemsStage().is_done(proj) is False


def test_run_uses_repo_owned_stems_script(tmp_path):
    proj = tmp_path / "proj"
    (proj / "01_raw_video").mkdir(parents=True, exist_ok=True)
    (proj / ".dub").mkdir(parents=True, exist_ok=True)
    (proj / "01_raw_video" / "video.mp4").write_bytes(b"fake")

    cfg = DubConfig()
    script = pipeline_script("dubbing_stems.py")

    assert script.name == "dubbing_stems.py"
    assert "vendor/pipeline_scripts" in str(script)
    state = StemsStage().run(proj, cfg)

    assert state.status == "failed"
    assert "exit" in (state.error or "")


def test_vendored_stems_script_resolves_repo_root_and_vocal_remover_module():
    script = pipeline_script("dubbing_stems.py")
    spec = importlib.util.spec_from_file_location("test_dubbing_stems", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("test_dubbing_stems", None)
    sys.modules["test_dubbing_stems"] = module
    spec.loader.exec_module(module)

    assert module._REPO_ROOT == script.parents[2]
    assert module._SRC_DIR == script.parents[2] / "src"
    assert module._VOCAL_REMOVER_MODULE == script.parents[2] / "src" / "vocal_remover"


def test_vendored_stems_script_passes_repo_src_first_in_pythonpath(tmp_path, monkeypatch):
    script = pipeline_script("dubbing_stems.py")
    spec = importlib.util.spec_from_file_location("test_dubbing_stems_env", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("test_dubbing_stems_env", None)
    sys.modules["test_dubbing_stems_env"] = module
    spec.loader.exec_module(module)

    project = tmp_path / "proj"
    raw = project / "01_raw_video"
    raw.mkdir(parents=True)
    (raw / "video.mp4").write_bytes(b"fake-video")

    recorded: dict[str, object] = {}

    def fake_run_cmd(cmd, check=True, env=None):
        recorded["cmd"] = cmd
        recorded["check"] = check
        recorded["env"] = env
        return object()

    monkeypatch.setattr(module, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(module.shutil, "copy2", lambda src, dst: Path(dst).write_bytes(Path(src).read_bytes()))
    monkeypatch.setattr(module, "get_duration", lambda _path: 0.0)
    monkeypatch.setattr(module, "build_instrumental", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(module, "_VOCAL_REMOVER_MODULE", module._SRC_DIR / "vocal_remover")
    monkeypatch.setenv("PYTHONPATH", "existing-suffix")
    monkeypatch.setattr(sys, "argv", [str(script), str(project)])

    module.main()

    env = recorded["env"]
    assert isinstance(env, dict)
    assert env["PYTHONPATH"] == f"{module._SRC_DIR}{os.pathsep}existing-suffix"
    assert recorded["cmd"][:3] == [str(Path(sys.executable)), "-m", "vocal_remover"]


def test_package_stems_stage_exports_real_implementation():
    from dub.stages import StemsStage as package_stage
    from dub.stages.base import StemsStage as base_stage
    from dub.stages.stems import StemsStage as real_stage

    assert package_stage is real_stage
    assert package_stage is not base_stage
