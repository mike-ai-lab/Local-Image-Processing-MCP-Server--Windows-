"""MCP tool definitions — AI-powered denoise, upscale, and pipeline."""

from __future__ import annotations
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Any

logger = logging.getLogger("local-image-agent")


class AiDenoiseInput(BaseModel):
    input_file:  str = Field(..., description="Path to source image.")
    output_file: str = Field(..., description="Path to write denoised image.")
    strength:    str = Field("medium", description="Denoise strength: low | medium | high")


def ai_denoise(params: AiDenoiseInput) -> dict[str, Any]:
    from ai_process import ai_denoise as _denoise
    import validation as val
    src = val.validate_input_file(params.input_file)
    dst = val.validate_output_file(params.output_file)
    return _denoise(src, dst, strength=params.strength)


class AiUpscaleInput(BaseModel):
    input_file:  str = Field(..., description="Path to source image.")
    output_file: str = Field(..., description="Path to write upscaled image.")
    scale:       int = Field(2,  description="Upscale factor: 2 or 4.")
    model:       str = Field("RealESRGAN_x4plus",
                             description="Model: RealESRGAN_x4plus | RealESRGAN_x2plus | RealESRGAN_x4plus_anime_6B")


def ai_upscale(params: AiUpscaleInput) -> dict[str, Any]:
    from ai_process import ai_upscale as _upscale
    import validation as val
    src = val.validate_input_file(params.input_file)
    dst = val.validate_output_file(params.output_file)
    return _upscale(src, dst, scale=params.scale, model=params.model)


class AiProcessPipelineInput(BaseModel):
    input_file:       str = Field(..., description="Path to source image.")
    output_file:      str = Field(..., description="Path to write final image.")
    denoise_strength: str = Field("medium", description="Denoise strength: low | medium | high")
    upscale:          int = Field(2,         description="Upscale factor: 2 or 4.")
    model:            str = Field("RealESRGAN_x4plus",
                                  description="Real-ESRGAN model to use for upscaling.")


def ai_process_pipeline(params: AiProcessPipelineInput) -> dict[str, Any]:
    from ai_process import ai_process_pipeline as _pipeline
    import validation as val
    src = val.validate_input_file(params.input_file)
    dst = val.validate_output_file(params.output_file)
    return _pipeline(src, dst,
                     denoise_strength=params.denoise_strength,
                     upscale=params.upscale,
                     model=params.model)
