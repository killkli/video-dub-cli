# Quickstart — 5 分鐘上手 video-dub-cli

## 安裝

```bash
git clone <repo> ~/projects/video-dub-cli
cd ~/projects/video-dub-cli
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

驗證：
```bash
dub --help
```

---

## 第一次跑

### Step 1：準備設定檔

先建立設定目錄，並複製 canonical example：

```bash
mkdir -p ~/.config/dub/
cp examples/config_delegate_en2zh.yaml /path/to/config.yaml
vim /path/to/config.yaml   # 修改 paths（見下方）
```

`config_delegate_en2zh.yaml` 是公開參考模板。你需要把其中所有 `/path/to/...` 佔位路徑改成你自己機器上的實際路徑：
```yaml
paths:
  qwenasr_cli: /path/to/qwenasr-mlx
  omnivoice_python: /path/to/omnivoice-python
  skills_dir: /path/to/video-dubbing-pipeline/scripts
  dub_root: /path/to/dub-root
  translation_skill: /path/to/subtitle_translation.py

translation:
  provider: gemini
  model: gemini-2.5-flash
  api_env_var: GOOGLE_API_KEY
  temperature: 0.2
  mode: delegate
```

### Step 2：執行配音

**英文 → 中文（delegate mode，CLI 自己翻譯）：**
```bash
dub run /path/to/input/my_talk.mp4 --source-lang en --target-lang zh
```

**日文 → 中文（delegate mode，CLI 自己翻譯）：**
```bash
dub run /path/to/input/my_anime.mp4 --source-lang ja --target-lang zh
```

**已有外部翻譯字幕（use-existing mode）：**
```bash
dub run /path/to/input/my_talk.mp4 \
  --source-lang en \
  --target-lang zh \
  --translate-mode use-existing \
  --translated-srt /path/to/input/my_talk.zhtw.srt
```

### Step 3：確認狀態

```bash
# 查看每個 stage 的狀態
dub status --project-dir /path/to/dub-project/

# 驗證專案結構與最終輸出
dub validate --project-dir /path/to/dub-project/
```

### Step 4：找到輸出

```
/path/to/dub-project/07_final/video_dubbed_stem.mp4
```

---

## 中斷後繼續

```bash
dub resume --project-dir /path/to/dub-project/
```

---

## 清理重跑

```bash
# 刪除所有 stage 產物，重新來過
dub clean --project-dir /path/to/dub-project/

# 再跑一次
dub run /path/to/input/my_talk.mp4 --source-lang en --target-lang zh
```