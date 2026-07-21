"""Core video processing logic using FFmpeg."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ffmpeg import run_ffmpeg, probe, FFmpegError

import logging
logger = logging.getLogger("local-image-agent")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _video_info_from_probe(data: dict) -> dict[str, Any]:
    fmt = data.get("format", {})
    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    size = int(fmt.get("size", 0))
    duration = float(fmt.get("duration", 0))
    return {
        "duration_s":    round(duration, 3),
        "file_size_bytes": size,
        "file_size_mb":  round(size / 1024 / 1024, 2),
        "format":        fmt.get("format_long_name", ""),
        "bit_rate_kbps": round(int(fmt.get("bit_rate", 0)) / 1000, 1),
        "video_codec":   video_stream.get("codec_name", ""),
        "width":         video_stream.get("width"),
        "height":        video_stream.get("height"),
        "fps":           _parse_fps(video_stream.get("r_frame_rate", "")),
        "audio_codec":   audio_stream.get("codec_name", ""),
        "audio_channels": audio_stream.get("channels"),
        "audio_sample_rate": audio_stream.get("sample_rate"),
    }


def _parse_fps(rate_str: str) -> float | None:
    """Parse '30000/1001' or '30' into a float."""
    if not rate_str:
        return None
    try:
        if "/" in rate_str:
            a, b = rate_str.split("/")
            return round(int(a) / int(b), 3)
        return float(rate_str)
    except (ValueError, ZeroDivisionError):
        return None


def _parse_timecode(tc: str) -> float:
    """Accept HH:MM:SS, MM:SS, or plain seconds."""
    tc = tc.strip()
    if re.fullmatch(r"\d+(\.\d+)?", tc):
        return float(tc)
    parts = tc.split(":")
    parts = [float(p) for p in parts]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(f"Cannot parse timecode: {tc}")


# ---------------------------------------------------------------------------
# Video info
# ---------------------------------------------------------------------------

def get_video_info(path: Path) -> dict[str, Any]:
    data = probe(path)
    info = _video_info_from_probe(data)
    info["file"] = str(path)
    return info


# ---------------------------------------------------------------------------
# Compress to target size (binary search on bitrate)
# ---------------------------------------------------------------------------

def compress_video(
    src: Path,
    dst: Path,
    max_size_mb: float | None = None,
    crf: int = 23,
    preset: str = "medium",
    audio_bitrate_kbps: int = 128,
) -> Path:
    """
    Compress video. If max_size_mb given, binary-search bitrate to hit target.
    Otherwise encode with given CRF.
    """
    if max_size_mb is None:
        run_ffmpeg([
            "-i", str(src),
            "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
            "-c:a", "aac", "-b:a", f"{audio_bitrate_kbps}k",
            "-movflags", "+faststart",
            str(dst),
        ])
        return dst

    # Get duration for bitrate calculation
    info = probe(src)
    duration = float(info["format"].get("duration", 0))
    if duration <= 0:
        raise FFmpegError("Cannot determine video duration for size-targeted compression.")

    target_bits = max_size_mb * 1024 * 1024 * 8
    audio_bits  = audio_bitrate_kbps * 1000 * duration
    video_bits  = target_bits - audio_bits
    if video_bits <= 0:
        raise FFmpegError("Target size too small to fit even the audio track.")

    # Binary search: lo/hi in kbps
    lo  = 50
    hi  = int(video_bits / duration / 1000)
    best_kbps = lo

    for _ in range(8):  # max 8 iterations — accurate enough
        mid = (lo + hi) // 2
        run_ffmpeg([
            "-i", str(src),
            "-c:v", "libx264", "-b:v", f"{mid}k", "-preset", preset,
            "-c:a", "aac", "-b:a", f"{audio_bitrate_kbps}k",
            "-movflags", "+faststart",
            str(dst),
        ])
        actual_mb = dst.stat().st_size / 1024 / 1024
        if actual_mb <= max_size_mb:
            best_kbps = mid
            lo = mid + 1
        else:
            hi = mid - 1

    # Final encode at best found bitrate
    run_ffmpeg([
        "-i", str(src),
        "-c:v", "libx264", "-b:v", f"{best_kbps}k", "-preset", preset,
        "-c:a", "aac", "-b:a", f"{audio_bitrate_kbps}k",
        "-movflags", "+faststart",
        str(dst),
    ])
    return dst


# ---------------------------------------------------------------------------
# Trim
# ---------------------------------------------------------------------------

def trim_video(src: Path, dst: Path, start: str, end: str) -> Path:
    ss = _parse_timecode(start)
    to = _parse_timecode(end)
    run_ffmpeg([
        "-i", str(src),
        "-ss", str(ss), "-to", str(to),
        "-c", "copy",
        str(dst),
    ])
    return dst


# ---------------------------------------------------------------------------
# Strip metadata
# ---------------------------------------------------------------------------

def strip_video_metadata(src: Path, dst: Path) -> Path:
    run_ffmpeg([
        "-i", str(src),
        "-map_metadata", "-1",
        "-c", "copy",
        str(dst),
    ])
    return dst


# ---------------------------------------------------------------------------
# Speed change + optional frame interpolation + sharpness
# ---------------------------------------------------------------------------

def adjust_video(
    src: Path,
    dst: Path,
    speed: float = 1.0,
    interpolate_frames: bool = False,
    sharpen: float = 0.0,
) -> Path:
    """
    speed:             0.25–4.0 multiplier (>1 = faster, <1 = slower)
    interpolate_frames: use minterpolate to generate in-between frames (smooths fast motion)
    sharpen:           0.0 = off, 0.1–1.0 = subtle to strong
    """
    vf_parts: list[str] = []

    if abs(speed - 1.0) > 0.01:
        # setpts adjusts video timing; atempo adjusts audio (limited to 0.5–2.0 per filter)
        pts = round(1.0 / speed, 6)
        vf_parts.append(f"setpts={pts}*PTS")

    if interpolate_frames:
        vf_parts.append("minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")

    if sharpen > 0.0:
        s = min(sharpen, 1.0)
        # unsharp: luma_msize_x, luma_msize_y, luma_amount
        amount = round(1.0 + s * 4.0, 2)
        vf_parts.append(f"unsharp=5:5:{amount}:5:5:0")

    # Audio speed via atempo (chain filters for speeds outside 0.5–2.0)
    af_parts = _build_atempo(speed) if abs(speed - 1.0) > 0.01 else []

    cmd = ["-i", str(src)]
    if vf_parts:
        cmd += ["-vf", ",".join(vf_parts)]
    if af_parts:
        cmd += ["-af", ",".join(af_parts)]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-c:a", "aac", str(dst)]
    run_ffmpeg(cmd)
    return dst


def _build_atempo(speed: float) -> list[str]:
    """Chain atempo filters to handle speed outside 0.5–2.0."""
    filters = []
    remaining = speed
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={round(remaining, 6)}")
    return filters


# ---------------------------------------------------------------------------
# Social media optimise
# ---------------------------------------------------------------------------

# Presets: (max_width, max_height, target_bitrate_kbps, fps_cap)
SOCIAL_PRESETS: dict[str, tuple[int, int, int, int]] = {
    "instagram":  (1080, 1080, 3500, 30),
    "tiktok":     (1080, 1920, 4000, 30),
    "youtube":    (1920, 1080, 8000, 60),
    "twitter":    (1280,  720, 2500, 30),
    "facebook":   (1280,  720, 4000, 30),
    "linkedin":   (1920, 1080, 5000, 30),
}


def optimize_for_social(
    src: Path,
    dst: Path,
    platform: str = "instagram",
) -> Path:
    preset = SOCIAL_PRESETS.get(platform.lower())
    if preset is None:
        raise ValueError(
            f"Unknown platform '{platform}'. Choose from: {list(SOCIAL_PRESETS)}"
        )
    max_w, max_h, vbr, fps_cap = preset
    run_ffmpeg([
        "-i", str(src),
        "-vf",  f"scale='min({max_w},iw)':'min({max_h},ih)':force_original_aspect_ratio=decrease"
                f",fps=fps={fps_cap}",
        "-c:v", "libx264", "-b:v", f"{vbr}k", "-preset", "medium",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-map_metadata", "-1",
        str(dst),
    ])
    return dst


# ---------------------------------------------------------------------------
# Pipeline transaction
# ---------------------------------------------------------------------------

def run_video_pipeline(
    src: Path,
    dst: Path,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Execute an ordered list of processing steps on a video.
    Each step: {"op": "<name>", ...params}

    Supported ops:
        trim            start, end
        compress        max_size_mb, crf, preset
        strip_metadata
        speed           speed, interpolate_frames, sharpen
        social          platform
    """
    import tempfile, shutil as _shutil

    tmp_dir = Path(tempfile.mkdtemp())
    current = src
    log: list[dict] = []

    try:
        for i, step in enumerate(steps):
            op = step.get("op", "").lower()
            suffix = current.suffix
            nxt = tmp_dir / f"step_{i:02d}{suffix}"

            if op == "trim":
                trim_video(current, nxt, step["start"], step["end"])
            elif op == "compress":
                compress_video(
                    current, nxt,
                    max_size_mb=step.get("max_size_mb"),
                    crf=step.get("crf", 23),
                    preset=step.get("preset", "medium"),
                )
            elif op == "strip_metadata":
                strip_video_metadata(current, nxt)
            elif op == "speed":
                adjust_video(
                    current, nxt,
                    speed=step.get("speed", 1.0),
                    interpolate_frames=step.get("interpolate_frames", False),
                    sharpen=step.get("sharpen", 0.0),
                )
            elif op == "social":
                optimize_for_social(current, nxt, platform=step.get("platform", "instagram"))
            else:
                raise ValueError(f"Unknown pipeline op: '{op}'")

            log.append({"step": i + 1, "op": op, "status": "ok",
                        "size_mb": round(nxt.stat().st_size / 1024 / 1024, 2)})
            current = nxt

        dst.parent.mkdir(parents=True, exist_ok=True)
        _shutil.copy2(str(current), str(dst))

    finally:
        _shutil.rmtree(tmp_dir, ignore_errors=True)

    before = src.stat().st_size
    after  = dst.stat().st_size
    return {
        "output_file":       str(dst),
        "steps_completed":   len(log),
        "size_before_mb":    round(before / 1024 / 1024, 2),
        "size_after_mb":     round(after  / 1024 / 1024, 2),
        "reduction_pct":     round((before - after) / before * 100, 2) if before else 0,
        "pipeline_log":      log,
    }
