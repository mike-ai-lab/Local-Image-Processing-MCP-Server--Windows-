"""Core file system operations for the file tools."""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

import logging
logger = logging.getLogger("local-image-agent")


# Plain-text extensions the AI can meaningfully read/edit
TEXT_EXTENSIONS = frozenset([
    "txt", "md", "markdown", "rst",
    "py", "js", "ts", "jsx", "tsx", "mjs", "cjs",
    "html", "htm", "css", "scss", "sass", "less",
    "json", "jsonc", "yaml", "yml", "toml", "ini", "cfg", "conf", "config",
    "xml", "svg", "csv", "tsv",
    "sql", "sh", "bash", "zsh", "ps1", "bat", "cmd",
    "env", "env.local", "gitignore", "gitattributes", "editorconfig",
    "c", "cpp", "h", "hpp", "cs", "java", "go", "rs", "rb", "php",
    "r", "m", "swift", "kt", "scala", "lua", "pl",
    "log", "diff", "patch",
])


def _is_text(path: Path) -> bool:
    ext = path.suffix.lstrip(".").lower()
    if ext in TEXT_EXTENSIONS:
        return True
    # Fallback: sniff first 8KB for null bytes (binary indicator)
    try:
        chunk = path.read_bytes()[:8192]
        return b"\x00" not in chunk
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def read_file(path: Path, encoding: str = "utf-8") -> str:
    try:
        return path.read_text(encoding=encoding, errors="replace")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="replace")


# ---------------------------------------------------------------------------
# Write / overwrite
# ---------------------------------------------------------------------------

def write_file(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding)


# ---------------------------------------------------------------------------
# Edit — find & replace (literal or regex)
# ---------------------------------------------------------------------------

def edit_file(
    path: Path,
    old_text: str,
    new_text: str,
    use_regex: bool = False,
    replace_all: bool = True,
) -> int:
    """Replace occurrences of old_text with new_text. Returns number of replacements made."""
    content = read_file(path)
    if use_regex:
        new_content, count = re.subn(old_text, new_text, content,
                                     count=0 if replace_all else 1)
    else:
        count = content.count(old_text) if replace_all else (1 if old_text in content else 0)
        if replace_all:
            new_content = content.replace(old_text, new_text)
        else:
            new_content = content.replace(old_text, new_text, 1)
    if count > 0:
        write_file(path, new_content)
    return count


# ---------------------------------------------------------------------------
# List directory
# ---------------------------------------------------------------------------

def list_directory(folder: Path, recursive: bool = False) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    pattern = "**/*" if recursive else "*"
    for p in sorted(folder.glob(pattern)):
        entry: dict[str, Any] = {
            "name":     p.name,
            "path":     str(p),
            "type":     "file" if p.is_file() else "directory",
        }
        if p.is_file():
            entry["size_bytes"] = p.stat().st_size
            entry["extension"]  = p.suffix.lstrip(".").lower()
            entry["readable"]   = _is_text(p)
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Search across files
# ---------------------------------------------------------------------------

def search_in_files(
    folder: Path,
    query: str,
    recursive: bool = True,
    use_regex: bool = False,
    file_pattern: str = "*",
    max_results: int = 200,
    timeout_s: float = 30.0,
    max_files_scanned: int = 50_000,
) -> dict[str, Any]:
    """Search for text across readable files. Hard-limited by timeout and file count."""
    results: list[dict[str, Any]] = []
    glob = f"**/{file_pattern}" if recursive else file_pattern
    deadline = time.monotonic() + timeout_s
    scanned = 0
    skipped_binary = 0
    timed_out = False

    for p in sorted(folder.glob(glob)):
        if time.monotonic() > deadline:
            timed_out = True
            logger.warning("search_in_files timed out after %.0fs scanning %s", timeout_s, folder)
            break
        if scanned >= max_files_scanned:
            timed_out = True
            logger.warning("search_in_files hit max_files_scanned=%d in %s", max_files_scanned, folder)
            break
        if not p.is_file():
            continue
        if not _is_text(p):
            skipped_binary += 1
            continue

        scanned += 1
        try:
            content = read_file(p)
        except OSError:
            continue

        matches: list[dict[str, Any]] = []
        for i, line in enumerate(content.splitlines(), 1):
            hit = (re.search(query, line) is not None) if use_regex else (query in line)
            if hit:
                matches.append({"line": i, "content": line.rstrip()})
                if len(matches) >= 50:
                    break
        if matches:
            results.append({"file": str(p), "matches": matches})
        if len(results) >= max_results:
            break

    return {
        "results":        results,
        "files_matched":  len(results),
        "files_scanned":  scanned,
        "timed_out":      timed_out,
    }


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_path(path: Path) -> str:
    if path.is_dir():
        shutil.rmtree(path)
        return "directory"
    else:
        path.unlink()
        return "file"


# ---------------------------------------------------------------------------
# Create directory
# ---------------------------------------------------------------------------

def create_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Move / rename
# ---------------------------------------------------------------------------

def move_path(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
