#!/usr/bin/env python3
"""
dubbing_stems.py — Demucs stem separation for video-dubbing pipeline.

Adds a stem-separation preprocessing step BEFORE ASR/ref_audio:
  - ASR runs on the vocals stem (cleaner speech recognition)
  - ref_audio is extracted from the isolated vocal track
  - Non-vocal stems preserved for stem-preserving remix (future stage)

Usage:
    python dubbing_stems.py <project_dir> [video_filename]

Assumes project structure:
    project/
        01_raw_video/
            video.mp4          <- input
        02_stems/             <- created by this script
            video.vocals.wav
            video.drums.wav
            video.bass.wav
            video.other.wav
            video.instrumental.wav   # drums+bass+other mix
"""
import argparse
import subprocess
import sys
import shutil
from pathlib import Path

VOCAL_REMOVER_CLI = Path("/Users/johnchen/.hermes/projects/vocal-remover/.venv/bin/vocal-remover")


def run_cmd(cmd, check=True):
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout:
        for line in r.stdout.splitlines()[:12]:
            print(f"    {line}")
    if r.returncode != 0:
        if r.stderr:
            for line in r.stderr.splitlines()[:12]:
                print(f"    [stderr] {line}")
        if check:
            raise RuntimeError(f"Command failed with exit {r.returncode}")
        else:
            print(f"  WARNING: non-zero exit {r.returncode}, continuing")
    return r


def get_duration(wav_path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(wav_path)],
        capture_output=True, text=True
    )
    return float(r.stdout.strip() or 0)


def build_instrumental(stem_dir: Path, video_stem: str, out_path: Path) -> bool:
    """Mix available non-vocal stems (drums+bass+other) into instrumental bed."""
    drums = stem_dir / f"{video_stem}.drums.wav"
    bass  = stem_dir / f"{video_stem}.bass.wav"
    other = stem_dir / f"{video_stem}.other.wav"

    available = [s for s in [drums, bass, other] if s.exists()]
    if not available:
        print("  no non-vocal stems found, skipping instrumental bed")
        return False

    inputs = []
    for s in available:
        inputs += ["-i", str(s)]

    n = len(available)
    filter_str = f"amix=inputs={n}:duration=longest:normalize=0[aout]"

    r = subprocess.run(
        ["ffmpeg", "-y"] + inputs +
        ["-filter_complex", filter_str,
         "-map", "[aout]",
         "-ar", "44100", "-ac", "2", "-acodec", "pcm_s16le",
         str(out_path)],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"  instrumental mix failed: {r.stderr[-200:]}")
        return False
    dur = get_duration(out_path)
    print(f"  instrumental bed: {out_path.name} ({dur:.1f}s)")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Demucs stem separation for dubbing pipeline")
    parser.add_argument("project_dir", help="Project root directory")
    parser.add_argument("video_filename", nargs="?", default="video.mp4",
                        help="Video filename inside 01_raw_video/ (default: video.mp4)")
    parser.add_argument("--stems", default="all",
                        help="Comma-separated stems (default: all)")
    parser.add_argument("--model", default=None,
                        help="demucs model override (default: htdemucs_nano)")
    args = parser.parse_args()

    project    = Path(args.project_dir).resolve()
    video_path = project / "01_raw_video" / args.video_filename
    stems_dir  = project / "02_stems"

    if not project.exists():
        print(f"ERROR: project dir not found: {project}")
        sys.exit(1)
    if not video_path.exists():
        print(f"ERROR: video not found: {video_path}")
        sys.exit(1)

    stems_dir.mkdir(parents=True, exist_ok=True)
    print(f"Project:   {project}")
    print(f"Video:     {video_path}")
    print(f"Stems dir: {stems_dir}")

    # demucs writes output next to the input file.
    # Strategy: copy video to stems_dir, run demucs, then rename outputs.
    temp_video_copy = stems_dir / args.video_filename
    print(f"\n[1] Copy video to stems dir ...")
    shutil.copy2(video_path, temp_video_copy)

    if not VOCAL_REMOVER_CLI.exists():
        print(f"ERROR: vocal-remover CLI not found: {VOCAL_REMOVER_CLI}")
        print("Install: pip install ~/.hermes/projects/vocal-remover/")
        sys.exit(1)

    # vocal-remover CLI: takes --stems (comma-separated or 'all') as positional args
    # Output goes next to the input file (or to --output dir)
    cmd = [
        str(VOCAL_REMOVER_CLI),
        "--stems", args.stems,
        "--output", str(stems_dir),
        str(temp_video_copy),
    ]
    if args.model:
        cmd += ["--model", args.model]

    print(f"\n[2] Run demucs stem separation ...")
    print(f"  stems: {args.stems}")
    print(f"  model: {args.model or 'htdemucs (default)'}")
    run_cmd(cmd)

    # Rename demucs output to standard naming: <video>.<stem>.wav
    video_stem = temp_video_copy.stem  # "video" from "video.mp4"
    expected = ["vocals", "drums", "bass", "other"]
    renamed = {}

    for suffix in expected:
        raw      = stems_dir / f"{video_stem}.{suffix}.wav"
        standard = stems_dir / f"{args.video_filename}.{suffix}.wav"
        if raw.exists():
            raw.rename(standard)
            renamed[suffix] = standard
            dur = get_duration(standard)
            print(f"  OK  {standard.name} ({dur:.1f}s)")

    temp_video_copy.unlink(missing_ok=True)

    # Build instrumental bed
    if "other" in renamed:
        print(f"\n[3] Build instrumental bed ...")
        instrumental = stems_dir / f"{args.video_filename}.instrumental.wav"
        build_instrumental(stems_dir, args.video_filename, instrumental)

    # Summary
    print(f"\n{'='*50}")
    print(f"Done. Files in {stems_dir}:")
    for f in sorted(stems_dir.glob(f"{args.video_filename}.*")):
        dur = get_duration(f)
        print(f"  {f.name} ({dur:.1f}s)")

    print(f"\nNext steps:")
    print(f"  # ASR on vocals stem:")
    print(f"  qwenasr-mlx transcribe \\")
    print(f"    {stems_dir}/{args.video_filename}.vocals.wav \\")
    print(f"    --output-format srt --language en --output 03_asr/video.srt")
    print(f"  # Extract ref_audio from vocals:")
    print(f"  python dubbing_extract_ref.py \\")
    print(f"    {stems_dir}/{args.video_filename}.vocals.wav \\")
    print(f"    03_asr/video.srt 04_ref_audio/")


if __name__ == "__main__":
    main()
