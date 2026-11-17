"""
Vision & Hand Gesture Recognition Subsystem (Phase 3).

Provides real-time local webcam acquisition, MediaPipe hand tracking,
gesture detection, debouncing/cooldown, state transitions, and safe action dispatching.
"""

from backend.vision.models import (
    Handedness,
    LandmarkPoint,
    HandLandmarks,
    GestureType,
    GestureState,
    GestureEvent
)
from backend.vision.config import vision_config, get_vision_config, update_vision_config
from backend.vision.camera import camera_manager, CameraManager
from backend.vision.hand_tracker import hand_tracker, HandTracker
from backend.vision.gesture_detector import gesture_detector, GestureDetector
from backend.vision.gesture_registry import gesture_registry, GestureRegistry, GestureDefinition
from backend.vision.gesture_events import gesture_action_resolver, GestureActionResolver
from backend.vision.gesture_manager import gesture_manager, GestureManager

__all__ = [
    "Handedness",
    "LandmarkPoint",
    "HandLandmarks",
    "GestureType",
    "GestureState",
    "GestureEvent",
    "vision_config",
    "get_vision_config",
    "update_vision_config",
    "camera_manager",
    "CameraManager",
    "hand_tracker",
    "HandTracker",
    "gesture_detector",
    "GestureDetector",
    "gesture_registry",
    "GestureRegistry",
    "GestureDefinition",
    "gesture_action_resolver",
    "GestureActionResolver",
    "gesture_manager",
    "GestureManager",
]
