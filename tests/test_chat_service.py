import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from backend.agent.chat_service import ChatService
from backend.agent.cache import evaluate_constant_math, response_cache


@pytest.fixture
def mock_chat_service():
    service = ChatService()
    # Mock LLM streaming to count calls
    async def mock_stream(*args, **kwargs):
        tokens = ["Hello", " there! ", "I'm Ace."]
        for t in tokens:
            yield t
    service.llm.chat_stream = MagicMock(side_effect=mock_stream)
    service.tts.speak = MagicMock()
    service.cache.clear()

    # Clean test conversations
    from backend.memory.database import SessionLocal, ConversationModel
    db = SessionLocal()
    try:
        db.query(ConversationModel).filter(ConversationModel.session_id.like("test_%")).delete()
        db.commit()
    finally:
        db.close()

    return service



@pytest.mark.anyio
async def test_chat_service_execute_chat(mock_chat_service):
    res = await mock_chat_service.execute_chat(
        message="Hello Ace",
        session_id="test_session",
        speak=False
    )
    assert res["user_message"] == "Hello Ace"
    assert res["response"] == "Hello there! I'm Ace."
    assert res["state"] == "idle"


@pytest.mark.anyio
async def test_chat_service_stream_chat(mock_chat_service):
    events = []
    async for ev in mock_chat_service.stream_chat(
        message="What is up?",
        session_id="test_session",
        speak=False
    ):
        events.append(ev)

    assert len(events) >= 3
    assert events[0]["type"] == "start"
    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) == 3
    assert "".join([e["content"] for e in token_events]) == "Hello there! I'm Ace."
    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1
    assert done_events[0]["response"] == "Hello there! I'm Ace."


@pytest.mark.anyio
async def test_constant_math_eval_instant(mock_chat_service):
    """Verify that constant calculations like 2+2 do not query Ollama at all."""
    res = await mock_chat_service.execute_chat("2+2", session_id="test_math", speak=False)
    assert "**4**" in res["response"]
    assert res["cached"] is True
    # LLM stream should NOT be called
    mock_chat_service.llm.chat_stream.assert_not_called()

    # Streaming test
    events = []
    async for ev in mock_chat_service.stream_chat("what is 25 * 4?", session_id="test_math", speak=False):
        events.append(ev)
    assert any("**100**" in ev.get("content", "") for ev in events)
    mock_chat_service.llm.chat_stream.assert_not_called()


@pytest.mark.anyio
async def test_repeated_query_caching(mock_chat_service):
    """Verify that asking the same question again does not call Ollama twice."""
    # First call: hits mocked LLM
    res1 = await mock_chat_service.execute_chat("Who is Gol D. Roger?", session_id="test_cache", speak=False)
    assert res1["response"] == "Hello there! I'm Ace."
    assert mock_chat_service.llm.chat_stream.call_count == 1

    # Second call with same question (even with different whitespace or ?): served from cache
    res2 = await mock_chat_service.execute_chat("who is Gol D. Roger", session_id="test_cache", speak=False)
    assert res2["response"] == "Hello there! I'm Ace."
    assert res2["cached"] is True
    # LLM call count should still be 1 (Ollama was NOT called again!)
    assert mock_chat_service.llm.chat_stream.call_count == 1


@pytest.mark.anyio
async def test_historical_conversation_answer_lookup(mock_chat_service):
    """If user already asked a question in past conversation history, answer is recovered without Ollama."""
    from backend.memory.conversation import add_message
    session_id = "test_hist_session"

    # Simulate past conversation in SQLite
    add_message(sender="user", message="What is the One Piece?", session_id=session_id)
    add_message(sender="assistant", message="It is the ultimate treasure left by Gol D. Roger!", session_id=session_id)

    # Clear memory cache so it MUST read from persistent database
    mock_chat_service.cache._memory_cache.clear()

    # User asks the question again
    res = await mock_chat_service.execute_chat("what is the one piece?", session_id="another_session", speak=False)
    assert res["response"] == "It is the ultimate treasure left by Gol D. Roger!"
    assert res["cached"] is True
    # Ollama was NOT called at all!
    mock_chat_service.llm.chat_stream.assert_not_called()



@pytest.mark.anyio
async def test_chat_service_tool_intent_detection(mock_chat_service):
    tool_name, tool_exec, prefix = mock_chat_service.check_and_execute_tool("what time is it?")
    assert tool_name == "get_time"
    assert tool_exec is not None
    assert "get_time" in tool_exec
    assert prefix is not None
    assert "Executed desktop tool" in prefix


def test_markdown_code_formatting():
    from desktop.chat_drawer import format_markdown_to_html
    raw = "Here is some code:\n```python\nprint('hello world')\n```\nEnjoy!"
    formatted = format_markdown_to_html(raw)
    assert "hello world" in formatted and "print" in formatted
    assert "Python" in formatted or "code" in formatted.lower()
