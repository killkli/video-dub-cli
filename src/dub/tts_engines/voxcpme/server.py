from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import gradio as gr
from funasr import AutoModel

import voxcpm

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class VoxCPMServer:
    def __init__(self, model_id: str = "openbmb/VoxCPM2") -> None:
        self.device = "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES") else "mps"
        self.asr_model: Optional[AutoModel] = AutoModel(
            model="iic/SenseVoiceSmall",
            disable_update=True,
            log_level="ERROR",
            device="cuda:0" if self.device == "cuda" else "mps",
        )
        self.vox_model: Optional[voxcpm.VoxCPM] = None
        self.model_id = model_id

    def get_model(self) -> voxcpm.VoxCPM:
        if self.vox_model is None:
            logger.info("Loading VoxCPM model: %s", self.model_id)
            self.vox_model = voxcpm.VoxCPM.from_pretrained(self.model_id, optimize=True)
        return self.vox_model

    def generate(
        self,
        text: str,
        control_instruction: str,
        ref_wav,
        use_prompt_text: bool,
        prompt_text_value: str,
        cfg_value: float,
        do_normalize: bool,
        denoise: bool,
        dit_steps: int,
    ):
        audio_path = None
        if isinstance(ref_wav, dict):
            audio_path = ref_wav.get("path")
        elif isinstance(ref_wav, str):
            audio_path = ref_wav
        final_text = f"({control_instruction}){text}" if control_instruction else text
        prompt_text = prompt_text_value if use_prompt_text else None
        model = self.get_model()
        wav = model.generate(
            text=final_text,
            prompt_wav_path=audio_path,
            prompt_text=prompt_text,
            cfg_value=cfg_value,
            inference_timesteps=dit_steps,
            normalize=do_normalize,
            denoise=denoise,
        )
        import tempfile
        import soundfile as sf
        tmpdir = Path(tempfile.mkdtemp(prefix="voxcpm-server-"))
        out = tmpdir / "voxcpm_server_output.wav"
        sf.write(out, wav, 24000)
        return str(out)


def build_app(server: VoxCPMServer) -> gr.Blocks:
    with gr.Blocks() as app:
        text = gr.Textbox(label="Target Text")
        control = gr.Textbox(label="Control Instruction", value="")
        ref_wav = gr.Audio(type="filepath", label="Reference Audio")
        use_prompt_text = gr.Checkbox(label="Use Prompt Text", value=False)
        prompt_text = gr.Textbox(label="Prompt Text", value="")
        cfg_value = gr.Slider(minimum=1.0, maximum=3.0, value=2.0, step=0.1, label="CFG")
        do_normalize = gr.Checkbox(label="Normalize", value=True)
        denoise = gr.Checkbox(label="Denoise", value=True)
        dit_steps = gr.Slider(minimum=1, maximum=50, value=10, step=1, label="Steps")
        out = gr.Audio(label="Generated Audio")
        run_btn = gr.Button("Generate", variant="primary")
        run_btn.click(
            fn=server.generate,
            inputs=[text, control, ref_wav, use_prompt_text, prompt_text, cfg_value, do_normalize, denoise, dit_steps],
            outputs=[out],
            api_name="generate",
        )
    return app


def run_server(model_id: str = "openbmb/VoxCPM2", port: int = 8808) -> None:
    server = VoxCPMServer(model_id=model_id)
    app = build_app(server)
    app.queue(max_size=10, default_concurrency_limit=1).launch(
        server_name="0.0.0.0",
        server_port=port,
        show_error=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default="openbmb/VoxCPM2")
    parser.add_argument("--port", type=int, default=8808)
    args = parser.parse_args()
    run_server(model_id=args.model_id, port=args.port)


if __name__ == "__main__":
    main()
