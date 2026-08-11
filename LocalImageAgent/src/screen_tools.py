"""MCP tool - silent screen capture using Windows GDI (no dependencies, no UI flashes)."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import io
import logging
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("local-image-agent")

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


def _capture_to_pil(monitor: int = 0):
    """Capture a monitor via GDI and return a PIL Image (RGB) plus width/height."""
    from PIL import Image

    SM_XVIRTUALSCREEN  = 76
    SM_YVIRTUALSCREEN  = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79

    if monitor == 0:
        left   = _user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        top    = _user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        width  = _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        height = _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    else:
        monitors = []

        def _cb(hmon, hdc, lprect, lparam):
            rect = ctypes.cast(lprect, ctypes.POINTER(ctypes.wintypes.RECT)).contents
            monitors.append((rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top))
            return 1

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.POINTER(ctypes.wintypes.RECT), ctypes.c_double,
        )
        _user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_cb), 0)

        if monitor > len(monitors):
            raise ValueError(f"Monitor {monitor} not found. Available: {len(monitors)}")

        left, top, width, height = monitors[monitor - 1]

    hdc_screen = _user32.GetDC(None)
    hdc_mem    = _gdi32.CreateCompatibleDC(hdc_screen)
    hbitmap    = _gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
    _gdi32.SelectObject(hdc_mem, hbitmap)
    _gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, left, top, SRCCOPY)

    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize        = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth       = width
    bmi.bmiHeader.biHeight      = -height
    bmi.bmiHeader.biPlanes      = 1
    bmi.bmiHeader.biBitCount    = 32
    bmi.bmiHeader.biCompression = 0

    buf = (ctypes.c_char * (width * height * 4))()
    _gdi32.GetDIBits(hdc_mem, hbitmap, 0, height, buf, ctypes.byref(bmi), DIB_RGB_COLORS)

    _gdi32.DeleteObject(hbitmap)
    _gdi32.DeleteDC(hdc_mem)
    _user32.ReleaseDC(None, hdc_screen)

    raw = bytes(buf)
    img = Image.frombuffer("RGBA", (width, height), raw, "raw", "BGRA", 0, 1)
    return img.convert("RGB"), width, height


class CaptureScreenInput(BaseModel):
    output_file: str = Field(
        ...,
        description="Full path where the screenshot PNG will be saved.",
    )
    monitor: int = Field(
        0, ge=0,
        description="Monitor to capture. 0 = all monitors, 1 = primary, 2 = secondary, etc.",
    )
    return_base64: bool = Field(
        False,
        description="Kept for backwards compatibility - ignored.",
    )


def capture_screen(params: CaptureScreenInput):
    """
    Silently capture the Windows desktop using GDI - no window flash, no new processes,
    zero interference with running applications. Returns a proper MCP Image content block
    so the screenshot renders inline in chat.
    """
    from PIL import Image as PilImage
    from fastmcp.utilities.types import Image as MCPImage

    out = Path(params.output_file)
    out.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    img, width, height = _capture_to_pil(monitor=params.monitor)

    # Save full-res PNG to disk
    img.save(str(out), "PNG", optimize=True)
    size_kb = round(out.stat().st_size / 1024, 1)

    # Encode as JPEG for inline display - scale down large screens
    thumb = img.copy()
    if max(width, height) > 1280:
        thumb.thumbnail((1280, 1280), PilImage.LANCZOS)

    jpeg_buf = io.BytesIO()
    thumb.save(jpeg_buf, format="JPEG", quality=82, optimize=True)
    jpeg_bytes = jpeg_buf.getvalue()

    elapsed = round(time.perf_counter() - t0, 3)
    logger.info(
        "capture_screen: monitor=%s  %dx%d  png=%.1fKB  jpeg=%.1fKB  (%.3fs)",
        params.monitor, width, height, size_kb, round(len(jpeg_bytes) / 1024, 1), elapsed,
    )

    # Return proper MCP ImageContent block - this is what renders inline in chat
    return MCPImage(data=jpeg_bytes, format="jpeg")
