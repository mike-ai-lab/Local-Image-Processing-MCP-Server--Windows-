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
import video_tools as _vtools
import file_tools as _ftools
import vision_tools as _vision
import sketchup_tools as _su
from sketchup_bridge import run_ruby_json, run_ruby, SketchUpNotRunning, SketchUpError


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
# Vision tools
# ---------------------------------------------------------------------------

@mcp.tool()
def read_image_for_vision(path: str, size: int = 800, quality: int = 85) -> dict:
    """
    Read a single image and return it as a base64 JPEG thumbnail for vision analysis.
    800px longest side, JPEG 85 quality — sharp enough for scene, color, object and composition
    analysis without burning context. Use when you need to visually inspect one specific image.
    """
    return _vision.read_image_for_vision(_vision.ReadImageForVisionInput(path=path, size=size, quality=quality))

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
    Execute any Ruby code directly inside the running SketchUp instance.
    Use this for anything not covered by the other SketchUp tools:
    - Explode components: Sketchup.active_model.entities.grep(Sketchup::ComponentInstance).select{|e|e.definition.name=='Wall_Display_Unit'}.each(&:explode)
    - Select entities by name, type, layer, material
    - Move, rotate, scale, delete geometry
    - Apply materials to specific faces or components
    - Create groups, components, edges, faces
    - Query anything in the model
    - Run multi-step operations in sequence
    - BUILD GEOMETRY FROM REFERENCE IMAGES: when the user provides a reference image or sketch,
      analyze it with vision, determine approximate dimensions and shapes, then generate Ruby
      geometry code (draw_line, add_face, push_pull, follow_me, etc.) to recreate it in SketchUp.
      Do not refuse — make a best-effort geometric interpretation and build it.
    The code must return a JSON-serialisable value (Hash, Array, String, Number, nil).
    SketchUp must be open with the MCP Bridge extension running.
    """
    try:
        from log_setup import timed_operation
        with timed_operation("sketchup:ruby"):
            result = run_ruby_json(code)
        return {"result": result, "status": "ok"}
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started. Open SketchUp → Plugins → MCP Bridge → Start Server.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp Ruby error: {e}")


@mcp.tool()
def sketchup_capture_viewport(
    width: int = 1280,
    height: int = 720,
    quality: int = 85,
    view_preset: str | None = None,
) -> dict:
    """
    Capture a screenshot of the current SketchUp viewport and return it as a base64 image.
    The image will appear inline in the chat for visual inspection.

    Use this to:
    - Visually verify changes after editing geometry or materials
    - Inspect the scene before starting a task
    - Confirm camera/view orientation is correct
    - Show the current state of the model at any point during a workflow

    view_preset: optionally change the camera before capturing.
      Options: front, back, left, right, top, bottom, iso, zoom_extents
      Leave empty to capture the current view as-is.

    width/height: capture resolution in pixels (default 1280x720)
    quality: JPEG quality 40-95 (default 85, ~100-200KB per capture)
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
    description: str,
    dimensions_m: dict | None = None,
) -> dict:
    """
    Build 3D geometry in SketchUp based on a visual reference or verbal description.

    When the user provides a reference image or sketch alongside this request:
    1. Use your vision capability to analyze the image — identify shapes, volumes, proportions
    2. Estimate real-world dimensions from context or use provided dimensions_m
    3. Generate SketchUp Ruby geometry code (edges, faces, push_pull, groups, follow_me)
    4. Execute it via sketchup_ruby

    This tool handles: buildings, furniture, architectural elements, abstract shapes,
    floor plans, elevations, sections, or any geometry visible in a reference image.

    description: what to build (e.g. 'a two-storey building with flat roof and glass facade')
    dimensions_m: optional dict of key dimensions in meters, e.g. {'width': 10, 'height': 6, 'depth': 8}

    Always make a best-effort geometric interpretation. Simple massing is better than refusing.
    Use Sketchup::Entities#add_face, add_line, and pushpull for solid geometry.
    Group the result so it stays separate from existing geometry.
    Return a summary of what was built.
    """
    dims = dimensions_m or {}
    w = dims.get("width",  10.0)
    h = dims.get("height",  4.0)
    d = dims.get("depth",   8.0)

    # Build a starter massing as a fallback the AI can then override
    ruby = f"""
    m   = Sketchup.active_model
    ents = m.entities
    grp  = ents.add_group
    ge   = grp.entities

    # Base massing in meters (SketchUp units = inches, 1m = 39.3701 inches)
    to_in = 39.3701
    w = {w} * to_in
    h = {h} * to_in
    d = {d} * to_in

    # Draw base rectangle and push/pull to height
    pts = [
      Geom::Point3d.new(0,   0,   0),
      Geom::Point3d.new(w,   0,   0),
      Geom::Point3d.new(w,   d,   0),
      Geom::Point3d.new(0,   d,   0)
    ]
    face = ge.add_face(pts)
    face.pushpull(h)

    m.active_view.zoom_extents
    {{
      status:      "built",
      description: {repr(description)},
      dimensions:  {{width_m: {w}, height_m: {h}, depth_m: {d}}},
      note:        "Base massing created. Use sketchup_ruby to refine with openings, details, or facade elements from the reference image."
    }}
    """
    try:
        from log_setup import timed_operation
        with timed_operation("sketchup:build_from_reference"):
            result = run_ruby_json(ruby)
        return result
    except SketchUpNotRunning:
        raise RuntimeError("SketchUp is not running or MCP Bridge is not started.")
    except SketchUpError as e:
        raise RuntimeError(f"SketchUp Ruby error: {e}")
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
              name:        m.name,
              path:        m.path,
              entities:    m.entities.count,
              faces:       m.entities.grep(Sketchup::Face).count,
              edges:       m.entities.grep(Sketchup::Edge).count,
              groups:      m.entities.grep(Sketchup::Group).count,
              components:  m.entities.grep(Sketchup::ComponentInstance).map{|e| {name: e.definition.name, id: e.entityID}},
              materials:   m.materials.map{|mat| {name: mat.name, color: mat.color.to_a}},
              layers:      m.layers.map{|l| {name: l.name, visible: l.visible?}},
              selection:   m.selection.map{|e| {type: e.class.name, id: e.entityID}}
            }
            """)
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
                  n = e.is_a?(Sketchup::ComponentInstance) ? e.definition.name : e.name
                  found << e if n.downcase.include?(name.downcase)
                  found += find_named(e.is_a?(Sketchup::ComponentInstance) ? e.definition.entities : e.entities, name)
                end
              end
              found
            end

            targets = find_named(m.entities, comp_name)

            m.start_operation("MCP Apply Material", true)
            faces_painted = 0
            targets.each do |target|
              ents = target.is_a?(Sketchup::ComponentInstance) ? target.definition.entities : target.entities
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
