from __future__ import annotations

from dub.config import DubConfig
from dub.stages.stems import StemsStage


def test_run_fails_when_stems_script_missing(tmp_path):
    proj = tmp_path / "proj"
    (proj / "01_raw_video").mkdir(parents=True, exist_ok=True)
    (proj / ".dub").mkdir(parents=True, exist_ok=True)
    (proj / "01_raw_video" / "video.mp4").write_bytes(b"fake")

    empty_scripts = tmp_path / "empty-scripts"
    empty_scripts.mkdir()

    cfg = DubConfig()
    cfg.paths.skills_dir = empty_scripts

    state = StemsStage().run(proj, cfg)

    assert state.status == "failed"
    assert "stems script not found" in (state.error or "")
    assert "dubbing_stems.py" in (state.error or "")
