from typing import Optional
from pydantic import BaseModel, Field


class VoiceSpeakRequest(BaseModel):
    """Payload to trigger speech synthesis for text."""
    text: str = Field(..., min_length=1, description="Text to synthesize to speech")
    block: Optional[bool] = Field(default=False, description="Whether to block execution until playback finishes")


class VoiceStatusResponse(BaseModel):
    """Current audio output state."""
    is_speaking: bool


class VoiceListenResponse(BaseModel):
    """STT voice listening turn result."""
    transcript: str
    response: str
    has_speech: bool
    tool_executed: Optional[str] = None
    state: str = "idle"
