# Quickstart｜5 分鐘上手 video-dub-cli

目前已驗證的標準操作路徑，統一使用台灣繁體中文。

---

## 1. 安裝 `uv`

如果還沒有安裝 `uv`：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 2. Clone 並進入 repo

```bash
git clone https://codeberg.org/killkli/video-dub-cli
cd video-dub-cli
```

---

## 3. 建立標準執行環境

```bash
uv sync --extra all
```

這會建立 `.venv/`，並安裝 `dub` CLI、本地 ASR 依賴、Gemini 翻譯依賴與標準 VoxCPM route 依賴。

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
export GOOGLE_API_KEY=your_g...
```

或：

```bash
cp .env.example .env
set -a; source .env; set +a
```

`dub doctor` 會自動從 `~/.zshrc` / `~/.bashrc` 復原 key。

---

## 6. 確認環境就緒

```bash
uv run dub doctor
```

成功時會看到：

```
doctor ok: ready for `dub auto`, `dub en2zh`, `dub ja2zh`
next:    uv run dub auto <video>

# 若某一路徑 backend 未就緒，doctor 會改印 `doctor lanes: ready=... ; blocked=...`
```

缺少項目時，`dub doctor` 會列出缺少的項目與修復方式。

---

## 7. 第一次直接跑

### `dub auto`（推薦起點）

`dub auto` 執行 30 秒音訊探針，自動判斷來源語言（英文或日文），再選擇對應路線。明確的 `--source-lang` 永遠優先。

```bash
uv run dub auto talk.mp4           # 自動偵測（30 秒探針後選路）
uv run dub auto talk.mp4 --source-lang en    # 明確指定英文→中文
uv run dub auto anime.mp4 --source-lang ja    # 明確指定日文→中文
```

### 語言專用別名

若要明確指定語言方向，可使用專用別名：

```bash
uv run dub en2zh talk.mp4    # 英文→中文
uv run dub ja2zh anime.mp4   # 日文→中文
```

別名內部與 `dub auto` 共用同一套 staged pipeline 合約，只是語言方向已寫死。

### 使用既有翻譯字幕

```bash
uv run dub auto talk.mp4 \
  --translate-mode use-existing \
  --translated-srt talk.zhtw.srt
```

### 進階入口（需明確控制時使用）

```bash
uv run dub run talk.mp4 --source-lang en --target-lang zh --config ~/.config/dub/config.yaml
```

`dub run` 保留作為進階 escape hatch；常見情境請用 `dub auto` 或別名。

---

## 8. 找最終輸出

完成時 CLI 會印出最終影片路徑。預設專案目錄為 `<video-stem>.dub/` 在輸入影片旁邊：

```text
<project>/07_final/video_dubbed_stem.mp4
```

若要做可重現 smoke，建議顯式指定隔離 `--project-dir`：

```bash
uv run dub auto tests/fixtures/test_short.mp4 \
  --source-lang en \
  --project-dir ~/.hermes/dub-cli-test/smoke-20260604-t10-qa \
  --config ~/.config/dub/config.yaml \
  --yes
```

---

## 9. 續跑

```bash
uv run dub resume --project-dir /path/to/project
```

---

## 10. 查看狀態與驗證

```bash
uv run dub status --project-dir /path/to/project
uv run dub validate --project-dir /path/to/project
```

---

## 11. 清理後重跑

```bash
uv run dub clean --project-dir /path/to/project
uv run dub resume --project-dir /path/to/project
```

若只想重跑某個 stage：

```bash
uv run dub clean --project-dir /path/to/project --stage 6
uv run dub resume --project-dir /path/to/project
```

---

## 12. 若要使用 OmniVoice

```bash
uv run dub bootstrap-omnivoice --config ~/.config/dub/config.yaml
uv run dub doctor --config ~/.config/dub/config.yaml
```

目標是看到 `tts_backends.omnivoice: READY`。

`bootstrap-omnivoice` 現在不只會建立 venv，還會立刻驗證該 venv 能 import `torch`、`omnivoice`、`opencc`；這三個 import 不通，就不應直接進 smoke。

---

## 進階：自訂設定檔

多數情境**不需要**設定檔。若需自訂：

```bash
mkdir -p ~/.config/dub
cp examples/config_en2zh.yaml ~/.config/dub/config.yaml
```

---

## 出問題先跑什麼

```bash
uv run dub doctor
uv run dub bootstrap
```

若是 OmniVoice 路線異常，優先補跑：

```bash
uv run dub bootstrap-omnivoice --config ~/.config/dub/config.yaml
uv run dub doctor --config ~/.config/dub/config.yaml
```

完整故障排除請看 `docs/operator-runbook.md`。
