"""
Domain models and data contracts for Phase 3 Vision & Gesture Recognition subsystem.

Provides clean abstractions decoupled from MediaPipe internals.
"""

from __future__ import annotations
import enum
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class Handedness(str, enum.Enum):
    """Handedness classification."""
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    UNKNOWN = "UNKNOWN"


class LandmarkPoint(BaseModel):
    """Normalized 3D hand landmark coordinate."""
    x: float = Field(..., description="Normalized X coordinate [0.0, 1.0]")
    y: float = Field(..., description="Normalized Y coordinate [0.0, 1.0]")
    z: float = Field(default=0.0, description="Normalized depth Z coordinate")


class HandLandmarks(BaseModel):
    """
    Normalized hand landmarks representation.
    Decoupled from underlying MediaPipe landmark classes.
    """
    hand_id: int = Field(default=0, description="Tracking index of detected hand")
    handedness: Handedness = Field(default=Handedness.RIGHT, description="Handedness (LEFT or RIGHT)")
    landmarks: List[LandmarkPoint] = Field(default_factory=list, description="21 standard landmark points")
    confidence: float = Field(default=1.0, description="Detection confidence [0.0, 1.0]")
    ml_gesture: Optional[str] = Field(default=None, description="Neural ML classified gesture if available")
    ml_score: float = Field(default=0.0, description="Neural ML classification confidence score")


class GestureType(str, enum.Enum):
    """Supported gesture classifications."""
    NONE = "NONE"
    OPEN_PALM = "OPEN_PALM"
    FIST = "FIST"
    THUMBS_UP = "THUMBS_UP"
    POINT = "POINT"
    PEACE = "PEACE"
    PINCH = "PINCH"
    WAVE = "WAVE"
    UNKNOWN = "UNKNOWN"


class GestureState(str, enum.Enum):
    """Gesture lifecycle transition state."""
    GESTURE_STARTED = "gesture_started"
    GESTURE_HELD = "gesture_held"
    GESTURE_ENDED = "gesture_ended"


class GestureEvent(BaseModel):
    """Normalized gesture event emitted when a valid gesture is recognized."""
    event_type: str = Field(default="gesture", description="Event classification identifier")
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Globally unique event UUID"
    )
    gesture: GestureType = Field(..., description="Recognized gesture type")
    confidence: float = Field(..., description="Detection confidence score [0.0, 1.0]")
    hand: Handedness = Field(default=Handedness.RIGHT, description="Hand that produced the gesture")
    state: GestureState = Field(default=GestureState.GESTURE_STARTED, description="Gesture lifecycle state")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Event creation UTC timestamp"
    )
    duration_ms: float = Field(default=0.0, description="Elapsed gesture duration in milliseconds")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Auxiliary event metadata")
