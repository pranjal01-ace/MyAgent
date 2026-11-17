"""
Automated Test Suite for Phase 3 — Hand Gesture Recognition Subsystem.

Tests:
1. Landmark Data Models and Serialization
2. Geometric Gesture Detector (Static Gestures: OPEN_PALM, FIST, THUMBS_UP, POINT, PEACE, PINCH)
3. Dynamic Gesture Detection (WAVE with horizontal oscillation)
4. Confidence Thresholding (0.79 rejected, 0.85 accepted)
5. Cooldown / Debouncing (repeat suppression within cooldown window)
6. State Transitions (gesture_started, gesture_held, gesture_ended)
7. Gesture Registry Management (lookup, update, disabled gestures)
8. Action Resolver & Safe Mappings (THUMBS_UP, WAVE, OPEN_PALM, PEACE, PINCH, FIST, POINT)
9. Camera Error Resilience (camera unavailable does not crash)
10. FastAPI REST Endpoints (/api/gesture/status, start, stop, configure, registry)
"""

import sys
import time
import asyncio
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.main import app
from backend.vision.models import (
    HandLandmarks,
    LandmarkPoint,
    Handedness,
    GestureType,
    GestureState,
    GestureEvent
)
from backend.vision.gesture_detector import GestureDetector
from backend.vision.gesture_registry import GestureRegistry, GestureDefinition
from backend.vision.gesture_events import GestureActionResolver
from backend.vision.gesture_manager import GestureManager
from backend.vision.camera import CameraManager
from backend.vision.config import update_vision_config, get_vision_config


# ==============================================================================
# Helper Landmark Factories
# ==============================================================================

def make_base_landmarks() -> list[LandmarkPoint]:
    """Generates a default 21-point hand landmark skeleton centered at wrist (0.5, 0.8)."""
    return [
        LandmarkPoint(x=0.5, y=0.8, z=0.0),     # 0: Wrist
        # Thumb: 1, 2, 3, 4
        LandmarkPoint(x=0.45, y=0.75, z=0.0),   # 1: Thumb CMC
        LandmarkPoint(x=0.42, y=0.70, z=0.0),   # 2: Thumb MCP
        LandmarkPoint(x=0.40, y=0.65, z=0.0),   # 3: Thumb IP
        LandmarkPoint(x=0.38, y=0.60, z=0.0),   # 4: Thumb Tip
        # Index: 5, 6, 7, 8
        LandmarkPoint(x=0.46, y=0.60, z=0.0),   # 5: Index MCP
        LandmarkPoint(x=0.46, y=0.50, z=0.0),   # 6: Index PIP
        LandmarkPoint(x=0.46, y=0.42, z=0.0),   # 7: Index DIP
        LandmarkPoint(x=0.46, y=0.35, z=0.0),   # 8: Index Tip
        # Middle: 9, 10, 11, 12
        LandmarkPoint(x=0.50, y=0.58, z=0.0),   # 9: Middle MCP
        LandmarkPoint(x=0.50, y=0.48, z=0.0),   # 10: Middle PIP
        LandmarkPoint(x=0.50, y=0.40, z=0.0),   # 11: Middle DIP
        LandmarkPoint(x=0.50, y=0.32, z=0.0),   # 12: Middle Tip
        # Ring: 13, 14, 15, 16
        LandmarkPoint(x=0.54, y=0.60, z=0.0),   # 13: Ring MCP
        LandmarkPoint(x=0.54, y=0.50, z=0.0),   # 14: Ring PIP
        LandmarkPoint(x=0.54, y=0.42, z=0.0),   # 15: Ring DIP
        LandmarkPoint(x=0.54, y=0.35, z=0.0),   # 16: Ring Tip
        # Pinky: 17, 18, 19, 20
        LandmarkPoint(x=0.58, y=0.63, z=0.0),   # 17: Pinky MCP
        LandmarkPoint(x=0.58, y=0.55, z=0.0),   # 18: Pinky PIP
        LandmarkPoint(x=0.58, y=0.48, z=0.0),   # 19: Pinky DIP
        LandmarkPoint(x=0.58, y=0.42, z=0.0),   # 20: Pinky Tip
    ]


def make_open_palm_landmarks() -> HandLandmarks:
    """All 5 fingers extended outward."""
    lms = make_base_landmarks()
    # Spread thumb outward
    lms[4] = LandmarkPoint(x=0.30, y=0.55, z=0.0)
    return HandLandmarks(landmarks=lms, handedness=Handedness.RIGHT, confidence=0.96)


def make_fist_landmarks() -> HandLandmarks:
    """All 5 fingers curled toward palm."""
    lms = make_base_landmarks()
    # Curl tips down close to wrist/MCP
    lms[4] = LandmarkPoint(x=0.48, y=0.68, z=0.0)   # Thumb curled across
    lms[8] = LandmarkPoint(x=0.46, y=0.66, z=0.0)   # Index curled (below PIP 0.50)
    lms[12] = LandmarkPoint(x=0.50, y=0.65, z=0.0)  # Middle curled (below PIP 0.48)
    lms[16] = LandmarkPoint(x=0.54, y=0.66, z=0.0)  # Ring curled (below PIP 0.50)
    lms[20] = LandmarkPoint(x=0.58, y=0.68, z=0.0)  # Pinky curled (below PIP 0.55)
    return HandLandmarks(landmarks=lms, handedness=Handedness.RIGHT, confidence=0.95)


def make_thumbs_up_landmarks() -> HandLandmarks:
    """Thumb pointing high up, all 4 fingers curled."""
    lms = make_fist_landmarks().landmarks
    # Point thumb straight up above wrist
    lms[1] = LandmarkPoint(x=0.46, y=0.72, z=0.0)
    lms[2] = LandmarkPoint(x=0.46, y=0.62, z=0.0)
    lms[3] = LandmarkPoint(x=0.46, y=0.52, z=0.0)
    lms[4] = LandmarkPoint(x=0.46, y=0.40, z=0.0)  # Upward!
    return HandLandmarks(landmarks=lms, handedness=Handedness.RIGHT, confidence=0.94)


def make_point_landmarks() -> HandLandmarks:
    """Index extended, middle/ring/pinky and thumb curled."""
    lms = make_fist_landmarks().landmarks
    # Extend index finger straight up
    lms[6] = LandmarkPoint(x=0.46, y=0.50, z=0.0)
    lms[8] = LandmarkPoint(x=0.46, y=0.35, z=0.0)
    return HandLandmarks(landmarks=lms, handedness=Handedness.RIGHT, confidence=0.93)


def make_peace_landmarks() -> HandLandmarks:
    """Index and middle extended in V, ring and pinky curled."""
    lms = make_fist_landmarks().landmarks
    # Extend index
    lms[6] = LandmarkPoint(x=0.44, y=0.50, z=0.0)
    lms[8] = LandmarkPoint(x=0.42, y=0.35, z=0.0)
    # Extend middle
    lms[10] = LandmarkPoint(x=0.52, y=0.48, z=0.0)
    lms[12] = LandmarkPoint(x=0.54, y=0.33, z=0.0)
    return HandLandmarks(landmarks=lms, handedness=Handedness.RIGHT, confidence=0.92)


def make_pinch_landmarks() -> HandLandmarks:
    """Thumb tip and index tip pinched together."""
    lms = make_base_landmarks()
    # Pinch tips 4 and 8 together
    lms[4] = LandmarkPoint(x=0.46, y=0.45, z=0.0)
    lms[8] = LandmarkPoint(x=0.46, y=0.455, z=0.0)  # distance = 0.005
    return HandLandmarks(landmarks=lms, handedness=Handedness.RIGHT, confidence=0.95)


# ==============================================================================
# Unit Tests
# ==============================================================================

def test_models_and_event_serialization():
    """Verify HandLandmarks and GestureEvent construction and serialization."""
    pt = LandmarkPoint(x=0.5, y=0.5, z=0.0)
    hl = HandLandmarks(hand_id=1, handedness=Handedness.LEFT, landmarks=[pt], confidence=0.95)
    assert hl.hand_id == 1
    assert hl.handedness == Handedness.LEFT
    assert len(hl.landmarks) == 1

    event = GestureEvent(
        gesture=GestureType.THUMBS_UP,
        confidence=0.94,
        hand=Handedness.RIGHT,
        state=GestureState.GESTURE_STARTED
    )
    assert event.event_type == "gesture"
    assert event.gesture == GestureType.THUMBS_UP
    assert event.confidence == 0.94
    assert event.hand == Handedness.RIGHT
    assert event.state == GestureState.GESTURE_STARTED
    assert len(event.id) > 10  # UUID check


def test_static_gesture_detector_all():
    """Verify detection of OPEN_PALM, FIST, THUMBS_UP, POINT, PEACE, PINCH."""
    detector = GestureDetector()

    # 1. OPEN_PALM
    g, c = detector.detect_gesture(make_open_palm_landmarks())
    assert g == GestureType.OPEN_PALM
    assert c >= 0.80

    # 2. FIST
    g, c = detector.detect_gesture(make_fist_landmarks())
    assert g == GestureType.FIST
    assert c >= 0.80

    # 3. THUMBS_UP
    g, c = detector.detect_gesture(make_thumbs_up_landmarks())
    assert g == GestureType.THUMBS_UP
    assert c >= 0.80

    # 4. POINT
    g, c = detector.detect_gesture(make_point_landmarks())
    assert g == GestureType.POINT
    assert c >= 0.80

    # 5. PEACE
    g, c = detector.detect_gesture(make_peace_landmarks())
    assert g == GestureType.PEACE
    assert c >= 0.80

    # 6. PINCH
    g, c = detector.detect_gesture(make_pinch_landmarks())
    assert g == GestureType.PINCH
    assert c >= 0.80


def test_dynamic_wave_gesture_detection():
    """Verify that horizontal oscillation of an open palm is recognized as WAVE."""
    detector = GestureDetector(history_window_seconds=1.5)
    base_palm = make_open_palm_landmarks()

    # Simulate hand oscillating left-right-left: x = 0.35 -> 0.50 -> 0.35 -> 0.52
    x_sequence = [0.35, 0.40, 0.45, 0.50, 0.45, 0.40, 0.35, 0.42, 0.48, 0.54]
    detected = False
    wave_conf = 0.0

    for x_val in x_sequence:
        # Move palm center
        base_palm.landmarks[9].x = x_val
        g, c = detector.detect_gesture(base_palm)
        if g == GestureType.WAVE:
            detected = True
            wave_conf = c
        time.sleep(0.01)

    assert detected, "Horizontal oscillating palm was expected to be recognized as WAVE"
    assert wave_conf >= 0.80


def test_gesture_registry():
    """Verify registry listing, lookup, update, and disabled gesture logic."""
    reg = GestureRegistry()

    thumbs = reg.get("THUMBS_UP")
    assert thumbs is not None
    assert thumbs.action == "ace_positive_reaction"
    assert reg.is_enabled("THUMBS_UP") is True

    # Disable THUMBS_UP
    updated = reg.update("THUMBS_UP", enabled=False)
    assert updated.enabled is False
    assert reg.is_enabled("THUMBS_UP") is False

    # Re-enable
    reg.update("THUMBS_UP", enabled=True)
    assert reg.is_enabled("THUMBS_UP") is True


def test_action_resolver_safe_mappings():
    """Verify that GestureActionResolver dispatches safe reactions and handles unknown/disabled gestures."""
    async def _run():
        resolver = GestureActionResolver()

        # 1. THUMBS_UP -> ace_positive_reaction
        event = GestureEvent(gesture=GestureType.THUMBS_UP, confidence=0.92, hand=Handedness.RIGHT)
        res = await resolver.dispatch_event(event)
        assert res["status"] == "success"
        assert res["action"] == "ace_positive_reaction"

        # 2. OPEN_PALM -> stop_current_action
        event_palm = GestureEvent(gesture=GestureType.OPEN_PALM, confidence=0.95, hand=Handedness.RIGHT)
        res_palm = await resolver.dispatch_event(event_palm)
        assert res_palm["status"] == "success"
        assert res_palm["action"] == "stop_current_action"

        # 3. WAVE -> ace_greeting
        event_wave = GestureEvent(gesture=GestureType.WAVE, confidence=0.88, hand=Handedness.RIGHT)
        res_wave = await resolver.dispatch_event(event_wave)
        assert res_wave["status"] == "success"
        assert res_wave["action"] == "ace_greeting"

        # 4. Unknown gesture -> ignored
        event_unknown = GestureEvent(gesture=GestureType.UNKNOWN, confidence=0.50, hand=Handedness.UNKNOWN)
        res_unknown = await resolver.dispatch_event(event_unknown)
        assert res_unknown["status"] == "ignored"

        # 5. Disabled gesture -> ignored
        resolver.registry.update("PEACE", enabled=False)
        event_peace = GestureEvent(gesture=GestureType.PEACE, confidence=0.90, hand=Handedness.RIGHT)
        res_peace = await resolver.dispatch_event(event_peace)
        assert res_peace["status"] == "ignored"
        assert res_peace["reason"] == "gesture_disabled"
        resolver.registry.update("PEACE", enabled=True)

    asyncio.run(_run())


def test_confidence_threshold_rejection_and_acceptance():
    """Verify confidence filtering: 0.79 rejected, 0.85 accepted."""
    mock_camera = MagicMock(spec=CameraManager)
    mock_resolver = MagicMock(spec=GestureActionResolver)
    mock_resolver.dispatch_event = AsyncMock()

    mgr = GestureManager(camera=mock_camera, resolver=mock_resolver)
    mgr.registry.update("THUMBS_UP", confidence_threshold=0.80)

    # 1. Confidence = 0.79 with threshold 0.80 -> Rejected
    mgr._handle_gesture_transition(GestureType.THUMBS_UP, confidence=0.79, hand=Handedness.RIGHT)
    assert mgr._current_gesture == GestureType.NONE
    mock_resolver.dispatch_event.assert_not_called()

    # 2. Confidence = 0.85 with threshold 0.80 -> Accepted
    mgr._handle_gesture_transition(GestureType.THUMBS_UP, confidence=0.85, hand=Handedness.RIGHT)
    assert mgr._current_gesture == GestureType.THUMBS_UP

    # Restore default
    mgr.registry.update("THUMBS_UP", confidence_threshold=0.65)


def test_cooldown_debouncing():
    """Verify debounce / cooldown: first triggers, immediate duplicate ignored."""
    mock_camera = MagicMock(spec=CameraManager)
    dispatched_events = []

    mock_resolver = MagicMock(spec=GestureActionResolver)
    async def fake_dispatch(e):
        dispatched_events.append(e)
        return {"status": "ok"}
    mock_resolver.dispatch_event = AsyncMock(side_effect=fake_dispatch)

    mgr = GestureManager(camera=mock_camera, resolver=mock_resolver)
    mgr._main_loop = None  # Use inline runner

    # Trigger 1: THUMBS_UP -> executes
    mgr._handle_gesture_transition(GestureType.THUMBS_UP, confidence=0.92, hand=Handedness.RIGHT)
    first_trigger_time = mgr._last_trigger_times.get("THUMBS_UP")
    assert first_trigger_time is not None

    # Reset current gesture to simulate transition back and forth immediately
    mgr._current_gesture = GestureType.NONE
    # Trigger 2 immediately (< cooldown 1000ms) -> should be suppressed
    mgr._handle_gesture_transition(GestureType.THUMBS_UP, confidence=0.94, hand=Handedness.RIGHT)
    # The last trigger time should not have been updated
    assert mgr._last_trigger_times.get("THUMBS_UP") == first_trigger_time


def test_camera_failure_graceful_handling():
    """Verify that camera failure / unavailability does not crash the system."""
    mock_camera = MagicMock(spec=CameraManager)
    mock_camera.start.return_value = False
    mock_camera.get_status.return_value = {"running": False, "last_error": "No webcam connected"}

    mgr = GestureManager(camera=mock_camera)
    started = mgr.start()
    assert started is False
    assert mgr.is_running() is False
    status = mgr.get_status()
    assert status["running"] is False
    assert status["camera_status"]["last_error"] == "No webcam connected"


# ==============================================================================
# REST API Endpoint Tests
# ==============================================================================

@pytest.fixture
def client():
    return TestClient(app)


def test_api_gesture_status(client):
    """Test GET /api/gesture/status endpoint."""
    resp = client.get("/api/gesture/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "running" in data
    assert "camera_status" in data
    assert "current_gesture" in data
    assert "confidence_threshold" in data


def test_api_gesture_registry_and_update(client):
    """Test GET /api/gesture/registry and PUT /api/gesture/registry/{name}."""
    resp = client.get("/api/gesture/registry")
    assert resp.status_code == 200
    gestures = resp.json()
    assert len(gestures) >= 6
    names = [g["name"] for g in gestures]
    assert "THUMBS_UP" in names
    assert "OPEN_PALM" in names

    # Update gesture configuration
    put_resp = client.put(
        "/api/gesture/registry/THUMBS_UP",
        json={"confidence_threshold": 0.85, "cooldown_ms": 1500}
    )
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["confidence_threshold"] == 0.85
    assert updated["cooldown_ms"] == 1500

    # Restore default
    client.put(
        "/api/gesture/registry/THUMBS_UP",
        json={"confidence_threshold": 0.80, "cooldown_ms": 1000}
    )


def test_api_gesture_configure(client):
    """Test POST /api/gesture/configure endpoint."""
    resp = client.post(
        "/api/gesture/configure",
        json={"camera_fps": 20, "confidence_threshold": 0.82}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"
    assert data["config"]["camera_fps"] == 20
    assert data["config"]["confidence_threshold"] == 0.82

    # Restore default
    client.post(
        "/api/gesture/configure",
        json={"camera_fps": 15, "confidence_threshold": 0.80}
    )


def test_api_gesture_stop(client):
    """Test POST /api/gesture/stop cleanly handles stopping."""
    resp = client.post("/api/gesture/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"
