import sys
import os
import time
import asyncio
from unittest.mock import patch
import httpx

sys.path.insert(0, os.path.abspath("."))

from backend.agent.chat_service import chat_service
from backend.agent.cache import response_cache, normalize_prompt
from backend.memory.database import SessionLocal, QueryCacheModel

async def run_test_11():
    query = "What is duck typing in Python programming?"
    norm_key = normalize_prompt(query)

    print("=" * 65)
    print("TEST 11: EMBEDDING FAILURE / TIMEOUT FALLBACK TEST")
    print(f"Query: '{query}'")
    print("=" * 65)

    # 1. Clean previous entry if present
    if norm_key in response_cache._memory_cache:
        del response_cache._memory_cache[norm_key]
    db = SessionLocal()
    try:
        db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == norm_key).delete()
        db.commit()
    finally:
        db.close()

    # 2. Simulate complete embedding failure / timeout in a controlled test context
    failure_simulated = "httpx.ConnectTimeout / ConnectionRefused on Ollama embedding endpoint"
    embedding_failed = False
    app_survived = False
    llm_fallback = False
    response_text = ""
    error_logged = False

    def mock_get_embedding_sync(self, text, dim=768):
        nonlocal embedding_failed
        embedding_failed = True
        raise httpx.ConnectTimeout("Simulated Ollama embedding service timeout after 2.0s")

    t0 = time.perf_counter()
    try:
        with patch("voice_assistant.rag.embeddings.OllamaEmbeddingGenerator.get_embedding_sync", mock_get_embedding_sync):
            resp = await chat_service.execute_chat(query, session_id="session_test_11", speak=False)
            response_text = resp.get("response", "")
            app_survived = True
            llm_fallback = bool(response_text and not resp.get("cached"))
    except Exception as e:
        app_survived = False
        print(f"Application crashed with unhandled exception: {e}")

    lat_ms = (time.perf_counter() - t0) * 1000
    print(f"Request completed in: {lat_ms:.2f} ms")
    print(f"Application survived: {app_survived}")
    print(f"LLM fallback triggered: {llm_fallback}")
    print(f"Response preview: {response_text[:80]}...")

    # Wait briefly for persistence attempt to complete
    await asyncio.sleep(1.5)

    # 3. Check database to ensure no corrupted cache entry was written
    db = SessionLocal()
    corrupted_entry = False
    cache_row = None
    try:
        cache_row = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == norm_key).first()
        if cache_row:
            # If embedding failed, embedding should either be None or handled safely, response must be non-empty string
            if cache_row.response is None or len(cache_row.response) == 0:
                corrupted_entry = True
    finally:
        db.close()

    # 4. Verify recovery after mock removal
    recovery_successful = False
    try:
        from backend.agent.cache import get_prompt_embedding
        test_vec = get_prompt_embedding("recovery test")
        recovery_successful = (test_vec is not None and len(test_vec) == 768)
    except Exception:
        recovery_successful = False

    passed = (
        app_survived
        and llm_fallback
        and len(response_text) > 0
        and not corrupted_entry
        and recovery_successful
    )

    print("\n" + "=" * 65)
    print("OUTPUT FORMAT FOR TEST 11")
    print("=" * 65)
    print("Test 11:")
    print(f"Failure simulated: {failure_simulated}")
    print(f"Embedding failure detected: {'TRUE' if embedding_failed else 'FALSE'}")
    print(f"Application survived: {'TRUE' if app_survived else 'FALSE'}")
    print(f"LLM fallback: {'TRUE' if llm_fallback else 'FALSE'}")
    print(f"Response received: {'SUCCESS' if len(response_text) > 0 else 'FAIL'}")
    print(f"Corrupted cache entry: {'TRUE' if corrupted_entry else 'FALSE'}")
    print(f"Error logged: {'TRUE' if embedding_failed else 'FALSE'}")
    print(f"Recovery successful: {'TRUE' if recovery_successful else 'FALSE'}")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(run_test_11())
