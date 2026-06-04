# video-dub-cli

> 可續跑的影片翻譯／中文配音 CLI 管線。
> 正式支援：**單一 repo + `uv sync --extra all`**，提供 CLI、本地 ASR、Gemini 翻譯與 VoxCPM 路線。
> OmniVoice 已改為 **repo 內建程式碼 + 獨立 Python 環境** 的可選路線，請用 `dub bootstrap-omnivoice` 建立。

```bash
uv sync --extra all
uv run dub doctor
uv run dub auto talk.mp4           # ← canonical one-command entrypoint
```

`dub auto` 會自動選擇英文→中文或日文→中文路徑，全程無需指定 `--source-lang` 或 `--target-lang`。
`dub en2zh` / `dub ja2zh` 是明確的語言專用別名，內部與 `dub auto` 共用同一套 staged pipeline 合約。
`dub run` 保留作為需要明確控制的進階 escape hatch。

---

## 已內建

- CLI 與設定載入
- 專案狀態管理與重跑控制
- 管線腳本（`vendor/pipeline_scripts/`）
- Gemini 翻譯邏輯
- 內建 ASR（`src/qwenasr_mlx_cli/`）
- OmniVoice 轉接層與內嵌模型程式碼（`src/omnivoice/`）
- VoxCPM 轉接層

## 外部前置條件

- `ffmpeg` / `ffprobe`
- Gemini API key
- VoxCPM 路線：標準 `uv sync --extra all` 即可支援 `ja2zh`；若要獨立 VoxCPM interpreter，跑 `dub bootstrap-voxcpm`
- 若 `dub doctor` 顯示 `service` 缺失，仍需啟動本機 VoxCPM 服務（`127.0.0.1:8808`）
- OmniVoice（若要使用；由 `dub bootstrap-omnivoice` 自動建立專用環境）

---

## 安裝契約

### 1. clone repo

```bash
git clone https://codeberg.org/killkli/video-dub-cli
cd video-dub-cli
```

### 2. 建立標準 dub 環境

```bash
uv sync --extra all
```

這會建立 `.venv/`，並安裝 `dub` CLI、本地 ASR 依賴、Gemini 翻譯依賴與標準 VoxCPM route 依賴。

### 3. 安裝系統工具

```bash
# macOS
brew install ffmpeg

# Debian / Ubuntu
sudo apt-get install -y ffmpeg
```

### 4. 設定 Gemini API key

```bash
export GOOGLE_API_KEY=your_g..._key
```

或：

```bash
cp .env.example .env
# 編輯 .env 後載入
set -a; source .env; set +a
```

### 5. 驗證環境

```bash
uv run dub --help
uv run dub doctor
```

`dub doctor` 會報告 lane-aware readiness：雙路都可用時顯示 `ready for dub auto, dub en2zh, dub ja2zh`；若只剩單一路徑可用，會分別列出 ready / blocked lanes 與缺少項目。

---

## 主要命令

###  canonical 一鍵流程（推薦起點）

```bash
uv run dub auto talk.mp4           # 由 CLI 自動推斷語言路由
uv run dub auto talk.mp4 --source-lang en   # 明確指定英文→中文
uv run dub auto anime.mp4 --source-lang ja   # 明確指定日文→中文
```

### 語言專用別名

```bash
uv run dub en2zh talk.mp4          # 英文→中文，明確別名
uv run dub ja2zh anime.mp4         # 日文→中文，明確別名
```

### 使用既有翻譯字幕

```bash
uv run dub auto talk.mp4 \
  --translate-mode use-existing \
  --translated-srt talk.zhtw.srt
```

### 進階入口（escape hatch）

```bash
uv run dub run talk.mp4 --source-lang en --target-lang zh
```

`dub run` 保留用於需要明確覆寫 pipeline 參數的進階情境，常見 operator 情境應使用 `dub auto` 或 `en2zh`/`ja2zh` 別名。

### 續跑、狀態、驗證

```bash
uv run dub resume --project-dir /path/to/project
uv run dub status --project-dir /path/to/project
uv run dub validate --project-dir /path/to/project
uv run dub clean --project-dir /path/to/project
```

---

## `dub doctor` 會檢查什麼

目前檢查：

- `ffmpeg` / `ffprobe`
- `repo_pipeline_scripts`
- `gemini_api_key`
- Python 依賴：`qwen3_asr_mlx`, `soundfile`, `pydub`, `silero_vad`, `google_genai`, `torchcodec`
- `tts_backends.omnivoice`（wrapper / interpreter / deps / service 各 gate）
- `tts_backends.voxcpme`（wrapper / interpreter / deps / service 各 gate）

`dub doctor` 成功時顯示：

```
doctor ok: ready for `dub auto`, `dub en2zh`, `dub ja2zh`
next:    uv run dub auto <video>

# 若只有單一路徑可用，會改成類似：
doctor lanes: ready=`dub ja2zh` ; blocked=`dub en2zh`
```

失敗時列出缺少的項目與修復建議。

---

## 專案輸出結構

每次執行將產物存成可續跑的專案結構：

```
<project>/               # 預設：<video-stem>.dub/ 在輸入影片旁邊
├── 01_raw_video/
├── 02_stems/
├── 03_asr/
├── 04_ref_audio/
├── 05_translate/
├── 05_translated_srt/
├── 06_tts_wav/
├── 07_final/
│   └── video_dubbed_stem.mp4   # 最終產物
└── .dub/
    ├── state.json
    └── *.log
```

完成時會印出最終影片的完整路徑。

---

## 設定檔原則

多數情境**不需要**手動建立或複製設定檔。

若需自訂：

```bash
mkdir -p ~/.config/dub
cp examples/config_en2zh.yaml ~/.config/dub/config.yaml
```

常見自訂需求：

- `GOOGLE_API_KEY` 環境變數（必填，已由 doctor 自動復原）
- OmniVoice：`dub bootstrap-omnivoice --config ~/.config/dub/config.yaml`
- 獨立 VoxCPM interpreter：`dub bootstrap-voxcpm`

---

## OmniVoice 的正式做法

```bash
uv run dub bootstrap-omnivoice
```

會自動建立 OmniVoice 專用 venv 並寫入 `paths.omnivoice_python`。
完成後重新驗證：

```bash
uv run dub doctor --config ~/.config/dub/config.yaml
```

---

## 文件索引

- `QUICKSTART.md`：5 分鐘上手
- `docs/operator-runbook.md`：故障排除與恢復流程
- `docs/qa-auto-workflow-acceptance-criteria-2026-06-04.md`：auto-workflow 驗收標準（T2 QA 定義）
- `docs/auto-workflow-contract-2026-06-04.md`：operator 合約（T0 gate）
- `docs/operator-qa-real-backend-en2zh-2026-06-03.md`：英文→中文真實驗證
- `docs/operator-qa-real-backend-ja2zh-2026-06-03.md`：日文→中文真實驗證

---

## 目前可以誠實宣稱的範圍

### 已驗證

- `uv sync --extra all`
- `uv run dub --help` / `uv run dub auto --help`
- `uv run dub doctor`（自動從 `~/.zshrc` 復原 Gemini key）
- `uv run dub bootstrap-omnivoice` / `uv run dub bootstrap-voxcpm`
- `uv run dub auto ...` / `uv run dub en2zh ...` / `uv run dub ja2zh ...`
- `dub resume / status / validate / clean`

### 不應過度宣稱

- 不是所有 TTS backend 都在同一個 Python 環境內
- OmniVoice 採「標準 dub venv + 專用 OmniVoice venv」雙環境契約
- VoxCPM 依賴本機服務（`127.0.0.1:8808`）

這是目前已驗證、可維運、可交付的 operator contract。