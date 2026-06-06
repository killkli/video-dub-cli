from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fake_qwenasr_config(tmp_path: Path) -> Path:
    skills_dir = tmp_path / "fake-skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    # ASR is now repo-owned (src/dub/stages/asr.py imports run_transcription
    # from the vendored qwenasr_mlx_cli package). Real MLX weights can't be
    # bundled in the integration suite, so we point the stage at a
    # pre-baked SRT fixture via the DUB_ASR_TEST_FIXTURE_SRT escape hatch
    # that the stage honours when explicitly set by a test harness.
    #
    # The SRT contains Chinese cues (哈囉, 歡迎...) so downstream assertions
    # such as "SRT contains Chinese characters" pass without running real
    # ASR. The fixture's en/ja-srt counterpart is read by the fake TTS
    # scripts to learn the cue count.
    asr_fixture = tmp_path / "fake-asr.srt"
    asr_fixture.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n哈囉，歡迎來到課堂。\n"
        "2\n00:00:02,000 --> 00:00:04,000\n這是第二句測試字幕。\n",
        encoding="utf-8",
    )

    fake_ref = skills_dir / "dubbing_extract_ref.py"
    fake_ref.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import sys, re\n"
        "video, srt, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]\n"
        "text = Path(srt).read_text(encoding='utf-8', errors='replace').replace('\\r\\n','\\n').replace('\\r','\\n')\n"
        "count = len(re.findall(r'-->.*', text))\n"
        "out = Path(out_dir)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "for i in range(1, count + 1):\n"
        "    (out / f'line_{i}_ref.wav').write_bytes(b'RIFFfakeWAVE')\n",
        encoding="utf-8",
    )
    fake_ref.chmod(0o755)

    # Fake dubbing_remix.py — stand-in for the real stem-preserving remixer.
    # The integration test only cares that the stage writes a real mp4 to
    # `--output` and exits 0; the real mixer is exercised by the unit tests
    # in tests/test_assemble_stage.py (with subprocess.run mocked).
    # Behaviour: copy 01_raw_video/video.mp4 → <output>.
    fake_remix = skills_dir / "dubbing_remix.py"
    fake_remix.write_text(
        "#!/usr/bin/env python3\n"
        "import argparse, shutil, sys\n"
        "from pathlib import Path\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--project-dir', required=True)\n"
        "p.add_argument('--vocal-mix', required=True)\n"
        "p.add_argument('--output', required=True)\n"
        "p.add_argument('--vocal-gain', type=float, default=3.0)\n"
        "p.add_argument('--inst-gain', type=float, default=-3.0)\n"
        "args = p.parse_args()\n"
        "src = Path(args.project_dir) / '01_raw_video' / 'video.mp4'\n"
        "dst = Path(args.output)\n"
        "dst.parent.mkdir(parents=True, exist_ok=True)\n"
        "if not src.exists():\n"
        "    sys.stderr.write(f'fake-remix: source missing: {src}\\n')\n"
        "    sys.exit(2)\n"
        "shutil.copy2(src, dst)\n",
        encoding="utf-8",
    )
    fake_remix.chmod(0o755)

    # Fake dubbing_assemble_loudnorm.py — stand-in for the real time-aligned
    # loudnorm builder. The stage wires it with:
    #   --video <video.mp4> --zh-srt <zh SRT> --tts-dir <06_tts_wav>
    #   --output <fulltrack.mp4> --save-normalized-wav <06_tts_wav/tts_normalized.wav>
    # Behaviour: copy source video → output, and write a >1000-byte stub WAV
    # for --save-normalized-wav (the next stage consumes it and enforces a
    # >1000 byte gate on tts_normalized.wav).
    fake_loudnorm = skills_dir / "dubbing_assemble_loudnorm.py"
    fake_loudnorm.write_text(
        "#!/usr/bin/env python3\n"
        "import argparse, shutil, sys\n"
        "from pathlib import Path\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--video', required=True)\n"
        "p.add_argument('--zh-srt', required=True)\n"
        "p.add_argument('--tts-dir', required=True)\n"
        "p.add_argument('--output', required=True)\n"
        "p.add_argument('--save-normalized-wav', required=True)\n"
        "args = p.parse_args()\n"
        "src = Path(args.video)\n"
        "dst = Path(args.output)\n"
        "dst.parent.mkdir(parents=True, exist_ok=True)\n"
        "if not src.exists():\n"
        "    sys.stderr.write(f'fake-loudnorm: source missing: {src}\\n')\n"
        "    sys.exit(2)\n"
        "shutil.copy2(src, dst)\n"
        "norm = Path(args.save_normalized_wav)\n"
        "norm.parent.mkdir(parents=True, exist_ok=True)\n"
        "# > 1000 bytes so the AssembleStage's tts_normalized gate passes.\n"
        "norm.write_bytes(b'\\x00' * 2048)\n",
        encoding="utf-8",
    )
    fake_loudnorm.chmod(0o755)

    # Fake dubbing_batch_tts.py — stand-in for the real OmniVoice per-segment
    # TTS script. The stage wires it with: --zh-srt <zh SRT> --en-srt <en SRT>
    # --ref-dir <ref dir> --out-dir <out dir>. We read the en SRT to learn
    # the cue count, then write a >1000-byte stub WAV for each line_<i> cue
    # to the out dir. The byte-size gate is enforced by the real TtsStage
    # is_done() — fake must produce >1000 bytes per wav or is_done trips.
    # (mirrors tests/fixtures/test_short.mp4's 30s clip — one cue per file is
    # enough for the integration tests; longer clips would just produce
    # more line_<i>_tts.wav files, all of which the fake handles identically.)
    fake_tts = skills_dir / "dubbing_batch_tts.py"
    fake_tts.write_text(
        "#!/usr/bin/env python3\n"
        "\"\"\"Fake OmniVoice per-segment TTS: write stub WAVs that satisfy the\n"
        "TtsStage.is_done() byte-size gate (>1000 bytes per file).\"\"\"\n"
        "import argparse, re, sys\n"
        "from pathlib import Path\n"
        "\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--zh-srt', required=True)\n"
        "p.add_argument('--en-srt', required=True)\n"
        "p.add_argument('--ref-dir', required=True)\n"
        "p.add_argument('--out-dir', required=True)\n"
        "args = p.parse_args()\n"
        "\n"
        "en_srt = Path(args.en_srt)\n"
        "out_dir = Path(args.out_dir)\n"
        "out_dir.mkdir(parents=True, exist_ok=True)\n"
        "if not en_srt.exists():\n"
        "    sys.stderr.write(f'fake-tts: en-srt missing: {en_srt}\\n')\n"
        "    sys.exit(2)\n"
        "\n"
        "text = en_srt.read_text(encoding='utf-8', errors='replace')\n"
        "text = text.lstrip('\\ufeff').replace('\\r\\n', '\\n').replace('\\r', '\\n')\n"
        "cue_idx = 0\n"
        "for block in text.split('\\n\\n'):\n"
        "    block = block.strip()\n"
        "    if not block:\n"
        "        continue\n"
        "    lines = block.split('\\n')\n"
        "    if not lines or not re.match(r'\\d+', lines[0].strip()):\n"
        "        continue\n"
        "    cue_idx += 1\n"
        "    # > 1000 bytes so the TtsStage is_done() byte-size gate passes.\n"
        "    (out_dir / f'line_{cue_idx}_tts.wav').write_bytes(b'\\x00' * 2048)\n"
        "if cue_idx == 0:\n"
        "    sys.stderr.write(f'fake-tts: no cues parsed from {en_srt}\\n')\n"
        "    sys.exit(3)\n",
        encoding="utf-8",
    )
    fake_tts.chmod(0o755)

    # Fake dubbing_batch_tts_vox.py — VoxCPM (ja→zh) route. Same behaviour as
    # the OmniVoice fake, except it accepts --ja-srt and --project-dir.
    # Adding it up front so the test config can flip source_lang=ja if needed.
    fake_tts_vox = skills_dir / "dubbing_batch_tts_vox.py"
    fake_tts_vox.write_text(
        "#!/usr/bin/env python3\n"
        "\"\"\"Fake VoxCPM per-segment TTS (ja→zh route). Writes stub WAVs.\"\"\"\n"
        "import argparse, re, sys\n"
        "from pathlib import Path\n"
        "\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--zh-srt', required=True)\n"
        "p.add_argument('--ja-srt', required=True)\n"
        "p.add_argument('--ref-dir', required=True)\n"
        "p.add_argument('--out-dir', required=True)\n"
        "p.add_argument('--project-dir', required=True)\n"
        "args = p.parse_args()\n"
        "\n"
        "ja_srt = Path(args.ja_srt)\n"
        "out_dir = Path(args.out_dir)\n"
        "out_dir.mkdir(parents=True, exist_ok=True)\n"
        "if not ja_srt.exists():\n"
        "    sys.stderr.write(f'fake-tts-vox: ja-srt missing: {ja_srt}\\n')\n"
        "    sys.exit(2)\n"
        "\n"
        "text = ja_srt.read_text(encoding='utf-8', errors='replace')\n"
        "text = text.lstrip('\\ufeff').replace('\\r\\n', '\\n').replace('\\r', '\\n')\n"
        "cue_idx = 0\n"
        "for block in text.split('\\n\\n'):\n"
        "    block = block.strip()\n"
        "    if not block:\n"
        "        continue\n"
        "    lines = block.split('\\n')\n"
        "    if not lines or not re.match(r'\\d+', lines[0].strip()):\n"
        "        continue\n"
        "    cue_idx += 1\n"
        "    (out_dir / f'line_{cue_idx}_tts.wav').write_bytes(b'\\x00' * 2048)\n"
        "if cue_idx == 0:\n"
        "    sys.stderr.write(f'fake-tts-vox: no cues parsed from {ja_srt}\\n')\n"
        "    sys.exit(3)\n",
        encoding="utf-8",
    )
    fake_tts_vox.chmod(0o755)

    # Fake dubbing_stems.py — stand-in for the real Demucs stem separator.
    # The real script invokes vocal-remover (MLX) on the source video; the
    # integration suite can't run that, so we write a stub vocals.wav and
    # an instrumental bed into <project>/02_stems/. The StemsStage's
    # is_done() requires:
    #   02_stems/<video>.vocals.wav exists AND mtime > source video mtime
    # so we explicitly bump the atime/mtime of the stub past the source.
    # The fake also writes video.mp4.instrumental.wav because the
    # AssembleStage reads it (and copies it from instrumental.wav as a
    # compatibility shim) — the real remix never consumes it because the
    # fake remix just copies the source video, but producing both keeps
    # the post-pipeline artifact set consistent with real runs.
    fake_stems = skills_dir / "dubbing_stems.py"
    fake_stems.write_text(
        "#!/usr/bin/env python3\n"
        "\"\"\"Fake Demucs stem separation: write a stub vocals.wav (and\n"
        "instrumental bed) into <project>/02_stems/ that satisfies the\n"
        "StemsStage.is_done() mtime gate.\"\"\"\n"
        "import argparse, os, sys\n"
        "from pathlib import Path\n"
        "\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('project_dir')\n"
        "p.add_argument('video_filename', nargs='?', default='video.mp4')\n"
        "p.add_argument('--stems', default='all')\n"
        "p.add_argument('--model', default=None)\n"
        "args = p.parse_args()\n"
        "\n"
        "project = Path(args.project_dir).resolve()\n"
        "video = project / '01_raw_video' / args.video_filename\n"
        "stems_dir = project / '02_stems'\n"
        "stems_dir.mkdir(parents=True, exist_ok=True)\n"
        "\n"
        "if not video.exists():\n"
        "    sys.stderr.write(f'fake-stems: source missing: {video}\\n')\n"
        "    sys.exit(2)\n"
        "\n"
        "vocals = stems_dir / f'{args.video_filename}.vocals.wav'\n"
        "instrumental = stems_dir / f'{args.video_filename}.instrumental.wav'\n"
        "# 2048 bytes is well past the 1000-byte gate the real Demucs would\n"
        # produce, and large enough for any downstream stage that probes size.\n"
        "vocals.write_bytes(b'\\x00' * 2048)\n"
        "instrumental.write_bytes(b'\\x00' * 2048)\n"
        "\n"
        "# Bump mtime past the source video so StemsStage.is_done() returns\n"
        "# True on the next run (resume / idempotency tests rely on this).\n"
        "src_mtime = video.stat().st_mtime\n"
        "for stub in (vocals, instrumental):\n"
        "    os.utime(stub, (src_mtime + 1, src_mtime + 1))\n",
        encoding="utf-8",
    )
    fake_stems.chmod(0o755)

    cfg = tmp_path / "integration-config.yaml"
    cfg.write_text(
        f"""
paths:
  qwenasr_cli: repo-owned-stage2
  omnivoice_python: /usr/bin/python3
  skills_dir: {skills_dir}
  translation_skill: /bin/true
  dub_root: /path/to/dub-root

translation:
  provider: mock
  model: mock-offline
  api_env_var: GOOGLE_API_KEY
  temperature: 0.0

defaults:
  source_lang: en
  target_lang: zh
  vocal_gain: 3.0
  inst_gain: -3.0
  keep_fulltrack: false

retry:
  max_attempts: 1
  backoff_seconds: 0.1
  retry_on:
    - subprocess.CalledProcessError
    - TimeoutError
    - ConnectionError

logging:
  level: INFO
  json_logs: false
  progress: rich
""".strip() + "\n",
        encoding="utf-8",
    )
    return cfg
