"""
Voice Domain Router.

Provides HTTP REST endpoints for text-to-speech (TTS), speech-to-text (STT),
status polling, and instant barge-in interruption.
"""

import logging
from fastapi import APIRouter, HTTPException, status

from backend.voice.schemas import VoiceSpeakRequest, VoiceStatusResponse, VoiceListenResponse
from backend.voice.service import tts_engine

try:
    from backend.speech.stt_engine import stt_engine
except ImportError:
    stt_engine = None

from backend.conversations.repository import conversation_repository
from backend.agent.agent import agent_router
from backend.llm.ollama_client import ollama_client
from backend.memory.conversation import get_long_term_memories

logger = logging.getLogger("ace.voice.router")

router = APIRouter(prefix="/voice", tags=["voice"])


# ==============================================================================
# Speech Synthesis (TTS) Endpoints
# ==============================================================================

@router.post(
    "/speak",
    summary="Speak text response"
)
async def voice_speak_endpoint(req: VoiceSpeakRequest):
    """
    Synthesize text to speech using Edge-TTS or SAPI5 with instant barge-in support.

    Accepts text and an optional block flag (defaults to asynchronous non-blocking).
    """
    text = req.text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text cannot be empty."
        )

    duration = tts_engine.speak(text, block=req.block if req.block is not None else False)
    return {"status": "speaking", "duration": duration}


@router.post(
    "/stop",
    summary="Stop speech playback immediately (Barge-In)"
)
async def voice_stop_endpoint():
    """
    Barge-in endpoint: instantly cancels active speech playback and clears queued audio.

    Ensures zero delay when the user starts speaking or clicks interrupt.
    """
    tts_engine.stop()
    return {
        "status": "interrupted",
        "message": "Speech playback stopped instantly."
    }


@router.get(
    "/status",
    response_model=VoiceStatusResponse,
    summary="Check speech playback status"
)
async def voice_status_endpoint():
    """Check if speech audio is currently playing."""
    return VoiceStatusResponse(is_speaking=tts_engine.is_speaking())


# ==============================================================================
# Speech Recognition (STT) Endpoints
# ==============================================================================

@router.post(
    "/listen",
    summary="Listen to microphone and process voice turn"
)
async def voice_listen_endpoint():
    """
    Trigger microphone listening allowing natural mid-sentence pauses up to 30s.

    Transcribes user speech, checks for tool intent, queries Ollama,
    and speaks the response asynchronously.
    """
    if stt_engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="STT speech recognition engine not available."
        )

    text = stt_engine.listen_and_transcribe(timeout=5, phrase_time_limit=12)
    if not text:
        return {
            "transcript": "",
            "response": "",
            "has_speech": False,
            "tool_executed": None,
            "state": "idle"
        }

    # Store user message in repository
    conversation_repository.add_message(role="user", content=text)

    # Check for desktop tool execution intent
    tool_executed = None
    intent = agent_router.check_intent(text)
    tool_result_prefix = ""

    if intent:
        tool_name, tool_args = intent
        tool_result = agent_router.execute_tool(tool_name, tool_args)
        tool_executed = f"{tool_name}({tool_args})"
        tool_result_prefix = f"[Executed tool '{tool_name}': {tool_result}]\n"

    recent_messages = conversation_repository.get_recent_messages(limit=6)
    memories = get_long_term_memories()

    if tool_result_prefix:
        recent_messages.append({"role": "system", "content": tool_result_prefix})

    # Stream response from Ollama
    full_response = ""
    async for token in ollama_client.chat_stream(messages=recent_messages, memories=memories):
        full_response += token

    final_text = full_response.strip()

    # Play audio output if not interrupted
    if final_text and not getattr(tts_engine, "_interrupted", False):
        tts_engine.speak(final_text, block=False)

    # Store assistant response in repository
    conversation_repository.add_message(role="assistant", content=final_text)

    return {
        "transcript": text,
        "response": final_text,
        "has_speech": True,
        "tool_executed": tool_executed,
        "state": "idle"
    }
