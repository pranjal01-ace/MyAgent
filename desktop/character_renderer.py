import json
import math
import random
import logging
from abc import ABC, ABCMeta, abstractmethod
from pathlib import Path
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QGraphicsOpacityEffect
from PyQt5.QtGui import QPixmap, QMovie, QTransform, QPainter, QColor, QPen, QBrush, QPainterPath
from PyQt5.QtCore import Qt, QTimer, QObject, pyqtSignal as Signal

from desktop.living_character import LivingCharacterWidget

logger = logging.getLogger("desktop.character_renderer")

class QABCMeta(type(QObject), ABCMeta):
    pass

class CharacterRenderer(QWidget, metaclass=QABCMeta):
    """Abstract Base Class for Desktop Character Renderers."""
    state_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    @abstractmethod
    def load(self, character_path: Path) -> bool:
        """Load character assets and manifest from folder."""
        pass

    @abstractmethod
    def set_state(self, state: str):
        """Set character animation state (IDLE, LISTENING, THINKING, SPEAKING, HAPPY, CONFUSED, ERROR)."""
        pass

    @abstractmethod
    def set_scale(self, scale: float):
        """Set character visual scale."""
        pass

    @abstractmethod
    def set_opacity(self, opacity: float):
        """Set character visual opacity (0.0 to 1.0)."""
        pass

    def set_expression(self, expression: str):
        """Set character facial expression (NEUTRAL, HAPPY, SMILE, LAUGH, THINKING, SURPRISED, CONFUSED, WINK)."""
        pass

    def set_gaze(self, x: float, y: float):
        """Set eye lookat gaze tracking target coordinates (-1.0 to 1.0)."""
        pass

    def trigger_blink(self, blink_type: str = "NORMAL"):
        """Trigger an immediate eye blink (NORMAL, DOUBLE, LONG)."""
        pass


class LivingCharacterRenderer(CharacterRenderer):
    """Living Character Renderer with dynamic mouth speaking lip-sync, natural eye blinking,
    living hand & arm gestures, and breathing physics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.widget = LivingCharacterWidget(self, use_web=True)
        self.widget.state_changed.connect(self.state_changed.emit)
        layout.addWidget(self.widget)

    def load(self, character_path: Path) -> bool:
        return True

    def set_state(self, state: str):
        self.widget.set_state(state)

    def set_scale(self, scale: float):
        self.widget.set_scale(scale)

    def set_opacity(self, opacity: float):
        self.widget.set_opacity(opacity)


class Sprite2DRenderer(CharacterRenderer):
    """2D Image / Animated Sprite renderer supporting PNG, GIF, WebP, APNG, and frame sequences,
    enhanced with procedural eye blinking and mouth lip-sync overlays when speaking."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_state = "IDLE"
        self.manifest = {}
        self.assets_map = {}
        self.pixmaps = {}
        self.movies = {}
        
        self.scale_factor = 1.0
        self.opacity_val = 1.0
        self.flip_horizontal = False
        
        self.character_dir = None
        self.talk_step = 0
        self.breath_step = 0
        self.talk_phase = 0.0

        # Eye Blinking Logic
        self.is_blinking = False
        self.blink_progress = 0.0
        self.blink_timer_acc = 0.0
        self.next_blink_time = random.uniform(2.0, 4.5)

        # UI Container setup
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label)

        # Opacity effect
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        # Timers (~60 FPS tick for smooth mouth lip sync and blinking)
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(33) # ~30-60 FPS
        self.anim_timer.timeout.connect(self._on_anim_tick)
        self.anim_timer.start()

    def load(self, character_path: Path) -> bool:
        """Load character manifest and asset maps from folder."""
        character_path = Path(character_path)
        manifest_file = character_path / "character.json"
        
        if not manifest_file.exists():
            logger.error(f"Missing character.json in {character_path}")
            return False

        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                self.manifest = json.load(f)
        except Exception as e:
            logger.error(f"Failed to parse character.json: {e}")
            return False

        self.character_dir = character_path
        self.assets_map = self.manifest.get("assets", {})
        settings = self.manifest.get("settings", {})
        
        self.scale_factor = float(settings.get("scale", 1.0))
        self.flip_horizontal = bool(settings.get("flip_horizontal", False))
        self.opacity_val = float(settings.get("opacity", 1.0))
        
        self.set_opacity(self.opacity_val)

        # Preload state assets
        self.pixmaps.clear()
        self.movies.clear()

        states = ["idle", "listening", "thinking", "talking", "speaking", "happy", "confused", "searching", "working", "error"]
        
        # Determine fallback idle image
        idle_file = self.assets_map.get("idle", "idle.png")
        fallback_path = character_path / idle_file

        for state in states:
            file_name = self.assets_map.get(state, f"{state}.png")
            asset_path = character_path / file_name
            
            if not asset_path.exists():
                asset_path = fallback_path

            if asset_path.exists():
                if asset_path.suffix.lower() in [".gif", ".webp"]:
                    movie = QMovie(str(asset_path))
                    self.movies[state.upper()] = movie
                else:
                    pix = QPixmap(str(asset_path))
                    if self.flip_horizontal:
                        pix = pix.transformed(QTransform().scale(-1, 1))
                    self.pixmaps[state.upper()] = pix

        self.set_state("IDLE")
        logger.info(f"Loaded character renderer for: {self.manifest.get('name', 'Unknown')}")
        return True

    def set_state(self, state: str):
        state_upper = state.upper()
        if state_upper == "SPEAKING":
            state_upper = "TALKING"

        if state_upper not in self.pixmaps and state_upper not in self.movies:
            state_upper = "IDLE"

        if self.current_state != state_upper:
            # Stop previous movie if playing
            if self.current_state in self.movies:
                self.movies[self.current_state].stop()

            self.current_state = state_upper
            self.state_changed.emit(self.current_state)

            if self.current_state in self.movies:
                movie = self.movies[self.current_state]
                self.image_label.setMovie(movie)
                movie.start()

        self._render_current_frame()

    def set_scale(self, scale: float):
        self.scale_factor = max(0.2, min(3.0, scale))
        self._render_current_frame()

    def set_opacity(self, opacity: float):
        self.opacity_val = max(0.1, min(1.0, opacity))
        self.opacity_effect.setOpacity(self.opacity_val)

    def _on_anim_tick(self):
        """Tick timer for procedural bounce/scaling, eye blinking, and mouth lip-sync animations."""
        dt = 0.033
        self.blink_timer_acc += dt

        # Eye Blinking Logic
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

        if self.current_state in ["TALKING", "SPEAKING"]:
            self.talk_step = (self.talk_step + 1) % 4
            self.talk_phase += dt * 14.0
            self._render_current_frame()
        elif self.current_state == "IDLE":
            self.breath_step = (self.breath_step + 1) % 40
            if self.breath_step % 2 == 0 or self.is_blinking:
                self._render_current_frame()

    def _render_current_frame(self):
        if self.current_state in self.movies:
            return

        pix = self.pixmaps.get(self.current_state, self.pixmaps.get("IDLE"))
        if not pix or pix.isNull():
            return

        # Base size
        w = int(300 * self.scale_factor)
        h = int(300 * self.scale_factor)

        # Procedural talk bounce & arm sway
        if self.current_state in ["TALKING", "SPEAKING"]:
            bounce_offsets = [0, -5, 3, -3]
            h_adj = h + bounce_offsets[self.talk_step]
            scaled_pix = pix.scaled(w, h_adj, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        elif self.current_state == "IDLE":
            breath_offsets = [0, 2, 4, 2, 0, -2, 0, 2]
            h_adj = h + breath_offsets[(self.breath_step // 5) % len(breath_offsets)]
            scaled_pix = pix.scaled(w, h_adj, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            scaled_pix = pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        # Apply overlay mouth speaking & blinking if enabled
        final_pixmap = QPixmap(scaled_pix.size())
        final_pixmap.fill(Qt.transparent)
        painter = QPainter(final_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(0, 0, scaled_pix)

        # Draw procedural eye blinking eyelids overlay over sprite image if blinking
        if self.is_blinking:
            eyelid_factor = math.sin(self.blink_progress * math.pi)
            pw = final_pixmap.width()
            ph = final_pixmap.height()
            painter.setBrush(QBrush(QColor(40, 40, 50, int(220 * eyelid_factor))))
            painter.setPen(Qt.NoPen)
            # Eye mask areas overlaying eye level
            painter.drawRoundedRect(int(pw * 0.36), int(ph * 0.38), int(pw * 0.12), int(ph * 0.05 * eyelid_factor), 3, 3)
            painter.drawRoundedRect(int(pw * 0.52), int(ph * 0.38), int(pw * 0.12), int(ph * 0.05 * eyelid_factor), 3, 3)

        # Draw procedural dynamic mouth opening when speaking
        if self.current_state in ["TALKING", "SPEAKING"]:
            openness = 0.2 + 0.6 * abs(math.sin(self.talk_phase))
            pw = final_pixmap.width()
            ph = final_pixmap.height()
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

                # Teeth
                if mh > 5:
                    painter.setBrush(QBrush(QColor(250, 250, 250)))
                    painter.drawRect(mx + 2, my, mw - 4, 3)

        painter.end()

        self.image_label.setPixmap(final_pixmap)

