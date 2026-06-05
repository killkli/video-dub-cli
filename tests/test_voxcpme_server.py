from __future__ import annotations

from pathlib import Path
import importlib
import sys
import types


def _load_server_module(monkeypatch):
    fake_gradio = types.ModuleType("gradio")
    fake_torch = types.ModuleType("torch")
    class _Cuda:
        @staticmethod
        def is_available():
            return False
    fake_torch.cuda = _Cuda()
    class _Blocks:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def queue(self, *args, **kwargs):
            return self
        def launch(self, *args, **kwargs):
            return None
    fake_gradio.Blocks = _Blocks
    fake_gradio.Textbox = lambda *args, **kwargs: object()
    fake_gradio.Audio = lambda *args, **kwargs: object()
    fake_gradio.Checkbox = lambda *args, **kwargs: object()
    fake_gradio.Slider = lambda *args, **kwargs: object()
    class _Button:
        def click(self, *args, **kwargs):
            return None
    fake_gradio.Button = lambda *args, **kwargs: _Button()

    fake_funasr = types.ModuleType("funasr")
    fake_funasr.AutoModel = object

    fake_voxcpm = types.ModuleType("voxcpm")
    class _FakeVoxCPM:
        pass
    fake_voxcpm.VoxCPM = _FakeVoxCPM

    monkeypatch.setitem(sys.modules, "gradio", fake_gradio)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "funasr", fake_funasr)
    monkeypatch.setitem(sys.modules, "voxcpm", fake_voxcpm)
    sys.modules.pop("dub.tts_engines.voxcpme.server", None)
    return importlib.import_module("dub.tts_engines.voxcpme.server")


class _FakeModel:
    def __init__(self):
        self.kwargs = None
        self.tts_model = types.SimpleNamespace(sample_rate=24000)

    def generate(self, **kwargs):
        self.kwargs = kwargs
        return [0.0, 0.0, 0.0]


def test_server_generate_uses_reference_wav_when_prompt_text_disabled(tmp_path, monkeypatch):
    mod = _load_server_module(monkeypatch)
    VoxCPMServer = mod.VoxCPMServer
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"fake")

    fake_model = _FakeModel()
    server = VoxCPMServer.__new__(VoxCPMServer)
    server.vox_model = fake_model
    server.model_id = "fake"
    server.get_model = lambda: fake_model

    monkeypatch.setattr("soundfile.write", lambda *args, **kwargs: None)

    out = server.generate(
        text="你好",
        control_instruction="",
        ref_wav={"path": str(ref)},
        use_prompt_text=False,
        prompt_text_value="",
        cfg_value=2.0,
        do_normalize=True,
        denoise=True,
        dit_steps=10,
    )

    assert Path(out).name == "voxcpm_server_output.wav"
    assert fake_model.kwargs.get("prompt_wav_path") is None
    assert fake_model.kwargs.get("prompt_text") is None
    assert fake_model.kwargs["reference_wav_path"] == str(ref)


def test_server_generate_uses_prompt_pair_when_prompt_text_enabled(tmp_path, monkeypatch):
    mod = _load_server_module(monkeypatch)
    VoxCPMServer = mod.VoxCPMServer
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"fake")

    fake_model = _FakeModel()
    server = VoxCPMServer.__new__(VoxCPMServer)
    server.vox_model = fake_model
    server.model_id = "fake"
    server.get_model = lambda: fake_model

    monkeypatch.setattr("soundfile.write", lambda *args, **kwargs: None)

    server.generate(
        text="你好",
        control_instruction="",
        ref_wav={"path": str(ref)},
        use_prompt_text=True,
        prompt_text_value="こんにちは",
        cfg_value=2.0,
        do_normalize=True,
        denoise=True,
        dit_steps=10,
    )

    assert fake_model.kwargs["prompt_wav_path"] == str(ref)
    assert fake_model.kwargs["prompt_text"] == "こんにちは"
    assert fake_model.kwargs.get("reference_wav_path") == str(ref)
