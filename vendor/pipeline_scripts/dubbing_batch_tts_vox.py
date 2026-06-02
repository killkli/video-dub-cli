#!/usr/bin/env python3
"""
dubbing_batch_tts_vox.py — VoxCPM per-segment clone (日文片源 → 中文配音)。

VoxCPM Ultimate Cloning 模式：ref_wav + prompt_text 強制還原原音色。
**注意**：與 OmniVoice 不同，VoxCPM Ultimate Cloning **不接受 `duration=` 參數**，
會按自然語速輸出（通常比 SRT 該段目標長 0.2-1.8s）。
本腳本會在 TTS 產出後跑 `ffmpeg atempo` 把每段 WAV 拉到對齊 SRT 該段時長。
超短段（<1s, ratio > 2.0）atempo 無法處理，會保留自然長度（每段超時 ~0.5-1.5s，
累積 < 7% 影片總長，mix 階段可接受）。

歌曲段（zh 翻譯以 `[歌曲翻唱/保留原詞]` 開頭）跳過 TTS，
後續 stem-preserving remix 會保留原曲。

依賴：`hermes-agent/venv` 內已裝 gradio_client + httpx + opencc。
VoxCPM server 需先啟動（`cd ~/Dev/VoxCPM && .venv/bin/python app.py --port 8808`）。

用法：
  python dubbing_batch_tts_vox.py \\
    --project-dir /path/to/dub-project \\
    [--start N] [--end N] [--cfg 2.0] [--steps 10]

輸入 SRT：
  02_asr/video.srt           — 日文 ASR (per-segment ref_text 來源)
  04_translated_srt/video.zhtw.srt — 繁中翻譯 (TTS 輸入)

輸出：
  05_tts_wav/line_{i}_tts.wav — 24kHz mono (VoxCPM 24k 輸出 → atempo 對齊 → 24k pcm_s16le)

執行環境：必須在 `~/.hermes/hermes-agent/venv` 內（gradio_client + opencc 都在那）。
"""
import os, sys, json, time, argparse, shutil, subprocess
from pathlib import Path
from gradio_client import Client


def dur(p: str) -> float:
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'csv=p=0', p], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def generate_one(client: Client, text: str, ref_wav_path: str, ref_text: str,
                 cfg: float = 2.0, steps: int = 10) -> str:
    """呼叫 /generate endpoint,Ultimate Cloning 模式 (ref_wav + prompt_text)。
    回傳 server 端 wav 路徑。
    Gradio FileData 必須包成 {"path": ..., "meta": {"_type": "gradio.FileData"}}。
    """
    result = client.predict(
        text=text,
        control_instruction="",
        ref_wav={"path": ref_wav_path, "meta": {"_type": "gradio.FileData"}},
        # ja -> zh cloning: prompt_text 會讓 VoxCPM 偏向原日文語句，
        # 導致輸出雖是中文聲音但不穩定遵循中文字幕內容。
        # 正式路線改為只提供 ref_wav 保留音色，不再餵原日文 prompt_text。
        use_prompt_text=False,
        prompt_text_value="",
        cfg_value=cfg,
        do_normalize=True,
        denoise=True,
        dit_steps=steps,
        api_name="/generate",
    )
    return result


def parse_srt(path: str) -> dict[int, dict]:
    """回傳 {index: {start, end, text}}"""
    with open(path, encoding="utf-8") as f:
        content = f.read().replace("\r\n", "\n")
    out = {}
    for block in content.strip().split("\n\n"):
        lines = block.strip().split("\n")
        if len(lines) < 3: continue
        try:
            idx = int(lines[0])
            t = lines[1].split(" --> ")
            text = "\n".join(lines[2:]).strip()
            out[idx] = {"start": t[0].strip(), "end": t[1].strip(), "text": text}
        except: pass
    return out


def atempo_align(wav_path: Path, target_dur: float) -> bool:
    """ffmpeg atempo 拉到對齊 target_dur。atempo 範圍 0.5-2.0 (單段)。
    超出範圍不做事,保留原 WAV。

    重要：atempo=N 表示速度 Nx。若原 tts 1.76s 要變 0.88s,ratio = 1.76/0.88 = 2.0。
    """
    tts_dur = dur(str(wav_path))
    if tts_dur <= target_dur * 1.05:  # 5% tolerance, 已對齊
        return True

    ratio = tts_dur / target_dur  # atempo 加速比
    if not (0.5 <= ratio <= 2.0):
        return False  # out of range, 保留原 WAV

    tmp_wav = wav_path.with_suffix('.tmp.wav')
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
           '-i', str(wav_path),
           '-af', f'atempo={ratio:.4f}',
           '-ar', '24000', '-ac', '1', '-acodec', 'pcm_s16le',
           str(tmp_wav)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        tmp_wav.replace(wav_path)
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--ja-srt", help="原文 SRT,預設 02_asr/video.srt")
    ap.add_argument("--zh-srt", help="翻譯 SRT,預設 04_translated_srt/video.zhtw.srt")
    ap.add_argument("--ref-dir", help="ref_audio 目錄,預設 03_ref_audio")
    ap.add_argument("--out-dir", help="TTS 輸出目錄,預設 05_tts_wav")
    ap.add_argument("--url", default=os.environ.get("VOXCPM_URL", "http://127.0.0.1:8808"))
    ap.add_argument("--cfg", type=float, default=2.0)
    ap.add_argument("--steps", type=int, default=10)
    ap.add_argument("--start", type=int, default=1, help="從哪個 line 開始")
    ap.add_argument("--end", type=int, default=0, help="跑到哪個 line (0 = 全部)")
    ap.add_argument("--skip-existing", action="store_true", default=True)
    args = ap.parse_args()

    proj = Path(args.project_dir).resolve()
    ja_srt = Path(args.ja_srt) if args.ja_srt else proj / "02_asr/video.srt"
    zh_srt = Path(args.zh_srt) if args.zh_srt else proj / "04_translated_srt/video.zhtw.srt"
    ref_dir = Path(args.ref_dir) if args.ref_dir else proj / "03_ref_audio"
    out_dir = Path(args.out_dir) if args.out_dir else proj / "05_tts_wav"
    out_dir.mkdir(parents=True, exist_ok=True)

    ja = parse_srt(str(ja_srt))
    zh = parse_srt(str(zh_srt))
    print(f"Loaded {len(ja)} ja, {len(zh)} zh segments")

    try:
        from opencc import OpenCC
        t2s = OpenCC("t2s")
    except ImportError:
        t2s = None
        print("WARN: opencc not available, t2s skipped", flush=True)

    indices = sorted(zh.keys())
    if args.end > 0:
        indices = [i for i in indices if args.start <= i <= args.end]
    else:
        indices = [i for i in indices if i >= args.start]

    print(f"Processing {len(indices)} segments (line {indices[0]}-{indices[-1]})")
    print(f"Server: {args.url}  CFG={args.cfg} Steps={args.steps} opencc={bool(t2s)}")
    print()

    print(f"Connecting to VoxCPM at {args.url}...")
    client = Client(args.url)
    print("Connected.\n")

    ok = 0
    fail = 0
    empty = 0
    skip = 0
    song = 0
    atempo_ok = 0
    atempo_skip = 0
    t0 = time.time()

    for n, idx in enumerate(indices, 1):
        out_wav = out_dir / f"line_{idx}_tts.wav"

        if args.skip_existing and out_wav.exists() and out_wav.stat().st_size > 1000:
            skip += 1
            print(f"  [{n}/{len(indices)}] line_{idx} SKIP (exists, {out_wav.stat().st_size} bytes)", flush=True)
            continue

        zh_text = zh[idx]["text"].strip()
        if zh_text.startswith("[歌曲翻唱/保留原詞]"):
            song += 1
            print(f"  [{n}/{len(indices)}] line_{idx} SONG (skip TTS, keep original in remix)", flush=True)
            continue

        ja_text = ja.get(idx, {}).get("text", "").strip()
        ref_audio = ref_dir / f"line_{idx}_ref.wav"
        if not ref_audio.exists():
            print(f"  [{n}/{len(indices)}] line_{idx} MISS ref_audio", flush=True)
            fail += 1
            continue

        zh_cap = zh[idx]
        sh, sm, ss = zh_cap['start'].split(':')
        eh, em, es = zh_cap['end'].split(':')
        s = int(sh)*3600+int(sm)*60+float(ss.replace(',', '.'))
        e = int(eh)*3600+int(em)*60+float(es.replace(',', '.'))
        target_dur = e - s

        final_text = t2s.convert(zh_text) if t2s else zh_text

        try:
            t_send = time.time()
            server_path = generate_one(client, final_text, str(ref_audio), ja_text, args.cfg, args.steps)
            t_gen = time.time() - t_send

            if not server_path or not Path(server_path).exists():
                print(f"  [{n}/{len(indices)}] line_{idx} FAIL: server returned {server_path}", flush=True)
                fail += 1
                continue

            # Atomic copy: write to .tmp then os.replace. shutil.copy2 directly
            # to out_wav is non-atomic — a reader (e.g. dub-cli verifier) could
            # observe a half-written wav mid-copy. The .tmp + replace pattern
            # mirrors the OmniVoice script's atomic-write contract.
            tmp_copy = out_wav.with_suffix(out_wav.suffix + ".tmp")
            try:
                if tmp_copy.exists():
                    tmp_copy.unlink()
            except OSError:
                pass
            try:
                shutil.copy2(server_path, tmp_copy)
                os.replace(tmp_copy, out_wav)
            except Exception as e:
                try:
                    if tmp_copy.exists():
                        tmp_copy.unlink()
                except OSError:
                    pass
                print(f"  [{n}/{len(indices)}] line_{idx} FAIL: copy/replace: {e}", flush=True)
                fail += 1
                continue

            # Post-process: atempo to align TTS duration with SRT target
            if atempo_align(out_wav, target_dur):
                new_dur = dur(str(out_wav))
                tts_orig = dur(str(out_wav))  # 已經是 atempo 後
                # 我們需要原 TTS 長度做 log,但 atempo_align 內已 in-place 改掉了。
                # 簡化：直接 log 新時長
                elapsed = time.time() - t0
                avg = elapsed / n
                if abs(new_dur - target_dur) < 0.1:
                    atempo_ok += 1
                    print(f"  [{n}/{len(indices)}] line_{idx} OK atempo→{new_dur:.2f}s (target {target_dur:.2f}s) (avg {avg:.1f}s)", flush=True)
                else:
                    atempo_skip += 1
                    print(f"  [{n}/{len(indices)}] line_{idx} OK {new_dur:.2f}s (target {target_dur:.2f}s, atempo out of range, kept) (avg {avg:.1f}s)", flush=True)
            else:
                new_dur = dur(str(out_wav))
                atempo_skip += 1
                print(f"  [{n}/{len(indices)}] line_{idx} OK {new_dur:.2f}s (target {target_dur:.2f}s, atempo out of range, kept) (avg {avg:.1f}s)", flush=True)

            # Final on-disk gate: only count as ok if the file is > 1000 bytes.
            # Empty / too-small files are the exact 22/32 failure mode and the
            # dub-cli stage verifier will treat them as missing.
            try:
                on_disk_sz = out_wav.stat().st_size
            except OSError:
                on_disk_sz = 0
            if on_disk_sz > 1000:
                ok += 1
            else:
                print(f"  [{n}/{len(indices)}] line_{idx} EMPTY (function said ok, size={on_disk_sz}b)", flush=True)
                # Roll back the atempo counter we just incremented so the
                # summary line reflects reality — this line produced nothing
                # usable. The ok counter was never incremented, so nothing
                # to undo there.
                if abs(new_dur - target_dur) < 0.1:
                    atempo_ok = max(0, atempo_ok - 1)
                else:
                    atempo_skip = max(0, atempo_skip - 1)
                empty += 1
        except Exception as e:
            print(f"  [{n}/{len(indices)}] line_{idx} FAIL: {str(e)[:200]}", flush=True)
            fail += 1

    total = time.time() - t0
    print()
    print(f"=== Done in {total:.0f}s ===")
    print(f"  OK: {ok}  FAIL: {fail}  EMPTY: {empty}  SKIP(existing): {skip}  SONG(skipped): {song}")
    print(f"  atempo aligned: {atempo_ok}  atempo out-of-range: {atempo_skip}")
    # Exit 0 only when no real failures and no empty results. Empty == partial
    # write == the 22/32 failure mode — dub-cli will treat it as missing.
    if fail > 0 or empty > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
