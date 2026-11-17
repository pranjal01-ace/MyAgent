"""Legacy facade module for backward compatibility.
Re-exports database engine, sessionmaker, and models from new modular domain packages.
"""
import logging
from sqlalchemy import Column, String, Text, Float, ARRAY, Index
from backend.common.models import Base, BaseAuditModel
from backend.conversations.models import ConversationModel, ConversationStateModel
from backend.memories.models import MemoryModel
from backend.cache.models import QueryCacheModel
from backend.core.database import (
    engine,
    SessionLocal,
    create_db_engine,
    init_db,
    get_db,
    COSINE_SIMILARITY_SQL,
    VECTOR_DOT_PRODUCT_SQL
)

logger = logging.getLogger("ace.database")


class KnowledgeVectorModel(BaseAuditModel):
    """Native Vector Store inside PostgreSQL for document chunks and embeddings with audit timestamps."""
    __tablename__ = "knowledge_vectors"
    __table_args__ = (
        Index("ix_vectors_coll_id", "collection_name", "id"),
    )

    collection_name = Column(String(100), default="knowledge", index=True)
    text = Column(Text, nullable=False)
    metadata_json = Column(Text, default="{}")
    embedding = Column(ARRAY(Float), nullable=False)


__all__ = [
    "Base",
    "BaseAuditModel",
    "ConversationModel",
    "ConversationStateModel",
    "MemoryModel",
    "QueryCacheModel",
    "KnowledgeVectorModel",
    "engine",
    "SessionLocal",
    "create_db_engine",
    "init_db",
    "get_db",
    "COSINE_SIMILARITY_SQL",
    "VECTOR_DOT_PRODUCT_SQL",
]
