#!/usr/bin/env python3
"""
dubbing_extract_ref.py — 從原始 MP4 + 原文 SRT 切割每句 ref_audio。
輸出：line_{i}_ref.wav（24kHz mono，保留自然起音，禁止 aggressive trim）。
用法：python dubbing_extract_ref.py <video.mp4> <source.srt> <output_dir/>
"""
import subprocess, sys, re
from pathlib import Path

def parse_timestamp(ts: str) -> float:
    ts = ts.strip().replace(',', '.')
    h, m, rest = ts.split(':')
    s, ms = (rest.split('.') if '.' in rest else (rest, '0'))[:2]
    return int(h)*3600 + int(m)*60 + float(f"{s}.{ms}")

def parse_srt(path: str) -> list[dict]:
    with open(path, encoding='utf-8') as f:
        content = f.read().replace('\r\n', '\n').replace('\r', '\n')
    blocks = content.strip().split('\n\n')
    captions = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        try:
            idx  = lines[0].strip()
            time = lines[1].strip()
            start_str, end_str = time.split(' --> ')
            text = '\n'.join(lines[2:])
            captions.append({
                'index': idx,
                'start': parse_timestamp(start_str),
                'end':   parse_timestamp(end_str),
                'text':  text,
            })
        except Exception:
            continue
    return captions

def extract_segment(video_path: str, start: float, end: float, out_wav: Path) -> bool:
    """
    用 ffmpeg 從影片抽出指定時間段的音訊。
    ⚠️ 禁止 silenceremove / loudnorm / 任何 aggressive trim。
    ⚠️ 保留自然起音；只做 -ar 24000 -ac 1。
    """
    dur = end - start
    cmd = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
        '-i', video_path,
        '-ss', str(start),
        '-t',  str(dur),
        '-ar', '24000', '-ac', '1', '-acodec', 'pcm_s16le',
        str(out_wav),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f'  FAIL: {r.stderr[-300:]}')
        return False
    # 驗證時長（誤差 < 0.2s）
    probe = subprocess.run([
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'csv=p=0', str(out_wav)
    ], capture_output=True, text=True)
    actual = float(probe.stdout.strip() or 0)
    if abs(actual - dur) > 0.3:
        print(f'  ⚠️ duration mismatch: expected {dur:.2f}s, got {actual:.2f}s')
    return True

def main():
    if len(sys.argv) < 4:
        print('Usage: python dubbing_extract_ref.py <video.mp4> <source.srt> <output_dir/>')
        sys.exit(1)

    video_path = sys.argv[1]
    srt_path   = sys.argv[2]
    out_dir    = Path(sys.argv[3]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    captions = parse_srt(srt_path)
    print(f'SRT: {len(captions)} entries from {srt_path}')

    for cap in captions:
        idx  = cap['index']
        start = cap['start']
        end   = cap['end']
        out_wav = out_dir / f'line_{idx}_ref.wav'

        print(f'  [{idx}/{len(captions)}] {start:.2f}s–{end:.2f}s → {out_wav.name}', end=' ')
        ok = extract_segment(video_path, start, end, out_wav)
        print('OK' if ok else 'FAIL')

    print(f'\nDone. Files in {out_dir}')

if __name__ == '__main__':
    main()