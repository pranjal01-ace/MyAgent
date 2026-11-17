import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.abspath("."))

from backend.agent.chat_service import chat_service
from backend.agent.cache import response_cache, normalize_prompt, compute_jaccard_similarity
from backend.memory.database import SessionLocal, QueryCacheModel

async def run_test_7():
    q1 = "How does garbage collection work in Python language?"
    q2 = "How does garbage collection work in the Python language?"

    norm1 = normalize_prompt(q1)
    norm2 = normalize_prompt(q2)

    # 1. Inspect lexical similarity & threshold
    threshold = 0.85
    sim = compute_jaccard_similarity(norm1, norm2)
    print("=" * 65)
    print("TEST 7: LEXICAL CACHE HIT BENCHMARK")
    print(f"Query 1: '{q1}'")
    print(f"Query 2: '{q2}'")
    print(f"Normalized 1: '{norm1}'")
    print(f"Normalized 2: '{norm2}'")
    print(f"Are normalized keys identical: {norm1 == norm2} (must be False)")
    print(f"Computed Jaccard similarity: {sim:.4f} (Threshold: {threshold})")
    assert norm1 != norm2, "Queries must have different normalized representations"
    assert sim >= threshold, f"Jaccard similarity {sim:.4f} must be >= {threshold}"
    print("=" * 65)

    # 2. Clean only these keys from cache to ensure clean test start
    for k in (norm1, norm2):
        if k in response_cache._memory_cache:
            del response_cache._memory_cache[k]

    db = SessionLocal()
    try:
        db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized.in_([norm1, norm2])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    assert response_cache.get(q1) is None, "Prerequisite check: q1 must be a cache miss initially"

    # 3. REQUEST 1 (Send Query 1 -> must invoke live Ollama LLM)
    tokens_1 = 0
    full_response_1 = ""
    is_cached_1 = False
    source_1 = None
    t0 = time.perf_counter()

    async for event in chat_service.stream_chat(q1, session_id="session_lexical_test", speak=False):
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

    print(f"\n[Request 1]")
    print(f"  Latency: {lat_1_ms:.2f} ms")
    print(f"  Cache source: {source_1}")
    print(f"  LLM invoked: {llm_invoked_1}")
    print(f"  Tokens received: {tokens_1}")
    print(f"  Response preview: {full_response_1[:80]}...")

    if not full_response_1 or tokens_1 == 0:
        print("[ERROR] Request 1 failed to receive LLM response. Aborting.")
        return

    # Verify that norm1 is now in in-memory cache
    assert norm1 in response_cache._memory_cache, "Expected Request 1 to populate in-memory cache with norm1"

    # 4. REQUEST 2 (Send Query 2 -> must hit Tier 3 lexical cache)
    # Check cache lookup directly beforehand to inspect tier resolution
    cached_lookup = response_cache.get(q2)
    source_from_cache = cached_lookup.get("source") if cached_lookup else None
    print(f"\n[Pre-check on Query 2 cache lookup]: source = '{source_from_cache}'")

    tokens_2 = 0
    full_response_2 = ""
    is_cached_2 = False
    source_2 = None

    t0 = time.perf_counter()
    async for event in chat_service.stream_chat(q2, session_id="session_lexical_test", speak=False):
        if event["type"] == "token":
            tokens_2 += 1
            full_response_2 += event.get("content", "")
        elif event["type"] == "done":
            is_cached_2 = event.get("cached", False)
            source_2 = event.get("source", source_from_cache)

    lat_2_ms = (time.perf_counter() - t0) * 1000
    llm_invoked_2 = (not is_cached_2) and (tokens_2 > 1)

    print(f"\n[Request 2]")
    print(f"  Latency: {lat_2_ms:.2f} ms")
    print(f"  Cache source: {source_2}")
    print(f"  LLM invoked: {llm_invoked_2}")
    print(f"  Tokens received: {tokens_2}")

    # 5. Verifications
    answer_equivalent = (full_response_1.strip() == full_response_2.strip())
    is_lexical_cache = (source_2 == "lexical_cache") or (source_from_cache == "lexical_cache")
    passed = (
        llm_invoked_1
        and (not llm_invoked_2)
        and is_cached_2
        and is_lexical_cache
        and answer_equivalent
        and (norm1 != norm2)
        and (sim >= threshold)
    )

    print("\n" + "=" * 65)
    print("REPORT")
    print("=" * 65)
    print("Test 7:\n")
    print(f"Query 1: {q1}")
    print(f"Query 2: {q2}\n")
    print(f"First latency: {lat_1_ms:.2f} ms")
    print(f"First cache source: {source_1}")
    print(f"First LLM invoked: {llm_invoked_1}\n")
    print(f"Second latency: {lat_2_ms:.2f} ms")
    print(f"Second cache source: {source_2}")
    print(f"Second LLM invoked: {llm_invoked_2}\n")
    print(f"Lexical similarity/matching evidence: Jaccard sim = {sim:.4f} (words: {len(set(norm1.split()) & set(norm2.split()))} shared / {len(set(norm1.split()) | set(norm2.split()))} total)")
    print(f"Matching threshold: >= {threshold}")
    print(f"Matched cache entry: '{norm1}'")
    print(f"Answer equivalent: {answer_equivalent}\n")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(run_test_7())
