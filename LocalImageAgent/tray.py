"""
LocalImageAgent — System Tray Controller
- Green icon = server running
- Red icon   = server stopped
- Click tray icon to start/stop
- Right-click for menu
"""

import sys
import os
import subprocess
import threading
import time
import socket
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE    = Path(__file__).parent
PYTHON  = BASE / ".venv" / "Scripts" / "python.exe"
SERVER  = BASE / "src" / "main_http.py"
NGROK   = BASE / "ngrok" / "ngrok.exe"
MCP_URL = "https://pectin-parting-caution.ngrok-free.dev/mcp"

# ---------------------------------------------------------------------------
# Icon helpers
# ---------------------------------------------------------------------------

def _make_icon(color: str) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=color, outline="white", width=3)
    return img

ICON_GREEN = _make_icon("#22c55e")
ICON_RED   = _make_icon("#ef4444")
ICON_AMBER = _make_icon("#f59e0b")

# ---------------------------------------------------------------------------
# Process state
# ---------------------------------------------------------------------------
_server_proc: subprocess.Popen | None = None
_ngrok_proc:  subprocess.Popen | None = None
_lock = threading.Lock()


def _port_free(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return False
    except OSError:
        return True


def _kill_port(port: int) -> None:
    """Kill whatever is holding the given port."""
    try:
        out = subprocess.check_output(
            f"netstat -ano | findstr :{port}", shell=True, text=True
        )
        for line in out.splitlines():
            parts = line.split()
            if parts:
                pid = parts[-1]
                if pid.isdigit() and pid != "0":
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True,
                                   capture_output=True)
    except Exception:
        pass


def is_running() -> bool:
    with _lock:
        return (
            _server_proc is not None and _server_proc.poll() is None
            and _ngrok_proc is not None and _ngrok_proc.poll() is None
        )


# ---------------------------------------------------------------------------
# Start / Stop
# ---------------------------------------------------------------------------

def start_server(icon: pystray.Icon) -> None:
    global _server_proc, _ngrok_proc

    icon.icon = ICON_AMBER
    icon.title = "MCP Server - Starting..."

    # Clean up stale processes
    _kill_port(8765)
    subprocess.run("taskkill /F /IM ngrok.exe", shell=True, capture_output=True)
    time.sleep(1)

    with _lock:
        _server_proc = subprocess.Popen(
            [str(PYTHON), str(SERVER)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    # Wait for port
    for _ in range(15):
        time.sleep(1)
        if not _port_free(8765):
            break
    else:
        icon.icon  = ICON_RED
        icon.title = "MCP Server - Failed to start"
        _update_menu(icon)
        return

    with _lock:
        _ngrok_proc = subprocess.Popen(
            [str(NGROK), "http", "8765",
             "--domain=pectin-parting-caution.ngrok-free.dev"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    time.sleep(2)
    icon.icon  = ICON_GREEN
    icon.title = f"MCP Server - Running  |  {MCP_URL}"
    _update_menu(icon)


def stop_server(icon: pystray.Icon) -> None:
    global _server_proc, _ngrok_proc
    with _lock:
        if _server_proc:
            _server_proc.terminate()
            _server_proc = None
        if _ngrok_proc:
            _ngrok_proc.terminate()
            _ngrok_proc = None
    subprocess.run("taskkill /F /IM ngrok.exe", shell=True, capture_output=True)
    icon.icon  = ICON_RED
    icon.title = "MCP Server - Stopped"
    _update_menu(icon)


def toggle(icon: pystray.Icon, item=None) -> None:
    if is_running():
        threading.Thread(target=stop_server, args=(icon,), daemon=True).start()
    else:
        threading.Thread(target=start_server, args=(icon,), daemon=True).start()


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

def _update_menu(icon: pystray.Icon) -> None:
    running = is_running()
    icon.menu = pystray.Menu(
        pystray.MenuItem(
            "Running  (click to stop)" if running else "Stopped  (click to start)",
            toggle,
            default=True,
        ),
        pystray.MenuItem(
            f"URL: {MCP_URL}",
            lambda icon, item: None,
            enabled=False,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", lambda icon, item: _quit(icon)),
    )


def _quit(icon: pystray.Icon) -> None:
    stop_server(icon)
    icon.stop()


# ---------------------------------------------------------------------------
# Watchdog — restart server if it crashes
# ---------------------------------------------------------------------------

def _watchdog(icon: pystray.Icon) -> None:
    while True:
        time.sleep(10)
        with _lock:
            sp = _server_proc
            np = _ngrok_proc
        if sp is not None and sp.poll() is not None:
            # Server died — restart
            threading.Thread(target=start_server, args=(icon,), daemon=True).start()
        elif np is not None and np.poll() is not None:
            threading.Thread(target=start_server, args=(icon,), daemon=True).start()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    icon = pystray.Icon(
        name="LocalImageAgent",
        icon=ICON_RED,
        title="MCP Server - Stopped",
    )
    _update_menu(icon)

    # Auto-start on launch
    threading.Thread(target=start_server, args=(icon,), daemon=True).start()
    # Watchdog
    threading.Thread(target=_watchdog, args=(icon,), daemon=True).start()

    icon.run()


if __name__ == "__main__":
    main()
