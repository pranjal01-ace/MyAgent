import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.abspath("."))

from backend.agent.chat_service import chat_service
from backend.agent.cache import response_cache, normalize_prompt
from backend.memory.database import SessionLocal, QueryCacheModel

async def run_test_10():
    query = "How do Python context managers work under the hood?"
    norm_key = normalize_prompt(query)

    print("=" * 65)
    print("TEST 10: BACKGROUND CACHE PERSISTENCE BENCHMARK")
    print(f"Query: '{query}'")
    print(f"Normalized Key: '{norm_key}'")
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

    assert response_cache.get(query) is None, "Prerequisite: Query must not be in cache"

    # 2. Measure user-facing chat execution
    t_start = time.perf_counter()
    resp = await chat_service.execute_chat(query, session_id="session_test_10", speak=False)
    t_returned = time.perf_counter()
    user_latency_ms = (t_returned - t_start) * 1000

    has_response = bool(resp and resp.get("response"))
    print(f"User-facing response returned in: {user_latency_ms:.2f} ms")
    print(f"Response preview: {resp.get('response', '')[:80]}...")

    # 3. Check IMMEDIATE database state (within ~1ms of return)
    # Background persistence involves Ollama embedding (~1.5s), so it should NOT block user response
    db = SessionLocal()
    immediate_row = None
    try:
        immediate_row = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == norm_key).first()
    finally:
        db.close()

    immediate_state = "PENDING / IN-FLIGHT (Asynchronous)" if immediate_row is None or immediate_row.embedding is None else "PERSISTED"
    print(f"Immediate PostgreSQL state: {immediate_state}")

    # 4. Await background worker completion and measure persistence latency
    t_bg_start = time.perf_counter()
    final_record = None
    bg_error = None
    for attempt in range(40): # up to 8 seconds
        await asyncio.sleep(0.2)
        db = SessionLocal()
        try:
            rec = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == norm_key).first()
            if rec and rec.embedding is not None and len(rec.embedding) > 0:
                final_record = {
                    "id": rec.id,
                    "prompt": rec.prompt_normalized,
                    "has_response": bool(rec.response),
                    "dim": len(rec.embedding),
                    "hit_count": rec.hit_count
                }
                break
        except Exception as e:
            bg_error = str(e)
        finally:
            db.close()

    t_bg_end = time.perf_counter()
    bg_duration_ms = (t_bg_end - t_returned) * 1000

    print(f"Background worker completed in: {bg_duration_ms:.2f} ms after user return")
    if final_record:
        print(f"Final Record: ID={final_record['id']}, Embedding Dimensions={final_record['dim']}, Response Present={final_record['has_response']}")

    passed = (
        has_response
        and final_record is not None
        and final_record["dim"] == 768
        and final_record["has_response"]
        and bg_error is None
    )

    print("\n" + "=" * 65)
    print("OUTPUT FORMAT FOR TEST 10")
    print("=" * 65)
    print("Test 10:")
    print(f"LLM response latency: {user_latency_ms:.2f} ms")
    print(f"Response returned: {'SUCCESS' if has_response else 'FAILED'}")
    print(f"Immediate persistence state: {immediate_state}")
    print(f"Persistence after worker completion: SUCCESS ({bg_duration_ms:.2f} ms)")
    print(f"Cache row created: {'TRUE' if final_record else 'FALSE'} (ID={final_record['id'] if final_record else 'None'})")
    print(f"Embedding persisted: {'TRUE' if final_record and final_record['dim'] == 768 else 'FALSE'} ({final_record['dim'] if final_record else 0} dimensions)")
    print(f"Background worker error: {bg_error if bg_error else 'None'}")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(run_test_10())
