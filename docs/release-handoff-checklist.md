# Release / Handoff Checklist

這份 checklist 用來把 `video-dub-cli` 從目前的 operator-grade 狀態，交接給下一位開發者、操作者，或下一輪產品化工作。重點不是把所有項目都假裝完成，而是明確標示：哪些已驗證、哪些仍待補齊。

## 1. Repo / branch 狀態

- [ ] 確認目前工作 branch 正確
- [ ] `git status --short` 為乾淨狀態
- [ ] README 與 docs 沒有引用不存在的檔案或舊路徑
- [ ] 最新變更已對應到可讀 commit 訊息

## 2. CLI surface

- [ ] `dub --help` 可正常顯示，且列出 `en2zh` / `ja2zh`
- [ ] `dub en2zh --help` 可正常顯示
- [ ] `dub ja2zh --help` 可正常顯示
- [ ] `dub run --help` 可正常顯示
- [ ] `dub resume --help` 可正常顯示
- [ ] `dub status --help` 可正常顯示
- [ ] `dub clean --help` 可正常顯示
- [ ] `dub validate --help` 可正常顯示

## 3. Supported scenario contract

目前應明確以這三類情境為主，其中 operator 主入口已是 alias commands：

- [ ] `delegate`：fresh run，由 CLI 直接執行翻譯 stage；常見 operator 入口為 `dub en2zh` / `dub ja2zh`
- [ ] `use-existing`：使用外部已翻譯 SRT
- [ ] `skip`：僅限既有 project，且 canonical translated subtitle 已存在

交接時必須確認文件仍符合目前行為：

- [ ] canonical translated subtitle path 是 `05_translated_srt/video.zhtw.srt`
- [ ] legacy sync path `05_translate/video.zhtw.srt` 仍有被正確描述為相容用途，而非主契約
- [ ] README 對 `skip` 模式的限制說明仍正確

## 4. Verification baseline

最低交接驗證應包含：

- [ ] targeted unit / integration tests 通過
- [ ] 至少一條 supported single-command flow 有實際 run 紀錄
- [ ] `status` / `validate` / `.dub/state.json` 三者對同一條 run 的解讀一致
- [ ] 最終 MP4 至少能被 `ffprobe` 讀取

建議最小驗證命令：

```bash
pytest tests/integration/test_6d_operator_flow.py -q
pytest tests/integration/test_6e_route_scenarios.py -q
```

如要做文件級 operator 驗證，參考：

- `docs/operator-qa-canonical-flow-2026-06-03.md`（fake-backend support-boundary 記錄）
- `docs/operator-qa-real-backend-en2zh-2026-06-03.md`（real-backend EN→ZH QA，已成功）
- `docs/operator-qa-real-backend-ja2zh-2026-06-03.md`（real-backend JA→ZH QA，已成功）
- `docs/real-backend-verification-gate-2026-06-03.md`（real-backend 閘門與非宣稱邊界）

## 4.5 Real-backend productization surface

`dub doctor` 與 `uv sync --extra all` 已涵蓋真實 backend 所需依賴：

- [ ] `dub doctor` 顯示 `py:google_genai: OK`
- [ ] `dub doctor` 顯示 `py:torchcodec: OK`
- [ ] `dub doctor` 顯示 `omnivoice: READY` 或 `voxcpme: READY`（依本次語言）
- [ ] `dub doctor` 在 zsh / Hermes shell 中會自動復原 `GOOGLE_API_KEY / GEMINI_API_KEY` 並印出 `auto-recovered ...` note
- [ ] `uv sync --extra all` 安裝後 `dub doctor` 直接 green，無需再手動 `pip install`

## 5. Config / examples

- [ ] `examples/` 內檔名與 README 引用一致
- [ ] `config_delegate_en2zh.yaml` 與 `config_use_existing_en2zh.yaml` 都可作為 canonical example
- [ ] 沒有殘留會誤導使用者的舊欄位名稱或舊目錄假設

## 6. Non-productized gaps

交接時不要隱藏以下風險：

- [ ] 真實模型品質驗證仍需獨立做，不可由 fake backend QA 替代
- [ ] 任意陌生片源的一次成功率尚未被產品級驗證
- [ ] 外部技能腳本（ASR / TTS / assemble）的 availability 與品質仍依賴外部環境
- [ ] operator UX 仍偏工程向，錯誤訊息與引導仍可持續收斂

## 7. Recommended next wave
## 7. Recommended next wave
如果要接續下一輪工作，建議優先順序：
1. 任意陌生片源 / 多語境 / 雜訊場景的 real-backend regression wave
2. release smoke script：一鍵跑 help + integration + real-backend operator QA
3. 失敗場景 handoff：整理常見錯誤與修復手冊
4. 若 alias commands 再擴充，README / QUICKSTART / runbook / checklist 要同波更新

## 8. Handoff verdict template

交接時可直接用這段摘要：

```text
video-dub-cli 目前已具備 operator-grade single-command workflow。
常見 operator 主入口為 `dub en2zh` / `dub ja2zh`；`dub run` 保留作進階底層入口。
已驗證的支援情境包括 delegate / use-existing / existing-project skip。
state / validate / integration coverage 已對齊。
`uv sync --extra all` + `dub doctor` 已是 real-backend productization surface：
real ASR / Gemini / OmniVoice / VoxCPM 所需依賴皆已收斂，`dub doctor` 會自動從
`~/.zshrc` 復原 Gemini key，並逐 gate 報告每一個 readiness 狀態。
`dub en2zh` / `dub ja2zh` 已有真實片源 end-to-end QA 紀錄。
```
