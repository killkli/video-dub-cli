# Quickstart — 5 分鐘上手 video-dub-cli (standalone contract)

> 這個 quickstart 對應 standalone clone+uv 安裝路徑。沒有其他 repo 要
> clone，沒有 `~/.hermes/...` 路徑要指定。

---

## 安裝

### 1. 安裝 `uv` (如果還沒有)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. clone 這個 repo

```bash
git clone https://codeberg.org/killkli/video-dub-cli
cd video-dub-cli
```

### 3. `uv sync` 一次到位

```bash
# 完整 standalone 環境（CLI + 翻譯 + TTS 助手 + ASR 助手）
uv sync --extra all
```

`uv` 會建立 `.venv/`，安裝：
- `dub` 主 CLI
- `dub-doctor`、`dub-bootstrap` script entrypoints
- `pyproject.toml` 內 `[project.optional-dependencies]` 的所有 extras

> 只想跑測試 / 開發：`uv sync --extra dev`
> 只要 bare CLI（單元測試用）：`uv sync`

### 4. 安裝系統工具

`dub run` 真正跑媒體前要裝 `ffmpeg` / `ffprobe`：

```bash
# macOS
brew install ffmpeg

# Debian / Ubuntu
sudo apt-get install -y ffmpeg
```

### 5. 設定翻譯 API key

`--translate-mode delegate`（預設）會呼叫 Gemini。需要匯出
`GOOGLE_API_KEY`（或 `GEMINI_API_KEY`）。

```bash
# 直接 export
export GOOGLE_API_KEY=your_g...n

# 或用 .env 風格
cp .env.example .env
# 編輯 .env 填入真實 key
set -a; source .env; set +a
```

### 6. 確認環境 ready

```bash
uv run dub doctor
```

passing 結果會列出每個 check 為 `OK`、每個 backend 為 `READY`。有
missing 就會被點名，請對照 `uv run dub bootstrap` 的說明修正。

> ASR 現在走 repo-owned in-process 路徑，不需要另外安裝一個
> `qwenasr-mlx` CLI 當 canonical operator workflow。

---

## 第一次跑

### Step 1：準備設定檔

```bash
mkdir -p ~/.config/dub/
cp examples/config_delegate_en2zh.yaml ~/.config/dub/config.yaml
```

`config_delegate_en2zh.yaml` 是公開參考模板，內含 legacy 相容欄位與
目前 standalone 契約的合理預設。多數情況**不需要改任何東西**。
需要客製時再改下面幾個欄位：

```yaml
paths:
  # Legacy 相容欄位。Stage 2 現在是 repo-owned；一般 operator 不需要設定。
  qwenasr_cli: null
  # Legacy 相容欄位。標準路徑通常不需要手動指定。
  omnivoice_python: python3
  # Legacy 相容欄位。標準路徑直接用 repo-owned runtime。
  skills_dir: <repo>/vendor/pipeline_scripts
  # 預設的 project 根目錄。
  dub_root: ~/video-dub-cli-runs/
  # 進階 / legacy 覆寫用。一般情況不要改，沿用 repo 內建路徑即可。
  tts_engines_dir: <repo>/vendor/pipeline_scripts

translation:
  provider: gemini
  model: gemini-2.5-flash
  api_env_var: GOOGLE_API_KEY
  temperature: 0.2
  mode: delegate
```

> 舊版範例檔裡的 `/path/to/...` placeholder 在 standalone 契約下已不
> 適用——請用真實絕對路徑或直接沿用內建預設值，不再保留
> `/path/to/qwenasr-mlx` 之類的字面值。新版範例檔的所有
> `paths.*` 欄位都已預設成可工作的 bare name 預設值，沒特別需求可
> 不用動。

### Step 2：跑配音

**英文 → 中文（一鍵 operator flow；delegate mode）**
```bash
uv run dub en2zh /path/to/input/my_talk.mp4
```

**日文 → 中文（一鍵 operator flow；delegate mode）**
```bash
uv run dub ja2zh /path/to/input/my_anime.mp4
```

**進階 / 底層入口（明確語言參數）**
```bash
uv run dub run /path/to/input/my_talk.mp4 --source-lang en --target-lang zh
```

**已有外部翻譯字幕（use-existing mode）**
```bash
uv run dub run /path/to/input/my_talk.mp4 \
  --source-lang en \
  --target-lang zh \
  --translate-mode use-existing \
  --translated-srt /path/to/input/my_talk.zhtw.srt
```

### Step 3：確認狀態

```bash
# 查看每個 stage 的狀態
uv run dub status --project-dir /path/to/dub-project/

# 驗證專案結構與最終輸出
uv run dub validate --project-dir /path/to/dub-project/
```

### Step 4：找到輸出

```
/path/to/dub-project/07_final/video_dubbed_stem.mp4
```

---

## 中斷後繼續

```bash
uv run dub resume --project-dir /path/to/dub-project/
```

---

## 清理重跑

```bash
# 刪除所有 stage 產物，重新來過（source video 保留）
uv run dub clean --project-dir /path/to/dub-project/

# 再跑一次
uv run dub en2zh /path/to/input/my_talk.mp4
```

只重跑特定 stage：

```bash
uv run dub clean --project-dir /path/to/dub-project/ --stage 6
uv run dub resume --project-dir /path/to/dub-project/
```

---

## ASR runtime（repo-owned）

Canonical path 是把 ASR 直接裝進 dub venv：

```bash
uv sync --extra all
uv run dub doctor
```

`dub doctor` 會直接檢查：

- `py:qwen3_asr_mlx`
- `py:soundfile`
- `py:pydub`
- `py:silero_vad`
- `py:torchcodec`

如果其中任何一項 missing，修的是 **這個 repo 的 venv**，不是去另裝
一個外部 `qwenasr-mlx` CLI。

`paths.qwenasr_cli` 仍保留在 schema，純粹是為了讓舊 YAML 還能 parse；
現在的 Stage 2 runtime 不再依賴它。

---

## TTS backend 相容覆寫 (`tts_engines_dir`)

預設情況下 Stage 5 走 repo-owned runner + vendored runtime 資源，
一般 operator 不需要改 `paths.*`。只有在你要重播舊設定、或刻意測試
自訂 wrapper 目錄時，才使用 `paths.tts_engines_dir`：

```yaml
paths:
  tts_engines_dir: /your/private/tts_wrappers
```

每個 backend 的 readiness 由 `dub doctor` 回報，列出 runner /
interpreter / deps / service 各個 gate：

```
tts_backends:
  omnivoice: READY (...)
  voxcpme:   READY (...)
```

`dub doctor` 同時會額外報告 `py:google_genai` 與 `py:torchcodec`
這兩個 real-backend 依賴 gate；在 Hermes / CI shell 中若偵測到
`~/.zshrc` 有 `GOOGLE_API_KEY / GEMINI_API_KEY` 的 export，會自動
復原並印出 `note: auto-recovered ...` 一行。

---

## 系統依賴摘要

| 依賴 | 必要？ | 安裝方式 |
|---|---|---|
| Python 3.11+ | yes | `uv` 自帶管理 |
| `uv` | yes | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `ffmpeg` / `ffprobe` | yes（任何真實 run） | `brew install ffmpeg` / `apt-get install ffmpeg` |
| repo-owned ASR Python deps | yes（ASR 模式） | `uv sync --extra all` |
| OmniVoice Python | optional（OmniVoice TTS backend） | 見 `dub bootstrap` |
| VoxCPM server | optional（VoxCPM TTS backend） | 見 `dub bootstrap` |
| `torchcodec` | yes（real ASR / `torchaudio >= 2.9`） | `uv sync --extra all` 已含 |
| `google-genai` | yes（real Gemini 翻譯） | `uv sync --extra all` 已含 |
| `gradio_client` | yes（VoxCPM TTS backend） | `uv sync --extra all` 已含 |
| Gemini API key | yes（delegate 翻譯） | `export GOOGLE_API_KEY=...`；或寫進 `~/.zshrc` 由 `dub doctor` 自動復原 |

`uv run dub doctor` 會把每一項都列出來。沒有 `~/.hermes/...` 路徑要求。

---

## 下一步

- 卡關 → `docs/operator-runbook.md` 故障排除
- 想了解 standalone 契約 → `docs/standalone-dependency-map.md` (T1)
- 想看 fresh operator 驗證結果 → `docs/qa-standalone-matrix.md` (T6)
- 想看 TTS adapter 設計 → `docs/tts-backend-consolidation.md` (T5)
- 想看真實片源 end-to-end QA 紀錄 → `docs/operator-qa-real-backend-en2zh-2026-06-03.md` / `docs/operator-qa-real-backend-ja2zh-2026-06-03.md`
