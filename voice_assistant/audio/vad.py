import logging
import numpy as np
from voice_assistant.config import settings
from voice_assistant.audio.audio_utils import int16_to_float32

logger = logging.getLogger("assistant.vad")

class SileroVAD:
    """Silero Voice Activity Detection engine for real-time speech frame classification."""

    def __init__(
        self,
        threshold: float = None,
        min_speech_duration: float = None,
        min_silence_duration: float = None
    ):
        self.threshold = threshold or settings.VAD_THRESHOLD
        self.min_speech_duration = min_speech_duration or settings.MIN_SPEECH_DURATION
        self.min_silence_duration = min_silence_duration or settings.MIN_SILENCE_DURATION
        self.sample_rate = 16000

        self.session = None
        self._init_onnx_model()

    def _init_onnx_model(self):
        try:
            import onnxruntime as ort
            import urllib.request
            from pathlib import Path

            model_dir = Path(__file__).resolve().parent.parent / "data"
            model_dir.mkdir(parents=True, exist_ok=True)
            model_path = model_dir / "silero_vad.onnx"

            if not model_path.exists():
                logger.info("Downloading Silero VAD ONNX model...")
                url = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
                urllib.request.urlretrieve(url, str(model_path))
                logger.info("Silero VAD ONNX model downloaded successfully!")

            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            self.session = ort.InferenceSession(str(model_path), opts)
            self._reset_states()
            logger.info("Silero VAD ONNX Session initialized successfully!")
        except Exception as e:
            logger.warning(f"ONNX Silero VAD load failed ({e}); using energy fallback VAD.")
            self.session = None

    def _reset_states(self):
        self._state = np.zeros((2, 1, 128), dtype=np.float32)

    def is_speech(self, frame: np.ndarray) -> bool:
        """Classify a 512-sample (32ms) audio frame as speech or non-speech."""
        if frame is None or len(frame) == 0:
            return False

        float_frame = int16_to_float32(frame)
        if float_frame.ndim == 1:
            float_frame = np.expand_dims(float_frame, axis=0)

        if self.session is not None:
            try:
                # Silero VAD ONNX inference
                inputs = {
                    "input": float_frame.astype(np.float32),
                    "state": self._state,
                    "sr": np.array(self.sample_rate, dtype=np.int64)
                }
                out, self._state = self.session.run(None, inputs)
                prob = float(out[0][0])
                return prob >= self.threshold
            except Exception as e:
                logger.error(f"VAD ONNX error: {e}")

        # Fallback energy-based VAD if ONNX is unavailable
        energy = np.sqrt(np.mean(float_frame**2))
        return bool(energy >= 0.02)

