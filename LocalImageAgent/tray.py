"""
LocalImageAgent — Headless Background Service
No system tray icon. Runs silently in the background.
- Auto-starts MCP server + ngrok on launch
- Watchdog restarts both if either crashes
- Snapshot backup protects against bad code edits
"""

import sys
import os
import subprocess
import threading
import time
import socket
import shutil
import logging
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging — write to agent.log same as the server
# ---------------------------------------------------------------------------
BASE       = Path(__file__).parent
LOG_FILE   = BASE / "agent.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  tray  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("tray")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PYTHON   = BASE / ".venv" / "Scripts" / "python.exe"
SERVER   = BASE / "src" / "main_http.py"
BACKUP   = BASE / "src" / "main_http.py.backup"
NGROK    = BASE / "ngrok" / "ngrok.exe"
DOMAIN   = "pectin-parting-caution.ngrok-free.dev"
MCP_URL  = f"https://{DOMAIN}/mcp"

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
# Backup / syntax guard
# ---------------------------------------------------------------------------

def _syntax_ok(path: Path) -> bool:
    """Return True if the file compiles without errors."""
    result = subprocess.run(
        [str(PYTHON), "-m", "py_compile", str(path)],
        capture_output=True, text=True
    )
    return result.returncode == 0


def _save_backup() -> None:
    """Snapshot current server file as known-good backup."""
    try:
        shutil.copy2(SERVER, BACKUP)
        logger.info("Backup saved: %s", BACKUP.name)
    except Exception as e:
        logger.warning("Could not save backup: %s", e)


def _restore_backup() -> bool:
    """Restore backup over the broken server file. Returns True if restored."""
    if BACKUP.exists():
        try:
            shutil.copy2(BACKUP, SERVER)
            logger.warning("BACKUP RESTORED — bad edit reverted, server restarting from last good version")
            return True
        except Exception as e:
            logger.error("Could not restore backup: %s", e)
    return False


# ---------------------------------------------------------------------------
# Start / Stop
# ---------------------------------------------------------------------------

def start_server() -> bool:
    """Start MCP server + ngrok. Returns True on success."""
    global _server_proc, _ngrok_proc

    logger.info("Starting MCP server...")

    # Syntax check before launching
    if not _syntax_ok(SERVER):
        logger.error("Syntax error in %s — attempting backup restore", SERVER.name)
        if _restore_backup():
            if not _syntax_ok(SERVER):
                logger.error("Backup also has errors — cannot start server")
                return False
        else:
            logger.error("No backup available — cannot start server")
            return False

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

    # Wait for port 8765 to be live
    for _ in range(15):
        time.sleep(1)
        if not _port_free(8765):
            break
    else:
        logger.error("MCP server did not come up on port 8765")
        return False

    with _lock:
        _ngrok_proc = subprocess.Popen(
            [str(NGROK), "http", "8765", f"--domain={DOMAIN}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    time.sleep(2)
    logger.info("Server running — MCP URL: %s", MCP_URL)

    # Save a good backup now that startup succeeded
    _save_backup()
    return True


def stop_server() -> None:
    global _server_proc, _ngrok_proc
    with _lock:
        if _server_proc:
            _server_proc.terminate()
            _server_proc = None
        if _ngrok_proc:
            _ngrok_proc.terminate()
            _ngrok_proc = None
    subprocess.run("taskkill /F /IM ngrok.exe", shell=True, capture_output=True)
    logger.info("Server stopped")


# ---------------------------------------------------------------------------
# Watchdog
# ---------------------------------------------------------------------------

def _watchdog() -> None:
    """Restart server/ngrok if either crashes or port drops."""
    while True:
        time.sleep(10)
        with _lock:
            sp = _server_proc
            np = _ngrok_proc
        if sp is None:
            continue  # intentionally stopped, don't revive
        server_dead = sp.poll() is not None
        ngrok_dead  = np is not None and np.poll() is not None
        port_gone   = _port_free(8765)
        if server_dead or ngrok_dead or port_gone:
            reason = []
            if server_dead: reason.append("server crashed")
            if ngrok_dead:  reason.append("ngrok crashed")
            if port_gone:   reason.append("port 8765 gone")
            logger.warning("Watchdog triggered (%s) — restarting...", ", ".join(reason))
            threading.Thread(target=start_server, daemon=True).start()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("LocalImageAgent background service starting")

    # Auto-start server on launch
    threading.Thread(target=start_server, daemon=True).start()

    # Watchdog runs forever
    threading.Thread(target=_watchdog, daemon=True).start()

    # Keep main thread alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
        stop_server()


if __name__ == "__main__":
    main()
