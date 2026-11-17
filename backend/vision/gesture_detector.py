"""
Gesture Detector for Phase 3 Vision Subsystem.

Classifies HandLandmarks into normalized GestureType classifications.
Combines Google's pre-trained neural gesture predictions with robust geometric
and temporal motion tracking (WAVE, PINCH).
"""

import math
import time
from collections import deque
from typing import Tuple, List, Optional, Deque

from backend.vision.models import HandLandmarks, LandmarkPoint, GestureType, Handedness

# Mapping from MediaPipe neural gesture categories to Ace domain GestureType
NEURAL_GESTURE_MAP = {
    "thumb_up": GestureType.THUMBS_UP,
    "open_palm": GestureType.OPEN_PALM,
    "closed_fist": GestureType.FIST,
    "pointing_up": GestureType.POINT,
    "victory": GestureType.PEACE,
}


def _euclidean_dist(p1: LandmarkPoint, p2: LandmarkPoint) -> float:
    """Calculates 2D Euclidean distance between two landmark points."""
    return math.hypot(p1.x - p2.x, p1.y - p2.y)


class GestureDetector:
    """
    Evaluates geometric hand landmark relations and neural gesture predictions to detect:
    - Static: OPEN_PALM, FIST, THUMBS_UP, POINT, PEACE, PINCH
    - Dynamic: WAVE
    """

    def __init__(self, history_window_seconds: float = 1.2):
        self._history_window = history_window_seconds
        # Deque of (timestamp: float, x: float, is_open: bool)
        self._motion_history: Deque[Tuple[float, float, bool]] = deque(maxlen=30)

    def reset_history(self) -> None:
        """Clears movement history."""
        self._motion_history.clear()

    def detect_gesture(self, hand: HandLandmarks) -> Tuple[GestureType, float]:
        """
        Analyzes HandLandmarks and returns (GestureType, confidence: float).
        """
        if not hand or not hand.landmarks or len(hand.landmarks) < 21:
            return GestureType.NONE, 0.0

        lm = hand.landmarks
        wrist = lm[0]

        # -------------------------------------------------------------
        # 1. Finger extension / posture measurement
        # -------------------------------------------------------------
        index_ext = _euclidean_dist(lm[8], wrist) > _euclidean_dist(lm[6], wrist) * 1.12
        middle_ext = _euclidean_dist(lm[12], wrist) > _euclidean_dist(lm[10], wrist) * 1.12
        ring_ext = _euclidean_dist(lm[16], wrist) > _euclidean_dist(lm[14], wrist) * 1.12
        pinky_ext = _euclidean_dist(lm[20], wrist) > _euclidean_dist(lm[18], wrist) * 1.12

        palm_center = lm[9]
        thumb_ext = _euclidean_dist(lm[4], palm_center) > _euclidean_dist(lm[2], palm_center) * 1.15
        pinch_dist = _euclidean_dist(lm[4], lm[8])

        # -------------------------------------------------------------
        # 2. Dynamic WAVE Detection
        # -------------------------------------------------------------
        now = time.monotonic()
        is_open_posture = (
            (index_ext and middle_ext and ring_ext and pinky_ext) or
            (hand.ml_gesture and hand.ml_gesture.lower() == "open_palm")
        )
        self._motion_history.append((now, lm[9].x, is_open_posture))

        while self._motion_history and (now - self._motion_history[0][0]) > self._history_window:
            self._motion_history.popleft()

        wave_detected, wave_conf = self._check_wave_motion()
        if wave_detected:
            return GestureType.WAVE, wave_conf

        # -------------------------------------------------------------
        # 3. Static PINCH / OK_SIGN Check
        # -------------------------------------------------------------
        # Pinch requires thumb tip and index tip in close proximity
        others_curled = (not index_ext) and (not middle_ext) and (not ring_ext) and (not pinky_ext)
        if pinch_dist < 0.068 and not (others_curled and not thumb_ext):
            pinch_conf = min(0.98, max(0.80, 1.0 - (pinch_dist / 0.08)))
            return GestureType.PINCH, round(pinch_conf, 2)

        # -------------------------------------------------------------
        # 4. Neural Gesture Prediction (MediaPipe ML model)
        # -------------------------------------------------------------
        if hand.ml_gesture:
            key = hand.ml_gesture.lower()
            if key in NEURAL_GESTURE_MAP and hand.ml_score >= 0.50:
                mapped_type = NEURAL_GESTURE_MAP[key]
                # Boost confidence from neural probability to match standard confidence scale
                boosted_conf = min(0.98, max(0.82, hand.ml_score + 0.15))
                return mapped_type, round(boosted_conf, 2)

        # -------------------------------------------------------------
        # 5. Geometric Rule Fallback (Robust static posture detection)
        # -------------------------------------------------------------

        # THUMBS_UP: Thumb pointing strictly up, all other 4 fingers curled
        thumb_pointing_up = (lm[4].y < lm[3].y < lm[2].y) and (lm[4].y < wrist.y - 0.08)
        if thumb_pointing_up and others_curled:
            conf = 0.94 if (lm[4].y < lm[2].y - 0.05) else 0.88
            return GestureType.THUMBS_UP, conf

        # FIST: All 5 fingers curled toward palm
        if others_curled and (not thumb_ext) and (not thumb_pointing_up):
            return GestureType.FIST, 0.95

        # OPEN_PALM: All 5 fingers extended outward
        if index_ext and middle_ext and ring_ext and pinky_ext and thumb_ext:
            return GestureType.OPEN_PALM, 0.96

        # PEACE: Index and Middle extended upright in V, Ring and Pinky curled
        if index_ext and middle_ext and (not ring_ext) and (not pinky_ext):
            tip_dist = _euclidean_dist(lm[8], lm[12])
            if tip_dist > 0.035:
                return GestureType.PEACE, 0.92
            else:
                return GestureType.PEACE, 0.86

        # POINT: Index extended, Middle, Ring, Pinky curled
        if index_ext and (not middle_ext) and (not ring_ext) and (not pinky_ext):
            return GestureType.POINT, 0.93

        return GestureType.UNKNOWN, 0.50

    def _check_wave_motion(self) -> Tuple[bool, float]:
        """
        Analyzes horizontal x-axis velocity oscillation over recent history.
        Requires at least 2 reversals of direction with significant displacement while hand is open.
        """
        if len(self._motion_history) < 8:
            return False, 0.0

        open_count = sum(1 for _, _, is_open in self._motion_history if is_open)
        if open_count < len(self._motion_history) * 0.5:
            return False, 0.0

        x_values = [x for _, x, _ in self._motion_history]
        dx = [x_values[i+1] - x_values[i] for i in range(len(x_values)-1)]

        threshold = 0.015
        directions = []
        for d in dx:
            if d > threshold:
                directions.append(1)
            elif d < -threshold:
                directions.append(-1)

        if not directions:
            return False, 0.0

        direction_changes = 0
        current_dir = directions[0]
        for d in directions[1:]:
            if d != current_dir:
                direction_changes += 1
                current_dir = d

        total_span = max(x_values) - min(x_values)
        if direction_changes >= 2 and total_span >= 0.08:
            conf = min(0.95, 0.82 + (direction_changes * 0.04))
            return True, round(conf, 2)

        return False, 0.0


# Global singleton detector
gesture_detector = GestureDetector()
