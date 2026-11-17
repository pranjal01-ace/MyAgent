import sys
import os
import time
import asyncio

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath("."))

from backend.agent.chat_service import chat_service
from backend.agent.cache import response_cache, normalize_prompt
from backend.memory.database import SessionLocal, QueryCacheModel

async def run_test():
    test_question = "What is the purpose of dependency injection in FastAPI?"
    key = normalize_prompt(test_question)
    
    # 1. Clear only this query from memory and database to ensure first request is a pure cache miss
    if key in response_cache._memory_cache:
        del response_cache._memory_cache[key]

    db = SessionLocal()
    try:
        db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == key).delete()
        db.commit()
    finally:
        db.close()

    # Verify cache miss initially
    assert response_cache.get(test_question) is None, "Cache should be empty for this test prompt"

    print("=" * 60)
    print(f"RUNNING EXACT CACHE HIT BENCHMARK")
    print(f"Query: '{test_question}'")
    print("=" * 60)

    # 2. First request (Cache miss -> live Ollama LLM execution)
    tokens_received_1 = 0
    t0 = time.perf_counter()
    full_response_1 = ""
    cache_source_1 = None
    is_cached_1 = False

    async for event in chat_service.stream_chat(test_question, session_id="test_cache_hit_session", speak=False):
        if event["type"] == "token":
            tokens_received_1 += 1
            full_response_1 += event.get("content", "")
        elif event["type"] == "done":
            is_cached_1 = event.get("cached", False)
            cache_source_1 = event.get("source", "none (cache miss)")

    lat_1_ms = (time.perf_counter() - t0) * 1000
    llm_invoked_1 = (not is_cached_1) and (tokens_received_1 > 0)
    if not is_cached_1:
        cache_source_1 = "None (Ollama LLM generation)"

    print(f"First request completed in {lat_1_ms:.2f} ms")
    print(f"Tokens received: {tokens_received_1}")
    print(f"Response preview: {full_response_1[:80]}...")

    # 3. Second identical request (Should hit Tier 1 in-memory cache instantly)
    tokens_received_2 = 0
    t0 = time.perf_counter()
    full_response_2 = ""
    cache_source_2 = None
    is_cached_2 = False

    # Check cache directly beforehand to inspect tier
    pre_check = response_cache.get(test_question)
    tier_detected = pre_check.get("source") if pre_check else "miss"

    async for event in chat_service.stream_chat(test_question, session_id="test_cache_hit_session", speak=False):
        if event["type"] == "token":
            tokens_received_2 += 1
            full_response_2 += event.get("content", "")
        elif event["type"] == "done":
            is_cached_2 = event.get("cached", False)
            cache_source_2 = event.get("source", tier_detected)

    lat_2_ms = (time.perf_counter() - t0) * 1000
    llm_invoked_2 = (not is_cached_2) and (tokens_received_2 > 1) # Cached yields the entire answer in 1 token event

    print(f"\nSecond request completed in {lat_2_ms:.2f} ms")
    print(f"Cache source: {cache_source_2}")

    # 4. Verifications
    answer_equivalent = (full_response_1.strip() == full_response_2.strip())
    is_in_memory = (cache_source_2 in ("in_memory", "Tier 1 (In-memory)")) or (tier_detected == "in_memory")
    no_llm_on_second = (not llm_invoked_2) and is_cached_2
    
    speedup = lat_1_ms / lat_2_ms if lat_2_ms > 0 else float("inf")
    passed = is_in_memory and answer_equivalent and no_llm_on_second

    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"First request:")
    print(f"  latency: {lat_1_ms:.2f} ms")
    print(f"  cache source: {cache_source_1}")
    print(f"  LLM invoked: {llm_invoked_1}")
    print("")
    print(f"Second request:")
    print(f"  latency: {lat_2_ms:.2f} ms")
    print(f"  cache source: {cache_source_2}")
    print(f"  LLM invoked: {llm_invoked_2}")
    print("")
    print(f"Speedup: {speedup:.1f}x")
    print(f"Answer equivalent: {answer_equivalent}")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_test())
