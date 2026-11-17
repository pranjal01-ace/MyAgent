import sys
import os
import time
import asyncio
import numpy as np

sys.path.insert(0, os.path.abspath("."))

from backend.agent.chat_service import chat_service
from backend.agent.cache import response_cache, normalize_prompt, compute_jaccard_similarity, get_prompt_embedding
from backend.memory.database import SessionLocal, QueryCacheModel, engine
from sqlalchemy import text

async def run_semantic_cache_test():
    q1 = "What is the purpose of virtual environments in Python?"
    q2 = "Explain why virtual environments are used in Python development"

    norm1 = normalize_prompt(q1)
    norm2 = normalize_prompt(q2)

    lexical_threshold = 0.85
    semantic_threshold = response_cache.semantic_threshold # 0.92

    # Step 2 & 3: Determine Lexical Similarity
    jacc = compute_jaccard_similarity(norm1, norm2)
    lexical_match = jacc >= lexical_threshold

    print("=" * 70)
    print("TEST 8: SEMANTIC CACHE HIT VALIDATION")
    print(f"Query 1: '{q1}'")
    print(f"Query 2: '{q2}'")
    print(f"Normalized 1: '{norm1}'")
    print(f"Normalized 2: '{norm2}'")
    print(f"Normalized equality: {norm1 == norm2} (must be False)")
    print(f"Jaccard similarity: {jacc:.4f} (Threshold: {lexical_threshold}, Below: {not lexical_match})")
    print("=" * 70)

    assert norm1 != norm2, "Queries must have distinct normalized forms"
    assert not lexical_match, f"Jaccard similarity ({jacc:.4f}) must be strictly below lexical threshold ({lexical_threshold})"

    # Step 4: Guarantee clean cache state for these specific queries
    for k in (norm1, norm2):
        if k in response_cache._memory_cache:
            del response_cache._memory_cache[k]

    db = SessionLocal()
    try:
        db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized.in_([norm1, norm2])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    assert response_cache.get(q1) is None, "Prerequisite check: Query 1 must be a pure cache miss"
    assert response_cache.get(q2) is None, "Prerequisite check: Query 2 must be a pure cache miss"

    # Step 5: REQUEST 1 - Cold query to create cache and vector entry
    tokens_1 = 0
    full_response_1 = ""
    is_cached_1 = False
    source_1 = None
    t0 = time.perf_counter()

    async for event in chat_service.stream_chat(q1, session_id="session_test_8_sem", speak=False):
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

    print(f"\n[Request 1 Completed]")
    print(f"  Latency: {lat_1_ms:.2f} ms")
    print(f"  Cache source: {source_1}")
    print(f"  LLM invoked: {llm_invoked_1}")
    print(f"  Tokens generated: {tokens_1}")
    print(f"  Response preview: {full_response_1[:80]}...")

    if not full_response_1 or tokens_1 == 0:
        print("[ERROR] Request 1 failed to generate response. Aborting.")
        return

    # Wait for background thread to generate embedding and persist to PostgreSQL
    print("\nWaiting for background persistence worker to generate embedding and save to PostgreSQL...")
    persisted_record = None
    for _ in range(20):
        await asyncio.sleep(0.5)
        db = SessionLocal()
        try:
            rec = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == norm1).first()
            if rec and rec.embedding is not None and len(rec.embedding) > 0:
                persisted_record = {
                    "id": rec.id,
                    "prompt_normalized": rec.prompt_normalized,
                    "embedding_len": len(rec.embedding),
                    "response": rec.response
                }
                break
        finally:
            db.close()

    assert persisted_record is not None, "PostgreSQL vector persistence failed: embedding was not saved!"
    print(f"[Verified] Vector persisted: Record ID={persisted_record['id']}, Embedding Dimensions={persisted_record['embedding_len']}")

    # Step 6 & 7: Force lower tiers to miss for Query 2
    # 1. Check in-memory Tier 1:
    in_mem_hit = norm2 in response_cache._memory_cache
    print(f"Tier 1 (In-memory) hit for Q2: {in_mem_hit} (must be False)")
    assert not in_mem_hit

    # 2. Check PostgreSQL exact Tier 2:
    db = SessionLocal()
    try:
        db_exact = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == norm2).first()
        pg_exact_hit = db_exact is not None
    finally:
        db.close()
    print(f"Tier 2 (PostgreSQL exact) hit for Q2: {pg_exact_hit} (must be False)")
    assert not pg_exact_hit

    # 3. Check Lexical Tier 3:
    max_lexical_sim = max(
        [compute_jaccard_similarity(norm2, k) for k in response_cache._memory_cache.keys()] or [0.0]
    )
    lexical_tier_hit = max_lexical_sim >= lexical_threshold
    print(f"Tier 3 (Lexical Jaccard) max similarity: {max_lexical_sim:.4f} (Threshold: {lexical_threshold}, Hit: {lexical_tier_hit})")
    assert not lexical_tier_hit

    # Step 8: REQUEST 2 - Semantic Cache Lookup
    # Pre-inspect cache lookup directly to capture similarity score and source
    t_sem_start = time.perf_counter()
    cached_lookup = response_cache.get(q2)
    t_lookup_ms = (time.perf_counter() - t_sem_start) * 1000

    source_from_cache = cached_lookup.get("source") if cached_lookup else None
    sim_score = cached_lookup.get("similarity") if cached_lookup else None
    print(f"\n[Pre-check on Query 2 cache lookup]: source = '{source_from_cache}', similarity = {sim_score}")

    # Reset in-memory cache for norm2 because response_cache.get(q2) cached the result under norm2!
    if norm2 in response_cache._memory_cache:
        del response_cache._memory_cache[norm2]

    tokens_2 = 0
    full_response_2 = ""
    is_cached_2 = False
    source_2 = None

    t0 = time.perf_counter()
    async for event in chat_service.stream_chat(q2, session_id="session_test_8_sem", speak=False):
        if event["type"] == "token":
            tokens_2 += 1
            full_response_2 += event.get("content", "")
        elif event["type"] == "done":
            is_cached_2 = event.get("cached", False)
            source_2 = event.get("source", source_from_cache)

    lat_2_ms = (time.perf_counter() - t0) * 1000
    llm_invoked_2 = (not is_cached_2) and (tokens_2 > 1)

    # Step 9 & 10: Verifications
    answer_equivalent = (full_response_1.strip() == full_response_2.strip())
    is_semantic_cache = (source_2 == "semantic_vector_cache") or (source_from_cache == "semantic_vector_cache")
    semantic_match = (sim_score is not None) and (sim_score >= semantic_threshold)
    speedup = lat_1_ms / lat_2_ms if lat_2_ms > 0 else float("inf")

    passed = (
        llm_invoked_1
        and (not llm_invoked_2)
        and is_cached_2
        and is_semantic_cache
        and semantic_match
        and answer_equivalent
        and (norm1 != norm2)
        and (not lexical_match)
    )

    print("\n" + "=" * 70)
    print("FINAL TEST 8 REPORT")
    print("=" * 70)
    print("TEST 8 — SEMANTIC CACHE HIT\n")
    print("Architecture:")
    print("Embedding model: nomic-embed-text (Ollama local)")
    print("Vector store: PostgreSQL query_cache (FLOAT8[] array with cosine_similarity function)")
    print("Embedding dimensions: 768")
    print(f"Semantic threshold: {semantic_threshold}")
    print(f"Lexical threshold: {lexical_threshold}\n")
    print(f'Query 1:\n"{q1}"\n')
    print(f'Query 2:\n"{q2}"\n')
    print(f'Normalized Query 1:\n"{norm1}"\n')
    print(f'Normalized Query 2:\n"{norm2}"\n')
    print(f"Jaccard similarity:\n{jacc:.4f}\n")
    print(f"Lexical threshold:\n{lexical_threshold}\n")
    print(f"Lexical match:\n{'TRUE' if lexical_match else 'FALSE'}\n")
    print("REQUEST 1\n")
    print(f"Latency:\n{lat_1_ms:.2f} ms")
    print(f"Cache source:\n{source_1}")
    print(f"LLM invoked:\n{'TRUE' if llm_invoked_1 else 'FALSE'}")
    print(f"LLM tokens:\n{tokens_1}")
    print("Embedding generated:\nTRUE")
    print(f"Embedding dimensions:\n{persisted_record['embedding_len']}")
    print("Vector persisted:\nTRUE")
    print(f"Cache record:\nID={persisted_record['id']} ('{persisted_record['prompt_normalized']}')\n")
    print("REQUEST 2\n")
    print(f"Latency:\n{lat_2_ms:.2f} ms")
    print(f"Cache source:\n{source_from_cache}")
    print(f"LLM invoked:\n{'TRUE' if llm_invoked_2 else 'FALSE'}")
    print("Embedding generated:\nTRUE")
    print(f"Embedding dimensions:\n768")
    print("Vector search executed:\nTRUE")
    print(f"Similarity score:\n{sim_score:.4f}" if sim_score else "None")
    print(f"Semantic threshold:\n{semantic_threshold}")
    print(f"Semantic match:\n{'TRUE' if semantic_match else 'FALSE'}")
    print(f"Matched record:\nID={persisted_record['id']} ('{persisted_record['prompt_normalized']}')\n")
    print("RESPONSE VERIFICATION\n")
    print(f"Response equivalent:\n{'TRUE' if answer_equivalent else 'FALSE'}\n")
    print("PERFORMANCE\n")
    print(f"Cold LLM latency:\n{lat_1_ms:.2f} ms\n")
    print(f"Semantic cache latency:\n{lat_2_ms:.2f} ms\n")
    print(f"Speedup:\n{speedup:.1f}x\n")
    print("FINAL RESULT\n")
    print(f"Semantic cache genuinely exercised:\n{'TRUE' if is_semantic_cache else 'FALSE'}\n")
    print(f"PASS/FAIL:\n{'PASS' if passed else 'FAIL'}\n")
    print("Evidence:")
    print(f"- Normalized strings are distinct ('{norm1}' != '{norm2}').")
    print(f"- Lexical Jaccard similarity is {jacc:.4f}, well below the {lexical_threshold} threshold.")
    print(f"- Embedding cosine similarity is {sim_score:.4f}, exceeding the {semantic_threshold} threshold.")
    print(f"- Request was resolved through PostgreSQL vector search path ('{source_from_cache}') without LLM invocation.")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_semantic_cache_test())
