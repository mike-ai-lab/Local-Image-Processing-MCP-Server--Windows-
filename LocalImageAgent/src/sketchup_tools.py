"""MCP tool definitions — SketchUp + V-Ray workflows."""

from __future__ import annotations

import logging
from typing import Any
from pydantic import BaseModel, Field

import sketchup_process as sp
from sketchup_bridge import SketchUpNotRunning, SketchUpError
from log_setup import timed_operation

logger = logging.getLogger("local-image-agent")

_NOT_RUNNING_MSG = (
    "SketchUp is not running or the MCP Bridge extension is not started. "
    "Open SketchUp, then: Plugins → MCP Bridge → Start Server."
)


def _verify_after_write() -> dict[str, Any]:
    """Quick model snapshot to confirm changes were applied. Always called after write operations."""
    try:
        return sp._ruby("""
        m=Sketchup.active_model
        cam=m.active_view.camera
        {
          entities:  m.entities.count,
          materials: m.materials.count,
          camera_direction: cam.direction.to_a.map{|v|v.round(3)},
          camera_eye: cam.eye.to_a.map{|v|v.round(1)},
          hidden_count: m.entities.select(&:hidden?).count,
          modified: m.modified?
        }
        """)
    except Exception:
        return {"note": "verify_unavailable"}


def _wrap(name: str, fn):
    """Execute fn inside a timed_operation, wrapping bridge errors cleanly."""
    with timed_operation(f"sketchup:{name}"):
        try:
            return fn()
        except SketchUpNotRunning:
            raise RuntimeError(_NOT_RUNNING_MSG)
        except SketchUpError as e:
            raise RuntimeError(f"SketchUp error: {e}")


# ---------------------------------------------------------------------------
# analyze_scene
# ---------------------------------------------------------------------------

class AnalyzeSceneInput(BaseModel):
    pass  # no parameters needed — operates on the active model


def analyze_scene(_: AnalyzeSceneInput) -> dict[str, Any]:
    """Analyze the currently open SketchUp scene and return a full report."""
    return _wrap("analyze_scene", sp.analyze_scene)


# ---------------------------------------------------------------------------
# prepare_scene_for_rendering
# ---------------------------------------------------------------------------

class PrepareSceneInput(BaseModel):
    purge_unused:           bool = Field(True,  description="Purge unused materials, components and layers.")
    fix_reversed_faces:     bool = Field(False, description="Automatically flip reversed faces.")
    remove_hidden_geometry: bool = Field(False, description="Erase hidden geometry.")


def prepare_scene_for_rendering(p: PrepareSceneInput) -> dict[str, Any]:
    """Optimize the SketchUp model for production rendering without changing its visual appearance."""
    result = _wrap("prepare_scene", lambda: sp.prepare_scene_for_rendering(
        purge_unused=p.purge_unused,
        fix_reversed_faces=p.fix_reversed_faces,
        remove_hidden_geometry=p.remove_hidden_geometry,
    ))
    result["_verified"] = _verify_after_write()
    return result


# ---------------------------------------------------------------------------
# analyze_render_setup
# ---------------------------------------------------------------------------

class AnalyzeRenderSetupInput(BaseModel):
    pass


def analyze_render_setup(_: AnalyzeRenderSetupInput) -> dict[str, Any]:
    """Inspect the V-Ray rendering setup in the current SketchUp scene."""
    return _wrap("analyze_render_setup", sp.analyze_render_setup)


# ---------------------------------------------------------------------------
# optimize_render_setup
# ---------------------------------------------------------------------------

class OptimizeRenderSetupInput(BaseModel):
    goals: str = Field("", description="Describe the render goal, e.g. 'faster render', 'less noise', 'production quality'.")


def optimize_render_setup(p: OptimizeRenderSetupInput) -> dict[str, Any]:
    """Generate V-Ray render setup recommendations based on the current scene and stated goals."""
    return _wrap("optimize_render_setup", lambda: sp.optimize_render_setup(goals=p.goals))


# ---------------------------------------------------------------------------
# material_assistant
# ---------------------------------------------------------------------------

class MaterialAssistantInput(BaseModel):
    instruction:   str       = Field(...,
        description="Natural language material instruction. Examples: "
                    "'Apply purple to the cabinet panels', 'Make the fabric deep purple', "
                    "'Change all wall materials to warm white', 'Make the wood darker'.")
    material_name: str | None = Field(None, description="Optional explicit name for the new material.")


def material_assistant(p: MaterialAssistantInput) -> dict[str, Any]:
    """Apply a natural-language material change to the open SketchUp model."""
    result = _wrap("material_assistant", lambda: sp.material_assistant(p.instruction, p.material_name))
    # Auto-verify
    result["_verified"] = _verify_after_write()
    return result


# ---------------------------------------------------------------------------
# create_vray_material
# ---------------------------------------------------------------------------

class CreateVRayMaterialInput(BaseModel):
    description:   str       = Field(...,
        description="Natural language material description. Examples: "
                    "'frosted plexiglass', 'brushed aluminium', 'polished marble', "
                    "'velvet', 'oak veneer', 'brass', 'ceramic'.")
    material_name: str | None = Field(None, description="Optional name for the material in SketchUp.")


def create_vray_material(p: CreateVRayMaterialInput) -> dict[str, Any]:
    """Generate a complete physically-based V-Ray material from a natural language description and add it to the model."""
    result = _wrap("create_vray_material", lambda: sp.create_vray_material(
        description=p.description, material_name=p.material_name
    ))
    result["_verified"] = _verify_after_write()
    return result


# ---------------------------------------------------------------------------
# lighting_assistant
# ---------------------------------------------------------------------------

class LightingAssistantInput(BaseModel):
    instruction: str = Field(...,
        description="Natural language lighting request. Examples: "
                    "'Make the lighting softer', 'Create a bright showroom feeling', "
                    "'Fix overexposed render', 'Create a moody evening atmosphere', "
                    "'Balance interior daylight'.")


def lighting_assistant(p: LightingAssistantInput) -> dict[str, Any]:
    """Analyze scene lighting and provide targeted improvement recommendations."""
    return _wrap("lighting_assistant", lambda: sp.lighting_assistant(p.instruction))


# ---------------------------------------------------------------------------
# render_diagnostics
# ---------------------------------------------------------------------------

class RenderDiagnosticsInput(BaseModel):
    issue: str = Field(...,
        description="Describe the render problem. Examples: "
                    "'Why is the render noisy?', 'Reflections are black', "
                    "'Textures look blurry', 'Render is overexposed', "
                    "'Glass looks wrong', 'Everything is too dark'.")


def render_diagnostics(p: RenderDiagnosticsInput) -> dict[str, Any]:
    """Diagnose a V-Ray rendering issue and provide specific fix recommendations."""
    return _wrap("render_diagnostics", lambda: sp.render_diagnostics(p.issue))


# ---------------------------------------------------------------------------
# texture_management
# ---------------------------------------------------------------------------

class TextureManagementInput(BaseModel):
    action: str = Field("report",
        description="What to do: 'report' (full texture audit), 'find missing', 'find duplicates'.")


def texture_management(p: TextureManagementInput) -> dict[str, Any]:
    """Audit scene textures: find missing files, duplicate textures, generate a texture usage report."""
    return _wrap("texture_management", lambda: sp.texture_management(p.action))


# ---------------------------------------------------------------------------
# generate_scene_report
# ---------------------------------------------------------------------------

class GenerateSceneReportInput(BaseModel):
    pass


def generate_scene_report(_: GenerateSceneReportInput) -> dict[str, Any]:
    """Generate a complete scene report: stats, rendering readiness, materials, lighting, issues, suggestions."""
    return _wrap("generate_scene_report", sp.generate_scene_report)
