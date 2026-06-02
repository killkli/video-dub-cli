# Provider / route 盤點：translation / TTS / script / artifact contract

日期：2026-06-02
範圍：`video-dub-cli` 目前的 translation + TTS provider route、source_lang route、script route、artifact contract。

## 1) 四層路由的實際分界

### A. source_lang route

入口在 `src/dub/cli.py`：
- `_prepare_project()`（15-21）
- `_validate_run_contract()`（62-79）
- `run()` 會把 `--source-lang` / `--target-lang` merge 進 config（131-140）
- `_refresh_runtime_input_state()` / `_restore_cfg_from_state_inputs()` 把 `state.input.source_lang` / `target_lang` 來回寫回 config（38-59）

實際消費 source_lang 的地方：
- `src/dub/stages/asr.py` 39-40：`qwenasr-mlx transcribe ... --language <source_lang>`
- `src/dub/stages/tts.py` 117-125, 267-269：`_resolve_route(source_lang, skills_dir)` 決定跑哪個 TTS script
- `src/dub/stages/translate.py` 70-72：`translate_srt_file(... source_lang=..., target_lang=...)`

### B. provider route

配置入口在 `src/dub/config.py`：
- `TranslationConfig.provider`（24-31）

真正的 provider 行為在 `src/dub/translator_gemini.py`：
- `translate_srt_file()`（168-184）
- `cfg.provider.lower() == "mock"` 時只走 mock；否則一律 `_call_gemini()`（171-176）

`src/dub/stages/translate.py` 只 import `translate_srt_file`，沒有 provider registry（11-12, 21-86）。

### C. script route

目前外部 script 是 hardcoded 的路徑/檔名契約，不是註冊式路由。

- `src/dub/stages/asr.py` 27-40：`config.paths.qwenasr_cli`，執行 `qwenasr-mlx transcribe`
- `src/dub/stages/ref_audio.py` 112-123：`config.paths.skills_dir / "dubbing_extract_ref.py"`
- `src/dub/stages/translate.py` 11-12：固定呼叫 Gemini translator module
- `src/dub/stages/tts.py` 56-65, 267-286：`source_lang -> (dubbing_batch_tts.py | dubbing_batch_tts_vox.py)`，然後 shell out

### D. artifact contract

現況 artifact contract 是「檔名 + 固定目錄 + state.json 內的 stage artifact list」三者綁在一起：
- `src/dub/state.py` 20-40, 56-75：`ProjectState.input` / `StageState.artifacts`
- `src/dub/stages/translate.py` 18-19, 25-27, 57-75, 82-85：canonical translated SRT 以 `05_translated_srt/video.zhtw.srt` 為準，另外再 copy 一份到 `05_translate/video.zhtw.srt`
- `src/dub/stages/tts.py` 88-115, 321-339：TTS done/failed 判斷依賴 `03_asr/video.srt` 的 cue count，以及 `04_ref_audio/line_<i>_ref.wav` 與 `06_tts_wav/line_<i>_tts.wav`
- `src/dub/cli.py` 209-249：validate 固定檢查 `05_translated_srt/video.zhtw.srt`
- `src/dub/runner.py` 24-30, 64-73：`stage_state.output_dir + artifacts` 必須真的在磁碟上

## 2) 現在最脆弱的 3 個 coupling 點

### Weakness 1 — source_lang 同時控制 ASR 語言、TTS 路由，但 resume 只把它當 runtime input 回填

位置：
- `src/dub/cli.py` 38-59（`_refresh_runtime_input_state()` / `_restore_cfg_from_state_inputs()`）
- `src/dub/stages/asr.py` 39-40
- `src/dub/stages/tts.py` 56-65, 117-125, 267-269

為什麼脆弱：
- `source_lang` 不是單一 contract，而是同時影響 ASR `--language` 與 TTS script route。
- 但目前它只被存成 `state.input.source_lang`，resume 時會直接回填到 config，沒有「這個 project 原本是用哪個 route 跑出來的」的不可變記錄。
- 這代表只要人手改了 config、或 future 版加了新語言 route，resume 可能用新 route 重跑舊 project，造成 ASR / ref_audio / TTS 的語義不一致。

會壞什麼：
- 已存在的 project 可能在 resume 時改走不同 ASR language / TTS script。
- `03_asr/video.srt` 的 cue 語言、`04_ref_audio` 的切段語意、`06_tts_wav` 的對應關係可能被破壞，但 state 看起來仍然合法。

最小修法方向：
- 把 per-project 的 route manifest 明文化到 state（例如 `route_contract`：`source_lang`, `asr_lang`, `tts_route`, `translator_provider`），resume 只讀不改。
- 在 resume / validate 時檢查「state 裡的 route contract」與現有 artifact 是否一致，不一致就 fail fast。

### Weakness 2 — provider route 名義上可配置，實際上只有 Gemini（+ mock）

位置：
- `src/dub/config.py` 24-31（`TranslationConfig.provider`）
- `src/dub/stages/translate.py` 11-12, 21-86（固定 import `translate_srt_file`）
- `src/dub/translator_gemini.py` 168-184（`provider == "mock"` 否則一律走 Gemini）

為什麼脆弱：
- `TranslationConfig.provider` 看起來像 provider route，但 stage 並沒有做 registry dispatch。
- 目前它不是「多 provider」，而是「Gemini + mock」。
- 未來只要把 config 改成 `openrouter` / `anthropic` / `local`，如果沒有同步改 `translate_srt_file`，系統仍然會照舊呼叫 Gemini，或只在 mock 分支不同。

會壞什麼：
- config 的 provider 欄位會變成假訊號；操作員以為切了 provider，實際路由沒變。
- 任何新增翻譯 backend 都會卡在 `translator_gemini.py` 這個單點。

最小修法方向：
- 在 `stages/translate.py` 做 provider dispatch（registry / map / callable injection），不要讓 backend selection 隱含在 Gemini 模組內。
- `TranslationConfig.provider` 只描述「要用哪個 backend」，backend module 自己不再負責決策。

### Weakness 3 — translated SRT artifact contract 同時存在 canonical path、compat copy、state input，三者不是單一真相

位置：
- `src/dub/stages/translate.py` 18-19, 25-27, 57-75, 82-85
- `src/dub/cli.py` 65-78, 209-249
- `src/dub/state.py` 64-75（`input.translated_srt` 只是一個 input 欄位，不是 artifact contract）

為什麼脆弱：
- canonical path 是 `05_translated_srt/video.zhtw.srt`，但 stage 也會 copy 一份到 `05_translate/video.zhtw.srt`。
- validate 只看 canonical path；stage done 判斷也只看 canonical path；但 compatibility copy 仍然被保留，這讓「真正的 artifact 是哪個」變得含糊。
- `state.input.translated_srt` 又是另一個層次的資訊：它像是外部輸入，但不是產物 contract。

會壞什麼：
- 一旦檔名或目錄改版，validate / skip / resume / operator smoke 可能出現不同步。
- `05_translate` 與 `05_translated_srt` 的雙寫會讓後續 refactor 很容易只改一邊，另一邊的歷史相容殘留造成誤判。

最小修法方向：
- 讓 canonical translated_srt path 成為明確 contract（最好進 state snapshot / config contract），`05_translate` 只做 compatibility mirror，且在 code 註解/驗證上明講它不是 source of truth。
- 若要支援多語言，應把 canonical artifact path 從硬編碼 `video.zhtw.srt` 提升成 config / route contract 的一部分。

## 3) 最小設計方向：支援更多語言 / 更多 provider，但不要大改架構

我建議只做 3 個小步驟，不重寫 pipeline：

### Step 1 — 把 route contract 變成顯式資料

新增一個 project-level route snapshot（可放 `state.json`）：
- `source_lang`
- `target_lang`
- `translator_provider`
- `asr_language`
- `tts_route`
- `canonical_translated_srt`

原則：
- 現有 stage 邏輯先不大搬家
- 但 resume / validate / smoke test 不再推測 route，而是讀 contract

### Step 2 — provider registry 只動 translation layer

把 `translate_srt_file()` 變成 backend dispatcher：
- `gemini`
- `mock`
- future backends（例如 local / openrouter / anthropic）

原則：
- `TranslateStage` 只負責選 provider，不負責 prompt / API client 細節
- 新 provider 的接入點集中在 translation layer，不要擴散到 CLI 或 runner

### Step 3 — canonical artifact path 一致化

保留 `05_translate/` 作相容鏡像，但把唯一真相定義清楚：
- canonical translated SRT path = route contract 內的值
- `state.json` / validate / resume / stage skip 都只看 canonical path
- compatibility copy 只為舊工具或舊操作習慣服務

這樣的設計可以在 ≤ 3 commits 內落地：
1. 加 route contract snapshot + validate/resume 比對
2. 做 translation provider registry
3. 整理 canonical artifact path 與相容鏡像規則

## 4) 給 dev / runbook 的精簡備忘

- `source_lang` 不是單純 CLI 參數，它同時是 ASR 語言與 TTS route key。
- `TranslationConfig.provider` 目前是弱契約：能選 mock，但其餘都默認 Gemini。
- `05_translated_srt/video.zhtw.srt` 是目前唯一 canonical translated SRT；`05_translate/video.zhtw.srt` 只是 compatibility copy。
- 真正適合未來擴充的切點是「route contract 顯式化 + translation provider registry」，不是先重寫整個 pipeline。
