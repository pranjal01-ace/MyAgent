"""
Voice Domain Service Layer
==========================
Houses the TTSEngine powering natural, low-latency audio playback for Ace AI.
Key Capabilities:
  - Real-time sentence-streaming playback queue for zero-lag speech during LLM generation
  - ThreadPoolExecutor for background synthesis
  - Edge-TTS high-fidelity neural voices with SAPI5 local fallback
  - Instant barge-in interruption stopping audio mixer and clearing pending chunks
"""

import os
import re
import time
import queue
import logging
import asyncio
import threading
import concurrent.futures
from pathlib import Path
from backend.core.config import settings

logger = logging.getLogger("ace.voice.service")

try:
    import edge_tts
    import pygame
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logger.warning("edge_tts or pygame not available, using SAPI5 fallback.")

ACE_VOICE = getattr(settings, "EDGE_TTS_VOICE", "en-US-GuyNeural")
PITCH = "+0Hz"
RATE = "+15%"

executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _generate_edge_tts_file(text: str, voice: str, pitch: str, rate: str, output_path: str):
    """Run edge_tts async Communicate in an isolated worker thread event loop."""
    async def _save():
        communicate = edge_tts.Communicate(text, voice, pitch=pitch, rate=rate)
        await communicate.save(output_path)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_save())
    finally:
        loop.close()


class TTSEngine:
    """Production Text-To-Speech engine supporting sentence-streaming synthesis,
    background playback queuing, SAPI5 fallback, and instant barge-in interruption.
    """

    def __init__(self):
        self.rate = settings.VOICE_RATE
        self.volume = settings.VOICE_VOLUME
        self._lock = threading.Lock()
        self._interrupted = False
        self._is_speaking = False
        self._stream_queue = queue.Queue()
        self._playback_thread = None
        self.audio_dir = Path(__file__).resolve().parent.parent.parent / "data" / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        if EDGE_TTS_AVAILABLE:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
            except Exception as e:
                logger.warning(f"Pygame mixer init error: {e}")

    def stop(self):
        """Barge-in interrupt: instantly cancel active speech and pending audio chunks."""
        self._interrupted = True
        self._is_speaking = False

        # Drain and clean up streaming audio queue
        while not self._stream_queue.empty():
            try:
                item = self._stream_queue.get_nowait()
                if item:
                    _, audio_path = item
                    if audio_path and isinstance(audio_path, Path) and audio_path.exists():
                        try:
                            audio_path.unlink()
                        except Exception:
                            pass
                self._stream_queue.task_done()
            except Exception:
                break

        try:
            if EDGE_TTS_AVAILABLE and pygame.mixer.get_init():
                pygame.mixer.music.stop()
                try:
                    pygame.mixer.music.unload()
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Error stopping audio mixer: {e}")

    def is_speaking(self) -> bool:
        return self._is_speaking or not self._stream_queue.empty()

    def start_streaming(self):
        """Prepare TTS engine for sentence-streaming chunked synthesis."""
        self._interrupted = False
        self._is_speaking = True

        # Clear any residual queue items
        while not self._stream_queue.empty():
            try:
                item = self._stream_queue.get_nowait()
                if item:
                    _, audio_path = item
                    if audio_path and isinstance(audio_path, Path) and audio_path.exists():
                        try:
                            audio_path.unlink()
                        except Exception:
                            pass
                self._stream_queue.task_done()
            except Exception:
                break

        # Start playback worker thread if not running
        if self._playback_thread is None or not self._playback_thread.is_alive():
            self._playback_thread = threading.Thread(target=self._stream_playback_loop, daemon=True)
            self._playback_thread.start()

    def speak_stream_chunk(self, chunk_text: str):
        """Queue a sentence chunk for immediate synthesis and subsequent streaming playback."""
        clean = self.clean_text_for_speech(chunk_text)
        if not clean or self._interrupted:
            return

        chunk_id = int(time.time() * 1000)
        audio_path = self.audio_dir / f"stream_{chunk_id}_{abs(hash(clean)) % 10000}.mp3"

        if EDGE_TTS_AVAILABLE:
            def _synth():
                if self._interrupted:
                    return False
                try:
                    _generate_edge_tts_file(clean, ACE_VOICE, PITCH, RATE, str(audio_path))
                    return True
                except Exception as e:
                    logger.error(f"Stream TTS chunk synthesis error: {e}")
                    return False

            future = executor.submit(_synth)
            self._stream_queue.put((future, audio_path))
        else:
            def _sapi_task():
                if not self._interrupted:
                    self._speak_sapi5_chunk(clean)
                return True
            future = executor.submit(_sapi_task)
            self._stream_queue.put((future, None))

    def flush_streaming(self):
        """Signal that all sentence chunks for the current stream have been enqueued."""
        self._stream_queue.put(None)

    def _stream_playback_loop(self):
        """Background worker executing continuous, gapless playback of queued sentence chunks."""
        while not self._interrupted:
            try:
                item = self._stream_queue.get(timeout=0.2)
            except queue.Empty:
                if not self._is_speaking:
                    break
                continue

            if item is None:
                self._stream_queue.task_done()
                break

            future, audio_path = item
            try:
                if self._interrupted:
                    self._cleanup_temp_file(audio_path)
                    continue

                spoken = False
                try:
                    spoken = future.result(timeout=15)
                except Exception as e:
                    logger.error(f"Stream TTS synthesis future failed: {e}")

                if self._interrupted:
                    self._cleanup_temp_file(audio_path)
                    continue

                if spoken and audio_path and isinstance(audio_path, Path) and audio_path.exists() and audio_path.stat().st_size > 0:
                    if not pygame.mixer.get_init():
                        pygame.mixer.init()

                    pygame.mixer.music.load(str(audio_path))
                    pygame.mixer.music.play()

                    while pygame.mixer.music.get_busy():
                        if self._interrupted:
                            pygame.mixer.music.stop()
                            break
                        time.sleep(0.02)

                    try:
                        pygame.mixer.music.unload()
                    except Exception:
                        pass
                    self._cleanup_temp_file(audio_path)
            except Exception as e:
                logger.error(f"Stream TTS playback error: {e}")
                self._cleanup_temp_file(audio_path)
            finally:
                self._stream_queue.task_done()

        self._is_speaking = False

    def _cleanup_temp_file(self, path):
        if path and isinstance(path, Path) and path.exists():
            try:
                path.unlink()
            except Exception:
                pass

    def clean_text_for_speech(self, text: str) -> str:
        """Clean markdown formatting, code blocks, emojis, and newlines for fluent continuous speech."""
        if not text:
            return ""
        clean = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        clean = re.sub(r"`.*?`", "", clean)
        clean = re.sub(r"https?://\S+", "", clean)
        clean = re.sub(r"[*_#~>|\-]", "", clean)
        clean = re.sub(r"\n+", ". ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def split_into_paragraphs(self, text: str) -> list[str]:
        """Return full text as a single smooth continuous block for fluent speech without gaps."""
        clean = self.clean_text_for_speech(text)
        if not clean:
            return []

        if len(clean) <= 1500:
            return [clean]

        sentences = re.split(r'(?<=[.!?])\s+', clean)
        chunks = []
        curr = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(curr) + len(s) < 1200:
                curr = f"{curr} {s}".strip()
            else:
                if curr:
                    chunks.append(curr)
                curr = s
        if curr:
            chunks.append(curr)

        return chunks if chunks else [clean]

    def speak(self, text: str, block: bool = True) -> float:
        """Speak response in natural voice with instant interruption support."""
        if not text or not text.strip():
            return 0.0

        self._interrupted = False
        chunks = self.split_into_paragraphs(text)
        if not chunks:
            return 0.0

        total_duration = 0.0

        def _speak_pipeline():
            nonlocal total_duration
            self._is_speaking = True
            try:
                with self._lock:
                    for idx, chunk in enumerate(chunks):
                        if self._interrupted:
                            break
                        spoken, duration = False, 0.0
                        if EDGE_TTS_AVAILABLE:
                            spoken, duration = self._speak_edge_tts_chunk(chunk, idx)
                        if not spoken and not self._interrupted:
                            duration = self._speak_sapi5_chunk(chunk)
                        total_duration += duration
            finally:
                self._is_speaking = False

        if block:
            _speak_pipeline()
        else:
            t = threading.Thread(target=_speak_pipeline, daemon=True)
            t.start()

        return total_duration

    def _speak_edge_tts_chunk(self, chunk_text: str, chunk_id: int) -> tuple[bool, float]:
        """Synthesize and play audio chunk with real-time barge-in monitoring."""
        if self._interrupted:
            return False, 0.0

        audio_path = self.audio_dir / f"speech_{chunk_id}_{int(time.time()*1000)}.mp3"
        duration = 0.0
        try:
            future = executor.submit(
                _generate_edge_tts_file,
                chunk_text, ACE_VOICE, PITCH, RATE, str(audio_path)
            )
            future.result(timeout=15)

            if self._interrupted:
                if audio_path.exists():
                    try:
                        audio_path.unlink()
                    except Exception:
                        pass
                return False, 0.0

            if audio_path.exists() and audio_path.stat().st_size > 0:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()

                sound = pygame.mixer.Sound(str(audio_path))
                duration = sound.get_length()

                pygame.mixer.music.load(str(audio_path))
                pygame.mixer.music.play()

                while pygame.mixer.music.get_busy():
                    if self._interrupted:
                        pygame.mixer.music.stop()
                        break
                    time.sleep(0.02)

                try:
                    pygame.mixer.music.unload()
                except Exception:
                    pass

                try:
                    audio_path.unlink()
                except Exception:
                    pass
                return True, duration
        except Exception as e:
            logger.error(f"Edge-TTS error for text '{chunk_text[:30]}...': {e}")
            if audio_path.exists():
                try:
                    audio_path.unlink()
                except Exception:
                    pass
        return False, 0.0

    def _speak_sapi5_chunk(self, text: str) -> float:
        """SAPI5 fallback speaker."""
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Rate = max(-10, min(10, int((self.rate - 150) / 10)))
            speaker.Volume = int(self.volume * 100)
            speaker.Speak(text)
            return len(text) * 0.06
        except Exception as e:
            logger.error(f"SAPI5 speak error: {e}")
            return 0.0


tts_engine = TTSEngine()
