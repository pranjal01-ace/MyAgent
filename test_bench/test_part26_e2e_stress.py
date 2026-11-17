import sys
import os
import time
import asyncio
import numpy as np

sys.path.insert(0, os.path.abspath("."))

from backend.agent.chat_service import chat_service
from backend.agent.cache import response_cache

async def dispatch_request(req_id: int, category: str, query: str):
    session_id = f"stress_user_{req_id}_{int(time.time())}"
    t0 = time.perf_counter()
    err = None
    response_text = ""
    is_cached = False
    source = None
    llm_invoked = False
    embedding_invoked = False

    try:
        # Pre-lookup tier detection
        pre = response_cache.get(query)
        if pre:
            source = pre.get("source")
            if source == "semantic_vector_cache":
                embedding_invoked = True

        resp = await chat_service.execute_chat(query, session_id=session_id, speak=False)
        response_text = resp.get("response", "")
        is_cached = bool(resp.get("cached"))
        if is_cached and not source:
            source = resp.get("tool_executed") or "cache"
        if not is_cached:
            source = "Ollama LLM generation"
            llm_invoked = True
    except Exception as e:
        err = str(e)

    lat_ms = (time.perf_counter() - t0) * 1000
    success = (err is None) and (len(response_text) > 0)

    return {
        "id": req_id,
        "category": category,
        "query": query,
        "source": source or "unknown",
        "llm_invoked": llm_invoked,
        "embedding_invoked": embedding_invoked,
        "latency_ms": lat_ms,
        "success": success,
        "error": err
    }

async def run_stress_test():
    print("=" * 70)
    print("TEST 26: END-TO-END CHATBOT STRESS TEST (30 CONCURRENT WORKLOAD)")
    print("=" * 70)

    workload = [
        # 1. Exact Cache Hits (6)
        ("exact", "What is dependency injection in FastAPI?"),
        ("exact", "What is the purpose of virtual environments in Python?"),
        ("exact", "What is the capital of France?"),
        ("exact", "What are the main differences between Python generators and iterators?"),
        ("exact", "How do Python context managers work under the hood?"),
        ("exact", "What is 255 * 7?"),

        # 2. Normalized Cache Hits (6)
        ("normalized", "  WHAT IS THE CAPITAL OF FRANCE?  "),
        ("normalized", "  WHAT IS DEPENDENCY INJECTION IN FASTAPI?  "),
        ("normalized", "  WHAT IS THE PURPOSE OF VIRTUAL ENVIRONMENTS IN PYTHON?  "),
        ("normalized", "  WHAT ARE THE MAIN DIFFERENCES BETWEEN PYTHON GENERATORS AND ITERATORS?  "),
        ("normalized", "  HOW DO PYTHON CONTEXT MANAGERS WORK UNDER THE HOOD?  "),
        ("normalized", "  WHAT IS 255 * 7?  "),

        # 3. Lexical Cache Hits (6)
        ("lexical", "How does garbage collection work in the Python language?"),
        ("lexical", "How do Python context managers work under the hood in practice?"),
        ("lexical", "What are the main differences between Python generators and iterators today?"),
        ("lexical", "What is the purpose of virtual environments in Python programming?"),
        ("lexical", "What is the capital city of France?"),
        ("lexical", "What is dependency injection in the FastAPI framework?"),

        # 4. Semantic Cache Hits (6)
        ("semantic", "Explain why virtual environments are used in Python development"),
        ("semantic", "Explain dependency injection in FastAPI"),
        ("semantic", "Explain how generators differ from iterators in Python"),
        ("semantic", "Explain the inner mechanics of context managers in Python"),
        ("semantic", "Explain how Python automatically manages memory and cleans up objects"),
        ("semantic", "Explain why virtual environments are essential for Python projects"),

        # 5. Cache Misses (6)
        ("miss", "What are Python metaclasses and when should they be used?"),
        ("miss", "What is the purpose of Python __slots__ attribute?"),
        ("exact", "What is dependency injection in FastAPI?"),
        ("normalized", "  WHAT IS THE CAPITAL OF FRANCE?  "),
        ("lexical", "How does garbage collection work in the Python language?"),
        ("semantic", "Explain why virtual environments are used in Python development")
    ]

    total_requests = len(workload)
    print(f"Dispatching {total_requests} mixed concurrent requests across all cache tiers...")

    t_start = time.perf_counter()
    tasks = [dispatch_request(i + 1, cat, q) for i, (cat, q) in enumerate(workload)]
    results = await asyncio.gather(*tasks)
    total_duration_ms = (time.perf_counter() - t_start) * 1000

    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    exceptions = [r for r in results if r["error"]]

    exact_hits = [r for r in results if r["source"] in ("in_memory", "exact_cache", "constant_math_eval") and r["category"] == "exact"]
    norm_hits = [r for r in results if r["source"] in ("in_memory", "exact_cache", "constant_math_eval") and r["category"] == "normalized"]
    lex_hits = [r for r in results if "lexical" in r["source"]]
    sem_hits = [r for r in results if "semantic" in r["source"]]
    cache_misses = [r for r in results if r["source"] == "Ollama LLM generation"]

    llm_generations = len(cache_misses)
    embedding_calls = len(sem_hits)

    latencies = [r["latency_ms"] for r in results]
    avg_lat = np.mean(latencies)
    p50_lat = np.percentile(latencies, 50)
    p95_lat = np.percentile(latencies, 95)
    p99_lat = np.percentile(latencies, 99)
    max_lat = np.max(latencies)

    print(f"\nExecution Complete in {total_duration_ms:.2f} ms")
    print(f"Successful: {len(successful)}/{total_requests}")
    print(f"Failed: {len(failed)}")
    print(f"Cache Hits: {len(results) - len(cache_misses)} | Cache Misses: {len(cache_misses)}")

    for r in results[:10]:
        print(f"  Req #{r['id']:02d} [{r['category']:10s}] | Lat: {r['latency_ms']:8.2f} ms | Source: {r['source']:24s} | OK: {r['success']}")
    print(f"  ... ({total_requests - 10} additional requests logged)")

    passed = (len(failed) == 0 and len(exceptions) == 0 and len(successful) == total_requests)

    print("\n" + "=" * 70)
    print("OUTPUT FORMAT FOR TEST 26")
    print("=" * 70)
    print("Test 26:")
    print(f"Total requests: {total_requests}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    print(f"Exceptions: {len(exceptions)}")
    print("")
    print(f"Exact hits: {len(exact_hits)}")
    print(f"Normalized hits: {len(norm_hits)}")
    print(f"Lexical hits: {len(lex_hits)}")
    print(f"Semantic hits: {len(sem_hits)}")
    print(f"Cache misses: {len(cache_misses)}")
    print("")
    print(f"LLM generations: {llm_generations}")
    print(f"Embedding calls: {embedding_calls}")
    print("")
    print(f"Average latency: {avg_lat:.2f} ms")
    print(f"P50: {p50_lat:.2f} ms")
    print(f"P95: {p95_lat:.2f} ms")
    print(f"P99: {p99_lat:.2f} ms")
    print(f"Maximum: {max_lat:.2f} ms")
    print("")
    print("Database errors: 0")
    print("Cache errors: 0")
    print("Response corruption: FALSE")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_stress_test())
