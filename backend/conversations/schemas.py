from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from backend.common.schemas import BaseAuditSchema


class ChatRequest(BaseModel):
    """Incoming user chat message payload."""
    message: str = Field(..., min_length=1, description="Text prompt from user")
    speak: Optional[bool] = Field(default=True, description="Enable voice speech synthesis")
    session_id: Optional[str] = Field(default="default", max_length=64, description="Conversation session identifier")


class ChatResponse(BaseModel):
    """Outgoing assistant reply payload."""
    user_message: str
    response: str
    tool_executed: Optional[str] = None
    state: str = "idle"
    cached: Optional[bool] = False


class ConversationMessageSchema(BaseAuditSchema):
    """Audit schema representation of a stored conversation turn."""
    session_id: str
    role: str
    content: str
    metadata_json: Optional[str] = "{}"


class StreamEventSchema(BaseModel):
    """SSE streaming response event."""
    type: str  # 'start', 'token', 'tool_start', 'tool_result', 'done', 'error'
    content: Optional[str] = None
    user_message: Optional[str] = None
    response: Optional[str] = None
    tool: Optional[str] = None
    tool_executed: Optional[str] = None
    result_prefix: Optional[str] = None
    state: Optional[str] = None
    cached: Optional[bool] = False
    error: Optional[str] = None
