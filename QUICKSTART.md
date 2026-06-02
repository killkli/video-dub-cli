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

```bash
mkdir -p ~/.config/dub/
cp examples/config_en2zh.yaml ~/.config/dub/config.yaml
vim ~/.config/dub/config.yaml   # 修改 paths（見下方）
```

`config_en2zh.yaml` 需要修改的 paths：
```yaml
paths:
  qwenasr_cli: /path/to/qwenasr-mlx
  omnivoice_python: /path/to/omnivoice-python
  skills_dir: /path/to/video-dubbing-pipeline/scripts
  dub_root: ~/.hermes
  translation_skill: /path/to/subtitle_translation.py
```

### Step 2：執行配音

```bash
dub run /path/to/input/my_talk.mp4 --source-lang en --target-lang zh
```

### Step 3：找到輸出

輸出位置：`~/.hermes/dub-my_talk-<timestamp>/07_final/video_dubbed_stem.mp4`

---

## 中斷後繼續

```bash
dub resume --project-dir ~/.hermes/dub-my_talk-<timestamp>/
```

---

## 確認狀態

```bash
dub status --project-dir ~/.hermes/dub-my_talk-<timestamp>/
```

---

## 清理重跑

```bash
# 刪除所有 stage 產物，重新來過
dub clean --project-dir ~/.hermes/dub-my_talk-<timestamp>/

# 再跑一次
dub run /path/to/input/my_talk.mp4 --source-lang en --target-lang zh
```

---

## 常用範例

### 英文 → 中文
```bash
dub run talk.mp4 --source-lang en --target-lang zh
```

### 日文 → 中文
```bash
# 先確認 config_ja2zh.yaml 中的 voxcpm 路徑正確
cp examples/config_ja2zh.yaml ~/.config/dub/config.yaml
dub run anime.mp4 --source-lang ja --target-lang zh
```

### 使用已翻譯的 SRT（跳過翻譯 stage）
```bash
dub run talk.mp4 --source-lang en --target-lang zh \
  --translate-mode use-existing \
  --translated-srt /path/to/translated.srt
```