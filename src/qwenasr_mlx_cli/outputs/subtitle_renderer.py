"""Subtitle renderers for SRT and WebVTT output formats."""

from qwenasr_mlx_cli.core.types import Segment


def _format_timestamp(seconds: float, *, vtt: bool = False) -> str:
    """Format a float-second timestamp as HH:MM:SS.mmm."""
    total_ms = int(round(seconds * 1000))
    hh = total_ms // 3_600_000
    mm = (total_ms % 3_600_000) // 60_000
    ss = (total_ms % 60_000) // 1_000
    ms = total_ms % 1_000
    if vtt:
        return f"{hh:02d}:{mm:02d}:{ss:02d}.{ms:03d}"
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def render_srt(segments: list[Segment]) -> str:
    """Render segments as SRT subtitle format.

    SRT format:
    1
    00:00:02,500 --> 00:00:05,300
    First subtitle text here.

    2
    00:00:06,100 --> 00:00:09,800
    Second subtitle text here.
    """
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        start_ts = _format_timestamp(seg.start)
        end_ts = _format_timestamp(seg.end)
        lines.append(f"{i}")
        lines.append(f"{start_ts} --> {end_ts}")
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)


def render_vtt(segments: list[Segment]) -> str:
    """Render segments as WebVTT subtitle format.

    VTT format:
    WEBVTT

    00:00:02.500 --> 00:00:05.300
    First subtitle text here.

    00:00:06.100 --> 00:00:09.800
    Second subtitle text here.
    """
    lines = ["WEBVTT", ""]
    for seg in segments:
        start_ts = _format_timestamp(seg.start, vtt=True)
        end_ts = _format_timestamp(seg.end, vtt=True)
        lines.append(f"{start_ts} --> {end_ts}")
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)