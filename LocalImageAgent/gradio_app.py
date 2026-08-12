"""
AI Image Processing Studio — RTX 5070
Tab 1: Denoise + Upscale (ESRGAN)
Tab 2: Remove / Generative Fill (LaMa + SD Inpaint)
"""
import sys, os, types
from pathlib import Path

os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent / "src"))

def _patch():
    try:
        import torchvision.transforms.functional_tensor
    except ModuleNotFoundError:
        import torchvision.transforms.functional as F, types as t
        shim = t.ModuleType("torchvision.transforms.functional_tensor")
        for n in dir(F): setattr(shim, n, getattr(F, n))
        sys.modules["torchvision.transforms.functional_tensor"] = shim
_patch()

import gradio as gr
from ai_process import ai_denoise, ai_upscale, ai_process_pipeline, COMMUNITY_MODELS

OUTPUT_DIR = Path(__file__).parent / "gradio_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

MODEL_CHOICES = [cfg["label"] for cfg in COMMUNITY_MODELS.values()]
MODEL_KEY_MAP  = {cfg["label"]: key for key, cfg in COMMUNITY_MODELS.items()}

# ---------------------------------------------------------------------------
# CSS — Gradio 6 compatible selectors
# ---------------------------------------------------------------------------
CSS = """
/* Base */
body, .gradio-container, .main, .wrap {
    background: #0f0f0f !important;
    color: #e0e0e0 !important;
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif !important;
}

/* Header */
#app-header {
    text-align: center;
    padding: 24px 0 16px;
    border-bottom: 1px solid #222;
    margin-bottom: 20px;
}
#app-header h1 { font-size: 20px; font-weight: 700; color: #fff; margin: 0 0 4px; letter-spacing: 0.06em; }
#app-header p  { font-size: 11px; color: #444; letter-spacing: 0.1em; text-transform: uppercase; margin: 0; }

/* Tabs */
.tab-nav { border-bottom: 1px solid #222 !important; }
.tab-nav button {
    background: transparent !important;
    color: #555 !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    padding: 10px 20px !important;
    transition: color 0.15s, border-color 0.15s !important;
}
.tab-nav button:hover { color: #aaa !important; }
.tab-nav button.selected {
    color: #a78bfa !important;
    border-bottom-color: #7c3aed !important;
}

/* Panels */
.block { background: #161616 !important; border: 1px solid #222 !important; border-radius: 10px !important; }

/* Labels */
label > span:first-child, .block > label > span {
    font-size: 10px !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: #555 !important;
}

/* Inputs / textareas */
input[type=text], textarea, .wrap input {
    background: #1a1a1a !important;
    border: 1px solid #2a2a2a !important;
    color: #e0e0e0 !important;
    border-radius: 6px !important;
}
input[type=text]:focus, textarea:focus {
    border-color: #7c3aed !important;
    outline: none !important;
}

/* Dropdown */
.dropdown, select {
    background: #1a1a1a !important;
    border: 1px solid #2a2a2a !important;
    color: #e0e0e0 !important;
    border-radius: 6px !important;
}

/* Radio buttons */
input[type=radio] { accent-color: #7c3aed !important; }
.radio-group label, fieldset label {
    color: #ccc !important;
    font-size: 13px !important;
}

/* Upload zone */
.upload-container {
    background: #111 !important;
    border: 2px dashed #2a2a2a !important;
    border-radius: 10px !important;
}

/* ALL buttons base */
button {
    cursor: pointer !important;
    transition: all 0.15s ease !important;
}

/* Primary action button */
button.primary, button[variant="primary"], #process-btn, #inpaint-btn {
    background: linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%) !important;
    border: none !important;
    color: #ffffff !important;
    font-size: 14px !important;
    font-weight: 700 !important;
    letter-spacing: 0.06em !important;
    border-radius: 8px !important;
    padding: 12px 24px !important;
    min-height: 48px !important;
    box-shadow: 0 4px 15px rgba(124, 58, 237, 0.3) !important;
}
button.primary:hover, button[variant="primary"]:hover, #process-btn:hover, #inpaint-btn:hover {
    background: linear-gradient(135deg, #6d28d9 0%, #4338ca 100%) !important;
    box-shadow: 0 6px 20px rgba(124, 58, 237, 0.5) !important;
    transform: translateY(-1px) !important;
}
button.primary:active, button[variant="primary"]:active, #process-btn:active, #inpaint-btn:active {
    transform: translateY(0px) !important;
    box-shadow: 0 2px 8px rgba(124, 58, 237, 0.3) !important;
}

/* Secondary buttons */
button.secondary {
    background: #1e1e1e !important;
    border: 1px solid #333 !important;
    color: #ccc !important;
    border-radius: 6px !important;
}
button.secondary:hover {
    background: #252525 !important;
    border-color: #555 !important;
    color: #fff !important;
}

/* File download button */
.file-preview { background: #1a1a1a !important; border-color: #2a2a2a !important; border-radius: 8px !important; }

/* Log / info box */
#log-box textarea {
    background: #0a0a0a !important;
    border-color: #1a1a1a !important;
    color: #6ee7b7 !important;
    font-family: 'Consolas', 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
    line-height: 1.6 !important;
}

/* Image components */
.image-container { background: #111 !important; border-radius: 10px !important; }

/* Divider */
hr { border: none !important; border-top: 1px solid #1e1e1e !important; margin: 14px 0 !important; }

/* Hide gradio footer */
footer, .built-with { display: none !important; }
"""

# ---------------------------------------------------------------------------
# Tab 1 — Enhance (Denoise + Upscale)
# ---------------------------------------------------------------------------
def run_enhance(input_path, mode, denoise_strength, model_label, output_scale):
    if not input_path:
        return None, None, "⚠  Drop an image first."
    src = Path(input_path)
    model_key = MODEL_KEY_MAP.get(model_label, "4x-UltraSharp")
    dst = OUTPUT_DIR / f"{src.stem}_{model_key}_x{output_scale}{src.suffix}"
    try:
        if mode == "Denoise only":
            r = ai_denoise(src, dst, strength=denoise_strength)
            info = f"✓ DENOISE\n  Method  : {r['method']}\n  Strength: {denoise_strength}"
        elif mode == "Upscale only":
            r = ai_upscale(src, dst, scale=output_scale, model=model_key)
            info = f"✓ UPSCALE\n  Model : {model_key}\n  Device: {r['device']}\n  {r['input_resolution']} → {r['output_resolution']}"
        else:
            r = ai_process_pipeline(src, dst, denoise_strength=denoise_strength, upscale=output_scale, model=model_key)
            u = r["upscale"]
            info = f"✓ PIPELINE\n  Denoise : {r['denoise']['method']} ({denoise_strength})\n  Upscale : {model_key} ×{output_scale} [{u['device']}]\n  {u['input_resolution']} → {u['output_resolution']}"
        return str(dst), str(dst), info
    except Exception as e:
        return None, None, f"✗ ERROR\n  {e}"

# ---------------------------------------------------------------------------
# Tab 2 — Remove / Generative Fill
# ---------------------------------------------------------------------------
_lama = None
_sd_pipe = None

def _get_lama():
    global _lama
    if _lama is None:
        from simple_lama_inpainting import SimpleLama
        _lama = SimpleLama()
    return _lama

def _get_sd():
    global _sd_pipe
    if _sd_pipe is None:
        import torch
        from diffusers import StableDiffusionInpaintPipeline
        _sd_pipe = StableDiffusionInpaintPipeline.from_pretrained(
            "runwayml/stable-diffusion-inpainting",
            torch_dtype=torch.float16,
            safety_checker=None,
        ).to("cuda")
        _sd_pipe.enable_attention_slicing()
    return _sd_pipe

def run_inpaint(composite, inpaint_mode, prompt):
    """
    composite: dict with 'background' (PIL) and 'layers' (list of PIL masks)
    """
    if composite is None:
        return None, None, "⚠  Upload an image and draw a mask."
    try:
        from PIL import Image
        import numpy as np

        bg = composite.get("background")
        layers = composite.get("layers", [])

        if bg is None:
            return None, None, "⚠  No background image found."

        # Build mask from drawn layer
        if layers:
            mask_arr = np.array(layers[0].convert("L"))
            mask_arr = (mask_arr > 10).astype(np.uint8) * 255
            mask = Image.fromarray(mask_arr, "L")
        else:
            return None, None, "⚠  Draw a mask over the area to remove/fill."

        img = bg.convert("RGB")
        dst = OUTPUT_DIR / f"inpaint_result.png"

        if inpaint_mode == "Remove (LaMa)":
            lama = _get_lama()
            result = lama(img, mask)
            result.save(str(dst))
            info = "✓ REMOVE\n  Model: LaMa (Large Mask Inpainting)\n  Mode : Object removal / background fill"

        else:  # Generative Fill
            if not prompt or not prompt.strip():
                return None, None, "⚠  Enter a prompt for generative fill."
            pipe = _get_sd()
            w, h = img.size
            # SD inpaint needs 512x512 multiples
            rw = min(512, (w // 64) * 64)
            rh = min(512, (h // 64) * 64)
            img_r   = img.resize((rw, rh))
            mask_r  = mask.resize((rw, rh))
            out = pipe(prompt=prompt, image=img_r, mask_image=mask_r,
                      num_inference_steps=30, guidance_scale=7.5).images[0]
            # Paste result back at original size
            out_full = img.copy()
            out_full.paste(out.resize((w, h)), (0, 0))
            out_full.save(str(dst))
            info = f"✓ GENERATIVE FILL\n  Model : SD Inpainting\n  Prompt: {prompt[:60]}"

        return str(dst), str(dst), info

    except Exception as e:
        return None, None, f"✗ ERROR\n  {e}"

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
with gr.Blocks(title="AI Image Studio") as demo:

    gr.HTML("""
    <div id="app-header">
        <h1>◆ AI IMAGE STUDIO</h1>
        <p>ESRGAN Upscaler &nbsp;·&nbsp; OIDN Denoiser &nbsp;·&nbsp; LaMa Remove &nbsp;·&nbsp; SD Inpaint &nbsp;·&nbsp; RTX 5070</p>
    </div>
    """)

    with gr.Tabs():

        # ── Tab 1: Enhance ────────────────────────────────────────────────
        with gr.Tab("ENHANCE"):
            with gr.Row():
                with gr.Column(scale=1):
                    enh_input = gr.Image(label="INPUT IMAGE", type="filepath", height=300)
                    gr.HTML("<hr>")
                    enh_mode = gr.Radio(
                        ["Denoise + Upscale", "Denoise only", "Upscale only"],
                        value="Denoise + Upscale", label="MODE"
                    )
                    gr.HTML("<hr>")
                    enh_denoise = gr.Radio(["low", "medium", "high"], value="medium", label="DENOISE STRENGTH")
                    enh_model   = gr.Dropdown(choices=MODEL_CHOICES, value=MODEL_CHOICES[0], label="UPSCALE MODEL")
                    enh_scale   = gr.Radio([2, 4], value=4, label="OUTPUT SCALE")
                    gr.HTML("<hr>")
                    enh_btn = gr.Button("▶  PROCESS", variant="primary", elem_id="process-btn")

                with gr.Column(scale=1):
                    enh_preview = gr.Image(label="OUTPUT PREVIEW", height=300, interactive=False)
                    enh_file    = gr.File(label="DOWNLOAD")
                    enh_log     = gr.Textbox(label="LOG", lines=6, interactive=False, elem_id="log-box")

            enh_btn.click(
                fn=run_enhance,
                inputs=[enh_input, enh_mode, enh_denoise, enh_model, enh_scale],
                outputs=[enh_file, enh_preview, enh_log],
            )

        # ── Tab 2: Remove / Fill ──────────────────────────────────────────
        with gr.Tab("REMOVE / FILL"):
            with gr.Row():
                with gr.Column(scale=1):
                    inp_canvas = gr.ImageEditor(
                        label="PAINT MASK  (brush over area to remove/fill)",
                        type="pil",
                        height=380,
                        brush=gr.Brush(colors=["#ffffff"], color_mode="fixed", default_size=30),
                    )
                    gr.HTML("<hr>")
                    inp_mode = gr.Radio(
                        ["Remove (LaMa)", "Generative Fill (SD)"],
                        value="Remove (LaMa)", label="MODE"
                    )
                    inp_prompt = gr.Textbox(
                        label="FILL PROMPT  (for Generative Fill only)",
                        placeholder="e.g. marble floor, empty wall, grass...",
                        lines=2,
                    )
                    gr.HTML("<hr>")
                    inp_btn = gr.Button("▶  PROCESS", variant="primary", elem_id="inpaint-btn")

                with gr.Column(scale=1):
                    inp_preview = gr.Image(label="OUTPUT PREVIEW", height=380, interactive=False)
                    inp_file    = gr.File(label="DOWNLOAD")
                    inp_log     = gr.Textbox(label="LOG", lines=5, interactive=False, elem_id="log-box")

            inp_btn.click(
                fn=run_inpaint,
                inputs=[inp_canvas, inp_mode, inp_prompt],
                outputs=[inp_file, inp_preview, inp_log],
            )


if __name__ == "__main__":
    import torch
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    print(f"AI Image Studio  |  {gpu}  |  models: {len(COMMUNITY_MODELS)}")
    demo.launch(
        server_name="0.0.0.0",
        server_port=7861,
        share=False,
        show_error=True,
        allowed_paths=[str(OUTPUT_DIR)],
        css=CSS,
    )
