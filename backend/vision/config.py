"""
Configuration management for Phase 3 Vision & Gesture Subsystem.

Loads default configuration from backend.core.config.settings and supports
thread-safe dynamic runtime overrides.
"""

from typing import Optional
from pydantic import BaseModel, Field
from backend.core.config import settings


class VisionConfig(BaseModel):
    """Runtime configuration for Vision & Hand Gesture Subsystem."""
    enabled: bool = Field(default_factory=lambda: getattr(settings, "GESTURE_ENABLED", False))
    camera_index: int = Field(default_factory=lambda: getattr(settings, "CAMERA_INDEX", 0))
    camera_width: int = Field(default_factory=lambda: getattr(settings, "GESTURE_CAMERA_WIDTH", 640))
    camera_height: int = Field(default_factory=lambda: getattr(settings, "GESTURE_CAMERA_HEIGHT", 480))
    camera_fps: int = Field(default_factory=lambda: getattr(settings, "GESTURE_CAMERA_FPS", 15))
    confidence_threshold: float = Field(default_factory=lambda: getattr(settings, "GESTURE_CONFIDENCE_THRESHOLD", 0.65))
    cooldown_ms: int = Field(default_factory=lambda: getattr(settings, "GESTURE_COOLDOWN_MS", 1000))
    model_path: Optional[str] = Field(default="data/models/gesture_recognizer.task")


# Global singleton vision config instance
vision_config = VisionConfig()


def get_vision_config() -> VisionConfig:
    """Return the global vision configuration."""
    return vision_config


def update_vision_config(**kwargs) -> VisionConfig:
    """Update vision configuration fields dynamically."""
    global vision_config
    current = vision_config.model_dump()
    for k, v in kwargs.items():
        if v is not None and k in current:
            current[k] = v
    vision_config = VisionConfig(**current)
    return vision_config
