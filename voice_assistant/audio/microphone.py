import queue
import logging
import sounddevice as sd
import numpy as np
from voice_assistant.audio.audio_utils import SAMPLE_RATE, float32_to_int16

logger = logging.getLogger("assistant.mic")

class ContinuousMicrophone:
    """Non-blocking sounddevice continuous microphone audio capture stream."""

    def __init__(self, sample_rate: int = SAMPLE_RATE, block_size: int = 512):
        self.sample_rate = sample_rate
        self.block_size = block_size # 512 samples = 32ms at 16kHz
        self.audio_queue = queue.Queue()
        self.stream = None
        self._muted = False

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"Audio stream status: {status}")
        if self._muted:
            # Push silence if muted
            self.audio_queue.put(np.zeros(frames, dtype=np.int16))
        else:
            pcm_data = float32_to_int16(indata[:, 0])
            self.audio_queue.put(pcm_data)

    def start(self):
        if self.stream is None:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                channels=1,
                dtype="float32",
                callback=self._audio_callback
            )
            self.stream.start()
            logger.info(f"Microphone stream started ({self.sample_rate}Hz, block={self.block_size}).")

    def stop(self):
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            logger.info("Microphone stream stopped.")

    def get_frame(self, block: bool = True, timeout: float = 1.0) -> np.ndarray:
        try:
            return self.audio_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return np.zeros(self.block_size, dtype=np.int16)

    def set_muted(self, muted: bool):
        self._muted = muted
        logger.info(f"Microphone muted: {muted}")

    def is_muted(self) -> bool:
        return self._muted
