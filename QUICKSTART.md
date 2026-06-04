# Quickstart｜5 分鐘上手 video-dub-cli

這份文件只描述**目前已驗證的正式操作路徑**，並統一使用台灣繁體中文。

目前有兩條路：

1. **標準路線**：`uv sync --extra all` → `dub doctor` → `dub en2zh` / `dub ja2zh`
2. **OmniVoice 路線**：在標準路線之外，再執行 `dub bootstrap-omnivoice`

---

## 1. 安裝 `uv`

如果還沒有安裝 `uv`：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 2. 下載 repo

```bash
git clone https://codeberg.org/killkli/video-dub-cli
cd video-dub-cli
```

---

## 3. 建立標準執行環境

```bash
uv sync --extra all
```

這會建立 `.venv/`，並裝好：

- `dub` CLI
- 本地 ASR 依賴
- Gemini 翻譯依賴
- VoxCPM client 依賴

---

## 4. 安裝系統工具

```bash
# macOS
brew install ffmpeg

# Debian / Ubuntu
sudo apt-get install -y ffmpeg
```

---

## 5. 設定 Gemini API key

```bash
export GOOGLE_API_KEY=your_google_api_key
```

或：

```bash
cp .env.example .env
set -a; source .env; set +a
```

`dub doctor` 會先看 `GOOGLE_API_KEY`，也接受 `GEMINI_API_KEY`。

---

## 6. 確認環境是否可用

```bash
uv run dub doctor
```

你會看到：

- `ffmpeg: OK`
- `ffprobe: OK`
- `repo_pipeline_scripts: OK`
- ASR / Gemini 的 Python 依賴 gate
- `tts_backends:` 區塊

### 關於 `doctor` 的判讀

- `voxcpme: READY`：代表標準路線可用
- `omnivoice: BLOCKED`：不一定是錯，表示你**還沒有建立 OmniVoice 專用環境**
- 如果你需要 OmniVoice，再做下一步

---

## 7. 準備設定檔

```bash
mkdir -p ~/.config/dub
cp examples/config_en2zh.yaml ~/.config/dub/config.yaml
```

大多數情況下，這份檔案**不用改**。

---

## 8. 第一次直接跑

### 英文影片 → 中文

```bash
uv run dub en2zh /path/to/input/talk.mp4
```

### 日文影片 → 中文

```bash
uv run dub ja2zh /path/to/input/anime.mp4
```

### 進階入口

```bash
uv run dub run /path/to/input/talk.mp4 --source-lang en --target-lang zh
```

---

## 9. 找最終輸出

輸出專案會建立在影片旁邊，或依設定檔落到指定位置。

最終影片通常在：

```text
<project>/07_final/video_dubbed_stem.mp4
```

---

## 10. 中斷後續跑

```bash
uv run dub resume --project-dir /path/to/project
```

---

## 11. 查看狀態與驗證

```bash
uv run dub status --project-dir /path/to/project
uv run dub validate --project-dir /path/to/project
```

---

## 12. 清理後重跑

```bash
uv run dub clean --project-dir /path/to/project
uv run dub resume --project-dir /path/to/project
```

如果只要重跑某個 stage：

```bash
uv run dub clean --project-dir /path/to/project --stage 6
uv run dub resume --project-dir /path/to/project
```

---

## 13. 若你要用 OmniVoice

現在正式做法是：

```bash
uv run dub bootstrap-omnivoice --config ~/.config/dub/config.yaml
```

它會自動：

1. 建立 OmniVoice 專用 venv
2. 安裝 `video-dub-cli[tts-omnivoice]`
3. 寫入 `paths.omnivoice_python`

完成後重新驗證：

```bash
uv run dub doctor --config ~/.config/dub/config.yaml
```

如果看到：

```text
tts_backends:
  omnivoice: READY
```

就代表 OmniVoice 路線已可用。

---

## 14. 目前不要再用的舊說法

以下說法已過期：

- `DUB_OMNIVOICE_ROOT`
- 需要額外 clone 一份 OmniVoice repo 才能跑
- 需要額外安裝外部 `qwenasr-mlx` CLI

目前已驗證的正式做法是：

- ASR：repo 內建
- OmniVoice code：repo 內建
- OmniVoice heavy deps：由 `dub bootstrap-omnivoice` 自動建立專用環境

---

## 15. 出問題先跑什麼

先跑：

```bash
uv run dub doctor
uv run dub bootstrap
```

若是 OmniVoice 問題，再跑：

```bash
uv run dub bootstrap-omnivoice --config ~/.config/dub/config.yaml
```

更完整的故障排除請看：

- `docs/operator-runbook.md`
