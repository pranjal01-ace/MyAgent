import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.abspath("."))

from backend.agent.chat_service import chat_service
from backend.agent.cache import response_cache, normalize_prompt
from backend.memory.database import SessionLocal, QueryCacheModel

async def run_test_6a():
    q1 = "Explain dependency injection in FastAPI"
    q2 = "  EXPLAIN DEPENDENCY INJECTION IN FASTAPI  "
    
    norm1 = normalize_prompt(q1)
    norm2 = normalize_prompt(q2)
    assert norm1 == norm2, f"Normalization mismatch: '{norm1}' != '{norm2}'"

    # Step 1: Ensure this query is not already cached in memory or DB
    conflicting_keys = [
        "explain dependency injection in fastapi",
        "what is dependency injection in fastapi"
    ]
    for k in conflicting_keys:
        if k in response_cache._memory_cache:
            del response_cache._memory_cache[k]

    db = SessionLocal()
    try:
        db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized.in_(conflicting_keys)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    assert response_cache.get(q1) is None, "Prerequisite failed: q1 should be a pure cache miss initially"

    print("=" * 65)
    print("TEST 6A: POSTGRESQL NORMALIZED-CACHE HIT BENCHMARK")
    print(f"Query 1: '{q1}' (Normalized: '{norm1}')")
    print(f"Query 2: '{q2}' (Normalized: '{norm2}')")
    print("=" * 65)

    # Step 2: Send first query through real production chat pipeline
    tokens_1 = 0
    full_response_1 = ""
    is_cached_1 = False
    source_1 = None
    t0 = time.perf_counter()

    async for event in chat_service.stream_chat(q1, session_id="session_test_6a", speak=False):
        if event["type"] == "token":
            tokens_1 += 1
            full_response_1 += event.get("content", "")
        elif event["type"] == "done":
            is_cached_1 = event.get("cached", False)
            source_1 = event.get("source", "None (Ollama LLM generation)")

    lat_1_ms = (time.perf_counter() - t0) * 1000
    llm_invoked_1 = (not is_cached_1) and (tokens_1 > 0)
    if not is_cached_1:
        source_1 = "cache miss / Ollama"

    print(f"\n[First Request]")
    print(f"  Latency: {lat_1_ms:.2f} ms")
    print(f"  Cache source: {source_1}")
    print(f"  LLM invoked: {llm_invoked_1}")
    print(f"  Tokens generated: {tokens_1}")
    print(f"  Response preview: {full_response_1[:80]}...")

    if not full_response_1 or tokens_1 == 0:
        print("[ERROR] First request failed to generate response. Aborting.")
        return

    # Step 3: Verify QueryCacheModel record is persisted in PostgreSQL
    print("\nWaiting for background persistence to PostgreSQL...")
    persisted_record = None
    for attempt in range(10):
        await asyncio.sleep(0.5)
        db = SessionLocal()
        try:
            persisted_record = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == norm1).first()
            if persisted_record:
                break
        finally:
            db.close()

    assert persisted_record is not None, "PostgreSQL verification failed: QueryCacheModel not persisted!"
    print(f"[Verified] PostgreSQL QueryCacheModel record exists with id={persisted_record.id}, hit_count={persisted_record.hit_count}")

    # Step 4: Clear ONLY the in-memory response-cache entry
    assert norm1 in response_cache._memory_cache, "Expected norm1 to be in memory cache"
    del response_cache._memory_cache[norm1]
    # Ensure memory cache does NOT have norm1 or norm2
    assert norm2 not in response_cache._memory_cache, "Memory cache must NOT have norm2"
    print("[Verified] In-memory cache entry cleared. Memory cache does NOT contain query.")

    # Confirm PostgreSQL STILL has the record
    db = SessionLocal()
    try:
        check_db = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == norm1).first()
        initial_hit_count = check_db.hit_count or 1
        assert check_db is not None, "PostgreSQL record must still exist!"
    finally:
        db.close()

    # Step 5: Send second query
    # Check cache directly before to inspect tier source
    lookup_before = response_cache.get(q2)
    source_from_db_lookup = lookup_before.get("source") if lookup_before else None
    
    # Reset in-memory cache again because lookup_before loaded it into memory!
    if norm1 in response_cache._memory_cache:
        del response_cache._memory_cache[norm1]

    tokens_2 = 0
    full_response_2 = ""
    is_cached_2 = False
    source_2 = None

    t0 = time.perf_counter()
    async for event in chat_service.stream_chat(q2, session_id="session_test_6a", speak=False):
        if event["type"] == "token":
            tokens_2 += 1
            full_response_2 += event.get("content", "")
        elif event["type"] == "done":
            is_cached_2 = event.get("cached", False)
            source_2 = event.get("source", source_from_db_lookup)

    lat_2_ms = (time.perf_counter() - t0) * 1000
    llm_invoked_2 = (not is_cached_2) and (tokens_2 > 1)

    # Step 6: Verify PostgreSQL hit count was incremented
    db = SessionLocal()
    try:
        updated_db = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == norm1).first()
        postgres_queried = updated_db is not None and updated_db.hit_count > initial_hit_count
    finally:
        db.close()

    # If source reported is "exact_cache", that is production Tier 2 PostgreSQL exact
    if source_2 == "exact_cache":
        resolved_source_display = "postgres_exact (Tier 2 PostgreSQL exact cache)"
    else:
        resolved_source_display = source_2

    answer_equivalent = (full_response_1.strip() == full_response_2.strip())
    passed = (
        llm_invoked_1
        and (not llm_invoked_2)
        and is_cached_2
        and answer_equivalent
        and source_2 == "exact_cache"
        and postgres_queried
    )

    print("\n" + "=" * 65)
    print("TEST 6A EXECUTION REPORT")
    print("=" * 65)
    print("First:")
    print(f"  latency: {lat_1_ms:.2f} ms")
    print(f"  cache source: {source_1}")
    print(f"  LLM invoked: {llm_invoked_1}")
    print(f"  normalized prompt: '{norm1}'")
    print("")
    print("Second:")
    print(f"  latency: {lat_2_ms:.2f} ms")
    print(f"  cache source: {resolved_source_display}")
    print(f"  LLM invoked: {llm_invoked_2}")
    print(f"  PostgreSQL queried: {postgres_queried}")
    print(f"  normalized prompt: '{norm2}'")
    print("")
    print(f"Normalized prompt match: {norm1 == norm2} ('{norm1}')")
    print(f"Answer equivalent: {answer_equivalent}")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(run_test_6a())
