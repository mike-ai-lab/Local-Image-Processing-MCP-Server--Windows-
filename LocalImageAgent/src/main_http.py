"""LocalImageAgent MCP Server — Streamable HTTP transport for ChatGPT Desktop."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from log_setup import configure_logging
configure_logging()

import logging
from fastmcp import FastMCP
from config import config

logger = logging.getLogger("local-image-agent")

mcp = FastMCP(
    name=config.server_name,
    version=config.server_version,
)

import tools as _tools


@mcp.tool()
def compress_image(input_file: str, output_file: str, quality: int | None = None, max_size_kb: int | None = None) -> dict:
    """Compress a single image, optionally targeting a maximum file size (in KB)."""
    return _tools.compress_image(_tools.CompressImageInput(input_file=input_file, output_file=output_file, quality=quality, max_size_kb=max_size_kb))

@mcp.tool()
def compress_folder(input_folder: str, output_folder: str | None = None, recursive: bool = False, overwrite: bool = True, quality: int | None = None, max_size_kb: int | None = None) -> dict:
    """Compress all images in a folder."""
    return _tools.compress_folder(_tools.CompressFolderInput(input_folder=input_folder, output_folder=output_folder, recursive=recursive, overwrite=overwrite, quality=quality, max_size_kb=max_size_kb))

@mcp.tool()
def resize_image(input_file: str, output_file: str, width: int | None = None, height: int | None = None, mode: str = "fit") -> dict:
    """Resize a single image. mode: fit | fill | exact."""
    return _tools.resize_image(_tools.ResizeImageInput(input_file=input_file, output_file=output_file, width=width, height=height, mode=mode))

@mcp.tool()
def batch_resize(input_folder: str, output_folder: str | None = None, width: int | None = None, height: int | None = None, mode: str = "fit", recursive: bool = False, overwrite: bool = True) -> dict:
    """Resize all images in a folder."""
    return _tools.batch_resize(_tools.BatchResizeInput(input_folder=input_folder, output_folder=output_folder, width=width, height=height, mode=mode, recursive=recursive, overwrite=overwrite))

@mcp.tool()
def convert_image(input_file: str, output_file: str) -> dict:
    """Convert an image to another format. Target format is inferred from output_file extension."""
    return _tools.convert_image(_tools.ConvertImageInput(input_file=input_file, output_file=output_file))

@mcp.tool()
def batch_convert(input_folder: str, output_folder: str, output_format: str, recursive: bool = False, overwrite: bool = True) -> dict:
    """Convert all images in a folder to the specified format."""
    return _tools.batch_convert(_tools.BatchConvertInput(input_folder=input_folder, output_folder=output_folder, output_format=output_format, recursive=recursive, overwrite=overwrite))

@mcp.tool()
def strip_metadata(input_file: str, output_file: str) -> dict:
    """Remove EXIF and other metadata from an image."""
    return _tools.strip_metadata(_tools.StripMetadataInput(input_file=input_file, output_file=output_file))

@mcp.tool()
def image_info(input_file: str) -> dict:
    """Return detailed information about an image file."""
    return _tools.image_info(_tools.ImageInfoInput(input_file=input_file))

@mcp.tool()
def create_thumbnail(input_file: str, output_file: str, width: int = 256, height: int = 256) -> dict:
    """Generate a thumbnail preserving aspect ratio."""
    return _tools.create_thumbnail(_tools.CreateThumbnailInput(input_file=input_file, output_file=output_file, width=width, height=height))


if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 8765
    logger.info("Starting %s v%s", config.server_name, config.server_version)
    logger.info("Local endpoint: http://%s:%d/mcp", HOST, PORT)
    logger.info("ChatGPT URL (via ngrok): https://<ngrok-host>/mcp")
    mcp.run(
        transport="streamable-http",
        host=HOST,
        port=PORT,
        path="/mcp",
    )
