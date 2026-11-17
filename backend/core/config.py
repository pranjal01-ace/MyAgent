import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Centralized application configuration."""
    # Application & API
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    CHARACTER_NAME: str = "Portgas D. Ace"

    # Ollama LLM
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3:latest"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/ace_ai")

    # Speech (TTS / STT)
    VOICE_RATE: int = 180
    VOICE_VOLUME: float = 1.0
    EDGE_TTS_VOICE: str = "en-US-GuyNeural"
    TTS_SPEED: float = 1.15

    # VAD & Turn-taking
    MIN_SILENCE_DURATION: float = 0.35
    MIN_SPEECH_DURATION: float = 0.20

    # Vector store
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "knowledge"

    # Tool & Action Platform (Phase 1)
    TOOL_DEFAULT_TIMEOUT: float = 10.0
    ALLOWED_APPLICATIONS: list[str] = [
        "chrome", "google chrome", "notepad", "calculator", "calc",
        "code", "vscode", "vs code", "explorer", "task manager",
        "taskmgr", "terminal", "cmd", "powershell", "edge"
    ]

    # Vision & Gesture Subsystem (Phase 3)
    GESTURE_ENABLED: bool = False
    CAMERA_INDEX: int = 0
    GESTURE_CAMERA_WIDTH: int = 640
    GESTURE_CAMERA_HEIGHT: int = 480
    GESTURE_CAMERA_FPS: int = 15
    GESTURE_CONFIDENCE_THRESHOLD: float = 0.65
    GESTURE_COOLDOWN_MS: int = 1000

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

# Ensure required runtime directories exist
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data" / "audio").mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data" / "documents").mkdir(parents=True, exist_ok=True)
(BASE_DIR / "assets" / "character").mkdir(parents=True, exist_ok=True)
