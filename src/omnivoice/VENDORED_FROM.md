# Vendored OmniVoice inference subset

These files were copied from the OmniVoice repository on this machine:

- Source repo: `https://github.com/k2-fsa/OmniVoice`
- Local checkout: `/Users/johnchen/Dev/OmniVoice`
- Source commit: `a4068c820f21307df337e34f67d3dda443735ad4`
- License: Apache-2.0

Vendored scope in this repo:
- `src/omnivoice/models/omnivoice.py`
- `src/omnivoice/utils/audio.py`
- `src/omnivoice/utils/duration.py`
- `src/omnivoice/utils/lang_map.py`
- `src/omnivoice/utils/text.py`
- `src/omnivoice/utils/voice_design.py`
- package `__init__.py` files needed for importability

Why vendored:
- `video-dub-cli` needs a repo-contained OmniVoice inference path for Stage 5.
- The upstream repo is not treated as a required side checkout for operators.
- This repo only vendors the minimal inference subset required by the current dubbing pipeline, not the full OmniVoice training/eval stack.

Maintenance note:
- When updating this subset, preserve upstream license headers in copied files.
- Record the new upstream commit here.
