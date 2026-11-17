import os
import re
import time
import queue
import logging
import asyncio
import threading
import concurrent.futures
from pathlib import Path
from typing import AsyncGenerator, Optional

from voice_assistant.config import settings
from voice_assistant.tts.base import TTSProvider
from voice_assistant.tts.stream_buffer import LinguisticStreamBuffer

logger = logging.getLogger("assistant.tts")

try:
    import edge_tts
    import pygame
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logger.warning("edge_tts or pygame unavailable; using SAPI5 fallback.")

executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)

def _generate_edge_tts_contextual(text: str, voice: str, rate_str: str, output_path: str):
    """Synthesize text chunk with edge-tts."""
    async def _save():
        communicate = edge_tts.Communicate(text, voice, rate=rate_str)
        await communicate.save(output_path)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_save())
    finally:
        loop.close()

class LocalTTSProvider(TTSProvider):
    """Context-aware stateful streaming TTS provider maintaining prosody continuity and instant barge-in."""

    def __init__(self):
        self.voice = settings.TTS_VOICE
        self.speed = settings.TTS_SPEED
        self.rate_str = f"+{int((self.speed - 1.0) * 100)}%" if self.speed >= 1.0 else f"{int((self.speed - 1.0) * 100)}%"
        
        self.audio_dir = Path(__file__).resolve().parent.parent / "data" / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        self._stop_event = threading.Event()
        self._is_speaking = False
        self._lock = threading.Lock()
        
        self.audio_queue = queue.Queue()
        self.playback_thread = None

        if EDGE_TTS_AVAILABLE:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
            except Exception as e:
                logger.warning(f"Pygame mixer init error: {e}")

    def clean_text(self, text: str) -> str:
        if not text:
            return ""
        clean = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        clean = re.sub(r"`.*?`", "", clean)
        clean = re.sub(r"https?://\S+", "", clean)
        clean = re.sub(r"[*_#~>|\-]", "", clean)
        clean = re.sub(r"\n+", ". ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def is_speaking(self) -> bool:
        with self._lock:
            return self._is_speaking or not self.audio_queue.empty()

    async def speak(self, text: str):
        """Synthesize and play given text continuously."""
        cleaned = self.clean_text(text)
        if not cleaned:
            return

        self._stop_event.clear()
        with self._lock:
            self._is_speaking = True

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._speak_sync, cleaned)

        with self._lock:
            self._is_speaking = False

    async def speak_stream(self, token_generator: AsyncGenerator[str, None], cancel_event: Optional[asyncio.Event] = None):
        """Stream tokens from LLM into a context-aware linguistic buffer and play continuous audio seamlessly."""
        self._stop_event.clear()
        with self._lock:
            self._is_speaking = True

        buffer = LinguisticStreamBuffer(min_words_per_chunk=6, max_context_words=12)
        
        # Start background queue player
        self._start_playback_worker()

        try:
            async for token in token_generator:
                if (cancel_event and cancel_event.is_set()) or self._stop_event.is_set():
                    break

                chunks = buffer.append(token)
                for chunk_text, context_prefix in chunks:
                    if (cancel_event and cancel_event.is_set()) or self._stop_event.is_set():
                        break
                    self._enqueue_chunk_synthesis(chunk_text, context_prefix)

            # Flush remaining buffer upon stream completion
            if not self._stop_event.is_set() and not (cancel_event and cancel_event.is_set()):
                final_chunks = buffer.flush()
                for chunk_text, context_prefix in final_chunks:
                    self._enqueue_chunk_synthesis(chunk_text, context_prefix)

            # Wait for playback queue to drain
            while not self.audio_queue.empty() and not self._stop_event.is_set():
                if cancel_event and cancel_event.is_set():
                    break
                await asyncio.sleep(0.05)

        finally:
            with self._lock:
                self._is_speaking = False

    def _enqueue_chunk_synthesis(self, chunk_text: str, context_prefix: str):
        cleaned = self.clean_text(chunk_text)
        if not cleaned:
            return

        audio_path = self.audio_dir / f"stream_{int(time.time()*1000)}_{hash(cleaned) & 0xffff}.mp3"
        
        # Submit synthesis to executor
        future = executor.submit(
            _generate_edge_tts_contextual, cleaned, self.voice, self.rate_str, str(audio_path)
        )
        self.audio_queue.put((future, audio_path))

    def _start_playback_worker(self):
        if self.playback_thread and self.playback_thread.is_alive():
            return

        self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.playback_thread.start()

    def _playback_loop(self):
        """Worker thread executing gapless audio playback from queue."""
        while not self._stop_event.is_set():
            try:
                item = self.audio_queue.get(timeout=0.2)
            except queue.Empty:
                if not self._is_speaking:
                    break
                continue

            future, audio_path = item

            try:
                future.result(timeout=10)
                if self._stop_event.is_set():
                    self._cleanup_audio_file(audio_path)
                    break

                if audio_path.exists() and audio_path.stat().st_size > 0:
                    if not pygame.mixer.get_init():
                        pygame.mixer.init()

                    pygame.mixer.music.load(str(audio_path))
                    pygame.mixer.music.play()

                    while pygame.mixer.music.get_busy():
                        if self._stop_event.is_set():
                            pygame.mixer.music.stop()
                            break
                        time.sleep(0.01)

                    try:
                        pygame.mixer.music.unload()
                    except Exception:
                        pass
                    self._cleanup_audio_file(audio_path)

            except Exception as e:
                logger.error(f"Error playing streaming audio chunk: {e}")
                self._cleanup_audio_file(audio_path)
            finally:
                self.audio_queue.task_done()

    def _cleanup_audio_file(self, path: Path):
        if path and path.exists():
            try:
                path.unlink()
            except Exception:
                pass

    def _speak_sync(self, text: str):
        if self._stop_event.is_set():
            return

        audio_path = self.audio_dir / f"speech_{int(time.time()*1000)}.mp3"
        try:
            future = executor.submit(
                _generate_edge_tts_contextual, text, self.voice, self.rate_str, str(audio_path)
            )
            future.result(timeout=15)

            if self._stop_event.is_set():
                self._cleanup_audio_file(audio_path)
                return

            if audio_path.exists() and audio_path.stat().st_size > 0:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()

                pygame.mixer.music.load(str(audio_path))
                pygame.mixer.music.play()

                while pygame.mixer.music.get_busy():
                    if self._stop_event.is_set():
                        pygame.mixer.music.stop()
                        break
                    time.sleep(0.01)

                try:
                    pygame.mixer.music.unload()
                except Exception:
                    pass
                self._cleanup_audio_file(audio_path)
        except Exception as e:
            if not self._stop_event.is_set():
                logger.error(f"Local TTS error ({text[:30]}...): {e}")

    def stop_sync(self):
        """Synchronously stop speech playback, flush queue, and cancel ongoing TTS."""
        logger.info("TTS Provider stop_sync() invoked! Triggering immediate barge-in cancellation.")
        self._stop_event.set()

        # Clear pending queue
        while not self.audio_queue.empty():
            try:
                _, audio_path = self.audio_queue.get_nowait()
                self._cleanup_audio_file(audio_path)
            except Exception:
                pass

        if EDGE_TTS_AVAILABLE and pygame.mixer.get_init():
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            except Exception:
                pass

        with self._lock:
            self._is_speaking = False

    async def stop(self):
        """Async wrapper for stop_sync."""
        self.stop_sync()
