import os
import tempfile
import logging
import asyncio
import numpy as np
from typing import Dict, Any

from voice_assistant.config import settings
from voice_assistant.stt.base import STTProvider
from voice_assistant.audio.audio_utils import int16_to_float32

logger = logging.getLogger("assistant.stt")

# Common Whisper hallucinations to clean
HALLUCINATIONS = {
    "Thank you for watching!", "Thanks for watching!", "Subtitles by",
    "Amara.org", "you", "Thank you.", "Bye.", "So,"
}

class FasterWhisperSTT(STTProvider):
    """Faster-Whisper STT Provider supporting local low-latency transcription."""

    def __init__(self):
        self.model_name = settings.WHISPER_MODEL
        self.device = settings.WHISPER_DEVICE
        self.compute_type = settings.WHISPER_COMPUTE_TYPE
        self.language = None if settings.STT_LANGUAGE == "auto" else settings.STT_LANGUAGE

        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            from faster_whisper import WhisperModel
            logger.info(f"Loading Faster-Whisper model '{self.model_name}' on {self.device} ({self.compute_type})...")
            self.model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type
            )
            logger.info("Faster-Whisper model loaded successfully!")
        except Exception as e:
            logger.error(f"Failed to load Faster-Whisper model ({e}). Fallback mode active.")
            self.model = None

    async def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> Dict[str, Any]:
        if audio_data is None or len(audio_data) == 0:
            return {"text": "", "language": "en", "confidence": 0.0}

        def _sync_transcribe() -> Dict[str, Any]:
            if self.model is None:
                return {"text": "", "language": "en", "confidence": 0.0}

            # Convert to float32
            float_audio = int16_to_float32(audio_data)
            
            # Save audio to temporary WAV file for faster_whisper
            import wave
            temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            try:
                with wave.open(temp_wav.name, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes((float_audio * 32767).astype(np.int16).tobytes())
                
                segments, info = self.model.transcribe(
                    temp_wav.name,
                    beam_size=1,
                    vad_filter=True,
                    language=self.language
                )
                
                segment_texts = []
                prob_sum = 0.0
                count = 0
                for seg in segments:
                    segment_texts.append(seg.text.strip())
                    prob_sum += getattr(seg, "avg_logprob", 0.0)
                    count += 1
                
                full_text = " ".join(segment_texts).strip()

                # Clean obvious hallucinations
                if full_text in HALLUCINATIONS or len(full_text) <= 1:
                    full_text = ""

                confidence = round(np.exp(prob_sum / max(count, 1)), 2) if count > 0 else 0.9

                return {
                    "text": full_text,
                    "language": info.language if hasattr(info, "language") else "en",
                    "confidence": confidence
                }
            finally:
                if os.path.exists(temp_wav.name):
                    try:
                        os.remove(temp_wav.name)
                    except Exception:
                        pass

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync_transcribe)
