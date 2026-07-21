"""FFmpeg subprocess wrapper."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

logger = logging.getLogger("local-image-agent")

SUPPORTED_VIDEO_INPUT  = frozenset(["mp4", "mov", "avi", "mkv", "wmv", "webm", "flv", "m4v", "ts", "mts"])
SUPPORTED_VIDEO_OUTPUT = frozenset(["mp4", "mov", "avi", "mkv", "webm"])

FFMPEG_EXE: str = ""
FFPROBE_EXE: str = ""


class FFmpegError(RuntimeError):
    """Raised when an ffmpeg/ffprobe command fails."""


def _resolve(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    raise FFmpegError(
        f"'{name}' not found on PATH. Install FFmpeg and ensure it is on PATH."
    )


def _get_ffmpeg() -> str:
    global FFMPEG_EXE
    if not FFMPEG_EXE:
        FFMPEG_EXE = _resolve("ffmpeg")
    return FFMPEG_EXE


def _get_ffprobe() -> str:
    global FFPROBE_EXE
    if not FFPROBE_EXE:
        FFPROBE_EXE = _resolve("ffprobe")
    return FFPROBE_EXE


def run_ffmpeg(args: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run ffmpeg with the given arguments. -y (overwrite) is always prepended."""
    cmd = [_get_ffmpeg(), "-y", *args]
    logger.debug("ffmpeg: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise FFmpegError(
            f"ffmpeg failed (exit {result.returncode}):\n{result.stderr[-2000:].strip()}"
        )
    return result


def probe(path: Path) -> dict:
    """Return ffprobe JSON for a video file."""
    cmd = [
        _get_ffprobe(),
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise FFmpegError(f"ffprobe failed:\n{result.stderr.strip()}")
    return json.loads(result.stdout)
