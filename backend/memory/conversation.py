"""Legacy facade module delegating conversation and memory operations
to the new domain repositories (ConversationRepository and MemoryRepository).
"""
from typing import List, Dict, Any
from backend.conversations.repository import conversation_repository
from backend.memories.repository import memory_repository


def add_message(sender: str, message: str, session_id: str = "default"):
    """Persist a conversation turn."""
    return conversation_repository.add_message(role=sender, content=message, session_id=session_id)


def estimate_tokens(text: str) -> int:
    """Fast, safe token estimation (~3.8 characters per token on average)."""
    return conversation_repository.estimate_tokens(text)


def get_budgeted_messages(
    session_id: str = "default",
    max_tokens: int = 1200,
    max_count: int = 25
) -> List[Dict[str, str]]:
    """Retrieve most recent messages dynamically fitting inside max_tokens."""
    return conversation_repository.get_budgeted_messages(
        session_id=session_id, max_tokens=max_tokens, max_count=max_count
    )


def get_recent_messages(limit: int = 10, session_id: str = "default") -> List[Dict[str, str]]:
    """Retrieve the N most recent messages in chronological order."""
    return conversation_repository.get_recent_messages(session_id=session_id, limit=limit)


def clear_conversation(session_id: str = "default"):
    """Clear messages for a session."""
    return conversation_repository.clear_conversation(session_id=session_id)


def add_long_term_memory(key: str, value: str, category: str = "general"):
    """Upsert a long-term memory entry."""
    return memory_repository.add_or_update_memory(key=key, value=value, category=category)


def delete_long_term_memory(key: str) -> bool:
    """Delete a long-term memory by key."""
    return memory_repository.delete_memory(key=key)


def get_long_term_memories() -> List[str]:
    """Retrieve formatted list of memories for context injection."""
    return memory_repository.get_long_term_memories()


def get_all_memories_detailed() -> List[Dict[str, Any]]:
    """Retrieve detailed memories with timestamps."""
    return memory_repository.get_all_memories_detailed()
