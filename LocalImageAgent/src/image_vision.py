"""
Image vision helpers — generate analysis-quality thumbnails and encode as base64.
Target: 800px longest side, JPEG quality 85. Produces ~60-120 KB per image,
sharp enough for scene/color/composition analysis by a vision model.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger("local-image-agent")

# Longest side target for vision thumbnails
VISION_SIZE = 800
VISION_QUALITY = 85


def image_to_base64(path: Path, size: int = VISION_SIZE, quality: int = VISION_QUALITY) -> dict:
    """
    Open any supported image, resize to vision-safe dimensions, encode as base64 JPEG.
    Returns dict with base64 data, mime type, original and thumb dimensions, and encoded size.
    """
    with Image.open(path) as img:
        orig_w, orig_h = img.size
        orig_mode = img.mode

        # Convert to RGB (handles RGBA, palette, CMYK, etc.)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # Resize: scale down if larger than target, never upscale
        if max(orig_w, orig_h) > size:
            img.thumbnail((size, size), Image.LANCZOS)

        thumb_w, thumb_h = img.size

        # Encode to JPEG in memory
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        encoded_bytes = buf.getvalue()

    b64 = base64.b64encode(encoded_bytes).decode("ascii")
    encoded_kb = round(len(encoded_bytes) / 1024, 1)

    logger.debug(
        "vision encode: %s  %dx%d -> %dx%d  %.1f KB",
        path.name, orig_w, orig_h, thumb_w, thumb_h, encoded_kb
    )

    return {
        "path":            str(path),
        "name":            path.name,
        "original_size":   f"{orig_w}x{orig_h}",
        "original_mode":   orig_mode,
        "thumb_size":      f"{thumb_w}x{thumb_h}",
        "encoded_kb":      encoded_kb,
        "mime_type":       "image/jpeg",
        "base64":          b64,
    }
