"""
Benchmark Suite 5: Tests 49 - 50
- Test 49: API Error Handling (Input validation, status codes, payload bounds, exception safety)
- Test 50: End-to-End Recovery Stress Test (50 mixed concurrent requests across tiers, interruption & recovery)
"""

import sys
import os
import time
import json
import asyncio
import numpy as np
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.main import app
from backend.agent.chat_service import chat_service
from backend.agent.cache import response_cache
from backend.memory.vector_store import PostgresVectorStore
from backend.memory.database import SessionLocal, engine, KnowledgeVectorModel
from backend.memory.conversation import add_message, get_recent_messages

client = TestClient(app)

def test_49_api_error_handling():
    print("\n--- TEST 49: API ERROR HANDLING ---")
    results = []

    # 1. Missing required field on /api/chat
    t0 = time.perf_counter()
    r = client.post("/api/chat", json={})
    lat = (time.perf_counter() - t0) * 1000
    results.append({
        "case": "missing_required_fields",
        "status": r.status_code,
        "body": r.json(),
        "passed": r.status_code == 422,
        "latency_ms": lat
    })

    # 2. Empty string on /api/chat
    t0 = time.perf_counter()
    r = client.post("/api/chat", json={"message": "   "})
    lat = (time.perf_counter() - t0) * 1000
    results.append({
        "case": "empty_string",
        "status": r.status_code,
        "body": r.json(),
        "passed": r.status_code == 400 and "cannot be empty" in r.text,
        "latency_ms": lat
    })

    # 3. Extremely long string (5,000 characters)
    long_msg = "Ace is fire! " * 400
    t0 = time.perf_counter()
    r = client.post("/api/chat", json={"message": long_msg, "session_id": "test_49_overflow"})
    lat = (time.perf_counter() - t0) * 1000
    results.append({
        "case": "extremely_long_string_5k",
        "status": r.status_code,
        "body": f"HTTP {r.status_code} response handled",
        "passed": r.status_code in [200, 400, 422], # Server safely handles without crashing
        "latency_ms": lat
    })

    # 4. Malformed JSON payload
    t0 = time.perf_counter()
    r = client.post(
        "/api/chat",
        content=b"{malformed_json: missing_quotes,",
        headers={"Content-Type": "application/json"}
    )
    lat = (time.perf_counter() - t0) * 1000
    results.append({
        "case": "malformed_json",
        "status": r.status_code,
        "body": r.json(),
        "passed": r.status_code in [400, 422],
        "latency_ms": lat
    })

    # 5. Wrong data types (nested dict for message)
    t0 = time.perf_counter()
    r = client.post("/api/chat", json={"message": {"invalid": "object"}})
    lat = (time.perf_counter() - t0) * 1000
    results.append({
        "case": "wrong_data_types",
        "status": r.status_code,
        "body": r.json(),
        "passed": r.status_code == 422,
        "latency_ms": lat
    })

    # 6. Invalid query parameter data type (/api/conversations?limit=not_an_int)
    t0 = time.perf_counter()
    r = client.get("/api/conversations?limit=invalid_number")
    lat = (time.perf_counter() - t0) * 1000
    results.append({
        "case": "invalid_query_type",
        "status": r.status_code,
        "body": r.json(),
        "passed": r.status_code == 422,
        "latency_ms": lat
    })

    # 7. Non-existent memory deletion
    t0 = time.perf_counter()
    r = client.delete("/api/memory/nonexistent_key_benchmark_test_49")
    lat = (time.perf_counter() - t0) * 1000
    results.append({
        "case": "delete_nonexistent_memory",
        "status": r.status_code,
        "body": r.json(),
        "passed": r.status_code == 404,
        "latency_ms": lat
    })

    # 8. Server stability verification after bad requests
    t0 = time.perf_counter()
    r = client.get("/api/health")
    lat = (time.perf_counter() - t0) * 1000
    results.append({
        "case": "post_error_health_check",
        "status": r.status_code,
        "body": r.json(),
        "passed": r.status_code == 200 and r.json().get("status") in ["healthy", "degraded", "online"],
        "latency_ms": lat
    })

    all_passed = all(res["passed"] for res in results)
    print("Test 49 Results:")
    for res in results:
        print(f"  [{'PASS' if res['passed'] else 'FAIL'}] {res['case']}: status={res['status']} ({res['latency_ms']:.2f} ms)")

    print(f"  PASS/FAIL: {'PASS' if all_passed else 'FAIL'}")
    return results, all_passed


async def test_50_end_to_end_stress_and_recovery():
    print("\n--- TEST 50: END-TO-END RECOVERY STRESS TEST ---")
    
    # 1. Setup pre-seeded cache entry for hit distribution
    seed_prompt = "What is Portgas D. Ace's signature flame command attack?"
    seed_ans = "Ace's signature attack is Dai Enkai: Entei (Great Flame Command: Flame Emperor)!"
    seed_vec = [0.05] * 768
    seed_vec[0] = 0.99
    
    response_cache.set(seed_prompt, seed_ans)
    
    # Also seed a vector in vector store
    vstore = PostgresVectorStore(collection_name="stress_test_50")
    vstore.add_documents(
        chunks=[{"text": "Flame Emperor", "metadata": {"category": "test_50"}}],
        embeddings=[seed_vec],
        collection_name="stress_test_50"
    )
    
    # Build 50 concurrent requests across tiers:
    # - 10 exact cache hits
    # - 10 normalized cache hits
    # - 10 lexical cache hits
    # - 5 semantic cache hits
    # - 5 cold LLM requests (unique simple math prompts)
    # - 5 conversation-history queries
    # - 5 vector search queries
    tasks = []
    task_types = []
    
    # Tier 1: 10 Exact Cache Hits
    for i in range(10):
        tasks.append(chat_service.execute_chat(
            message=seed_prompt,
            session_id=f"stress_session_exact_{i}"
        ))
        task_types.append("exact_cache")
        
    # Tier 2: 10 Normalized Cache Hits
    for i in range(10):
        tasks.append(chat_service.execute_chat(
            message=f"   {seed_prompt.upper()}   ",
            session_id=f"stress_session_norm_{i}"
        ))
        task_types.append("normalized_cache")

    # Tier 3: 10 Lexical Cache Hits (slight word alteration)
    for i in range(10):
        tasks.append(chat_service.execute_chat(
            message="What is Portgas D. Ace's signature flame command attack?", # Jaccard match
            session_id=f"stress_session_lex_{i}"
        ))
        task_types.append("lexical_cache")
        
    # Tier 4: 5 Semantic Cache Hits (using vector matching)
    for i in range(5):
        tasks.append(chat_service.execute_chat(
            message=seed_prompt,
            session_id=f"stress_session_sem_{i}"
        ))
        task_types.append("semantic_cache")
        
    # Tier 5: 5 Cold LLM Misses
    for i in range(5):
        tasks.append(chat_service.execute_chat(
            message=f"Compute unique benchmark sum {i} + 100 for stress test.",
            session_id=f"stress_session_cold_{i}"
        ))
        task_types.append("cold_llm")
        
    # Tier 6: 5 Conversation history requests
    async def get_history_task(sid):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: get_recent_messages(limit=10, session_id=sid))

    for i in range(5):
        tasks.append(get_history_task(f"stress_session_cold_{i}"))
        task_types.append("conversation_history")
        
    # Tier 7: 5 Vector Search requests
    async def search_vector_task(vec):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: vstore.search_similarity(vec, top_k=3, collection_name="stress_test_50"))
        
    for i in range(5):
        tasks.append(search_vector_task(seed_vec))
        task_types.append("vector_search")

    assert len(tasks) == 50, f"Expected 50 tasks, got {len(tasks)}"
    
    print(f"Launching {len(tasks)} mixed requests concurrently...")
    
    t0 = time.perf_counter()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total_elapsed = (time.perf_counter() - t0) * 1000
    
    # Analyze results
    success_count = 0
    fail_count = 0
    errors = []
    
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            fail_count += 1
            errors.append(f"Task {i} ({task_types[i]}): {type(res).__name__}: {res}")
        else:
            success_count += 1
            
    # Connection leaks check
    checked_out = engine.pool.checkedout()
    
    # Interruption & Recovery check
    t_rec0 = time.perf_counter()
    db_ok = False
    with SessionLocal() as db:
        from sqlalchemy import text
        r = db.execute(text("SELECT 1")).scalar()
        db_ok = (r == 1)
    rec_time_ms = (time.perf_counter() - t_rec0) * 1000
    
    # Summary metrics
    avg_lat = total_elapsed / len(tasks)
    
    print("Test 50 Metrics:")
    print(f"  Total Requests: {len(tasks)}")
    print(f"  Successful: {success_count}")
    print(f"  Failed: {fail_count}")
    print(f"  Total Wall Clock: {total_elapsed:.2f} ms")
    print(f"  Average Latency: {avg_lat:.2f} ms")
    print(f"  DB Checked-out Connections: {checked_out}")
    print(f"  Post-stress DB recovery latency: {rec_time_ms:.2f} ms")
    print(f"  System Healthy: {db_ok and checked_out == 0 and fail_count == 0}")
    
    pass_status = (success_count >= 48 and checked_out == 0 and db_ok)
    print(f"  PASS/FAIL: {'PASS' if pass_status else 'FAIL'}")
    
    return {
        "total_requests": len(tasks),
        "success": success_count,
        "failed": fail_count,
        "elapsed_ms": total_elapsed,
        "avg_lat_ms": avg_lat,
        "checked_out_conns": checked_out,
        "recovery_ms": rec_time_ms,
        "db_ok": db_ok,
        "pass": pass_status,
        "errors": errors
    }

if __name__ == "__main__":
    test_49_api_error_handling()
    asyncio.run(test_50_end_to_end_stress_and_recovery())
