# Operator QA — supported single-command flow (2026-06-02)

這份記錄是 `video-dub-cli` 在 **已支援情境** 下的一次真實 operator 驗證，目的不是宣稱所有影片都已產品化，而是把目前可穩定工作的單一指令路徑、實際輸出、限制條件，固定成可追溯 reference。

## 驗證目標

- 情境：`delegate` 翻譯模式
- 來源語言：英文 `en`
- 目標語言：中文 `zh`
- 片源：測試短片 `test_short.mp4`
- 目標：確認 `dub run` 可從 fresh project 一路跑到最終 MP4，並且 `status` / `validate` / state artifact 都一致

## 驗證環境

- 日期：2026-06-02
- repo：`/path/to/video-dub-cli`
- branch：`feature/video-dub-cli-phase-next-productization`
- QA env builder：`tools/make_operator_qa_env.py`
- config：`.tmp_operator_qa/operator-config.yaml`
- 備註：此 QA 使用測試替身腳本（fake qwenasr / fake translate / fake TTS / fake assemble），用來驗證 CLI contract 與 stage wiring，不代表真實模型品質驗收

## 實際指令

```bash
python3 tools/make_operator_qa_env.py

dub run .tmp_operator_qa/test_short.mp4 \
  --source-lang en \
  --target-lang zh \
  --project-dir .tmp_operator_qa/op_phase5_run \
  --config .tmp_operator_qa/operator-config.yaml \
  --yes

dub status --project-dir .tmp_operator_qa/op_phase5_run

dub validate --project-dir .tmp_operator_qa/op_phase5_run
```

## `dub run` 實際輸出

```text
preflight: src=en tgt=zh project=.tmp_operator_qa/op_phase5_run mode=delegate route=translate=delegate (committed provider route)
2026-06-02 19:39:53.027 | INFO     | dub.runner:run_pipeline:79 - [01_stems] starting
2026-06-02 19:39:53.083 | INFO     | dub.runner:run_pipeline:97 - [01_stems] done
2026-06-02 19:39:53.084 | INFO     | dub.runner:run_pipeline:79 - [02_asr] starting
2026-06-02 19:39:53.502 | INFO     | dub.runner:run_pipeline:97 - [02_asr] done
2026-06-02 19:39:53.502 | INFO     | dub.runner:run_pipeline:79 - [03_ref_audio] starting
2026-06-02 19:39:53.533 | INFO     | dub.runner:run_pipeline:97 - [03_ref_audio] done
2026-06-02 19:39:53.533 | INFO     | dub.runner:run_pipeline:79 - [04_translate] starting
2026-06-02 19:39:57.849 | INFO     | dub.runner:run_pipeline:97 - [04_translate] done
2026-06-02 19:39:57.851 | INFO     | dub.runner:run_pipeline:79 - [05_tts] starting
2026-06-02 19:39:57.913 | INFO     | dub.runner:run_pipeline:97 - [05_tts] done
2026-06-02 19:39:57.913 | INFO     | dub.runner:run_pipeline:79 - [06_assemble] starting
2026-06-02 19:39:57.970 | INFO     | dub.runner:run_pipeline:97 - [06_assemble] done
run complete: project=.tmp_operator_qa/op_phase5_run
```

## `dub status` 實際輸出

```text
01_stems: done attempts=1
02_asr: done attempts=1
03_ref_audio: done attempts=1
04_translate: done attempts=1
05_tts: done attempts=1
06_assemble: done attempts=1
```

## `dub validate` 實際輸出

```text
validate ok: project=.tmp_operator_qa/op_phase5_run stages=6 mode=delegate translate_status=done
```

## 實際產物

專案目錄：`.tmp_operator_qa/op_phase5_run`

關鍵輸出：

- `01_raw_video/video.mp4`
- `02_stems/vocals.wav`
- `02_stems/instrumental.wav`
- `03_asr/video.srt`
- `04_ref_audio/line_1_ref.wav`
- `05_translate/video.zhtw.srt`  *(legacy sync path)*
- `05_translated_srt/video.zhtw.srt`  *(canonical translated subtitle path)*
- `06_tts_wav/line_1_tts.wav`
- `06_tts_wav/tts_normalized.wav`
- `07_final/video_dubbed_stem.mp4`
- `07_final/video_dubbed.mp4`

`ffprobe` 實測最終輸出：

```json
{
  "format": {
    "duration": "30.000000",
    "size": "419255"
  }
}
```

## State / route 佐證

`.dub/state.json` 反映本次 run 的核心契約：

- `source_lang: en`
- `target_lang: zh`
- `translate_mode: delegate`
- `03_asr.output_dir: 03_asr`
- `04_translate.output_dir: 05_translated_srt`
- `05_tts.output_dir: 06_tts_wav`
- `06_assemble.output_dir: 07_final`
- 六個 stage 全部 `done`

`.dub/05_tts.log` 內的實際命令：

```text
CMD: /usr/bin/python3 /path/to/video-dub-cli/.tmp_operator_qa/fake-skills/dubbing_batch_tts.py --zh-srt .tmp_operator_qa/op_phase5_run/05_translated_srt/video.zhtw.srt --en-srt .tmp_operator_qa/op_phase5_run/03_asr/video.srt --ref-dir .tmp_operator_qa/op_phase5_run/04_ref_audio --out-dir .tmp_operator_qa/op_phase5_run/06_tts_wav
```

這證明本次 operator flow 實際使用的是：

- canonical translated subtitle path：`05_translated_srt/video.zhtw.srt`
- 英文 ASR path：`03_asr/video.srt`
- TTS output path：`06_tts_wav/`

## 目前可以宣稱什麼

這次 QA 可以支持以下說法：

- `dub run` 已具備可工作的單一指令入口
- `delegate` 模式在支援情境下可從 fresh run 跑完整條 pipeline
- `status` / `validate` / state / artifact path 已對齊
- translated subtitle canonical contract 已落在 `05_translated_srt/video.zhtw.srt`

## 目前不能過度宣稱什麼

以下仍不應被描述成「已完全產品化」：

- 任意真實英文／日文影片都可零介入一次成功
- 真實 ASR / 翻譯 / TTS 品質已在此文件中驗證
- 所有外部技能腳本或模型 backend 都已完成 production hardening
- 所有失敗場景都有完整 operator UX 收斂

## 建議後續收尾

下一輪若要進 Phase 6，可聚焦：

1. release / handoff checklist
2. README 加入這份 QA note 的連結
3. 一次真實 backend（非 fake）的小樣本 operator 驗證
