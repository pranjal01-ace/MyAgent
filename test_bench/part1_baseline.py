import sys
import os
sys.path.insert(0, os.path.abspath("."))

import asyncio
import time
from backend.agent.chat_service import ChatService
from backend.agent.cache import response_cache

async def run_baseline_test():
    print("==================================================")
    print("TEST 1: BASELINE CHATBOT LATENCY")
    print("==================================================")

    service = ChatService()
    # Ensure fresh cache for baseline
    response_cache.clear()

    test_cases = [
        {
            "label": "Math Expression",
            "q1": "what is 255 * 7?",
            "q2": "what is 255 * 7?",
            "q3": "calculate 255 * 7"
        },
        {
            "label": "Factoid / Capital",
            "q1": "what is the capital of France?",
            "q2": "what is the capital of France?",
            "q3": "what is the capital city of France?"
        },
        {
            "label": "Conceptual / Python",
            "q1": "explain Python",
            "q2": "explain Python",
            "q3": "explain Python programming language"
        },
        {
            "label": "Framework / FastAPI",
            "q1": "what is FastAPI?",
            "q2": "what is FastAPI?",
            "q3": "what is FastAPI framework?"
        }
    ]

    for tc in test_cases:
        print(f"\n--- Question: '{tc['q1']}' ({tc['label']}) ---")
        
        # 1. First request
        t0 = time.perf_counter()
        res1 = await service.execute_chat(tc["q1"], session_id="baseline_session", speak=False)
        lat1 = (time.perf_counter() - t0) * 1000
        # Determine source
        src1 = "math_eval" if res1.get("tool_executed") == "constant_math_eval" else ("cache" if res1.get("cached") else "Ollama LLM generation")
        print(f"First request:           {lat1:8.2f} ms | Source: {src1}")
        print(f"Response preview:        {res1['response'][:80]}...")

        # Wait briefly for background persistence
        await asyncio.sleep(1.2)

        # 2. Second identical request
        cache_check2 = response_cache.get(tc["q2"])
        src2 = cache_check2.get("source", "unknown") if cache_check2 else "miss"
        t0 = time.perf_counter()
        res2 = await service.execute_chat(tc["q2"], session_id="baseline_session", speak=False)
        lat2 = (time.perf_counter() - t0) * 1000
        print(f"Second identical:        {lat2:8.2f} ms | Source: {src2}")

        # 3. Rephrased request
        cache_check3 = response_cache.get(tc["q3"])
        src3 = cache_check3.get("source", "miss") if cache_check3 else "miss"
        sim3 = cache_check3.get("similarity") if cache_check3 else None
        sim_str = f" (sim={sim3:.3f})" if sim3 is not None else ""
        t0 = time.perf_counter()
        res3 = await service.execute_chat(tc["q3"], session_id="baseline_session", speak=False)
        lat3 = (time.perf_counter() - t0) * 1000
        if not cache_check3 and not res3.get("cached"):
            src3 = "Ollama LLM generation"
        print(f"Rephrased ('{tc['q3']}'): {lat3:8.2f} ms | Source: {src3}{sim_str}")

if __name__ == "__main__":
    asyncio.run(run_baseline_test())
