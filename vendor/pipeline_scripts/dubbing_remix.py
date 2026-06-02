#!/usr/bin/env python3
"""
dubbing_remix.py — Stem-preserving remix assembly for dubbed video.

Replaces ONLY the vocal layer, preserving original non-vocal stems (drums, bass, other/SFX).
This is a separate script from dubbing_assemble_loudnorm.py — kept parallel until QA passes.

Architecture:
  dubbed_tts_vocal_mix.wav + instrumental_bed → final_audio → mux with video

The TTS vocal mix is the "new vocal track" — it spans the full video duration (with silence
between dialogue clips, via adelay+apad). Non-vocal stems are kept as-is.

Gain controls (all tunable via CLI):
  --vocal-gain   dB gain applied to dubbed vocal (default: +3 dB to lift above instrumental)
  --inst-gain    dB gain applied to instrumental bed (default: -3 dB to duck under vocal)

Usage:
  python dubbing_remix.py \\
    --project-dir   /path/to/project \\
    --vocal-mix    05_tts_wav/tts_normalized.wav    (already loudnorm-normalized)
    --output        07_remix/video_dubbed.mp4

Expected project structure:
  project/
  ├── 01_raw_video/video.mp4          # original video (for mux)
  ├── 02_stems/
  │   ├── video.vocals.wav            # isolated vocal stem (from demucs, for reference)
  │   ├── video.instrumental.wav      # drums+bass+other mix
  │   └── video.other.wav             # sometimes useful for SFX
  ├── 04_translated_srt/video.srt     # subtitle for mux
  ├── 05_tts_wav/                     # OmniVoice output
  │   └── tts_normalized.wav          # loudnorm-normalized TTS vocal mix
  └── 07_remix/                       # output dir
"""
import argparse, subprocess, sys, json, re, tempfile
from pathlib import Path

# ── helpers ───────────────────────────────────────────────────────────────────

def pf(msg, end='\n'):
    print(msg, flush=True, end=end)

def get_dur(path: str) -> float:
    r = subprocess.run([
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'csv=p=0', path
    ], capture_output=True, text=True)
    v = r.stdout.strip()
    return float(v) if v and v != 'N/A' else 0.0

def parse_srt_duration(srt_path: str) -> float:
    """Return the end time of the last SRT entry — i.e. video total duration."""
    with open(srt_path, encoding='utf-8') as f:
        content = f.read().replace('\r\n', '\n').replace('\r', '\n')
    blocks = content.strip().split('\n\n')
    max_end = 0.0
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue
        try:
            ts_line = lines[1].strip()
            start_str, end_str = ts_line.split(' --> ')
            for part in [start_str, end_str]:
                part_clean = part.strip().replace(',', '.')
                h, m, rest = part_clean.split(':')
                s, ms = (rest.split('.') if '.' in rest else (rest, '0'))[:2]
                t = int(h)*3600 + int(m)*60 + float(f"{s}.{ms}")
                if part is end_str:
                    if t > max_end:
                        max_end = t
                else:
                    if t > max_end:
                        max_end = t  # track max for both
        except Exception:
            continue
    # just return max_end from parsing
    return max_end

def db_to_linear(db: float) -> float:
    """Convert dB to linear gain factor."""
    return 10 ** (db / 20.0)

# ── Stage 1: Prepare both tracks ───────────────────────────────────────────────

def prepare_tracks(vocal_wav: str, inst_wav: str,
                   tmp_vocal_48: str, tmp_inst_48: str,
                   video_dur: float) -> bool:
    """
    Ensure both tracks:
    - Same sample rate (48kHz for final delivery)
    - Same channel count (2 = stereo)
    - Same total duration (pad both to video_dur so they align)
    """
    pf('\n[Stage 1] Preparing tracks ...')
    total_ms = int(video_dur * 1000)

    # Vocal: convert to 48k stereo, pad to video_dur
    r = subprocess.run([
        'ffmpeg', '-y', '-i', vocal_wav,
        '-af', f'apad=whole_dur={total_ms}ms',
        '-ar', '48000', '-ac', '2', '-acodec', 'pcm_s16le',
        '-t', str(video_dur), tmp_vocal_48
    ], capture_output=True, text=True)
    if r.returncode != 0:
        pf(f'  vocal prep FAIL: {r.stderr[-500:]}')
        return False
    pf(f'  vocal: {get_dur(tmp_vocal_48):.2f}s')

    # Instrumental: convert to 48k stereo, pad to video_dur
    r = subprocess.run([
        'ffmpeg', '-y', '-i', inst_wav,
        '-af', f'apad=whole_dur={total_ms}ms',
        '-ar', '48000', '-ac', '2', '-acodec', 'pcm_s16le',
        '-t', str(video_dur), tmp_inst_48
    ], capture_output=True, text=True)
    if r.returncode != 0:
        pf(f'  instrumental prep FAIL: {r.stderr[-500:]}')
        return False
    pf(f'  instrumental: {get_dur(tmp_inst_48):.2f}s')

    return True

# ── Stage 2: Mix vocal + instrumental with gain ────────────────────────────────

def mix_tracks(vocal_48: str, inst_48: str,
               out_mix: str,
               vocal_gain_db: float, inst_gain_db: float) -> bool:
    """
    Mix dubbed vocal + instrumental bed with tunable gains.
    Uses amix with normalize=0 (we control gain explicitly).
    """
    pf(f'\n[Stage 2] Mixing vocal ({vocal_gain_db:+g}dB) + instrumental ({inst_gain_db:+g}dB) ...')

    vocal_lin = db_to_linear(vocal_gain_db)
    inst_lin  = db_to_linear(inst_gain_db)

    filter_chain = (
        f'[0:a]volume={vocal_lin}[vocal];'
        f'[1:a]volume={inst_lin}[inst];'
        f'[vocal][inst]amix=inputs=2:duration=longest:normalize=0[mixed]'
    )

    r = subprocess.run([
        'ffmpeg', '-y',
        '-i', vocal_48,
        '-i', inst_48,
        '-filter_complex', filter_chain,
        '-map', '[mixed]',
        '-ar', '48000', '-ac', '2', '-acodec', 'pcm_s16le',
        out_mix
    ], capture_output=True, text=True)
    if r.returncode != 0:
        pf(f'  mix FAIL: {r.stderr[-500:]}')
        return False

    sz = Path(out_mix).stat().st_size
    pf(f'  mix OK: {sz//1024//1024} MB ({get_dur(out_mix):.2f}s)')
    return True

# ── Stage 3: Final loudnorm ─────────────────────────────────────────────────────

def normalize_final(mix_wav: str, out_wav: str) -> bool:
    """
    Apply loudnorm to bring final mix to broadcast standard.
    Two-pass: measure then apply.
    """
    pf('\n[Stage 3] Loudnorm normalizing ...')

    # First pass: measure
    r = subprocess.run([
        'ffmpeg', '-y', '-i', mix_wav,
        '-af', 'loudnorm=I=-16:LRA=11:tp=-1.5:print_format=json',
        '-f', 'null', '-'
    ], capture_output=True, text=True)

    measured = {}
    match = re.search(r'\{[^}]+\}', r.stderr)
    if match:
        try:
            measured = json.loads(match.group())
        except Exception:
            pass

    mi  = measured.get('input_i', '-16')
    ml  = measured.get('input_lra', '11')
    mt  = measured.get('input_tp', '-1.5')
    mth = measured.get('input_thresh', '-70')
    pf(f'  measured: I={mi}, LRA={ml}, tp={mt}, thresh={mth}')

    # Second pass: apply
    cmd = [
        'ffmpeg', '-y', '-i', mix_wav,
        '-af', (f'loudnorm=I=-16:LRA=11:tp=-1.5:'
                f'measured_I={mi}:'
                f'measured_LRA={ml}:'
                f'measured_tp={mt}:'
                f'measured_thresh={mth}'),
        '-ar', '48000', '-ac', '2', '-acodec', 'pcm_s16le',
        out_wav
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        pf(f'  norm FAIL: {r.stderr[-500:]}')
        return False

    dur = get_dur(out_wav)
    sz  = Path(out_wav).stat().st_size
    pf(f'  normalized OK: {sz//1024//1024} MB ({dur:.2f}s)')
    return True

# ── Stage 4: Mux into final MP4 ────────────────────────────────────────────────

def make_final_mp4(video: str, audio: str, srt: str, out_mp4: str) -> bool:
    pf('\n[Stage 4] Muxing into final MP4 ...')

    # NOTE: we intentionally omit -shortest when an SRT subtitle stream is present.
    # The subtitle stream from an SRT covers only a fraction of the video (e.g. 1-3s of
    # dialogue text), so -shortest would prematurely terminate the output at the subtitle
    # stream's end time rather than the video's actual duration.
    # Both the video and audio tracks are already padded to the same full video duration
    # via Stage 1 (apad=whole_dur=...), so -shortest is not needed for duration alignment.
    has_srt = bool(srt) and srt != '/dev/null' and Path(srt).exists()

    cmd = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
        '-i', video,
        '-i', audio,
    ]
    if has_srt:
        cmd += ['-i', srt]
    cmd += [
        '-map', '0:v:0',
        '-map', '1:a:0',
    ]
    if has_srt:
        cmd += ['-map', '2:s:0']
    cmd += [
        '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '192k',
    ]
    if has_srt:
        cmd += ['-c:s', 'mov_text']
    if not has_srt:
        cmd += ['-shortest']
    cmd += [out_mp4]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        pf(f'  mux FAIL: {r.stderr[-500:]}')
        return False
    dur = get_dur(out_mp4)
    sz  = Path(out_mp4).stat().st_size
    pf(f'  MP4 OK: {sz//1024//1024} MB ({dur:.2f}s)')
    return True

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description='Stem-preserving remix: TTS dubbed vocal + original non-vocal stems')
    ap.add_argument('--project-dir',   required=True,
                    help='Project root (contains 01_raw_video/, 02_stems/, 04_translated_srt/, etc.)')
    ap.add_argument('--vocal-mix',    required=True,
                    help='TTS vocal mix WAV (already normalized, e.g. 05_tts_wav/tts_normalized.wav)')
    ap.add_argument('--video-file',   default='video.mp4',
                    help='Video filename inside 01_raw_video/ (default: video.mp4)')
    ap.add_argument('--vocal-gain',   type=float, default=3.0,
                    help='dB gain on TTS vocal track (default: +3 dB)')
    ap.add_argument('--inst-gain',    type=float, default=-3.0,
                    help='dB gain on instrumental bed (default: -3 dB)')
    ap.add_argument('--output',       required=True,
                    help='Output MP4 path (e.g. 07_remix/video_dubbed.mp4)')
    args = ap.parse_args()

    project  = Path(args.project_dir).resolve()
    video    = project / '01_raw_video' / args.video_file
    stems    = project / '02_stems'
    srt_name = args.video_file.replace('.mp4', '.srt')
    srt_path = project / '04_translated_srt' / srt_name

    # Vocal mix — resolve relative to project or accept absolute
    vocal = Path(args.vocal_mix)
    if not vocal.is_absolute():
        vocal = project / args.vocal_mix
    if not vocal.exists():
        pf(f'ERROR: vocal mix not found: {vocal}')
        sys.exit(1)

    # Find instrumental
    instrumental = stems / f'{args.video_file}.instrumental.wav'

    pf(f'Project:      {project}')
    pf(f'Video:        {video}')
    pf(f'Vocal mix:    {vocal}')
    pf(f'Instrumental: {instrumental}')
    pf(f'Vocal gain:  {args.vocal_gain:+g}dB | Inst gain: {args.inst_gain:+g}dB')

    for p in [video, instrumental, srt_path]:
        if not p.exists():
            pf(f'WARNING: {p} not found — may be optional')

    if not video.exists():
        pf(f'ERROR: video not found: {video}')
        sys.exit(1)
    if not instrumental.exists():
        pf(f'ERROR: instrumental not found: {instrumental}')
        sys.exit(1)

    # Get video duration
    video_dur = get_dur(str(video))
    pf(f'Video duration: {video_dur:.2f}s')

    if video_dur == 0:
        pf('ERROR: could not determine video duration')
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpd:
        tmpd = Path(tmpd)
        tmp_vocal_48 = tmpd / 'vocal_48k.wav'
        tmp_inst_48  = tmpd / 'inst_48k.wav'
        tmp_mix      = tmpd / 'remix_mix.wav'
        tmp_norm     = tmpd / 'remix_normalized.wav'

        # Stage 1: prepare
        ok = prepare_tracks(str(vocal), str(instrumental),
                           str(tmp_vocal_48), str(tmp_inst_48), video_dur)
        if not ok:
            sys.exit(1)

        # Stage 2: mix
        ok = mix_tracks(str(tmp_vocal_48), str(tmp_inst_48),
                        str(tmp_mix),
                        args.vocal_gain, args.inst_gain)
        if not ok:
            sys.exit(1)

        # Stage 3: normalize
        ok = normalize_final(str(tmp_mix), str(tmp_norm))
        if not ok:
            sys.exit(1)

        # Stage 4: mux (skip SRT if not present)
        out_mp4 = Path(args.output)
        if not out_mp4.is_absolute():
            out_mp4 = project / out_mp4
        out_mp4.parent.mkdir(parents=True, exist_ok=True)

        if srt_path.exists():
            ok = make_final_mp4(str(video), str(tmp_norm), str(srt_path), str(out_mp4))
        else:
            pf('\n[Stage 4] Muxing into final MP4 (no SRT) ...')
            ok = make_final_mp4(str(video), str(tmp_norm), '/dev/null', str(out_mp4))

        if not ok:
            sys.exit(1)

    pf(f'\n✅ Stem-preserving remix complete: {out_mp4}')

if __name__ == '__main__':
    main()