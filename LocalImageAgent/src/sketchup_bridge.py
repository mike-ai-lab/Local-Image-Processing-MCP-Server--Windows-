"""
TCP bridge to the SketchUp Ruby extension.

Protocol: newline-delimited JSON (same as mhyrr/sketchup-mcp reference implementation).
  → Send: {"jsonrpc":"2.0","method":"...","params":{...},"id":1}\n
  ← Recv: {"jsonrpc":"2.0","id":1,"result":...}\n

The Ruby extension must be installed and started:
  SketchUp → Plugins → MCP Bridge → Start Server
"""

from __future__ import annotations

import json
import logging
import socket
import time
from typing import Any

logger = logging.getLogger("local-image-agent")

SKETCHUP_HOST   = "127.0.0.1"
SKETCHUP_PORT   = 9876
CONNECT_TIMEOUT = 5.0    # seconds to wait for connection
RECV_TIMEOUT    = 30.0   # seconds to wait for Ruby result
MAX_RETRIES     = 2


class SketchUpNotRunning(RuntimeError):
    """Raised when SketchUp is not reachable on the bridge port."""


class SketchUpError(RuntimeError):
    """Raised when the Ruby side returns an error."""


# ---------------------------------------------------------------------------
# Per-call connection (Ruby closes socket after each response)
# ---------------------------------------------------------------------------


def _new_connection() -> socket.socket:
    """Open a fresh socket connection to SketchUp."""
    try:
        sock = socket.create_connection(
            (SKETCHUP_HOST, SKETCHUP_PORT), timeout=CONNECT_TIMEOUT
        )
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        logger.debug("Connected to SketchUp at %s:%d", SKETCHUP_HOST, SKETCHUP_PORT)
        return sock
    except (ConnectionRefusedError, OSError) as exc:
        raise SketchUpNotRunning(
            f"Cannot connect to SketchUp on {SKETCHUP_HOST}:{SKETCHUP_PORT}. "
            "Make sure SketchUp is open and MCP Bridge is running "
            "(Plugins → MCP Bridge → Start Server)."
        ) from exc


def _disconnect():
    global _connection
    if _connection:
        try:
            _connection.close()
        except Exception:
            pass
        _connection = None


# ---------------------------------------------------------------------------
# Receive helpers — chunked read until valid JSON (reference pattern)
# ---------------------------------------------------------------------------

def _receive_response(sock: socket.socket, timeout: float) -> dict:
    """Read newline-delimited JSON — returns on the first valid complete line."""
    sock.settimeout(timeout)
    buf = b""

    while True:
        try:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
            # Try each newline-terminated line
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    return json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
        except socket.timeout:
            break
        except (ConnectionError, OSError) as e:
            raise SketchUpError(f"Connection error receiving from SketchUp: {e}") from e

    # Last attempt on remainder
    for line in buf.split(b"\n"):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            pass

    raise SketchUpError("No valid JSON response received from SketchUp.")


# ---------------------------------------------------------------------------
# Core send/receive with retry
# ---------------------------------------------------------------------------

def _send_command(method: str, params: dict | None = None,
                  timeout: float = RECV_TIMEOUT) -> Any:
    """Send a JSON-RPC command and return the result. Retries on connection failure."""
    request = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": 1,
    }
    payload = (json.dumps(request) + "\n").encode("utf-8")

    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        sock = None
        try:
            sock = _new_connection()
            sock.settimeout(CONNECT_TIMEOUT)
            logger.debug("SketchUp ← %s (attempt %d)", method, attempt + 1)
            sock.sendall(payload)

            response = _receive_response(sock, timeout)
            logger.debug("SketchUp → %s", str(response)[:300])

            if "error" in response:
                err = response["error"]
                raise SketchUpError(
                    f"SketchUp error: {err.get('message', err)}"
                )

            return response.get("result")

        except SketchUpNotRunning:
            raise  # Don't retry — SketchUp isn't open

        except SketchUpError:
            raise  # Don't retry — Ruby returned an error

        except Exception as exc:
            last_exc = exc
            logger.warning(
                "SketchUp communication error (attempt %d/%d): %s",
                attempt + 1, MAX_RETRIES + 1, exc,
            )
            if attempt < MAX_RETRIES:
                time.sleep(0.5)
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    raise SketchUpError(
        f"Failed to communicate with SketchUp after {MAX_RETRIES + 1} attempts: {last_exc}"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_ruby(ruby_code: str, timeout: float = RECV_TIMEOUT) -> Any:
    """Execute arbitrary Ruby inside SketchUp. Returns the raw result."""
    return _send_command("eval_ruby", {"code": ruby_code}, timeout=timeout)


def run_ruby_json(ruby_expression: str, timeout: float = RECV_TIMEOUT) -> Any:
    """
    Execute a Ruby expression, serialise the result to JSON in Ruby,
    and parse it back in Python. Handles nested objects correctly.
    """
    wrapped = f"""
require 'json'
begin
  _r_ = begin
    {ruby_expression}
  end
  _r_.to_json
rescue => e
  {{"error" => e.message, "backtrace" => e.backtrace.first(3)}}.to_json
end
""".strip()
    raw = run_ruby(wrapped, timeout=timeout)
    if isinstance(raw, str):
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "error" in parsed and len(parsed) <= 2:
            raise SketchUpError(
                f"Ruby error: {parsed['error']}\n"
                + "\n".join(parsed.get("backtrace", []))
            )
        return parsed
    return raw


def send_named_command(name: str, arguments: dict | None = None,
                       timeout: float = RECV_TIMEOUT) -> Any:
    """
    Send a named command using the tools/call envelope.
    Matches the protocol used by mhyrr/sketchup-mcp.
    """
    return _send_command(
        "tools/call",
        {"name": name, "arguments": arguments or {}},
        timeout=timeout,
    )


def is_running() -> bool:
    """Return True if the SketchUp bridge is reachable."""
    try:
        sock = socket.create_connection(
            (SKETCHUP_HOST, SKETCHUP_PORT), timeout=CONNECT_TIMEOUT
        )
        sock.close()
        return True
    except OSError:
        return False
