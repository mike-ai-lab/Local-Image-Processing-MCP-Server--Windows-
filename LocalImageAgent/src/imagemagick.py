"""ImageMagick subprocess wrapper."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from config import config

logger = logging.getLogger("local-image-agent")


class ImageMagickError(RuntimeError):
    """Raised when an ImageMagick command fails."""


def _resolve_magick() -> str:
    """Return the path to magick.exe, raising if not found."""
    # Use explicitly configured path first
    if config.magick_exe and Path(config.magick_exe).is_file():
        return config.magick_exe

    # Fall back to PATH lookup
    found = shutil.which("magick")
    if found:
        return found

    raise ImageMagickError(
        "ImageMagick 'magick.exe' not found. "
        "Install ImageMagick and ensure it is on PATH, or set magick_exe in config.json."
    )


MAGICK_EXE: str = ""  # resolved lazily


def _get_magick() -> str:
    global MAGICK_EXE
    if not MAGICK_EXE:
        MAGICK_EXE = _resolve_magick()
    return MAGICK_EXE


def run_magick(args: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a synchronous ImageMagick command."""
    cmd = [_get_magick(), *args]
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise ImageMagickError(
            f"ImageMagick failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )
    return result
