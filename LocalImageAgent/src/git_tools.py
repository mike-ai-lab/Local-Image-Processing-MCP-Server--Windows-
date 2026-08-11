"""Git tools for LocalImageAgent MCP — wraps subprocess git calls with clean structured output."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("local-image-agent")

# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _git(args: list[str], repo: str, timeout: int = 30) -> dict[str, Any]:
    """Run a git command in *repo* and return structured output."""
    repo_path = Path(repo)
    if not repo_path.exists():
        return {"success": False, "error": f"Repository path does not exist: {repo}"}

    cmd = ["git", "-C", str(repo_path)] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip() or None,
            "stderr": result.stderr.strip() or None,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"git timed out after {timeout}s"}
    except FileNotFoundError:
        return {"success": False, "error": "git executable not found — is Git installed?"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# git_status
# ---------------------------------------------------------------------------

class GitStatusInput(BaseModel):
    repo: str = Field(..., description="Absolute path to the git repository root.")


def git_status(params: GitStatusInput) -> dict[str, Any]:
    result = _git(["status", "--short", "--branch"], params.repo)
    logger.info("git_status: %s → %s", params.repo, "ok" if result["success"] else "fail")
    return {**result, "repository": params.repo}


# ---------------------------------------------------------------------------
# git_add
# ---------------------------------------------------------------------------

class GitAddInput(BaseModel):
    repo: str = Field(..., description="Absolute path to the git repository root.")
    files: list[str] = Field(
        default=["."],
        description="List of files/patterns to stage. Defaults to '.' (all changes).",
    )


def git_add(params: GitAddInput) -> dict[str, Any]:
    result = _git(["add", "--"] + params.files, params.repo)
    logger.info("git_add: %s %s → %s", params.repo, params.files, "ok" if result["success"] else "fail")
    return {**result, "repository": params.repo, "staged": params.files}


# ---------------------------------------------------------------------------
# git_commit
# ---------------------------------------------------------------------------

class GitCommitInput(BaseModel):
    repo: str = Field(..., description="Absolute path to the git repository root.")
    message: str = Field(..., description="Commit message.")
    allow_empty: bool = Field(False, description="Allow committing with no staged changes.")


def git_commit(params: GitCommitInput) -> dict[str, Any]:
    args = ["commit", "-m", params.message]
    if params.allow_empty:
        args.append("--allow-empty")
    result = _git(args, params.repo)

    # Extract short commit hash if successful
    commit_hash = None
    if result["success"]:
        rev = _git(["rev-parse", "--short", "HEAD"], params.repo)
        commit_hash = rev.get("stdout")

    logger.info("git_commit: %s '%s' → %s", params.repo, params.message, commit_hash or "fail")
    return {**result, "repository": params.repo, "commit": commit_hash, "message": params.message}


# ---------------------------------------------------------------------------
# git_push
# ---------------------------------------------------------------------------

class GitPushInput(BaseModel):
    repo: str = Field(..., description="Absolute path to the git repository root.")
    remote: str = Field("origin", description="Remote name (default: origin).")
    branch: str | None = Field(None, description="Branch to push. Defaults to current branch.")
    set_upstream: bool = Field(False, description="Set upstream tracking (-u flag).")


def git_push(params: GitPushInput) -> dict[str, Any]:
    args = ["push"]
    if params.set_upstream:
        args.append("-u")
    args.append(params.remote)
    if params.branch:
        args.append(params.branch)
    result = _git(args, params.repo, timeout=60)
    logger.info("git_push: %s → %s → %s", params.repo, params.remote, "ok" if result["success"] else "fail")
    return {**result, "repository": params.repo, "remote": params.remote}


# ---------------------------------------------------------------------------
# git_pull
# ---------------------------------------------------------------------------

class GitPullInput(BaseModel):
    repo: str = Field(..., description="Absolute path to the git repository root.")
    remote: str = Field("origin", description="Remote name (default: origin).")
    branch: str | None = Field(None, description="Branch to pull. Defaults to current branch.")


def git_pull(params: GitPullInput) -> dict[str, Any]:
    args = ["pull", params.remote]
    if params.branch:
        args.append(params.branch)
    result = _git(args, params.repo, timeout=60)
    logger.info("git_pull: %s ← %s → %s", params.repo, params.remote, "ok" if result["success"] else "fail")
    return {**result, "repository": params.repo, "remote": params.remote}


# ---------------------------------------------------------------------------
# git_log
# ---------------------------------------------------------------------------

class GitLogInput(BaseModel):
    repo: str = Field(..., description="Absolute path to the git repository root.")
    n: int = Field(10, gt=0, le=200, description="Number of commits to return.")
    oneline: bool = Field(True, description="Use compact one-line format.")


def git_log(params: GitLogInput) -> dict[str, Any]:
    fmt = "--oneline" if params.oneline else "--format=%H|%an|%ae|%ad|%s"
    result = _git(["log", fmt, f"-{params.n}"], params.repo)
    commits: list[str] = []
    if result["success"] and result.get("stdout"):
        commits = result["stdout"].splitlines()
    return {**result, "repository": params.repo, "commits": commits, "count": len(commits)}


# ---------------------------------------------------------------------------
# git_diff
# ---------------------------------------------------------------------------

class GitDiffInput(BaseModel):
    repo: str = Field(..., description="Absolute path to the git repository root.")
    staged: bool = Field(False, description="Show staged diff (--cached) instead of working tree.")
    file: str | None = Field(None, description="Limit diff to a specific file.")


def git_diff(params: GitDiffInput) -> dict[str, Any]:
    args = ["diff"]
    if params.staged:
        args.append("--cached")
    if params.file:
        args += ["--", params.file]
    result = _git(args, params.repo)
    return {**result, "repository": params.repo, "staged": params.staged}


# ---------------------------------------------------------------------------
# git_checkout
# ---------------------------------------------------------------------------

class GitCheckoutInput(BaseModel):
    repo: str = Field(..., description="Absolute path to the git repository root.")
    branch: str = Field(..., description="Branch name to checkout.")
    create: bool = Field(False, description="Create the branch if it doesn't exist (-b).")


def git_checkout(params: GitCheckoutInput) -> dict[str, Any]:
    args = ["checkout"]
    if params.create:
        args.append("-b")
    args.append(params.branch)
    result = _git(args, params.repo)
    logger.info("git_checkout: %s → %s → %s", params.repo, params.branch, "ok" if result["success"] else "fail")
    return {**result, "repository": params.repo, "branch": params.branch}


# ---------------------------------------------------------------------------
# git_publish_file  (add + commit + push in one call)
# ---------------------------------------------------------------------------

class GitPublishFileInput(BaseModel):
    repo: str = Field(..., description="Absolute path to the git repository root.")
    file: str = Field(..., description="File path relative to the repo root to stage and publish.")
    message: str = Field(..., description="Commit message.")
    remote: str = Field("origin", description="Remote to push to.")
    branch: str | None = Field(None, description="Branch to push. Defaults to current branch.")


def git_publish_file(params: GitPublishFileInput) -> dict[str, Any]:
    """Validate → add → commit → push in one atomic call."""
    repo_path = Path(params.repo)
    file_path = repo_path / params.file

    # Validate file exists
    if not file_path.exists():
        return {
            "success": False,
            "repository": params.repo,
            "file": params.file,
            "error": f"File not found: {file_path}",
            "step_failed": "validation",
        }

    # git add
    add = _git(["add", "--", params.file], params.repo)
    if not add["success"]:
        return {**add, "repository": params.repo, "file": params.file, "step_failed": "add"}

    # git commit
    commit_args = ["commit", "-m", params.message]
    commit = _git(commit_args, params.repo)
    if not commit["success"]:
        # Nothing to commit is not really a failure — detect it
        stderr = commit.get("stderr") or ""
        stdout = commit.get("stdout") or ""
        if "nothing to commit" in stdout or "nothing to commit" in stderr:
            return {
                "success": False,
                "repository": params.repo,
                "file": params.file,
                "message": params.message,
                "commit": None,
                "pushed": False,
                "note": "Nothing to commit — file may already be committed.",
                "step_failed": "commit",
            }
        return {**commit, "repository": params.repo, "file": params.file, "step_failed": "commit"}

    # Extract commit hash
    rev = _git(["rev-parse", "--short", "HEAD"], params.repo)
    commit_hash = rev.get("stdout")

    # git push
    push_args = ["push", params.remote]
    if params.branch:
        push_args.append(params.branch)
    push = _git(push_args, params.repo, timeout=60)
    if not push["success"]:
        return {
            **push,
            "repository": params.repo,
            "file": params.file,
            "commit": commit_hash,
            "pushed": False,
            "step_failed": "push",
        }

    logger.info("git_publish_file: %s/%s → committed %s → pushed ok", params.repo, params.file, commit_hash)
    return {
        "success": True,
        "repository": params.repo,
        "file": params.file,
        "message": params.message,
        "commit": commit_hash,
        "pushed": True,
        "remote": params.remote,
    }
