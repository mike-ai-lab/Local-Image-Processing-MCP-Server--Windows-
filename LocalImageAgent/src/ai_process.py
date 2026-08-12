"""
AI image processing — Intel OIDN denoiser + ESRGAN upscaler (community models).
"""
from __future__ import annotations
import logging, os, sys, types, urllib.request
from pathlib import Path

logger = logging.getLogger("local-image-agent")

CACHE = Path(os.environ.get("USERPROFILE", "C:/Users/PC")) / ".cache" / "realesrgan"
CACHE.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# torchvision shim
# ---------------------------------------------------------------------------
def _patch_torchvision():
    try:
        import torchvision.transforms.functional_tensor
    except ModuleNotFoundError:
        import torchvision.transforms.functional as _F
        shim = types.ModuleType("torchvision.transforms.functional_tensor")
        for n in dir(_F): setattr(shim, n, getattr(_F, n))
        sys.modules["torchvision.transforms.functional_tensor"] = shim
_patch_torchvision()

# ---------------------------------------------------------------------------
# Community model registry
# ---------------------------------------------------------------------------
COMMUNITY_MODELS = {
    "4x-UltraSharp": {
        "file": "4x-UltraSharp.pth",
        "scale": 4,
        "arch": dict(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4),
        "label": "4x-UltraSharp — photorealistic, sharp textures (best for JPEG renders)",
    },
    "4x-UltraSharpV2": {
        "file": "4x-UltraSharpV2.pth",
        "scale": 4,
        "arch": dict(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4),
        "label": "4x-UltraSharpV2 — improved detail & texture over V1",
    },
    "4x-Remacri": {
        "file": "4x-Remacri.pth",
        "scale": 4,
        "arch": dict(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4),
        "label": "4x-Remacri — natural realism, no over-sharpening (best for interior/exterior viz)",
    },
    "4x-NMKD-Siax": {
        "file": "4x-NMKD-Siax.pth",
        "scale": 4,
        "arch": dict(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4),
        "label": "4x-NMKD-Siax — universal clean image, sharp edges & depth",
    },
    "RealESRGAN_x4plus": {
        "file": "RealESRGAN_x4plus.pth",
        "scale": 4,
        "arch": dict(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4),
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
        "label": "RealESRGAN x4plus — general purpose baseline",
    },
    "RealESRGAN_x2plus": {
        "file": "RealESRGAN_x2plus.pth",
        "scale": 2,
        "arch": dict(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2),
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
        "label": "RealESRGAN x2plus — 2x baseline",
    },
}

def _ensure_weight(model_key: str) -> Path:
    cfg = COMMUNITY_MODELS[model_key]
    dst = CACHE / cfg["file"]
    if not dst.exists():
        url = cfg.get("url")
        if not url:
            raise FileNotFoundError(f"Model weights not found: {dst}. Download manually.")
        logger.info("Downloading %s...", cfg["file"])
        urllib.request.urlretrieve(url, str(dst))
    return dst


# ---------------------------------------------------------------------------
# Denoiser — Intel OIDN (render-quality, same as Blender/V-Ray/Arnold)
# ---------------------------------------------------------------------------
def oidn_denoise(src: Path, dst: Path, strength: str = "medium") -> dict:
    """
    Denoise using Intel Open Image Denoise — the same denoiser inside
    Blender, V-Ray, Redshift, and Arnold. Trained on ray-traced renders.
    strength: low | medium | high  (controls blend with original)
    """
    import numpy as np
    import cv2
    try:
        import pyoidn
        HAS_OIDN = True
    except ImportError:
        HAS_OIDN = False

    img_bgr = cv2.imread(str(src))
    if img_bgr is None:
        raise ValueError(f"Cannot read: {src}")

    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

    if HAS_OIDN:
        device = pyoidn.Device()
        # pyoidn 2.x exposes Filter directly; Device has no RayTracing() method.
        # Use the installed wrapper API and explicitly provide the pixel format.
        from pyoidn import Filter, OIDN_FORMAT_FLOAT3, OIDN_IMAGE_COLOR, OIDN_IMAGE_OUTPUT
        device.commit()
        flt = Filter(device, "RT")
        flt.set_image(OIDN_IMAGE_COLOR, img_rgb, OIDN_FORMAT_FLOAT3)
        out = np.zeros_like(img_rgb)
        flt.set_image(OIDN_IMAGE_OUTPUT, out, OIDN_FORMAT_FLOAT3)
        flt.commit()
        flt.execute()
        device.wait()
        err = device.get_error()
        if err:
            raise RuntimeError(f"OIDN: {err}")
        denoised_rgb = np.clip(out, 0, 1)
    else:
        # Fallback to NLM if OIDN unavailable
        logger.warning("pyoidn unavailable, falling back to NLM")
        p = {"low": 5, "medium": 10, "high": 15}[strength]
        bgr_u8 = img_bgr
        denoised_bgr = cv2.fastNlMeansDenoisingColored(bgr_u8, None, p, p, 7, 21)
        denoised_rgb = cv2.cvtColor(denoised_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

    # Blend with original based on strength
    blend = {"low": 0.3, "medium": 0.6, "high": 0.9}[strength]
    result_rgb = img_rgb * (1 - blend) + denoised_rgb * blend
    result_bgr = cv2.cvtColor((result_rgb * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)

    dst.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dst), result_bgr, [cv2.IMWRITE_JPEG_QUALITY, 97])

    return {
        "output_file": str(dst),
        "method": "Intel OIDN" if HAS_OIDN else "OpenCV NLM (fallback)",
        "strength": strength, "blend": blend, "status": "ok",
    }


# Backward compat alias used by MCP tools
def ai_denoise(src: Path, dst: Path, strength: str = "medium") -> dict:
    return oidn_denoise(src, dst, strength)


# ---------------------------------------------------------------------------
# Upscaler — ESRGAN with community model support
# ---------------------------------------------------------------------------
def ai_upscale(src: Path, dst: Path, scale: int = 4, model: str = "4x-UltraSharp") -> dict:
    import torch, cv2
    from basicsr.archs.rrdbnet_arch import RRDBNet
    from realesrgan import RealESRGANer

    cfg = COMMUNITY_MODELS.get(model) or COMMUNITY_MODELS["4x-UltraSharp"]
    weight = _ensure_weight(model)
    net = RRDBNet(**cfg["arch"])

    device = "cuda" if torch.cuda.is_available() else "cpu"
    upsampler = RealESRGANer(
        scale=cfg["arch"]["scale"],
        model_path=str(weight),
        model=net,
        tile=512, tile_pad=10, pre_pad=0,
        half=(device == "cuda"),
        device=device,
    )

    img = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Cannot read: {src}")

    output, _ = upsampler.enhance(img, outscale=scale)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dst), output, [cv2.IMWRITE_JPEG_QUALITY, 97])

    oh, ow = img.shape[:2]
    rh, rw = output.shape[:2]
    return {
        "output_file": str(dst), "model": model, "device": device,
        "input_resolution": f"{ow}x{oh}", "output_resolution": f"{rw}x{rh}",
        "status": "ok",
    }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def ai_process_pipeline(src, dst, denoise_strength="medium", upscale=4, model="4x-UltraSharp"):
    import tempfile
    tmp = Path(tempfile.mktemp(suffix=".jpg"))
    try:
        d = oidn_denoise(src, tmp, strength=denoise_strength)
        u = ai_upscale(tmp, dst, scale=upscale, model=model)
    finally:
        if tmp.exists(): tmp.unlink()
    return {"output_file": str(dst), "denoise": d, "upscale": u, "status": "ok"}
