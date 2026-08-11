"""LocalImageAgent MCP Server — Streamable HTTP transport for ChatGPT Desktop."""

from __future__ import annotations

import sys
import subprocess
import urllib.request
import json as _json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from log_setup import configure_logging
configure_logging()

import logging
from fastmcp import FastMCP
from config import config

logger = logging.getLogger("local-image-agent")


def _get_ngrok_url() -> str:
    """Read the active ngrok public URL from the local ngrok API (port 4040).
    Falls back to placeholder if ngrok is not running."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2) as resp:
            data = _json.loads(resp.read())
            for tunnel in data.get("tunnels", []):
                url = tunnel.get("public_url", "")
                if url.startswith("https://"):
                    return url
    except Exception:
        pass
    return "https://<ngrok not running>"

import time as _time

mcp = FastMCP(
    name=config.server_name,
    version=config.server_version,
)

import tools as _tools
import video_tools as _vtools
import file_tools as _ftools
import vision_tools as _vision
import sketchup_tools as _su
import screen_tools as _screen
import system_tools as _sys
import git_tools as _git_tools
from sketchup_bridge import run_ruby_json, run_ruby, send_named_command, SketchUpNotRunning, SketchUpError


# ---------------------------------------------------------------------------
# Image tools
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Video tools
# ---------------------------------------------------------------------------

@mcp.tool()
def video_info(input_file: str) -> dict:
    """Return codec, resolution, fps, duration, bitrate and other metadata for a video file."""
    return _vtools.video_info(_vtools.VideoInfoInput(input_file=input_file))

@mcp.tool()
def video_pipeline(input_file: str, output_file: str, steps: list[dict]) -> dict:
    """
    Run multiple video processing operations as a single transaction.
    Steps run in order. Each step: {"op": "trim|compress|strip_metadata|speed|social", ...params}
    trim: start, end  |  compress: max_size_mb, crf, preset  |  speed: speed, interpolate_frames, sharpen  |  social: platform
    """
    return _vtools.video_pipeline(_vtools.VideoPipelineInput(input_file=input_file, output_file=output_file, steps=steps))

@mcp.tool()
def compress_video(input_file: str, output_file: str, max_size_mb: float | None = None, crf: int = 23, preset: str = "medium", audio_bitrate_kbps: int = 128) -> dict:
    """Compress a video. Optionally target a maximum file size in MB using bitrate binary search."""
    return _vtools.compress_video(_vtools.CompressVideoInput(input_file=input_file, output_file=output_file, max_size_mb=max_size_mb, crf=crf, preset=preset, audio_bitrate_kbps=audio_bitrate_kbps))

@mcp.tool()
def trim_video(input_file: str, output_file: str, start: str, end: str) -> dict:
    """Trim a video to a time range. start/end accept HH:MM:SS, MM:SS, or plain seconds."""
    return _vtools.trim_video(_vtools.TrimVideoInput(input_file=input_file, output_file=output_file, start=start, end=end))

@mcp.tool()
def strip_video_metadata(input_file: str, output_file: str) -> dict:
    """Remove all metadata from a video file."""
    return _vtools.strip_video_metadata(_vtools.StripVideoMetadataInput(input_file=input_file, output_file=output_file))

@mcp.tool()
def adjust_video(input_file: str, output_file: str, speed: float = 1.0, interpolate_frames: bool = False, sharpen: float = 0.0) -> dict:
    """Change video speed, add frame interpolation for smooth motion, and/or sharpen. speed: multiplier (3.0 = 3x faster)."""
    return _vtools.adjust_video(_vtools.AdjustVideoInput(input_file=input_file, output_file=output_file, speed=speed, interpolate_frames=interpolate_frames, sharpen=sharpen))

@mcp.tool()
def optimize_for_social(input_file: str, output_file: str, platform: str = "instagram") -> dict:
    """Re-encode a video optimised for a social media platform: instagram, tiktok, youtube, twitter, facebook, linkedin."""
    return _vtools.optimize_for_social(_vtools.OptimizeSocialInput(input_file=input_file, output_file=output_file, platform=platform))

@mcp.tool()
def batch_optimize_social(input_folder: str, output_folder: str, platform: str = "instagram", recursive: bool = False, overwrite: bool = True) -> dict:
    """Optimise all videos in a folder for a social media platform."""
    return _vtools.batch_optimize_social(_vtools.BatchOptimizeSocialInput(input_folder=input_folder, output_folder=output_folder, platform=platform, recursive=recursive, overwrite=overwrite))


# ---------------------------------------------------------------------------
# File tools
# ---------------------------------------------------------------------------

@mcp.tool()
def read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> dict:
    """Read a local text file. Optionally limit to a line range."""
    return _ftools.read_file(_ftools.ReadFileInput(path=path, start_line=start_line, end_line=end_line))

@mcp.tool()
def write_file(path: str, content: str, overwrite: bool = True) -> dict:
    """Write content to a local file. Creates the file and any missing parent folders."""
    return _ftools.write_file(_ftools.WriteFileInput(path=path, content=content, overwrite=overwrite))

@mcp.tool()
def edit_file(path: str, old_text: str, new_text: str, use_regex: bool = False, replace_all: bool = True) -> dict:
    """Find and replace text inside a local file."""
    return _ftools.edit_file(_ftools.EditFileInput(path=path, old_text=old_text, new_text=new_text, use_regex=use_regex, replace_all=replace_all))

@mcp.tool()
def list_directory(path: str, recursive: bool = False) -> dict:
    """List files and folders in a local directory."""
    return _ftools.list_directory(_ftools.ListDirectoryInput(path=path, recursive=recursive))

@mcp.tool()
def search_files(folder: str, query: str, recursive: bool = True, use_regex: bool = False, file_pattern: str = "*", timeout_s: float = 25.0, max_files_scanned: int = 50000) -> dict:
    """
    Search for text across all readable files in a folder.
    Use file_pattern to narrow scope (e.g. '*.py', '*.skb') for much faster searches.
    timeout_s and max_files_scanned prevent runaway scans on large drives.
    """
    return _ftools.search_files(_ftools.SearchFilesInput(folder=folder, query=query, recursive=recursive, use_regex=use_regex, file_pattern=file_pattern, timeout_s=timeout_s, max_files_scanned=max_files_scanned))

@mcp.tool()
def delete_path(path: str, confirm: bool = False) -> dict:
    """Delete a file or folder. confirm must be true."""
    return _ftools.delete_path(_ftools.DeletePathInput(path=path, confirm=confirm))

@mcp.tool()
def create_directory(path: str) -> dict:
    """Create a directory and any missing parent folders."""
    return _ftools.create_directory(_ftools.CreateDirectoryInput(path=path))

@mcp.tool()
def move_path(source: str, destination: str) -> dict:
    """Move or rename a file or folder."""
    return _ftools.move_path(_ftools.MovePathInput(source=source, destination=destination))

@mcp.tool()
def find_files(folder: str, name: str, recursive: bool = True, timeout_s: float = 30.0, max_results: int = 100) -> dict:
    """
    Find files by name on the local machine. Fast — only matches filenames, no file reading.
    name supports partial matches and * wildcards, e.g. 'STC-CRYSTAL*' or '*.skb'.
    Skips system folders automatically. Use this instead of search_files for finding files by name.
    """
    return _ftools.find_files(_ftools.FindFilesInput(folder=folder, name=name, recursive=recursive, timeout_s=timeout_s, max_results=max_results))


# ---------------------------------------------------------------------------
# ImageMagick raw command tool
# ---------------------------------------------------------------------------

@mcp.tool()
def magick(args: list[str]) -> dict:
    """
    ALWAYS CALL THIS TOOL for any image processing request. NEVER say you cannot access a
    local file path, cannot run ImageMagick, or suggest the user run commands themselves.
    The MCP server runs on the user's local Windows machine and executes magick directly.
    Any Windows path works — spaces, parentheses, UUIDs, anything.

    Pass the full magick argument list. The server prepends the magick executable automatically.

    Common patterns (replace paths as needed):
      Denoise:       ["C:/path/img.png", "-noise", "2", "C:/path/img_denoised.png"]
      Sharpen:       ["C:/path/img.png", "-unsharp", "0x1+1+0.05", "C:/path/img_sharp.png"]
      Enhance:       ["C:/path/img.png", "-enhance", "-normalize", "C:/path/img_enhanced.png"]
      Convert fmt:   ["C:/path/img.png", "C:/path/img.webp"]
      Identify:      ["identify", "-verbose", "C:/path/img.png"]
      Any operation: any valid magick argument sequence — no restrictions whatsoever

    Use forward slashes or escaped backslashes in paths.
    Returns exit_code, stdout, stderr. exit_code 0 = success.
    """
    import shlex
    from imagemagick import _get_magick, ImageMagickError
    from log_setup import timed_operation

    cmd = [_get_magick()] + [str(a) for a in args]
    display = "magick " + " ".join(shlex.quote(str(a)) for a in args)
    logger.info("magick: %s", display)

    with timed_operation(f"magick {args[0] if args else ''}"):
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    return {
        "command":   display,
        "exit_code": result.returncode,
        "stdout":    result.stdout.strip() or None,
        "stderr":    result.stderr.strip() or None,
        "status":    "ok" if result.returncode == 0 else "error",
    }


# ---------------------------------------------------------------------------
# Vision tools
# ---------------------------------------------------------------------------

@mcp.tool()
def read_image_for_vision(path: str, size: int = 512, quality: int = 80) -> dict:
    """
    READ a single local image file and return it as base64 for visual inspection or analysis.
    NEVER say a local file path is inaccessible — the MCP server runs on the user's machine
    and can read any local path. Always call this tool when the user provides a file path.
    Use read_image_for_generation instead when the user wants to generate a variation.
    Default 512px / quality 80 keeps the payload small (~20-40 KB) so follow-up tool calls
    (like sketchup_ruby) can run in the same turn without hitting token limits.
    """
    return _vision.read_image_for_vision(_vision.ReadImageForVisionInput(path=path, size=size, quality=quality))

@mcp.tool()
def read_image_for_generation(path: str, target_kb: int = 450, max_dimension: int = 1920) -> dict:
    """
    USE THIS TOOL whenever the user provides a local file path to an image and wants to see,
    analyze, or generate a variation of it.

    NEVER say "the file is not accessible" or ask the user to upload manually.
    The MCP server runs on the user's local machine and reads any local path directly.

    Workflow after this tool returns the base64 image:
    1. You will SEE the image — study the scene: composition, lighting, colors, objects, style
    2. Write a detailed text description of exactly what you see
    3. Call your image generation tool (DALL-E) using ONLY a text prompt — describe the full
       scene from step 2, then append the user's requested changes (e.g. "...but at night with
       warm street lighting and 4-5 people walking in the foreground")
    4. IMPORTANT: DALL-E here is text-to-image only — do NOT attempt to pass the base64 as
       input to DALL-E. Describe the scene in text and generate from that description.

    This produces the best results: you analyze the reference visually, then generate a fresh
    image that matches the scene with the requested modifications applied.

    target_kb: target WebP size in KB (default 450)
    max_dimension: longest side in pixels (default 1920)
    """
    return _vision.read_image_for_generation(
        _vision.ReadImageForGenerationInput(path=path, target_kb=target_kb, max_dimension=max_dimension)
    )


@mcp.tool()
def read_folder_for_vision(
    folder: str,
    recursive: bool = False,
    size: int = 800,
    quality: int = 85,
    max_images: int = 30,
    modified_within_hours: float | None = None,
    sort_by: str = "newest",
) -> dict:
    """
    Read images in a folder and return each as a base64 JPEG thumbnail for vision analysis.
    Always sorted and capped BEFORE encoding — never overloads the device regardless of folder size.
    sort_by: newest (default) | oldest | name
    modified_within_hours: e.g. 24 = only images from the last 24 hours
    max_images: hard cap before encoding, default 30 (max 100).
    Use for: renaming by content, finding images by scene/object/color, picking best shot.
    """
    return _vision.read_folder_for_vision(_vision.ReadFolderForVisionInput(
        folder=folder, recursive=recursive,
        size=size, quality=quality, max_images=max_images,
        modified_within_hours=modified_within_hours, sort_by=sort_by,
    ))


# ---------------------------------------------------------------------------
# Screen capture tool
# ---------------------------------------------------------------------------

@mcp.tool()
def capture_screen(
    output_file: str,
    monitor: int = 0,
    return_base64: bool = False,
) -> dict:
    """
    Silently capture the Windows desktop and save it as a PNG — no window flash,
    no new processes, zero interference with running applications (renders, etc.).

    output_file: full path for the saved PNG, e.g. C:/Users/PC/Desktop/snapshot.png
    monitor: 0 = all monitors (virtual desktop), 1 = primary, 2 = secondary, etc.
    return_base64: if true, also returns the image inline so it can be shown in chat.
    """
    return _screen.capture_screen(
        _screen.CaptureScreenInput(
            output_file=output_file,
            monitor=monitor,
            return_base64=return_base64,
        )
    )


# ---------------------------------------------------------------------------
# SketchUp + V-Ray tools
# ---------------------------------------------------------------------------

@mcp.tool()
def analyze_scene() -> dict:
    """Analyze the currently open SketchUp scene. Returns geometry stats, materials, reversed faces, missing textures, tags, components and rendering complexity."""
    return _su.analyze_scene(_su.AnalyzeSceneInput())

@mcp.tool()
def prepare_scene_for_rendering(purge_unused: bool = True, fix_reversed_faces: bool = False, remove_hidden_geometry: bool = False) -> dict:
    """Optimize the SketchUp model for production rendering: purge unused, fix reversed faces, remove hidden geometry."""
    return _su.prepare_scene_for_rendering(_su.PrepareSceneInput(purge_unused=purge_unused, fix_reversed_faces=fix_reversed_faces, remove_hidden_geometry=remove_hidden_geometry))

@mcp.tool()
def analyze_render_setup() -> dict:
    """Inspect the V-Ray render setup in the current SketchUp scene: lights, materials, render options."""
    return _su.analyze_render_setup(_su.AnalyzeRenderSetupInput())

@mcp.tool()
def optimize_render_setup(goals: str = "") -> dict:
    """Get V-Ray render setup recommendations. goals: e.g. 'faster render', 'less noise', 'production quality'."""
    return _su.optimize_render_setup(_su.OptimizeRenderSetupInput(goals=goals))

@mcp.tool()
def material_assistant(instruction: str, material_name: str | None = None) -> dict:
    """Apply a natural-language material change to the open SketchUp model.
    Examples: 'Apply purple to the cabinet panels', 'Make the fabric deep purple',
    'Change all wall materials to warm white', 'Make the wood darker'.
    material_name: optional explicit name for the created/updated material."""
    result = _su.material_assistant(_su.MaterialAssistantInput(instruction=instruction, material_name=material_name))
    return result

@mcp.tool()
def create_vray_material(description: str, material_name: str | None = None) -> dict:
    """Generate a physically-based V-Ray material from a description and add it to the SketchUp model.
    Examples: 'polished marble', 'brushed aluminium', 'frosted glass', 'oak veneer', 'velvet', 'brass'."""
    return _su.create_vray_material(_su.CreateVRayMaterialInput(description=description, material_name=material_name))

@mcp.tool()
def lighting_assistant(instruction: str) -> dict:
    """Analyze scene lighting and provide targeted recommendations.
    Examples: 'Make lighting softer', 'Fix overexposed render', 'Create moody evening atmosphere'."""
    return _su.lighting_assistant(_su.LightingAssistantInput(instruction=instruction))

@mcp.tool()
def render_diagnostics(issue: str) -> dict:
    """Diagnose a V-Ray rendering issue and provide specific fix recommendations.
    Examples: 'Why is the render noisy?', 'Reflections are black', 'Glass looks wrong'."""
    return _su.render_diagnostics(_su.RenderDiagnosticsInput(issue=issue))

@mcp.tool()
def texture_management(action: str = "report") -> dict:
    """Audit scene textures. action: 'report' (full audit), 'find missing', 'find duplicates'."""
    return _su.texture_management(_su.TextureManagementInput(action=action))

@mcp.tool()
def generate_scene_report() -> dict:
    """Generate a complete SketchUp scene report: stats, rendering readiness, materials, issues and suggestions."""
    return _su.generate_scene_report(_su.GenerateSceneReportInput())


@mcp.tool()
def sketchup_ruby(code: str) -> dict:
    """
    ALWAYS USE THIS TOOL when asked to do ANYTHING in SketchUp that no other tool covers.
    This executes ANY Ruby code directly in the live SketchUp instance — no restrictions.

    CRITICAL RULES:
    - NEVER say "the MCP doesn't support this" or "there is no tool for this"
    - NEVER say you need a specific named tool — this tool does EVERYTHING via Ruby
    - If you don't know the exact API, probe it first with a small introspection script
    - Always return a JSON-serialisable value (Hash, Array, String, Number, nil)
    - On error, the bridge returns {ruby_error: true, message: "..."} — read it and retry

    INTROSPECTION PATTERN (use when unsure of API):
      "defined?(VRay) ? VRay.constants.map(&:to_s).sort : 'VRay not loaded'"
      "VRay::Sun.methods(false).map(&:to_s).sort" (after confirming VRay exists)
      "Sketchup.active_model.rendering_options.keys"

    COMMON PATTERNS:
      Count V-Ray lights:  m.entities.select{|e| e.is_a?(Sketchup::ComponentInstance) && e.definition.name =~ /vray|light/i}.count
      Read sun settings:   Sketchup.active_model.shadow_info.keys.map{|k| [k, Sketchup.active_model.shadow_info[k]]}
      Explode component:   Sketchup.active_model.entities.grep(Sketchup::ComponentInstance).select{|e| e.definition.name=='Wall_Unit'}.each(&:explode)
      Set camera FOV:      Sketchup.active_model.active_view.camera.fov = 45
      Create geometry:     g=Sketchup.active_model.entities.add_group; g.entities.add_face([...]).pushpull(height)

    SketchUp must be open with MCP Bridge running (Plugins → MCP Bridge → Start Server).
    """
    try:
        from log_setup import timed_operation
        with timed_operation("sketchup:ruby"):
            result = run_ruby_json(code)
        # If Ruby returned an error dict, pass it through so ChatGPT can read and retry
        if isinstance(result, dict) and result.get("ruby_error"):
            return {"status": "ruby_error", "error": result.get("message"), 
                    "error_class": result.get("error_class"), "result": None,
                    "hint": "The Ruby code raised an exception. Inspect the error, adjust the code, and retry."}
        return {"result": result, "status": "ok"}
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started. Open SketchUp → Plugins → MCP Bridge → Start Server.")
    except SketchUpError as e:
        # Return as result so ChatGPT can read the error and retry with corrected Ruby
        return {"status": "ruby_error", "error": str(e),
                "hint": "The Ruby code raised an exception. Read the error message, adjust the code, and call sketchup_ruby again."}


@mcp.tool()
def sketchup_capture_viewport(
    width: int = 1280,
    height: int = 720,
    quality: int = 85,
    view_preset: str | None = None,
) -> dict:
    """
    SCREENSHOT TOOL — capture what is currently visible in the SketchUp window and return
    it as an inline image in the chat. Use this any time the user says:
    "show me", "screenshot", "capture", "take a photo", "what does it look like",
    "verify visually", "confirm the result", or any similar phrase.

    This is the ONLY tool for viewport screenshots. Do NOT use sketchup_build_from_reference
    or sketchup_ruby for screenshots — those are for geometry/code only.

    view_preset: snap camera to a standard view BEFORE capturing.
      Options: front, back, left, right, top, bottom, iso, zoom_extents
      Leave empty to capture exactly what is currently visible.

    width/height: pixels (default 1280x720). quality: JPEG 40-95 (default 85).
    """
    import base64, os, tempfile
    from log_setup import timed_operation

    # Map preset names to SketchUp camera constants
    preset_map = {
        "front":        "Sketchup::Camera::FRONT",
        "back":         "Sketchup::Camera::BACK",
        "left":         "Sketchup::Camera::LEFT",
        "right":        "Sketchup::Camera::RIGHT",
        "top":          "Sketchup::Camera::TOP",
        "bottom":       "Sketchup::Camera::BOTTOM",
        "iso":          "Sketchup::Camera::ISO",
    }

    preset_ruby = ""
    if view_preset:
        vp = view_preset.lower().strip()
        if vp == "zoom_extents":
            preset_ruby = "Sketchup.active_model.active_view.zoom_extents; sleep(0.1)"
        elif vp in preset_map:
            preset_ruby = f"Sketchup.active_model.active_view.camera = Sketchup::Camera.new({preset_map[vp]}); sleep(0.1)"

    tmp_path = os.path.join(tempfile.gettempdir(), "mcp_viewport_capture.jpg").replace("\\", "/")

    ruby = f"""
    {preset_ruby}
    view = Sketchup.active_model.active_view
    opts = {{
      filename:    {repr(tmp_path)},
      width:       {width},
      height:      {height},
      antialias:   true,
      compression: {quality / 100.0},
      transparent: false
    }}
    success = view.write_image(opts)
    cam = view.camera
    {{
      success:           success,
      path:              {repr(tmp_path)},
      width:             {width},
      height:            {height},
      camera_eye:        cam.eye.to_a.map{{|v|v.round(1)}},
      camera_direction:  cam.direction.to_a.map{{|v|v.round(3)}},
      view_preset:       {repr(view_preset or "current")}
    }}
    """

    try:
        with timed_operation(f"sketchup:capture_viewport ({width}x{height})"):
            meta = run_ruby_json(ruby)

        if not meta.get("success"):
            raise RuntimeError("SketchUp write_image returned false — viewport capture failed.")

        # Read the file and encode
        img_bytes = open(tmp_path, "rb").read()
        b64 = base64.b64encode(img_bytes).decode("ascii")

        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

        return {
            "mime_type":        "image/jpeg",
            "base64":           b64,
            "width":            meta.get("width"),
            "height":           meta.get("height"),
            "size_kb":          round(len(img_bytes) / 1024, 1),
            "view_preset":      meta.get("view_preset"),
            "camera_eye":       meta.get("camera_eye"),
            "camera_direction": meta.get("camera_direction"),
            "status":           "captured",
        }

    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp error: {e}")


@mcp.tool()
def sketchup_build_from_reference(
    description: str,
    dimensions_m: dict | None = None,
) -> dict:
    """
    DO NOT USE THIS TOOL for image-based modeling requests.

    When the user provides a reference image and asks to build it in SketchUp, use this
    workflow instead:
    1. Call read_image_for_vision with the image path to SEE the reference
    2. Analyze the geometry: identify volumes, proportions, hierarchy, dimensions
    3. Plan the Ruby script: groups, faces, push_pull, offsets, window recesses, etc.
    4. Call sketchup_ruby with the complete Ruby script to build it in the live model
    5. Call sketchup_capture_viewport to show the result

    This tool only creates a generic box massing — it has no vision capability and will
    produce incorrect results for any real architectural or object reference.
    Only use this tool if the user explicitly asks for a rough placeholder massing with
    no reference image provided.

    description: what to build
    dimensions_m: key dimensions in meters e.g. {'width': 10, 'height': 6, 'depth': 8}
    """
    dims = dimensions_m or {}
    w = dims.get("width",  10.0)
    h = dims.get("height",  4.0)
    d = dims.get("depth",   8.0)
    ruby = f"""
    m    = Sketchup.active_model
    grp  = m.entities.add_group
    ge   = grp.entities
    to_in = 39.3701
    w = {w} * to_in
    h = {h} * to_in
    d = {d} * to_in
    pts = [Geom::Point3d.new(0,0,0),Geom::Point3d.new(w,0,0),Geom::Point3d.new(w,d,0),Geom::Point3d.new(0,d,0)]
    face = ge.add_face(pts)
    face.pushpull(h)
    m.active_view.zoom_extents
    {{status:"built",description:{repr(description)},dimensions:{{width_m:{w},height_m:{h},depth_m:{d}}},
     note:"Base massing created. Refine with sketchup_ruby for openings and facade details."}}
    """
    try:
        from log_setup import timed_operation
        with timed_operation("sketchup:build_from_reference"):
            return run_ruby_json(ruby)
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp Ruby error: {e}")


@mcp.tool()
def sketchup_get_model_info() -> dict:
    """
    Return a quick summary of the currently open SketchUp model:
    name, path, entity counts, component list, material list, layer list.
    Use this to orient yourself before running sketchup_ruby operations.
    """
    try:
        from log_setup import timed_operation
        with timed_operation("sketchup:model_info"):
            return run_ruby_json("""
            m = Sketchup.active_model
            {
              name:       m.name,
              path:       m.path,
              entities:   m.entities.count,
              faces:      m.entities.grep(Sketchup::Face).count,
              edges:      m.entities.grep(Sketchup::Edge).count,
              groups:     m.entities.grep(Sketchup::Group).count,
              components: m.entities.grep(Sketchup::ComponentInstance).map{|e| {name: e.definition.name, id: e.entityID}},
              materials:  m.materials.map{|mat| {name: mat.name, color: mat.color.to_a}},
              layers:     m.layers.map{|l| {name: l.name, visible: l.visible?}},
              selection:  m.selection.map{|e| {type: e.class.name, id: e.entityID}}
            }
            """)
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp error: {e}")


@mcp.tool()
def sketchup_get_scene_info() -> dict:
    """
    Get comprehensive information about the current SketchUp scene:
    model name, face/edge counts, all components with positions, all groups,
    materials with colors, layers, and camera state.
    Use this for a full scene overview before planning any operations.
    """
    try:
        from log_setup import timed_operation
        with timed_operation("sketchup:get_scene_info"):
            return send_named_command("get_scene_info")
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp error: {e}")


@mcp.tool()
def sketchup_get_selection() -> dict:
    """
    Get all currently selected entities in SketchUp with their IDs, types,
    names and positions. Use before transform or material operations to
    confirm which entities are targeted.
    """
    try:
        from log_setup import timed_operation
        with timed_operation("sketchup:get_selection"):
            result = send_named_command("get_selection")
            return {"selection": result, "count": len(result) if isinstance(result, list) else 0}
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp error: {e}")


@mcp.tool()
def sketchup_create_component(
    type: str = "cube",
    position: list[float] | None = None,
    dimensions: list[float] | None = None,
) -> dict:
    """
    Create a new 3D component in SketchUp.
    type: cube | cylinder (more shapes via sketchup_ruby)
    position: [x, y, z] in meters (default [0,0,0])
    dimensions: [width, depth, height] in meters (default [1,1,1])
    Returns the entity ID and position of the created component.
    """
    try:
        from log_setup import timed_operation
        with timed_operation(f"sketchup:create_component {type}"):
            return send_named_command("create_component", {
                "type": type,
                "position": position or [0, 0, 0],
                "dimensions": dimensions or [1, 1, 1],
            })
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp error: {e}")


@mcp.tool()
def sketchup_delete_component(entity_id: str) -> dict:
    """
    Delete a component or group from SketchUp by its entity ID.
    Get entity IDs from sketchup_get_scene_info or sketchup_get_model_info.
    """
    try:
        from log_setup import timed_operation
        with timed_operation(f"sketchup:delete_component {entity_id}"):
            return send_named_command("delete_component", {"id": entity_id})
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp error: {e}")


@mcp.tool()
def sketchup_transform_component(
    entity_id: str,
    position: list[float] | None = None,
    rotation: list[float] | None = None,
    scale: list[float] | None = None,
) -> dict:
    """
    Move, rotate, or scale a component/group by entity ID.
    position: [x, y, z] in meters
    rotation: [rx, ry, rz] in degrees
    scale: [sx, sy, sz] as multipliers (e.g. [2,2,2] doubles size)
    Any combination of the three can be applied in one call.
    """
    try:
        from log_setup import timed_operation
        args: dict = {"id": entity_id}
        if position is not None:
            args["position"] = position
        if rotation is not None:
            args["rotation"] = rotation
        if scale is not None:
            args["scale"] = scale
        with timed_operation(f"sketchup:transform {entity_id}"):
            return send_named_command("transform_component", args)
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp error: {e}")


@mcp.tool()
def sketchup_set_material(entity_id: str, material: str) -> dict:
    """
    Apply a material to a component or group by entity ID.
    material: hex color (#ff0000), rgb string (rgb(255,0,0)), or named material.
    Applies to the entity and all its faces.
    """
    try:
        from log_setup import timed_operation
        with timed_operation(f"sketchup:set_material {entity_id}"):
            return send_named_command("set_material", {"id": entity_id, "material": material})
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp error: {e}")


@mcp.tool()
def sketchup_export_scene(format: str = "skp") -> dict:
    """
    Export the current SketchUp scene to a file.
    format: skp (default) | dae | obj | stl
    The file is saved alongside the current model file with an _export suffix.
    The model must be saved at least once before exporting.
    """
    try:
        from log_setup import timed_operation
        with timed_operation(f"sketchup:export {format}"):
            return send_named_command("export_scene", {"format": format})
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp error: {e}")


@mcp.tool()
def sketchup_get_environment() -> dict:
    """
    Read all current environment settings from the open SketchUp model:
    - Camera: FOV, perspective/parallel, eye/target position, aspect ratio
    - Sun: light/dark intensity, time of day, geographic location, shadow state
    - Sky: background color, fog, sky color
    - V-Ray: exposure, f-number, ISO, shutter speed, white balance, DOF (if V-Ray is loaded)
    - Scenes: all saved scenes with their property flags

    Use this before making any environment or camera adjustments.
    Always call this first, then save a backup scene, then apply changes.
    """
    try:
        from log_setup import timed_operation
        with timed_operation("sketchup:get_environment"):
            return _su.get_environment_setup()
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp error: {e}")


@mcp.tool()
def sketchup_save_environment_scene(scene_name: str) -> dict:
    """
    Create or update a SketchUp scene that saves the current camera, sun, shadows,
    and rendering options as a named snapshot.

    ALWAYS call this before applying any environment changes — it creates a restore
    point so the user can click the scene tab to undo any modifications.

    scene_name: name for the scene, e.g. 'MCP_Backup_Before_Edit' or a descriptive name
    like 'Night_Setup_Backup' or 'Original_Camera_20240721'
    """
    try:
        from log_setup import timed_operation
        with timed_operation(f"sketchup:save_environment_scene {scene_name}"):
            return _su.save_environment_scene(scene_name)
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp error: {e}")


@mcp.tool()
def sketchup_apply_environment(settings: dict) -> dict:
    """
    Apply environment, sun, camera or V-Ray settings to the current SketchUp scene.

    ALWAYS call sketchup_save_environment_scene BEFORE calling this tool.

    Supported settings keys:
      sun_light (0-100): sun brightness — high values cause overexposure
      sun_dark (0-100): shadow/ambient intensity — high values wash out shadows
      display_shadows (bool): enable/disable shadow casting
      fov (degrees): camera field of view, e.g. 45 for standard, 28 for wide
      perspective (bool): true=perspective, false=parallel projection
      fog_enabled (bool): enable/disable atmospheric fog
      vray_exposure (float): V-Ray physical camera exposure, typical 0.5-1.2
      vray_f_number (float): V-Ray aperture f-stop, e.g. 8.0 for arch renders
      vray_iso (float): V-Ray ISO sensitivity, typical 100-800
      vray_shutter (float): V-Ray shutter speed
      vray_white_balance (float): V-Ray color temperature in Kelvin

    Example: {"sun_light": 75, "sun_dark": 25, "vray_exposure": 0.8}
    """
    try:
        from log_setup import timed_operation
        with timed_operation("sketchup:apply_environment"):
            return _su.apply_environment_settings(settings)
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp error: {e}")


@mcp.tool()
def sketchup_diagnose_environment() -> dict:
    """
    Diagnose environment and rendering issues in the current SketchUp scene.
    Checks for: overexposure, underexposure, washed-out shadows, extreme FOV,
    V-Ray exposure/aperture problems, sun misconfiguration.

    Returns a list of issues with severity (high/medium/low) and specific fix
    recommendations with suggested values ready to pass to sketchup_apply_environment.

    Use this when the user says things like:
    - "the render looks overexposed / too bright / blown out"
    - "everything is too dark"
    - "fix the environment"
    - "the sun is too harsh"
    - "diagnose my render settings"
    """
    try:
        from log_setup import timed_operation
        with timed_operation("sketchup:diagnose_environment"):
            return _su.diagnose_environment()
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp error: {e}")


@mcp.tool()
def sketchup_apply_material_to_component(
    component_name: str,
    color_rgb: list[int],
    material_name: str | None = None,
) -> dict:
    """
    Apply a color material to all faces inside a named component or group.
    component_name: exact name as it appears in the model (e.g. 'Wall_Display_Unit')
    color_rgb: [R, G, B] values 0-255 (e.g. [128, 0, 128] for purple)
    material_name: optional name for the new material
    """
    r, g, b = color_rgb[0], color_rgb[1], color_rgb[2]
    mat_name = material_name or f"MCP_{r}_{g}_{b}"
    try:
        from log_setup import timed_operation
        with timed_operation(f"sketchup:apply_material {component_name}"):
            return run_ruby_json(f"""
            m        = Sketchup.active_model
            comp_name = {repr(component_name)}
            mat_name  = {repr(mat_name)}

            # Find or create material
            mat = m.materials[mat_name] || m.materials.add(mat_name)
            mat.color = Sketchup::Color.new({r}, {g}, {b})

            # Find all matching components/groups recursively
            def find_named(entities, name)
              found = []
              entities.each do |e|
                if (e.is_a?(Sketchup::ComponentInstance) || e.is_a?(Sketchup::Group))
                  if e.is_a?(Sketchup::ComponentInstance)
                    n = e.definition.name
                    ch = e.definition.entities
                  else
                    n = e.name
                    ch = e.entities
                  end
                  found << e if n.downcase.include?(name.downcase)
                  found += find_named(ch, name)
                end
              end
              found
            end

            targets = find_named(m.entities, comp_name)

            m.start_operation("MCP Apply Material", true)
            faces_painted = 0
            targets.each do |target|
              if target.is_a?(Sketchup::ComponentInstance)
                ents = target.definition.entities
              else
                ents = target.entities
              end
              ents.grep(Sketchup::Face).each do |face|
                face.material = mat
                faces_painted += 1
              end
            end
            m.commit_operation

            {{
              component_name:  comp_name,
              material_name:   mat.name,
              color_rgb:       [{r},{g},{b}],
              components_found: targets.count,
              faces_painted:   faces_painted,
              status:          faces_painted > 0 ? "applied" : "no_matching_faces"
            }}
            """)
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp error: {e}")


# ---------------------------------------------------------------------------
# System / process control tools
# ---------------------------------------------------------------------------

@mcp.tool()
def terminate_process(name_or_pid: str, force: bool = True) -> dict:
    """
    Terminate a running process by name or PID. Runs fully in the background.
    name_or_pid: process name (e.g. 'SketchUp.exe', '3dsmax.exe') or numeric PID.
    force: True = hard kill (/F), False = graceful terminate.
    """
    return _sys.terminate_process(name_or_pid, force)


@mcp.tool()
def list_processes(filter_name: str = "", sort_by: str = "name") -> dict:
    """
    List running processes with memory usage.
    filter_name: optional substring filter on process name.
    sort_by: 'memory' or 'name'.
    """
    return _sys.list_processes(filter_name, sort_by)


@mcp.tool()
def restart_gpu_driver() -> dict:
    """
    Restart the GPU display driver without rebooting (Win+Ctrl+Shift+B equivalent).
    Safe on all Windows 10/11 machines. Use when GPU is hung or display artifacts appear.
    """
    return _sys.restart_gpu_driver()


@mcp.tool()
def get_gpu_info() -> dict:
    """Return GPU name, driver version, and VRAM info from WMI."""
    return _sys.get_gpu_info()


@mcp.tool()
def set_power_plan(plan: str) -> dict:
    """
    Switch Windows CPU power plan.
    plan: 'balanced', 'performance', or 'powersaver'.
    """
    return _sys.set_power_plan(plan)


@mcp.tool()
def get_power_plan() -> dict:
    """Return the currently active Windows power plan."""
    return _sys.get_power_plan()


@mcp.tool()
def get_system_stats() -> dict:
    """Return current CPU usage %, RAM total/used/free in GB."""
    return _sys.get_system_stats()


# ---------------------------------------------------------------------------
# Log viewer
# ---------------------------------------------------------------------------

@mcp.tool()
def get_log(lines: int = 50) -> dict:
    """
    Return the last N lines of the server agent.log for debugging and monitoring.
    Shows tool call history with [START]/[DONE]/[FAIL] entries and timing.
    lines: number of recent lines to return (default 50, max 500)
    """
    log_path = Path(__file__).parent.parent / "agent.log"
    lines = min(max(1, lines), 500)
    if not log_path.exists():
        return {"log": "", "lines_returned": 0, "path": str(log_path), "note": "log file not found"}
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    recent = all_lines[-lines:]
    return {
        "log": "".join(recent),
        "lines_returned": len(recent),
        "total_lines": len(all_lines),
        "path": str(log_path),
    }


# ---------------------------------------------------------------------------
# Shell exec tool
# ---------------------------------------------------------------------------

@mcp.tool()
def fix_rdp() -> dict:
    """Re-enable Remote Desktop and open Windows Firewall port 3389."""
    return _sys.fix_rdp()


@mcp.tool()
def run_command(command: str, timeout: int = 30) -> dict:
    """
    Run any shell command on the remote machine and return stdout/stderr/exit code.
    Runs fully in the background — no terminal window, no popups.
    Use for git operations, PowerShell scripts, scheduled tasks, or anything else.
    command: any valid Windows cmd or PowerShell command string.
    timeout: max seconds to wait (default 30).
    """
    return _sys.run_command(command, timeout)


# ---------------------------------------------------------------------------
# Git tools
# ---------------------------------------------------------------------------

@mcp.tool()
def git_status(repo: str) -> dict:
    """Show the working tree status (branch + changed files) for a git repository."""
    return _git_tools.git_status(_git_tools.GitStatusInput(repo=repo))


@mcp.tool()
def git_add(repo: str, files: list[str] | None = None) -> dict:
    """Stage files in a git repository. Defaults to staging all changes ('.')."""
    return _git_tools.git_add(_git_tools.GitAddInput(repo=repo, files=files or ["."]))


@mcp.tool()
def git_commit(repo: str, message: str, allow_empty: bool = False) -> dict:
    """Commit staged changes with a message. Returns the short commit hash."""
    return _git_tools.git_commit(_git_tools.GitCommitInput(repo=repo, message=message, allow_empty=allow_empty))


@mcp.tool()
def git_push(repo: str, remote: str = "origin", branch: str | None = None, set_upstream: bool = False) -> dict:
    """Push commits to a remote repository."""
    return _git_tools.git_push(_git_tools.GitPushInput(repo=repo, remote=remote, branch=branch, set_upstream=set_upstream))


@mcp.tool()
def git_pull(repo: str, remote: str = "origin", branch: str | None = None) -> dict:
    """Pull latest commits from a remote repository."""
    return _git_tools.git_pull(_git_tools.GitPullInput(repo=repo, remote=remote, branch=branch))


@mcp.tool()
def git_log(repo: str, n: int = 10, oneline: bool = True) -> dict:
    """Show recent commit history for a git repository."""
    return _git_tools.git_log(_git_tools.GitLogInput(repo=repo, n=n, oneline=oneline))


@mcp.tool()
def git_diff(repo: str, staged: bool = False, file: str | None = None) -> dict:
    """Show unstaged (or staged) changes in a git repository."""
    return _git_tools.git_diff(_git_tools.GitDiffInput(repo=repo, staged=staged, file=file))


@mcp.tool()
def git_checkout(repo: str, branch: str, create: bool = False) -> dict:
    """Checkout a branch in a git repository, optionally creating it."""
    return _git_tools.git_checkout(_git_tools.GitCheckoutInput(repo=repo, branch=branch, create=create))


@mcp.tool()
def git_publish_file(repo: str, file: str, message: str, remote: str = "origin", branch: str | None = None) -> dict:
    """
    Stage, commit, and push a single file in one call.
    repo:    absolute path to the git repository root
    file:    path to the file relative to the repo root
    message: commit message
    """
    return _git_tools.git_publish_file(
        _git_tools.GitPublishFileInput(repo=repo, file=file, message=message, remote=remote, branch=branch)
    )


if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 8765
    ngrok_url = _get_ngrok_url()
    logger.info("Starting %s v%s", config.server_name, config.server_version)
    logger.info("Local endpoint:  http://%s:%d/mcp", HOST, PORT)
    logger.info("ngrok MCP URL:   %s/mcp", ngrok_url)
    mcp.run(
        transport="streamable-http",
        host=HOST,
        port=PORT,
        path="/mcp",
    )
