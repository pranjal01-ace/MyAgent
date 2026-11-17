from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3:latest"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    # PostgreSQL Database
    DATABASE_URL: str = "postgresql://postgres@localhost:5432/ace_ai"
    USE_POSTGRES: bool = True

    # Vector Store (Qdrant Vector DB)
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "knowledge"
    QDRANT_STORAGE_PATH: str = str(BASE_DIR / "data" / "qdrant")

    # STT (Faster-Whisper)
    WHISPER_MODEL: str = "tiny.en"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    STT_LANGUAGE: str = "auto"

    # Silero VAD
    VAD_THRESHOLD: float = 0.5
    MIN_SPEECH_DURATION: float = 0.20
    MIN_SILENCE_DURATION: float = 0.35
    MAX_UTTERANCE_DURATION: float = 30.0

    # RAG
    RAG_TOP_K: int = 5
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 150

    # Conversation Memory
    MAX_HISTORY_MESSAGES: int = 20

    # Wake Word
    WAKE_WORD_ENABLED: bool = False
    WAKE_WORD: str = "computer"

    # TTS
    TTS_VOICE: str = "en-US-GuyNeural"
    TTS_SPEED: float = 1.15

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Ensure required directories exist
(BASE_DIR / "data" / "documents").mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data" / "audio").mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data" / "qdrant").mkdir(parents=True, exist_ok=True)
