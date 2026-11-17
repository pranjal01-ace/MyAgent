from abc import ABC, abstractmethod

class TTSProvider(ABC):
    """Abstract base class for Text-To-Speech providers with interruption support."""

    @abstractmethod
    async def speak(self, text: str):
        """Synthesize and play audio for the given text chunk."""
        pass

    @abstractmethod
    async def stop(self):
        """Immediately stop speech playback and cancel ongoing TTS queue."""
        pass
