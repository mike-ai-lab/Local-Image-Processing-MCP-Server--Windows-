"""
Image generation vision helpers — optimize images for ChatGPT to see + use as generation reference.
Target: WebP 400-500 KB, preserving sufficient detail for image-to-image generation prompts.
"""

from __future__ import annotations

import base64
import logging
import tempfile
from pathlib import Path

from PIL import Image
from imagemagick import run_magick, ImageMagickError

logger = logging.getLogger("local-image-agent")


def optimize_for_gen_vision(
    input_path: Path,
    target_kb: int = 450,
    max_dimension: int = 1920,
) -> dict:
    """
    Optimize an image for both vision analysis AND image generation reference:
    1. Resize to max_dimension longest side (preserves detail vs small thumbnails)
    2. Convert to WebP targeting ~target_kb file size using binary search on quality
    3. Encode to base64
    
    Returns dict with base64 WebP data, dimensions, file size, quality used.
    This is larger and higher-quality than vision-only thumbnails (800px JPEG).
    """
    with Image.open(input_path) as img:
        orig_w, orig_h = img.size
        orig_mode = img.mode
        
        # Determine target size
        if max(orig_w, orig_h) > max_dimension:
            ratio = max_dimension / max(orig_w, orig_h)
            new_w = int(orig_w * ratio)
            new_h = int(orig_h * ratio)
        else:
            new_w, new_h = orig_w, orig_h
    
    # Use ImageMagick for WebP conversion with quality binary search
    tmp_webp = Path(tempfile.gettempdir()) / f"mcp_gen_vision_{input_path.stem}.webp"
    
    # Binary search for quality that hits target_kb
    lo, hi = 30, 95
    final_quality = 85
    final_size_kb = 0
    
    for _ in range(10):  # max 10 iterations
        mid = (lo + hi) // 2
        try:
            run_magick([
                str(input_path),
                "-resize", f"{new_w}x{new_h}",
                "-quality", str(mid),
                str(tmp_webp)
            ])
            
            size_kb = tmp_webp.stat().st_size / 1024
            
            if abs(size_kb - target_kb) < target_kb * 0.1:  # within 10%
                final_quality = mid
                final_size_kb = size_kb
                break
            
            if size_kb > target_kb:
                hi = mid - 1
            else:
                lo = mid + 1
            
            final_quality = mid
            final_size_kb = size_kb
            
        except ImageMagickError as e:
            logger.warning("WebP conversion failed at quality %d: %s", mid, e)
            # If it fails, try one more time at quality 85
            run_magick([
                str(input_path),
                "-resize", f"{new_w}x{new_h}",
                "-quality", "85",
                str(tmp_webp)
            ])
            final_quality = 85
            final_size_kb = tmp_webp.stat().st_size / 1024
            break
    
    # Read and encode
    webp_bytes = tmp_webp.read_bytes()
    b64 = base64.b64encode(webp_bytes).decode("ascii")
    
    # Get actual dimensions from the WebP
    with Image.open(tmp_webp) as webp_img:
        final_w, final_h = webp_img.size
    
    # Clean up temp
    try:
        tmp_webp.unlink()
    except OSError:
        pass
    
    logger.info(
        "gen_vision optimize: %s  %dx%d -> %dx%d WebP  %.1f KB (Q%d)",
        input_path.name, orig_w, orig_h, final_w, final_h, final_size_kb, final_quality
    )
    
    return {
        "path":            str(input_path),
        "name":            input_path.name,
        "original_size":   f"{orig_w}x{orig_h}",
        "original_mode":   orig_mode,
        "optimized_size":  f"{final_w}x{final_h}",
        "encoded_kb":      round(final_size_kb, 1),
        "quality":         final_quality,
        "mime_type":       "image/webp",
        "base64":          b64,
    }
