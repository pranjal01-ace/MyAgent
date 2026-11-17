import sys
import math
import random
import logging
from pathlib import Path

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGraphicsOpacityEffect
from PyQt5.QtCore import Qt, QTimer, QPointF, QUrl, pyqtSignal as Signal
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QLinearGradient, QRadialGradient, QFont
)

logger = logging.getLogger("desktop.living_character")

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_AVAILABLE = True
except ImportError:
    WEBENGINE_AVAILABLE = False


class NativeLivingCharacter(QWidget):
    """Native PyQt QPainter procedural living character with:
    - Real-time mouth speaking lip-sync animation
    - Natural random eye blinking system
    - Articulated living hand & arm gestures (speaking gestures, chin-thinking pose, idle sway)
    - Interactive cursor gaze tracking
    - Dynamic breathing physics & Ace flame aura
    """
    state_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_state = "IDLE" # IDLE, LISTENING, THINKING, SPEAKING, HAPPY
        self.scale_factor = 1.0
        self.opacity_val = 1.0

        # Animation state variables
        self.time_counter = 0.0
        self.blink_progress = 0.0 # 0.0 (open) to 1.0 (closed)
        self.is_blinking = False
        self.next_blink_time = random.uniform(2.0, 4.5)
        self.blink_timer_acc = 0.0

        # Mouth Lip Sync
        self.mouth_openness = 0.0 # 0.0 (closed) to 1.0 (wide open)
        self.mouth_width = 1.0
        self.talk_phase = 0.0

        # Hand / Arm Gestures
        self.left_arm_angle = 0.0 # Radians
        self.right_arm_angle = 0.0
        self.left_hand_y = 0.0
        self.right_hand_y = 0.0
        self.gesture_phase = 0.0

        # Breathing & Body Physics
        self.breath_y = 0.0
        self.head_tilt = 0.0

        # Gaze tracking target offset
        self.target_gaze = QPointF(0, 0)
        self.current_gaze = QPointF(0, 0)

        # Enable mouse tracking for gaze
        self.setMouseTracking(True)

        # Frame animation timer (~60 FPS)
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(16)
        self.anim_timer.timeout.connect(self._on_anim_frame)
        self.anim_timer.start()

    def set_state(self, state: str):
        state_upper = state.upper()
        if state_upper == "TALKING":
            state_upper = "SPEAKING"
        if state_upper not in ["IDLE", "LISTENING", "THINKING", "SPEAKING", "HAPPY", "CONFUSED", "ERROR"]:
            state_upper = "IDLE"

        if self.current_state != state_upper:
            self.current_state = state_upper
            self.state_changed.emit(self.current_state)

    def set_scale(self, scale: float):
        self.scale_factor = max(0.2, min(3.0, scale))
        self.update()

    def set_opacity(self, opacity: float):
        self.opacity_val = max(0.1, min(1.0, opacity))
        self.update()

    def update_gaze_target(self, cursor_pos: QPointF):
        """Update eye pupil gaze direction relative to widget center."""
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        dx = (cursor_pos.x() - center.x()) / max(1.0, self.width())
        dy = (cursor_pos.y() - center.y()) / max(1.0, self.height())
        # Clamp gaze range
        dx = max(-1.0, min(1.0, dx))
        dy = max(-1.0, min(1.0, dy))
        self.target_gaze = QPointF(dx * 8.0, dy * 6.0)

    def _on_anim_frame(self):
        dt = 0.016
        self.time_counter += dt

        # 1. Eye Blinking Logic
        self.blink_timer_acc += dt
        if not self.is_blinking:
            if self.blink_timer_acc >= self.next_blink_time:
                self.is_blinking = True
                self.blink_progress = 0.0
                self.blink_timer_acc = 0.0
        else:
            self.blink_progress += dt * 10.0 # Quick blink (~0.15s)
            if self.blink_progress >= 1.0:
                self.blink_progress = 0.0
                self.is_blinking = False
                self.next_blink_time = random.uniform(2.5, 5.0)

        # Smooth eyelid factor (0 -> 1 -> 0)
        eyelid_factor = math.sin(self.blink_progress * math.pi) if self.is_blinking else 0.0

        # 2. Smooth Gaze Tracking Interpolation
        gx = self.current_gaze.x() + (self.target_gaze.x() - self.current_gaze.x()) * 0.1
        gy = self.current_gaze.y() + (self.target_gaze.y() - self.current_gaze.y()) * 0.1
        self.current_gaze = QPointF(gx, gy)

        # 3. Breathing & Physics
        self.breath_y = math.sin(self.time_counter * 2.5) * 3.0

        # 4. State-Based Animations (Mouth Lip-Sync & Living Hand Gestures)
        if self.current_state == "SPEAKING":
            # Dynamic mouth open/close viseme simulation
            self.talk_phase += dt * 14.0
            self.mouth_openness = 0.2 + 0.7 * abs(math.sin(self.talk_phase) * math.cos(self.talk_phase * 0.7))
            self.mouth_width = 0.8 + 0.4 * math.sin(self.talk_phase * 0.5)

            # Expressive Living Hand & Arm Gestures
            self.gesture_phase += dt * 6.0
            # Left hand gestures up/down/outward
            self.left_arm_angle = math.sin(self.gesture_phase) * 0.35 + 0.2
            self.left_hand_y = math.cos(self.gesture_phase * 1.2) * 12.0
            # Right hand accent gestures
            self.right_arm_angle = -math.cos(self.gesture_phase * 0.9) * 0.4 - 0.25
            self.right_hand_y = math.sin(self.gesture_phase * 1.5) * 14.0

            # Subtle head tilt cadence when speaking
            self.head_tilt = math.sin(self.time_counter * 3.0) * 0.06

        elif self.current_state == "THINKING":
            # Mouth small neutral
            self.mouth_openness = 0.05
            self.mouth_width = 0.7

            # Right hand raised to chin pose!
            self.right_arm_angle = -1.15
            self.right_hand_y = -35.0
            self.left_arm_angle = 0.1
            self.left_hand_y = 0.0
            self.head_tilt = 0.12 # Tilt head thoughtfully

        elif self.current_state == "LISTENING":
            # Mouth closed, attentive pose
            self.mouth_openness = 0.0
            self.mouth_width = 1.0

            # Slightly leaning forward arms
            self.left_arm_angle = 0.15 + math.sin(self.time_counter * 3.0) * 0.05
            self.right_arm_angle = -0.15 - math.sin(self.time_counter * 3.0) * 0.05
            self.head_tilt = math.sin(self.time_counter * 1.5) * 0.04

        elif self.current_state == "HAPPY":
            # Wide smile mouth
            self.mouth_openness = 0.4
            self.mouth_width = 1.3
            self.left_arm_angle = 0.4 + math.sin(self.time_counter * 5.0) * 0.15
            self.right_arm_angle = -0.4 - math.sin(self.time_counter * 5.0) * 0.15
            self.head_tilt = math.sin(self.time_counter * 4.0) * 0.08

        else: # IDLE
            # Mouth closed, natural idle breathing
            self.mouth_openness = 0.0
            self.mouth_width = 1.0

            # Gentle arm rest sway
            self.left_arm_angle = math.sin(self.time_counter * 1.8) * 0.08
            self.right_arm_angle = -math.sin(self.time_counter * 1.8) * 0.08
            self.left_hand_y = math.sin(self.time_counter * 1.8) * 3.0
            self.right_hand_y = math.cos(self.time_counter * 1.8) * 3.0
            self.head_tilt = math.sin(self.time_counter * 1.0) * 0.02

        self.update()

    def mouseMoveEvent(self, event):
        self.update_gaze_target(QPointF(event.x(), event.y()))
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setOpacity(self.opacity_val)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0 + self.breath_y

        painter.save()
        painter.translate(cx, cy)
        painter.scale(self.scale_factor, self.scale_factor)

        # -------------------------------------------------------------
        # 0. Flame Aura (Fire Fist Ace Style)
        # -------------------------------------------------------------
        self._draw_flame_aura(painter)

        # -------------------------------------------------------------
        # 1. Torso & Clothes
        # -------------------------------------------------------------
        # Torso body
        body_path = QPainterPath()
        body_path.moveTo(-45, 40)
        body_path.lineTo(45, 40)
        body_path.lineTo(55, 120)
        body_path.lineTo(-55, 120)
        body_path.closeSubpath()
        
        torso_grad = QLinearGradient(0, 40, 0, 120)
        torso_grad.setColorAt(0.0, QColor(35, 38, 50))
        torso_grad.setColorAt(1.0, QColor(20, 22, 30))
        painter.setBrush(QBrush(torso_grad))
        painter.setPen(QPen(QColor(60, 65, 85), 2))
        painter.drawPath(body_path)

        # Ace Belt / Buckle Accent
        painter.setBrush(QBrush(QColor(255, 120, 0)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(-20, 105, 40, 10, 3, 3)

        # -------------------------------------------------------------
        # 2. Living Articulated Left & Right Arms & Hands
        # -------------------------------------------------------------
        self._draw_left_arm_and_hand(painter)
        self._draw_right_arm_and_hand(painter)

        # -------------------------------------------------------------
        # 3. Head & Face (with Tilt)
        # -------------------------------------------------------------
        painter.save()
        painter.translate(0, 10)
        painter.rotate(self.head_tilt * 57.2958) # Radians to degrees

        # Neck
        painter.setBrush(QBrush(QColor(240, 190, 160)))
        painter.setPen(QPen(QColor(200, 140, 110), 1.5))
        painter.drawRect(-14, 15, 28, 25)

        # Head Base
        head_rect = QPainterPath()
        head_rect.addRoundedRect(-42, -55, 84, 80, 40, 40)
        skin_grad = QLinearGradient(0, -55, 0, 25)
        skin_grad.setColorAt(0.0, QColor(255, 215, 185))
        skin_grad.setColorAt(1.0, QColor(240, 185, 155))
        painter.setBrush(QBrush(skin_grad))
        painter.setPen(QPen(QColor(190, 130, 100), 2))
        painter.drawPath(head_rect)

        # Hair Base / Ace Locks
        hair_path = QPainterPath()
        hair_path.moveTo(-45, -35)
        hair_path.cubicTo(-50, -65, -20, -75, 0, -70)
        hair_path.cubicTo(20, -75, 50, -65, 45, -35)
        hair_path.cubicTo(48, -20, 40, -10, 38, 0)
        hair_path.lineTo(32, -30)
        hair_path.cubicTo(15, -45, -15, -45, -32, -30)
        hair_path.lineTo(-38, 0)
        hair_path.closeSubpath()
        painter.setBrush(QBrush(QColor(30, 25, 25)))
        painter.setPen(Qt.NoPen)
        painter.drawPath(hair_path)

        # Ace Orange Hat
        hat_path = QPainterPath()
        hat_path.moveTo(-60, -45)
        hat_path.cubicTo(-62, -52, 62, -52, 60, -45)
        hat_path.lineTo(40, -55)
        hat_path.cubicTo(35, -85, -35, -85, -40, -55)
        hat_path.closeSubpath()
        hat_grad = QLinearGradient(0, -85, 0, -45)
        hat_grad.setColorAt(0.0, QColor(255, 85, 0))
        hat_grad.setColorAt(1.0, QColor(210, 50, 0))
        painter.setBrush(QBrush(hat_grad))
        painter.setPen(QPen(QColor(150, 30, 0), 2))
        painter.drawPath(hat_path)

        # Hat Red Beads
        painter.setBrush(QBrush(QColor(220, 20, 20)))
        for bx in range(-35, 40, 12):
            painter.drawEllipse(bx, -51, 8, 8)

        # -------------------------------------------------------------
        # 4. Eyes & Blinking System
        # -------------------------------------------------------------
        self._draw_eyes(painter)

        # -------------------------------------------------------------
        # 5. Dynamic Mouth Lip Sync Speaking System
        # -------------------------------------------------------------
        self._draw_mouth(painter)

        painter.restore() # Restore head transform
        painter.restore() # Restore center transform

    def _draw_flame_aura(self, painter: QPainter):
        """Draw dynamic animated fire particle aura for Portgas D. Ace theme."""
        painter.save()
        t = self.time_counter
        for i in range(12):
            angle = (i / 12.0) * math.pi * 2 + t * 1.5
            dist = 70 + math.sin(t * 3.0 + i) * 12.0
            fx = math.cos(angle) * dist
            fy = math.sin(angle) * dist - 20
            r = 8 + math.sin(t * 5.0 + i * 2) * 4

            flame_grad = QRadialGradient(fx, fy, r)
            flame_grad.setColorAt(0.0, QColor(255, 200, 0, 200))
            flame_grad.setColorAt(0.6, QColor(255, 80, 0, 140))
            flame_grad.setColorAt(1.0, QColor(255, 0, 0, 0))
            painter.setBrush(QBrush(flame_grad))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(fx, fy), r, r)
        painter.restore()

    def _draw_left_arm_and_hand(self, painter: QPainter):
        """Draw left arm & hand with articulated rotation and gesture animation."""
        painter.save()
        painter.translate(-42, 45) # Shoulder joint
        painter.rotate(self.left_arm_angle * 57.2958)

        # Upper & Forearm
        arm_path = QPainterPath()
        arm_path.moveTo(-8, 0)
        arm_path.lineTo(-16, 50 + self.left_hand_y * 0.3)
        arm_path.lineTo(4, 50 + self.left_hand_y * 0.3)
        arm_path.lineTo(8, 0)
        arm_path.closeSubpath()

        painter.setBrush(QBrush(QColor(240, 185, 155)))
        painter.setPen(QPen(QColor(190, 130, 100), 1.5))
        painter.drawPath(arm_path)

        # Hand / Palm & Fingers
        painter.save()
        painter.translate(-6, 50 + self.left_hand_y * 0.3)
        painter.setBrush(QBrush(QColor(245, 190, 160)))
        painter.drawRoundedRect(-8, 0, 16, 16, 5, 5)

        # Expressive fingers when speaking
        if self.current_state == "SPEAKING":
            f_offset = math.sin(self.gesture_phase * 2.0) * 4.0
            painter.drawEllipse(-10, 12, 6, 8)
            painter.drawEllipse(-4, 14 + f_offset * 0.5, 6, 9)
            painter.drawEllipse(3, 13, 6, 8)
        painter.restore()

        painter.restore()

    def _draw_right_arm_and_hand(self, painter: QPainter):
        """Draw right arm & hand with articulated rotation and gesture animation."""
        painter.save()
        painter.translate(42, 45) # Right shoulder joint
        painter.rotate(self.right_arm_angle * 57.2958)

        # Upper & Forearm
        arm_path = QPainterPath()
        arm_path.moveTo(-8, 0)
        arm_path.lineTo(-4, 50 + self.right_hand_y * 0.3)
        arm_path.lineTo(16, 50 + self.right_hand_y * 0.3)
        arm_path.lineTo(8, 0)
        arm_path.closeSubpath()

        painter.setBrush(QBrush(QColor(240, 185, 155)))
        painter.setPen(QPen(QColor(190, 130, 100), 1.5))
        painter.drawPath(arm_path)

        # Hand / Palm & Fingers
        painter.save()
        painter.translate(6, 50 + self.right_hand_y * 0.3)
        painter.setBrush(QBrush(QColor(245, 190, 160)))
        painter.drawRoundedRect(-8, 0, 16, 16, 5, 5)

        # Expressive fingers when speaking
        if self.current_state == "SPEAKING":
            f_offset = math.cos(self.gesture_phase * 2.0) * 4.0
            painter.drawEllipse(4, 12, 6, 8)
            painter.drawEllipse(-2, 14 + f_offset * 0.5, 6, 9)
            painter.drawEllipse(-8, 13, 6, 8)
        elif self.current_state == "THINKING":
            # Chin rest hand shape
            painter.drawEllipse(-6, -4, 12, 10)
        painter.restore()

        painter.restore()

    def _draw_eyes(self, painter: QPainter):
        """Draw eyes with pupils tracking cursor and smooth eyelid blinking system."""
        eyelid_factor = math.sin(self.blink_progress * math.pi) if self.is_blinking else 0.0

        for eye_x in [-20, 20]:
            painter.save()
            painter.translate(eye_x, -15)

            # Eye White Sclera
            eye_w = 18
            eye_h = 16 * (1.0 - eyelid_factor * 0.9)
            if eye_h < 1.0:
                eye_h = 1.0

            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.setPen(QPen(QColor(60, 60, 60), 1.5))
            painter.drawEllipse(QPointF(0, 0), eye_w / 2.0, eye_h / 2.0)

            # Pupil (Gaze Tracked)
            if eyelid_factor < 0.7:
                px = self.current_gaze.x() * 0.4
                py = self.current_gaze.y() * 0.3
                painter.setBrush(QBrush(QColor(40, 25, 20)))
                painter.drawEllipse(QPointF(px, py), 4.5, 4.5 * (1.0 - eyelid_factor))

                # Catchlight shine dot
                painter.setBrush(QBrush(QColor(255, 255, 255)))
                painter.drawEllipse(QPointF(px - 1.5, py - 1.5), 1.8, 1.8)

            # Eyebrows
            painter.setPen(QPen(QColor(30, 25, 25), 3, Qt.SolidLine, Qt.RoundCap))
            brow_tilt = 0.0
            if self.current_state == "SPEAKING":
                brow_tilt = math.sin(self.talk_phase * 0.5) * 3.0
            elif self.current_state == "THINKING":
                brow_tilt = -4.0 if eye_x < 0 else 4.0
            elif self.current_state == "HAPPY":
                brow_tilt = -3.0

            painter.drawLine(int(-10), int(-13 + brow_tilt), int(10), int(-13 - brow_tilt))

            painter.restore()

    def _draw_mouth(self, painter: QPainter):
        """Draw dynamic mouth lip-sync speaking system."""
        painter.save()
        painter.translate(0, 12)

        mw = 24.0 * self.mouth_width
        mh = 2.0 + 18.0 * self.mouth_openness

        if self.current_state == "SPEAKING" and self.mouth_openness > 0.05:
            # Open talking mouth cavity with teeth & tongue!
            mouth_path = QPainterPath()
            mouth_path.moveTo(-mw / 2.0, 0)
            mouth_path.cubicTo(-mw / 2.0, mh, mw / 2.0, mh, mw / 2.0, 0)
            mouth_path.closeSubpath()

            # Mouth interior cavity (dark red)
            painter.setBrush(QBrush(QColor(140, 20, 20)))
            painter.setPen(QPen(QColor(180, 80, 70), 1.5))
            painter.drawPath(mouth_path)

            # Upper Teeth
            if mh > 6.0:
                painter.setBrush(QBrush(QColor(250, 250, 250)))
                painter.setPen(Qt.NoPen)
                painter.drawRect(int(-mw / 3.0), 0, int(mw * 0.66), 4)

            # Tongue
            if mh > 10.0:
                painter.setBrush(QBrush(QColor(230, 90, 100)))
                painter.drawEllipse(QPointF(0, mh * 0.65), mw * 0.3, mh * 0.35)

        elif self.current_state == "HAPPY":
            # Broad smile curve
            smile_path = QPainterPath()
            smile_path.moveTo(-14, 0)
            smile_path.quadTo(0, 10, 14, 0)
            painter.setPen(QPen(QColor(160, 60, 50), 2.5, Qt.SolidLine, Qt.RoundCap))
            painter.drawPath(smile_path)
        else:
            # Neutral / closed lip line
            painter.setPen(QPen(QColor(160, 60, 50), 2.0, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(-10, 0, 10, 0)

        painter.restore()


class WebLivingCharacter(QWidget):
    """WebGL / Canvas 2D Vector HTML procedural living character widget running in QWebEngineView."""
    state_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_state = "IDLE"
        self.scale_factor = 1.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web_view = QWebEngineView(self)
        self.web_view.setAttribute(Qt.WA_TranslucentBackground, True)
        self.web_view.page().setBackgroundColor(Qt.transparent)
        layout.addWidget(self.web_view)

        html_content = self._generate_html()
        self.web_view.setHtml(html_content, baseUrl=QUrl("file:///"))

    def set_state(self, state: str):
        self.current_state = state.upper()
        self.state_changed.emit(self.current_state)
        js_code = f"if (window.setAvatarState) {{ window.setAvatarState('{self.current_state}'); }}"
        self.web_view.page().runJavaScript(js_code)

    def set_scale(self, scale: float):
        self.scale_factor = scale
        js_code = f"if (window.setAvatarScale) {{ window.setAvatarScale({scale}); }}"
        self.web_view.page().runJavaScript(js_code)

    def set_opacity(self, opacity: float):
        pass

    def _generate_html(self) -> str:
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body { margin: 0; padding: 0; overflow: hidden; background: transparent; }
                canvas { width: 100vw; height: 100vh; display: block; }
            </style>
        </head>
        <body>
            <canvas id="charCanvas"></canvas>
            <script>
                const canvas = document.getElementById('charCanvas');
                const ctx = canvas.getContext('2d');

                let currentState = "IDLE";
                let scaleFactor = 1.0;
                let time = 0;

                // Eye Blinking State
                let blinkProgress = 0;
                let isBlinking = false;
                let nextBlinkTime = 2.5;
                let blinkTimer = 0;

                // Mouth Speaking Lip-sync State
                let talkPhase = 0;
                let mouthOpenness = 0;
                let mouthWidth = 1.0;

                // Gesture & Arm State
                let gesturePhase = 0;
                let leftArmAngle = 0;
                let rightArmAngle = 0;

                // Mouse Gaze Tracking
                let mouseX = 0, mouseY = 0;
                let gazeX = 0, gazeY = 0;

                function resize() {
                    canvas.width = window.innerWidth;
                    canvas.height = window.innerHeight;
                }
                window.addEventListener('resize', resize);
                resize();

                window.addEventListener('mousemove', (e) => {
                    const cx = canvas.width / 2;
                    const cy = canvas.height / 2;
                    mouseX = (e.clientX - cx) / cx;
                    mouseY = (e.clientY - cy) / cy;
                });

                function update(dt) {
                    time += dt;

                    // 1. Eye Blinking Logic
                    blinkTimer += dt;
                    if (!isBlinking) {
                        if (blinkTimer >= nextBlinkTime) {
                            isBlinking = true;
                            blinkProgress = 0;
                            blinkTimer = 0;
                        }
                    } else {
                        blinkProgress += dt * 10.0;
                        if (blinkProgress >= 1.0) {
                            isBlinking = false;
                            blinkProgress = 0;
                            nextBlinkTime = 2.0 + Math.random() * 3.0;
                        }
                    }

                    // Gaze Interpolation
                    gazeX += (mouseX * 8.0 - gazeX) * 0.1;
                    gazeY += (mouseY * 6.0 - gazeY) * 0.1;

                    // 2. State-Based Animations (Mouth Lip-sync & Living Hands Gestures)
                    if (currentState === "SPEAKING" || currentState === "TALKING") {
                        talkPhase += dt * 14.0;
                        mouthOpenness = 0.2 + 0.7 * Math.abs(Math.sin(talkPhase) * Math.cos(talkPhase * 0.7));
                        mouthWidth = 0.8 + 0.4 * Math.sin(talkPhase * 0.5);

                        gesturePhase += dt * 6.0;
                        leftArmAngle = Math.sin(gesturePhase) * 0.35 + 0.2;
                        rightArmAngle = -Math.cos(gesturePhase * 0.9) * 0.4 - 0.25;
                    } else if (currentState === "THINKING") {
                        mouthOpenness = 0.05;
                        mouthWidth = 0.7;
                        rightArmAngle = -1.15; // Hand to chin!
                        leftArmAngle = 0.1;
                    } else if (currentState === "LISTENING") {
                        mouthOpenness = 0.0;
                        mouthWidth = 1.0;
                        leftArmAngle = 0.15 + Math.sin(time * 3.0) * 0.05;
                        rightArmAngle = -0.15 - Math.sin(time * 3.0) * 0.05;
                    } else {
                        mouthOpenness = 0.0;
                        mouthWidth = 1.0;
                        leftArmAngle = Math.sin(time * 1.8) * 0.08;
                        rightArmAngle = -Math.sin(time * 1.8) * 0.08;
                    }
                }

                function draw() {
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    ctx.save();

                    const cx = canvas.width / 2;
                    const cy = canvas.height / 2 + Math.sin(time * 2.5) * 3.0; // Breathing
                    ctx.translate(cx, cy);
                    ctx.scale(scaleFactor, scaleFactor);

                    // Flame Aura
                    for (let i = 0; i < 12; i++) {
                        let angle = (i / 12.0) * Math.PI * 2 + time * 1.5;
                        let dist = 70 + Math.sin(time * 3.0 + i) * 12.0;
                        let fx = Math.cos(angle) * dist;
                        let fy = Math.sin(angle) * dist - 20;
                        let r = 8 + Math.sin(time * 5.0 + i * 2) * 4;

                        let radGrad = ctx.createRadialGradient(fx, fy, 0, fx, fy, r);
                        radGrad.addColorStop(0, 'rgba(255, 200, 0, 0.8)');
                        radGrad.addColorStop(0.6, 'rgba(255, 80, 0, 0.5)');
                        radGrad.addColorStop(1, 'rgba(255, 0, 0, 0)');
                        ctx.fillStyle = radGrad;
                        ctx.beginPath();
                        ctx.arc(fx, fy, r, 0, Math.PI * 2);
                        ctx.fill();
                    }

                    // Torso Body
                    ctx.fillStyle = '#232632';
                    ctx.strokeStyle = '#3c4155';
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    ctx.moveTo(-45, 40);
                    ctx.lineTo(45, 40);
                    ctx.lineTo(55, 120);
                    ctx.lineTo(-55, 120);
                    ctx.closePath();
                    ctx.fill();
                    ctx.stroke();

                    // Belt
                    ctx.fillStyle = '#ff7800';
                    ctx.fillRect(-20, 105, 40, 10);

                    // Left Arm & Hand
                    ctx.save();
                    ctx.translate(-42, 45);
                    ctx.rotate(leftArmAngle);
                    ctx.fillStyle = '#f0b99b';
                    ctx.strokeStyle = '#be8264';
                    ctx.fillRect(-8, 0, 16, 50);
                    ctx.fillRect(-10, 48, 20, 16);
                    ctx.restore();

                    // Right Arm & Hand
                    ctx.save();
                    ctx.translate(42, 45);
                    ctx.rotate(rightArmAngle);
                    ctx.fillStyle = '#f0b99b';
                    ctx.strokeStyle = '#be8264';
                    ctx.fillRect(-8, 0, 16, 50);
                    ctx.fillRect(-10, 48, 20, 16);
                    ctx.restore();

                    // Head
                    ctx.save();
                    ctx.translate(0, 10);
                    ctx.rotate(Math.sin(time * 2.0) * 0.03);

                    // Neck
                    ctx.fillStyle = '#f0be9c';
                    ctx.fillRect(-14, 15, 28, 25);

                    // Head Circle
                    ctx.fillStyle = '#ffd7b9';
                    ctx.strokeStyle = '#be8264';
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    ctx.arc(0, -15, 42, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.stroke();

                    // Ace Hat
                    ctx.fillStyle = '#ff4400';
                    ctx.beginPath();
                    ctx.ellipse(0, -48, 60, 14, 0, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.beginPath();
                    ctx.moveTo(-38, -48);
                    ctx.lineTo(-25, -78);
                    ctx.lineTo(25, -78);
                    ctx.lineTo(38, -48);
                    ctx.closePath();
                    ctx.fill();

                    // Eyes & Blinking
                    let eyelidFactor = isBlinking ? Math.sin(blinkProgress * Math.PI) : 0;
                    for (let eyeX of [-20, 20]) {
                        ctx.save();
                        ctx.translate(eyeX, -18);

                        let eyeH = 16 * (1.0 - eyelidFactor * 0.9);
                        if (eyeH < 1) eyeH = 1;

                        ctx.fillStyle = '#ffffff';
                        ctx.strokeStyle = '#3c3c3c';
                        ctx.lineWidth = 1.5;
                        ctx.beginPath();
                        ctx.ellipse(0, 0, 9, eyeH / 2, 0, 0, Math.PI * 2);
                        ctx.fill();
                        ctx.stroke();

                        if (eyelidFactor < 0.7) {
                            ctx.fillStyle = '#281914';
                            ctx.beginPath();
                            ctx.arc(gazeX * 0.4, gazeY * 0.3, 4.5, 0, Math.PI * 2);
                            ctx.fill();

                            ctx.fillStyle = '#ffffff';
                            ctx.beginPath();
                            ctx.arc(gazeX * 0.4 - 1.5, gazeY * 0.3 - 1.5, 1.8, 0, Math.PI * 2);
                            ctx.fill();
                        }
                        ctx.restore();
                    }

                    // Mouth Lip Sync
                    ctx.save();
                    ctx.translate(0, 12);
                    let mw = 24 * mouthWidth;
                    let mh = 2 + 18 * mouthOpenness;

                    if ((currentState === "SPEAKING" || currentState === "TALKING") && mouthOpenness > 0.05) {
                        ctx.fillStyle = '#8c1414';
                        ctx.strokeStyle = '#b45046';
                        ctx.beginPath();
                        ctx.moveTo(-mw / 2, 0);
                        ctx.bezierCurveTo(-mw / 2, mh, mw / 2, mh, mw / 2, 0);
                        ctx.closePath();
                        ctx.fill();
                        ctx.stroke();

                        if (mh > 6) {
                            ctx.fillStyle = '#ffffff';
                            ctx.fillRect(-mw / 3, 0, mw * 0.66, 4);
                        }
                    } else {
                        ctx.strokeStyle = '#a03c32';
                        ctx.lineWidth = 2;
                        ctx.beginPath();
                        ctx.moveTo(-10, 0);
                        ctx.lineTo(10, 0);
                        ctx.stroke();
                    }
                    ctx.restore();

                    ctx.restore();
                    ctx.restore();
                }

                let lastTime = performance.now();
                function loop(now) {
                    let dt = (now - lastTime) / 1000.0;
                    lastTime = now;
                    update(dt);
                    draw();
                    requestAnimationFrame(loop);
                }
                requestAnimationFrame(loop);

                window.setAvatarState = function(st) { currentState = st; };
                window.setAvatarScale = function(sc) { scaleFactor = sc; };
            </script>
        </body>
        </html>
        """

class LivingCharacterWidget(QWidget):
    """High level character renderer widget combining Native QPainter and WebGL engines."""
    state_changed = Signal(str)

    def __init__(self, parent=None, use_web: bool = True):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if use_web and WEBENGINE_AVAILABLE:
            self.engine = WebLivingCharacter(self)
        else:
            self.engine = NativeLivingCharacter(self)

        layout.addWidget(self.engine)
        self.engine.state_changed.connect(self.state_changed.emit)

    def set_state(self, state: str):
        self.engine.set_state(state)

    def set_scale(self, scale: float):
        self.engine.set_scale(scale)

    def set_opacity(self, opacity: float):
        self.engine.set_opacity(opacity)
