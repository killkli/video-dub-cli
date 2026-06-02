from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".tmp_operator_qa"
SKILLS = OUT / "fake-skills"
FIXTURES = ROOT / "tests" / "fixtures"


def write_exe(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    SKILLS.mkdir(parents=True, exist_ok=True)

    fake_cli = OUT / "fake-qwenasr"
    write_exe(
        fake_cli,
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "lang = 'en'\n"
        "for i, arg in enumerate(sys.argv):\n"
        "    if arg == '--language' and i + 1 < len(sys.argv):\n"
        "        lang = sys.argv[i + 1]\n"
        "text = 'Hello and welcome.' if lang == 'en' else 'こんにちは。'\n"
        "sys.stdout.write('1\\n00:00:00,000 --> 00:00:01,000\\n' + text + '\\n')\n",
    )

    write_exe(
        SKILLS / "dubbing_extract_ref.py",
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
    )

    write_exe(
        SKILLS / "dubbing_batch_tts.py",
        "#!/usr/bin/env python3\n"
        "import argparse, re, sys\n"
        "from pathlib import Path\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--zh-srt', required=True)\n"
        "p.add_argument('--en-srt', required=True)\n"
        "p.add_argument('--ref-dir', required=True)\n"
        "p.add_argument('--out-dir', required=True)\n"
        "args = p.parse_args()\n"
        "text = Path(args.en_srt).read_text(encoding='utf-8', errors='replace').replace('\\r\\n','\\n').replace('\\r','\\n')\n"
        "out = Path(args.out_dir)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "cue_idx = 0\n"
        "for block in text.split('\\n\\n'):\n"
        "    block = block.strip()\n"
        "    if not block:\n"
        "        continue\n"
        "    lines = block.split('\\n')\n"
        "    if not lines or not re.match(r'\\d+', lines[0].strip()):\n"
        "        continue\n"
        "    cue_idx += 1\n"
        "    (out / f'line_{cue_idx}_tts.wav').write_bytes(b'\\x00' * 2048)\n"
        "if cue_idx == 0:\n"
        "    sys.exit(3)\n",
    )

    write_exe(
        SKILLS / "dubbing_batch_tts_vox.py",
        "#!/usr/bin/env python3\n"
        "import argparse, re, sys\n"
        "from pathlib import Path\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--zh-srt', required=True)\n"
        "p.add_argument('--ja-srt', required=True)\n"
        "p.add_argument('--ref-dir', required=True)\n"
        "p.add_argument('--out-dir', required=True)\n"
        "p.add_argument('--project-dir', required=True)\n"
        "args = p.parse_args()\n"
        "text = Path(args.ja_srt).read_text(encoding='utf-8', errors='replace').replace('\\r\\n','\\n').replace('\\r','\\n')\n"
        "out = Path(args.out_dir)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "cue_idx = 0\n"
        "for block in text.split('\\n\\n'):\n"
        "    block = block.strip()\n"
        "    if not block:\n"
        "        continue\n"
        "    lines = block.split('\\n')\n"
        "    if not lines or not re.match(r'\\d+', lines[0].strip()):\n"
        "        continue\n"
        "    cue_idx += 1\n"
        "    (out / f'line_{cue_idx}_tts.wav').write_bytes(b'\\x00' * 2048)\n"
        "if cue_idx == 0:\n"
        "    sys.exit(3)\n",
    )

    write_exe(
        SKILLS / "dubbing_assemble_loudnorm.py",
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
        "    sys.exit(2)\n"
        "shutil.copy2(src, dst)\n"
        "norm.write_bytes(b'\\x00' * 4096)\n",
    )

    write_exe(
        SKILLS / "dubbing_remix.py",
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
        "    sys.exit(2)\n"
        "shutil.copy2(src, dst)\n",
    )

    translator = OUT / "fake_translate.py"
    translator.write_text(
        "from pathlib import Path\n"
        "\n"
        "def translate_srt(src, dst):\n"
        "    text = Path(src).read_text(encoding='utf-8', errors='replace')\n"
        "    text = text.replace('Hello and welcome.', '哈囉，歡迎來到課堂。')\n"
        "    text = text.replace('こんにちは。', '哈囉，歡迎來到課堂。')\n"
        "    Path(dst).parent.mkdir(parents=True, exist_ok=True)\n"
        "    Path(dst).write_text(text, encoding='utf-8')\n",
        encoding="utf-8",
    )

    cfg = OUT / "operator-config.yaml"
    cfg.write_text(
        f"""
paths:
  qwenasr_cli: {fake_cli}
  omnivoice_python: /usr/bin/python3
  skills_dir: {SKILLS}
  translation_skill: {translator}
  dub_root: ~/.hermes

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

    shutil.copy2(FIXTURES / "test_short.mp4", OUT / "test_short.mp4")
    print(OUT)


if __name__ == "__main__":
    main()
