# video-dub-cli 專案狀態摘要與後續看板處理說明

**日期：** 2026-06-06
**Repo：** `/Users/johnchen/.hermes/projects/video-dub-cli`
**目前 branch：** `feature/next-wave-audit-roadmap`
**文件目的：** 統整目前專案真實狀態，說明已完成的 Phase 1 開發波次，以及後續看板應處理的強化 / 改善工作；避免再把當前任務誤描述為「從 0 開始開發」。

---

## 1. 目前專案真實狀態

### 1.1 結論

`video-dub-cli` 目前**不是起步中的原型專案**，也**不是尚未形成正式 CLI 的草稿**。

依據 repo、CLI、Phase 1 看板與測試現況，較準確的描述是：

- 已有正式 CLI 與 one-command workflow 入口
- 已完成一輪正式的 Kanban 規劃、開發、QA、cleanup
- 產品已進入**可執行、可運作、可驗證**的階段
- 但尚未達到「全部驗證全綠、可宣稱完全收斂」的 finished 狀態
- 當前工作重心應定義為：**強化、補穩、改善 operator-grade 契約與測試完整性**

### 1.2 不能再用的描述

以下說法不準確：

- 「現在要開始開發 video-dub-cli」
- 「目前還在建正式 CLI 基礎」
- 「專案尚未可運作」

### 1.3 應採用的描述

以下說法較準確：

> `video-dub-cli` 已完成正式 CLI 與 auto workflow 主體建置，並已完成一波 Kanban 驅動的 Phase 1 quick wins、QA 與 cleanup。當前任務是持續強化 runtime 契約、補齊測試與整合 seam、改善 operator UX / reliability，而不是重新開始做產品開發。

---

## 2. 已完成狀態（截至本文件撰寫時）

### 2.1 Phase 1 execution board 已完成

實查 `video-dub-cli-phase1-exec` 看板，全部卡片已完成：

- `t_17bb2f1c` — P1-T0 branch gate: phase1 execution baseline
- `t_975f08aa` — P1-A implement UX quick wins batch
- `t_bcc47c75` — P1-B implement reliability quick wins
- `t_91f1cdde` — P1-C translation batching and verification groundwork
- `t_7585e58f` — P1-QA final phase1 review
- `t_65eda6b2` — P1-cleanup doc follow-up: FR numbering + track canonical plan

### 2.2 cleanup follow-up 已完成

`t_65eda6b2` 的完成 summary 顯示，本輪 cleanup 已實際收掉：

- runbook FR 編號歧義整理
- VoxCPM doctor remediation cross-ref 對齊
- `docs/plans/2026-06-06-phase1-quick-wins-plan.md` 正式納入 git tracking

對應 commits：

- `0932d80` — `doc(runbook,plans): resolve FR numbering ambiguity [P1-cleanup]`
- `fbd9d6d` — `fix(cli): align voxcpme doctor remediation FR reference [P1-cleanup]`
- `8074293` — `docs(plans): track canonical phase1 quick wins plan [P1-cleanup]`

### 2.3 Repo 現況乾淨

實查 `git status --short --branch`：

- branch: `feature/next-wave-audit-roadmap`
- working tree: clean

這表示目前不是一個留著未整理髒工作樹、還沒收束的半完成狀態。

---

## 3. 已形成的產品面能力

### 3.1 正式 CLI 已存在

實查 `uv run dub --help`，目前已存在正式 CLI 與命令集合：

- `dub auto`
- `dub bootstrap`
- `dub bootstrap-omnivoice`
- `dub bootstrap-voxcpm`
- `dub clean`
- `dub doctor`
- `dub en2zh`
- `dub ja2zh`
- `dub resume`
- `dub run`
- `dub status`
- `dub validate`

這表示產品層級已不是單一腳本或臨時 runner，而是具備正式命令面。

### 3.2 one-command workflow 已存在

實查 `uv run dub auto --help`，已可確認：

- `dub auto <VIDEO>` 是正式入口之一
- 支援 `--source-lang` override
- 支援 source language auto-detection
- 對 ambiguous detection 採 fail-fast，而非 silent fallback
- 支援 `--project-dir`、`--config`、`--translate-mode`、`--translated-srt`

這表示「輸入影片後自動走後續流程」的工作流主體已落地，不應再被描述為尚未建立。

---

## 4. 目前尚未收斂之處

### 4.1 測試現況不是全綠

實查 `uv run pytest -q` 結果：

- `285 passed`
- `12 failed`
- `1 skipped`

因此目前不能把專案描述成「完全 finished / 全部驗證通過」。

### 4.2 主要失敗面向

#### A. fake backend / integration seam 失敗

多數 integration test 失敗訊息集中於：

- `stems script not found: .../fake-skills/dubbing_stems.py`

這代表當前主要問題不是 CLI 不存在，也不是主工作流完全不可用，而是：

- 測試用 fake backend 路徑契約未完全同步
- `DUB_PIPELINE_SCRIPTS_DIR` / fake skills lookup 與目前 runtime 預期不一致
- repo-owned runtime script 與 integration harness 之間仍有接縫要補

#### B. TTS entrypoint 依賴 / help 契約未完全隔離

另有測試失敗集中於：

- OmniVoice help probe 因 `transformers` 缺失而失敗
- VoxCPM module entrypoint 因 `gradio_client` 缺失而失敗

這表示仍需加強：

- help / bootstrap / doctor / runtime import 邊界
- optional dependency 與 operator-facing probe 的隔離策略
- vendored TTS runner entrypoint 的測試契約

---

## 5. 對專案狀態的正式定位

### 5.1 正式定位

目前應將專案定位為：

**「已完成正式 CLI 與 auto workflow 主體、已完成一輪 Kanban quick wins / QA / cleanup，現階段進入 operator-grade 強化與整合收斂。」**

### 5.2 不是當前任務的事項

以下不應被當作這一輪工作的主敘事：

- 從零建立 CLI
- 決定是否要做 auto workflow
- 把單一 script 第一次包成產品
- 宣稱目前已無剩餘工程風險

### 5.3 當前任務的準確敘事

以下才是準確敘事：

- 補齊 runtime / fake-backend / operator QA 契約
- 修整測試 seam，讓產品可持續驗證
- 強化 doctor / bootstrap / help / resume / validate 的 operator-grade 信任度
- 把已可運作的 workflow 收斂成更穩定、更可交付的成品

---

## 6. 後續看板應處理的工作狀態描述

下一波看板不應命名或敘述成「開始做 auto workflow 開發」，而應明確描述為**強化波次**或**收斂波次**。

### 6.1 建議的看板敘事

建議採用以下描述：

> 本波次目標不是重新開發 `video-dub-cli`，而是針對已存在且可運作的 CLI / auto workflow，進行 operator-grade 強化、測試契約補齊、runtime seam 修正、文件與驗證一致性收斂。

### 6.2 建議後續工作流分組

#### WS-A — 測試 / fake backend 契約收斂

目的：讓 integration harness 再次對齊目前 repo-owned runtime。

應處理內容：
- 補齊 fake `dubbing_stems.py` seam 或修正 stage lookup 規則
- 讓 `DUB_PIPELINE_SCRIPTS_DIR` 與 config override 的測試約定重新一致
- 修正 `dub run` / `resume` / `en2zh` / `ja2zh` / route-scenario integration tests
- 以 focused pytest 驗證測試面恢復

#### WS-B — TTS entrypoint / optional dependency 邊界強化

目的：讓 operator-facing help / doctor / bootstrap 不因重依賴缺失而直接崩潰。

應處理內容：
- OmniVoice runner `--help` 的 import boundary
- VoxCPM runner entrypoint 的依賴檢查與 graceful failure contract
- bootstrap / doctor / readiness 提示與實際 import probe 一致
- 補 focused tests 鎖定行為

#### WS-C — operator-grade 回歸驗證收斂

目的：確認目前對外主張的 supported flow 與真實 CLI 行為一致。

應處理內容：
- `dub auto` / `dub doctor` / `dub validate` / `dub resume` operator path 回歸
- docs / runbook / QUICKSTART 與 CLI 實際輸出對齊
- 若必要，補一輪 fake-backend smoke + 一輪 real-backend smoke checklist

#### WS-D — 文件 truthfulness / release handoff 收尾

目的：讓 repo 內文件對專案真實狀態描述一致，不誇大、不落後。

應處理內容：
- README / QUICKSTART / operator runbook 的「可用但仍在強化」表述
- release handoff / acceptance docs 是否需更新
- 把本文件作為後續 planning / board kickoff 的狀態基底

---

## 7. 建議的看板狀態標籤語言

後續卡片標題與狀態說明，建議避免以下用語：

- `build auto workflow`
- `start CLI productization`
- `initial standalone workflow`

建議改用以下用語：

- `stabilize fake-backend integration contract`
- `harden TTS entrypoint dependency boundaries`
- `restore operator-grade integration green path`
- `align docs / tests / runtime truth for supported workflow`
- `phase2 hardening and convergence`

---

## 8. 建議的下一輪看板目標句

後續若要再開一個新 wave，看板目標句建議可直接用：

> 針對已可運作的 `video-dub-cli` 正式 CLI 與 auto workflow，執行 Phase 2 hardening：補齊 fake-backend / integration seams、收斂 TTS entrypoint dependency boundaries、恢復 operator-grade regression 綠燈，並使 docs / tests / runtime truth 再次一致。

---

## 9. 與既有 Phase 1 文件的關係

本文件不是取代 `docs/plans/2026-06-06-phase1-quick-wins-plan.md`。

兩者關係如下：

- `2026-06-06-phase1-quick-wins-plan.md`
  - 記錄本輪 Phase 1 quick wins 的來源、範圍、排序與執行意圖
- `2026-06-06-project-status-and-next-wave-state.md`
  - 記錄 Phase 1 完成後，專案的真實位置，以及下一輪看板應如何描述與收斂

---

## 10. 現階段一句話摘要

**`video-dub-cli` 已完成可執行 CLI 與 auto workflow 主體建設，當前任務是 hardening 與 convergence，不是重新開始開發。**
