# Operator Runbook｜故障排除與恢復指南

**日期：** 2026-06-04
**適用範圍：** `video-dub-cli` 正式操作工作流
**前提：** `uv sync --extra all` → `dub doctor` → `dub auto ...` / `dub en2zh ...` / `dub ja2zh ...`
**OmniVoice：** 若要啟用，另外跑 `dub bootstrap-omnivoice`

---

## 0. 任何問題，先做這兩步

```bash
uv run dub doctor
uv run dub bootstrap
```

判讀原則：

- `MISSING`：缺少必要項目
- `BLOCKED`：某條 backend 路線尚未就緒
- `READY`：該 backend 路線可用

成功時 `dub doctor` 會顯示 `ready for dub auto` 或 `ready for dub en2zh / dub ja2zh`。

若是 OmniVoice 問題，再補跑：

```bash
uv run dub bootstrap-omnivoice --config ~/.config/dub/config.yaml
```

---

## 1. 如何看專案狀態

每個專案都有：

- `.dub/state.json`
- `.dub/*.log`

### 常用檢查命令

```bash
uv run dub status --project-dir /path/to/project
uv run dub validate --project-dir /path/to/project
```

### 若要直接看 state

```bash
python3 -m json.tool /path/to/project/.dub/state.json
```

### 若要看某個 stage 的 log

```bash
tail -30 /path/to/project/.dub/05_tts.log
```

---

## 2. 什麼時候用 `resume`，什麼時候用 `clean`

### 用 `resume`

適合：中斷、stage 跑到一半中止、process 被殺掉。

```bash
uv run dub resume --project-dir /path/to/project
```

### 用 `clean --stage N` + `resume`

適合：某個 stage 已完成但產物有問題，想重跑該 stage 之後的內容。

```bash
uv run dub clean --project-dir /path/to/project --stage 6
uv run dub resume --project-dir /path/to/project
```

### 全部重跑但保留 source video

```bash
uv run dub clean --project-dir /path/to/project
uv run dub auto talk.mp4           # 重建新專案
# 或
uv run dub en2zh talk.mp4          # 重建新專案
```

---

## 3. 最常見的錯誤情境

### FR-1：`use-existing` 但沒給 `--translated-srt`

**錯誤訊息**

```
translate-mode=use-existing requires --translated-srt
```

**處理方式**

```bash
uv run dub auto talk.mp4 \
  --translate-mode use-existing \
  --translated-srt /path/to/talk.zhtw.srt
```

---

### FR-2：`--translated-srt` 指向不存在的檔案

**錯誤訊息**

```
translated SRT not found: /path/to/file.srt
```

**處理方式**

先確認檔案存在，再重跑：

```bash
uv run dub auto talk.mp4 \
  --translate-mode use-existing \
  --translated-srt /correct/path/to/talk.zhtw.srt
```

---

### FR-3：在全新專案上用 `--translate-mode skip`

**錯誤訊息**

```
translate-mode=skip requires an existing translated subtitle at
<project>/05_translated_srt/video.zhtw.srt
```

**原因**

你要求跳過翻譯，但專案裡還沒有既有的中文字幕。

**處理方式**

若有現成字幕，用 `use-existing`：

```bash
uv run dub auto talk.mp4 \
  --translate-mode use-existing \
  --translated-srt /path/to/talk.zhtw.srt
```

若沒有，直接走預設翻譯：

```bash
uv run dub auto talk.mp4          # 英文影片
uv run dub auto anime.mp4 --source-lang ja   # 日文影片
```

---

### FR-4：Stage 5 TTS 失敗或中途崩潰

**症狀**

- `status` 顯示 `05_tts: failed`
- `.dub/05_tts.log` 有錯誤

**處理方式**

先試：

```bash
uv run dub resume --project-dir /path/to/project
```

若仍失敗，再看 `.dub/05_tts.log` 判斷是哪條 backend 出問題。

---

### FR-5：Stage 6 組裝失敗

**症狀**

- `06_assemble` 或最終輸出失敗
- ffprobe / ffmpeg 報錯

**處理方式**

```bash
uv run dub clean --project-dir /path/to/project --stage 6
uv run dub resume --project-dir /path/to/project
```

這只會清掉最終輸出，不會動到前面的 ASR / 翻譯 / TTS 產物。

---

## 4. 與目前 standalone 契約直接相關的錯誤

### FR-6：`repo_pipeline_scripts: MISSING`

**症狀**

```
repo_pipeline_scripts: MISSING (...)
```

**原因**

repo 內建的 `vendor/pipeline_scripts/` 沒被正確找到。

**處理方式**

```bash
uv run dub doctor
```

若仍有問題，確認 repo 內容完整，並從 repo 根目錄執行。

這通常是 checkout / worktree 問題，不是 operator 設定問題。

---

### FR-7：`gemini_api_key: MISSING`

**症狀**

```
gemini_api_key: MISSING (GOOGLE_API_KEY,GEMINI_API_KEY)
```

**處理方式**

```bash
export GOOGLE_API_KEY=your_g..._key
uv run dub doctor
```

或：

```bash
cp .env.example .env
set -a; source .env; set +a
uv run dub doctor
```

如果你把 key 寫在 `~/.zshrc`，`dub doctor` 也會自動復原並顯示 `note: auto-recovered ...`。

---

### FR-8：`omnivoice: BLOCKED`

**症狀**

```
tts_backends:
  omnivoice: BLOCKED (...)
```

**這不一定是錯。**

如果只是跑標準 `en2zh` / `ja2zh` / `auto` 流程，而不是強制要用 OmniVoice，整體流程仍可能可用（`voxcpme: READY`）。

**若真的要啟用 OmniVoice**

```bash
uv run dub bootstrap-omnivoice --config ~/.config/dub/config.yaml
uv run dub doctor --config ~/.config/dub/config.yaml
```

目標是讓 `tts_backends.omnivoice` 顯示 `READY`。

---

### FR-9：`voxcpme: BLOCKED`

**常見原因**

- `gradio_client` / `opencc` 缺失
- 本機 VoxCPM 服務沒起來
- `127.0.0.1:8808` 無法連線

**處理方式**

先跑 `dub doctor` 確認缺少的是哪一個 gate：

- `deps:gradio_client` — 缺少 Python 套件
- `deps:opencc` — 缺少 Python 套件
- `service` — Python 套件已就緒，但 VoxCPM server 沒起來

標準路線檢查：

```bash
uv sync --extra all
uv run dub doctor
```

若要把 VoxCPM 重依賴隔離到獨立 interpreter：

```bash
uv run dub bootstrap-voxcpm
```

---

## 5. 關於 OmniVoice 的新規則

### 已廢棄

- `DUB_OMNIVOICE_ROOT`
- 額外 clone 一份 OmniVoice repo 才能讓 CLI 認得它

### 目前正式做法

- OmniVoice code 已 vendor 進 repo
- OmniVoice heavy deps 不跟標準 dub venv 混裝
- 用 `dub bootstrap-omnivoice` 建立獨立 venv
- `paths.omnivoice_python` 指向該 venv 的 Python

---

## 6. 建議的故障排除順序

### 第一步：看 readiness

```bash
uv run dub doctor
```

### 第二步：看 bootstrap 指引

```bash
uv run dub bootstrap
```

### 第三步：若是 OmniVoice，建立專用環境

```bash
uv run dub bootstrap-omnivoice --config ~/.config/dub/config.yaml
```

### 第四步：看專案狀態

```bash
uv run dub status --project-dir /path/to/project
uv run dub validate --project-dir /path/to/project
```

### 第五步：看 `.dub/*.log`

重點先看：

- `.dub/02_asr.log`
- `.dub/04_translate.log`
- `.dub/05_tts.log`
- `.dub/06_assemble_step1_tts.log`
- `.dub/06_assemble_remix.log`

---

## 7. 目前可以信任的操作面

以下命令都已經納入目前 operator contract：

```bash
uv sync --extra all
uv run dub --help
uv run dub auto --help
uv run dub doctor
uv run dub bootstrap
uv run dub bootstrap-omnivoice
uv run dub auto <VIDEO>              # canonical one-command entrypoint
uv run dub en2zh <VIDEO>             # explicit English→Chinese alias
uv run dub ja2zh <VIDEO>             # explicit Japanese→Chinese alias
uv run dub resume --project-dir <DIR>
uv run dub status --project-dir <DIR>
uv run dub validate --project-dir <DIR>
uv run dub clean --project-dir <DIR>
```

若文件內容與這些命令的真實輸出不同，應以命令實際輸出為準。

---

## 8. 與舊版文件的差異說明

本版 runbook 以 `dub auto` 為主要操作起點，並將 `dub run` 定位為進階 escape hatch。
舊版曾以 `dub run ... --source-lang en --target-lang zh` 為主要範例；該用法現在仍支援，但已非推薦路徑。