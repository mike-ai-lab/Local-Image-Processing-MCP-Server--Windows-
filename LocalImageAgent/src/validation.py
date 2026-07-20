"""Input validation helpers."""

from __future__ import annotations

from pathlib import Path

from config import SUPPORTED_INPUT_FORMATS, SUPPORTED_OUTPUT_FORMATS


class ValidationError(ValueError):
    """Raised when user-supplied parameters are invalid."""


def validate_input_file(path: str) -> Path:
    p = Path(path)
    if not p.exists():
        raise ValidationError(f"Input file not found: {path}")
    if not p.is_file():
        raise ValidationError(f"Path is not a file: {path}")
    ext = p.suffix.lstrip(".").lower()
    if ext not in SUPPORTED_INPUT_FORMATS:
        raise ValidationError(
            f"Unsupported input format '.{ext}'. Supported: {sorted(SUPPORTED_INPUT_FORMATS)}"
        )
    return p


def validate_input_folder(path: str) -> Path:
    p = Path(path)
    if not p.exists():
        raise ValidationError(f"Folder not found: {path}")
    if not p.is_dir():
        raise ValidationError(f"Path is not a directory: {path}")
    return p


def validate_output_format(fmt: str) -> str:
    clean = fmt.lstrip(".").lower()
    if clean not in SUPPORTED_OUTPUT_FORMATS:
        raise ValidationError(
            f"Unsupported output format '.{clean}'. Supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    return clean


def validate_output_file(path: str) -> Path:
    p = Path(path)
    ext = p.suffix.lstrip(".").lower()
    if ext not in SUPPORTED_OUTPUT_FORMATS:
        raise ValidationError(
            f"Unsupported output format '.{ext}'. Supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def validate_quality(quality: int | None) -> int | None:
    if quality is None:
        return None
    if not (1 <= quality <= 100):
        raise ValidationError("Quality must be between 1 and 100.")
    return quality


def validate_max_size_bytes(max_size_kb: int | None) -> int | None:
    if max_size_kb is None:
        return None
    if max_size_kb <= 0:
        raise ValidationError("max_size_kb must be a positive integer.")
    return max_size_kb * 1024


def validate_dimensions(width: int | None, height: int | None) -> tuple[int | None, int | None]:
    for name, val in [("width", width), ("height", height)]:
        if val is not None and val <= 0:
            raise ValidationError(f"{name} must be a positive integer.")
    if width is None and height is None:
        raise ValidationError("At least one of width or height must be provided.")
    return width, height


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
