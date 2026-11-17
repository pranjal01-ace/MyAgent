import os
import math
import random
from pathlib import Path
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QFont, QPainterPath, QBrush, QPen
from PyQt5.QtCore import Qt, QTimer, pyqtSignal as Signal

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "character"

class AvatarWidget(QWidget):
    """Visual Living 2D Avatar renderer displaying Ace's character states with:
    - Dynamic mouth speaking lip-sync animation
    - Natural eye blinking system
    - Living hand & arm gesture movement
    - Idle breathing physics
    """
    state_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_state = "IDLE" # IDLE, LISTENING, THINKING, SPEAKING
        self.pixmaps = {}
        self.scale_factor = 1.0

        # Animation states
        self.talk_phase = 0.0
        self.is_blinking = False
        self.blink_progress = 0.0
        self.blink_timer_acc = 0.0
        self.next_blink_time = random.uniform(2.0, 4.5)

        # Load avatar state images
        self._load_avatar_images()

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Avatar Pixmap Display Label
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label)

        # Status Pill Badge
        self.status_pill = QLabel("IDLE", self)
        self.status_pill.setAlignment(Qt.AlignCenter)
        self.status_pill.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 100, 0, 0.85);
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-weight: bold;
                font-size: 11px;
                border-radius: 10px;
                padding: 3px 10px;
            }
        """)
        layout.addWidget(self.status_pill, alignment=Qt.AlignCenter)

        # High frame-rate animation timer (~30 FPS)
        self.breath_step = 0
        self.breath_timer = QTimer(self)
        self.breath_timer.setInterval(33)
        self.breath_timer.timeout.connect(self._animate_breathing)
        self.breath_timer.start()

        self.set_state("IDLE")

    def _load_avatar_images(self):
        states = ["idle", "listening", "thinking", "speaking"]
        for state in states:
            img_path = ASSETS_DIR / f"{state}.png"
            if img_path.exists():
                pix = QPixmap(str(img_path))
                self.pixmaps[state.upper()] = pix
            else:
                # Placeholder image if missing
                pix = QPixmap(300, 300)
                pix.fill(Qt.transparent)
                self.pixmaps[state.upper()] = pix

    def set_state(self, state: str):
        state_upper = state.upper()
        if state_upper not in ["IDLE", "LISTENING", "THINKING", "SPEAKING"]:
            state_upper = "IDLE"

        self.current_state = state_upper
        self.state_changed.emit(self.current_state)

        # Update pill badge color and text
        badge_styles = {
            "IDLE": "background-color: rgba(255, 120, 0, 0.9); color: white;",
            "LISTENING": "background-color: rgba(0, 180, 255, 0.95); color: white;",
            "THINKING": "background-color: rgba(180, 70, 255, 0.95); color: white;",
            "SPEAKING": "background-color: rgba(255, 40, 40, 0.95); color: white;"
        }
        self.status_pill.setText(f"🔥 {self.current_state}")
        self.status_pill.setStyleSheet(f"""
            QLabel {{
                {badge_styles.get(self.current_state, badge_styles['IDLE'])}
                font-family: 'Segoe UI', Arial, sans-serif;
                font-weight: bold;
                font-size: 11px;
                border-radius: 10px;
                padding: 3px 12px;
            }}
        """)

        self._update_display()

    def _animate_breathing(self):
        dt = 0.033
        self.blink_timer_acc += dt

        # Natural Eye Blinking
        if not self.is_blinking:
            if self.blink_timer_acc >= self.next_blink_time:
                self.is_blinking = True
                self.blink_progress = 0.0
                self.blink_timer_acc = 0.0
        else:
            self.blink_progress += dt * 10.0
            if self.blink_progress >= 1.0:
                self.blink_progress = 0.0
                self.is_blinking = False
                self.next_blink_time = random.uniform(2.5, 5.0)

        if self.current_state == "IDLE":
            self.breath_step = (self.breath_step + 1) % 60
            self.scale_factor = 1.0 + (math.sin(self.breath_step * 0.1) * 0.01)
        elif self.current_state == "SPEAKING":
            self.breath_step = (self.breath_step + 1) % 20
            self.talk_phase += dt * 14.0
            self.scale_factor = 1.0 + (math.sin(self.breath_step * 0.5) * 0.02)
        else:
            self.scale_factor = 1.0

        self._update_display()

    def _update_display(self):
        pixmap = self.pixmaps.get(self.current_state, self.pixmaps.get("IDLE"))
        if pixmap and not pixmap.isNull():
            base_size = 320
            w = int(base_size * self.scale_factor)
            h = int(base_size * self.scale_factor)
            scaled = pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # Apply procedural eye blinking and speaking mouth lip-sync overlays
            final_pixmap = QPixmap(scaled.size())
            final_pixmap.fill(Qt.transparent)
            painter = QPainter(final_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.drawPixmap(0, 0, scaled)

            pw = final_pixmap.width()
            ph = final_pixmap.height()

            # Eye Blinking Overlay
            if self.is_blinking:
                eyelid_factor = math.sin(self.blink_progress * math.pi)
                painter.setBrush(QBrush(QColor(40, 40, 50, int(220 * eyelid_factor))))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(int(pw * 0.36), int(ph * 0.38), int(pw * 0.12), int(ph * 0.05 * eyelid_factor), 3, 3)
                painter.drawRoundedRect(int(pw * 0.52), int(ph * 0.38), int(pw * 0.12), int(ph * 0.05 * eyelid_factor), 3, 3)

            # Mouth Speaking Lip-sync Overlay
            if self.current_state == "SPEAKING":
                openness = 0.2 + 0.6 * abs(math.sin(self.talk_phase))
                mx = int(pw * 0.44)
                my = int(ph * 0.52)
                mw = int(pw * 0.12)
                mh = int(ph * 0.06 * openness)

                if mh > 2:
                    mouth_path = QPainterPath()
                    mouth_path.moveTo(mx, my)
                    mouth_path.cubicTo(mx, my + mh, mx + mw, my + mh, mx + mw, my)
                    mouth_path.closeSubpath()

                    painter.setBrush(QBrush(QColor(140, 20, 20)))
                    painter.setPen(QPen(QColor(180, 80, 70), 1.5))
                    painter.drawPath(mouth_path)

                    if mh > 5:
                        painter.setBrush(QBrush(QColor(250, 250, 250)))
                        painter.drawRect(mx + 2, my, mw - 4, 3)

            painter.end()
            self.image_label.setPixmap(final_pixmap)

