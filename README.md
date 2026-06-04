# video-dub-cli

> 可續跑的影片翻譯／中文配音 CLI 管線。
> 目前正式支援的標準路徑：**單一 repo + `uv sync --extra all`**，提供 CLI、本地 ASR、Gemini 翻譯與 VoxCPM 路線。
> OmniVoice 已改為 **repo 內建程式碼 + 獨立 Python 環境** 的可選路線，請用 `dub bootstrap-omnivoice` 建立。

```bash
uv sync --extra all
uv run dub doctor
uv run dub en2zh talk.mp4
```

`video-dub-cli` 把多階段影片配音流程收斂成單一 CLI，具備：

- 專案狀態持久化
- 中斷後續跑
- 各 stage 產物落盤
- 明確的環境檢查、驗證、清理與續跑操作面

---

## 目前這個 repo 真的包含了什麼

### 已內建
- CLI 與設定載入
- 專案狀態管理與重跑控制
- 管線腳本（`vendor/pipeline_scripts/`）
- Gemini 翻譯邏輯
- 內建 ASR 路線（`src/qwenasr_mlx_cli/`）
- OmniVoice 轉接層與內嵌模型程式碼（`src/omnivoice/`）
- VoxCPM 轉接層

### 仍屬外部前置條件
- `ffmpeg` / `ffprobe`
- Gemini API key
- VoxCPM 本機服務（若要走 VoxCPM）
- OmniVoice 專用 Python 環境（若要走 OmniVoice；可由 `dub bootstrap-omnivoice` 自動建立）

---

## 正式支援的安裝契約

### 1. clone repo

```bash
git clone https://codeberg.org/killkli/video-dub-cli
cd video-dub-cli
```

### 2. 建立標準 dub 環境

```bash
uv sync --extra all
```

這個命令會建立 `.venv/`，並安裝：

- `dub` CLI
- 本地 ASR 依賴
- Gemini 翻譯依賴
- VoxCPM client 依賴

### 3. 安裝系統工具

```bash
# macOS
brew install ffmpeg

# Debian / Ubuntu
sudo apt-get install -y ffmpeg
```

### 4. 設定 Gemini API key

```bash
export GOOGLE_API_KEY=your_google_api_key
```

或：

```bash
cp .env.example .env
# 編輯 .env 後載入
set -a; source .env; set +a
```

### 5. 驗證標準環境

```bash
uv run dub --help
uv run dub doctor
```

---

## OmniVoice 的正式做法

OmniVoice **不再使用 `DUB_OMNIVOICE_ROOT`**。

目前正式做法是：

```bash
uv run dub bootstrap-omnivoice
```

這個命令會自動：

1. 建立 OmniVoice 專用 venv
2. 安裝 `video-dub-cli[tts-omnivoice]`
3. 把 `paths.omnivoice_python` 寫入設定檔

若你的設定檔不在預設位置：

```bash
uv run dub bootstrap-omnivoice --config /path/to/config.yaml
```

完成後可再驗證：

```bash
uv run dub doctor --config /path/to/config.yaml
```

當 `tts_backends.omnivoice` 顯示 `READY`，代表 OmniVoice 路線已可用。

---

## 主要命令

### 一鍵流程

```bash
uv run dub en2zh talk.mp4
uv run dub ja2zh anime.mp4
```

### 進階入口

```bash
uv run dub run talk.mp4 --source-lang en --target-lang zh
```

### 使用既有翻譯字幕

```bash
uv run dub run talk.mp4 \
  --source-lang en \
  --target-lang zh \
  --translate-mode use-existing \
  --translated-srt talk.zhtw.srt
```

### 續跑

```bash
uv run dub resume --project-dir /path/to/project
```

### 查看狀態

```bash
uv run dub status --project-dir /path/to/project
```

### 驗證產物

```bash
uv run dub validate --project-dir /path/to/project
```

### 清理後重跑

```bash
uv run dub clean --project-dir /path/to/project
uv run dub resume --project-dir /path/to/project
```

---

## `dub doctor` 會檢查什麼

目前 `dub doctor` 會直接檢查：

- `ffmpeg`
- `ffprobe`
- `repo_pipeline_scripts`
- `gemini_api_key`
- `py:qwen3_asr_mlx`
- `py:soundfile`
- `py:pydub`
- `py:silero_vad`
- `py:google_genai`
- `py:torchcodec`
- `tts_backends.omnivoice`
- `tts_backends.voxcpme`

另外它也會：

- 在 Hermes / CI shell 下，嘗試從 `~/.zshrc` / `~/.bashrc` 自動復原 `GOOGLE_API_KEY` / `GEMINI_API_KEY`
- 逐項列出 OmniVoice / VoxCPM 的 gate（wrapper / interpreter / deps / service）

注意：

- `doctor ok` 代表**標準 operator 路線可跑**
- 即使 OmniVoice 顯示 `BLOCKED`，只要標準 `en2zh` / `ja2zh` 路線可跑，整體 doctor 仍可能通過
- 若要讓 OmniVoice 變成 `READY`，請跑 `dub bootstrap-omnivoice`

---

## 專案輸出結構

每次執行都會把產物存成可續跑的專案結構：

- `01_raw_video/`
- `02_stems/`
- `03_asr/`
- `04_ref_audio/`
- `05_translate/`
- `05_translated_srt/`
- `06_tts_wav/`
- `07_final/`
- `.dub/state.json`
- `.dub/*.log`

最終影片位置通常是：

```text
<project>/07_final/video_dubbed_stem.mp4
```

---

## 設定檔原則

多數 operator 不需要手動改 `paths.*`。

常見情況只需要：

- 複製範例設定檔
- 設定 API key
- 需要 OmniVoice 時再跑 `dub bootstrap-omnivoice`

推薦起點：

```bash
mkdir -p ~/.config/dub
cp examples/config_en2zh.yaml ~/.config/dub/config.yaml
```

若要建立 OmniVoice 路線：

```bash
uv run dub bootstrap-omnivoice --config ~/.config/dub/config.yaml
```

---

## 文件索引

- `QUICKSTART.md`：5 分鐘上手
- `docs/operator-runbook.md`：故障排除與恢復流程
- `docs/operator-qa-real-backend-en2zh-2026-06-03.md`：英文→中文真實驗證紀錄
- `docs/operator-qa-real-backend-ja2zh-2026-06-03.md`：日文→中文真實驗證紀錄
- `docs/standalone-dependency-map.md`：依賴地圖

---

## 目前可以誠實宣稱的範圍

### 已驗證
- `uv sync --extra all`
- `uv run dub doctor`
- `uv run dub bootstrap`
- `uv run dub bootstrap-omnivoice`
- `uv run dub en2zh ...`
- `uv run dub ja2zh ...`
- `dub resume / status / validate / clean`

### 不應過度宣稱
- 不是所有 TTS backend 都在同一個 Python 環境內完成安裝
- OmniVoice 仍採「標準 dub venv + 專用 OmniVoice venv」雙環境契約
- VoxCPM 仍需要本機服務可用

這是目前已驗證、可維運、可交付的 operator contract。
