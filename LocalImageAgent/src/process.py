"""Core image processing logic using ImageMagick."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import logging

from imagemagick import run_magick

logger = logging.getLogger("local-image-agent")

ResizeMode = Literal["fit", "fill", "exact"]


# ---------------------------------------------------------------------------
# Compression
# ---------------------------------------------------------------------------

def compress_image(
    input_path: Path,
    output_path: Path,
    quality: int = 85,
    max_size_bytes: int | None = None,
) -> Path:
    """Compress an image. If max_size_bytes is set, binary-search for quality."""
    if max_size_bytes is None:
        _run_compress(input_path, output_path, quality)
        return output_path

    # Binary search: find highest quality that fits within max_size_bytes
    lo, hi = 1, quality
    best_quality = lo

    # First check if the requested quality already fits
    _run_compress(input_path, output_path, quality)
    if output_path.stat().st_size <= max_size_bytes:
        return output_path

    while lo <= hi:
        mid = (lo + hi) // 2
        _run_compress(input_path, output_path, mid)
        size = output_path.stat().st_size
        if size <= max_size_bytes:
            best_quality = mid
            lo = mid + 1
        else:
            hi = mid - 1

    _run_compress(input_path, output_path, best_quality)
    final_size = output_path.stat().st_size
    if final_size > max_size_bytes:
        logger.warning(
            "Could not achieve target size %d bytes even at quality 1. Final size: %d bytes.",
            max_size_bytes,
            final_size,
        )
    return output_path


def _run_compress(src: Path, dst: Path, quality: int) -> None:
    run_magick([str(src), "-quality", str(quality), "-strip", str(dst)])


# ---------------------------------------------------------------------------
# Resize
# ---------------------------------------------------------------------------

def resize_image(
    input_path: Path,
    output_path: Path,
    width: int | None,
    height: int | None,
    mode: ResizeMode = "fit",
) -> Path:
    """Resize an image according to mode."""
    geometry = _build_geometry(width, height, mode)
    run_magick([str(input_path), "-resize", geometry, str(output_path)])
    return output_path


def _build_geometry(width: int | None, height: int | None, mode: ResizeMode) -> str:
    w = str(width) if width else ""
    h = str(height) if height else ""
    base = f"{w}x{h}"
    if mode == "fit":
        return base  # preserve aspect ratio, fit within box
    if mode == "fill":
        return base + "^"  # fill box, may crop
    return base + "!"  # exact, ignore aspect ratio


# ---------------------------------------------------------------------------
# Convert
# ---------------------------------------------------------------------------

def convert_image(input_path: Path, output_path: Path) -> Path:
    """Convert image to the format implied by output_path extension."""
    run_magick([str(input_path), str(output_path)])
    return output_path


# ---------------------------------------------------------------------------
# Strip metadata
# ---------------------------------------------------------------------------

def strip_metadata(input_path: Path, output_path: Path) -> Path:
    run_magick([str(input_path), "-strip", str(output_path)])
    return output_path


# ---------------------------------------------------------------------------
# Image info
# ---------------------------------------------------------------------------

def get_image_info(input_path: Path) -> dict:
    """Return image metadata via ImageMagick identify."""
    result = run_magick([
        "identify", "-verbose", str(input_path)
    ])
    raw = result.stdout

    # Parse key fields from verbose output
    def _extract(label: str) -> str:
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith(label.lower() + ":"):
                return stripped.split(":", 1)[1].strip()
        return ""

    file_size = os.path.getsize(input_path)
    return {
        "file": str(input_path),
        "file_size_bytes": file_size,
        "file_size_kb": round(file_size / 1024, 2),
        "format": _extract("Format"),
        "geometry": _extract("Geometry"),
        "colorspace": _extract("Colorspace"),
        "type": _extract("Type"),
        "depth": _extract("Depth"),
        "resolution": _extract("Resolution"),
        "print_size": _extract("Print size"),
        "properties": _parse_properties(raw),
    }


def _parse_properties(verbose: str) -> dict[str, str]:
    """Extract the Properties section from identify -verbose output."""
    props: dict[str, str] = {}
    in_props = False
    for line in verbose.splitlines():
        stripped = line.strip()
        if stripped.lower() == "properties:":
            in_props = True
            continue
        if in_props:
            if not line.startswith(" ") and not line.startswith("\t"):
                break  # left the Properties block
            if ":" in stripped:
                k, _, v = stripped.partition(":")
                props[k.strip()] = v.strip()
    return props


# ---------------------------------------------------------------------------
# Thumbnail
# ---------------------------------------------------------------------------

def create_thumbnail(
    input_path: Path,
    output_path: Path,
    width: int,
    height: int,
) -> Path:
    """Generate a thumbnail preserving aspect ratio."""
    geometry = f"{width}x{height}"
    run_magick([str(input_path), "-thumbnail", geometry, str(output_path)])
    return output_path
