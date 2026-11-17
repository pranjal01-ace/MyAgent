import time
import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from backend.main import app
from backend.common.models import BaseAuditModel
from backend.core.database import SessionLocal, init_db
from backend.conversations.models import ConversationModel
from backend.conversations.repository import conversation_repository
from backend.memories.models import MemoryModel
from backend.memories.repository import memory_repository
from backend.cache.models import QueryCacheModel
from backend.cache.repository import cache_repository


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_base_audit_model_attributes():
    """Verify BaseAuditModel provides audit timestamps and active state."""
    db = SessionLocal()
    try:
        # Create a conversation turn using audit model
        msg = ConversationModel(
            session_id="test_audit_session",
            role="user",
            content="Testing audit timestamps."
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)

        assert msg.id is not None
        assert isinstance(msg.created_at, datetime)
        assert isinstance(msg.updated_at, datetime)
        assert msg.is_active is True

        created_ts = msg.created_at
        time.sleep(0.05)

        # Update message
        msg.content = "Updated content for audit timestamp."
        db.commit()
        db.refresh(msg)

        assert msg.content == "Updated content for audit timestamp."
        # Clean up
        db.delete(msg)
        db.commit()
    finally:
        db.close()


def test_conversation_repository_crud_and_budgeting():
    """Verify ConversationRepository CRUD operations and token budgeting."""
    session_id = "test_repo_session"
    conversation_repository.clear_conversation(session_id)

    # Insert turns
    msg1 = conversation_repository.add_message(role="user", content="Turn 1", session_id=session_id)
    msg2 = conversation_repository.add_message(role="assistant", content="Turn 2 reply", session_id=session_id)

    assert msg1.id is not None
    assert msg1.created_at is not None
    assert msg2.id is not None

    recent = conversation_repository.get_recent_messages(session_id=session_id, limit=10)
    assert len(recent) == 2
    assert recent[0]["content"] == "Turn 1"
    assert recent[1]["content"] == "Turn 2 reply"

    # Token budgeting
    budgeted = conversation_repository.get_budgeted_messages(session_id=session_id, max_tokens=100)
    assert len(budgeted) == 2

    # Cleanup
    deleted = conversation_repository.clear_conversation(session_id)
    assert deleted >= 2


def test_memory_repository_crud_and_audit():
    """Verify MemoryRepository upsert, audit fields, and deletion."""
    test_key = "test_arch_pref"
    memory_repository.delete_memory(test_key)

    mem = memory_repository.add_or_update_memory(
        key=test_key,
        value="Clean Architecture",
        category="design"
    )
    assert mem.id is not None
    assert mem.created_at is not None
    assert mem.updated_at is not None
    assert mem.is_active is True
    assert mem.value == "Clean Architecture"

    # Update value
    mem_updated = memory_repository.add_or_update_memory(
        key=test_key,
        value="Modular Domain Architecture",
        category="design"
    )
    assert mem_updated.id == mem.id
    assert mem_updated.value == "Modular Domain Architecture"

    # Fetch detailed
    detailed = memory_repository.get_all_memories_detailed()
    match = next((d for d in detailed if d["key"] == test_key), None)
    assert match is not None
    assert match["value"] == "Modular Domain Architecture"
    assert "created_at" in match

    # Delete
    deleted = memory_repository.delete_memory(test_key)
    assert deleted is True


def test_cache_repository_crud_and_audit():
    """Verify CacheRepository saves entries with audit fields and tracks hits."""
    norm_prompt = "what is clean code architecture?"
    # Cleanup previous entry if exists
    db = SessionLocal()
    try:
        db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == norm_prompt).delete()
        db.commit()
    finally:
        db.close()

    entry = cache_repository.save_cache_entry(
        prompt_norm=norm_prompt,
        response="Clean architecture separates concerns into domain modules.",
        tool_executed=None
    )
    assert entry.id is not None
    assert entry.created_at is not None
    assert entry.updated_at is not None
    assert entry.is_active is True
    assert entry.hit_count == 1

    # Fetch
    fetched = cache_repository.get_by_normalized_prompt(norm_prompt)
    assert fetched is not None
    assert fetched.response == "Clean architecture separates concerns into domain modules."

    # Hit count increment
    cache_repository.increment_hit_count(entry.id)
    fetched_after = cache_repository.get_by_normalized_prompt(norm_prompt)
    assert fetched_after.hit_count == 2

    # Cleanup
    db = SessionLocal()
    try:
        db.query(QueryCacheModel).filter(QueryCacheModel.id == entry.id).delete()
        db.commit()
    finally:
        db.close()


def test_domain_routers_integration(client):
    """Verify domain routers (conversations, memories, voice) through FastAPI TestClient."""
    # Health endpoint
    h_res = client.get("/api/health")
    assert h_res.status_code == 200

    # Conversations endpoint
    c_res = client.get("/api/conversations?session_id=test_api")
    assert c_res.status_code == 200
    assert "messages" in c_res.json()

    # Memories detailed endpoint
    m_res = client.get("/api/memories/detailed")
    assert m_res.status_code == 200
    assert "memories" in m_res.json()

    # Voice status endpoint
    v_res = client.get("/api/voice/status")
    assert v_res.status_code == 200
    assert "is_speaking" in v_res.json()

    # Voice stop endpoint
    s_res = client.post("/api/voice/stop")
    assert s_res.status_code == 200
    assert s_res.json().get("status") == "interrupted"
