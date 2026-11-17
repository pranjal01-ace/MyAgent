import os
import sys
import json
import logging
import requests
from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QApplication, QMenu, QAction, QSystemTrayIcon, QStyle, QShortcut
)
from PyQt5.QtCore import Qt, QPoint, QTimer
from PyQt5.QtGui import QIcon, QFont, QCursor, QKeySequence, QPixmap

from desktop.character_manager import CharacterManager
from desktop.character_renderer import Sprite2DRenderer
from desktop.character_ui import (
    CharacterSelectionDialog, CharacterSettingsDialog, CharacterChatBubble, UserSpeechBubble
)
from desktop.chat_drawer import ChatDrawerWidget
from desktop.task_panel import AgentTaskPanel
from desktop.memory_viewer import MemoryViewerDialog
from desktop.audio_worker import ChatWorker, VoiceWorker

logger = logging.getLogger("desktop.window")

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
POSITION_FILE = CONFIG_DIR / "desktop_position.json"
API_BASE_URL = "http://127.0.0.1:8000/api"

class AceDesktopWindow(QMainWindow):
    """Transparent desktop overlay window for Desktop AI Mate with dynamic character selection,
    system tray integration, barge-in interruption, and agent task transparency."""

    def __init__(self):
        super().__init__()
        self.drag_position = QPoint()
        self.voice_mode_active = False
        self.silence_count = 0

        # Character Manager
        self.char_manager = CharacterManager()

        # Frameless, Always-on-top, Transparent background window flags
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.SubWindow |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("Desktop AI Mate Companion")

        # Container Widget
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Left Column: Character Renderer & Status Controls
        left_col = QVBoxLayout()
        left_col.setSpacing(6)

        # Character Renderer Widget (Supports 2D Sprite, Living Procedural, and 3D WebGL)
        self.character_renderer = self._create_renderer_for_active_character()
        left_col.addWidget(self.character_renderer)

        # Status Pill Badge - Sleek Developer Glass Capsule
        self.status_pill = QLabel("● IDLE", self)
        self.status_pill.setAlignment(Qt.AlignCenter)
        self.status_pill.setStyleSheet("""
            QLabel {
                background-color: rgba(14, 17, 24, 0.94);
                color: #94a3b8;
                border: 1px solid #232a3d;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Arial, sans-serif;
                font-weight: 600;
                font-size: 10px;
                border-radius: 9px;
                padding: 3px 12px;
                letter-spacing: 0.5px;
            }
        """)
        left_col.addWidget(self.status_pill, alignment=Qt.AlignCenter)
        self.character_renderer.state_changed.connect(self._on_renderer_state_changed)
        self.setMouseTracking(True)

        # Action Buttons Row - Sleek Minimalist Controls
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        common_btn_style = """
            QPushButton {
                background-color: rgba(18, 22, 32, 0.92);
                color: #94a3b8;
                border: 1px solid #232c40;
                border-radius: 8px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-weight: 600;
                font-size: 11px;
                padding: 5px 9px;
            }
            QPushButton:hover {
                background-color: #202738;
                color: #f1f5f9;
                border-color: #38bdf8;
            }
        """

        self.chat_toggle_btn = QPushButton("💬 Chat", self)
        self.chat_toggle_btn.setToolTip("Toggle Chat Drawer")
        self.chat_toggle_btn.setStyleSheet(common_btn_style)
        self.chat_toggle_btn.clicked.connect(self._toggle_chat_drawer)
        btn_row.addWidget(self.chat_toggle_btn)

        self.task_toggle_btn = QPushButton("⚡ Tasks", self)
        self.task_toggle_btn.setToolTip("Toggle Agent Task Activity Panel")
        self.task_toggle_btn.setStyleSheet(common_btn_style)
        self.task_toggle_btn.clicked.connect(self._toggle_task_panel)
        btn_row.addWidget(self.task_toggle_btn)

        self.mic_quick_btn = QPushButton("🎤 Voice", self)
        self.mic_quick_btn.setToolTip("Toggle Continuous Voice Mode (Ctrl+Shift+M)")
        self.mic_quick_btn.setStyleSheet(common_btn_style)
        self.mic_quick_btn.clicked.connect(self._toggle_voice_mode)
        btn_row.addWidget(self.mic_quick_btn)

        self.close_btn = QPushButton("✕", self)
        self.close_btn.setToolTip("Minimize to System Tray (or Right Click -> Exit)")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(18, 22, 32, 0.92);
                color: #64748b;
                border: 1px solid #232c40;
                border-radius: 8px;
                font-size: 11px;
                padding: 5px 8px;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.2);
                color: #f87171;
                border-color: #ef4444;
            }
        """)
        self.close_btn.clicked.connect(self._minimize_to_tray)
        btn_row.addWidget(self.close_btn)

        left_col.addLayout(btn_row)

        main_layout.addLayout(left_col)

        # Right Column: Slide-out Chat Drawer
        self.chat_drawer = ChatDrawerWidget(self)
        self.chat_drawer.send_message_signal.connect(self._send_chat_message)
        self.chat_drawer.voice_trigger_signal.connect(self._toggle_voice_mode)
        self.chat_drawer.open_memory_signal.connect(self._open_memory_viewer)
        self.chat_drawer.open_task_signal.connect(self._toggle_task_panel)
        self.chat_drawer.open_settings_signal.connect(self._open_character_settings)
        self.chat_drawer.stop_speech_signal.connect(self._interrupt_speech)
        self.chat_drawer.hide()
        main_layout.addWidget(self.chat_drawer)

        # Agent Task Transparency Panel
        self.task_panel = AgentTaskPanel(self)
        self.task_panel.stop_task_signal.connect(self._interrupt_speech)
        self.task_panel.hide()
        main_layout.addWidget(self.task_panel)

        # Floating Speech Bubbles
        self.chat_bubble = CharacterChatBubble(self)
        self.user_bubble = UserSpeechBubble(self)

        # Active worker references
        self.active_chat_worker = None
        self.active_voice_worker = None

        # Speech status polling timer
        self.speech_poll_timer = QTimer(self)
        self.speech_poll_timer.setInterval(300)
        self.speech_poll_timer.timeout.connect(self._check_speech_status)

        # Setup Keyboard Shortcuts & System Tray
        self._setup_shortcuts()
        self._setup_system_tray()

        # Restore window position or place bottom right
        self._restore_position()

    def _setup_shortcuts(self):
        """Setup global keyboard shortcuts within the application."""
        # ESC: Interrupt AI speech / Barge-in
        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.esc_shortcut.activated.connect(self._interrupt_speech)

        # Ctrl+Space: Toggle visibility
        self.space_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.space_shortcut.activated.connect(self._toggle_visibility)

        # Ctrl+Shift+M: Toggle Voice Mode
        self.voice_shortcut = QShortcut(QKeySequence("Ctrl+Shift+M"), self)
        self.voice_shortcut.activated.connect(self._toggle_voice_mode)

        # Ctrl+Shift+A: Toggle Agent Task Panel
        self.task_shortcut = QShortcut(QKeySequence("Ctrl+Shift+A"), self)
        self.task_shortcut.activated.connect(self._toggle_task_panel)

    def _setup_system_tray(self):
        """Setup Windows System Tray icon with right-click menu."""
        self.tray_icon = QSystemTrayIcon(self)
        icon = QApplication.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("Desktop AI Mate Companion")

        tray_menu = QMenu()
        show_action = tray_menu.addAction("👁️ Show Companion")
        show_action.triggered.connect(self._show_companion)

        hide_action = tray_menu.addAction("🙈 Hide Companion")
        hide_action.triggered.connect(self.hide)

        tray_menu.addSeparator()

        voice_action = tray_menu.addAction("🎤 Toggle Voice Mode")
        voice_action.triggered.connect(self._toggle_voice_mode)

        task_action = tray_menu.addAction("⚡ Task Activity Panel")
        task_action.triggered.connect(self._toggle_task_panel)

        memory_action = tray_menu.addAction("🧠 Long-Term Memory")
        memory_action.triggered.connect(self._open_memory_viewer)

        settings_action = tray_menu.addAction("⚙️ Character Settings")
        settings_action.triggered.connect(self._open_character_settings)

        tray_menu.addSeparator()
        exit_action = tray_menu.addAction("✕ Exit Companion")
        exit_action.triggered.connect(QApplication.instance().quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._toggle_visibility()

    def _toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self._show_companion()

    def _show_companion(self):
        self.showNormal()
        self.activateWindow()

    def _minimize_to_tray(self):
        self.hide()
        self.tray_icon.showMessage(
            "Desktop AI Mate",
            "Companion minimized to tray. Double click icon to restore.",
            QSystemTrayIcon.Information,
            2000
        )

    def _restore_position(self):
        """Restore previous desktop position from config/desktop_position.json with boundary checks."""
        POSITION_FILE.parent.mkdir(parents=True, exist_ok=True)
        restored = False

        if POSITION_FILE.exists():
            try:
                with open(POSITION_FILE, "r", encoding="utf-8") as f:
                    pos_data = json.load(f)
                    x, y = pos_data.get("x"), pos_data.get("y")
                    if x is not None and y is not None:
                        for screen in QApplication.screens():
                            geom = screen.geometry()
                            if geom.contains(x, y):
                                self.move(x, y)
                                restored = True
                                break
            except Exception as e:
                logger.warning(f"Failed to load desktop position: {e}")

        if not restored:
            screen = QApplication.primaryScreen()
            geom = screen.availableGeometry() if screen else self.geometry()
            self.move(geom.width() - 440, geom.height() - 540)

    def _save_position(self):
        """Save window position to config/desktop_position.json."""
        try:
            pos = self.pos()
            with open(POSITION_FILE, "w", encoding="utf-8") as f:
                json.dump({"x": pos.x(), "y": pos.y()}, f, indent=4)
        except Exception as e:
            logger.warning(f"Failed to save desktop position: {e}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and not self.drag_position.isNull():
            self.move(event.globalPos() - self.drag_position)
            event.accept()
        else:
            # Phase 3: Eye and head gaze tracking relative to companion window center
            w = max(1, self.width())
            h = max(1, self.height())
            gx = (event.x() - w / 2) / (w / 2)
            gy = (event.y() - h / 2) / (h / 2)
            if hasattr(self.character_renderer, "set_gaze"):
                self.character_renderer.set_gaze(gx, gy)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._save_position()

    def contextMenuEvent(self, event):
        """Right-click context menu on desktop companion."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e2029;
                color: #ffffff;
                border: 1px solid #ff7814;
                border-radius: 8px;
                padding: 4px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: rgba(255, 120, 0, 0.3);
                color: #ff9d42;
            }
        """)

        chat_action = menu.addAction("💬 Chat Drawer")
        task_action = menu.addAction("⚡ Agent Task Panel")
        voice_action = menu.addAction("🎤 Voice Mode")
        memory_action = menu.addAction("🧠 Long-Term Memory")
        menu.addSeparator()

        change_char_action = menu.addAction("🎭 Change Character")
        char_cfg_action = menu.addAction("⚙️ Character Settings")
        menu.addSeparator()

        always_top_action = menu.addAction("📌 Always on Top")
        always_top_action.setCheckable(True)
        always_top_action.setChecked(bool(self.windowFlags() & Qt.WindowStaysOnTopHint))

        stop_action = menu.addAction("🛑 Stop Speaking (ESC)")
        menu.addSeparator()

        hide_action = menu.addAction("👁️ Minimize to Tray")
        exit_action = menu.addAction("✕ Exit Companion")

        action = menu.exec_(QCursor.pos())

        if action == chat_action:
            self._toggle_chat_drawer()
        elif action == task_action:
            self._toggle_task_panel()
        elif action == voice_action:
            self._toggle_voice_mode()
        elif action == memory_action:
            self._open_memory_viewer()
        elif action == change_char_action:
            self._open_character_selection()
        elif action == char_cfg_action:
            self._open_character_settings()
        elif action == always_top_action:
            self._toggle_always_on_top(always_top_action.isChecked())
        elif action == stop_action:
            self._interrupt_speech()
        elif action == hide_action:
            self._minimize_to_tray()
        elif action == exit_action:
            QApplication.instance().quit()

    def _open_character_selection(self):
        dlg = CharacterSelectionDialog(self.char_manager, parent=self)
        dlg.character_changed.connect(self._on_character_switched)
        dlg.exec_()

    def _open_character_settings(self):
        char_id = self.char_manager.active_character_id
        dlg = CharacterSettingsDialog(self.char_manager, char_id=char_id, parent=self)
        if dlg.exec_():
            self._on_character_switched(char_id)

    def _open_memory_viewer(self):
        dlg = MemoryViewerDialog(self)
        dlg.exec_()

    def _create_renderer_for_active_character(self):
        """Creates and initializes character renderer based on manifest renderer_type (2d, living, 3d)."""
        manifest = self.char_manager.get_active_manifest()
        renderer_type = manifest.get("renderer_type", "2d")
        char_path = self.char_manager.get_active_character_path()

        if renderer_type == "living":
            from desktop.character_renderer import LivingCharacterRenderer
            renderer = LivingCharacterRenderer(self)
        elif renderer_type == "3d":
            try:
                from desktop.renderer_3d import Model3DRenderer
                renderer = Model3DRenderer(self)
            except Exception as e:
                logger.warning(f"Fallback to 2D renderer: {e}")
                renderer = Sprite2DRenderer(self)
        else:
            renderer = Sprite2DRenderer(self)

        renderer.load(char_path)
        return renderer

    def _on_character_switched(self, char_id: str):
        new_renderer = self._create_renderer_for_active_character()

        # Replace renderer widget in left column layout
        left_col = self.centralWidget().layout().itemAt(0).layout()
        old_renderer = self.character_renderer
        left_col.replaceWidget(old_renderer, new_renderer)
        old_renderer.deleteLater()

        self.character_renderer = new_renderer
        self.character_renderer.state_changed.connect(self._on_renderer_state_changed)

        manifest = self.char_manager.get_active_manifest()
        char_name = manifest.get("name", "Companion")
        if self.chat_drawer.isVisible():
            self.chat_drawer.append_chat_message("assistant", f"✨ <i>Character switched to: <b>{char_name}</b></i>")

    def _toggle_always_on_top(self, enable: bool):
        flags = self.windowFlags()
        if enable:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def _on_renderer_state_changed(self, state: str):
        dot_colors = {
            "IDLE": "#10b981",
            "LISTENING": "#38bdf8",
            "THINKING": "#f59e0b",
            "SPEAKING": "#818cf8",
            "TALKING": "#818cf8",
            "HAPPY": "#10b981",
            "WORKING": "#06b6d4",
            "ERROR": "#f43f5e"
        }
        dot = dot_colors.get(state, "#94a3b8")
        self.status_pill.setText(f"● {state}")
        self.status_pill.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(14, 17, 24, 0.94);
                color: {dot};
                border: 1px solid #232a3d;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Arial, sans-serif;
                font-weight: 600;
                font-size: 10px;
                border-radius: 9px;
                padding: 3px 12px;
                letter-spacing: 0.5px;
            }}
        """)


    def _toggle_chat_drawer(self):
        if self.chat_drawer.isVisible():
            self.chat_drawer.hide()
        else:
            self.chat_drawer.show()

    def _toggle_task_panel(self):
        if self.task_panel.isVisible():
            self.task_panel.hide()
        else:
            self.task_panel.show()

    def _send_chat_message(self, text: str):
        self.chat_drawer.append_chat_message("user", text)
        self.character_renderer.set_state("THINKING")
        self.task_panel.set_working(f"Processing '{text[:25]}...'")
        self.chat_drawer.start_thinking()

        self.active_chat_worker = ChatWorker(text, speak=True)
        self.active_chat_worker.token_received.connect(self._on_chat_token)
        self.active_chat_worker.tool_started.connect(self._on_chat_tool_started)
        self.active_chat_worker.response_received.connect(self._on_chat_response)
        self.active_chat_worker.error_occurred.connect(self._on_error)
        self.active_chat_worker.start()

    def _on_chat_token(self, token: str):
        if self.character_renderer.current_state != "SPEAKING":
            self.character_renderer.set_state("SPEAKING")
        self.chat_drawer.append_stream_token(token)

    def _on_chat_tool_started(self, tool_name: str):
        self.character_renderer.set_state("WORKING")
        self.task_panel.set_working(f"Executing: {tool_name}")


    def _toggle_voice_mode(self):
        if self.voice_mode_active:
            self.voice_mode_active = False
            self.silence_count = 0
            self._interrupt_speech()
            self.mic_quick_btn.setText("🎤 Voice")
            self.mic_quick_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 140, 255, 0.85);
                    color: white; border: none; border-radius: 12px; font-weight: bold; font-size: 11px; padding: 6px 10px;
                }
            """)
            if self.chat_drawer.isVisible():
                self.chat_drawer.append_chat_message("assistant", "<i>Voice Mode Stopped.</i>")
        else:
            self.voice_mode_active = True
            self.silence_count = 0
            self.mic_quick_btn.setText("🔴 Listening")
            self.mic_quick_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 40, 40, 0.95);
                    color: white; border: none; border-radius: 12px; font-weight: bold; font-size: 11px; padding: 6px 10px;
                }
            """)
            if not self.chat_drawer.isVisible():
                self.chat_drawer.show()

            self.chat_drawer.append_chat_message("assistant", "🔥 <i>Voice Conversation Active! Start speaking...</i>")
            self._start_voice_listener_cycle()

    def _start_voice_listener_cycle(self):
        if not self.voice_mode_active:
            return

        from voice_assistant.audio.sound_effects import play_listening_chime
        play_listening_chime()

        self.character_renderer.set_state("LISTENING")
        self.task_panel.set_working("Listening to microphone...")

        self.active_voice_worker = VoiceWorker()
        self.active_voice_worker.response_received.connect(self._on_voice_response)
        self.active_voice_worker.error_occurred.connect(self._on_error)
        self.active_voice_worker.start()

    def _apply_response_expression(self, text: str):
        """Phase 3 — Infer character emotion from assistant response text and apply facial expression."""
        if not text:
            return
        t_low = text.lower()
        if any(w in t_low for w in ["*laughs*", "*laughing*", "haha", "chuckle", "😂", "rofl"]):
            self.character_renderer.set_expression("LAUGH")
        elif any(w in t_low for w in ["*smiles*", "*smiling*", "*grins*", "awesome", "great!", "happy to help", "glad"]):
            self.character_renderer.set_expression("HAPPY")
        elif any(w in t_low for w in ["*winks*", "*winking*", ";)", "got it!"]):
            self.character_renderer.set_expression("WINK")
        elif any(w in t_low for w in ["*confused*", "huh?", "puzzled", "not sure", "strange"]):
            self.character_renderer.set_expression("CONFUSED")
        elif any(w in t_low for w in ["*surprised*", "wow!", "whoa", "incredible"]):
            self.character_renderer.set_expression("SURPRISED")
        else:
            self.character_renderer.set_expression("SMILE")

    def _on_chat_response(self, user_text: str, ai_response: str, tool_exec: str):
        self.character_renderer.set_state("SPEAKING")
        self._apply_response_expression(ai_response)
        self.chat_drawer.finish_streaming_response(full_text=ai_response, tool_exec=tool_exec)

        # Bubble
        bubble_pos = self.pos() + QPoint(10, -80)
        self.chat_bubble.move(bubble_pos)
        self.chat_bubble.show_message(ai_response, timeout_ms=6000)

        if tool_exec:
            self.task_panel.complete_step(f"Executed: {tool_exec}")

        self.task_panel.complete_step("Generated response")
        self.speech_poll_timer.start()

    def _on_voice_response(self, transcript: str, ai_response: str, tool_exec: str, has_speech: bool):
        if not self.voice_mode_active:
            self.character_renderer.set_state("IDLE")
            return

        if has_speech and transcript:
            self.silence_count = 0
            self.chat_drawer.append_chat_message("user", transcript)
            
            # Show visual user speech bubble showing exactly what the user said
            user_bubble_pos = self.pos() + QPoint(10, -130)
            self.user_bubble.move(user_bubble_pos)
            self.user_bubble.show_user_speech(transcript, timeout_ms=4500)

            self.character_renderer.set_state("SPEAKING")
            self._apply_response_expression(ai_response)
            self.chat_drawer.append_chat_message("assistant", ai_response)

            bubble_pos = self.pos() + QPoint(10, -80)
            self.chat_bubble.move(bubble_pos)
            self.chat_bubble.show_message(ai_response, timeout_ms=6000)

            if tool_exec:
                self.chat_drawer.append_chat_message("assistant", f"⚡ <i>Executed tool: {tool_exec}</i>")
                self.task_panel.complete_step(f"Executed: {tool_exec}")

            self.task_panel.complete_step("Response delivered")
            self.speech_poll_timer.start()

            # Schedule next listening cycle after brief delay
            QTimer.singleShot(1500, self._start_voice_listener_cycle)
        else:
            self.silence_count += 1
            if self.silence_count >= 3:
                self.voice_mode_active = False
                self.silence_count = 0
                self.character_renderer.set_state("IDLE")
                self.mic_quick_btn.setText("🎤 Voice")
                self.mic_quick_btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(0, 140, 255, 0.85);
                        color: white; border: none; border-radius: 12px; font-weight: bold; font-size: 11px; padding: 6px 10px;
                    }
                """)
                self.chat_drawer.append_chat_message("assistant", "<i>Voice Mode paused due to silence. Click 'Voice' to talk again!</i>")
            else:
                QTimer.singleShot(400, self._start_voice_listener_cycle)

    def _check_speech_status(self):
        """Poll backend voice status to return to IDLE when audio finishes."""
        try:
            res = requests.get(f"{API_BASE_URL}/voice/status", timeout=1)
            if res.status_code == 200:
                is_speaking = res.json().get("is_speaking", False)
                if not is_speaking:
                    self.speech_poll_timer.stop()
                    if not self.voice_mode_active:
                        self.character_renderer.set_state("IDLE")
                        self.task_panel.set_idle()
        except Exception:
            self.speech_poll_timer.stop()
            self.character_renderer.set_state("IDLE")

    def _interrupt_speech(self):
        """Barge-In: Instantly cancel speech synthesis and reset to IDLE."""
        logger.info("Barge-In triggered: stopping speech and task execution.")
        if self.active_chat_worker and self.active_chat_worker.isRunning():
            self.active_chat_worker.stop()

        try:
            requests.post(f"{API_BASE_URL}/voice/stop", timeout=2)
        except Exception:
            pass

        self.speech_poll_timer.stop()
        self.character_renderer.set_state("IDLE")
        self.task_panel.set_idle()
        self.chat_bubble.hide()

    def _on_error(self, err_msg: str):
        self.voice_mode_active = False
        self.character_renderer.set_state("ERROR")
        self.mic_quick_btn.setText("🎤 Voice")
        self.chat_drawer.append_chat_message("assistant", f"⚠️ {err_msg}")
        self.task_panel.set_idle()
        QTimer.singleShot(3000, lambda: self.character_renderer.set_state("IDLE"))


def main():
    app = QApplication(sys.argv)
    window = AceDesktopWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
