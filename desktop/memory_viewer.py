import requests
import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

logger = logging.getLogger("desktop.memory_viewer")

API_BASE_URL = "http://127.0.0.1:8000/api"

class MemoryViewerDialog(QDialog):
    """Dialog allowing user to inspect, create, and delete long-term companion memories."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🧠 Companion Long-Term Memory")
        self.setFixedSize(540, 420)
        self.setStyleSheet("""
            QDialog {
                background-color: #181a22;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 12px;
            }
            QTableWidget {
                background-color: #101218;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                color: #f0f0f0;
                gridline-color: #2a2d3a;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #222634;
                color: #ff9d42;
                font-weight: bold;
                padding: 6px;
                border: none;
            }
            QLineEdit {
                background-color: #222634;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 6px;
                padding: 6px;
                color: #ffffff;
                font-size: 12px;
            }
            QPushButton {
                background-color: #ff6400;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #ff7814;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header Title
        title = QLabel("🧠 Long-Term Memories (Stored in SQLite)", self)
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        layout.addWidget(title)

        # Memory Table
        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Key", "Value", "Category"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        # Add Memory Row
        add_layout = QHBoxLayout()
        self.key_input = QLineEdit(self)
        self.key_input.setPlaceholderText("Key (e.g. favorite_food)")
        add_layout.addWidget(self.key_input)

        self.val_input = QLineEdit(self)
        self.val_input.setPlaceholderText("Value (e.g. Meat / Pizza)")
        add_layout.addWidget(self.val_input)

        add_btn = QPushButton("Add Memory", self)
        add_btn.clicked.connect(self._add_memory)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)

        # Action Buttons Row
        btn_row = QHBoxLayout()
        delete_btn = QPushButton("Delete Selected", self)
        delete_btn.setStyleSheet("background-color: #d93838;")
        delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(delete_btn)

        refresh_btn = QPushButton("Refresh", self)
        refresh_btn.setStyleSheet("background-color: #3867d6;")
        refresh_btn.clicked.connect(self.load_memories)
        btn_row.addWidget(refresh_btn)

        close_btn = QPushButton("Close", self)
        close_btn.setStyleSheet("background-color: #4b6584;")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

        self.load_memories()

    def load_memories(self):
        try:
            res = requests.get(f"{API_BASE_URL}/memories/detailed", timeout=5)
            if res.status_code == 200:
                data = res.json().get("memories", [])
                self.table.setRowCount(len(data))
                for row, item in enumerate(data):
                    self.table.setItem(row, 0, QTableWidgetItem(item.get("key", "")))
                    self.table.setItem(row, 1, QTableWidgetItem(item.get("value", "")))
                    self.table.setItem(row, 2, QTableWidgetItem(item.get("category", "")))
        except Exception as e:
            logger.warning(f"Failed to load memories: {e}")

    def _add_memory(self):
        k = self.key_input.text().strip()
        v = self.val_input.text().strip()
        if not k or not v:
            QMessageBox.warning(self, "Missing Fields", "Please provide both Key and Value.")
            return

        try:
            res = requests.post(f"{API_BASE_URL}/memory", json={"key": k, "value": v, "category": "user_info"}, timeout=5)
            if res.status_code == 200:
                self.key_input.clear()
                self.val_input.clear()
                self.load_memories()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add memory: {e}")

    def _delete_selected(self):
        curr_row = self.table.currentRow()
        if curr_row < 0:
            QMessageBox.information(self, "Select Item", "Please select a memory row to delete.")
            return

        key_item = self.table.item(curr_row, 0)
        if not key_item:
            return

        key = key_item.text()
        try:
            res = requests.delete(f"{API_BASE_URL}/memory/{key}", timeout=5)
            if res.status_code == 200:
                self.load_memories()
            else:
                QMessageBox.warning(self, "Error", "Failed to delete memory.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete memory: {e}")
