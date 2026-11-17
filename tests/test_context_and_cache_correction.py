"""
Test Suite: Context Understanding, Context-Aware Cache & Correction System
==========================================================================
Tests A through O covering all acceptance scenarios:
- Ambiguity recognition
- Correction detection and context updating
- Repeated query after correction (guaranteeing old cache does NOT win)
- Pronoun / coreference resolution ('it', 'they', 'that')
- Topic switching with coreferences
- Cache poisoning resistance and multi-tier invalidation (L1 Memory, L2 DB, L3 Lexical, L4 Vector)
- Session isolation
- Fallback resilience under analyzer failures
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agent.chat_service import ChatService
from backend.agent.cache import response_cache
from backend.context.models import ContextType, ContextAnalysis
from backend.context.analyzer import context_analyzer, ContextAnalyzer
from backend.context.state_manager import conversation_state_manager
from backend.conversations.repository import conversation_repository
from backend.memory.database import SessionLocal, QueryCacheModel, ConversationStateModel, ConversationModel


@pytest.fixture
def mock_service():
    """Setup a ChatService instance with clean state and mocked LLM."""
    service = ChatService()

    # Clear caches and states
    service.cache.clear()
    conversation_state_manager._memory_states.clear()

    # Clean test rows from database
    db = SessionLocal()
    try:
        db.query(ConversationModel).filter(ConversationModel.session_id.like("test_%")).delete()
        db.query(ConversationStateModel).filter(ConversationStateModel.session_id.like("test_%")).delete()
        db.query(QueryCacheModel).delete()
        db.commit()
    finally:
        db.close()

    # Mock Ollama stream generator that reflects context
    async def mock_stream(messages, system_prompt=None, memories=None):
        last_msg = (messages[-1]["content"] if messages else "").lower()
        sys_str = (system_prompt or "").lower()

        # Extract active contextual entity/topic if present
        is_fruit = "primary entity: fruit" in sys_str or "primary entity: apple fruit" in sys_str or "fruit" in last_msg
        is_samsung = "primary entity: samsung" in sys_str or "active topic: samsung" in sys_str or "samsung" in last_msg
        is_python = "primary entity: python" in sys_str or "active topic: python" in sys_str or "python" in last_msg

        if is_fruit:
            yield "An apple is a sweet edible fruit produced by an apple tree."
        elif is_samsung:
            yield "Samsung manufactures Galaxy series smartphones and various electronics."
        elif is_python:
            yield "Python was created by Guido van Rossum and released in 1991."
        elif "what is apple" in last_msg:
            yield "Apple Inc. is a major American multinational technology company."
        else:
            yield f"Response regarding: {messages[-1]['content'] if messages else ''}"

    service.llm.chat_stream = MagicMock(side_effect=mock_stream)
    service.tts.speak = MagicMock()
    return service


# ==============================================================================
# Test A: Basic Question
# ==============================================================================
@pytest.mark.anyio
async def test_a_basic_question(mock_service):
    """Basic non-contextual questions should return normal answers without spurious context."""
    res = await mock_service.execute_chat("What is the internet?", session_id="test_a", speak=False)
    assert "internet" in res["response"].lower()
    assert res["cached"] is False


# ==============================================================================
# Test B: Apple Ambiguity Recognition
# ==============================================================================
@pytest.mark.anyio
async def test_b_apple_ambiguity():
    """Analyzer identifies standalone 'What is Apple?' as inherently ambiguous."""
    analysis = await context_analyzer.analyze("What is Apple?", current_topic=None, current_entity=None)
    assert analysis.context_type == ContextType.AMBIGUOUS
    assert analysis.ambiguity_detected is True
    assert "fruit" in analysis.candidate_entities
    assert "technology_company" in analysis.candidate_entities


# ==============================================================================
# Test C: Correction Handling
# ==============================================================================
@pytest.mark.anyio
async def test_c_correction_handling(mock_service):
    """User correction 'No, I mean fruit' updates conversational entity and state."""
    session_id = "test_c"

    # Turn 1: Initial query
    res1 = await mock_service.execute_chat("What is Apple?", session_id=session_id, speak=False)
    assert any(w in res1["response"].lower() for w in ["tech", "iphone", "company", "apple inc"])

    # Turn 2: Correction
    res2 = await mock_service.execute_chat("No, I mean fruit.", session_id=session_id, speak=False)
    assert "fruit" in res2["response"].lower()

    # Verify updated state
    state = conversation_state_manager.get_state(session_id)
    assert "fruit" in (state["current_entity"] or "").lower()


# ==============================================================================
# Test D: Repeated Question After Correction (CRITICAL ACCEPTANCE TEST)
# ==============================================================================
@pytest.mark.anyio
async def test_d_repeated_question_after_correction(mock_service):
    """
    CRITICAL: Turn 1: 'What is Apple?' -> Apple Inc.
              Turn 2: 'No, I mean fruit' -> fruit
              Turn 3: 'What is Apple?' -> MUST return fruit, NOT Apple Inc.!
    """
    session_id = "test_d"

    # Turn 1
    res1 = await mock_service.execute_chat("What is Apple?", session_id=session_id, speak=False)
    assert any(w in res1["response"].lower() for w in ["tech", "iphone", "company", "apple inc"])

    # Turn 2: Correction
    res2 = await mock_service.execute_chat("No, I mean fruit.", session_id=session_id, speak=False)
    assert "fruit" in res2["response"].lower()

    # Turn 3: Ask the exact same query again!
    res3 = await mock_service.execute_chat("What is Apple?", session_id=session_id, speak=False)

    # MUST NOT return the old Apple Inc. answer!
    assert "technology company" not in res3["response"].lower()
    assert "fruit" in res3["response"].lower()


# ==============================================================================
# Test E: Follow-Up Pronoun Resolution
# ==============================================================================
@pytest.mark.anyio
async def test_e_follow_up_pronoun_resolution(mock_service):
    """'Where does it grow?' correctly resolves 'it' to the tracked apple fruit entity."""
    session_id = "test_e"

    await mock_service.execute_chat("Tell me about apple fruit.", session_id=session_id, speak=False)
    state = conversation_state_manager.get_state(session_id)
    resolved = conversation_state_manager.resolve_reference(session_id, "it")
    assert resolved is not None

    res = await mock_service.execute_chat("Where does it grow?", session_id=session_id, speak=False)
    assert "fruit" in res["response"].lower() or "apple" in res["response"].lower()


# ==============================================================================
# Test F: Topic Switch
# ==============================================================================
@pytest.mark.anyio
async def test_f_topic_switch(mock_service):
    """Switching from Apple to Python updates state and resolves subsequent 'it' to Python."""
    session_id = "test_f"

    await mock_service.execute_chat("Tell me about Apple.", session_id=session_id, speak=False)
    await mock_service.execute_chat("Forget that. Tell me about Python.", session_id=session_id, speak=False)

    state = conversation_state_manager.get_state(session_id)
    assert "python" in (state["current_topic"] or "").lower()

    res = await mock_service.execute_chat("Who created it?", session_id=session_id, speak=False)
    assert "Guido van Rossum" in res["response"]


# ==============================================================================
# Test G: Topic Switch With Explicit Pronoun 'They'
# ==============================================================================
@pytest.mark.anyio
async def test_g_topic_switch_with_they(mock_service):
    """Switching to Samsung correctly resolves 'they' to Samsung."""
    session_id = "test_g"

    await mock_service.execute_chat("Tell me about Apple.", session_id=session_id, speak=False)
    await mock_service.execute_chat("Actually, tell me about Samsung.", session_id=session_id, speak=False)

    res = await mock_service.execute_chat("What phones do they make?", session_id=session_id, speak=False)
    assert "samsung" in res["response"].lower() or "galaxy" in res["response"].lower()


# ==============================================================================
# Test H & I: Cache Poisoning & In-Memory LRU Invalidation
# ==============================================================================
@pytest.mark.anyio
async def test_h_and_i_cache_poisoning_and_lru_invalidation(mock_service):
    """Seed cache with wrong entity, trigger correction, verify old response is evicted from LRU."""
    # Seed cache
    mock_service.cache.set("what is apple", "Apple Inc. technology giant", entity="apple_inc", topic="apple")

    # Verify it was in LRU
    hit_before = mock_service.cache.get("what is apple", entity="apple_inc")
    assert hit_before is not None
    assert "technology giant" in hit_before["response"]

    # Trigger invalidation
    mock_service.cache.invalidate_context(topic="apple", entity="fruit", conflicting_context="apple_inc")

    # Incompatible cache lookup for fruit must be a MISS
    hit_after = mock_service.cache.get("what is apple", entity="fruit")
    assert hit_after is None


# ==============================================================================
# Test J: PostgreSQL Database Invalidation (Status Marked STALE)
# ==============================================================================
@pytest.mark.anyio
async def test_j_postgresql_invalidation(mock_service):
    """Verify database cache status transitions to STALE on invalidation."""
    db = SessionLocal()
    try:
        # Create an active record in database
        rec = QueryCacheModel(
            prompt_normalized="what is apple",
            cache_key="what is apple::apple_inc",
            context_key="apple_inc",
            topic="apple",
            entity="apple_inc",
            response="Apple technology corporation",
            status="ACTIVE"
        )
        db.add(rec)
        db.commit()

        # Invalidate
        mock_service.cache.invalidate_context(topic="apple", entity="fruit", conflicting_context="apple_inc")

        # Check DB status
        updated_rec = db.query(QueryCacheModel).filter(QueryCacheModel.cache_key == "what is apple::apple_inc").first()
        assert updated_rec.status == "STALE"
        assert updated_rec.is_active is False
    finally:
        db.close()


# ==============================================================================
# Test K: Lexical Cache Compatibility Safety
# ==============================================================================
@pytest.mark.anyio
async def test_k_lexical_cache_safety(mock_service):
    """Lexical similarity rejects match if entities are incompatible."""
    mock_service.cache.set("what is apple fruit", "Apples are delicious fruits", entity="fruit")

    # Query asking about tech company with similar words
    res = mock_service.cache.get("what is apple company", entity="technology_company")
    assert res is None


# ==============================================================================
# Test L: Vector Semantic Cache Context Compatibility Safety
# ==============================================================================
@pytest.mark.anyio
async def test_l_vector_cache_safety(mock_service):
    """Semantic vector lookup rejects semantically close candidate if entity conflicts."""
    cand = {
        "response": "Apple Inc is an American multinational tech giant",
        "entity": "apple_inc",
        "context_key": "apple_inc",
        "status": "ACTIVE"
    }

    # If active required entity is fruit, candidate MUST be rejected
    is_valid = mock_service.cache._validate_candidate(cand, required_entity="fruit")
    assert is_valid is False

    # If active required entity is apple_inc, candidate is accepted
    is_valid_match = mock_service.cache._validate_candidate(cand, required_entity="apple_inc")
    assert is_valid_match is True


# ==============================================================================
# Test M: New Session Isolation
# ==============================================================================
@pytest.mark.anyio
async def test_m_session_isolation(mock_service):
    """New session does not inherit prior session's temporary context."""
    session_1 = "test_m_1"
    session_2 = "test_m_2"

    # In session 1, user corrects to fruit
    await mock_service.execute_chat("What is Apple?", session_id=session_1, speak=False)
    await mock_service.execute_chat("No, I mean fruit.", session_id=session_1, speak=False)

    state_1 = conversation_state_manager.get_state(session_1)
    assert "fruit" in (state_1["current_entity"] or "").lower()

    # In session 2, initial state is clean
    state_2 = conversation_state_manager.get_state(session_2)
    assert state_2["current_entity"] is None


# ==============================================================================
# Test N & O: Analyzer Failure & Fallback Resilience
# ==============================================================================
@pytest.mark.anyio
async def test_n_and_o_analyzer_failure_fallback():
    """Analyzer gracefully handles LLM exceptions, returning safe fallback ContextAnalysis."""
    analyzer = ContextAnalyzer()

    # Simulate LLM raising an exception
    with patch("backend.llm.ollama_client.ollama_client._get_client") as mock_client:
        mock_client.side_effect = RuntimeError("Ollama connection timeout")

        res = await analyzer.analyze("Explain quantum computing", use_llm_if_needed=True)
        assert res is not None
        assert res.context_type == ContextType.NEW_TOPIC
        assert "quantum computing" in (res.topic or "").lower()
