import os
import sys
import time
import threading
import uvicorn
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backend.config import settings

def start_backend():
    """Runs FastAPI backend server with Uvicorn."""
    uvicorn.run("backend.main:app", host=settings.API_HOST, port=settings.API_PORT, log_level="info")

def main():
    print("==================================================")
    print("  🔥 Portgas D. Ace 2D Anime AI Desktop Agent 🔥")
    print("==================================================")
    print(f"[1/2] Launching FastAPI Backend on http://{settings.API_HOST}:{settings.API_PORT}...")

    # Start FastAPI backend in background daemon thread
    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()

    time.sleep(2) # Give backend server time to initialize

    print("[2/2] Launching PyQt5 Desktop Transparent Overlay GUI...")
    from PyQt5.QtWidgets import QApplication
    from desktop.window import AceDesktopWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Portgas D. Ace Companion")
    window = AceDesktopWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
