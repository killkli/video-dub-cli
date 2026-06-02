# Release / Handoff Checklist

這份 checklist 用來把 `video-dub-cli` 從目前的 operator-grade 狀態，交接給下一位開發者、操作者，或下一輪產品化工作。重點不是把所有項目都假裝完成，而是明確標示：哪些已驗證、哪些仍待補齊。

## 1. Repo / branch 狀態

- [ ] 確認目前工作 branch 正確
- [ ] `git status --short` 為乾淨狀態
- [ ] README 與 docs 沒有引用不存在的檔案或舊路徑
- [ ] 最新變更已對應到可讀 commit 訊息

## 2. CLI surface

- [ ] `dub --help` 可正常顯示
- [ ] `dub run --help` 可正常顯示
- [ ] `dub resume --help` 可正常顯示
- [ ] `dub status --help` 可正常顯示
- [ ] `dub clean --help` 可正常顯示
- [ ] `dub validate --help` 可正常顯示

## 3. Supported scenario contract

目前應明確以這三類情境為主：

- [ ] `delegate`：fresh run，由 CLI 直接執行翻譯 stage
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

- `docs/operator-qa-supported-flow-2026-06-02.md`

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

如果要接續下一輪工作，建議優先順序：

1. 真實 backend 小樣本 operator QA（非 fake）
2. README / QUICKSTART 再收斂為更短的操作者入口
3. release smoke script：一鍵跑 help + integration + operator QA
4. 失敗場景 handoff：整理常見錯誤與修復手冊

## 8. Handoff verdict template

交接時可直接用這段摘要：

```text
video-dub-cli 目前已具備 operator-grade single-command workflow。
已驗證的支援情境包括 delegate / use-existing / existing-project skip。
state / validate / integration coverage 已對齊。
尚未宣稱為 fully productized，因為真實 backend 品質驗證與陌生片源成功率仍待補強。
```
