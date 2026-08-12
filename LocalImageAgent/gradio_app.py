"""
AI Image Processing Studio â€” clean dark UI, RTX 5070 backend.
"""
import sys, os, types
from pathlib import Path

# Always run from our own directory so Gradio can write .gradio/certificate.pem
os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent / "src"))

# torchvision shim
def _patch():
    try:
        import torchvision.transforms.functional_tensor
    except ModuleNotFoundError:
        import torchvision.transforms.functional as F
        import types as t
        shim = t.ModuleType("torchvision.transforms.functional_tensor")
        for n in dir(F): setattr(shim, n, getattr(F, n))
        sys.modules["torchvision.transforms.functional_tensor"] = shim
_patch()

import gradio as gr
import tempfile
from ai_process import ai_denoise, ai_upscale, ai_process_pipeline, COMMUNITY_MODELS

OUTPUT_DIR = Path(__file__).parent / "gradio_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

MODEL_CHOICES = [cfg["label"] for cfg in COMMUNITY_MODELS.values()]
MODEL_KEY_MAP  = {cfg["label"]: key for key, cfg in COMMUNITY_MODELS.items()}

DARK_CSS = """
/* â”€â”€ Reset & base â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
body, .gradio-container {
    background: #0f0f0f !important;
    color: #e8e8e8 !important;
    font-family: 'Inter', 'Segoe UI', sans-serif !important;
}
/* â”€â”€ Header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
#header {
    padding: 28px 0 10px 0;
    text-align: center;
    border-bottom: 1px solid #222;
    margin-bottom: 24px;
}
#header h1 {
    font-size: 22px;
    font-weight: 600;
    letter-spacing: 0.04em;
    color: #fff;
    margin: 0 0 4px 0;
}
#header p {
    font-size: 12px;
    color: #555;
    margin: 0;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
/* â”€â”€ Panels â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.panel {
    background: #161616;
    border: 1px solid #252525;
    border-radius: 10px;
    padding: 20px;
}
/* â”€â”€ Labels â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
label span, .block label span {
    font-size: 11px !important;
    font-weight: 500 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: #666 !important;
}
/* â”€â”€ Inputs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
input, select, textarea, .gr-input {
    background: #1e1e1e !important;
    border: 1px solid #2e2e2e !important;
    color: #e8e8e8 !important;
    border-radius: 6px !important;
}
/* â”€â”€ Radio / Checkboxes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.gr-radio label, .gr-checkbox label {
    color: #ccc !important;
    font-size: 13px !important;
}
/* â”€â”€ Dropdown â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.gr-dropdown {
    background: #1e1e1e !important;
    border-color: #2e2e2e !important;
}
/* â”€â”€ Upload zone â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.upload-container, [data-testid="image"] {
    background: #141414 !important;
    border: 2px dashed #2a2a2a !important;
    border-radius: 10px !important;
}
/* â”€â”€ Process button â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
#run-btn {
    background: linear-gradient(135deg, #7c3aed, #4f46e5) !important;
    border: none !important;
    color: #fff !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em !important;
    border-radius: 8px !important;
    height: 48px !important;
    cursor: pointer !important;
    transition: opacity 0.15s !important;
}
#run-btn:hover { opacity: 0.88 !important; }
/* â”€â”€ Info box â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
#info-box textarea {
    background: #0d0d0d !important;
    border-color: #1e1e1e !important;
    font-family: 'JetBrains Mono', 'Consolas', monospace !important;
    font-size: 12px !important;
    color: #7dd3a8 !important;
}
/* â”€â”€ Tabs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.tab-nav button {
    background: transparent !important;
    border-bottom: 2px solid transparent !important;
    color: #555 !important;
    font-size: 12px !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
}
.tab-nav button.selected {
    border-bottom-color: #7c3aed !important;
    color: #e8e8e8 !important;
}
/* â”€â”€ Divider â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.divider { border: none; border-top: 1px solid #1e1e1e; margin: 16px 0; }
/* â”€â”€ Footer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
footer { display: none !important; }
.svelte-1ipelgc { display: none !important; }
"""


def process(input_path, mode, denoise_strength, model_label, output_scale):
    if not input_path:
        return None, "⚠ No image uploaded."

    src = Path(input_path)
    model_key = MODEL_KEY_MAP.get(model_label, "4x-UltraSharp")
    dst = OUTPUT_DIR / f"{src.stem}_{model_key}_x{output_scale}{src.suffix}"

    try:
        if mode == "Denoise only":
            r = ai_denoise(src, dst, strength=denoise_strength)
            info = f"✓ DENOISE COMPLETE\n  Method : {r['method']}\n  Strength: {denoise_strength}\n  Output : {Path(r['output_file']).name}"

        elif mode == "Upscale only":
            r = ai_upscale(src, dst, scale=output_scale, model=model_key)
            info = (f"✓ UPSCALE COMPLETE\n  Model  : {model_key}\n  Device : {r['device']}\n"
                    f"  Input  : {r['input_resolution']}\n  Output : {r['output_resolution']}")

        else:
            r = ai_process_pipeline(src, dst,
                denoise_strength=denoise_strength,
                upscale=output_scale,
                model=model_key)
            u = r["upscale"]
            info = (f"✓ PIPELINE COMPLETE\n  Denoise: {r['denoise']['method']} ({denoise_strength})\n"
                    f"  Upscale: {model_key}  ×{output_scale}  [{u['device']}]\n"
                    f"  Input  : {u['input_resolution']}\n  Output : {u['output_resolution']}")

        return str(dst), info

    except Exception as e:
        return None, f"✗ ERROR\n  {e}"


with gr.Blocks(title="AI Image Studio") as demo:

    gr.HTML("""
    <div id="header">
        <h1>◆ AI IMAGE STUDIO</h1>
        <p>Intel OIDN Denoiser &nbsp;·&nbsp; ESRGAN Upscaler &nbsp;·&nbsp; RTX 5070</p>
    </div>
    """)

    with gr.Row(equal_height=False):

        # — — Left panel: controls â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        with gr.Column(scale=1, elem_classes="panel"):
            input_img = gr.Image(
                label="INPUT IMAGE",
                type="filepath",
                height=280,
            )

            gr.HTML("<hr class='divider'>")

            mode = gr.Radio(
                ["Denoise + Upscale", "Denoise only", "Upscale only"],
                value="Denoise + Upscale",
                label="PIPELINE MODE",
            )

            gr.HTML("<hr class='divider'>")

            denoise_strength = gr.Radio(
                ["low", "medium", "high"],
                value="medium",
                label="DENOISE STRENGTH",
            )

            model_label = gr.Dropdown(
                choices=MODEL_CHOICES,
                value=MODEL_CHOICES[0],
                label="UPSCALE MODEL",
            )

            output_scale = gr.Radio(
                [2, 4],
                value=4,
                label="OUTPUT SCALE",
            )

            gr.HTML("<hr class='divider'>")

            run_btn = gr.Button("PROCESS  →", elem_id="run-btn", variant="primary")

        # — — Right panel: output â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        with gr.Column(scale=1, elem_classes="panel"):
            output_img  = gr.Image(
                label="OUTPUT PREVIEW",
                height=280,
                interactive=False,
            )
            output_file = gr.File(label="DOWNLOAD RESULT")
            info_box    = gr.Textbox(
                label="PROCESSING LOG",
                lines=7,
                interactive=False,
                elem_id="info-box",
            )

    # Wire up
    def _process_and_show(img, mode, den, mdl, scl):
        f, info = process(img, mode, den, mdl, scl)
        return f, f, info  # file, preview, log

    run_btn.click(
        fn=_process_and_show,
        inputs=[input_img, mode, denoise_strength, model_label, output_scale],
        outputs=[output_file, output_img, info_box],
        queue=False,
    )


if __name__ == "__main__":
    import torch
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    print(f"AI Image Studio  |  {gpu}  |  models: {len(COMMUNITY_MODELS)}")
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=True,
        show_error=True,
        allowed_paths=[str(OUTPUT_DIR)],
        css=DARK_CSS,
    )

