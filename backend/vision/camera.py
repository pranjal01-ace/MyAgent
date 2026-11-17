"""
Camera Manager for Phase 3 Vision Subsystem.

Responsible for:
- Opening the webcam using OpenCV
- Checking camera availability
- Reading video frames safely
- Configuring resolution and FPS
- Releasing hardware cleanly upon shutdown
- Preventing multiple concurrent camera instances via thread-safe locking
"""

import threading
import logging
from typing import Optional, Tuple
import cv2
import numpy as np

from backend.vision.config import get_vision_config

logger = logging.getLogger("ace.vision.camera")


class CameraManager:
    """
    Thread-safe camera abstraction for capturing frames from a local webcam.
    Prevents duplicate camera openings and ensures graceful hardware release.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cap: Optional[cv2.VideoCapture] = None
        self._is_running = False
        self._camera_index: int = 0
        self._width: int = 640
        self._height: int = 480
        self._fps: int = 15
        self._last_error: Optional[str] = None

    def start(
        self,
        camera_index: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None
    ) -> bool:
        """
        Initializes and opens the camera device.

        Returns True if camera opened successfully, False otherwise.
        """
        with self._lock:
            if self._is_running and self._cap is not None and self._cap.isOpened():
                logger.info("Camera is already active.")
                return True

            cfg = get_vision_config()
            self._camera_index = camera_index if camera_index is not None else cfg.camera_index
            self._width = width if width is not None else cfg.camera_width
            self._height = height if height is not None else cfg.camera_height
            self._fps = fps if fps is not None else cfg.camera_fps

            try:
                # Use DSHOW on Windows if available for faster initialization, with CAP_ANY fallback
                cap = cv2.VideoCapture(self._camera_index, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap.release()
                    cap = cv2.VideoCapture(self._camera_index)

                if not cap.isOpened():
                    err_msg = f"Failed to open webcam at index {self._camera_index}."
                    logger.warning(err_msg)
                    self._last_error = err_msg
                    self._is_running = False
                    return False

                # Configure resolution and target frame rate
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
                cap.set(cv2.CAP_PROP_FPS, self._fps)

                actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                actual_fps = cap.get(cv2.CAP_PROP_FPS)

                self._cap = cap
                self._is_running = True
                self._last_error = None
                logger.info(
                    f"Camera started successfully on index {self._camera_index} "
                    f"({actual_w}x{actual_h} @ {actual_fps:.1f} FPS)."
                )
                return True

            except Exception as e:
                err_msg = f"Unexpected error opening camera {self._camera_index}: {e}"
                logger.error(err_msg)
                self._last_error = err_msg
                self._is_running = False
                if self._cap:
                    try:
                        self._cap.release()
                    except Exception:
                        pass
                    self._cap = None
                return False

    def read(self) -> Optional[np.ndarray]:
        """
        Reads a single frame from the camera.

        Returns RGB numpy ndarray frame if successful, or None on failure/not running.
        """
        with self._lock:
            if not self._is_running or self._cap is None:
                return None

            try:
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    # Non-fatal frame drop
                    return None

                # Return frame (OpenCV defaults to BGR, caller or tracker handles color conversion)
                return frame
            except Exception as e:
                logger.error(f"Error reading frame from camera: {e}")
                return None

    def stop(self) -> None:
        """Stops the camera and releases device hardware cleanly."""
        with self._lock:
            if not self._is_running and self._cap is None:
                return

            try:
                if self._cap is not None:
                    self._cap.release()
                    self._cap = None
                logger.info("Camera stopped and hardware released.")
            except Exception as e:
                logger.error(f"Error releasing camera: {e}")
            finally:
                self._is_running = False

    def is_running(self) -> bool:
        """Returns True if the camera is currently opened and active."""
        with self._lock:
            return self._is_running and self._cap is not None and self._cap.isOpened()

    def get_status(self) -> dict:
        """Returns camera diagnostic status."""
        with self._lock:
            return {
                "running": self._is_running and self._cap is not None and self._cap.isOpened(),
                "camera_index": self._camera_index,
                "width": self._width,
                "height": self._height,
                "fps": self._fps,
                "last_error": self._last_error
            }


# Global singleton camera manager instance
camera_manager = CameraManager()
