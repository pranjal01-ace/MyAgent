"""
Gesture Manager for Phase 3 Vision Subsystem.

Orchestrates the entire vision pipeline:
CameraManager -> HandTracker -> GestureDetector -> Debounce/Cooldown ->
State Transitions -> GestureRegistry -> GestureActionResolver.

Runs in an isolated background thread to guarantee zero blocking of the FastAPI event loop.
"""

import time
import uuid
import logging
import threading
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import numpy as np

from backend.vision.models import (
    HandLandmarks,
    GestureType,
    GestureState,
    GestureEvent,
    Handedness
)
from backend.vision.config import get_vision_config, VisionConfig
from backend.vision.camera import camera_manager, CameraManager
from backend.vision.hand_tracker import hand_tracker, HandTracker
from backend.vision.gesture_detector import gesture_detector, GestureDetector
from backend.vision.gesture_registry import gesture_registry, GestureRegistry
from backend.vision.gesture_events import gesture_action_resolver, GestureActionResolver

logger = logging.getLogger("ace.vision.manager")


class GestureManager:
    """
    Background worker managing the lifecycle of the webcam, hand tracking,
    gesture classification, debouncing, and action dispatching.
    """

    def __init__(
        self,
        camera: Optional[CameraManager] = None,
        tracker: Optional[HandTracker] = None,
        detector: Optional[GestureDetector] = None,
        registry: Optional[GestureRegistry] = None,
        resolver: Optional[GestureActionResolver] = None
    ):
        self.camera = camera or camera_manager
        self.tracker = tracker or hand_tracker
        self.detector = detector or gesture_detector
        self.registry = registry or gesture_registry
        self.resolver = resolver or gesture_action_resolver

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

        # Tracking state
        self._current_gesture: GestureType = GestureType.NONE
        self._current_hand: Handedness = Handedness.UNKNOWN
        self._gesture_start_time: float = 0.0
        self._last_trigger_times: Dict[str, float] = {}  # gesture_name -> timestamp
        self._last_detected_confidence: float = 0.0
        self._hand_present: bool = False
        self._frame_count: int = 0
        self._actual_fps: float = 0.0

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Sets the main asyncio loop for dispatching async events from background thread."""
        self._main_loop = loop

    def start(self, event_loop: Optional[asyncio.AbstractEventLoop] = None) -> bool:
        """
        Starts the camera capture and gesture detection background thread.
        """
        with self._lock:
            if self._running and self._thread is not None and self._thread.is_alive():
                logger.info("Gesture subsystem is already running.")
                return True

            if event_loop is not None:
                self._main_loop = event_loop
            elif self._main_loop is None:
                try:
                    self._main_loop = asyncio.get_running_loop()
                except RuntimeError:
                    self._main_loop = None

            cfg = get_vision_config()
            cam_started = self.camera.start(
                camera_index=cfg.camera_index,
                width=cfg.camera_width,
                height=cfg.camera_height,
                fps=cfg.camera_fps
            )

            if not cam_started:
                logger.error("Failed to start camera for gesture subsystem.")
                return False

            self.tracker.initialize()
            self.detector.reset_history()

            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(
                target=self._worker_loop,
                name="AceGestureWorker",
                daemon=True
            )
            self._thread.start()
            logger.info("Gesture subsystem started.")
            return True

    def stop(self) -> None:
        """
        Stops the gesture detection thread and safely releases camera hardware.
        """
        with self._lock:
            if not self._running:
                return

            self._running = False
            self._stop_event.set()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None

        self.camera.stop()
        self.tracker.close()
        logger.info("Gesture subsystem stopped.")

    def is_running(self) -> bool:
        """Returns True if the gesture manager is actively processing frames."""
        with self._lock:
            return self._running and self._thread is not None and self._thread.is_alive()

    def _worker_loop(self) -> None:
        """Main camera acquisition and gesture recognition loop running in background thread."""
        cfg = get_vision_config()
        target_fps = cfg.camera_fps or 15
        frame_interval = 1.0 / max(1, target_fps)

        fps_calc_time = time.monotonic()
        fps_frame_counter = 0

        while not self._stop_event.is_set() and self._running:
            loop_start = time.monotonic()

            try:
                frame = self.camera.read()
                if frame is not None:
                    self._process_frame(frame)
                    self._frame_count += 1
                    fps_frame_counter += 1
                else:
                    self._hand_present = False
                    self._handle_gesture_transition(GestureType.NONE, 0.0, Handedness.UNKNOWN)
                    time.sleep(0.02)
            except Exception as e:
                logger.error(f"Error in gesture processing worker loop: {e}")
                time.sleep(0.05)

            # Compute actual rolling FPS
            now = time.monotonic()
            if (now - fps_calc_time) >= 1.0:
                self._actual_fps = round(fps_frame_counter / (now - fps_calc_time), 1)
                fps_frame_counter = 0
                fps_calc_time = now

            # Rate limit loop to target FPS to ensure low CPU usage
            elapsed = time.monotonic() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _process_frame(self, frame: np.ndarray) -> None:
        """Runs hand tracking and gesture detection on a single frame."""
        hands = self.tracker.process_frame(frame)
        if not hands:
            self._hand_present = False
            self._handle_gesture_transition(GestureType.NONE, 0.0, Handedness.UNKNOWN)
            return

        self._hand_present = True
        # Process primary hand (index 0)
        primary_hand = hands[0]
        detected_gesture, confidence = self.detector.detect_gesture(primary_hand)
        self._last_detected_confidence = confidence

        self._handle_gesture_transition(detected_gesture, confidence, primary_hand.handedness)

    def _handle_gesture_transition(
        self,
        new_gesture: GestureType,
        confidence: float,
        hand: Handedness
    ) -> None:
        """
        Manages state transitions: started -> held -> ended,
        applies confidence thresholding and cooldown debouncing.
        """
        now = time.monotonic()

        # Check confidence threshold for non-NONE gestures
        cfg = get_vision_config()
        min_conf = cfg.confidence_threshold

        if new_gesture != GestureType.NONE and new_gesture != GestureType.UNKNOWN:
            defn = self.registry.get(new_gesture.value)
            if defn:
                min_conf = defn.confidence_threshold

            if confidence < min_conf:
                logger.debug(
                    f"Gesture rejected due to confidence: {new_gesture.value} "
                    f"({confidence:.2f} < {min_conf:.2f})"
                )
                new_gesture = GestureType.NONE

        prev_gesture = self._current_gesture

        # 1. Gesture Ended Transition
        if prev_gesture != GestureType.NONE and new_gesture != prev_gesture:
            duration_ms = (now - self._gesture_start_time) * 1000.0
            end_event = GestureEvent(
                gesture=prev_gesture,
                confidence=self._last_detected_confidence,
                hand=self._current_hand,
                state=GestureState.GESTURE_ENDED,
                duration_ms=round(duration_ms, 2)
            )
            self._dispatch_async(end_event)
            self._current_gesture = GestureType.NONE

        # 2. Gesture Started Transition
        if new_gesture != GestureType.NONE and new_gesture != prev_gesture:
            self._current_gesture = new_gesture
            self._current_hand = hand
            self._gesture_start_time = now

            # Check cooldown / debouncing
            gesture_key = new_gesture.value
            last_triggered = self._last_trigger_times.get(gesture_key, 0.0)
            defn = self.registry.get(gesture_key)
            cooldown_ms = defn.cooldown_ms if defn else cfg.cooldown_ms
            cooldown_sec = cooldown_ms / 1000.0

            if (now - last_triggered) < cooldown_sec:
                logger.info(
                    f"Gesture ignored due to cooldown: {gesture_key} "
                    f"({(now - last_triggered)*1000:.0f}ms < {cooldown_ms}ms)"
                )
                return

            self._last_trigger_times[gesture_key] = now
            start_event = GestureEvent(
                gesture=new_gesture,
                confidence=confidence,
                hand=hand,
                state=GestureState.GESTURE_STARTED,
                duration_ms=0.0
            )
            self._dispatch_async(start_event)

        # 3. Gesture Held State
        elif new_gesture != GestureType.NONE and new_gesture == prev_gesture:
            duration_ms = (now - self._gesture_start_time) * 1000.0
            # Emit held state periodically (e.g. every 500ms) if needed
            pass

    def _dispatch_async(self, event: GestureEvent) -> None:
        """Dispatches event to resolver in thread-safe manner."""
        if self._main_loop and self._main_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.resolver.dispatch_event(event),
                self._main_loop
            )
        else:
            # Fallback for standalone / non-loop environments
            def _runner():
                asyncio.run(self.resolver.dispatch_event(event))
            threading.Thread(target=_runner, daemon=True).start()

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive real-time status of the gesture recognition subsystem."""
        cfg = get_vision_config()
        now = time.monotonic()
        curr_name = self._current_gesture.value

        # Calculate cooldown status
        last_triggered = self._last_trigger_times.get(curr_name, 0.0)
        defn = self.registry.get(curr_name)
        cooldown_ms = defn.cooldown_ms if defn else cfg.cooldown_ms
        cooldown_sec = cooldown_ms / 1000.0
        remaining_cd = max(0.0, cooldown_sec - (now - last_triggered))

        return {
            "running": self.is_running(),
            "camera_status": self.camera.get_status(),
            "hand_detected": self._hand_present,
            "hand": self._current_hand.value if self._hand_present else "NONE",
            "current_gesture": curr_name,
            "confidence": round(self._last_detected_confidence, 2),
            "cooldown_status": "READY" if remaining_cd <= 0.0 else f"{int(remaining_cd*1000)}ms",
            "actual_fps": self._actual_fps,
            "target_fps": cfg.camera_fps,
            "confidence_threshold": cfg.confidence_threshold,
            "cooldown_ms": cfg.cooldown_ms,
            "frames_processed": self._frame_count
        }


# Global singleton gesture manager
gesture_manager = GestureManager()
