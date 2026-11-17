"""
Memories Repository Layer
=========================
Encapsulates all database persistence, retrieval, updating, and deletion operations
for the long-term memory domain.
Provides clean query isolation from business logic, ensuring audit timestamps and
soft-deletion statuses are consistently enforced.
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.core.database import SessionLocal
from backend.memories.models import MemoryModel

logger = logging.getLogger("ace.memories.repository")


class MemoryRepository:
    """
    Database repository managing CRUD for MemoryModel entities.
    """

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize repository with optional external session (e.g. for testing transactions).
        """
        self._external_db = db

    def _get_session(self) -> Session:
        """Helper to obtain active database session."""
        return self._external_db if self._external_db is not None else SessionLocal()

    def add_or_update_memory(
        self,
        key: str,
        value: str,
        category: str = "general"
    ) -> MemoryModel:
        """
        Upserts a memory record by key, automatically maintaining audit timestamps.

        Args:
            key (str): Unique memory identifier.
            value (str): Content/fact to remember.
            category (str): Optional grouping tag (default: 'general').

        Returns:
            MemoryModel: Persisted and refreshed database record.
        """
        db = self._get_session()
        try:
            existing = db.query(MemoryModel).filter(MemoryModel.key == key).first()
            if existing:
                existing.value = value
                existing.category = category
                existing.is_active = True
                db.commit()
                db.refresh(existing)
                logger.info(f"MemoryRepository: Updated memory '{key}'")
                return existing
            else:
                record = MemoryModel(category=category, key=key, value=value)
                db.add(record)
                db.commit()
                db.refresh(record)
                logger.info(f"MemoryRepository: Created memory '{key}'")
                return record
        finally:
            if self._external_db is None:
                db.close()

    def get_memory_by_key(self, key: str) -> Optional[MemoryModel]:
        """
        Fetch a single memory by its unique key.

        Args:
            key (str): Unique key to look up.

        Returns:
            Optional[MemoryModel]: Matching record if found and active, else None.
        """
        db = self._get_session()
        try:
            return db.query(MemoryModel).filter(
                MemoryModel.key == key,
                MemoryModel.is_active == True
            ).first()
        finally:
            if self._external_db is None:
                db.close()

    def get_all_memories(self, category: Optional[str] = None) -> List[MemoryModel]:
        """
        Fetch all active memories, optionally filtered by category.

        Args:
            category (Optional[str]): Optional category filter.

        Returns:
            List[MemoryModel]: Chronologically ordered memories (newest first).
        """
        db = self._get_session()
        try:
            query = db.query(MemoryModel).filter(MemoryModel.is_active == True)
            if category:
                query = query.filter(MemoryModel.category == category)
            return query.order_by(MemoryModel.created_at.desc()).all()
        finally:
            if self._external_db is None:
                db.close()

    def get_long_term_memories(self) -> List[str]:
        """
        Return formatted string list of memories for LLM prompt context injection.

        Returns:
            List[str]: Formatted list of strings in 'key: value' format.
        """
        db = self._get_session()
        try:
            records = db.query(MemoryModel).filter(MemoryModel.is_active == True).all()
            return [f"{m.key}: {m.value}" for m in records]
        finally:
            if self._external_db is None:
                db.close()

    def get_all_memories_detailed(self) -> List[Dict[str, Any]]:
        """
        Return detailed memory records with formatted ISO audit timestamps.

        Returns:
            List[Dict[str, Any]]: Serialized records with audit metadata.
        """
        db = self._get_session()
        try:
            records = (
                db.query(MemoryModel)
                .filter(MemoryModel.is_active == True)
                .order_by(MemoryModel.created_at.desc())
                .all()
            )
            return [
                {
                    "id": m.id,
                    "category": m.category,
                    "key": m.key,
                    "value": m.value,
                    "created_at": m.created_at.isoformat() if m.created_at else "",
                    "updated_at": m.updated_at.isoformat() if m.updated_at else ""
                }
                for m in records
            ]
        finally:
            if self._external_db is None:
                db.close()

    def delete_memory(self, key: str) -> bool:
        """
        Permanently delete a memory record by key.

        Args:
            key (str): Unique memory key to remove.

        Returns:
            bool: True if record was found and deleted, False otherwise.
        """
        db = self._get_session()
        try:
            deleted = db.query(MemoryModel).filter(MemoryModel.key == key).delete()
            db.commit()
            return deleted > 0
        finally:
            if self._external_db is None:
                db.close()


# Global repository singleton instance
memory_repository = MemoryRepository()
