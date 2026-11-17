import os
import pytest
import asyncio
from unittest.mock import MagicMock, patch
from pathlib import Path

from voice_assistant.config import settings as va_settings
from voice_assistant.tts.stream_buffer import LinguisticStreamBuffer
from backend.speech.tts_engine import TTSEngine
from backend.agent.chat_service import ChatService


def test_vad_optimized_configuration():
    """Verify VAD parameters in voice_assistant are tuned for ultra-low turn-taking latency."""
    # MIN_SILENCE_DURATION reduced from 0.6s to 0.35s to eliminate user turn-taking dead air
    assert va_settings.MIN_SILENCE_DURATION == 0.35
    assert va_settings.MIN_SPEECH_DURATION == 0.20
    assert "postgresql://" in va_settings.DATABASE_URL


def test_linguistic_stream_buffer_early_boundary():
    """Verify LinguisticStreamBuffer emits early on first chunk (3 words) for low Time-To-First-Audio (TTFA)."""
    buf = LinguisticStreamBuffer(min_words_per_chunk=5, first_chunk_min_words=3)
    
    # First chunk with 3 words ending with exclamation mark
    chunks = buf.append("Hello there friend! ")
    assert len(chunks) == 1
    assert chunks[0][0] == "Hello there friend!"

    # Abbreviation protection: Dr. should not split
    buf.reset()
    chunks = buf.append("Hello Dr. Smith who is ")
    assert len(chunks) == 0  # Should not split at Dr.
    
    chunks = buf.append("arriving today. ")
    assert len(chunks) == 1
    assert "Dr. Smith" in chunks[0][0]

    # Decimal protection: 3.14 should not split
    buf.reset()
    chunks = buf.append("Pi is approx 3.14 and ")
    assert len(chunks) == 0  # Should not split at 3.14


def test_chat_service_find_sentence_boundary():
    """Verify sentence boundary detector in ChatService correctly handles sentences, decimals, and abbreviations."""
    # Standard period boundary
    text1 = "Hello there. How are you?"
    idx1 = ChatService._find_sentence_boundary(text1)
    assert idx1 == len("Hello there. ")
    assert text1[:idx1].strip() == "Hello there."

    # Decimal number should not be a boundary
    text2 = "The value is 3.14 radians."
    idx2 = ChatService._find_sentence_boundary(text2)
    assert idx2 == len(text2)
    assert text2[:idx2].strip() == "The value is 3.14 radians."

    # Common abbreviation should not trigger split
    text3 = "Call Mr. Watson right now."
    idx3 = ChatService._find_sentence_boundary(text3)
    assert idx3 == len(text3)

    # Exclamation mark
    text4 = "Look out! Incoming attack."
    idx4 = ChatService._find_sentence_boundary(text4)
    assert text4[:idx4].strip() == "Look out!"

    # Newline break
    text5 = "Line one here\nLine two follows"
    idx5 = ChatService._find_sentence_boundary(text5)
    assert idx5 == len("Line one here\n")


def test_tts_engine_streaming_lifecycle_and_barge_in():
    """Verify TTSEngine start_streaming, chunk queuing, and instant stop barge-in behavior."""
    engine = TTSEngine()
    engine.start_streaming()
    assert engine._is_speaking is True
    assert engine._interrupted is False

    # Enqueue chunks
    engine.speak_stream_chunk("This is the first streaming sentence.")
    engine.speak_stream_chunk("This is the second streaming sentence.")
    assert engine.is_speaking() is True

    # Test instant barge-in interruption
    engine.stop()
    assert engine._interrupted is True
    assert engine._stream_queue.empty() is True


@pytest.mark.anyio
async def test_chat_service_stream_sentence_tts_dispatch():
    """Verify stream_chat with speak=True dispatches sentence chunks to TTS while LLM is generating tokens."""
    service = ChatService()
    
    # Mock LLM stream returning two full sentences across incremental tokens
    async def mock_stream(*args, **kwargs):
        tokens = ["First ", "sentence ", "is ", "here! ", "Second ", "sentence ", "is ", "done."]
        for t in tokens:
            yield t
            await asyncio.sleep(0.01)

    service.llm.chat_stream = MagicMock(side_effect=mock_stream)
    
    # Mock TTS streaming methods
    dispatched_chunks = []
    service.tts.start_streaming = MagicMock()
    service.tts.speak_stream_chunk = MagicMock(side_effect=lambda chunk: dispatched_chunks.append(chunk))
    service.tts.flush_streaming = MagicMock()
    service.tts.speak = MagicMock()
    service.cache.get = MagicMock(return_value=None)

    events = []
    async for ev in service.stream_chat(
        message="Tell me two sentences",
        session_id="test_stream_voice_session",
        speak=True
    ):
        events.append(ev)

    # Assert start_streaming was called
    service.tts.start_streaming.assert_called_once()
    
    # Assert sentence chunks were dispatched as they occurred
    assert len(dispatched_chunks) >= 2
    assert "First sentence is here!" in dispatched_chunks[0]
    assert "Second sentence is done." in dispatched_chunks[1]
    
    # Assert flush_streaming was called upon finish
    service.tts.flush_streaming.assert_called_once()
    
    # Assert non-streaming speak was NOT called since streaming TTS handled it
    service.tts.speak.assert_not_called()

    # Verify done event indicates speaking state
    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1
    assert done_events[0]["state"] == "speaking"
