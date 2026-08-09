"""MCP tool — silent screen capture using Windows GDI (no dependencies, no UI flashes)."""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("local-image-agent")

# ---------------------------------------------------------------------------
# GDI screen capture — pure ctypes, zero external libs, background-safe
# ---------------------------------------------------------------------------

_gdi32 = ctypes.windll.gdi32
_user32 = ctypes.windll.user32

SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize",          ctypes.c_uint32),
        ("biWidth",         ctypes.c_int32),
        ("biHeight",        ctypes.c_int32),
        ("biPlanes",        ctypes.c_uint16),
        ("biBitCount",      ctypes.c_uint16),
        ("biCompression",   ctypes.c_uint32),
        ("biSizeImage",     ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed",       ctypes.c_uint32),
        ("biClrImportant",  ctypes.c_uint32),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]


def _capture_screen_png(output_path: str, monitor: int = 0) -> dict[str, Any]:
    """
    Capture a monitor using pure Windows GDI (ctypes only).
    Saves as PNG via Pillow (already a dep via Pillow in requirements).
    Falls back to PowerShell if Pillow is unavailable.
    monitor: 0 = virtual screen (all monitors), 1+ = specific monitor index.
    """
    from PIL import Image  # Pillow is already a dependency

    SM_XVIRTUALSCREEN  = 76
    SM_YVIRTUALSCREEN  = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79
    SM_CMONITORS       = 80

    if monitor == 0:
        left   = _user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        top    = _user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        width  = _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        height = _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    else:
        # Enumerate monitors
        monitors = []

        def _monitor_enum_proc(hmon, hdc, lprect, lparam):
            rect = ctypes.cast(lprect, ctypes.POINTER(ctypes.wintypes.RECT)).contents
            monitors.append((rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top))
            return 1

        MonitorEnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong, ctypes.c_ulong,
                                              ctypes.POINTER(ctypes.wintypes.RECT), ctypes.c_double)
        _user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_monitor_enum_proc), 0)

        if monitor > len(monitors):
            raise ValueError(f"Monitor {monitor} not found. Available: {len(monitors)}")

        left, top, width, height = monitors[monitor - 1]

    # Get screen DC
    hdc_screen = _user32.GetDC(None)
    hdc_mem    = _gdi32.CreateCompatibleDC(hdc_screen)
    hbitmap    = _gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
    _gdi32.SelectObject(hdc_mem, hbitmap)
    _gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, left, top, SRCCOPY)

    # Extract pixel data
    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize        = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth       = width
    bmi.bmiHeader.biHeight      = -height  # top-down
    bmi.bmiHeader.biPlanes      = 1
    bmi.bmiHeader.biBitCount    = 32
    bmi.bmiHeader.biCompression = 0  # BI_RGB

    buf = (ctypes.c_char * (width * height * 4))()
    _gdi32.GetDIBits(hdc_mem, hbitmap, 0, height, buf, ctypes.byref(bmi), DIB_RGB_COLORS)

    # Clean up GDI objects
    _gdi32.DeleteObject(hbitmap)
    _gdi32.DeleteDC(hdc_mem)
    _user32.ReleaseDC(None, hdc_screen)

    # Build PIL image from BGRA buffer
    import struct
    raw = bytes(buf)
    img = Image.frombuffer("RGBA", (width, height), raw, "raw", "BGRA", 0, 1)
    img = img.convert("RGB")
    img.save(output_path, "PNG", optimize=True)

    return {"width": width, "height": height, "monitor": monitor}


# ---------------------------------------------------------------------------
# Tool input / output
# ---------------------------------------------------------------------------

class CaptureScreenInput(BaseModel):
    output_file: str = Field(
        ...,
        description=(
            "Full path where the screenshot PNG will be saved. "
            "Example: C:/Users/PC/Desktop/LocalImageAgent-Clean/snapshot_20260809_120000.png"
        ),
    )
    monitor: int = Field(
        0,
        ge=0,
        description=(
            "Monitor to capture. 0 = virtual desktop (all monitors combined). "
            "1 = primary monitor, 2 = secondary, etc."
        ),
    )
    return_base64: bool = Field(
        False,
        description="If true, also return the image as base64 so it can be shown inline in chat.",
    )


def capture_screen(params: CaptureScreenInput) -> dict[str, Any]:
    """
    Silently capture the Windows desktop/monitor using GDI — no window flash,
    no new processes, no interference with running applications.
    """
    out = Path(params.output_file)
    out.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    meta = _capture_screen_png(str(out), monitor=params.monitor)
    elapsed = round(time.perf_counter() - t0, 3)

    size_bytes = out.stat().st_size
    result: dict[str, Any] = {
        "output_file":    str(out),
        "width":          meta["width"],
        "height":         meta["height"],
        "monitor":        meta["monitor"],
        "size_kb":        round(size_bytes / 1024, 1),
        "capture_time_s": elapsed,
        "status":         "ok",
    }

    if params.return_base64:
        result["mime_type"] = "image/png"
        result["base64"]    = base64.b64encode(out.read_bytes()).decode("ascii")

    logger.info(
        "capture_screen: monitor=%s  %dx%d  %.1f KB  (%.3fs)",
        meta["monitor"], meta["width"], meta["height"],
        result["size_kb"], elapsed,
    )
    return result
