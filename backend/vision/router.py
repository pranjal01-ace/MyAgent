"""
REST API Router for Phase 3 Vision & Gesture Subsystem.

Provides endpoints to inspect status, start/stop the camera, reconfigure parameters,
and inspect or modify the gesture registry.
"""

import asyncio
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.vision.gesture_manager import gesture_manager
from backend.vision.gesture_registry import gesture_registry, GestureDefinition
from backend.vision.config import get_vision_config, update_vision_config

router = APIRouter(prefix="/gesture", tags=["Vision & Gestures"])


class ConfigureVisionRequest(BaseModel):
    """Payload to configure vision and gesture parameters dynamically."""
    camera_index: Optional[int] = Field(None, description="Webcam device index (default 0)")
    camera_width: Optional[int] = Field(None, description="Camera frame width")
    camera_height: Optional[int] = Field(None, description="Camera frame height")
    camera_fps: Optional[int] = Field(None, description="Target processing FPS (e.g. 15)")
    confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Global minimum confidence")
    cooldown_ms: Optional[int] = Field(None, ge=0, description="Global debounce cooldown in milliseconds")


class UpdateGestureDefinitionRequest(BaseModel):
    """Payload to update an individual gesture's configuration."""
    enabled: Optional[bool] = None
    confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    cooldown_ms: Optional[int] = Field(None, ge=0)
    action: Optional[str] = None


@router.get("/status", summary="Get Vision & Gesture Status")
async def get_gesture_status() -> Dict[str, Any]:
    """Returns current real-time state of the camera and gesture recognition pipeline."""
    return gesture_manager.get_status()


@router.post("/start", summary="Start Gesture Recognition")
async def start_gesture_subsystem() -> Dict[str, Any]:
    """Starts the webcam acquisition and gesture recognition background thread."""
    loop = asyncio.get_running_loop()
    success = gesture_manager.start(event_loop=loop)
    if not success:
        cam_status = gesture_manager.camera.get_status()
        raise HTTPException(
            status_code=503,
            detail=f"Failed to start camera device: {cam_status.get('last_error', 'Camera unavailable')}"
        )
    return {
        "status": "started",
        "message": "Vision and gesture recognition subsystem started successfully.",
        "diagnostics": gesture_manager.get_status()
    }


@router.post("/stop", summary="Stop Gesture Recognition")
async def stop_gesture_subsystem() -> Dict[str, Any]:
    """Stops the gesture recognition loop and cleanly releases camera hardware."""
    gesture_manager.stop()
    return {
        "status": "stopped",
        "message": "Vision subsystem stopped and camera hardware released."
    }


@router.post("/configure", summary="Update Vision Settings")
async def configure_vision(req: ConfigureVisionRequest) -> Dict[str, Any]:
    """Updates runtime vision and gesture recognition parameters."""
    updates = req.model_dump(exclude_unset=True)
    cfg = update_vision_config(**updates)
    return {
        "status": "updated",
        "config": cfg.model_dump()
    }


@router.get("/registry", summary="List Registered Gestures")
async def list_gestures() -> List[GestureDefinition]:
    """Lists all available gestures, thresholds, cooldowns, and bound actions."""
    return gesture_registry.list_all()


@router.put("/registry/{gesture_name}", summary="Update Gesture Definition")
async def update_gesture(gesture_name: str, req: UpdateGestureDefinitionRequest) -> GestureDefinition:
    """Updates configuration or enabled state for a specific registered gesture."""
    updates = req.model_dump(exclude_unset=True)
    updated = gesture_registry.update(gesture_name, **updates)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Gesture '{gesture_name}' not found in registry.")
    return updated
