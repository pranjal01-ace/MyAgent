import pytest
import numpy as np
from voice_assistant.audio.vad import SileroVAD

def test_silero_vad_initialization():
    vad = SileroVAD(threshold=0.5, min_speech_duration=0.25, min_silence_duration=0.6)
    assert vad.threshold == 0.5
    assert vad.sample_rate == 16000

def test_vad_silence_frame():
    vad = SileroVAD()
    silence_frame = np.zeros(512, dtype=np.int16)
    is_speech = vad.is_speech(silence_frame)
    assert is_speech is False

def test_vad_noise_frame():
    vad = SileroVAD()
    # High energy noise array
    loud_frame = (np.sin(np.linspace(0, 100, 512)) * 20000).astype(np.int16)
    is_speech = vad.is_speech(loud_frame)
    assert isinstance(is_speech, bool)
