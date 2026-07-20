"""
Core functionality tests for LocalImageAgent.
Tests: ImageMagick detection, compress, resize, convert, image_info.
Requires ImageMagick installed and a real Python image to be created via Pillow.
"""

from __future__ import annotations

import json
import sys
import os
from pathlib import Path

import pytest

# Ensure src/ is on the path
SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture(scope="session")
def tmp_images(tmp_path_factory) -> Path:
    """Create a small test image directory with one PNG."""
    from PIL import Image

    folder = tmp_path_factory.mktemp("images")
    img = Image.new("RGB", (800, 600), color=(100, 149, 237))
    img.save(folder / "test.png")
    img.save(folder / "test.jpg", quality=90)
    return folder


# ------------------------------------------------------------------
# 1. ImageMagick detection
# ------------------------------------------------------------------

class TestImageMagickDetection:
    def test_magick_resolves(self):
        from imagemagick import _get_magick
        path = _get_magick()
        assert path, "magick path should be non-empty"
        assert Path(path).exists() or path == "magick", f"Expected valid path, got: {path}"

    def test_run_magick_version(self):
        from imagemagick import run_magick
        result = run_magick(["-version"])
        assert result.returncode == 0
        assert "ImageMagick" in result.stdout or "ImageMagick" in result.stderr


# ------------------------------------------------------------------
# 2. Compress image
# ------------------------------------------------------------------

class TestCompressImage:
    def test_compress_basic(self, tmp_images, tmp_path):
        from process import compress_image
        src = tmp_images / "test.png"
        dst = tmp_path / "compressed.png"
        compress_image(src, dst, quality=75)
        assert dst.exists()
        assert dst.stat().st_size > 0

    def test_compress_with_max_size(self, tmp_images, tmp_path):
        from process import compress_image
        src = tmp_images / "test.jpg"
        dst = tmp_path / "compressed_maxsize.jpg"
        # 50 KB target
        compress_image(src, dst, quality=85, max_size_bytes=50 * 1024)
        assert dst.exists()
        # Allow 10% overage only if image cannot compress further
        assert dst.stat().st_size <= 50 * 1024 * 1.1

    def test_compress_reduces_size(self, tmp_images, tmp_path):
        from process import compress_image
        src = tmp_images / "test.jpg"
        dst = tmp_path / "compressed_q10.jpg"
        compress_image(src, dst, quality=10)
        assert dst.stat().st_size < src.stat().st_size


# ------------------------------------------------------------------
# 3. Resize image
# ------------------------------------------------------------------

class TestResizeImage:
    def test_resize_fit_width(self, tmp_images, tmp_path):
        from process import resize_image
        src = tmp_images / "test.png"
        dst = tmp_path / "resized_fit.png"
        resize_image(src, dst, width=400, height=None, mode="fit")
        assert dst.exists()
        _assert_dimensions(dst, max_width=400)

    def test_resize_exact(self, tmp_images, tmp_path):
        from process import resize_image
        src = tmp_images / "test.png"
        dst = tmp_path / "resized_exact.png"
        resize_image(src, dst, width=200, height=150, mode="exact")
        assert dst.exists()
        _assert_exact_dimensions(dst, 200, 150)

    def test_resize_fill(self, tmp_images, tmp_path):
        from process import resize_image
        src = tmp_images / "test.png"
        dst = tmp_path / "resized_fill.png"
        resize_image(src, dst, width=300, height=300, mode="fill")
        assert dst.exists()


# ------------------------------------------------------------------
# 4. Convert image
# ------------------------------------------------------------------

class TestConvertImage:
    def test_png_to_jpg(self, tmp_images, tmp_path):
        from process import convert_image
        src = tmp_images / "test.png"
        dst = tmp_path / "converted.jpg"
        convert_image(src, dst)
        assert dst.exists()
        assert dst.stat().st_size > 0

    def test_jpg_to_webp(self, tmp_images, tmp_path):
        from process import convert_image
        src = tmp_images / "test.jpg"
        dst = tmp_path / "converted.webp"
        convert_image(src, dst)
        assert dst.exists()
        assert dst.stat().st_size > 0

    def test_png_to_bmp(self, tmp_images, tmp_path):
        from process import convert_image
        src = tmp_images / "test.png"
        dst = tmp_path / "converted.bmp"
        convert_image(src, dst)
        assert dst.exists()


# ------------------------------------------------------------------
# 5. Image info
# ------------------------------------------------------------------

class TestImageInfo:
    def test_info_fields_present(self, tmp_images):
        from process import get_image_info
        info = get_image_info(tmp_images / "test.png")
        assert "file" in info
        assert "file_size_bytes" in info
        assert info["file_size_bytes"] > 0
        assert "geometry" in info
        assert "format" in info
        assert "colorspace" in info

    def test_info_geometry_contains_dimensions(self, tmp_images):
        from process import get_image_info
        info = get_image_info(tmp_images / "test.png")
        # geometry is like "800x600+0+0"
        assert "800" in info["geometry"]
        assert "600" in info["geometry"]


# ------------------------------------------------------------------
# 6. Validation
# ------------------------------------------------------------------

class TestValidation:
    def test_missing_file_raises(self):
        from validation import validate_input_file, ValidationError
        with pytest.raises(ValidationError, match="not found"):
            validate_input_file("nonexistent_file.png")

    def test_unsupported_input_format_raises(self, tmp_path):
        from validation import validate_input_file, ValidationError
        bad = tmp_path / "file.xyz"
        bad.write_bytes(b"data")
        with pytest.raises(ValidationError, match="Unsupported input format"):
            validate_input_file(str(bad))

    def test_unsupported_output_format_raises(self):
        from validation import validate_output_file, ValidationError
        with pytest.raises(ValidationError, match="Unsupported output format"):
            validate_output_file("out.xyz")

    def test_quality_out_of_range_raises(self):
        from validation import validate_quality, ValidationError
        with pytest.raises(ValidationError):
            validate_quality(0)
        with pytest.raises(ValidationError):
            validate_quality(101)

    def test_no_dimensions_raises(self):
        from validation import validate_dimensions, ValidationError
        with pytest.raises(ValidationError, match="At least one"):
            validate_dimensions(None, None)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _assert_dimensions(path: Path, max_width: int) -> None:
    from PIL import Image
    with Image.open(path) as img:
        assert img.width <= max_width, f"Expected width <= {max_width}, got {img.width}"


def _assert_exact_dimensions(path: Path, width: int, height: int) -> None:
    from PIL import Image
    with Image.open(path) as img:
        assert img.width == width, f"Expected width {width}, got {img.width}"
        assert img.height == height, f"Expected height {height}, got {img.height}"
