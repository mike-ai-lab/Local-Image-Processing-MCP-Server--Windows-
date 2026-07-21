"""Structured Rich logging + rotating file log for LocalImageAgent."""

from __future__ import annotations

import logging
import logging.handlers
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from rich.console import Console
from rich.logging import RichHandler

from config import config

console = Console(stderr=True)

LOG_FILE = Path(__file__).parent.parent / "agent.log"


def configure_logging() -> None:
    """Apply Rich console + rotating file logging. Call once at startup."""
    level = getattr(logging, config.log_level, logging.INFO)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,   # 5 MB per file
        backupCount=3,               # keep 3 rotated files
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(console=console, rich_tracebacks=True, markup=True),
            file_handler,
        ],
    )


logger = logging.getLogger("local-image-agent")


@contextmanager
def timed_operation(name: str) -> Generator[None, None, None]:
    logger.info("[START] %s", name)
    start = time.perf_counter()
    try:
        yield
    except Exception as exc:
        elapsed = time.perf_counter() - start
        logger.error("[FAIL]  %s  (%.3fs) — %s", name, elapsed, exc)
        raise
    else:
        elapsed = time.perf_counter() - start
        logger.info("[DONE]  %s  (%.3fs)", name, elapsed)
