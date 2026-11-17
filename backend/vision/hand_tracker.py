"""
Hand Tracking Module for Phase 3 Vision Subsystem.

Wraps MediaPipe GestureRecognizer and HandLandmarker in CPU-friendly mode,
isolating all MediaPipe-specific objects from the rest of the application
and returning clean domain HandLandmarks models with neural gesture scores.
"""

import os
import urllib.request
import logging
from pathlib import Path
from typing import List, Optional
import numpy as np

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    GestureRecognizer,
    GestureRecognizerOptions,
    HandLandmarker,
    HandLandmarkerOptions,
    RunningMode
)

from backend.vision.models import HandLandmarks, LandmarkPoint, Handedness
from backend.vision.config import get_vision_config
from backend.core.config import BASE_DIR

logger = logging.getLogger("ace.vision.tracker")

GESTURE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task"
)
LANDMARK_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)


class HandTracker:
    """
    Tracks hand landmarks and neural gesture predictions using MediaPipe.
    Outputs normalized HandLandmarks decoupled from MediaPipe internals.
    """

    def __init__(self, model_path: Optional[str] = None):
        self._model_path = model_path
        self._recognizer: Optional[GestureRecognizer] = None
        self._landmarker: Optional[HandLandmarker] = None
        self._initialized = False

    def _ensure_model(self) -> Path:
        """Verifies or downloads the gesture_recognizer.task or hand_landmarker.task model locally."""
        if self._model_path:
            p = Path(self._model_path)
            if not p.is_absolute():
                p = BASE_DIR / p
            if p.exists() and p.stat().st_size > 1000000:
                return p

        # Prefer gesture_recognizer.task which bundles full landmarks + neural classification
        gesture_model_path = BASE_DIR / "data" / "models" / "gesture_recognizer.task"
        if gesture_model_path.exists() and gesture_model_path.stat().st_size > 1000000:
            return gesture_model_path

        gesture_model_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloading MediaPipe Gesture Recognizer model to {gesture_model_path}...")
        try:
            urllib.request.urlretrieve(GESTURE_MODEL_URL, str(gesture_model_path))
            logger.info("Gesture Recognizer model downloaded successfully.")
            return gesture_model_path
        except Exception as e:
            logger.warning(f"Could not download gesture_recognizer model: {e}. Trying hand_landmarker fallback...")

        # Fallback to hand_landmarker.task
        landmark_model_path = BASE_DIR / "data" / "models" / "hand_landmarker.task"
        if landmark_model_path.exists() and landmark_model_path.stat().st_size > 1000000:
            return landmark_model_path

        urllib.request.urlretrieve(LANDMARK_MODEL_URL, str(landmark_model_path))
        return landmark_model_path

    def initialize(self) -> bool:
        """Initializes the MediaPipe recognition pipeline."""
        if self._initialized and (self._recognizer is not None or self._landmarker is not None):
            return True

        try:
            model_file = self._ensure_model()

            if "gesture_recognizer" in model_file.name:
                options = GestureRecognizerOptions(
                    base_options=BaseOptions(model_asset_path=str(model_file)),
                    running_mode=RunningMode.IMAGE,
                    num_hands=2,
                    min_hand_detection_confidence=0.35,
                    min_hand_presence_confidence=0.35,
                    min_tracking_confidence=0.35
                )
                self._recognizer = GestureRecognizer.create_from_options(options)
                logger.info("MediaPipe GestureRecognizer initialized with neural classifier.")
            else:
                options = HandLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=str(model_file)),
                    running_mode=RunningMode.IMAGE,
                    num_hands=2,
                    min_hand_detection_confidence=0.35,
                    min_hand_presence_confidence=0.35,
                    min_tracking_confidence=0.35
                )
                self._landmarker = HandLandmarker.create_from_options(options)
                logger.info("MediaPipe HandLandmarker initialized successfully.")

            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize MediaPipe Tracker: {e}")
            self._initialized = False
            self._recognizer = None
            self._landmarker = None
            return False

    def process_frame(self, bgr_frame: np.ndarray) -> List[HandLandmarks]:
        """
        Processes a single BGR OpenCV frame and returns detected HandLandmarks.
        Returns empty list if no hand is detected or if tracker fails.
        """
        if not self._initialized or (self._recognizer is None and self._landmarker is None):
            if not self.initialize():
                return []

        if bgr_frame is None or bgr_frame.size == 0:
            return []

        try:
            import cv2
            rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
            rgb_frame = np.ascontiguousarray(rgb_frame)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

            if self._recognizer is not None:
                result = self._recognizer.recognize(mp_image)
            else:
                result = self._landmarker.detect(mp_image)

            if not result or not result.hand_landmarks:
                return []

            detected_hands: List[HandLandmarks] = []

            for idx, raw_landmarks in enumerate(result.hand_landmarks):
                # Extract handedness
                hand_type = Handedness.UNKNOWN
                conf = 0.90
                if result.handedness and idx < len(result.handedness):
                    categories = result.handedness[idx]
                    if categories:
                        cat = categories[0]
                        cat_name = cat.category_name.upper() if hasattr(cat, "category_name") else ""
                        if "RIGHT" in cat_name:
                            hand_type = Handedness.RIGHT
                        elif "LEFT" in cat_name:
                            hand_type = Handedness.LEFT
                        if hasattr(cat, "score"):
                            conf = float(cat.score)

                # Extract neural gesture if available
                ml_gesture = None
                ml_score = 0.0
                if hasattr(result, "gestures") and result.gestures and idx < len(result.gestures):
                    g_list = result.gestures[idx]
                    if g_list:
                        top_g = g_list[0]
                        cat_name = getattr(top_g, "category_name", None)
                        if cat_name and cat_name.lower() != "none":
                            ml_gesture = cat_name
                            ml_score = float(getattr(top_g, "score", 0.0))

                # Convert landmark points
                points: List[LandmarkPoint] = [
                    LandmarkPoint(
                        x=float(lm.x),
                        y=float(lm.y),
                        z=float(getattr(lm, "z", 0.0))
                    )
                    for lm in raw_landmarks
                ]

                detected_hands.append(
                    HandLandmarks(
                        hand_id=idx,
                        handedness=hand_type,
                        landmarks=points,
                        confidence=round(conf, 3),
                        ml_gesture=ml_gesture,
                        ml_score=round(ml_score, 3)
                    )
                )

            return detected_hands

        except Exception as e:
            logger.error(f"Error during hand tracking inference: {e}")
            return []

    def close(self) -> None:
        """Releases MediaPipe resources."""
        if self._recognizer is not None:
            try:
                self._recognizer.close()
            except Exception:
                pass
            self._recognizer = None
        if self._landmarker is not None:
            try:
                self._landmarker.close()
            except Exception:
                pass
            self._landmarker = None
        self._initialized = False


# Global singleton hand tracker
hand_tracker = HandTracker()
