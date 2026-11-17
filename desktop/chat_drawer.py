import re
import html
import requests
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QTextBrowser, QLineEdit,
    QPushButton, QLabel, QFrame, QApplication
)
from PyQt5.QtCore import Qt, QUrl, QTimer, pyqtSignal as Signal
from PyQt5.QtGui import QFont, QTextCursor

from desktop.markdown_renderer import render_full_markdown, code_registry

# Backward-compatibility alias for legacy callers and tests
format_markdown_to_html = render_full_markdown

API_BASE_URL = "http://127.0.0.1:8000/api"


class ChatDrawerWidget(QFrame):
    """Sleek developer-grade black chat drawer with streaming, markdown, and modern dark styling."""
    send_message_signal = Signal(str)
    voice_trigger_signal = Signal()
    open_memory_signal = Signal()
    open_settings_signal = Signal()
    open_task_signal = Signal()
    stop_speech_signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(400)
        self.setFixedHeight(540)

        # Developer Obsidian Dark Theme Stylesheet
        self.setStyleSheet("""
            ChatDrawerWidget {
                background-color: #0b0d13;
                border: 1px solid #1f2536;
                border-radius: 12px;
            }
            QLabel {
                color: #e2e8f0;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Arial, sans-serif;
            }
            QTextBrowser, QTextEdit {
                background-color: #0e111a;
                color: #e2e8f0;
                border: 1px solid #1a202c;
                border-radius: 8px;
                padding: 10px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
                line-height: 1.5;
            }
            /* Sleek Custom Dark Scrollbar (No ugly white block!) */
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #252d40;
                border-radius: 3px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3b4663;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QLineEdit {
                background-color: #121622;
                color: #f8fafc;
                border: 1px solid #242c3f;
                border-radius: 8px;
                padding: 8px 12px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #38bdf8;
                background-color: #141926;
            }
            QPushButton {
                background-color: #181e2b;
                color: #94a3b8;
                border: 1px solid #263045;
                border-radius: 6px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #21293a;
                color: #f1f5f9;
                border-color: #384666;
            }
        """)

        self._is_streaming = False
        self._current_stream_text = ""
        self._thinking_active = False
        self._stream_cursor_start = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 1. Header Bar
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(2, 0, 2, 4)

        # Title & Online dot
        title_box = QHBoxLayout()
        title_box.setSpacing(6)
        status_dot = QLabel("●", self)
        status_dot.setStyleSheet("color: #10b981; font-size: 9px;")
        title_box.addWidget(status_dot)

        self.title_label = QLabel("Ace Agent", self)
        self.title_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.title_label.setStyleSheet("color: #f1f5f9;")
        title_box.addWidget(self.title_label)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        # Minimalist Action Buttons
        self.memory_btn = QPushButton("Memory", self)
        self.memory_btn.setToolTip("Open Long-Term Memory")
        self.memory_btn.clicked.connect(self.open_memory_signal.emit)
        header_layout.addWidget(self.memory_btn)

        self.task_btn = QPushButton("Tasks", self)
        self.task_btn.setToolTip("View Activity Log")
        self.task_btn.clicked.connect(self.open_task_signal.emit)
        header_layout.addWidget(self.task_btn)

        self.clear_btn = QPushButton("Clear", self)
        self.clear_btn.setToolTip("Clear conversation history")
        self.clear_btn.clicked.connect(self._clear_chat)
        header_layout.addWidget(self.clear_btn)

        close_btn = QPushButton("✕", self)
        close_btn.setFixedSize(22, 22)
        close_btn.setToolTip("Close Chat")
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #64748b;
                font-size: 12px;
                padding: 0;
            }
            QPushButton:hover {
                color: #f87171;
            }
        """)
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)

        layout.addLayout(header_layout)

        # 2. History Display (Scrollable QTextBrowser with clickable links)
        self.history_display = QTextBrowser(self)
        self.history_display.setReadOnly(True)
        self.history_display.setOpenExternalLinks(False)
        self.history_display.anchorClicked.connect(self._on_anchor_clicked)
        layout.addWidget(self.history_display)

        # 3. Input & Send Bar
        input_layout = QHBoxLayout()
        input_layout.setSpacing(6)

        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Ask a question, run a command, or /help...")
        self.input_field.returnPressed.connect(self._on_send_clicked)
        input_layout.addWidget(self.input_field)

        self.send_btn = QPushButton("Send", self)
        self.send_btn.setFixedWidth(54)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 7px;
                font-weight: 600;
                font-size: 11px;
                padding: 8px 0;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.send_btn.clicked.connect(self._on_send_clicked)
        input_layout.addWidget(self.send_btn)

        self.mic_btn = QPushButton("🎤", self)
        self.mic_btn.setFixedSize(32, 32)
        self.mic_btn.setToolTip("Push to talk / Voice mode")
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e2536;
                color: #94a3b8;
                border: 1px solid #2b354d;
                border-radius: 7px;
                font-size: 12px;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #283248;
                color: #38bdf8;
                border-color: #38bdf8;
            }
        """)
        self.mic_btn.clicked.connect(self._on_mic_clicked)
        input_layout.addWidget(self.mic_btn)

        layout.addLayout(input_layout)

    def _on_anchor_clicked(self, url: QUrl):
        """Handles copy actions triggered from interactive HTML code block and response buttons."""
        url_str = url.toString()
        if url_str.startswith("copy_code:"):
            cid = url_str.split(":", 1)[1]
            raw_code = code_registry.get_code(cid)
            if raw_code is not None:
                QApplication.clipboard().setText(raw_code)
                self._show_copy_feedback(cid, is_code=True)
        elif url_str.startswith("copy_response:"):
            rid = url_str.split(":", 1)[1]
            raw_resp = code_registry.get_response(rid)
            if raw_resp is not None:
                QApplication.clipboard().setText(raw_resp)
                self._show_copy_feedback(rid, is_code=False)

    def _show_copy_feedback(self, target_id: str, is_code: bool = True):
        """Temporarily highlights the Copy button state to '✓ Copied!' for 2 seconds."""
        current_html = self.history_display.toHtml()
        if is_code:
            old_tag = f"copy_code:{target_id}"
            pattern = re.compile(rf"<a\s+href=['\"]copy_code:{re.escape(target_id)}['\"][^>]*>.*?</a>", re.IGNORECASE)
            new_btn = (
                f"<a href='copy_code:{target_id}' style='color: #10b981; text-decoration: none; "
                f"font-size: 10px; font-weight: 700; padding: 2px 8px; background-color: #064e3b; "
                f"border-radius: 4px; border: 1px solid #059669;'>✓ Copied!</a>"
            )
        else:
            pattern = re.compile(rf"<a\s+href=['\"]copy_response:{re.escape(target_id)}['\"][^>]*>.*?</a>", re.IGNORECASE)
            new_btn = (
                f"<a href='copy_response:{target_id}' style='color: #10b981; text-decoration: none; "
                f"font-size: 10px; font-weight: 700; padding: 2px 6px; background-color: #064e3b; "
                f"border-radius: 4px; border: 1px solid #059669;'>✓ Copied!</a>"
            )

        updated_html = pattern.sub(new_btn, current_html)
        if updated_html != current_html:
            sb = self.history_display.verticalScrollBar()
            val = sb.value()
            self.history_display.setHtml(updated_html)
            sb.setValue(val)
            QTimer.singleShot(2000, lambda: self._revert_copy_feedback(target_id, is_code))

    def _revert_copy_feedback(self, target_id: str, is_code: bool = True):
        """Reverts the Copy button text back to normal."""
        current_html = self.history_display.toHtml()
        if is_code:
            pattern = re.compile(rf"<a\s+href=['\"]copy_code:{re.escape(target_id)}['\"][^>]*>.*?</a>", re.IGNORECASE)
            orig_btn = (
                f"<a href='copy_code:{target_id}' style='color: #94a3b8; text-decoration: none; "
                f"font-size: 10px; font-weight: 600; padding: 2px 8px; background-color: #21283b; "
                f"border-radius: 4px; border: 1px solid #2f3a54;'>📋 Copy</a>"
            )
        else:
            pattern = re.compile(rf"<a\s+href=['\"]copy_response:{re.escape(target_id)}['\"][^>]*>.*?</a>", re.IGNORECASE)
            orig_btn = (
                f"<a href='copy_response:{target_id}' style='color: #64748b; text-decoration: none; "
                f"font-size: 10px; font-weight: 600; padding: 2px 6px; background-color: #121622; "
                f"border-radius: 4px; border: 1px solid #1f2738;'>📄 Copy Response</a>"
            )

        updated_html = pattern.sub(orig_btn, current_html)
        if updated_html != current_html:
            sb = self.history_display.verticalScrollBar()
            val = sb.value()
            self.history_display.setHtml(updated_html)
            sb.setValue(val)

    def append_chat_message(self, sender: str, text: str):
        """Appends a completed user or assistant message with clean developer styling."""
        now_str = datetime.now().strftime("%I:%M %p")

        if sender == "user":
            formatted_body = html.escape(text).replace("\n", "<br>")
            bubble_html = (
                f"<div style='margin-top: 10px; margin-bottom: 6px;'>"
                f"<div style='display: flex; justify-content: space-between; margin-bottom: 3px;'>"
                f"<span style='color: #64748b; font-size: 10px; font-weight: 600;'>YOU</span> "
                f"<span style='color: #475569; font-size: 10px;'>{now_str}</span>"
                f"</div>"
                f"<div style='background-color: #151a26; border: 1px solid #232c40; "
                f"border-radius: 7px; padding: 7px 10px; color: #f1f5f9; font-size: 12px; line-height: 1.45;'>"
                f"{formatted_body}"
                f"</div>"
                f"</div>"
            )
        else:
            formatted_body = render_full_markdown(text, is_streaming=False)
            bubble_html = (
                f"<div style='margin-top: 10px; margin-bottom: 6px;'>"
                f"<div style='margin-bottom: 3px;'>"
                f"<span style='color: #38bdf8; font-size: 10px; font-weight: 600;'>✦ ACE AGENT</span> "
                f"<span style='color: #475569; font-size: 10px;'>{now_str}</span>"
                f"</div>"
                f"<div style='background-color: transparent; padding: 2px 4px; "
                f"color: #e2e8f0; font-size: 12px; line-height: 1.5;'>"
                f"{formatted_body}"
                f"</div>"
                f"</div>"
            )

        self.history_display.append(bubble_html)
        self._scroll_to_bottom()

    def start_thinking(self, tool_hint: str = None):
        """Displays subtle developer thinking status without broken raw tags."""
        self._thinking_active = True
        label = f"⚙ Executing {html.escape(tool_hint)}..." if tool_hint else "✦ Thinking..."
        indicator_html = (
            f"<div id='thinking-box' style='margin-top: 6px; margin-bottom: 4px; color: #38bdf8; "
            f"font-size: 11px; font-style: italic;'>"
            f"{label}</div>"
        )
        self.history_display.append(indicator_html)
        self._scroll_to_bottom()

    def start_streaming_response(self):
        """Prepares for real-time token streaming using textCursor to preserve whitespace."""
        self._is_streaming = True
        self._current_stream_text = ""
        self._thinking_active = False

        now_str = datetime.now().strftime("%I:%M %p")
        header_html = (
            f"<div style='margin-top: 12px; margin-bottom: 4px;'>"
            f"<span style='color: #38bdf8; font-size: 10px; font-weight: 600;'>✦ ACE AGENT</span> "
            f"<span style='color: #64748b; font-size: 10px;'>{now_str}</span>"
            f"</div>"
        )
        self.history_display.append(header_html)

        # Move to end and create a clean separate text block for the response
        cursor = self.history_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertBlock()
        self._stream_cursor_start = cursor.position()

        # Switch send button to stop button during streaming
        self.send_btn.setText("Stop")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: #ffffff;
                border: none;
                border-radius: 7px;
                font-weight: 600;
                font-size: 11px;
                padding: 8px 0;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
        """)

    def append_stream_token(self, token: str):
        """Appends a newly received token using insertText so spaces and newlines are NEVER collapsed."""
        if not self._is_streaming:
            self.start_streaming_response()

        self._current_stream_text += token

        # Safe text insertion preserving all spaces, indentation, and newlines!
        cursor = self.history_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self._scroll_to_bottom()

    def finish_streaming_response(self, full_text: str = None, tool_exec: str = None):
        """Finalizes the stream. Seamlessly transforms streamed markdown & code blocks into rich HTML."""
        final = (full_text or self._current_stream_text).strip()
        self._is_streaming = False
        self._current_stream_text = ""
        self._thinking_active = False

        # Reset Send button
        self.send_btn.setText("Send")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 7px;
                font-weight: 600;
                font-size: 11px;
                padding: 8px 0;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)

        rendered = render_full_markdown(final, is_streaming=False)

        if self._stream_cursor_start is not None:
            cursor = self.history_display.textCursor()
            cursor.setPosition(self._stream_cursor_start)
            cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            cursor.insertHtml(rendered)
            self._stream_cursor_start = None
        else:
            self.append_chat_message("assistant", final)

        if tool_exec:
            self.history_display.append(
                f"<div style='margin-top: 4px; margin-bottom: 4px; color: #10b981; font-size: 11px; font-weight: 600;'>"
                f"✓ {html.escape(tool_exec)}</div>"
            )

        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        sb = self.history_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_send_clicked(self):
        # If currently streaming, clicking this button stops/cancels stream
        if self._is_streaming:
            self._on_stop_clicked()
            return

        text = self.input_field.text().strip()
        if not text:
            return

        self.input_field.clear()

        # Check for Slash Commands
        if text.startswith("/"):
            self._handle_slash_command(text)
            return

        self.send_message_signal.emit(text)

    def _handle_slash_command(self, cmd: str):
        c = cmd.lower().strip()
        self.append_chat_message("user", cmd)

        if c == "/help":
            help_text = (
                "**📌 Available Slash Commands:**\n"
                "• **/help** - Show command guide\n"
                "• **/memory** - View and manage persistent PostgreSQL memories\n"
                "• **/tools** - Show desktop agent tools\n"
                "• **/clear** - Clear current conversation\n"
                "• **/voice** - Toggle continuous voice mode\n"
                "• **/stop** - Stop active speech / cancel stream (Barge-in)\n"
                "• **/settings** - Open companion character settings\n\n"
                "**⌨️ Global Shortcuts:**\n"
                "• **ESC** - Instant speech barge-in / cancel\n"
                "• **Ctrl + Space** - Show/Hide companion\n"
                "• **Ctrl + Shift + M** - Toggle Voice Mode\n"
                "• **Ctrl + Shift + A** - Toggle Task Panel"
            )
            self.append_chat_message("assistant", help_text)

        elif c == "/memory":
            self.open_memory_signal.emit()
            self.append_chat_message("assistant", "*Opening Memory Manager...*")

        elif c == "/tools":
            tools_text = (
                "**🛠️ Desktop Agent Tools:**\n"
                "• **get_time** - System date and real-time clock\n"
                "• **get_system_info** - CPU, RAM, Disk, and Battery metrics\n"
                "• **take_screenshot** - Capture desktop to data/screenshots/\n"
                "• **read_clipboard / write_clipboard** - Clipboard access\n"
                "• **open_application** - VS Code, Chrome, Terminal, Notepad, etc.\n"
                "• **open_website / search_web** - Web navigation & search\n"
                "• **list_files / read_file** - Safe filesystem access\n"
                "• **search_knowledge_base** - PostgreSQL RAG Vector Search"
            )
            self.append_chat_message("assistant", tools_text)

        elif c == "/clear":
            self._clear_chat()

        elif c == "/voice":
            self.voice_trigger_signal.emit()

        elif c == "/stop":
            self._on_stop_clicked()

        elif c == "/settings":
            self.open_settings_signal.emit()

        else:
            self.append_chat_message("assistant", f"*Unknown command '{cmd}'. Type **/help** for commands.*")

    def _clear_chat(self):
        self.history_display.clear()
        try:
            requests.post(f"{API_BASE_URL}/conversations/clear", timeout=3)
        except Exception:
            pass
        self.append_chat_message("assistant", "*Conversation cleared.*")

    def _on_stop_clicked(self):
        self.stop_speech_signal.emit()
        self._is_streaming = False
        self.send_btn.setText("Send")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 7px;
                font-weight: 600;
                font-size: 11px;
                padding: 8px 0;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        try:
            requests.post(f"{API_BASE_URL}/voice/stop", timeout=3)
        except Exception:
            pass
        self.append_chat_message("assistant", "🛑 *Stopped generation.*")

    def _on_mic_clicked(self):
        self.voice_trigger_signal.emit()
