import os
import io
import time
import tempfile
import logging
import speech_recognition as sr

logger = logging.getLogger("ace.stt")

# Try importing faster-whisper for fast local speech recognition
try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    logger.warning("faster-whisper not available, using Google Web STT fallback.")

class STTEngine:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        
        # Comfortable speech parameters allowing mid-sentence pauses & long thoughts:
        self.recognizer.pause_threshold = 2.0        # Waits 2.0 seconds of silence so user can pause comfortably mid-sentence!
        self.recognizer.phrase_threshold = 0.3
        self.recognizer.non_speaking_duration = 0.8

        self.whisper_model = None
        if FASTER_WHISPER_AVAILABLE:
            try:
                logger.info("Loading Faster-Whisper local model (tiny.en)...")
                self.whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
                logger.info("Faster-Whisper model loaded successfully!")
            except Exception as e:
                logger.error(f"Failed to load Faster-Whisper model: {e}")
                self.whisper_model = None

    def listen_and_transcribe(self, timeout: int = 8, phrase_time_limit: int = 30) -> str:
        """Record full microphone speech comfortably allowing mid-sentence pauses."""
        try:
            with sr.Microphone() as source:
                logger.info("Microphone ready. Adjusting for ambient noise...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                logger.info("Listening on microphone for complete thought (2.0s pause threshold)...")
                
                # Listen with 2.0s pause threshold & 30s limit so user is never cut off prematurely
                audio_data = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                logger.info("Audio recorded! Transcribing complete sentence...")

                if self.whisper_model:
                    wav_bytes = audio_data.get_wav_data()
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                        temp_wav.write(wav_bytes)
                        temp_wav_path = temp_wav.name

                    try:
                        segments, info = self.whisper_model.transcribe(
                            temp_wav_path,
                            beam_size=1,
                            language="en",
                            vad_filter=True
                        )
                        text = " ".join([segment.text for segment in segments]).strip()
                        logger.info(f"Faster-Whisper Transcribed: '{text}'")
                        return text
                    finally:
                        if os.path.exists(temp_wav_path):
                            try:
                                os.remove(temp_wav_path)
                            except Exception:
                                pass
                else:
                    text = self.recognizer.recognize_google(audio_data)
                    logger.info(f"Google Web STT Transcribed: '{text}'")
                    return text.strip()

        except sr.WaitTimeoutError:
            logger.info("Silence timeout (user did not speak).")
            return ""
        except sr.UnknownValueError:
            logger.info("Speech recognition could not parse audio.")
            return ""
        except Exception as e:
            logger.error(f"STT error: {e}")
            return ""

stt_engine = STTEngine()
