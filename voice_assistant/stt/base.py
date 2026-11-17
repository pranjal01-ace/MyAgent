from abc import ABC, abstractmethod
from typing import Dict, Any
import numpy as np

class STTProvider(ABC):
    """Abstract base class for Speech-To-Text transcription providers."""

    @abstractmethod
    async def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> Dict[str, Any]:
        """
        Transcribes PCM audio array and returns structured output:
        {
            "text": "transcribed text",
            "language": "en",
            "confidence": 0.95
        }
        """
        pass
