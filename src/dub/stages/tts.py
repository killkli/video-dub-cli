"""stages/tts.py — Stage 5: TTS generation with source-lang routing (en→OmniVoice, ja→VoxCPM)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from dub.stages.base import Stage, StageState
from dub.config import DubConfig
from dub.state import now_iso


class TtsStage(Stage):
    name = "05_tts"

    def is_done(self, project_dir: Path) -> bool:
        # Check all expected line_{i}_tts.wav exist
        ref_dir = project_dir / "04_ref_audio"
        if not ref_dir.exists():
            return False
        ref_files = sorted(ref_dir.glob("line_*_ref.wav"))
        if not ref_files:
            return False
        tts_dir = project_dir / "06_tts_wav"
        missing = [f for f in ref_files if not (tts_dir / f"{f.stem.replace('_ref','_tts')}.wav").exists()]
        return len(missing) == 0

    def _missing_lines(self, project_dir: Path) -> list[int]:
        ref_dir = project_dir / "04_ref_audio"
        tts_dir = project_dir / "06_tts_wav"
        ref_files = sorted(ref_dir.glob("line_*_ref.wav"))
        missing = []
        for rf in ref_files:
            stem = rf.stem  # e.g. "line_5_ref"
            tts_file = tts_dir / f"{stem.replace('_ref','_tts')}.wav"
            if not tts_file.exists():
                # extract number
                import re
                m = re.search(r"line_(\d+)_ref", rf.name)
                if m:
                    missing.append(int(m.group(1)))
        return missing

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        state = StageState(name=self.name, status="running", started_at=now_iso())
        state.attempts = 1

        log_file = project_dir / ".dub" / f"{self.name}.log"
        source_lang = config.defaults.source_lang

        if source_lang == "ja":
            script = config.paths.skills_dir / "dubbing_batch_tts_vox.py"
            py = config.paths.omnivoice_python
            # VoxCPM path
            cmd = [
                str(py), str(script),
                "--zh-srt", str(project_dir / "05_translated_srt" / "video.zhtw.srt"),
                "--en-srt", str(project_dir / "03_asr" / "video.srt"),
                "--ref-dir", str(project_dir / "04_ref_audio"),
                "--out-dir", str(project_dir / "06_tts_wav"),
            ]
        else:
            # en → OmniVoice
            script = config.paths.skills_dir / "dubbing_batch_tts.py"
            py = config.paths.omnivoice_python
            cmd = [
                str(py), str(script),
                "--zh-srt", str(project_dir / "05_translated_srt" / "video.zhtw.srt"),
                "--en-srt", str(project_dir / "03_asr" / "video.srt"),
                "--ref-dir", str(project_dir / "04_ref_audio"),
                "--out-dir", str(project_dir / "06_tts_wav"),
            ]

        with open(log_file, "w") as fh:
            result = subprocess.run(
                cmd,
                stdout=fh,
                stderr=subprocess.STDOUT,
                check=False,
            )

        if result.returncode != 0:
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"exit {result.returncode}"
            return state

        artifacts = [p.name for p in (project_dir / "06_tts_wav").glob("line_*_tts.wav")]
        state.artifacts = sorted(artifacts)
        state.output_dir = "06_tts_wav"
        state.status = "done"
        state.finished_at = now_iso()
        return state