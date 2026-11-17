"""
Cache Domain Repository.

Handles database persistence and retrieval for normalized and exact prompt query cache entries.
Integrates with BaseAuditModel tracking for cache entry lifecycles and hit counters.
"""

import logging
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.core.database import SessionLocal, engine
from backend.cache.models import QueryCacheModel

logger = logging.getLogger("ace.cache.repository")


class CacheRepository:
    """Encapsulates all database operations for exact, normalized, and semantic prompt caching."""

    def __init__(self, db: Optional[Session] = None):
        self._external_db = db

    def _get_session(self) -> Session:
        """Helper to obtain active session or create a new session if none provided."""
        return self._external_db if self._external_db is not None else SessionLocal()

    def get_by_normalized_prompt(self, prompt_norm: str) -> Optional[QueryCacheModel]:
        """
        Fetch cached response by exact normalized prompt match.

        Only retrieves active (is_active=True) entries.
        """
        db = self._get_session()
        try:
            return db.query(QueryCacheModel).filter(
                QueryCacheModel.prompt_normalized == prompt_norm,
                QueryCacheModel.is_active == True
            ).first()
        finally:
            if self._external_db is None:
                db.close()

    def save_cache_entry(
        self,
        prompt_norm: str,
        response: str,
        tool_executed: Optional[str] = None,
        embedding: Optional[List[float]] = None
    ) -> QueryCacheModel:
        """
        Upsert a prompt-response cache entry.

        If an entry with this normalized prompt exists, updates the response,
        embedding, hit count, and ensures is_active is set to True.
        Otherwise, inserts a new QueryCacheModel entry.
        """
        db = self._get_session()
        try:
            existing = db.query(QueryCacheModel).filter(
                QueryCacheModel.prompt_normalized == prompt_norm
            ).first()

            if existing:
                existing.response = response
                existing.tool_executed = tool_executed
                if embedding:
                    existing.embedding = embedding
                existing.hit_count += 1
                existing.is_active = True
                db.commit()
                db.refresh(existing)
                return existing
            else:
                entry = QueryCacheModel(
                    prompt_normalized=prompt_norm,
                    response=response,
                    tool_executed=tool_executed,
                    embedding=embedding
                )
                db.add(entry)
                db.commit()
                db.refresh(entry)
                return entry
        finally:
            if self._external_db is None:
                db.close()

    def increment_hit_count(self, entry_id: int):
        """Atomically increment the cache hit count for a specific entry."""
        db = self._get_session()
        try:
            db.query(QueryCacheModel).filter(QueryCacheModel.id == entry_id).update(
                {QueryCacheModel.hit_count: QueryCacheModel.hit_count + 1}
            )
            db.commit()
        finally:
            if self._external_db is None:
                db.close()

    def clear(self):
        """Purge all persistent cache entries from the database."""
        db = self._get_session()
        try:
            db.query(QueryCacheModel).delete()
            db.commit()
        finally:
            if self._external_db is None:
                db.close()


# Singleton repository instance for application use
cache_repository = CacheRepository()
