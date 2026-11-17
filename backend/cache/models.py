"""
Cache Domain Model
==================
Defines QueryCacheModel representing persisted prompt responses.
Equipped with BaseAuditModel (id, created_at, updated_at, is_active) for tracking
cache lifetime, eviction candidates, hit counts, and vector embeddings for semantic search.
"""

from sqlalchemy import Column, String, Text, Integer, ARRAY, Float
from backend.common.models import BaseAuditModel


class QueryCacheModel(BaseAuditModel):
    """
    Persistent response cache entry.

    Attributes:
        prompt_normalized: Canonical lowercase stripped prompt string (unique index)
        response: Cached response text
        tool_executed: Optional representation of deterministic tool call
        embedding: Float array storing dense vector embedding for semantic search
        hit_count: Frequency counter tracking cache hits
    """
    __tablename__ = "query_cache"

    prompt_normalized = Column(String(500), index=True, nullable=False, doc="Normalized unique prompt")
    cache_key = Column(String(255), unique=True, index=True, nullable=True, doc="Composite context-aware unique key")
    context_key = Column(String(100), index=True, default="general", nullable=False, doc="Context discriminator key")
    topic = Column(String(100), nullable=True, index=True, doc="Associated topic")
    entity = Column(String(100), nullable=True, index=True, doc="Associated entity")
    status = Column(String(20), default="ACTIVE", index=True, nullable=False, doc="Cache entry status (ACTIVE, STALE, INVALIDATED)")
    version = Column(Integer, default=1, nullable=False, doc="Cache version counter")
    response = Column(Text, nullable=False, doc="Cached response text")
    tool_executed = Column(String(200), nullable=True, doc="Executed tool invocation string")
    embedding = Column(ARRAY(Float), nullable=True, doc="Dense semantic vector embedding")
    hit_count = Column(Integer, default=1, doc="Total cache hits counter")

