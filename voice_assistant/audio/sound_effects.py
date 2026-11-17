import logging
import threading
import numpy as np

logger = logging.getLogger("assistant.audio.sound_effects")

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

_listening_sound = None
_processing_sound = None
_init_done = False

def _ensure_mixer_init():
    global _init_done, _listening_sound, _processing_sound
    if _init_done or not PYGAME_AVAILABLE:
        return

    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=22050, size=-16, channels=2)

        _listening_sound = _generate_chime(f_start=400, f_end=550, duration_ms=75, volume=0.12)
        _processing_sound = _generate_chime(f_start=550, f_end=400, duration_ms=75, volume=0.12)
        _init_done = True
    except Exception as e:
        logger.warning(f"Could not initialize Pygame sound effects: {e}")

def _generate_chime(f_start: int, f_end: int, duration_ms: int = 75, volume: float = 0.12):
    sample_rate = 22050
    n_samples = int(sample_rate * (duration_ms / 1000.0))
    t = np.linspace(0, duration_ms / 1000.0, n_samples, False)
    freqs = np.linspace(f_start, f_end, n_samples)
    
    # Smooth sine wave
    waveform = np.sin(2 * np.pi * freqs * t) * volume

    # Soft attack and decay envelope to eliminate popping/clicking
    envelope = np.ones(n_samples)
    attack = int(n_samples * 0.15)
    decay = int(n_samples * 0.35)
    envelope[:attack] = np.linspace(0, 1, attack)
    envelope[-decay:] = np.linspace(1, 0, decay)

    audio_int16 = (waveform * envelope * 32767.0).astype(np.int16)
    stereo_data = np.column_stack((audio_int16, audio_int16))

    try:
        return pygame.sarray.make_sound(stereo_data)
    except Exception:
        return None

def play_listening_chime():
    """Play soft low-volume chime indicating listening has started."""
    def _play():
        _ensure_mixer_init()
        if _listening_sound:
            try:
                _listening_sound.play()
            except Exception:
                pass
    threading.Thread(target=_play, daemon=True).start()

def play_processing_chime():
    """Play soft low-volume chime indicating speech finished and processing started."""
    def _play():
        _ensure_mixer_init()
        if _processing_sound:
            try:
                _processing_sound.play()
            except Exception:
                pass
    threading.Thread(target=_play, daemon=True).start()
