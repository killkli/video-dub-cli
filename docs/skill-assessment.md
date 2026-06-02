# Skill Assessment: video-dub-cli as Hermes Agent Skill

**Date**: 2026-06-02
**Assessor**: T7 Writer
**CLI under assessment**: `video-dub-cli` (v0.1.0)
**Context**: DESIGN.md §13 — evaluate whether to package CLI as a Hermes Agent skill

---

## 1. 目的

讓 `dub <video.mp4> --src en --tgt zh` 也能從 Hermes Agent prompt 觸發，而不需要使用者知道 CLI 或手动输入命令。

---

## 2. 候選 Skill 名稱

`video-dub-cli`

---

## 3. 與現有 Skill 關係

| 現有 Skill | 關係 | 說明 |
|------------|------|------|
| `video-dubbing-pipeline` | 上游 / 並存 | 該 skill 是使用者手動呼叫 6 個 stage scripts 的文件來源，CLI 內部呼叫同樣的 scripts。本 CLI 不會取代它，也不該合併——兩者功能重疊但受眾不同。 |

**結論**：新 skill `video-dub-cli` 與 `video-dubbing-pipeline` **並存**，各有職責：
- `video-dubbing-pipeline`：單一 stage script 的操作手冊（給熟悉工具的人）
- `video-dub-cli`：端到端 pipeline CLI（給想一键跑完的人）

---

## 4. Trigger 條件

| Trigger phrase | 對應 action |
|----------------|-------------|
| `dub 這個影片` | `dub run <video>` |
| `幫我配音` | `dub run <video>` |
| `翻譯這個 YouTube 影片` | `yt-dlp` 下載 + `dub run` |
| `resume 這個配音專案` | `dub resume --project-dir <dir>` |
| `檢查配音狀態` | `dub status --project-dir <dir>` |
| `清理配音資料` | `dub clean --project-dir <dir>` |

---

## 5. 介面對應（CLI subcommand → Skill action）

| CLI subcommand | Skill action | Notes |
|----------------|--------------|-------|
| `dub run VIDEO --src en --tgt zh` | `dub_run(video, source_lang, target_lang, translate_mode)` | 最常用 |
| `dub resume --project-dir` | `dub_resume(project_dir)` | 中斷後繼續 |
| `dub status --project-dir` | `dub_status(project_dir)` | 狀態查詢 |
| `dub clean --project-dir` | `dub_clean(project_dir, keep_source, stage)` | 清理 |
| `dub validate --project-dir` | `dub_validate(project_dir)` | 驗證 |

---

## 6. 測試計畫

用以下 prompt 跑過一輪驗證：
```
我有一段英文影片在 /path/to/input/talk.mp4，幫我用中文配音。
```

預期行為：
1. 找到 `talk.mp4` 或询问路径
2. 執行 `dub run /path/to/input/talk.mp4 --source-lang en --target-lang zh`
3. 完成後報告輸出位置

---

## 7. 決定

**建議：開新 skill `video-dub-cli`**

| 理由 |
|------|
| CLI 已是 production-ready，封裝成 skill 成本低 |
| 與 `video-dubbing-pipeline` 並存不衝突，職責清晰 |
| 5 個 action 對應完整，trigger 語意自然 |
| 測試計畫簡單，可以快速驗證 |

**風險**：
- 使用者需要正確設定 `/path/to/config.yaml`（paths 在不同機器不同）
- skill 裡需要說明如何修改 paths，否則第一次觸發容易失敗

**配套動作**：
1. 將 `video-dub-cli` skill 文件寫入 `/path/to/dub-root/profiles/<profile>/skills/`（Skill author skill 可用）
2. 測試完成後更新 DESIGN.md §13 的狀態

---

**最終結論**：✅ 建議開新 skill，不建議現在就實作（等 T6 smoke test 通過，確認 CLI 本身穩定再封裝）