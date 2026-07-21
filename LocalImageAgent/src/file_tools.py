"""MCP tool definitions — File system read/write/edit."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

import file_process as fp
import validation as val
from log_setup import timed_operation

logger = logging.getLogger("local-image-agent")


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

class ReadFileInput(BaseModel):
    path: str = Field(..., description="Absolute path to the file to read.")
    start_line: int | None = Field(None, ge=1, description="First line to return (1-based). Optional.")
    end_line:   int | None = Field(None, ge=1, description="Last line to return (1-based). Optional.")


def read_file(params: ReadFileInput) -> dict[str, Any]:
    """Read a text file and return its content. Optionally limit to a line range."""
    with timed_operation(f"read_file {params.path}"):
        p = Path(params.path)
        if not p.exists():
            raise val.ValidationError(f"File not found: {params.path}")
        if not p.is_file():
            raise val.ValidationError(f"Path is not a file: {params.path}")
        if not fp._is_text(p):
            raise val.ValidationError(f"File does not appear to be readable text: {params.path}")
        content = fp.read_file(p)
        lines = content.splitlines()
        total_lines = len(lines)
        if params.start_line or params.end_line:
            s = (params.start_line or 1) - 1
            e = params.end_line or total_lines
            lines = lines[s:e]
            content = "\n".join(lines)
        return {"path": str(p), "content": content, "total_lines": total_lines, "size_bytes": p.stat().st_size}


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

class WriteFileInput(BaseModel):
    path:    str = Field(..., description="Absolute path to write. Created if it does not exist.")
    content: str = Field(..., description="Full text content to write.")
    overwrite: bool = Field(True, description="If false, raises an error if the file already exists.")


def write_file(params: WriteFileInput) -> dict[str, Any]:
    """Write (or overwrite) a text file with the given content."""
    with timed_operation(f"write_file {params.path}"):
        p = Path(params.path)
        if not params.overwrite and p.exists():
            raise val.ValidationError(f"File already exists and overwrite=false: {params.path}")
        fp.write_file(p, params.content)
        return {"path": str(p), "size_bytes": p.stat().st_size, "status": "written"}


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------

class EditFileInput(BaseModel):
    path:        str  = Field(..., description="Absolute path to the file to edit.")
    old_text:    str  = Field(..., description="Text to find (literal string or regex pattern).")
    new_text:    str  = Field(..., description="Replacement text.")
    use_regex:   bool = Field(False, description="Treat old_text as a regular expression.")
    replace_all: bool = Field(True,  description="Replace all occurrences. If false, only replaces the first.")


def edit_file(params: EditFileInput) -> dict[str, Any]:
    """Find and replace text in a file."""
    p = Path(params.path)
    if not p.exists():
        raise val.ValidationError(f"File not found: {params.path}")
    count = fp.edit_file(p, params.old_text, params.new_text,
                         use_regex=params.use_regex, replace_all=params.replace_all)
    return {
        "path":          str(p),
        "replacements":  count,
        "status":        "edited" if count > 0 else "no_match",
    }


# ---------------------------------------------------------------------------
# list_directory
# ---------------------------------------------------------------------------

class ListDirectoryInput(BaseModel):
    path:      str  = Field(..., description="Absolute path to the folder to list.")
    recursive: bool = Field(False, description="List all files and subfolders recursively.")


def list_directory(params: ListDirectoryInput) -> dict[str, Any]:
    """List files and folders in a directory."""
    p = Path(params.path)
    if not p.exists():
        raise val.ValidationError(f"Folder not found: {params.path}")
    if not p.is_dir():
        raise val.ValidationError(f"Path is not a directory: {params.path}")
    entries = fp.list_directory(p, recursive=params.recursive)
    return {
        "path":    str(p),
        "count":   len(entries),
        "entries": entries,
    }


# ---------------------------------------------------------------------------
# search_files
# ---------------------------------------------------------------------------

class SearchFilesInput(BaseModel):
    folder:            str   = Field(..., description="Absolute path to the folder to search in.")
    query:             str   = Field(..., description="Text or regex pattern to search for.")
    recursive:         bool  = Field(True,  description="Search subfolders recursively.")
    use_regex:         bool  = Field(False, description="Treat query as a regular expression.")
    file_pattern:      str   = Field("*",   description="Glob pattern to filter files, e.g. '*.py' or '*.skb'.")
    timeout_s:         float = Field(25.0,  gt=0, description="Max seconds to spend searching. Default 25.")
    max_files_scanned: int   = Field(50000, gt=0, description="Max number of files to scan.")


def search_files(params: SearchFilesInput) -> dict[str, Any]:
    """Search for text across all readable files in a folder. Returns matches with file path and line numbers."""
    with timed_operation(f"search_files {params.folder} query={params.query!r} pattern={params.file_pattern}"):
        p = Path(params.folder)
        if not p.exists():
            raise val.ValidationError(f"Folder not found: {params.folder}")
        data = fp.search_in_files(
            p, params.query,
            recursive=params.recursive,
            use_regex=params.use_regex,
            file_pattern=params.file_pattern,
            timeout_s=params.timeout_s,
            max_files_scanned=params.max_files_scanned,
        )
        return {
            "query":          params.query,
            "folder":         str(p),
            "files_matched":  data["files_matched"],
            "files_scanned":  data["files_scanned"],
            "timed_out":      data["timed_out"],
            "results":        data["results"],
        }


# ---------------------------------------------------------------------------
# delete_file
# ---------------------------------------------------------------------------

class DeletePathInput(BaseModel):
    path:    str  = Field(..., description="Absolute path to the file or folder to delete.")
    confirm: bool = Field(..., description="Must be true to proceed. Safety guard.")


def delete_path(params: DeletePathInput) -> dict[str, Any]:
    """Delete a file or folder. confirm must be true."""
    if not params.confirm:
        raise val.ValidationError("deletion requires confirm=true.")
    p = Path(params.path)
    if not p.exists():
        raise val.ValidationError(f"Path not found: {params.path}")
    kind = fp.delete_path(p)
    return {"path": str(p), "deleted": kind}


# ---------------------------------------------------------------------------
# create_directory
# ---------------------------------------------------------------------------

class CreateDirectoryInput(BaseModel):
    path: str = Field(..., description="Absolute path of the directory to create.")


def create_directory(params: CreateDirectoryInput) -> dict[str, Any]:
    """Create a directory (and any missing parents)."""
    p = Path(params.path)
    fp.create_directory(p)
    return {"path": str(p), "status": "created"}


# ---------------------------------------------------------------------------
# move_path
# ---------------------------------------------------------------------------

class MovePathInput(BaseModel):
    source:      str = Field(..., description="Absolute path of the file or folder to move/rename.")
    destination: str = Field(..., description="Absolute destination path.")


def move_path(params: MovePathInput) -> dict[str, Any]:
    """Move or rename a file or folder."""
    src = Path(params.source)
    dst = Path(params.destination)
    if not src.exists():
        raise val.ValidationError(f"Source not found: {params.source}")
    fp.move_path(src, dst)
    return {"source": str(src), "destination": str(dst), "status": "moved"}


# ---------------------------------------------------------------------------
# find_files  (fast filename search — no content scanning)
# ---------------------------------------------------------------------------

class FindFilesInput(BaseModel):
    folder:     str   = Field(...,    description="Root folder to search from.")
    name:       str   = Field(...,    description="Filename or partial name to match (case-insensitive, supports * wildcard).")
    recursive:  bool  = Field(True,   description="Search subfolders.")
    timeout_s:  float = Field(30.0,   gt=0, description="Max seconds. Default 30.")
    max_results: int  = Field(100,    gt=0)


def find_files(params: FindFilesInput) -> dict[str, Any]:
    """
    Find files by name (not content). Fast — only compares filenames, no file reading.
    Use this to locate files by name, e.g. find all .skb files containing a project name.
    """
    import fnmatch, time as _time

    root = Path(params.folder)
    if not root.exists():
        raise val.ValidationError(f"Folder not found: {params.folder}")

    pattern = f"*{params.name}*" if "*" not in params.name else params.name
    found: list[dict[str, Any]] = []
    deadline = _time.monotonic() + params.timeout_s
    timed_out = False
    dirs_scanned = 0

    with timed_operation(f"find_files {params.folder} name={params.name!r}"):
        if params.recursive:
            for dirpath, dirnames, filenames in os.walk(root):
                if _time.monotonic() > deadline:
                    timed_out = True
                    break
                dirs_scanned += 1
                # Skip hidden/system folders to avoid wasted time
                dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in
                               ("$Recycle.Bin", "Windows", "System32", "SysWOW64", "WinSxS")]
                for fn in filenames:
                    if fnmatch.fnmatch(fn.lower(), pattern.lower()):
                        p = Path(dirpath) / fn
                        try:
                            stat = p.stat()
                            found.append({
                                "path":          str(p),
                                "name":          fn,
                                "size_bytes":    stat.st_size,
                                "size_mb":       round(stat.st_size / 1024 / 1024, 3),
                                "modified":      time.strftime(
                                    "%Y-%m-%d %H:%M:%S",
                                    time.localtime(stat.st_mtime)
                                ),
                            })
                        except OSError:
                            pass
                        if len(found) >= params.max_results:
                            break
                if len(found) >= params.max_results:
                    break
        else:
            for p in root.iterdir():
                if p.is_file() and fnmatch.fnmatch(p.name.lower(), pattern.lower()):
                    try:
                        stat = p.stat()
                        found.append({
                            "path":       str(p),
                            "name":       p.name,
                            "size_bytes": stat.st_size,
                            "size_mb":    round(stat.st_size / 1024 / 1024, 3),
                            "modified":   time.strftime(
                                "%Y-%m-%d %H:%M:%S",
                                time.localtime(stat.st_mtime)
                            ),
                        })
                    except OSError:
                        pass

    return {
        "pattern":      pattern,
        "folder":       str(root),
        "found":        len(found),
        "timed_out":    timed_out,
        "dirs_scanned": dirs_scanned,
        "files":        found,
    }
