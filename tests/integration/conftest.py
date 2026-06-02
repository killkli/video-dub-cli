from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fake_qwenasr_config(tmp_path: Path) -> Path:
    skills_dir = tmp_path / "fake-skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    fake_cli = tmp_path / "fake-qwenasr"
    fake_cli.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "lang = 'en'\n"
        "for i, arg in enumerate(sys.argv):\n"
        "    if arg == '--language' and i + 1 < len(sys.argv):\n"
        "        lang = sys.argv[i + 1]\n"
        "text = '哈囉，歡迎來到課堂。' if lang in {'zh','ja','en'} else '測試字幕。'\n"
        "sys.stdout.write('1\\n00:00:00,000 --> 00:00:01,000\\n' + text + '\\n')\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)

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

    # Fake dubbing_assemble_loudnorm.py — stand-in for the canonical
    # time-aligned builder. The real stage now always passes
    # --save-normalized-wav <06_tts_wav/tts_normalized.wav>, even when
    # keep_fulltrack=false. So the fake must both: (1) copy source video to
    # --output and (2) write a >1000-byte normalized wav to the requested path.
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
        "norm = Path(args.save_normalized_wav)\n"
        "dst.parent.mkdir(parents=True, exist_ok=True)\n"
        "norm.parent.mkdir(parents=True, exist_ok=True)\n"
        "if not src.exists():\n"
        "    sys.stderr.write(f'fake-loudnorm: source missing: {src}\\n')\n"
        "    sys.exit(2)\n"
        "shutil.copy2(src, dst)\n"
        "norm.write_bytes(b'\\x00' * 4096)\n",
        encoding="utf-8",
    )
    fake_loudnorm.chmod(0o755)

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

    cfg = tmp_path / "integration-config.yaml"
    cfg.write_text(
        f"""
paths:
  qwenasr_cli: {fake_cli}
  omnivoice_python: /usr/bin/python3
  skills_dir: {skills_dir}
  translation_skill: /bin/true
  dub_root: ~/.hermes

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
