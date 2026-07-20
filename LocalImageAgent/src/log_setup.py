"""Structured Rich logging for LocalImageAgent."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Generator

from rich.console import Console
from rich.logging import RichHandler

from config import config


console = Console(stderr=True)


def configure_logging() -> None:
    """Apply Rich logging configuration. Must be called once at startup."""
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True)],
    )


logger = logging.getLogger("local-image-agent")


@contextmanager
def timed_operation(name: str) -> Generator[None, None, None]:
    """Log the duration of a block of code."""
    logger.info("Starting: %s", name)
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        logger.info("Completed: %s in %.3fs", name, elapsed)
