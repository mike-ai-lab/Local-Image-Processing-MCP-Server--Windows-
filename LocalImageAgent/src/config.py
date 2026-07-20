"""Configuration loader for LocalImageAgent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator


CONFIG_PATH = Path(__file__).parent.parent / "config.json"

SUPPORTED_INPUT_FORMATS = frozenset(["jpg", "jpeg", "png", "tiff", "bmp", "gif", "webp", "avif"])
SUPPORTED_OUTPUT_FORMATS = frozenset(["jpg", "png", "tiff", "bmp", "webp", "avif"])


class AppConfig(BaseModel):
    imagemagick_path: str = ""
    magick_exe: str = "magick"
    server_name: str = "local-image-agent"
    server_version: str = "1.0.0"
    log_level: str = "INFO"
    supported_input_formats: list[str] = list(SUPPORTED_INPUT_FORMATS)
    supported_output_formats: list[str] = list(SUPPORTED_OUTPUT_FORMATS)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper


def load_config() -> AppConfig:
    """Load config from config.json, falling back to defaults."""
    if CONFIG_PATH.exists():
        raw: dict[str, Any] = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        return AppConfig(**raw)
    return AppConfig()


config: AppConfig = load_config()
