"""
Conversations Domain Model
==========================
Defines ConversationModel representing user and assistant chat dialogue turns.
Equipped with BaseAuditModel (id, created_at, updated_at, is_active) and composite index
(ix_conv_session_id) for rapid historical turn queries and dynamic token-window budgeting.
"""

from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, Index
from backend.common.models import BaseAuditModel


class ConversationModel(BaseAuditModel):
    """
    Stores individual conversation dialogue turns.

    Attributes:
        session_id: Multi-session grouping identifier (default: 'default')
        role: Dialogue participant ('user', 'assistant', or 'system')
        content: Message text payload
        metadata_json: Optional JSON string storing turn metadata (tokens, tools, latency)
    """
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conv_session_id", "session_id", "id"),
    )

    session_id = Column(String(64), index=True, default="default", doc="Session grouping identifier")
    role = Column(String(20), nullable=False, default="user", doc="Turn sender ('user', 'assistant', 'system')")
    content = Column(Text, nullable=False, doc="Raw message content")
    metadata_json = Column(Text, default="{}", doc="Turn execution metadata serialized as JSON")

    def __init__(self, *args, **kwargs):
        # Backward compatibility for code passing legacy 'sender' and 'message' keyword arguments
        if "sender" in kwargs and "role" not in kwargs:
            kwargs["role"] = kwargs.pop("sender")
        if "message" in kwargs and "content" not in kwargs:
            kwargs["content"] = kwargs.pop("message")
        super().__init__(*args, **kwargs)

    @property
    def sender(self) -> str:
        """Alias for role, supporting legacy callers."""
        return self.role

    @sender.setter
    def sender(self, val: str):
        self.role = val

    @property
    def message(self) -> str:
        """Alias for content, supporting legacy callers."""
        return self.content

    @message.setter
    def message(self, val: str):
        self.content = val

    @property
    def timestamp(self) -> datetime:
        """Alias for created_at, supporting legacy callers."""
        return self.created_at


class ConversationStateModel(BaseAuditModel):
    """
    Stores the active context state of a conversation session.

    Attributes:
        session_id: Multi-session grouping identifier (unique)
        current_topic: Active conversation topic (e.g. 'apple', 'python')
        current_entity: Active primary entity (e.g. 'fruit', 'technology_company')
        current_entity_type: Category of current entity (e.g. 'concept', 'food', 'company')
        current_context: Summary or detail of active contextual state
        last_turn_id: ID of the most recent conversation turn
        last_user_message: Text of the latest user query
        last_assistant_message: Text of the latest assistant reply
        active_correction: Boolean flag indicating an ongoing or recent correction
    """
    __tablename__ = "conversation_states"

    session_id = Column(String(64), unique=True, index=True, nullable=False, doc="Session identifier")
    current_topic = Column(String(100), nullable=True, index=True, doc="Current conversational topic")
    current_entity = Column(String(100), nullable=True, index=True, doc="Current primary entity")
    current_entity_type = Column(String(50), nullable=True, doc="Entity category")
    current_context = Column(Text, nullable=True, doc="Active context description")
    last_turn_id = Column(Integer, nullable=True, doc="Last conversation turn ID")
    last_user_message = Column(Text, nullable=True, doc="Most recent user message")
    last_assistant_message = Column(Text, nullable=True, doc="Most recent assistant message")
    active_correction = Column(Text, nullable=True, doc="Active correction detail if any")

