# Real-Backend Verification Gate (2026-06-03)

這份文件不是在宣稱 `video-dub-cli` 已完成真實 backend 驗收；相反地，它是用來把 **目前還沒完成的 real-backend 驗證閘門** 寫清楚，避免 fake-backend QA 被誤讀成 production verification。

## 目前已完成的是什麼

截至 2026-06-03，repo 已完成並可重現的，是 **fake-backend operator QA**：

- canonical operator QA note：`docs/operator-qa-canonical-flow-2026-06-03.md`
- CLI aliases：`dub en2zh` / `dub ja2zh`
- integration / regression coverage 綠燈
- `status` / `validate` / `.dub/state.json` / final artifact probe 對齊

這些成果可以支持：

- CLI wiring 正常
- stage orchestration 正常
- project state persistence 正常
- route selection 正常
- canonical artifact contract 正常
- operator-facing docs 已基本對齊 alias-era surface

## 目前尚未完成的是什麼

以下 **都還沒有** 被真實 backend 驗證：

1. 真實 `qwenasr-mlx` 的安裝摩擦、相依與穩定度
2. 真實 Gemini 翻譯的品質 / 成本 / latency / quota 邊界
3. 真實 OmniVoice / VoxCPM 的安裝與合成品質
4. 真實 ffmpeg 混音在陌生片源上的一次成功率
5. EN/JA→ZH 在不同片源長度、口音、背景噪音下的穩定度
6. operator 在沒有開發者介入時，自行排錯的成功率

因此，現在**不能**宣稱：

- production verified
- fully productized
- arbitrary real videos succeed first try
- real model quality has been accepted

## 真實 backend 驗證的最低 gate

在下一輪 real-backend verification 中，至少要補齊下面 6 個證據：

### Gate 1 — 真實 ASR route
- 使用真實 `qwenasr-mlx`
- 不可使用 `DUB_ASR_TEST_FIXTURE_SRT`
- 保留 `03_asr/video.srt` 作為 artifact
- 記錄實際 command、執行時間、是否需要額外模型下載

### Gate 2 — 真實 translate route
- 使用真實 Gemini provider
- 不可使用 `translation.provider=mock`
- 保留 request mode / model / env var contract
- 至少記錄一次成功翻譯與一次常見失敗類型（例如 quota / auth / malformed output）

### Gate 3 — 真實 TTS route
- 英文來源至少驗證一次 OmniVoice route
- 日文來源至少驗證一次 VoxCPM route
- 不可使用 fake TTS wrapper
- 保留 `.dub/05_tts.log` 作為 route evidence

### Gate 4 — Final media artifact correctness
- final MP4 可被 `ffprobe` 讀取
- duration 與來源片長合理接近
- 非空檔、非 0-byte、非明顯截斷
- 至少人工 spot-check 1~2 段影音同步情況

### Gate 5 — Operator follow-up surfaces
- `dub status` 成功
- `dub validate` 成功
- `.dub/state.json` 與實際產物一致
- completion summary 的 next-step 指令可直接工作

### Gate 6 — Failure / recovery evidence
- 至少驗證一個真實失敗場景的可恢復性
- 例如：API key 缺失、TTS backend 缺依賴、stage 6 後 clean+resume
- 要證明 operator 不必重跑全部 stage

## 建議的最小 real-backend 驗證組合

建議先做兩條最小樣本，不要一開始就宣稱全 coverage：

### Sample A — EN → ZH
- command: `uv run dub en2zh <short_english_video>`
- translate: Gemini
- TTS: OmniVoice route
- goal: 驗證最常見主入口

### Sample B — JA → ZH
- command: `uv run dub ja2zh <short_japanese_video>`
- translate: Gemini
- TTS: VoxCPM route
- goal: 驗證第二條 alias 主入口與日文 route

## 驗證完成前的 release 說法邊界

在 real-backend gate 完成前，README / handoff / release 說法應維持：

- 可以說：operator-grade CLI workflow
- 可以說：supported fake-backend single-command flow
- 可以說：repo-contained runtime contract 已成形
- 不可以說：production verified
- 不可以說：real backend accepted
- 不可以說：任意片源 fully supported

## 建議交付物

當下一輪 real-backend verification 開始時，應新增：

1. `docs/operator-qa-real-backend-en2zh-<date>.md`
2. `docs/operator-qa-real-backend-ja2zh-<date>.md`
3. 若遇到實際安裝痛點，再補：
   - `docs/troubleshooting-real-backend.md`

## 結論

目前 `video-dub-cli` 已完成的是：

- **產品化的 CLI/operator surface**
- **truthful fake-backend QA proof**
- **清楚的 support boundary**

下一個真正的 release gate，不是再多寫一份 fake-backend QA，而是補上 **real-backend verification evidence**。
