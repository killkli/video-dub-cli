# Auto Workflow Execution Wave — 2026-06-04

## Goal

把 `video-dub-cli` 的影片自動英文/日文轉中文流程，收斂成可直接輸入影片的一鍵 CLI 工作流，並以看板式節奏持續完成 operator-grade 交付。

## This wave's grounded baseline

- Branch: `feature/standalone-repo-uv`
- Canonical CLI: `dub auto`, `dub en2zh`, `dub ja2zh`
- `dub doctor` 已修正為預設可讀 `~/.config/dub/config.yaml`
- OmniVoice dedicated interpreter 已 bootstrap 至 `.venvs/omnivoice`
- `uv run dub doctor` 實測：`omnivoice READY`、`voxcpme READY`
- 測試素材：`tests/fixtures/test_short.mp4`（30s）、`tests/fixtures/test_5min.mp4`

## Workboard for this execution wave

### Lane 1 — Workflow truth / baseline
- 驗證 repo branch、工作樹、最新 commits
- 驗證 operator config / doctor / route readiness
- 驗證 smoke fixture 與隔離 project-dir 策略

### Lane 2 — Real smoke workflow
- 用隔離目錄跑 `dub auto <video>`
- 驗證 preflight route summary
- 驗證 stage artifact 生成
- 驗證 final output / state / ffprobe
- 若失敗，按 artifact gate 定位在哪一層失敗

### Lane 3 — Operator acceptance contract
- README / QUICKSTART / runbook 與真實行為對齊
- 記錄最短成功命令
- 記錄 rerun / resume / clean 紀律
- 記錄已驗證素材與 backend 依賴

### Lane 4 — Regression / hardening
- 把真 smoke 抓到的 bug 轉成測試
- 保持 `doctor`, `auto`, `resume`, `validate` 契約一致
- 任何修補都要有對應 verification command

## Acceptance criteria for this wave

1. `uv run dub doctor` 為綠
2. `dub auto <fixture>` 能在隔離 project-dir 真實啟動
3. 至少拿到完整 stage truth：
   - 成功產出 final MP4；或
   - 明確定位第一個實際失敗 stage，並留下可重現證據
4. 驗證不可只看 exit code：必須同時檢查 artifacts / state / ffprobe / stage logs
5. 所有新發現的契約缺口，要落成測試或文件

## This turn's execution order

1. 提交 `load_config()` 預設 operator config 修補
2. 建立此 execution-wave plan
3. 用 `tests/fixtures/test_short.mp4` 跑第一條隔離真實 smoke
4. 根據真實結果決定下一個 fix lane
