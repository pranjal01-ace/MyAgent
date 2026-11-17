import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.abspath("."))

from backend.agent.chat_service import chat_service
from backend.agent.cache import response_cache, normalize_prompt
from backend.memory.database import SessionLocal, QueryCacheModel

async def run_normalized_cache_test():
    q1 = "What is dependency injection in FastAPI?"
    q2 = "  WHAT IS DEPENDENCY INJECTION IN FASTAPI?  "
    
    key1 = normalize_prompt(q1)
    key2 = normalize_prompt(q2)
    
    # Ensure both resolve to the exact same normalized key
    assert key1 == key2, f"Normalization mismatch: '{key1}' != '{key2}'"

    # Remove any previous FastAPI test entries so q1 is a guaranteed fresh cache miss
    keys_to_clean = [
        "what is dependency injection in fastapi",
        "what is the purpose of dependency injection in fastapi"
    ]
    for k in keys_to_clean:
        if k in response_cache._memory_cache:
            del response_cache._memory_cache[k]

    db = SessionLocal()
    try:
        db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized.in_(keys_to_clean)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    assert response_cache.get(q1) is None, "Cache should be empty for q1 initially"
    assert response_cache.get(q2) is None, "Cache should be empty for q2 initially"

    print("=" * 60)
    print("TEST 6: NORMALIZED CACHE HIT BENCHMARK")
    print(f"Q1: '{q1}'")
    print(f"Q2: '{q2}'")
    print(f"Normalized key for both: '{key1}'")
    print("=" * 60)

    # 1. First request (Must be a cache miss -> invoke live LLM)
    tokens_1 = 0
    full_response_1 = ""
    is_cached_1 = False
    source_1 = None
    t0 = time.perf_counter()

    async for event in chat_service.stream_chat(q1, session_id="test_norm_session", speak=False):
        if event["type"] == "token":
            tokens_1 += 1
            full_response_1 += event.get("content", "")
        elif event["type"] == "done":
            is_cached_1 = event.get("cached", False)
            source_1 = event.get("source", "None (Ollama LLM generation)")

    lat_1_ms = (time.perf_counter() - t0) * 1000
    llm_invoked_1 = (not is_cached_1) and (tokens_1 > 0)
    if not is_cached_1:
        source_1 = "None (Ollama LLM generation)"

    print(f"\n[First Request] Completed in {lat_1_ms:.2f} ms")
    print(f"Cache source: {source_1}")
    print(f"LLM invoked: {llm_invoked_1}")
    print(f"Tokens received: {tokens_1}")
    print(f"Response preview: {full_response_1[:80]}...")

    # Verification checkpoint: Do not proceed if first request failed
    if not full_response_1 or tokens_1 == 0:
        print("[ERROR] First request failed to generate response. Aborting test.")
        return

    # 2. Second request with whitespace/casing differences (Must hit normalized cache)
    tokens_2 = 0
    full_response_2 = ""
    is_cached_2 = False
    source_2 = None

    # Check cache entry beforehand to get exact source from cache tier
    cached_lookup = response_cache.get(q2)
    source_from_cache = cached_lookup.get("source") if cached_lookup else None

    t0 = time.perf_counter()
    async for event in chat_service.stream_chat(q2, session_id="test_norm_session", speak=False):
        if event["type"] == "token":
            tokens_2 += 1
            full_response_2 += event.get("content", "")
        elif event["type"] == "done":
            is_cached_2 = event.get("cached", False)
            source_2 = event.get("source", source_from_cache)

    lat_2_ms = (time.perf_counter() - t0) * 1000
    llm_invoked_2 = (not is_cached_2) and (tokens_2 > 1)

    print(f"\n[Second Request] Completed in {lat_2_ms:.2f} ms")
    print(f"Cache source: {source_2}")
    print(f"LLM invoked: {llm_invoked_2}")
    print(f"Tokens received: {tokens_2}")

    # 3. Verifications
    answer_equivalent = (full_response_1.strip() == full_response_2.strip())
    passed = (
        llm_invoked_1
        and (not llm_invoked_2)
        and is_cached_2
        and answer_equivalent
        and source_2 == "in_memory"
    )

    print("\n" + "=" * 60)
    print("REPORT")
    print("=" * 60)
    print("First:")
    print(f"  latency: {lat_1_ms:.2f} ms")
    print(f"  cache source: {source_1}")
    print(f"  LLM invoked: {llm_invoked_1}")
    print("")
    print("Second:")
    print(f"  latency: {lat_2_ms:.2f} ms")
    print(f"  cache source: {source_2}")
    print(f"  LLM invoked: {llm_invoked_2}")
    print("")
    print(f"Answer equivalent: {answer_equivalent}")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_normalized_cache_test())
