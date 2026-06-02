#!/usr/bin/env python3
"""
dubbing_assemble_loudnorm.py — FFmpeg adelay+amix+loudnorm 組裝，最後輸出配音 MP4。

用法：
  python dubbing_assemble_loudnorm.py \\
    --video 01_raw_video/video.mp4 \\
    --zh-srt 04_translated_srt/video.srt \\
    --tts-dir 05_tts_wav \\
    --output 06_final/video_dubbed.mp4

Step 1: 每個 TTS clip 用 adelay + apad 墊到總時長，再 amix
Step 2: loudnorm 後製（把 RMS 從 -60 dBFS 拉到 -16 dBFS）
Step 3: 最終 MP4（視訊 + 配音音訊 + 字幕）
"""
import argparse, subprocess, sys, tempfile, os
from pathlib import Path

# ── helpers ───────────────────────────────────────────────────────────────────
def parse_timestamp(ts: str) -> float:
    ts = ts.strip().replace(',', '.')
    h, m, rest = ts.split(':')
    s, ms = (rest.split('.') if '.' in rest else (rest, '0'))[:2]
    return int(h)*3600 + int(m)*60 + float(f"{s}.{ms}")

def parse_srt(path: str) -> list[dict]:
    with open(path, encoding='utf-8') as f:
        content = f.read().replace('\r\n', '\n').replace('\r', '\n')
    blocks = content.strip().split('\n\n')
    caps = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        try:
            idx       = lines[0].strip()
            start_str, end_str = lines[1].strip().split(' --> ')
            caps.append({
                'index': idx,
                'start': parse_timestamp(start_str),
                'end':   parse_timestamp(end_str),
                'text':  '\n'.join(lines[2:]),
            })
        except Exception:
            continue
    return caps

def get_dur(path: str) -> float:
    r = subprocess.run([
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'csv=p=0', path
    ], capture_output=True, text=True)
    v = r.stdout.strip()
    return float(v) if v and v != 'N/A' else 0.0

def pf(msg):
    print(msg, flush=True)

# ── Step 1: adelay + apad + amix ─────────────────────────────────────────────
def mix_tts_clips(clips: list, total_dur: float, out_mix: Path) -> bool:
    """
    clips: [(start_ms, end_ms, wav_path), ...]
    total_dur: 影片總時長（秒）from SRT 最後一段結尾
    out_mix: 中間產物（仍是安靜的 mix，RMS ~-60 dBFS）
    """
    total_ms = int(total_dur * 1000)
    n = len(clips)
    pf(f'Step1: mixing {n} clips, total_dur={total_dur:.2f}s')

    # 建 filter_complex: 每段 adelay + apad
    delay_parts = []
    for ci, (start_ms, end_ms, wav) in enumerate(clips):
        delay_parts.append(f'[{ci}]adelay={start_ms}|{start_ms},apad=whole_dur={total_ms}ms[tts_{ci}]')

    amix_ins = ''.join(f'[tts_{ci}]' for ci in range(n))
    filter_chain = (
        ';'.join(delay_parts) +
        f';{amix_ins}amix=inputs={n}:duration=longest:normalize=0[tts_mix]'
    )

    inputs = []
    for _, _, wav in clips:
        inputs += ['-i', wav]

    cmd = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
        *inputs,
        '-filter_complex', filter_chain,
        '-map', '[tts_mix]',
        '-ar', '24000', '-ac', '1', '-acodec', 'pcm_s16le',
        '-t', str(total_dur),
        str(out_mix),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        pf(f'Step1 FAIL:\n{r.stderr[-2000:]}')
        return False
    pf(f'Step1 OK: {out_mix} ({Path(out_mix).stat().st_size} bytes)')
    return True

# ── Step 2: loudnorm 後製 ──────────────────────────────────────────────────────
def loudnorm_normalize(in_wav: str, out_wav: str) -> bool:
    """
    loudnorm 把 amix 輸出的安靜音訊（RMS ~-60 dBFS）拉到 broadcast 標準。
    兩階段測量：第一階段測量，第二階段應用測量值。
    """
    pf('Step2: loudnorm normalizing ...')

    # 第一階段：測量
    r = subprocess.run([
        'ffmpeg', '-y', '-i', in_wav,
        '-af', 'loudnorm=I=-16:print_format=json',
        '-f', 'null', '-'
    ], capture_output=True, text=True)

    import json, re
    # 抓 measured_* 值
    match = re.search(r'\{[^}]+\}', r.stderr)
    if match:
        try:
            measured = json.loads(match.group())
        except Exception:
            measured = {}
    else:
        measured = {}

    measured_i = measured.get('input_i', '-60')
    measured_lra = measured.get('input_lra', '0')
    measured_tp = measured.get('input_tp', '-50')
    measured_thresh = measured.get('input_thresh', '-61')

    pf(f'  measured: I={measured_i}, LRA={measured_lra}, tp={measured_tp}, thresh={measured_thresh}')

    # 第二階段：應用測量值
    cmd = [
        'ffmpeg', '-y', '-i', in_wav,
        '-af', (f'loudnorm=I=-16:LRA=11:tp=-1.5:'
                f'measured_I={measured_i}:'
                f'measured_LRA={measured_lra}:'
                f'measured_tp={measured_tp}:'
                f'measured_thresh={measured_thresh}'),
        '-ar', '24000', '-ac', '2', '-acodec', 'pcm_s16le',
        out_wav,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        pf(f'Step2 FAIL:\n{r.stderr[-1000:]}')
        return False

    # 驗證 RMS
    dur = get_dur(out_wav)
    pf(f'Step2 OK: {out_wav} ({Path(out_wav).stat().st_size} bytes), dur={dur:.2f}s')
    return True

# ── Step 3: 最終 MP4 ──────────────────────────────────────────────────────────
def make_final_mp4(video: str, audio: str, srt: str, out_mp4: str) -> bool:
    pf('Step3: muxing into final MP4 ...')
    has_srt = bool(srt) and Path(srt).exists()
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
    else:
        cmd += ['-shortest']
    cmd += [out_mp4]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        pf(f'Step3 FAIL:\n{r.stderr[-1000:]}')
        return False
    dur = get_dur(out_mp4)
    sz  = Path(out_mp4).stat().st_size
    pf(f'Step3 OK: {out_mp4} ({sz//1024//1024} MB), dur={dur:.2f}s')
    return True

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video',   required=True, help='原始 MP4（01_raw_video/video.mp4）')
    ap.add_argument('--zh-srt',  required=True, help='翻譯後 SRT（用於時間軸）')
    ap.add_argument('--tts-dir', required=True, help='TTS WAV 目錄（line_{i}_tts.wav）')
    ap.add_argument('--output',  required=True, help='最終 MP4 路徑')
    ap.add_argument('--save-normalized-wav', default='', help='若提供，另存 Step2 的 tts_normalized.wav 供 remix 使用')
    args = ap.parse_args()

    video   = Path(args.video).resolve()
    zh_srt  = Path(args.zh_srt).resolve()
    tts_dir = Path(args.tts_dir).resolve()
    out_mp4 = Path(args.output)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    # 解析 SRT
    caps = parse_srt(str(zh_srt))
    pf(f'SRT: {len(caps)} entries')

    # 建立 clips 清單（跳過空檔）
    clips = []
    for cap in caps:
        idx = cap['index']
        start_ms = int(cap['start'] * 1000)
        end_ms   = int(cap['end']   * 1000)
        wav = tts_dir / f'line_{idx}_tts.wav'
        if wav.exists() and wav.stat().st_size > 500:
            clips.append((start_ms, end_ms, str(wav)))
        else:
            pf(f'  ⏭ line_{idx}: 空檔或缺失（{wav}）')

    pf(f'有效 clips: {len(clips)}')

    # 總時長：以實際影片長度為準，不能只看 SRT 最後一段結尾
    total_dur = get_dur(str(video))
    if total_dur <= 0:
        pf('ERROR: 無法取得影片時長')
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpd:
        tmp_mix = Path(tmpd) / 'tts_mix_raw.wav'
        tmp_norm = Path(tmpd) / 'tts_normalized.wav'

        ok1 = mix_tts_clips(clips, total_dur, tmp_mix)
        if not ok1:
            sys.exit(1)

        ok2 = loudnorm_normalize(str(tmp_mix), str(tmp_norm))
        if not ok2:
            sys.exit(1)

        if args.save_normalized_wav:
            save_norm = Path(args.save_normalized_wav).resolve()
            save_norm.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(tmp_norm, save_norm)
            pf(f'已另存 normalized WAV: {save_norm}')

        ok3 = make_final_mp4(str(video), str(tmp_norm), str(zh_srt), str(out_mp4))
        if not ok3:
            sys.exit(1)

    pf(f'\n✅ 完成：{out_mp4}')

if __name__ == '__main__':
    main()