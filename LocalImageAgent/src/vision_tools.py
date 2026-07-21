"""MCP tool definitions — Image vision (read images for ChatGPT vision analysis)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from config import SUPPORTED_INPUT_FORMATS
from image_vision import image_to_base64
from log_setup import timed_operation
import validation as val

logger = logging.getLogger("local-image-agent")


# ---------------------------------------------------------------------------
# read_image_for_vision  — single image
# ---------------------------------------------------------------------------

class ReadImageForVisionInput(BaseModel):
    path:    str = Field(..., description="Absolute path to the image file.")
    size:    int = Field(800, ge=128, le=2048,
                         description="Longest side in pixels for the vision thumbnail. Default 800.")
    quality: int = Field(85,  ge=40,  le=95,
                         description="JPEG quality for encoding (40-95). Default 85.")


def read_image_for_vision(params: ReadImageForVisionInput) -> dict[str, Any]:
    """
    Read an image file and return it as a base64-encoded JPEG thumbnail sized for vision analysis.
    The returned base64 field can be passed directly to a vision model.
    Default 800px / quality 85 produces ~60-120 KB — sharp enough for scene, color,
    composition, and object recognition without burning context.
    """
    p = Path(params.path)
    if not p.exists():
        raise val.ValidationError(f"Image not found: {params.path}")
    if not p.is_file():
        raise val.ValidationError(f"Not a file: {params.path}")
    ext = p.suffix.lstrip(".").lower()
    if ext not in SUPPORTED_INPUT_FORMATS:
        raise val.ValidationError(
            f"Unsupported image format '.{ext}'. Supported: {sorted(SUPPORTED_INPUT_FORMATS)}"
        )
    with timed_operation(f"read_image_for_vision {p.name}"):
        return image_to_base64(p, size=params.size, quality=params.quality)


# ---------------------------------------------------------------------------
# read_folder_for_vision  — batch, returns list of encoded images
# ---------------------------------------------------------------------------

class ReadFolderForVisionInput(BaseModel):
    folder:               str   = Field(..., description="Absolute path to folder containing images.")
    recursive:            bool  = Field(False, description="Include subfolders.")
    size:                 int   = Field(800,  ge=128, le=2048,
                                        description="Longest side in pixels. Default 800.")
    quality:              int   = Field(85,   ge=40,  le=95,
                                        description="JPEG encoding quality. Default 85.")
    max_images:           int   = Field(30,   ge=1,   le=100,
                                        description="Maximum images to encode in one call. Default 30.")
    modified_within_hours: float | None = Field(None, gt=0,
                                        description="Only include images modified within the last N hours. "
                                                    "e.g. 24 = last 24 hours. None = no filter.")
    sort_by:              str   = Field("newest",
                                        description="Sort order before applying max_images cap. "
                                                    "newest (default) | oldest | name")


def read_folder_for_vision(params: ReadFolderForVisionInput) -> dict[str, Any]:
    """
    Read images in a folder and return each as a base64 JPEG thumbnail for vision analysis.
    Sorted newest-first by default. Capped at max_images BEFORE encoding — never overloads device.
    Use modified_within_hours to focus on recent files (e.g. 24 = last 24 hours).
    Use for: renaming by content, finding images by scene/object, picking best angle/quality.
    """
    import time as _time

    folder = Path(params.folder)
    if not folder.exists():
        raise val.ValidationError(f"Folder not found: {params.folder}")
    if not folder.is_dir():
        raise val.ValidationError(f"Not a directory: {params.folder}")

    pattern = "**/*" if params.recursive else "*"
    cutoff = (_time.time() - params.modified_within_hours * 3600) \
             if params.modified_within_hours else None

    # Gather candidates with mtime
    candidates: list[tuple[float, Path]] = []
    for p in folder.glob(pattern):
        if not p.is_file():
            continue
        if p.suffix.lstrip(".").lower() not in SUPPORTED_INPUT_FORMATS:
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if cutoff and mtime < cutoff:
            continue
        candidates.append((mtime, p))

    total_available = len(candidates)

    # Sort BEFORE capping
    sort_by = params.sort_by.lower()
    if sort_by == "oldest":
        candidates.sort(key=lambda x: x[0])
    elif sort_by == "name":
        candidates.sort(key=lambda x: x[1].name.lower())
    else:  # newest (default)
        candidates.sort(key=lambda x: x[0], reverse=True)

    # Cap here — this is what prevents device overload
    candidates = candidates[: params.max_images]

    images: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    with timed_operation(
        f"read_folder_for_vision {folder.name} "
        f"({len(candidates)}/{total_available} images, sort={sort_by})"
    ):
        for _, p in candidates:
            try:
                data = image_to_base64(p, size=params.size, quality=params.quality)
                images.append(data)
            except Exception as exc:
                logger.warning("vision encode failed for %s: %s", p.name, exc)
                errors.append({"file": str(p), "error": str(exc)})

    total_kb = round(sum(img["encoded_kb"] for img in images), 1)

    return {
        "folder":                 str(folder),
        "total_available":        total_available,
        "returned":               len(images),
        "sort_by":                sort_by,
        "modified_within_hours":  params.modified_within_hours,
        "total_encoded_kb":       total_kb,
        "errors":                 errors,
        "images":                 images,
    }
