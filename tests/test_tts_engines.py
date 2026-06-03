from __future__ import annotations

from pathlib import Path

from dub.config import DubConfig
from dub.tts_engines import builtin_backends, engines_dir, list_registered
from dub.tts_engines.omnivoice import build_route as build_omnivoice_route
from dub.tts_engines.voxcpme import build_route as build_voxcpme_route


def test_builtin_backends_are_autoregistered():
    assert builtin_backends() == ["omnivoice", "voxcpme"]
    assert list_registered() == ["omnivoice", "voxcpme"]


def test_repo_owned_engines_dir_points_at_vendored_runtime_scripts():
    path = engines_dir()
    assert path.name == "pipeline_scripts"
    assert path.parent.name == "vendor"
    assert (path / "dubbing_batch_tts.py").exists()
    assert (path / "dubbing_batch_tts_vox.py").exists()


def test_omnivoice_route_uses_repo_owned_runtime_scripts(tmp_path):
    cfg = DubConfig()
    cfg.paths.skills_dir = tmp_path / "legacy-skills"
    cfg.paths.tts_engines_dir = tmp_path / "repo-tts"
    cfg.paths.omnivoice_python = Path("/usr/bin/python3")

    route = build_omnivoice_route(cfg, source_lang="en")

    assert route.script_path == engines_dir() / "dubbing_batch_tts.py"
    assert route.source_srt_flag == "--en-srt"
    assert route.needs_project_dir is False
    assert route.backend_name == "omnivoice"


def test_voxcpme_route_uses_repo_owned_runtime_scripts(tmp_path):
    cfg = DubConfig()
    cfg.paths.skills_dir = tmp_path / "legacy-skills"
    cfg.paths.tts_engines_dir = tmp_path / "repo-tts"

    route = build_voxcpme_route(cfg, source_lang="ja")

    assert route.script_path == engines_dir() / "dubbing_batch_tts_vox.py"
    assert route.source_srt_flag == "--ja-srt"
    assert route.needs_project_dir is True
    assert route.backend_name == "voxcpme"
