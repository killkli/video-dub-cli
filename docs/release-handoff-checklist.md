# Release / Handoff Checklist

這份 checklist 用來把 `video-dub-cli` 從目前的 operator-grade 狀態交接給下一位開發者或操作者。重點不是把所有項目都假裝完成，而是明確標示：哪些已驗證、哪些仍待補齊。

## 1. Repo / Branch 狀態

- [ ] 目前交接基線已回到 `main`（若在其他 branch，需在交接摘要中明寫原因）
- [ ] `git status --short` 為乾淨狀態，或僅保留交接方明確知道用途的 local supplement 文件
- [ ] README 與 docs 沒有引用不存在的檔案、舊 branch 名稱或舊路徑

## 2. CLI Surface（Phase 1 + AUTO-S1 完成的項目）

- [ ] `dub --help` 顯示 `auto`, `en2zh`, `ja2zh` 為主要入口，`run` 為 advanced
- [ ] `dub auto --help` 可正常顯示，說明 `--source-lang` 與 `<video>` 位置參數
- [ ] `dub en2zh --help` / `dub ja2zh --help` 可正常顯示
- [ ] `dub run --help` 可正常顯示（escape hatch）
- [ ] `dub resume --help` / `dub status --help` / `dub clean --help` / `dub validate --help` 可正常顯示

## 3. Auto-Workflow 契約（Phase 1-3 + AUTO-S1/S2 完成的項目）

- [ ] `dub auto <VIDEO>` 存在且為 canonical 一鍵入口
- [ ] `dub auto <VIDEO>` 預設 `--project-dir` 為 `<video-stem>.dub/` 在輸入影片旁邊
- [ ] `dub auto <VIDEO> --source-lang en` 等於 `dub en2zh <VIDEO>`
- [ ] `dub auto <VIDEO> --source-lang ja` 等於 `dub ja2zh <VIDEO>`
- [ ] `dub en2zh` / `dub ja2zh` 為明確語言方向別名（內部與 `dub auto` 共用同一 pipeline 合約）
- [ ] `dub run` 保留為進階 escape hatch，README / QUICKSTART 不以之為主要起點
- [ ] 零 flag `dub en2zh <VIDEO>` / `dub ja2zh <VIDEO>` 可完成 end-to-end（AC-1 PASS）

## 4. `dub doctor` 就緒訊息（AC-3）

- [ ] 全部 prerequisite 與 route backend 都滿足時，`dub doctor` 顯示 `doctor ok: ready for dub auto, dub en2zh, dub ja2zh` 而非泛用訊息
- [ ] 若只有部分 route 可用，`dub doctor` 顯示 lane-aware 訊息（例如 `doctor lanes: ready=... ; blocked=...`），列出缺少的項目與修復建議
- [ ] `dub doctor` 會自動從 `~/.zshrc` / `~/.bashrc` 復原 `GOOGLE_API_KEY` / `GEMINI_API_KEY`，並顯示 `note: auto-recovered ...`

## 5. Supported Scenario Contract

目前支援三類情境：

- [ ] `delegate`（預設）：`dub auto` / `en2zh` / `ja2zh` 走 Gemini 翻譯
- [ ] `use-existing`：附 `--translated-srt` 使用外部已翻譯 SRT
- [ ] `skip`：僅限既有專案，且 `05_translated_srt/video.zhtw.srt` 已存在

---

## 6. 驗證基線

最低交接驗證：

```bash
# CLI surface
uv run dub --help
uv run dub auto --help
uv run dub en2zh --help
uv run dub ja2zh --help

# doctor lane-aware message (needs GOOGLE_API_KEY set)
export GOOGLE_API_KEY=your_key
uv run dub doctor

# targeted tests
uv run pytest tests/test_cli.py -q
uv run pytest tests/integration/test_6e_route_scenarios.py -q
```

若有實際片源：

```bash
# real-backend smoke（英文）
uv run dub en2zh /path/to/talk.mp4

# real-backend smoke（日文）
uv run dub ja2zh /path/to/anime.mp4

# validate output
uv run dub validate --project-dir /path/to/talk.dub

# resume smoke
uv run dub resume --project-dir /path/to/talk.dub
```

---

## 7. Real-Backend Productization Surface

`dub doctor` 與 `uv sync --extra all` 已涵蓋真實 backend 所需依賴：

- [ ] `dub doctor` 顯示 `py:google_genai: OK`
- [ ] `dub doctor` 顯示 `py:torchcodec: OK`
- [ ] `dub doctor` 顯示 `omnivoice: READY` 或 `voxcpme: READY`（依本次語言與配置）
- [ ] `uv sync --extra all` 安裝後 `dub doctor` 可直接 green，無需再手動 `pip install`

---

## 8. Config / Examples

- [ ] `examples/config_delegate_en2zh.yaml` 為 canonical delegate 範例
- [ ] `examples/config_en2zh.yaml` 為向後相容 alias（指向 canonical）
- [ ] `examples/config_ja2zh.yaml` 為日文→中文範例
- [ ] `examples/config_use_existing_en2zh.yaml` 為外部字幕情境範例
- [ ] 沒有殘留會誤導使用者的舊欄位名稱或舊目錄假設

---

## 9. 目前可以誠實宣稱的範圍

### 已驗證

```
uv sync --extra all
uv run dub --help
uv run dub auto --help
uv run dub doctor                    # 自動從 ~/.zshrc 復原 Gemini key
uv run dub bootstrap                 # 列出 bootstrap 選項
uv run dub bootstrap-omnivoice
uv run dub bootstrap-voxcpm
uv run dub auto <VIDEO>              # canonical one-command entrypoint
uv run dub en2zh <VIDEO>            # explicit English→Chinese alias
uv run dub ja2zh <VIDEO>            # explicit Japanese→Chinese alias
dub resume / status / validate / clean
```

### 不應過度宣稱

- 不是所有 TTS backend 都在同一個 Python 環境內完成安裝
- OmniVoice 仍採「標準 dub venv + 專用 OmniVoice venv」雙環境契約
- VoxCPM 依賴本機服務（`127.0.0.1:8808`）

---

## 10. 非產品化缺口（交接時不要隱藏）

- 真實模型品質驗證仍需獨立做，不可由 fake backend QA 替代
- 任意陌生片源的一次成功率尚未被產品級驗證
- 外部技能腳本（ASR / TTS / assemble）的 availability 與品質仍依賴外部環境
- operator UX 仍偏工程向，錯誤訊息與引導仍可持續收斂

---

## 11. 建議的下一波工作

1. 任意陌生片源 / 多語境 / 雜訊場景的 real-backend regression wave
2. release smoke script：一鍵跑 help + integration + real-backend operator QA
3. 失敗場景 handoff：整理常見錯誤與修復手冊
4. 若 alias commands 再擴充（e.g. `dub zh2en`），README / QUICKSTART / runbook / checklist 要同波更新

---

## 12. Handoff 摘要（可直接複製）

```
video-dub-cli 目前已具備 operator-grade single-command workflow。
canonical 入口為 `dub auto <VIDEO>`，自動推斷英文→中文或日文→中文路由。
`dub en2zh` / `dub ja2zh` 為明確語言方向別名，內部與 `dub auto` 共用同一 pipeline 合約。
`dub run` 保留為進階 escape hatch。
`dub doctor` 只有在全部 shared prerequisites 與 route backends 都 ready 時，才顯示 `ready for dub auto, dub en2zh, dub ja2zh`；否則會改用 lane-aware ready/blocked 訊息。
`uv sync --extra all` + `dub doctor` 已是 real-backend productization surface：
real ASR / Gemini 與標準 VoxCPM route 所需依賴已收斂；
OmniVoice 與獨立 VoxCPM interpreter 由 `dub bootstrap-omnivoice` / `dub bootstrap-voxcpm` 建立。
`dub en2zh` / `dub ja2zh` 已有真實片源 end-to-end QA 紀錄（見 docs/operator-qa-real-backend-*）。
```