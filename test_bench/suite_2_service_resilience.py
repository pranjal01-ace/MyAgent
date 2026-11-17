import sys
import os
import time
import asyncio
from unittest.mock import patch
import httpx

sys.path.insert(0, os.path.abspath("."))

from backend.agent.chat_service import chat_service
from backend.agent.cache import response_cache
from voice_assistant.rag.vector_store import UnifiedVectorStore

async def test_31_embedding_unavailable():
    print("\n--- TEST 31: EMBEDDING MODEL UNAVAILABLE ---")
    # Seed an exact entry, a normalized entry, and a lexical entry
    response_cache.set("what is python?", "Python is a high-level language.")
    response_cache.set("how does garbage collection work in python language?", "GC cleans memory.")

    def mock_embed_fail(self, text, dim=768):
        raise httpx.ConnectTimeout("Simulated nomic-embed-text outage")

    with patch("voice_assistant.rag.embeddings.OllamaEmbeddingGenerator.get_embedding_sync", mock_embed_fail), \
         patch("voice_assistant.rag.embeddings.OllamaEmbeddingGenerator.get_embedding", mock_embed_fail):

        t0 = time.perf_counter()
        # 1. Exact cache lookup works
        r_exact = response_cache.get("what is python?")
        # 2. Normalized cache lookup works
        r_norm = response_cache.get("  WHAT IS PYTHON?  ")
        # 3. Lexical lookup works
        r_lex = response_cache.get("how does garbage collection work in the python language?")
        # 4. Semantic lookup gracefully fails without crash on non-exact query
        r_sem = response_cache.get("What is an abstract syntax tree parser in computer science?")
        lat_ms = (time.perf_counter() - t0) * 1000

        # 5. Cold query still reaches LLM fallback
        resp = await chat_service.execute_chat("Tell me one word: hello", session_id="test_embed_unavail", speak=False)
        llm_fallback = bool(resp.get("response"))

    passed = (
        r_exact is not None and
        r_norm is not None and
        r_lex is not None and
        r_sem is None and # Graceful semantic miss without crash
        llm_fallback
    )

    print("Test 31 Results:")
    print(f"  Exact cache during embed outage: {'SUCCESS' if r_exact else 'FAILED'}")
    print(f"  Normalized cache during embed outage: {'SUCCESS' if r_norm else 'FAILED'}")
    print(f"  Lexical cache during embed outage: {'SUCCESS' if r_lex else 'FAILED'}")
    print(f"  Semantic lookup failure: GRACEFUL MISS (no crash)")
    print(f"  LLM fallback: {'SUCCESS' if llm_fallback else 'FAILED'}")
    print(f"  Latency: {lat_ms:.2f} ms")
    print(f"  PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    return {"name": "Test 31", "passed": passed, "lat": lat_ms, "details": "All non-semantic caches and LLM fallback operational during embed outage"}

async def test_32_chat_model_unavailable():
    print("\n--- TEST 32: OLLAMA CHAT MODEL UNAVAILABLE ---")
    response_cache.set("what is python?", "Python is a high-level language.")

    # 1. Cached requests continue working even if chat model is offline
    r_cached = await chat_service.execute_chat("what is python?", session_id="sess_chat_offline", speak=False)
    cache_worked = (r_cached.get("response") == "Python is a high-level language.")

    # 2. Simulate Ollama chat endpoint down for cold queries
    async def mock_stream_down(*args, **kwargs):
        raise httpx.ConnectError("Simulated Ollama chat model service unreachable on port 11434")
        yield "never"

    with patch("backend.llm.ollama_client.OllamaClient.chat_stream", mock_stream_down):
        t0 = time.perf_counter()
        caught_gracefully = False
        error_msg = ""
        try:
            # Stream chat should yield an error payload rather than crashing the process
            events = []
            async for ev in chat_service.stream_chat("What is an untranslatable quantum concept?", session_id="sess_err", speak=False):
                events.append(ev)
                if ev.get("type") == "error":
                    caught_gracefully = True
                    error_msg = ev.get("error", "")
        except Exception as e:
            caught_gracefully = False
            error_msg = str(e)
        lat_ms = (time.perf_counter() - t0) * 1000

    # 3. Verify recovery when unpatched
    resp_recovered = await chat_service.execute_chat("What is 10 + 10?", session_id="sess_rec", speak=False)
    recovered = bool(resp_recovered.get("response"))

    passed = cache_worked and caught_gracefully and recovered
    print("Test 32 Results:")
    print(f"  Cached requests operational: {cache_worked}")
    print(f"  Cold miss handled gracefully: {caught_gracefully} ('{error_msg}')")
    print(f"  Service recovered after restore: {recovered}")
    print(f"  PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    return {"name": "Test 32", "passed": passed, "lat": lat_ms, "details": "Stream yields structured error event; cache unaffected"}

async def test_33_postgresql_unavailable():
    print("\n--- TEST 33: POSTGRESQL UNAVAILABLE ---")
    response_cache.set("in memory key", "in memory value")

    # 1. In-memory cache works without PostgreSQL
    t0 = time.perf_counter()
    r_mem = response_cache._memory_cache.get("in memory key")

    # 2. Simulate PostgreSQL outage during UnifiedVectorStore search
    store = UnifiedVectorStore(collection_name="test_pg_outage")
    qdrant_fallback_worked = False

    with patch.object(store.pg_store, "search_similarity", side_effect=Exception("Simulated PostgreSQL connection drop / DB crash")):
        try:
            # Seed vector into Qdrant fallback store
            store._get_qdrant().add_documents(
                [{"text": "Qdrant fallback content during PG crash", "metadata": {"source": "qdrant"}}],
                [[0.1]*768]
            )
            hits = store.search_similarity([0.1]*768, top_k=1)
            qdrant_fallback_worked = len(hits) > 0
        except Exception as e:
            print(f"Qdrant fallback error: {e}")

    lat_ms = (time.perf_counter() - t0) * 1000
    passed = (r_mem is not None) and qdrant_fallback_worked

    print("Test 33 Results:")
    print(f"  In-memory cache survived: {r_mem is not None}")
    print(f"  Qdrant fallback during PG crash: {'SUCCESS' if qdrant_fallback_worked else 'FAILED'}")
    print(f"  Latency: {lat_ms:.2f} ms")
    print(f"  PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    return {"name": "Test 33", "passed": passed, "lat": lat_ms, "details": "Memory cache survives, UnifiedVectorStore switches to Qdrant"}

async def run_suite_2():
    r31 = await test_31_embedding_unavailable()
    r32 = await test_32_chat_model_unavailable()
    r33 = await test_33_postgresql_unavailable()
    return [r31, r32, r33]

if __name__ == "__main__":
    asyncio.run(run_suite_2())
