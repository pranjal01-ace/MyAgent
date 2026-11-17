import json
import logging
from pathlib import Path
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFileDialog, QSlider, QFrame, QMessageBox, QGraphicsOpacityEffect
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal as Signal
from PyQt5.QtGui import QFont, QPixmap, QColor

from desktop.character_manager import CharacterManager
from desktop.character_renderer import Sprite2DRenderer

logger = logging.getLogger("desktop.character_ui")


class CharacterCard(QFrame):
    """Card widget displaying a character summary with selection button."""
    selected = Signal(str)
    configure = Signal(str)

    def __init__(self, char_info: dict, is_active: bool, parent=None):
        super().__init__(parent)
        self.char_id = char_info.get("id", "unknown")
        
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {"rgba(255, 120, 0, 0.15)" if is_active else "rgba(35, 38, 50, 0.95)"};
                border: 2px solid {"#ff7814" if is_active else "rgba(80, 85, 110, 0.5)"};
                border-radius: 12px;
                padding: 10px;
            }}
        """)

        layout = QVBoxLayout(self)

        name_lbl = QLabel(char_info.get("name", "Unknown Character"), self)
        name_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        name_lbl.setStyleSheet("color: #ffffff; border: none;")
        layout.addWidget(name_lbl)

        author_lbl = QLabel(f"By: {char_info.get('author', 'User')} | v{char_info.get('version', '1.0')}", self)
        author_lbl.setStyleSheet("color: #8a8fba; font-size: 11px; border: none;")
        layout.addWidget(author_lbl)

        desc_lbl = QLabel(char_info.get("description", "No description provided."), self)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #d0d5ff; font-size: 11px; border: none;")
        layout.addWidget(desc_lbl)

        p = char_info.get("personality", {})
        traits = p.get("personality", "Friendly")
        trait_lbl = QLabel(f"🎭 {traits}", self)
        trait_lbl.setStyleSheet("color: #ff9d42; font-size: 11px; font-weight: bold; border: none;")
        layout.addWidget(trait_lbl)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(6)

        select_btn = QPushButton("Active ✓" if is_active else "Select", self)
        select_btn.setEnabled(not is_active)
        select_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff7814;
                color: white;
                font-weight: bold;
                border-radius: 8px;
                padding: 5px 10px;
            }
            QPushButton:disabled {
                background-color: #555;
                color: #aaa;
            }
        """)
        select_btn.clicked.connect(lambda: self.selected.emit(self.char_id))
        btn_box.addWidget(select_btn)

        cfg_btn = QPushButton("Settings ⚙️", self)
        cfg_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b4260;
                color: white;
                font-weight: bold;
                border-radius: 8px;
                padding: 5px 10px;
            }
        """)
        cfg_btn.clicked.connect(lambda: self.configure.emit(self.char_id))
        btn_box.addWidget(cfg_btn)

        layout.addLayout(btn_box)


class CharacterSelectionDialog(QDialog):
    """Character Selection modal displaying available character cards and import button."""
    character_changed = Signal(str)

    def __init__(self, manager: CharacterManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Choose Desktop Companion Character")
        self.setMinimumSize(520, 420)
        self.setStyleSheet("background-color: #1a1c24; color: white;")

        layout = QVBoxLayout(self)

        header = QLabel("Choose Character", self)
        header.setFont(QFont("Segoe UI", 16, QFont.Bold))
        header.setStyleSheet("color: #ff9d42;")
        layout.addWidget(header)

        # Scroll Area for Character Cards
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.card_container = QWidget()
        self.card_layout = QVBoxLayout(self.card_container)
        self.card_layout.setSpacing(10)
        scroll.setWidget(self.card_container)
        layout.addWidget(scroll)

        # Bottom Buttons
        bottom_box = QHBoxLayout()

        import_btn = QPushButton("📥 Import Character Folder", self)
        import_btn.setStyleSheet("""
            QPushButton {
                background-color: #008cff;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 16px;
                border-radius: 10px;
            }
        """)
        import_btn.clicked.connect(self._import_character)
        bottom_box.addWidget(import_btn)

        close_btn = QPushButton("Close", self)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #383d52;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 16px;
                border-radius: 10px;
            }
        """)
        close_btn.clicked.connect(self.accept)
        bottom_box.addWidget(close_btn)

        layout.addLayout(bottom_box)
        self._refresh_cards()

    def _refresh_cards(self):
        # Clear existing
        while self.card_layout.count():
            child = self.card_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        available = self.manager.list_available_characters()
        active_id = self.manager.active_character_id

        for info in available:
            char_id = info.get("id")
            card = CharacterCard(info, is_active=(char_id == active_id), parent=self)
            card.selected.connect(self._select_character)
            card.configure.connect(self._open_settings)
            self.card_layout.addWidget(card)

    def _select_character(self, char_id: str):
        if self.manager.set_active_character(char_id):
            self.character_changed.emit(char_id)
            self._refresh_cards()

    def _open_settings(self, char_id: str):
        dlg = CharacterSettingsDialog(self.manager, char_id=char_id, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.character_changed.emit(self.manager.active_character_id)
            self._refresh_cards()

    def _import_character(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Character Folder with character.json")
        if folder:
            success, msg = self.manager.import_character_folder(Path(folder))
            if success:
                QMessageBox.information(self, "Import Success", msg)
                self.character_changed.emit(self.manager.active_character_id)
                self._refresh_cards()
            else:
                QMessageBox.warning(self, "Import Failed", f"Could not import character:\n\n{msg}")


class CharacterSettingsDialog(QDialog):
    """Character Settings modal with live preview, scale, opacity, and expression test controls."""

    def __init__(self, manager: CharacterManager, char_id: str, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.char_id = char_id
        self.char_path = manager.get_active_character_path() if char_id == manager.active_character_id else (manager.CHARACTERS_ROOT / char_id)

        self.setWindowTitle("Character Settings & Preview")
        self.setMinimumSize(420, 520)
        self.setStyleSheet("background-color: #1a1c24; color: white;")

        layout = QVBoxLayout(self)

        title = QLabel(f"Character: {char_id.title()}", self)
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet("color: #ff9d42;")
        layout.addWidget(title)

        # Preview Container
        preview_box = QFrame(self)
        preview_box.setStyleSheet("background-color: rgba(0, 0, 0, 0.4); border: 1px solid #383d52; border-radius: 10px;")
        preview_layout = QVBoxLayout(preview_box)
        
        self.renderer = Sprite2DRenderer(preview_box)
        self.renderer.load(self.char_path)
        preview_layout.addWidget(self.renderer, alignment=Qt.AlignCenter)
        layout.addWidget(preview_box)

        # Controls Grid
        # Scale Slider
        scale_label = QLabel("Scale Factor:", self)
        layout.addWidget(scale_label)

        self.scale_slider = QSlider(Qt.Horizontal, self)
        self.scale_slider.setRange(20, 200) # 0.2 to 2.0
        curr_scale = int(self.renderer.scale_factor * 100)
        self.scale_slider.setValue(curr_scale)
        self.scale_slider.valueChanged.connect(self._on_scale_changed)
        layout.addWidget(self.scale_slider)

        # Opacity Slider
        op_label = QLabel("Opacity:", self)
        layout.addWidget(op_label)

        self.opacity_slider = QSlider(Qt.Horizontal, self)
        self.opacity_slider.setRange(10, 100) # 0.1 to 1.0
        curr_op = int(self.renderer.opacity_val * 100)
        self.opacity_slider.setValue(curr_op)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        layout.addWidget(self.opacity_slider)

        # Test Expression & Living Animation Buttons
        test_lbl = QLabel("Test Living Animations (Mouth Lip-Sync, Blinking & Gestures):", self)
        test_lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        layout.addWidget(test_lbl)

        btn_grid = QHBoxLayout()
        test_states = [("Idle", "IDLE"), ("Speaking (Mouth & Hands)", "SPEAKING"), ("Thinking (Chin)", "THINKING"), ("Listening", "LISTENING"), ("Happy", "HAPPY")]
        for label, state in test_states:
            btn = QPushButton(label, self)
            btn.setStyleSheet("background-color: #383d52; color: #ffffff; padding: 6px 8px; border-radius: 6px; font-weight: bold; font-size: 11px;")
            btn.clicked.connect(lambda _, s=state: self.renderer.set_state(s))
            btn_grid.addWidget(btn)
        layout.addLayout(btn_grid)

        # Save & Cancel
        bottom_box = QHBoxLayout()
        save_btn = QPushButton("Save Settings", self)
        save_btn.setStyleSheet("background-color: #ff7814; color: white; font-weight: bold; padding: 8px 16px; border-radius: 8px;")
        save_btn.clicked.connect(self._save_settings)
        bottom_box.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setStyleSheet("background-color: #383d52; color: white; padding: 8px 16px; border-radius: 8px;")
        cancel_btn.clicked.connect(self.reject)
        bottom_box.addWidget(cancel_btn)

        layout.addLayout(bottom_box)

    def _on_scale_changed(self, val: int):
        scale = val / 100.0
        self.renderer.set_scale(scale)

    def _on_opacity_changed(self, val: int):
        op = val / 100.0
        self.renderer.set_opacity(op)

    def _save_settings(self):
        manifest_file = self.char_path / "character.json"
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                data.setdefault("settings", {})
                data["settings"]["scale"] = self.scale_slider.value() / 100.0
                data["settings"]["opacity"] = self.opacity_slider.value() / 100.0

                with open(manifest_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
            except Exception as e:
                logger.error(f"Error saving character settings: {e}")

        self.accept()


class CharacterChatBubble(QWidget):
    """Floating Chat Speech Bubble displaying AI responses beside character."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.text_label = QLabel(self)
        self.text_label.setWordWrap(True)
        self.text_label.setMaximumWidth(280)
        self.text_label.setStyleSheet("""
            QLabel {
                background-color: rgba(25, 28, 38, 0.95);
                color: #ffffff;
                border: 2px solid #ff7814;
                border-radius: 14px;
                padding: 10px 14px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.text_label)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    def show_message(self, text: str, timeout_ms: int = 6000):
        if not text.strip():
            return
        self.text_label.setText(text)
        self.adjustSize()
        self.show()
        if timeout_ms > 0:
            self.hide_timer.start(timeout_ms)


class UserSpeechBubble(QWidget):
    """Floating speech bubble displaying user's transcribed speech in real-time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.text_label = QLabel(self)
        self.text_label.setWordWrap(True)
        self.text_label.setMaximumWidth(280)
        self.text_label.setStyleSheet("""
            QLabel {
                background-color: rgba(15, 25, 45, 0.95);
                color: #ffffff;
                border: 2px solid #008cff;
                border-radius: 14px;
                padding: 10px 14px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.text_label)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    def show_user_speech(self, text: str, timeout_ms: int = 4000):
        if not text.strip():
            return
        self.text_label.setText(f"🎤 <b>You said:</b>\n\"{text}\"")
        self.adjustSize()
        self.show()
        if timeout_ms > 0:
            self.hide_timer.start(timeout_ms)
