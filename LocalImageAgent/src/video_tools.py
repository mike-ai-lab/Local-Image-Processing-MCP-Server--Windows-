"""MCP tool definitions — Video processing."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ffmpeg import SUPPORTED_VIDEO_INPUT
import video_process as vp
import validation as val

logger = logging.getLogger("local-image-agent")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _video_files(folder: Path, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return [
        p for p in folder.glob(pattern)
        if p.is_file() and p.suffix.lstrip(".").lower() in SUPPORTED_VIDEO_INPUT
    ]


def _size_delta_mb(before: int, after: int) -> dict[str, Any]:
    saved = before - after
    pct = round(saved / before * 100, 2) if before > 0 else 0.0
    return {
        "size_before_mb": round(before / 1024 / 1024, 2),
        "size_after_mb":  round(after  / 1024 / 1024, 2),
        "saved_mb":       round(saved  / 1024 / 1024, 2),
        "reduction_pct":  pct,
    }


# ---------------------------------------------------------------------------
# video_info
# ---------------------------------------------------------------------------

class VideoInfoInput(BaseModel):
    input_file: str = Field(..., description="Path to the video file.")


def video_info(params: VideoInfoInput) -> dict[str, Any]:
    src = _validate_video(params.input_file)
    return vp.get_video_info(src)


# ---------------------------------------------------------------------------
# video_pipeline  (the main transaction tool)
# ---------------------------------------------------------------------------

class VideoPipelineInput(BaseModel):
    input_file: str = Field(..., description="Path to the source video file.")
    output_file: str = Field(..., description="Path to write the processed video.")
    steps: list[dict[str, Any]] = Field(
        ...,
        description="""
Ordered list of processing steps. Each step is an object with an 'op' key plus
parameters for that op. Available ops:

  trim            — cut the video. params: start (HH:MM:SS or seconds), end
  compress        — re-encode to reduce size. params: max_size_mb (optional), crf (0-51, default 23), preset
  strip_metadata  — remove all metadata. no extra params
  speed           — change speed/smoothness/sharpness.
                    params: speed (float, e.g. 3.0 = 3x faster),
                            interpolate_frames (bool, generates in-between frames for smoothness),
                            sharpen (float 0.0-1.0)
  social          — optimise for a platform.
                    params: platform = instagram|tiktok|youtube|twitter|facebook|linkedin

Example — compress to 50 MB, trim 0-60s, strip metadata:
[
  {"op": "compress", "max_size_mb": 50},
  {"op": "trim", "start": "0", "end": "60"},
  {"op": "strip_metadata"}
]
""",
    )


def video_pipeline(params: VideoPipelineInput) -> dict[str, Any]:
    """
    Execute multiple video processing operations as a single transaction.
    Steps run in order on a temp copy; the final result is written to output_file.
    """
    src = _validate_video(params.input_file)
    dst = Path(params.output_file)
    dst.parent.mkdir(parents=True, exist_ok=True)
    return vp.run_video_pipeline(src, dst, params.steps)


# ---------------------------------------------------------------------------
# compress_video  (convenience single-step)
# ---------------------------------------------------------------------------

class CompressVideoInput(BaseModel):
    input_file:         str   = Field(..., description="Path to the source video.")
    output_file:        str   = Field(..., description="Output path.")
    max_size_mb:        float | None = Field(None, gt=0, description="Target maximum file size in MB.")
    crf:                int   = Field(23, ge=0, le=51, description="CRF quality (lower = better). Default 23.")
    preset:             str   = Field("medium", description="ffmpeg preset: ultrafast/fast/medium/slow/veryslow.")
    audio_bitrate_kbps: int   = Field(128, gt=0, description="Audio bitrate in kbps.")


def compress_video(params: CompressVideoInput) -> dict[str, Any]:
    """Compress a single video, optionally targeting a maximum file size in MB."""
    src = _validate_video(params.input_file)
    dst = Path(params.output_file)
    dst.parent.mkdir(parents=True, exist_ok=True)
    before = src.stat().st_size
    vp.compress_video(src, dst,
                      max_size_mb=params.max_size_mb,
                      crf=params.crf,
                      preset=params.preset,
                      audio_bitrate_kbps=params.audio_bitrate_kbps)
    after = dst.stat().st_size
    return {"output_file": str(dst), **_size_delta_mb(before, after)}


# ---------------------------------------------------------------------------
# trim_video
# ---------------------------------------------------------------------------

class TrimVideoInput(BaseModel):
    input_file:  str = Field(..., description="Source video path.")
    output_file: str = Field(..., description="Output path.")
    start:       str = Field(..., description="Start time: HH:MM:SS, MM:SS, or seconds.")
    end:         str = Field(..., description="End time: HH:MM:SS, MM:SS, or seconds.")


def trim_video(params: TrimVideoInput) -> dict[str, Any]:
    """Trim a video to a specific time range."""
    src = _validate_video(params.input_file)
    dst = Path(params.output_file)
    dst.parent.mkdir(parents=True, exist_ok=True)
    vp.trim_video(src, dst, params.start, params.end)
    return {"output_file": str(dst),
            "start": params.start, "end": params.end,
            "size_mb": round(dst.stat().st_size / 1024 / 1024, 2)}


# ---------------------------------------------------------------------------
# strip_video_metadata
# ---------------------------------------------------------------------------

class StripVideoMetadataInput(BaseModel):
    input_file:  str = Field(..., description="Source video path.")
    output_file: str = Field(..., description="Output path.")


def strip_video_metadata(params: StripVideoMetadataInput) -> dict[str, Any]:
    """Remove all metadata from a video file."""
    src = _validate_video(params.input_file)
    dst = Path(params.output_file)
    dst.parent.mkdir(parents=True, exist_ok=True)
    vp.strip_video_metadata(src, dst)
    return {"output_file": str(dst), "status": "metadata stripped"}


# ---------------------------------------------------------------------------
# adjust_video  (speed + interpolation + sharpness)
# ---------------------------------------------------------------------------

class AdjustVideoInput(BaseModel):
    input_file:         str   = Field(..., description="Source video path.")
    output_file:        str   = Field(..., description="Output path.")
    speed:              float = Field(1.0, gt=0, description="Speed multiplier. 2.0 = 2x faster, 0.5 = half speed.")
    interpolate_frames: bool  = Field(False, description="Generate in-between frames to smooth motion.")
    sharpen:            float = Field(0.0, ge=0.0, le=1.0, description="Sharpness amount 0.0–1.0.")


def adjust_video(params: AdjustVideoInput) -> dict[str, Any]:
    """Change video speed, add frame interpolation for smoothness, and/or apply sharpening."""
    src = _validate_video(params.input_file)
    dst = Path(params.output_file)
    dst.parent.mkdir(parents=True, exist_ok=True)
    vp.adjust_video(src, dst,
                    speed=params.speed,
                    interpolate_frames=params.interpolate_frames,
                    sharpen=params.sharpen)
    return {
        "output_file":        str(dst),
        "speed":              params.speed,
        "interpolate_frames": params.interpolate_frames,
        "sharpen":            params.sharpen,
        "size_mb":            round(dst.stat().st_size / 1024 / 1024, 2),
    }


# ---------------------------------------------------------------------------
# optimize_for_social
# ---------------------------------------------------------------------------

class OptimizeSocialInput(BaseModel):
    input_file:  str = Field(..., description="Source video path.")
    output_file: str = Field(..., description="Output path.")
    platform:    str = Field("instagram",
                             description="Target platform: instagram, tiktok, youtube, twitter, facebook, linkedin.")


def optimize_for_social(params: OptimizeSocialInput) -> dict[str, Any]:
    """Re-encode a video with settings optimised for a specific social media platform."""
    src = _validate_video(params.input_file)
    dst = Path(params.output_file)
    dst.parent.mkdir(parents=True, exist_ok=True)
    before = src.stat().st_size
    vp.optimize_for_social(src, dst, platform=params.platform)
    after = dst.stat().st_size
    return {
        "output_file": str(dst),
        "platform": params.platform,
        **_size_delta_mb(before, after),
    }


# ---------------------------------------------------------------------------
# batch_optimize_social
# ---------------------------------------------------------------------------

class BatchOptimizeSocialInput(BaseModel):
    input_folder:  str  = Field(..., description="Folder containing video files.")
    output_folder: str  = Field(..., description="Destination folder.")
    platform:      str  = Field("instagram", description="Target platform.")
    recursive:     bool = Field(False)
    overwrite:     bool = Field(True)


def batch_optimize_social(params: BatchOptimizeSocialInput) -> dict[str, Any]:
    """Optimise all videos in a folder for a social media platform."""
    src_folder = val.validate_input_folder(params.input_folder)
    out_folder = Path(params.output_folder)
    out_folder.mkdir(parents=True, exist_ok=True)

    files = _video_files(src_folder, params.recursive)
    results: list[dict] = []
    total_before = total_after = skipped = 0
    start = time.perf_counter()

    for f in files:
        rel = f.relative_to(src_folder).with_suffix(".mp4")
        dst = out_folder / rel
        if not params.overwrite and dst.exists():
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        before = f.stat().st_size
        try:
            vp.optimize_for_social(f, dst, platform=params.platform)
            after = dst.stat().st_size
            total_before += before
            total_after  += after
            results.append({"file": str(rel), "status": "ok", **_size_delta_mb(before, after)})
        except Exception as exc:
            results.append({"file": str(rel), "status": "error", "error": str(exc)})

    elapsed = time.perf_counter() - start
    failures = sum(1 for r in results if r["status"] == "error")
    return {
        "processed":          len(results) - failures,
        "skipped":            skipped,
        "failures":           failures,
        "total_size_before_mb": round(total_before / 1024 / 1024, 2),
        "total_size_after_mb":  round(total_after  / 1024 / 1024, 2),
        "processing_time_s":  round(elapsed, 3),
        "files":              results,
    }


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------

def _validate_video(path: str) -> Path:
    p = Path(path)
    if not p.exists():
        raise val.ValidationError(f"Video file not found: {path}")
    if not p.is_file():
        raise val.ValidationError(f"Path is not a file: {path}")
    ext = p.suffix.lstrip(".").lower()
    if ext not in SUPPORTED_VIDEO_INPUT:
        raise val.ValidationError(
            f"Unsupported video format '.{ext}'. Supported: {sorted(SUPPORTED_VIDEO_INPUT)}"
        )
    return p
