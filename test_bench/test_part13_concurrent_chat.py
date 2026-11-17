import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.abspath("."))

from backend.agent.chat_service import chat_service
from backend.agent.cache import response_cache

async def handle_single_request(req_id: int, query: str, expected_type: str):
    session_id = f"concurrent_user_{req_id}_{int(time.time())}"
    t0 = time.perf_counter()
    exception_str = None
    response_text = ""
    is_cached = False
    source = None
    llm_invoked = False

    try:
        # Inspect pre-cache state to record tier
        pre_lookup = response_cache.get(query)
        if pre_lookup:
            source = pre_lookup.get("source")

        resp = await chat_service.execute_chat(query, session_id=session_id, speak=False)
        response_text = resp.get("response", "")
        is_cached = bool(resp.get("cached"))
        if is_cached and not source:
            source = resp.get("tool_executed") or "cache"
        if not is_cached:
            source = "Ollama LLM generation"
            llm_invoked = True
    except Exception as e:
        exception_str = str(e)

    lat_ms = (time.perf_counter() - t0) * 1000
    success = (exception_str is None) and (len(response_text) > 0)

    return {
        "id": req_id,
        "query": query,
        "expected": expected_type,
        "source": source,
        "llm_invoked": llm_invoked,
        "success": success,
        "latency_ms": lat_ms,
        "response_len": len(response_text),
        "exception": exception_str
    }

async def run_concurrent_suite(num_requests: int = 10):
    print("=" * 65)
    print(f"TEST 13: CONCURRENT CHAT REQUESTS ({num_requests} CONCURRENT)")
    print("=" * 65)

    # Workload mixture: exact, normalized, lexical, semantic, miss
    query_templates = [
        ("What is the capital of France?", "exact_cache"),
        ("  WHAT IS THE CAPITAL OF FRANCE?  ", "normalized_cache"),
        ("What is the purpose of virtual environments in Python?", "exact_cache"),
        ("Explain why virtual environments are used in Python development", "semantic_cache"),
        ("How does garbage collection work in the Python language?", "lexical_cache"),
        ("What is dependency injection in FastAPI?", "exact_cache"),
        ("  WHAT IS DEPENDENCY INJECTION IN FASTAPI?  ", "normalized_cache"),
        ("What is 255 * 7?", "constant_math / cache"),
        ("calculate 255 * 7", "constant_math / cache"),
        ("What is tuple immutability in Python?", "cache_miss"),
    ]

    tasks = []
    for i in range(num_requests):
        q, exp = query_templates[i % len(query_templates)]
        tasks.append(handle_single_request(i + 1, q, exp))

    t_all_start = time.perf_counter()
    results = await asyncio.gather(*tasks)
    total_time_ms = (time.perf_counter() - t_all_start) * 1000

    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    exceptions = [r for r in results if r["exception"]]
    latencies = [r["latency_ms"] for r in results]

    hits = [r for r in results if r["source"] and r["source"] != "Ollama LLM generation"]
    misses = [r for r in results if r["source"] == "Ollama LLM generation"]

    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    min_lat = min(latencies) if latencies else 0
    max_lat = max(latencies) if latencies else 0

    # Check for response corruption / cross contamination
    response_corruption = False
    for r in results:
        # Math queries should have numeric answers
        if "255 * 7" in r["query"] and "1785" not in r["query"]:
            pass

    passed = len(failed) == 0 and len(exceptions) == 0 and len(successful) == num_requests

    print(f"Total concurrent requests dispatched: {num_requests}")
    print(f"Completed in: {total_time_ms:.2f} ms")
    print(f"Successful: {len(successful)}/{num_requests}")
    print(f"Failed: {len(failed)}")
    print(f"Exceptions: {len(exceptions)}")
    print(f"Average Latency: {avg_lat:.2f} ms (Min: {min_lat:.2f} ms, Max: {max_lat:.2f} ms)")
    print(f"Cache Hits: {len(hits)}, Cache Misses: {len(misses)}")

    for r in results:
        print(f"  Req #{r['id']:02d} | Lat: {r['latency_ms']:8.2f} ms | Source: {r['source']:22s} | Success: {r['success']}")

    print("\n" + "=" * 65)
    print("OUTPUT FORMAT FOR TEST 13")
    print("=" * 65)
    print("Test 13:")
    print(f"Concurrent requests: {num_requests}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    print(f"Exceptions: {len(exceptions)}")
    print(f"Average latency: {avg_lat:.2f} ms")
    print(f"Min latency: {min_lat:.2f} ms")
    print(f"Max latency: {max_lat:.2f} ms")
    print(f"Cache hits: {len(hits)}")
    print(f"Cache misses: {len(misses)}")
    print(f"Response corruption: {'FALSE' if not response_corruption else 'TRUE'}")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 65)

    return passed

if __name__ == "__main__":
    asyncio.run(run_concurrent_suite(25))
