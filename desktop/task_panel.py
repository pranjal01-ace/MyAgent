import logging
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, pyqtSignal as Signal
from PyQt5.QtGui import QFont, QColor

logger = logging.getLogger("desktop.task_panel")

class AgentTaskPanel(QFrame):
    """Transparent, floating Agent Task Transparency Panel showing step-by-step progress and cancellation."""
    stop_task_signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(320)
        self.setFixedHeight(300)
        self.setStyleSheet("""
            AgentTaskPanel {
                background-color: rgba(18, 20, 26, 0.96);
                border: 2px solid rgba(0, 180, 255, 0.7);
                border-radius: 16px;
            }
            QLabel {
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QListWidget {
                background-color: rgba(10, 12, 16, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                padding: 6px;
                color: #ffffff;
                font-size: 12px;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton {
                background-color: rgba(255, 50, 50, 0.85);
                color: white;
                border: none;
                border-radius: 10px;
                font-weight: bold;
                font-size: 12px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: rgba(255, 20, 20, 1.0);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header with Title and Close
        header_layout = QHBoxLayout()
        self.title_label = QLabel("⚡ Agent Task Activity", self)
        self.title_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        header_layout.addWidget(self.title_label)

        close_btn = QPushButton("✕", self)
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("background-color: transparent; color: #888888; font-size: 13px; border: none;")
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)
        layout.addLayout(header_layout)

        # Status text
        self.status_label = QLabel("Idle - Waiting for agent tasks", self)
        self.status_label.setStyleSheet("color: #00d4ff; font-weight: bold; font-size: 12px;")
        layout.addWidget(self.status_label)

        # Progress Steps List
        self.steps_list = QListWidget(self)
        layout.addWidget(self.steps_list)

        # Bottom Bar: Stop Button
        bottom_bar = QHBoxLayout()
        self.stop_btn = QPushButton("🛑 Stop Task", self)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        bottom_bar.addWidget(self.stop_btn)

        clear_btn = QPushButton("Clear", self)
        clear_btn.setStyleSheet("background-color: rgba(60, 65, 80, 0.8); color: #ccc;")
        clear_btn.clicked.connect(self.clear_tasks)
        bottom_bar.addWidget(clear_btn)

        layout.addLayout(bottom_bar)

    def set_working(self, task_name: str):
        self.status_label.setText(f"● Working: {task_name}")
        self.status_label.setStyleSheet("color: #ffaa00; font-weight: bold; font-size: 12px;")
        item = QListWidgetItem(f"● {task_name}")
        item.setForeground(QColor("#ffaa00"))
        self.steps_list.addItem(item)
        self.steps_list.scrollToBottom()

    def complete_step(self, step_name: str):
        item = QListWidgetItem(f"✓ {step_name}")
        item.setForeground(QColor("#00ff88"))
        self.steps_list.addItem(item)
        self.steps_list.scrollToBottom()

    def set_idle(self):
        self.status_label.setText("Idle - Ready")
        self.status_label.setStyleSheet("color: #00ff88; font-weight: bold; font-size: 12px;")

    def clear_tasks(self):
        self.steps_list.clear()
        self.set_idle()

    def _on_stop_clicked(self):
        item = QListWidgetItem("🛑 Task cancelled by user.")
        item.setForeground(QColor("#ff4444"))
        self.steps_list.addItem(item)
        self.set_idle()
        self.stop_task_signal.emit()
