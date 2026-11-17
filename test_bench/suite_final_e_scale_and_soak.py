"""
Benchmark Suite Final E: Scale, Stress, Leaks & Soak Testing
- Test 66: Vector Search Accuracy at Scale (100, 1,000, 10,000 vectors)
- Test 67: Vector Search Performance Regression (100 to 20,000 vectors)
- Test 68: Connection Pool Leak Test (1,000 DB operations, checked-out == 0)
- Test 69: Concurrent Mixed Workload (100 concurrent operations across all tiers)
- Test 70: Full System Soak Test (continuous multi-cycle workload monitoring metrics)
"""

import sys
import os
import time
import psutil
import json
import asyncio
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.agent.cache import response_cache, normalize_prompt
from backend.memory.database import SessionLocal, engine, KnowledgeVectorModel, ConversationModel, QueryCacheModel
from backend.memory.vector_store import PostgresVectorStore
from backend.memory.conversation import add_message, get_recent_messages
from backend.agent.chat_service import chat_service
from voice_assistant.rag.embeddings import OllamaEmbeddingGenerator

emb_gen = OllamaEmbeddingGenerator()

def generate_synthetic_vectors(count: int, dim: int = 768):
    vecs = np.random.randn(count, dim).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return (vecs / norms).tolist()

def test_66_vector_search_accuracy_at_scale():
    print("\n--- TEST 66: VECTOR SEARCH ACCURACY AT SCALE (100, 1k, 10k) ---")
    dataset_sizes = [100, 1000, 10000]
    results = []
    
    for size in dataset_sizes:
        coll = f"bench_acc_scale_{size}"
        store = PostgresVectorStore(collection_name=coll)
        
        # Clean any old rows
        with SessionLocal() as db:
            db.query(KnowledgeVectorModel).filter(KnowledgeVectorModel.collection_name == coll).delete()
            db.commit()
            
        # Target needle
        target_vec = np.random.randn(768).astype(np.float32)
        target_vec /= np.linalg.norm(target_vec)
        target_vec = target_vec.tolist()
        
        # Distractors
        distractors = generate_synthetic_vectors(size - 1, dim=768)
        
        # Insert all
        chunks = [{"text": f"Distractor document #{i} for scale test", "metadata": {"idx": i}} for i in range(size - 1)]
        chunks.append({"text": "TARGET NEEDLE: Portgas D. Ace executes Dai Enkai: Entei!", "metadata": {"is_target": True}})
        all_vecs = distractors + [target_vec]
        
        store.add_documents(chunks, all_vecs, collection_name=coll)
        
        # Search with target vector
        t0 = time.perf_counter()
        hits = store.search_similarity(target_vec, top_k=5, collection_name=coll)
        lat = (time.perf_counter() - t0) * 1000
        
        target_in_top1 = len(hits) > 0 and "TARGET NEEDLE" in hits[0].get("text", "")
        target_in_top5 = any("TARGET NEEDLE" in h.get("text", "") for h in hits)
        score = hits[0]["score"] if hits else 0.0
        
        passed = target_in_top1 and (score >= 0.999)
        results.append({
            "dataset_size": size,
            "top_k": 5,
            "recall_at_1": 1.0 if target_in_top1 else 0.0,
            "recall_at_5": 1.0 if target_in_top5 else 0.0,
            "score": score,
            "latency_ms": lat,
            "pass": passed
        })
        
        # Cleanup
        store.clear_collection(coll)
        
    all_pass = all(r["pass"] for r in results)
    print("Test 66 Results:")
    for r in results:
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] Size {r['dataset_size']:5d}: recall@1={r['recall_at_1']}, recall@5={r['recall_at_5']}, score={r['score']:.4f} ({r['latency_ms']:.2f} ms)")
    print(f"  PASS/FAIL: {'PASS' if all_pass else 'FAIL'}")
    return results, all_pass


def test_67_vector_search_performance_regression():
    print("\n--- TEST 67: VECTOR SEARCH PERFORMANCE REGRESSION ---")
    sizes = [100, 1000, 5000, 10000, 20000]
    results = []
    
    # Pre-generate 1 real embedding to measure pure DB search latency
    probe_query = "What is Ace's ultimate flame attack?"
    t_emb0 = time.perf_counter()
    probe_vec = emb_gen.get_embedding_sync(probe_query)
    emb_latency = (time.perf_counter() - t_emb0) * 1000
    
    coll = "bench_perf_regression"
    store = PostgresVectorStore(collection_name=coll)
    store.clear_collection(coll)
    
    current_count = 0
    for target_size in sizes:
        needed = target_size - current_count
        new_vecs = generate_synthetic_vectors(needed, dim=768)
        new_chunks = [{"text": f"Doc {current_count + i}", "metadata": {"idx": current_count + i}} for i in range(needed)]
        store.add_documents(new_chunks, new_vecs, collection_name=coll)
        current_count = target_size
        
        # Run 10 DB searches to collect percentiles
        db_latencies = []
        for _ in range(10):
            t0 = time.perf_counter()
            hits = store.search_similarity(probe_vec, top_k=5, collection_name=coll)
            db_latencies.append((time.perf_counter() - t0) * 1000)
            
        p50 = float(np.percentile(db_latencies, 50))
        p95 = float(np.percentile(db_latencies, 95))
        p99 = float(np.percentile(db_latencies, 99))
        avg = float(np.mean(db_latencies))
        
        results.append({
            "vector_count": target_size,
            "embedding_gen_ms": emb_latency,
            "db_search_avg_ms": avg,
            "db_search_p50_ms": p50,
            "db_search_p95_ms": p95,
            "db_search_p99_ms": p99,
            "total_retrieval_avg_ms": emb_latency + avg,
            "pass": avg < 100.0 # Strict threshold: in-database search < 100ms
        })
        
    store.clear_collection(coll)
    all_pass = all(r["pass"] for r in results)
    print(f"Embedding Generation Latency: {emb_latency:.2f} ms")
    print("Database Vector Search Latency across Dataset Scales:")
    for r in results:
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['vector_count']:5d} vecs: DB Avg={r['db_search_avg_ms']:.2f}ms, P50={r['db_search_p50_ms']:.2f}ms, P95={r['db_search_p95_ms']:.2f}ms | Total={r['total_retrieval_avg_ms']:.2f}ms")
    print(f"  PASS/FAIL: {'PASS' if all_pass else 'FAIL'}")
    return results, all_pass


def test_68_connection_pool_leak_test():
    print("\n--- TEST 68: CONNECTION POOL LEAK TEST (1,000 DB OPERATIONS) ---")
    num_ops = 1000
    pool_size = engine.pool.size()
    max_overflow = engine.pool._max_overflow
    
    latencies = []
    failures = 0
    
    def db_task(idx: int):
        t0 = time.perf_counter()
        try:
            with SessionLocal() as db:
                from sqlalchemy import text
                res = db.execute(text("SELECT :num AS n"), {"num": idx}).scalar()
                assert res == idx
            lat = (time.perf_counter() - t0) * 1000
            return lat, True
        except Exception:
            return 0.0, False
            
    t_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(db_task, range(num_ops)))
        
    total_elapsed = (time.perf_counter() - t_start) * 1000
    
    for lat, ok in results:
        if ok:
            latencies.append(lat)
        else:
            failures += 1
            
    # Settle time & leak verification
    time.sleep(0.5)
    checked_out = engine.pool.checkedout()
    
    avg_lat = float(np.mean(latencies)) if latencies else 0.0
    p95_lat = float(np.percentile(latencies, 95)) if latencies else 0.0
    
    passed = (failures == 0 and checked_out == 0)
    print("Test 68 Metrics:")
    print(f"  Configured Pool Size: {pool_size}, Max Overflow: {max_overflow}")
    print(f"  Total Operations: {num_ops}")
    print(f"  Failures: {failures}")
    print(f"  Total Time: {total_elapsed:.2f} ms ({num_ops / (total_elapsed/1000):.1f} ops/sec)")
    print(f"  Average Latency: {avg_lat:.2f} ms")
    print(f"  P95 Latency: {p95_lat:.2f} ms")
    print(f"  Checked-out Connections Remaining: {checked_out} (Leaks = {checked_out})")
    print(f"  PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    return passed


async def test_69_concurrent_mixed_workload():
    print("\n--- TEST 69: CONCURRENT MIXED WORKLOAD (100 CONCURRENT REQUESTS) ---")
    
    # 1. Setup seed cache item
    seed_q = "What is Portgas D. Ace's epithet in One Piece? #bench_69"
    seed_ans = "Fire Fist Ace (Hiken no Ace)!"
    seed_key = normalize_prompt(seed_q)
    seed_vec = [0.08] * 768
    seed_vec[0] = 0.99
    
    with SessionLocal() as db:
        rec = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == seed_key).first()
        if not rec:
            rec = QueryCacheModel(prompt_normalized=seed_key, response=seed_ans, embedding=seed_vec, hit_count=1)
            db.add(rec)
        db.commit()
        
    response_cache._memory_cache[seed_key] = {
        "response": seed_ans,
        "tool_executed": None,
        "cached": True,
        "source": "in_memory"
    }
    
    # Seed vector
    vstore = PostgresVectorStore(collection_name="bench_mix_69")
    vstore.add_documents([{"text": "Hiken no Ace", "metadata": {"tag": "69"}}], [seed_vec], collection_name="bench_mix_69")
    
    tasks = []
    
    # 20 Exact Hits
    for i in range(20):
        tasks.append(chat_service.execute_chat(message=seed_q, session_id=f"mix_exact_{i}"))
        
    # 20 Normalized Hits
    for i in range(20):
        tasks.append(chat_service.execute_chat(message=f"   {seed_q.upper()}   ", session_id=f"mix_norm_{i}"))
        
    # 15 Lexical Hits
    for i in range(15):
        tasks.append(chat_service.execute_chat(message=f"{seed_q} indeed", session_id=f"mix_lex_{i}"))
        
    # 15 DB Reads
    async def db_read_task():
        loop = asyncio.get_event_loop()
        def _read():
            with SessionLocal() as db:
                from sqlalchemy import text
                return db.execute(text("SELECT COUNT(*) FROM conversations")).scalar()
        return await loop.run_in_executor(None, _read)
        
    for _ in range(15):
        tasks.append(db_read_task())
        
    # 15 DB Writes
    async def db_write_task(idx):
        loop = asyncio.get_event_loop()
        def _write():
            with SessionLocal() as db:
                rec = ConversationModel(session_id="mix_write_sess", role="user", content=f"Write turn #{idx}")
                db.add(rec)
                db.commit()
                return rec.id
        return await loop.run_in_executor(None, _write)
        
    for i in range(15):
        tasks.append(db_write_task(i))
        
    # 15 Vector Searches
    async def vsearch_task():
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: vstore.search_similarity(seed_vec, top_k=3, collection_name="bench_mix_69"))
        
    for _ in range(15):
        tasks.append(vsearch_task())
        
    assert len(tasks) == 100, f"Expected 100 tasks, got {len(tasks)}"
    
    print(f"Launching {len(tasks)} concurrent operations across all tiers...")
    t0 = time.perf_counter()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total_elapsed = (time.perf_counter() - t0) * 1000
    
    successes = sum(1 for r in results if not isinstance(r, Exception))
    failures = len(tasks) - successes
    
    # Settle
    time.sleep(0.5)
    checked_out = engine.pool.checkedout()
    
    # Cleanup
    with SessionLocal() as db:
        db.query(ConversationModel).filter(ConversationModel.session_id == "mix_write_sess").delete()
        db.commit()
    vstore.clear_collection("bench_mix_69")
    
    passed = (successes == 100 and checked_out == 0)
    print("Test 69 Metrics:")
    print(f"  Total Concurrent Operations: {len(tasks)}")
    print(f"  Successes: {successes}")
    print(f"  Failures: {failures}")
    print(f"  Total Wall Clock: {total_elapsed:.2f} ms")
    print(f"  Average Latency per Op: {total_elapsed / len(tasks):.2f} ms")
    print(f"  Checked-out Connections: {checked_out}")
    print(f"  PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    return passed


def test_70_system_soak_test():
    print("\n--- TEST 70: SYSTEM SOAK TEST ---")
    # Multi-cycle soak simulation across 5 intervals: 0% (start), 25%, 50%, 75%, 100%
    intervals = ["start (0%)", "25%", "50%", "75%", "100% (end)"]
    soak_metrics = []
    
    process = psutil.Process(os.getpid())
    
    for stage in intervals:
        # Run a burst of 20 mixed queries in each cycle
        burst_tasks = []
        for i in range(10):
            response_cache.get(f"Soak query #{i}")
        for i in range(5):
            add_message(sender="user", message=f"Soak turn #{i}", session_id="soak_sess")
            
        mem_mb = process.memory_info().rss / (1024 * 1024)
        cpu_pct = process.cpu_percent(interval=0.1)
        conns = engine.pool.checkedout()
        cache_size = len(response_cache._memory_cache)
        
        with SessionLocal() as db:
            row_count = db.query(ConversationModel).count()
            
        stage_record = {
            "stage": stage,
            "memory_rss_mb": round(mem_mb, 2),
            "cpu_percent": round(cpu_pct, 1),
            "checked_out_conns": conns,
            "cache_size": cache_size,
            "conversations_row_count": row_count
        }
        soak_metrics.append(stage_record)
        print(f"  [{stage:11s}] Mem: {mem_mb:6.1f} MB | CPU: {cpu_pct:4.1f}% | DB Conns: {conns} | Cache: {cache_size} | DB Rows: {row_count}")
        time.sleep(0.5)
        
    # Cleanup soak conversation rows
    with SessionLocal() as db:
        db.query(ConversationModel).filter(ConversationModel.session_id == "soak_sess").delete()
        db.commit()
        
    # Verify no unbounded memory growth and zero leaked connections
    mem_delta = soak_metrics[-1]["memory_rss_mb"] - soak_metrics[0]["memory_rss_mb"]
    no_leaks = (soak_metrics[-1]["checked_out_conns"] == 0)
    passed = (mem_delta < 150.0 and no_leaks)
    
    print(f"Soak Summary: Memory Delta = {mem_delta:+.2f} MB, Leaked Connections = {soak_metrics[-1]['checked_out_conns']}")
    print(f"  PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    return soak_metrics, passed

if __name__ == "__main__":
    test_66_vector_search_accuracy_at_scale()
    test_67_vector_search_performance_regression()
    test_68_connection_pool_leak_test()
    asyncio.run(test_69_concurrent_mixed_workload())
    test_70_system_soak_test()
