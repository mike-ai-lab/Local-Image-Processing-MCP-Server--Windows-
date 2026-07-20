"""MCP tool definitions for LocalImageAgent."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from config import SUPPORTED_INPUT_FORMATS
import process as proc
import validation as val

logger = logging.getLogger("local-image-agent")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _image_files(folder: Path, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return [
        p for p in folder.glob(pattern)
        if p.is_file() and p.suffix.lstrip(".").lower() in SUPPORTED_INPUT_FORMATS
    ]


def _size_delta(before: int, after: int) -> dict[str, Any]:
    saved = before - after
    pct = round(saved / before * 100, 2) if before > 0 else 0.0
    return {
        "size_before_bytes": before,
        "size_after_bytes": after,
        "saved_bytes": saved,
        "reduction_pct": pct,
    }


# ---------------------------------------------------------------------------
# compress_image
# ---------------------------------------------------------------------------

class CompressImageInput(BaseModel):
    input_file: str = Field(..., description="Path to the source image file.")
    output_file: str = Field(..., description="Path to write the compressed image.")
    quality: int | None = Field(None, ge=1, le=100, description="Target JPEG/WebP quality (1-100). Default 85.")
    max_size_kb: int | None = Field(None, gt=0, description="Maximum output file size in KB.")


def compress_image(params: CompressImageInput) -> dict[str, Any]:
    src = val.validate_input_file(params.input_file)
    dst = val.validate_output_file(params.output_file)
    quality = val.validate_quality(params.quality) or 85
    max_bytes = val.validate_max_size_bytes(params.max_size_kb)

    before = src.stat().st_size
    proc.compress_image(src, dst, quality=quality, max_size_bytes=max_bytes)
    after = dst.stat().st_size

    result = {"output_file": str(dst), **_size_delta(before, after)}
    logger.info("compress_image: %s → %s (%.1f%% reduction)", src.name, dst.name, result["reduction_pct"])
    return result


# ---------------------------------------------------------------------------
# compress_folder
# ---------------------------------------------------------------------------

class CompressFolderInput(BaseModel):
    input_folder: str = Field(..., description="Folder containing images to compress.")
    output_folder: str | None = Field(None, description="Destination folder. Defaults to input_folder.")
    recursive: bool = Field(False, description="Process subfolders recursively.")
    overwrite: bool = Field(True, description="Overwrite existing files.")
    quality: int | None = Field(None, ge=1, le=100, description="Target quality (1-100). Default 85.")
    max_size_kb: int | None = Field(None, gt=0, description="Maximum output file size in KB.")


def compress_folder(params: CompressFolderInput) -> dict[str, Any]:
    src_folder = val.validate_input_folder(params.input_folder)
    out_folder = Path(params.output_folder) if params.output_folder else src_folder
    val.ensure_output_dir(out_folder)
    quality = val.validate_quality(params.quality) or 85
    max_bytes = val.validate_max_size_bytes(params.max_size_kb)

    files = _image_files(src_folder, params.recursive)
    results: list[dict] = []
    total_before = total_after = 0
    skipped = 0
    start = time.perf_counter()

    for f in files:
        rel = f.relative_to(src_folder)
        dst = out_folder / rel
        if not params.overwrite and dst.exists():
            skipped += 1
            continue
        val.ensure_output_dir(dst.parent)
        before = f.stat().st_size
        try:
            proc.compress_image(f, dst, quality=quality, max_size_bytes=max_bytes)
            after = dst.stat().st_size
            total_before += before
            total_after += after
            results.append({"file": str(rel), "status": "ok", **_size_delta(before, after)})
        except Exception as exc:
            results.append({"file": str(rel), "status": "error", "error": str(exc)})

    elapsed = time.perf_counter() - start
    failures = sum(1 for r in results if r["status"] == "error")
    return {
        "processed": len(results) - failures,
        "skipped": skipped,
        "failures": failures,
        "total_size_before_bytes": total_before,
        "total_size_after_bytes": total_after,
        **_size_delta(total_before, total_after),
        "processing_time_s": round(elapsed, 3),
        "files": results,
    }


# ---------------------------------------------------------------------------
# resize_image
# ---------------------------------------------------------------------------

class ResizeImageInput(BaseModel):
    input_file: str
    output_file: str
    width: int | None = Field(None, gt=0)
    height: int | None = Field(None, gt=0)
    mode: str = Field("fit", description="One of: fit, fill, exact")


def resize_image(params: ResizeImageInput) -> dict[str, Any]:
    src = val.validate_input_file(params.input_file)
    dst = val.validate_output_file(params.output_file)
    width, height = val.validate_dimensions(params.width, params.height)
    mode = params.mode if params.mode in ("fit", "fill", "exact") else "fit"
    proc.resize_image(src, dst, width, height, mode)  # type: ignore[arg-type]
    return {"output_file": str(dst), "width": width, "height": height, "mode": mode}


# ---------------------------------------------------------------------------
# batch_resize
# ---------------------------------------------------------------------------

class BatchResizeInput(BaseModel):
    input_folder: str
    output_folder: str | None = None
    width: int | None = Field(None, gt=0)
    height: int | None = Field(None, gt=0)
    mode: str = Field("fit", description="One of: fit, fill, exact")
    recursive: bool = False
    overwrite: bool = True


def batch_resize(params: BatchResizeInput) -> dict[str, Any]:
    src_folder = val.validate_input_folder(params.input_folder)
    out_folder = Path(params.output_folder) if params.output_folder else src_folder
    val.ensure_output_dir(out_folder)
    width, height = val.validate_dimensions(params.width, params.height)
    mode = params.mode if params.mode in ("fit", "fill", "exact") else "fit"

    files = _image_files(src_folder, params.recursive)
    results: list[dict] = []
    skipped = 0
    start = time.perf_counter()

    for f in files:
        rel = f.relative_to(src_folder)
        dst = out_folder / rel
        if not params.overwrite and dst.exists():
            skipped += 1
            continue
        val.ensure_output_dir(dst.parent)
        try:
            proc.resize_image(f, dst, width, height, mode)  # type: ignore[arg-type]
            results.append({"file": str(rel), "status": "ok"})
        except Exception as exc:
            results.append({"file": str(rel), "status": "error", "error": str(exc)})

    elapsed = time.perf_counter() - start
    failures = sum(1 for r in results if r["status"] == "error")
    return {
        "processed": len(results) - failures,
        "skipped": skipped,
        "failures": failures,
        "processing_time_s": round(elapsed, 3),
        "files": results,
    }


# ---------------------------------------------------------------------------
# convert_image
# ---------------------------------------------------------------------------

class ConvertImageInput(BaseModel):
    input_file: str
    output_file: str = Field(..., description="Output path including target extension.")


def convert_image(params: ConvertImageInput) -> dict[str, Any]:
    src = val.validate_input_file(params.input_file)
    dst = val.validate_output_file(params.output_file)
    proc.convert_image(src, dst)
    return {"output_file": str(dst)}


# ---------------------------------------------------------------------------
# batch_convert
# ---------------------------------------------------------------------------

class BatchConvertInput(BaseModel):
    input_folder: str
    output_folder: str
    output_format: str = Field(..., description="Target format extension e.g. webp, png")
    recursive: bool = False
    overwrite: bool = True


def batch_convert(params: BatchConvertInput) -> dict[str, Any]:
    src_folder = val.validate_input_folder(params.input_folder)
    out_folder = Path(params.output_folder)
    val.ensure_output_dir(out_folder)
    fmt = val.validate_output_format(params.output_format)

    files = _image_files(src_folder, params.recursive)
    results: list[dict] = []
    skipped = 0
    start = time.perf_counter()

    for f in files:
        rel = f.relative_to(src_folder).with_suffix(f".{fmt}")
        dst = out_folder / rel
        if not params.overwrite and dst.exists():
            skipped += 1
            continue
        val.ensure_output_dir(dst.parent)
        try:
            proc.convert_image(f, dst)
            results.append({"file": str(rel), "status": "ok"})
        except Exception as exc:
            results.append({"file": str(rel), "status": "error", "error": str(exc)})

    elapsed = time.perf_counter() - start
    failures = sum(1 for r in results if r["status"] == "error")
    return {
        "processed": len(results) - failures,
        "skipped": skipped,
        "failures": failures,
        "processing_time_s": round(elapsed, 3),
        "files": results,
    }


# ---------------------------------------------------------------------------
# strip_metadata
# ---------------------------------------------------------------------------

class StripMetadataInput(BaseModel):
    input_file: str
    output_file: str


def strip_metadata(params: StripMetadataInput) -> dict[str, Any]:
    src = val.validate_input_file(params.input_file)
    dst = val.validate_output_file(params.output_file)
    proc.strip_metadata(src, dst)
    return {"output_file": str(dst), "status": "metadata stripped"}


# ---------------------------------------------------------------------------
# image_info
# ---------------------------------------------------------------------------

class ImageInfoInput(BaseModel):
    input_file: str


def image_info(params: ImageInfoInput) -> dict[str, Any]:
    src = val.validate_input_file(params.input_file)
    return proc.get_image_info(src)


# ---------------------------------------------------------------------------
# create_thumbnail
# ---------------------------------------------------------------------------

class CreateThumbnailInput(BaseModel):
    input_file: str
    output_file: str
    width: int = Field(256, gt=0)
    height: int = Field(256, gt=0)


def create_thumbnail(params: CreateThumbnailInput) -> dict[str, Any]:
    src = val.validate_input_file(params.input_file)
    dst = val.validate_output_file(params.output_file)
    proc.create_thumbnail(src, dst, params.width, params.height)
    return {"output_file": str(dst), "width": params.width, "height": params.height}
