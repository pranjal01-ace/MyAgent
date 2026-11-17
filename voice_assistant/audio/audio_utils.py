import numpy as np

SAMPLE_RATE = 16000

def int16_to_float32(audio_int16: np.ndarray) -> np.ndarray:
    """Convert int16 PCM audio array to normalized float32 [-1.0, 1.0]."""
    if audio_int16.dtype == np.float32:
        return audio_int16
    return audio_int16.astype(np.float32) / 32768.0

def float32_to_int16(audio_float32: np.ndarray) -> np.ndarray:
    """Convert float32 [-1.0, 1.0] audio array to int16 PCM."""
    if audio_float32.dtype == np.int16:
        return audio_float32
    clipped = np.clip(audio_float32, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16)
