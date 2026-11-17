"""
Manual Developer Test Bench for Phase 3 Hand Gesture Recognition.

Runs local webcam capture, MediaPipe hand tracking, and gesture detection.
Displays real-time diagnostic output:
Camera: ON
Hand detected: YES
Hand: RIGHT
Gesture: THUMBS_UP
Confidence: 94%
Cooldown: READY

Usage:
  python test_bench/manual_gesture_test.py [--preview] [--camera 0]
"""

import sys
import time
import argparse
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.vision.camera import CameraManager
from backend.vision.hand_tracker import HandTracker
from backend.vision.gesture_detector import GestureDetector
from backend.vision.models import GestureType, Handedness

# Standard 21-point hand landmark skeleton connections
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),          # Index
    (5, 9), (9, 10), (10, 11), (11, 12),     # Middle
    (9, 13), (13, 14), (14, 15), (15, 16),   # Ring
    (13, 17), (17, 18), (18, 19), (19, 20),  # Pinky
    (0, 17)                                  # Palm base
]


def main():
    parser = argparse.ArgumentParser(description="Ace AI Hand Gesture Manual Test Bench")
    parser.add_argument("--camera", type=int, default=0, help="Camera device index (default: 0)")
    parser.add_argument("--preview", action="store_true", help="Show live OpenCV visual preview window")
    parser.add_argument("--fps", type=int, default=15, help="Target FPS (default: 15)")
    args = parser.parse_args()

    print("=" * 60)
    print("🔥 Ace AI Companion — Phase 3 Gesture Recognition Test Bench")
    print("=" * 60)
    print(f"Target Camera Index: {args.camera}")
    print(f"Visual Preview: {'ENABLED' if args.preview else 'DISABLED (Terminal Only)'}")
    print("Tip: Raise your hand into the camera frame (about 1.5 - 2.5 ft away).")
    print("Press Ctrl+C (or 'q' in preview window) to exit.\n")

    camera = CameraManager()
    tracker = HandTracker()
    detector = GestureDetector()

    if not camera.start(camera_index=args.camera, fps=args.fps):
        print(f"❌ Failed to open webcam at index {args.camera}.")
        sys.exit(1)

    if not tracker.initialize():
        print("❌ Failed to initialize MediaPipe HandTracker.")
        camera.stop()
        sys.exit(1)

    print("Camera initialized and tracking running...\n")

    if args.preview:
        import cv2
        cv2.namedWindow("Ace AI Gesture Test Bench", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Ace AI Gesture Test Bench", 800, 600)

    last_gesture = GestureType.NONE
    last_trigger_times = {}
    cooldown_sec = 1.0

    try:
        while True:
            t0 = time.monotonic()
            raw_frame = camera.read()
            if raw_frame is None:
                time.sleep(0.05)
                continue

            # Mirror frame horizontally so user movement feels natural like a mirror
            import cv2
            frame = cv2.flip(raw_frame, 1)

            hands = tracker.process_frame(frame)
            now = time.monotonic()

            h, w, _ = frame.shape

            if hands:
                hand = hands[0]
                gesture, confidence = detector.detect_gesture(hand)
                hand_detected = "YES"
                hand_side = hand.handedness.value
                conf_pct = f"{int(confidence * 100)}%"

                # Check cooldown status
                last_time = last_trigger_times.get(gesture.value, 0.0)
                rem = max(0.0, cooldown_sec - (now - last_time))
                cooldown_str = "READY" if rem <= 0.0 else f"{int(rem * 1000)}ms"

                status_line = (
                    f"\rCamera: ON | Hand detected: {hand_detected:3s} ({hand_side:5s}) | "
                    f"Gesture: {gesture.value:12s} | Confidence: {conf_pct:4s} | Cooldown: {cooldown_str:6s}"
                )
                sys.stdout.write(status_line)
                sys.stdout.flush()

                if gesture != last_gesture and gesture != GestureType.NONE and rem <= 0.0:
                    last_trigger_times[gesture.value] = now
                    print(f"\n  >> Triggered Gesture Action: [{gesture.value}] (Confidence: {conf_pct})")

                last_gesture = gesture

                if args.preview:
                    # Draw bones / connections
                    for p1_idx, p2_idx in HAND_CONNECTIONS:
                        if p1_idx < len(hand.landmarks) and p2_idx < len(hand.landmarks):
                            pt1 = hand.landmarks[p1_idx]
                            pt2 = hand.landmarks[p2_idx]
                            x1, y1 = int(pt1.x * w), int(pt1.y * h)
                            x2, y2 = int(pt2.x * w), int(pt2.y * h)
                            cv2.line(frame, (x1, y1), (x2, y2), (0, 200, 255), 2)

                    # Draw landmark nodes
                    for pt in hand.landmarks:
                        cx, cy = int(pt.x * w), int(pt.y * h)
                        cv2.circle(frame, (cx, cy), 5, (0, 255, 0), -1)
                        cv2.circle(frame, (cx, cy), 6, (0, 100, 0), 1)

                    # Top HUD overlay
                    cv2.rectangle(frame, (0, 0), (w, 75), (20, 20, 20), -1)
                    cv2.putText(
                        frame,
                        f"GESTURE: {gesture.value}",
                        (20, 38),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.0,
                        (0, 255, 255) if gesture != GestureType.NONE else (200, 200, 200),
                        2
                    )
                    cv2.putText(
                        frame,
                        f"Confidence: {conf_pct}  |  Hand: {hand_side}  |  Cooldown: {cooldown_str}",
                        (20, 65),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (180, 255, 180),
                        1
                    )
            else:
                last_gesture = GestureType.NONE
                sys.stdout.write(
                    f"\rCamera: ON | Hand detected: NO  (-----) | Gesture: NONE         | Confidence: 0%   | Cooldown: READY "
                )
                sys.stdout.flush()

                if args.preview:
                    # Top HUD overlay when searching
                    cv2.rectangle(frame, (0, 0), (w, 75), (20, 20, 20), -1)
                    cv2.putText(
                        frame,
                        "Searching for hand...",
                        (20, 38),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.9,
                        (0, 180, 255),
                        2
                    )
                    cv2.putText(
                        frame,
                        "Raise your hand into the camera view (1.5 - 2.5 ft away)",
                        (20, 65),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (200, 200, 200),
                        1
                    )

            # Timing and window event processing
            elapsed = time.monotonic() - t0
            sleep_needed = (1.0 / args.fps) - elapsed

            if args.preview:
                cv2.imshow("Ace AI Gesture Test Bench", frame)
                wait_ms = max(1, int(sleep_needed * 1000)) if sleep_needed > 0 else 1
                key = cv2.waitKey(wait_ms)
                if key & 0xFF == ord('q'):
                    break
            else:
                if sleep_needed > 0:
                    time.sleep(sleep_needed)

    except KeyboardInterrupt:
        print("\n\nStopping test bench...")
    finally:
        camera.stop()
        tracker.close()
        if args.preview:
            import cv2
            cv2.destroyAllWindows()
        print("Hardware released cleanly. Goodbye!")


if __name__ == "__main__":
    main()
