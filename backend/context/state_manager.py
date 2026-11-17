"""
Conversation State Manager
==========================
Maintains, updates, and persists the active contextual state per dialogue session:
- In-memory LRU for 0.05ms real-time conversational lookups.
- PostgreSQL database persistence via ConversationStateModel for durable cross-restart context.
- Entity & pronoun resolution ('it', 'they', 'that', 'this').
- Active correction tracking and state transitions.
"""

import logging
from collections import OrderedDict
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from backend.core.database import SessionLocal
from backend.conversations.models import ConversationStateModel

logger = logging.getLogger("ace.context.state")


class ConversationStateManager:
    """
    Manages session-level conversational state and reference tracking.
    """

    def __init__(self, max_memory_sessions: int = 250):
        self.max_memory_sessions = max_memory_sessions
        self._memory_states: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    def get_state(self, session_id: str = "default") -> Dict[str, Any]:
        """
        Retrieve current state for a session.
        Checks in-memory cache first, then PostgreSQL.
        """
        if not session_id:
            session_id = "default"

        # 1. In-memory check
        if session_id in self._memory_states:
            self._memory_states.move_to_end(session_id)
            return dict(self._memory_states[session_id])

        # 2. Database check
        db: Session = SessionLocal()
        try:
            record = db.query(ConversationStateModel).filter(
                ConversationStateModel.session_id == session_id,
                ConversationStateModel.is_active == True
            ).first()

            if record:
                state_data = {
                    "session_id": record.session_id,
                    "current_topic": record.current_topic,
                    "current_entity": record.current_entity,
                    "current_entity_type": record.current_entity_type,
                    "current_context": record.current_context,
                    "last_turn_id": record.last_turn_id,
                    "last_user_message": record.last_user_message,
                    "last_assistant_message": record.last_assistant_message,
                    "active_correction": record.active_correction,
                }
                # Cache in memory
                if len(self._memory_states) >= self.max_memory_sessions:
                    self._memory_states.popitem(last=False)
                self._memory_states[session_id] = state_data
                return state_data
        except Exception as e:
            logger.warning(f"Error reading conversation state from DB for {session_id}: {e}")
        finally:
            db.close()

        # Default empty state
        default_state = {
            "session_id": session_id,
            "current_topic": None,
            "current_entity": None,
            "current_entity_type": None,
            "current_context": None,
            "last_turn_id": None,
            "last_user_message": None,
            "last_assistant_message": None,
            "active_correction": None,
        }
        self._memory_states[session_id] = default_state
        return default_state

    def update_state(
        self,
        session_id: str = "default",
        topic: Optional[str] = None,
        entity: Optional[str] = None,
        entity_type: Optional[str] = None,
        context_desc: Optional[str] = None,
        last_user: Optional[str] = None,
        last_assistant: Optional[str] = None,
        last_turn_id: Optional[int] = None,
        active_correction: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Updates session state in memory and asynchronously/synchronously in PostgreSQL.
        """
        if not session_id:
            session_id = "default"

        curr = self.get_state(session_id)

        if topic is not None:
            curr["current_topic"] = topic
        if entity is not None:
            curr["current_entity"] = entity
        if entity_type is not None:
            curr["current_entity_type"] = entity_type
        if context_desc is not None:
            curr["current_context"] = context_desc
        if last_user is not None:
            curr["last_user_message"] = last_user
        if last_assistant is not None:
            curr["last_assistant_message"] = last_assistant
        if last_turn_id is not None:
            curr["last_turn_id"] = last_turn_id
        if active_correction is not None:
            curr["active_correction"] = active_correction

        # Update in-memory
        self._memory_states[session_id] = curr

        # Persist to database
        db: Session = SessionLocal()
        try:
            record = db.query(ConversationStateModel).filter(
                ConversationStateModel.session_id == session_id
            ).first()

            if record:
                if topic is not None:
                    record.current_topic = topic
                if entity is not None:
                    record.current_entity = entity
                if entity_type is not None:
                    record.current_entity_type = entity_type
                if context_desc is not None:
                    record.current_context = context_desc
                if last_user is not None:
                    record.last_user_message = last_user
                if last_assistant is not None:
                    record.last_assistant_message = last_assistant
                if last_turn_id is not None:
                    record.last_turn_id = last_turn_id
                if active_correction is not None:
                    record.active_correction = active_correction
            else:
                record = ConversationStateModel(
                    session_id=session_id,
                    current_topic=curr["current_topic"],
                    current_entity=curr["current_entity"],
                    current_entity_type=curr["current_entity_type"],
                    current_context=curr["current_context"],
                    last_user_message=curr["last_user_message"],
                    last_assistant_message=curr["last_assistant_message"],
                    last_turn_id=curr["last_turn_id"],
                    active_correction=curr["active_correction"],
                )
                db.add(record)
            db.commit()
        except Exception as e:
            logger.warning(f"Error persisting conversation state for {session_id}: {e}")
            db.rollback()
        finally:
            db.close()

        return curr

    def apply_correction(
        self,
        session_id: str,
        new_entity: str,
        new_topic: Optional[str] = None,
        entity_type: Optional[str] = None
    ) -> Tuple[Optional[str], str]:
        """
        Applies a correction: returns (old_entity, new_entity) and updates state.
        """
        curr = self.get_state(session_id)
        old_entity = curr.get("current_entity")
        topic = new_topic or curr.get("current_topic") or new_entity

        correction_detail = f"{old_entity or 'unspecified'} -> {new_entity}"
        self.update_state(
            session_id=session_id,
            topic=topic,
            entity=new_entity,
            entity_type=entity_type or curr.get("current_entity_type"),
            active_correction=correction_detail
        )
        logger.info(f"Correction applied for session '{session_id}': {correction_detail}")
        return old_entity, new_entity

    def resolve_reference(self, session_id: str, pronoun: str) -> Optional[str]:
        """
        Resolves coreference pronouns ('it', 'they', 'that', 'this', 'its') using active state.
        """
        curr = self.get_state(session_id)
        entity = curr.get("current_entity")
        topic = curr.get("current_topic")

        clean_p = pronoun.lower().strip()
        if clean_p in {"it", "its", "that", "this"}:
            return entity or topic
        elif clean_p in {"they", "them", "their", "theirs", "these", "those"}:
            return entity or topic
        return entity or topic

    def clear_state(self, session_id: str = "default"):
        """Resets session state in memory and database."""
        if session_id in self._memory_states:
            del self._memory_states[session_id]

        db: Session = SessionLocal()
        try:
            db.query(ConversationStateModel).filter(
                ConversationStateModel.session_id == session_id
            ).delete()
            db.commit()
        except Exception as e:
            logger.warning(f"Error clearing conversation state for {session_id}: {e}")
            db.rollback()
        finally:
            db.close()


conversation_state_manager = ConversationStateManager()
