import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.abspath("."))

from backend.agent.chat_service import chat_service
from backend.agent.cache import response_cache, normalize_prompt, compute_jaccard_similarity, get_prompt_embedding
from backend.memory.database import SessionLocal, QueryCacheModel, engine
from backend.config import settings

async def run_test_9():
    query = "What are the main differences between Python generators and iterators?"
    norm_key = normalize_prompt(query)

    print("=" * 65)
    print("TEST 9: CACHE MISS -> ACTUAL LLM GENERATION")
    print(f"Query: '{query}'")
    print(f"Normalized Key: '{norm_key}'")
    print("=" * 65)

    # 1. Inspect initial cache state across all tiers
    db = SessionLocal()
    try:
        # Tier 1 check
        t1_hit = norm_key in response_cache._memory_cache
        t1_result = "HIT" if t1_hit else "MISS"

        # Tier 2 check
        t2_rec = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == norm_key).first()
        t2_result = "HIT" if t2_rec else "MISS"

        # Tier 3 check (Lexical)
        max_lex = max([compute_jaccard_similarity(norm_key, k) for k in response_cache._memory_cache.keys()] or [0.0])
        t3_result = f"HIT ({max_lex:.4f})" if max_lex >= 0.85 else f"MISS ({max_lex:.4f})"

        # Tier 4 check (Semantic)
        query_vec = get_prompt_embedding(query)
        t4_sim = 0.0
        if query_vec and "postgresql" in str(engine.url):
            from sqlalchemy import text
            sql = text("SELECT cosine_similarity(embedding, :vec) AS sim FROM query_cache WHERE embedding IS NOT NULL ORDER BY sim DESC LIMIT 1;")
            row = db.execute(sql, {"vec": query_vec}).first()
            if row and row.sim is not None:
                t4_sim = float(row.sim)
        t4_result = f"HIT ({t4_sim:.4f})" if t4_sim >= response_cache.semantic_threshold else f"MISS ({t4_sim:.4f})"
    finally:
        db.close()

    print(f"Initial Cache Verification:")
    print(f"  Tier 1 (In-memory):     {t1_result}")
    print(f"  Tier 2 (PostgreSQL):    {t2_result}")
    print(f"  Tier 3 (Lexical):       {t3_result}")
    print(f"  Tier 4 (Semantic):      {t4_result}")

    assert t1_result == "MISS", "Tier 1 must be MISS"
    assert t2_result == "MISS", "Tier 2 must be MISS"
    assert "MISS" in t3_result, "Tier 3 must be MISS"
    assert "MISS" in t4_result, "Tier 4 must be MISS"

    # 2. Invoke real chat pipeline
    tokens = 0
    full_response = ""
    is_cached = False
    source = None
    t0 = time.perf_counter()

    async for event in chat_service.stream_chat(query, session_id="session_test_9", speak=False):
        if event["type"] == "token":
            tokens += 1
            full_response += event.get("content", "")
        elif event["type"] == "done":
            is_cached = event.get("cached", False)
            source = event.get("source", "None (Ollama LLM generation)")

    lat_ms = (time.perf_counter() - t0) * 1000
    llm_invoked = (not is_cached) and (tokens > 0)
    if not is_cached:
        source = "None (Ollama LLM generation)"

    print(f"\nExecution Complete:")
    print(f"  Latency: {lat_ms:.2f} ms")
    print(f"  LLM Invoked: {llm_invoked}")
    print(f"  Tokens Received: {tokens}")
    print(f"  Response Preview: {full_response[:100]}...")

    # 3. Verify Background Persistence
    print("\nVerifying background cache persistence in PostgreSQL...")
    persisted_rec = None
    for _ in range(20):
        await asyncio.sleep(0.5)
        db = SessionLocal()
        try:
            r = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == norm_key).first()
            if r and r.embedding is not None and len(r.embedding) > 0:
                persisted_rec = {
                    "id": r.id,
                    "prompt_normalized": r.prompt_normalized,
                    "embedding_dim": len(r.embedding),
                    "hit_count": r.hit_count
                }
                break
        finally:
            db.close()

    assert persisted_rec is not None, "PostgreSQL cache persistence failed!"
    print(f"  Cache Record ID: {persisted_rec['id']}")
    print(f"  Embedding Dimensions: {persisted_rec['embedding_dim']}")

    passed = (
        llm_invoked
        and not is_cached
        and len(full_response) > 0
        and persisted_rec is not None
        and persisted_rec["embedding_dim"] == 768
    )

    print("\n" + "=" * 65)
    print("OUTPUT FORMAT FOR TEST 9")
    print("=" * 65)
    print("Test 9:")
    print(f"Query: {query}")
    print(f"Cache source: {source}")
    print(f"LLM invoked: {'TRUE' if llm_invoked else 'FALSE'}")
    print(f"Response received: {'SUCCESS' if len(full_response) > 0 else 'FAIL'}")
    print(f"Latency: {lat_ms:.2f} ms")
    print(f"Tokens: {tokens}")
    print(f"Cache record: ID={persisted_rec['id']} ('{persisted_rec['prompt_normalized']}')")
    print(f"Embedding persisted: {'TRUE' if persisted_rec['embedding_dim'] == 768 else 'FALSE'} ({persisted_rec['embedding_dim']} dimensions)")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(run_test_9())
