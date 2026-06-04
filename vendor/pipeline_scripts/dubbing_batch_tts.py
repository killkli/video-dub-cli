#!/usr/bin/env python3
"""
dubbing_batch_tts.py — OmniVoice per-segment clone。
輸入：中文翻譯 SRT + 每句原始 ref_audio。
輸出：每句配音 WAV（line_{i}_tts.wav）。

用法：
  DUB_OMNIVOICE_ROOT=/path/to/OmniVoice  # the OmniVoice dev repo checkout
  source $DUB_OMNIVOICE_ROOT/.venv/bin/activate
  PYTHONPATH=$DUB_OMNIVOICE_ROOT python3 dubbing_batch_tts.py \\
    --zh-srt 04_translated_srt/video.srt \\
    --en-srt 02_asr/video.srt \\
    --ref-dir 03_ref_audio \\
    --out-dir 05_tts_wav

`DUB_OMNIVOICE_ROOT` is the only operator-supplied path the script
needs (it points at the OmniVoice dev repo, which is not on PyPI
yet — that's a documented bootstrap step, not a hidden repo
coupling). If the env var is not set, the script refuses to run
with a clear error instead of silently inserting a hard-coded
fallback path that would only work on one developer's machine.
"""
import argparse, os, sys, time
from pathlib import Path

# ── 載入 OmniVoice（須在 venv 環境內）────────────────────────────────────────
# DUB_OMNIVOICE_ROOT is the operator-supplied env var. The legacy
# OMNIVOICE_ROOT name is also accepted as a fallback for backwards
# compatibility with existing operator shell scripts.
# This guard runs BEFORE every heavy import (torch, torchaudio,
# opencc, omnivoice.models.omnivoice) so a missing / wrong env
# var produces a clear, scoped error instead of a confusing
# ``ModuleNotFoundError`` from the wrong layer. argparse stays
# at the top of the file because it is part of the Python
# standard library and is required for the ``--help`` path.
_OMNIVOICE_ROOT = os.environ.get("DUB_OMNIVOICE_ROOT") or os.environ.get("OMNIVOICE_ROOT")
if not _OMNIVOICE_ROOT:
    sys.stderr.write(
        "dubbing_batch_tts.py: DUB_OMNIVOICE_ROOT is not set. "
        "Point it at a checkout of the OmniVoice dev repo "
        "(the package is not on PyPI yet). "
        "Run `dub bootstrap` for the full instructions.\n"
    )
    sys.exit(2)
OMNIROOT = Path(_OMNIVOICE_ROOT).expanduser().resolve()
if not (OMNIROOT / "omnivoice" / "models" / "omnivoice.py").is_file():
    sys.stderr.write(
        f"dubbing_batch_tts.py: DUB_OMNIVOICE_ROOT={OMNIROOT} does not look "
        f"like a valid OmniVoice checkout (missing omnivoice/models/omnivoice.py). "
        f"Run `dub bootstrap` for the full instructions.\n"
    )
    sys.exit(2)
sys.path.insert(0, str(OMNIROOT))

# Heavy model stack — only imported after the env-var guard passes.
from opencc import OpenCC  # noqa: E402
import torch  # noqa: E402
import torchaudio  # noqa: E402
from omnivoice.models.omnivoice import OmniVoice  # noqa: E402

OPENCC = OpenCC('t2s')

# ── Atomic write + size gate (dub-cli's tts.py mirrors _TTS_MIN_BYTES = 1000) ──
_TTS_MIN_BYTES = 1000


def _atomic_write_wav(tmp_path: Path, final_path: Path, wav_tensor, sample_rate: int) -> bool:
    """Write the wav to ``tmp_path`` first, fsync, then ``os.replace`` onto
    ``final_path``. ``os.replace`` is atomic on the same filesystem, so a
    concurrent reader either sees the old file or the new one — never a
    half-written intermediate.

    Returns True iff the final file exists and is > _TTS_MIN_BYTES afterwards.
    """
    try:
        torchaudio.save(str(tmp_path), wav_tensor.cpu(), sample_rate)
        # Make sure bytes hit the platter before the rename publishes them.
        try:
            with open(tmp_path, "rb") as _fh:
                _fh.flush()
                os.fsync(_fh.fileno())
        except OSError:
            pass
        os.replace(tmp_path, final_path)
    except Exception as e:
        pf(f'  atomic-write FAIL: {e}')
        # Best-effort cleanup of the tmp file so a retry starts clean.
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        return False
    try:
        return final_path.exists() and final_path.stat().st_size > _TTS_MIN_BYTES
    except OSError:
        return False

# ── SRT 解析 ─────────────────────────────────────────────────────────────────
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
            idx       = lines[0].strip()
            time_str  = lines[1].strip()
            start_str, end_str = time_str.split(' --> ')
            text = '\n'.join(lines[2:])
            captions.append({
                'index': idx,
                'start': parse_timestamp(start_str),
                'end':   parse_timestamp(end_str),
                'duration': parse_timestamp(end_str) - parse_timestamp(start_str),
                'text': text,
            })
        except Exception:
            continue
    return captions

def preprocess(text: str) -> str:
    """OpenCC t2s 繁→簡（OmniVoice 必用）"""
    return OPENCC.convert(text)

def pf(msg, end='\n'):
    print(msg, flush=True, end=end)

# ── TTS ──────────────────────────────────────────────────────────────────────
def tts_segment(model, zh_text: str, orig_text: str,
                ref_audio_path: Path, duration: float, out_wav: Path) -> bool:
    """
    用 duration= 控制語速（優先於 speed=）。
    ref_text 也要走同樣前處理，確保與 text 的 prompt alignment 一致。

    Atomic write contract: we never leave a partial wav at ``out_wav`` — either
    the file is fully present (> _TTS_MIN_BYTES) or it is absent. This is the
    single property the dub-cli stage verifier depends on for resumability.
    """
    ref_audio_path = Path(ref_audio_path)
    if not ref_audio_path.exists():
        pf(f'  MISS ref_audio: {ref_audio_path}')
        return False

    try:
        zh_simp = preprocess(zh_text)
        orig_simp = preprocess(orig_text)

        wav = model.generate(
            text=zh_simp,
            ref_audio=str(ref_audio_path),
            ref_text=orig_simp,
            duration=duration,          # ← 控制語速，勝於 speed=
            denoise=True,
            postprocess_output=True,
        )

        # ⚠️ CRITICAL: torchaudio.save() 需要 2D tensor
        wav_tensor = wav[0]
        if wav_tensor.dim() == 1:
            wav_tensor = wav_tensor.unsqueeze(0)

        # Atomic write: tmp + replace. Guards against partial files being
        # observed by a reader (e.g. the stage verifier) mid-write.
        tmp_wav = out_wav.with_suffix(".tmp.wav")
        # Remove any stale tmp from a previous aborted run.
        try:
            if tmp_wav.exists():
                tmp_wav.unlink()
        except OSError:
            pass
        return _atomic_write_wav(tmp_wav, out_wav, wav_tensor, 24000)
    except Exception as e:
        pf(f'  FAIL: {e}')
        return False

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zh-srt',  required=True, help='中文翻譯 SRT 路徑')
    ap.add_argument('--en-srt',  required=True, help='英文原文 SRT 路徑')
    ap.add_argument('--ref-dir', required=True, help='ref_audio 目錄（line_{i}_ref.wav）')
    ap.add_argument('--out-dir', required=True, help='輸出目錄（line_{i}_tts.wav）')
    ap.add_argument('--start', type=int, default=0,
                    help='只處理 index ≥ start 的段（0 = 全部；dub-cli 用於補跑缺失的 line）')
    ap.add_argument('--end',   type=int, default=0,
                    help='只處理 index ≤ end 的段（0 = 全部）')
    ap.add_argument('--skip-existing', action='store_true', default=True,
                    help='跳過已存在且 > _TTS_MIN_BYTES 的 line（預設 True；dub-cli 重跑時必開）')
    ap.add_argument('--no-skip-existing', dest='skip_existing', action='store_false',
                    help='強制重跑所有 line（不論檔案是否已存在）')
    args = ap.parse_args()

    zh_srt = Path(args.zh_srt)
    en_srt = Path(args.en_srt)
    ref_dir = Path(args.ref_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 解析字幕
    orig_caps  = {c['index']: c['text'] for c in parse_srt(str(en_srt))}
    trans_caps = parse_srt(str(zh_srt))
    if args.start > 0 or args.end > 0:
        trans_caps = [
            c for c in trans_caps
            if (args.start <= 0 or int(c['index']) >= args.start)
            and (args.end   <= 0 or int(c['index']) <= args.end)
        ]
    pf(f'共 {len(trans_caps)} 段字幕 (start={args.start} end={args.end})')

    # 載入 OmniVoice（device auto-detected，勿傳 device=）
    pf('Loading OmniVoice on MPS ...')
    model = OmniVoice.from_pretrained('k2-fsa/OmniVoice', torch_dtype=torch.float32)
    pf('Model loaded. Starting synthesis ...')

    ok, fail, skip, empty = 0, 0, 0, 0
    total = len(trans_caps)
    for seq, cap in enumerate(trans_caps):
        idx   = cap['index']
        zh    = cap['text']
        orig  = orig_caps.get(idx, '')
        dur   = cap['duration']
        out_wav = out_dir / f'line_{idx}_tts.wav'

        # Skip-existing gate: 跟 VoxCPM script 的 _TTS_MIN_BYTES 門檻一致,
        # 跟 dub-cli stages/tts.py:113 is_done() 的 _TTS_MIN_BYTES 也一致。
        # 三處用同一個值,resume / 重跑 / verifier 都不會看到「半檔案」狀態。
        if args.skip_existing and out_wav.exists() and out_wav.stat().st_size > _TTS_MIN_BYTES:
            skip += 1
            pf(f'[{seq+1}/{total}] [{idx}] SKIP (exists, {out_wav.stat().st_size}b)')
            continue

        ref_audio_path = ref_dir / f'line_{idx}_ref.wav'
        seq_num = seq + 1

        pf(f'[{seq_num}/{total}] [{idx}] dur={dur:.2f}s → {out_wav.name}', end=' ')
        t0 = time.time()
        ok_flag = tts_segment(model, zh, orig, ref_audio_path, dur, out_wav)
        elapsed = time.time() - t0

        if ok_flag:
            # Atomic write means: if tts_segment returned True, the file is
            # already > _TTS_MIN_BYTES. We double-check on disk here so a
            # silent regression in _atomic_write_wav can't poison the count.
            try:
                sz = out_wav.stat().st_size
            except OSError:
                sz = 0
            if sz > _TTS_MIN_BYTES:
                pf(f'OK  gen={elapsed:.1f}s  size={sz}b')
                ok += 1
            else:
                # Function said ok but the file is missing or too small —
                # the exact failure mode that produced the 22/32 bug.
                pf(f'EMPTY  gen={elapsed:.1f}s  size={sz}b (function said ok!)')
                empty += 1
        else:
            pf('FAIL')
            fail += 1

    pf(f'\nDone: {ok} ok, {fail} failed, {empty} empty, {skip} skipped (of {total})')
    # Exit 0 only if no real failures AND no empty results. Empty = partial
    # write that the dub-cli verifier will treat as missing.
    if fail > 0 or empty > 0:
        sys.exit(1)

if __name__ == '__main__':
    main()