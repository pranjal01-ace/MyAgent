"""Legacy facade re-exporting TTSEngine from the voice domain module."""
from backend.voice.service import (
    TTSEngine,
    tts_engine,
    _generate_edge_tts_file,
    EDGE_TTS_AVAILABLE,
    ACE_VOICE
)

__all__ = [
    "TTSEngine",
    "tts_engine",
    "_generate_edge_tts_file",
    "EDGE_TTS_AVAILABLE",
    "ACE_VOICE"
]
