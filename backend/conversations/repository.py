import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from backend.core.database import SessionLocal
from backend.conversations.models import ConversationModel

logger = logging.getLogger("ace.conversations.repository")


class ConversationRepository:
    """Encapsulates all database persistence and retrieval operations for conversations."""

    def __init__(self, db: Optional[Session] = None):
        self._external_db = db

    def _get_session(self) -> Session:
        return self._external_db if self._external_db is not None else SessionLocal()

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Fast, safe token estimation (~3.8 characters per token on average)."""
        if not text:
            return 0
        return max(1, len(text) // 4 + 1)

    def add_message(
        self,
        role: str,
        content: str,
        session_id: str = "default",
        metadata_json: str = "{}"
    ) -> ConversationModel:
        """Persist a conversation turn to the database with audit timestamps."""
        db = self._get_session()
        try:
            record = ConversationModel(
                session_id=session_id,
                role=role,
                content=content,
                metadata_json=metadata_json
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record
        finally:
            if self._external_db is None:
                db.close()

    def get_recent_messages(
        self,
        session_id: str = "default",
        limit: int = 10
    ) -> List[Dict[str, str]]:
        """Retrieve the N most recent messages in chronological order."""
        db = self._get_session()
        try:
            records = (
                db.query(ConversationModel)
                .filter(ConversationModel.session_id == session_id, ConversationModel.is_active == True)
                .order_by(ConversationModel.id.desc())
                .limit(limit)
                .all()
            )
            records.reverse()
            return [{"role": r.role, "content": r.content} for r in records]
        finally:
            if self._external_db is None:
                db.close()

    def get_budgeted_messages(
        self,
        session_id: str = "default",
        max_tokens: int = 1200,
        max_count: int = 25
    ) -> List[Dict[str, str]]:
        """Retrieve most recent conversation turns strictly fitting within a token budget."""
        db = self._get_session()
        try:
            records = (
                db.query(ConversationModel)
                .filter(ConversationModel.session_id == session_id, ConversationModel.is_active == True)
                .order_by(ConversationModel.id.desc())
                .limit(max_count)
                .all()
            )

            budgeted = []
            total_tokens = 0
            for r in records:
                text_content = r.content or ""
                tok = self.estimate_tokens(text_content)
                if total_tokens + tok > max_tokens and budgeted:
                    break
                budgeted.append({"role": r.role, "content": text_content})
                total_tokens += tok

            budgeted.reverse()
            return budgeted
        finally:
            if self._external_db is None:
                db.close()

    def clear_conversation(self, session_id: str = "default") -> int:
        """Soft-delete or purge messages for a session."""
        db = self._get_session()
        try:
            deleted_count = (
                db.query(ConversationModel)
                .filter(ConversationModel.session_id == session_id)
                .delete()
            )
            db.commit()
            return deleted_count
        finally:
            if self._external_db is None:
                db.close()


conversation_repository = ConversationRepository()
