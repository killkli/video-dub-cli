"""stages/ref_audio.py — Stage 3: Extract per-segment reference audio from video+SRT.

Real wire: invokes repo-owned `vendor/pipeline_scripts/dubbing_extract_ref.py`
(resolved via config.paths.skills_dir) which uses ffmpeg to slice
01_raw_video/video.mp4 into 04_ref_audio/line_<i>_ref.wav
based on the SRT cue timestamps in 03_asr/video.srt.

Output format: 24kHz mono pcm_s16le (OmniVoice ref_audio contract).
Aggressive trim is intentionally avoided — we keep natural onsets so the TTS
model has clean prosody/voice reference.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from dub.config import DubConfig
from dub.runtime_paths import pipeline_script
from dub.state import StageState
from dub.stages.base import Stage


_SRT_TS_RE = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
)


def _count_srt_cues(srt_path: Path) -> int:
    """Count non-empty caption blocks in an SRT file. Tolerant of CRLF / BOM."""
    if not srt_path.exists():
        return 0
    try:
        text = srt_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = srt_path.read_text(encoding="utf-8", errors="replace")
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return 0
    count = 0
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        # A valid block has at least: index, time, text
        lines = block.split("\n")
        if len(lines) < 2:
            continue
        # Look for the time arrow on any line; the time line typically comes
        # after the index but we accept either ordering for robustness.
        if any(_SRT_TS_RE.search(ln) for ln in lines):
            count += 1
    return count


def _list_ref_wavs(ref_dir: Path) -> list[Path]:
    if not ref_dir.exists():
        return []
    return sorted(ref_dir.glob("line_*_ref.wav"))


class RefAudioStage(Stage):
    """Stage 3: extract per-cue ref audio from raw video using ASR SRT cues."""

    name = "03_ref_audio"

    def is_done(self, project_dir: Path) -> bool:
        """True iff 03_asr/video.srt exists AND every cue has a corresponding
        line_<i>_ref.wav in 04_ref_audio/. We do NOT depend on stems here —
        the script slices from 01_raw_video/video.mp4 directly so the ref
        matches the original vocal track.
        """
        srt_path = project_dir / "03_asr" / "video.srt"
        if not srt_path.exists():
            return False
        expected = _count_srt_cues(srt_path)
        if expected == 0:
            return False
        ref_dir = project_dir / "04_ref_audio"
        existing = _list_ref_wavs(ref_dir)
        if len(existing) < expected:
            return False
        # Verify each SRT index 1..expected has its wav (some SRTs have
        # non-contiguous indices, but the script names by SRT index not
        # position, so this is the correct invariant).
        for i in range(1, expected + 1):
            if not (ref_dir / f"line_{i}_ref.wav").exists():
                return False
        return True

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        state = StageState(status="running", started_at=_now_iso(), attempts=1)

        video_mp4 = project_dir / "01_raw_video" / "video.mp4"
        srt_path = project_dir / "03_asr" / "video.srt"
        ref_dir = project_dir / "04_ref_audio"
        log_file = project_dir / ".dub" / f"{self.name}.log"

        if not video_mp4.exists():
            state.status = "failed"
            state.finished_at = _now_iso()
            state.error = f"raw video missing: {video_mp4}"
            return state
        if not srt_path.exists():
            state.status = "failed"
            state.finished_at = _now_iso()
            state.error = f"ASR SRT missing: {srt_path}"
            return state

        ref_dir.mkdir(parents=True, exist_ok=True)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        script = pipeline_script("dubbing_extract_ref.py")
        # Script signature: <video.mp4> <source.srt> <output_dir/>
        # The trailing slash matters — the script uses Path.resolve() and
        # mkdir(parents=True, exist_ok=True) on it.
        cmd = [
            "python3",
            str(script),
            str(video_mp4),
            str(srt_path),
            str(ref_dir) + "/",
        ]

        with open(log_file, "w", encoding="utf-8") as log_fh:
            result = subprocess.run(
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )

        if result.returncode != 0:
            state.status = "failed"
            state.finished_at = _now_iso()
            state.error = f"dubbing_extract_ref.py exited with code {result.returncode}; see {log_file}"
            return state

        # Verify the script actually produced every expected ref wav.
        expected = _count_srt_cues(srt_path)
        produced = [p.name for p in _list_ref_wavs(ref_dir)]
        missing = [
            f"line_{i}_ref.wav"
            for i in range(1, expected + 1)
            if not (ref_dir / f"line_{i}_ref.wav").exists()
        ]
        if missing:
            state.status = "failed"
            state.finished_at = _now_iso()
            state.error = (
                f"dubbing_extract_ref.py produced {len(produced)}/{expected} "
                f"ref wavs; missing: {', '.join(missing)}; see {log_file}"
            )
            return state

        state.artifacts = produced
        state.output_dir = "04_ref_audio"
        state.status = "done"
        state.finished_at = _now_iso()
        return state


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


__all__ = ["RefAudioStage", "_count_srt_cues"]
