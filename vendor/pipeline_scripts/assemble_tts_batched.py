#!/usr/bin/env python3
"""
assemble_tts_batched.py — Batched TTS mix + loudnorm + final MP4 assembly.

Use this instead of dubbing_assemble_loudnorm.py when the SRT has more than
~60 caption clips.  The single-pass filter_complex string in
dubbing_assemble_loudnorm.py blows past FFmpeg's command-line / filter-graph
parsing limit around 60–150 clips (silent truncation, "Error opening output
file", or args that look fine but produce a 0-byte WAV).  Verified on:
  • 249-clip English run (2026-06-01, ThePrimeagen clip) ✅ PASS
  • 426-clip Japanese run (2026-06-02, anime episode) ✅ PASS

Strategy:
  1. Split clips into batches of 30.
  2. For each batch: adelay + apad + amix into one mono 24kHz WAV.
  3. amix all batches together.
  4. Two-pass loudnorm (measure → apply).
  5. Optional: save tts_normalized.wav for stem-preserving remix downstream.
  6. Mux with original video + translated SRT → final MP4.

Usage:
  python assemble_tts_batched.py \\
    --video 01_raw_video/video.mp4 \\
    --zh-srt 04_translated_srt/video.srt \\
    --tts-dir 05_tts_wav \\
    --output 06_final/video_dubbed_fulltrack.mp4 \\
    --save-normalized-wav 05_tts_wav/tts_normalized.wav \\
    --batch-size 30
"""
import argparse, subprocess, sys, tempfile, os, json, re, shutil
from pathlib import Path


def parse_timestamp(ts):
    ts = ts.strip().replace(',', '.')
    h, m, rest = ts.split(':')
    s, ms = (rest.split('.') if '.' in rest else (rest, '0'))[:2]
    return int(h) * 3600 + int(m) * 60 + float(f"{s}.{ms}")


def parse_srt(path):
    content = Path(path).read_text(encoding='utf-8').replace('\r\n', '\n').replace('\r', '\n')
    caps = []
    for block in content.strip().split('\n\n'):
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        try:
            idx = lines[0].strip()
            s, e = lines[1].strip().split(' --> ')
            caps.append({
                'index': idx,
                'start': parse_timestamp(s),
                'end': parse_timestamp(e),
            })
        except Exception:
            continue
    return caps


def get_dur(path):
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'csv=p=0', str(path)],
        capture_output=True, text=True)
    v = r.stdout.strip()
    return float(v) if v and v != 'N/A' else 0.0


def pf(msg):
    print(msg, flush=True)


def make_batch(seg_clips, total_ms, out_wav):
    """adelay+apad+amix for one batch of clips → 24kHz mono WAV."""
    n = len(seg_clips)
    delay_parts = []
    for ci, (start_ms, _e, wav) in enumerate(seg_clips):
        delay_parts.append(f'[{ci}]adelay={start_ms}|{start_ms},apad=whole_dur={total_ms}ms[tts_{ci}]')
    amix_ins = ''.join(f'[tts_{ci}]' for ci in range(n))
    fc = ';'.join(delay_parts) + f';{amix_ins}amix=inputs={n}:duration=longest:normalize=0[m]'
    inputs = []
    for _, _, wav in seg_clips:
        inputs += ['-i', wav]
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
           *inputs, '-filter_complex', fc, '-map', '[m]',
           '-ar', '24000', '-ac', '1', '-acodec', 'pcm_s16le', str(out_wav)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        pf(f'batch FAIL: {r.stderr[-1500:]}')
        return False
    return True


def amix_many(parts, out_wav):
    """amix a list of mono 24kHz WAVs into one."""
    n = len(parts)
    fc = ''.join(f'[{i}:a]' for i in range(n)) + f'amix=inputs={n}:duration=longest:normalize=0[m]'
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
    for p in parts:
        cmd += ['-i', str(p)]
    cmd += ['-filter_complex', fc, '-map', '[m]',
            '-ar', '24000', '-ac', '1', '-acodec', 'pcm_s16le', str(out_wav)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        pf(f'amix FAIL: {r.stderr[-1500:]}')
        return False
    return True


def loudnorm(in_wav, out_wav):
    """Two-pass loudnorm (I=-16, LRA=11, tp=-1.5)."""
    pf('loudnorm ...')
    r = subprocess.run(
        ['ffmpeg', '-y', '-i', str(in_wav),
         '-af', 'loudnorm=I=-16:print_format=json', '-f', 'null', '-'],
        capture_output=True, text=True)
    match = re.search(r'\{[^}]+\}', r.stderr)
    measured = {}
    if match:
        try:
            measured = json.loads(match.group())
        except Exception:
            measured = {}
    mi = measured.get('input_i', '-60')
    ml = measured.get('input_lra', '0')
    mt = measured.get('input_tp', '-50')
    mth = measured.get('input_thresh', '-61')
    pf(f'  measured I={mi} LRA={ml} tp={mt} thresh={mth}')
    af = (f'loudnorm=I=-16:LRA=11:tp=-1.5:'
          f'measured_I={mi}:measured_LRA={ml}:measured_tp={mt}:measured_thresh={mth}')
    r = subprocess.run(
        ['ffmpeg', '-y', '-i', str(in_wav),
         '-af', af, '-ar', '24000', '-ac', '2', '-acodec', 'pcm_s16le', str(out_wav)],
        capture_output=True, text=True)
    if r.returncode != 0:
        pf(f'loudnorm FAIL: {r.stderr[-1500:]}')
        return False
    return True


def make_final(video, audio, srt, out_mp4):
    """Mux: video (copy) + loudnormed AAC + translated SRT."""
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
           '-i', str(video), '-i', str(audio), '-i', str(srt),
           '-map', '0:v:0', '-map', '1:a:0', '-map', '2:s:0',
           '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-c:s', 'mov_text',
           str(out_mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        pf(f'mux FAIL: {r.stderr[-1500:]}')
        return False
    sz = Path(out_mp4).stat().st_size
    pf(f'OK: {out_mp4} ({sz // 1024 // 1024} MB), dur={get_dur(out_mp4):.2f}s')
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', required=True)
    ap.add_argument('--zh-srt', required=True)
    ap.add_argument('--tts-dir', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--save-normalized-wav', default='',
                    help='Optional: copy final tts_normalized.wav to this path for stem-preserving remix')
    ap.add_argument('--batch-size', type=int, default=30,
                    help='Clips per adelay+amix batch. Keep ≤30 to stay under FFmpeg filter limit.')
    args = ap.parse_args()

    video = Path(args.video).resolve()
    srt = Path(args.zh_srt).resolve()
    tts = Path(args.tts_dir).resolve()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    caps = parse_srt(srt)
    pf(f'SRT entries: {len(caps)}')
    clips = []
    for c in caps:
        w = tts / f"line_{c['index']}_tts.wav"
        if w.exists() and w.stat().st_size > 500:
            clips.append((int(c['start'] * 1000), int(c['end'] * 1000), str(w)))
    pf(f'valid clips: {len(clips)}')

    total_dur = get_dur(video)
    if total_dur <= 0:
        sys.exit('ERROR: cannot get video duration')
    total_ms = int(total_dur * 1000)
    pf(f'video dur: {total_dur:.2f}s')
    pf(f'batch size: {args.batch_size} clips/batch')

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        # 1) split into batches → batch WAVs
        batch_files = []
        for bi in range(0, len(clips), args.batch_size):
            batch = clips[bi:bi + args.batch_size]
            bw = tmp / f'batch_{bi // args.batch_size:02d}.wav'
            pf(f'  batch {bi // args.batch_size:02d} ({len(batch)} clips) ...')
            if not make_batch(batch, total_ms, bw):
                sys.exit(1)
            batch_files.append(bw)
        # 2) amix all batches → single timeline
        mixed = tmp / 'tts_mix_raw.wav'
        pf(f'mixing {len(batch_files)} batches ...')
        if not amix_many(batch_files, mixed):
            sys.exit(1)
        # 3) loudnorm
        norm = tmp / 'tts_normalized.wav'
        if not loudnorm(mixed, norm):
            sys.exit(1)
        # 4) optional save normalized WAV for downstream remix
        if args.save_normalized_wav:
            sn = Path(args.save_normalized_wav)
            sn.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(norm, sn)
            pf(f'saved normalized WAV: {sn}')
        # 5) final mux
        if not make_final(video, norm, srt, out):
            sys.exit(1)
    pf(f'\nDONE: {out}')


if __name__ == '__main__':
    main()
