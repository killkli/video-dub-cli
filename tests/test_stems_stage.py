from __future__ import annotations

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


def test_package_stems_stage_exports_real_implementation():
    from dub.stages import StemsStage as package_stage
    from dub.stages.base import StemsStage as base_stage
    from dub.stages.stems import StemsStage as real_stage

    assert package_stage is real_stage
    assert package_stage is not base_stage
