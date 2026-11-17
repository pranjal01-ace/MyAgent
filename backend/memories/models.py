"""
Memories Domain Model
=====================
Defines MemoryModel representing long-term user facts, preferences, and project context.
Inherits from BaseAuditModel (providing id, created_at, updated_at, is_active) with a composite
index (ix_memories_cat_key) for fast categorized retrieval and context injection into prompts.
"""

from sqlalchemy import Column, String, Text, Index
from backend.common.models import BaseAuditModel


class MemoryModel(BaseAuditModel):
    """
    Persistent memory record for long-term user context.

    Attributes:
        category: Logical grouping tag ('preferences', 'general', 'user_info', 'projects')
        key: Unique descriptor or variable name
        value: Fact or preference string content
    """
    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_cat_key", "category", "key"),
    )

    category = Column(String(50), default="general", index=True, doc="Logical memory categorization")
    key = Column(String(120), nullable=False, index=True, doc="Unique memory lookup key")
    value = Column(Text, nullable=False, doc="Memory factual text or preferences")
