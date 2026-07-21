"""
TCP bridge to the SketchUp Ruby extension.

Architecture:
  MCP tool call
    → sketchup_bridge.run_ruby(code)
      → TCP socket → SketchUp Ruby extension (port 9876)
        → Executes Ruby inside SketchUp
          → Returns JSON result

The Ruby extension must be installed in SketchUp and the server started via
  Plugins → MCP Bridge → Start Server

Frame format (matches sketchup-mcp2 protocol):
  [4 bytes big-endian length][UTF-8 JSON payload]
"""

from __future__ import annotations

import json
import logging
import socket
import struct
from typing import Any

logger = logging.getLogger("local-image-agent")

SKETCHUP_HOST    = "127.0.0.1"
SKETCHUP_PORT    = 9876
CONNECT_TIMEOUT  = 5.0    # seconds to wait for SketchUp to accept
RECV_TIMEOUT     = 120.0  # seconds to wait for Ruby execution result
MAX_FRAME_BYTES  = 64 * 1024 * 1024  # 64 MB cap


class SketchUpNotRunning(RuntimeError):
    """Raised when SketchUp is not reachable on the bridge port."""


class SketchUpError(RuntimeError):
    """Raised when the Ruby side returns an error."""


# ---------------------------------------------------------------------------
# Low-level framing
# ---------------------------------------------------------------------------

def _send_frame(sock: socket.socket, payload: bytes) -> None:
    header = struct.pack(">I", len(payload))
    sock.sendall(header + payload)


def _recv_frame(sock: socket.socket) -> bytes:
    header = _recv_exactly(sock, 4)
    length = struct.unpack(">I", header)[0]
    if length > MAX_FRAME_BYTES:
        raise SketchUpError(f"Response frame too large: {length} bytes")
    return _recv_exactly(sock, length)


def _recv_exactly(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise SketchUpError("SketchUp closed the connection before sending a complete frame.")
        buf.extend(chunk)
    return bytes(buf)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_ruby(ruby_code: str, timeout: float = RECV_TIMEOUT) -> Any:
    """
    Execute arbitrary Ruby inside the running SketchUp instance.
    Returns the parsed JSON result.
    Raises SketchUpNotRunning if SketchUp is not reachable.
    Raises SketchUpError if Ruby raises an exception.
    """
    request = json.dumps({"jsonrpc": "2.0", "method": "eval_ruby",
                          "params": {"code": ruby_code}, "id": 1})
    payload = request.encode("utf-8")

    try:
        sock = socket.create_connection((SKETCHUP_HOST, SKETCHUP_PORT),
                                        timeout=CONNECT_TIMEOUT)
    except (ConnectionRefusedError, OSError) as exc:
        raise SketchUpNotRunning(
            f"Cannot connect to SketchUp on {SKETCHUP_HOST}:{SKETCHUP_PORT}. "
            "Make sure SketchUp is open and the MCP Bridge extension is running "
            "(Plugins → MCP Bridge → Start Server)."
        ) from exc

    with sock:
        sock.settimeout(timeout)
        logger.debug("SketchUp ← %d chars of Ruby", len(ruby_code))
        _send_frame(sock, payload)
        raw = _recv_frame(sock)

    response = json.loads(raw.decode("utf-8"))
    logger.debug("SketchUp → %s", str(response)[:200])

    if "error" in response:
        raise SketchUpError(
            f"Ruby error in SketchUp: {response['error'].get('message', response['error'])}"
        )
    return response.get("result")


def is_running() -> bool:
    """Return True if SketchUp bridge is reachable."""
    try:
        sock = socket.create_connection((SKETCHUP_HOST, SKETCHUP_PORT),
                                        timeout=CONNECT_TIMEOUT)
        sock.close()
        return True
    except OSError:
        return False


def run_ruby_json(ruby_expression: str) -> Any:
    """
    Execute a Ruby expression that returns a JSON string.
    Automatically parses the result.
    """
    # Wrap expression so Ruby serialises result to JSON and returns the string
    wrapped = f"""
require 'json'
begin
  _result_ = begin
    {ruby_expression}
  end
  _result_.to_json
rescue => e
  {{"error" => e.message, "backtrace" => e.backtrace.first(5)}}.to_json
end
""".strip()
    raw = run_ruby(wrapped)
    if isinstance(raw, str):
        return json.loads(raw)
    return raw
