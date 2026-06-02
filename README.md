# video-dub-cli

**把任何英文影片自動配音成中文 — 一個指令就完成。**

```
dub run talk.mp4 --source-lang en --target-lang zh
```

6 個 stage 全自動：人聲分離 → 語音辨識 → 提取範例音頻 → 翻譯 → TTS 配音 → 組裝MP4。中斷後 `dub resume` 接續。

---

## 目錄

- [特色](#特色)
- [安裝](#安裝)
- [快速上手](#快速上手)
- [完整指令](#完整指令)
- [架構](#架構)
- [設定檔](#設定檔)
- [Stage 流程](#stage-流程)
- [Resume / Status / Clean](#resume--status--clean)
- [測試](#測試)
- [故障排除](#故障排除)
- [授權](#授權)

---

## 特色

| 特色 | 說明 |
|------|------|
| **Single command** | `dub run <video> --src en --tgt zh` 一個指令跑完整條 pipeline |
| **skip-existing resume** | 每個 stage 結果磁碟化，中斷後從最後一步繼續，不重頭來過 |
| **Production-ready error handling** | Per-stage 3 次重試、指數退避、明確的錯誤訊息 |
| **6 stages 全自動** | stems → ASR → ref_audio → 翻譯 → TTS → 組裝 |
| **Rich progress條** | 即時進度條，清楚看到每個 stage 的執行狀態 |

---

## 安裝

```bash
# 建議：用 Python 3.11 venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

確認安裝成功：
```bash
dub --help
```

---

## 快速上手

### 第一次跑

```bash
# 1. 複製並修改設定檔
cp examples/config_en2zh.yaml ~/.config/dub/config.yaml
vim ~/.config/dub/config.yaml   # 修改 paths（如 qwenasr_cli、omnivoice_python）

# 2. 執行配音
dub run /path/to/input/my_talk.mp4 --source-lang en --target-lang zh

# 3. 輸出位置
#   ~/.hermes/dub-my_talk-YYYYMMDD-HHMMSS/07_final/video_dubbed_stem.mp4
```

### 中斷後繼續

```bash
dub resume --project-dir ~/.hermes/dub-my_talk-YYYYMMDD-HHMMSS/
```

---

## 完整指令

### `dub run` — 執行完整配音流程

```bash
dub run VIDEO --source-lang en --target-lang zh [OPTIONS]

# 常用選項
  --source-lang, --src      來源語言（如 en、ja）
  --target-lang, --tgt      目標語言（如 zh、zhtw）
  --project-dir             專案目錄（預設：~/.hermes/dub-<topic>-<timestamp>/）
  --config                  指定 YAML 設定檔（預設：~/.config/dub/config.yaml）
  --translate-mode          delegate | skip | use-existing（預設：delegate）
  --translated-srt          translate-mode=use-existing 時，指定已翻譯的 SRT 路徑
  --vocal-gain              人聲增益 dB（預設：3.0）
  --inst-gain               背景音樂增益 dB（預設：-3.0）
  --keep-fulltrack          輸出額外的全軌替換版（legacy 比較用）
  --yes, -y                 跳過所有確認提示

# 範例
dub run talk.mp4 --src en --tgt zh                          # 英文→中文
dub run talk.mp4 --src en --tgt zh --keep-fulltrack          # 含全軌版
dub run talk.mp4 --src en --tgt zh --translate-mode skip    # 跳過翻譯 stage
```

### `dub resume` — 繼續中斷的 pipeline

```bash
dub resume --project-dir ~/.hermes/dub-talk-YYYYMMDD-HHMMSS/
```

讀取 `.dub/state.json`，自動跳過已完成 stage，從第一個未完成或失敗的 stage 繼續。

### `dub status` — 顯示 pipeline 狀態

```bash
dub status --project-dir ~/.hermes/dub-talk-YYYYMMDD-HHMMSS/

# 輸出範例：
#   ✓ 01 stems           (12.4s, 2 stems)
#   ✓ 02 asr             (54 segments)
#   ✓ 03 ref_audio       (54 wavs)
#   ▶ 04 translate       (running, segment 12/54)
#   ✗ 05 tts             (failed: line_12 — TTS OOM)
#   ○ 06 assemble        (pending)
```

### `dub clean` — 清理 partial 產物

```bash
dub clean --project-dir ~/.hermes/dub-talk-YYYYMMDD-HHMMSS/
# 刪除 02~07 與 .dub/state.json，保留 01_raw_video/ 與原始 video.mp4

# 進階用法
dub clean --project-dir ... --stage 05    # 只清第 5 stage
dub clean --project-dir ... --keep-source # 連 source 也刪除
```

### `dub validate` — 驗證專案結構

```bash
dub validate --project-dir ~/.hermes/dub-talk-YYYYMMDD-HHMMSS/
```

檢查：01 有 video.mp4、`.dub/state.json` 格式正確、所有 ref_audio 與 tts_wav 數量一致、最終 MP4 可被 ffprobe 讀。

---

## 架構

```
video-dub-cli/
├── pyproject.toml              # setuptools + click + rich + pyyaml
├── README.md
├── DESIGN.md
├── CHANGELOG.md
├── QUICKSTART.md
├── src/
│   └── dub/
│       ├── __init__.py         # __version__ = "0.1.0"
│       ├── __main__.py         # python -m dub 也行
│       ├── cli.py              # click group + 5 subcommands
│       ├── config.py           # YAML loader + merge
│       ├── state.py            # State load/save/mutate
│       ├── project.py          # project dir 建構
│       ├── runner.py           # 主流程 orchestrator
│       ├── stages/
│       │   ├── __init__.py
│       │   ├── base.py         # Stage ABC
│       │   ├── stems.py
│       │   ├── asr.py
│       │   ├── ref_audio.py
│       │   ├── translate.py
│       │   ├── tts.py
│       │   └── assemble.py
│       ├── retry.py            # tenacity wrappers
│       ├── progress.py         # rich progress bar
│       ├── logging.py          # loguru config
│       └── errors.py
├── tests/
│   ├── test_config.py
│   ├── test_state.py
│   ├── test_skip_existing.py
│   ├── test_runner_smoke.py
│   └── fixtures/
│       └── test_short.mp4      # 30s 英文片（既有測試素材）
├── examples/
│   ├── config_en2zh.yaml
│   ├── config_ja2zh.yaml
│   └── config_with_translated_srt.yaml
└── docs/
    └── skill-assessment.md
```

**Python**：3.11+

**依賴**：`click` 8.x、`rich` 13.x、`pyyaml` 6.x、`tenacity` 8.x、`loguru` 0.7.x

---

## 設定檔

路徑：`~/.config/dub/config.yaml`（找不到就用內建 default）

```yaml
paths:
  qwenasr_cli: /path/to/qwenasr-mlx/.venv/bin/qwenasr-mlx
  omnivoice_python: /path/to/OmniVoice/.venv/bin/python3
  skills_dir: /path/to/video-dubbing-pipeline/scripts
  dub_root: ~/.hermes                    # dub-{topic} 建在這底下
  translation_skill: /path/to/subtitle_translation.py

defaults:
  source_lang: en
  target_lang: zh
  vocal_gain: 3.0
  inst_gain: -3.0
  keep_fulltrack: false

retry:
  max_attempts: 3
  backoff_seconds: 5                      # 3 attempts: 0s, 5s, 25s
  retry_on:
    - subprocess.CalledProcessError
    - TimeoutError
    - ConnectionError

logging:
  level: INFO
  json_logs: false
  file: <project>/.dub/log.txt
  progress: rich
```

**覆寫優先順序（高 → 低）**：
1. CLI flags
2. `--config` 指定的 YAML
3. `~/.config/dub/config.yaml`
4. 內建 default

---

## Stage 流程

每個 stage 進入前檢查 skip-existing，若產物已存在且比 input 新則跳過。

| Stage | Script | 輸入 | 輸出 |
|-------|--------|------|------|
| 01 stems | `dubbing_stems.py` | `01_raw_video/video.mp4` | `02_stems/video.{vocals,instrumental}.wav` |
| 02 asr | `qwenasr-mlx transcribe` | `02_stems/video.vocals.wav` | `03_asr/video.srt` |
| 03 ref_audio | `dubbing_extract_ref.py` | `01_raw_video/video.mp4` + `03_asr/video.srt` | `04_ref_audio/line_{i}_ref.wav` |
| 04 translate | `subtitle_translation.py` | `03_asr/video.srt` | `05_translated_srt/video.zhtw.srt` |
| 05 tts | `dubbing_batch_tts.py` (en) / `dubbing_batch_tts_vox.py` (ja) | `04_ref_audio/` + `05_translated_srt/` | `06_tts_wav/line_{i}_tts.wav` |
| 06 assemble | `dubbing_remix.py` | `06_tts_wav/tts_normalized.wav` + `02_stems/video.instrumental.wav` | `07_final/video_dubbed_stem.mp4` |

**skip-existing 規則**：
- `01 stems`：檢查 `02_stems/video.vocals.wav` 存在且 mtime 比 input video 新
- `02 asr`：檢查 `03_asr/video.srt` 存在且 segment 數 > 0
- `03 ref_audio`：檢查 `04_ref_audio/line_{1}_ref.wav` 存在
- `04 translate`：檢查 `05_translated_srt/video.zhtw.srt` 存在
- `05 tts`：逐一檢查 `line_{i}_tts.wav` 存在（缺一個就跑那個，不全跑）
- `06 assemble`：檢查 `07_final/video_dubbed_stem.mp4` 存在

---

## Resume / Status / Clean

### resume

```bash
dub resume --project-dir ~/.hermes/dub-talk-YYYYMMDD-HHMMSS/
```

若 state.json 中有 stage 狀態為 `running`（上次被 kill），自動退回 `pending` 重跑。會自動跳过已完成的 stage。

### status

```bash
dub status --project-dir ~/.hermes/dub-talk-YYYYMMDD-HHMMSS/
```

即時表格輸出：每個 stage 的狀態耗時與產物數。

### clean

```bash
dub clean --project-dir ~/.hermes/dub-talk-YYYYMMDD-HHMMSS/
```

預設行為：刪除 `02_raw_video/` 以外的所有 stage 產物與 `.dub/state.json`。不動 `01_raw_video/` 與原始 video。

---

## 測試

```bash
# 單元測試
pytest tests/

# 整合測試（含 smoke test）
pytest tests/integration/
```

整合測試需要完整的影片檔案，執行時間較長。CI 建議分開跑。

---

## 故障排除

### OmniVoice venv 找不到

```bash
# 檢查設定檔中的路徑
cat ~/.config/dub/config.yaml | grep omnivoice

# 測試路徑是否正確
/path/to/OmniVoice/.venv/bin/python3 --version
```

### GPU OOM（TTS stage 最常見）

- 降低剪輯長度或分段處理
- 確認 CUDA 可用：`python3 -c "import torch; print(torch.cuda.is_available())"`

### ASR timeout

- 檢查 `qwenasr-mlx` 是否正常：`qwenasr-mlx --help`
- 確認人聲檔案存在：`ls 02_stems/`
- 增加 `--config` 中的 `retry.backoff_seconds`

### 翻譯子代理失敗

- 確認 `translation_skill` 路徑正確
- 檢查 `.dub/log.txt` 中的詳細錯誤
- 可用 `--translate-mode skip` 跳過翻譯 stage（直接用現有 SRT）

---

## 授權

MIT License