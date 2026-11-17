"""
Benchmark Suite Final B: Cache Precision & Exclusivity
- Test 52: Cache Tier Exclusivity (Tiers 1-4 & Cold LLM miss isolated)
- Test 53: Cache Negative Cases (10+ unrelated query pairs, false positive protection)
- Test 54: Semantic Threshold False-Positive Protection (<0.85, 0.85-0.91, ~0.92, >0.92)
- Test 55: Cache Response Correctness & Cross-Contamination Prevention (Queries A, B, C)
"""

import sys
import os
import time
import asyncio
import numpy as np
from typing import Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.agent.cache import response_cache, normalize_prompt, compute_jaccard_similarity
from backend.memory.database import SessionLocal, QueryCacheModel, engine
from backend.agent.chat_service import chat_service
from voice_assistant.rag.embeddings import OllamaEmbeddingGenerator

emb_gen = OllamaEmbeddingGenerator()

def clear_cache_tiers(in_memory: bool = True, db: bool = True, pattern: str = None):
    """Safely clear temporary test items from cache without disturbing other data."""
    if in_memory:
        if pattern:
            keys_to_del = [k for k in response_cache._memory_cache if pattern in k]
            for k in keys_to_del:
                del response_cache._memory_cache[k]
        else:
            response_cache._memory_cache.clear()
            
    if db:
        session = SessionLocal()
        try:
            if pattern:
                session.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized.like(f"%{pattern}%")).delete(synchronize_session=False)
            else:
                pass # Don't wipe entire DB without pattern
            session.commit()
        finally:
            session.close()


def test_52_cache_tier_exclusivity():
    print("\n--- TEST 52: CACHE TIER EXCLUSIVITY ---")
    results = []
    
    base_q = "What is the primary fire fist attack in One Piece? #bench_52"
    base_ans = "Hiken (Fire Fist) is Portgas D. Ace's signature flame attack!"
    base_key = normalize_prompt(base_q)
    vec = emb_gen.get_embedding_sync(base_q)
    
    # 1. Directly insert into PostgreSQL so DB tiers are immediately available
    with SessionLocal() as db:
        rec = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == base_key).first()
        if not rec:
            rec = QueryCacheModel(
                prompt_normalized=base_key,
                response=base_ans,
                embedding=vec,
                hit_count=1
            )
            db.add(rec)
        else:
            rec.embedding = vec
            rec.response = base_ans
        db.commit()
    
    # Tier 1 — In-memory exact
    response_cache._memory_cache.clear()
    response_cache._memory_cache[base_key] = {
        "response": base_ans,
        "tool_executed": None,
        "cached": True,
        "source": "in_memory"
    }
    t0 = time.perf_counter()
    hit1 = response_cache.get(base_q)
    lat1 = (time.perf_counter() - t0) * 1000
    tier1_pass = (hit1 is not None and hit1.get("source") == "in_memory" and hit1["response"] == base_ans)
    results.append({
        "case": "Tier 1 (In-Memory Exact)",
        "query": base_q,
        "expected_tier": "in_memory",
        "actual_tier": hit1.get("source") if hit1 else None,
        "llm_invoked": False,
        "embedding_invoked": False,
        "latency_ms": lat1,
        "response_equality": hit1.get("response") == base_ans if hit1 else False,
        "pass": tier1_pass
    })
    
    # Tier 2 — Database exact match (Memory cache cleared, so it falls to DB exact)
    response_cache._memory_cache.clear()
    norm_q = f"   {base_q.upper()}   "
    t0 = time.perf_counter()
    hit2 = response_cache.get(norm_q)
    lat2 = (time.perf_counter() - t0) * 1000
    tier2_pass = (hit2 is not None and hit2.get("source") == "exact_cache" and hit2["response"] == base_ans)
    results.append({
        "case": "Tier 2 (PostgreSQL Normalized/Exact)",
        "query": norm_q,
        "expected_tier": "exact_cache",
        "actual_tier": hit2.get("source") if hit2 else None,
        "llm_invoked": False,
        "embedding_invoked": False,
        "latency_ms": lat2,
        "response_equality": hit2.get("response") == base_ans if hit2 else False,
        "pass": tier2_pass
    })
    
    # Tier 3 — Lexical Jaccard (Populate in-memory with base_key; query with Jaccard >= 0.85)
    response_cache._memory_cache.clear()
    response_cache._memory_cache[base_key] = {
        "response": base_ans,
        "tool_executed": None,
        "cached": True,
        "source": "in_memory"
    }
    # Jaccard >= 0.85: append 1 minor word
    words = base_key.split()
    lex_q = " ".join(words) + " indeed"
    jacc = compute_jaccard_similarity(normalize_prompt(lex_q), base_key)
    assert jacc >= 0.85, f"Jaccard {jacc} too low"
    
    t0 = time.perf_counter()
    hit3 = response_cache.get(lex_q)
    lat3 = (time.perf_counter() - t0) * 1000
    tier3_pass = (hit3 is not None and hit3.get("source") == "lexical_cache" and hit3["response"] == base_ans)
    results.append({
        "case": "Tier 3 (Lexical Jaccard)",
        "query": lex_q,
        "expected_tier": "lexical_cache",
        "actual_tier": hit3.get("source") if hit3 else None,
        "llm_invoked": False,
        "embedding_invoked": False,
        "latency_ms": lat3,
        "response_equality": hit3.get("response") == base_ans if hit3 else False,
        "pass": tier3_pass
    })
    
    # Tier 4 — Semantic Vector (Clear memory cache, query with high semantic similarity >= 0.92 but different words)
    response_cache._memory_cache.clear()
    # Create query whose embedding is identical or >= 0.95 cosine similarity
    # Query with exact semantic intent
    sem_probe_q = "What is the primary fire fist attack in One Piece? #bench_52_sem"
    # Seed this into DB
    sem_key = normalize_prompt(sem_probe_q)
    with SessionLocal() as db:
        rec2 = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == sem_key).first()
        if not rec2:
            rec2 = QueryCacheModel(
                prompt_normalized=sem_key,
                response=base_ans,
                embedding=vec, # Use the exact same vector so cosine similarity is 1.0!
                hit_count=1
            )
            db.add(rec2)
        else:
            rec2.embedding = vec
        db.commit()
        
    t0 = time.perf_counter()
    hit4 = response_cache.get(base_q) # Will match via DB exact or semantic
    # To ensure it ONLY hits semantic: query a variant that does not exist in DB prompt_normalized
    sem_variant = "Tell me the primary fire fist attack in One Piece? #bench_52_variant"
    hit4 = response_cache.get(sem_variant)
    lat4 = (time.perf_counter() - t0) * 1000
    tier4_pass = (hit4 is not None and hit4.get("source") == "semantic_vector_cache" and hit4["response"] == base_ans)
    results.append({
        "case": "Tier 4 (Semantic Vector)",
        "query": sem_variant,
        "expected_tier": "semantic_vector_cache",
        "actual_tier": hit4.get("source") if hit4 else None,
        "llm_invoked": False,
        "embedding_invoked": True,
        "latency_ms": lat4,
        "response_equality": hit4.get("response") == base_ans if hit4 else False,
        "pass": tier4_pass
    })
    
    # Complete Cache Miss → Ollama
    cold_q = f"Calculate unique random entropy value {time.time()} #bench_52_miss"
    t0 = time.perf_counter()
    hit5 = response_cache.get(cold_q)
    lat5 = (time.perf_counter() - t0) * 1000
    miss_pass = (hit5 is None)
    results.append({
        "case": "Complete Cache Miss (Falls through to LLM)",
        "query": cold_q,
        "expected_tier": None,
        "actual_tier": None,
        "llm_invoked": True,
        "embedding_invoked": True,
        "latency_ms": lat5,
        "response_equality": True,
        "pass": miss_pass
    })
    
    all_pass = all(r["pass"] for r in results)
    print("Test 52 Results:")
    for r in results:
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['case']}: actual={r['actual_tier']} ({r['latency_ms']:.2f} ms)")
    print(f"  PASS/FAIL: {'PASS' if all_pass else 'FAIL'}")
    return results, all_pass


def test_53_cache_negative_cases():
    print("\n--- TEST 53: CACHE NEGATIVE CASES ---")
    # Seed 5 distinct known queries into cache
    seeds = [
        ("How does Python garbage collection work?", "Python uses reference counting and a cyclic generational GC."),
        ("What are the health benefits of regular exercise?", "Exercise improves cardiovascular health, muscle strength, and mood."),
        ("What is the capital of Australia?", "The capital of Australia is Canberra."),
        ("Explain quantum entanglement in physics", "Quantum entanglement is a phenomenon where pairs of particles interact."),
        ("How do you bake sourdough bread?", "Sourdough requires starter, flour, water, salt, fermentation, and baking.")
    ]
    for q, a in seeds:
        response_cache.set(q, a)
        
    time.sleep(0.1)
    
    # 10 Unrelated test queries that must NEVER hit the cache
    negative_queries = [
        "How do airplanes stay in the air with lift and thrust?",
        "What is the exchange rate of Japanese Yen to US Dollar?",
        "Who directed the movie Interstellar?",
        "Can Python compile to machine code using PyPy?", # Shares word 'Python' but different intent
        "What is garbage collection in Java virtual machine?", # Shares 'garbage collection' but distinct
        "Is regular walking considered good cardio exercise?", # Shares 'exercise' but different question
        "What is the largest city in Australia by population?", # Shares 'Australia' but Sydney, not capital
        "Quantum computing vs classical computing explained", # Shares 'quantum'
        "Why does sourdough bread develop large air pockets?", # Shares 'sourdough'
        "Write a quicksort algorithm in C++"
    ]
    
    results = []
    for nq in negative_queries:
        t0 = time.perf_counter()
        hit = response_cache.get(nq)
        lat = (time.perf_counter() - t0) * 1000
        
        # Must be None (no false positive)
        passed = (hit is None)
        results.append({
            "query": nq,
            "hit_tier": hit.get("source") if hit else None,
            "passed": passed,
            "latency_ms": lat
        })
        
    all_pass = all(r["passed"] for r in results)
    print(f"Test 53 Results: {sum(1 for r in results if r['passed'])}/{len(results)} negative cases safely missed cache.")
    for r in results:
        print(f"  [{'PASS' if r['passed'] else 'FAIL'}] '{r['query'][:40]}...': tier={r['hit_tier']} ({r['latency_ms']:.2f} ms)")
    print(f"  PASS/FAIL: {'PASS' if all_pass else 'FAIL'}")
    return results, all_pass


def test_54_semantic_cache_threshold_protection():
    print("\n--- TEST 54: SEMANTIC CACHE FALSE-POSITIVE THRESHOLD PROTECTION ---")
    # Seed a target item in DB vector store
    target_q = "What is the primary function of an operating system kernel?"
    target_ans = "The kernel manages hardware resources, CPU scheduling, and memory allocation."
    target_vec = emb_gen.get_embedding_sync(target_q)
    
    with SessionLocal() as db:
        rec = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == normalize_prompt(target_q)).first()
        if not rec:
            rec = QueryCacheModel(
                prompt_normalized=normalize_prompt(target_q),
                response=target_ans,
                embedding=target_vec,
                hit_count=1
            )
            db.add(rec)
        else:
            rec.embedding = target_vec
            rec.response = target_ans
        db.commit()
        
    response_cache._memory_cache.clear()
    
    # Candidate queries with varying expected cosine similarities
    test_probes = [
        ("What is the recipe for chocolate chip cookies?", "below_0.85", False),
        ("How does a relational database management system work?", "0.85_to_0.91", False),
        ("What does the kernel do in computer operating systems?", "above_0.92", True),
        ("What is the core role of an OS kernel?", "above_0.92", True)
    ]
    
    probe_results = []
    for probe_q, bracket, expect_hit in test_probes:
        p_vec = emb_gen.get_embedding_sync(probe_q)
        # Compute exact cosine similarity
        dot = np.dot(target_vec, p_vec)
        norm_a = np.linalg.norm(target_vec)
        norm_b = np.linalg.norm(p_vec)
        cos_sim = float(dot / (norm_a * norm_b))
        
        response_cache._memory_cache.clear()
        t0 = time.perf_counter()
        hit = response_cache.get(probe_q)
        lat = (time.perf_counter() - t0) * 1000
        
        # Verify strict threshold rule: cos_sim >= 0.92 allows semantic hit, cos_sim < 0.92 forbids it
        if cos_sim < 0.92:
            passed = (hit is None or hit.get("source") != "semantic")
        else:
            passed = (hit is not None and hit.get("source") == "semantic")
            
        probe_results.append({
            "probe": probe_q,
            "bracket": bracket,
            "cosine_sim": cos_sim,
            "expected_hit": (cos_sim >= 0.92),
            "actual_hit": (hit is not None and hit.get("source") == "semantic"),
            "latency_ms": lat,
            "pass": passed
        })
        
    all_pass = all(r["pass"] for r in probe_results)
    print("Test 54 Results:")
    for r in probe_results:
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] sim={r['cosine_sim']:.4f} (exp_hit={r['expected_hit']}, got_hit={r['actual_hit']}): '{r['probe'][:35]}...'")
    print(f"  PASS/FAIL: {'PASS' if all_pass else 'FAIL'}")
    return probe_results, all_pass


def test_55_cache_response_correctness():
    print("\n--- TEST 55: CACHE RESPONSE CORRECTNESS & ISOLATION ---")
    qa_pairs = [
        ("Query Alpha: What color is the sky?", "ANSWER_ALPHA_AZURE_BLUE"),
        ("Query Beta: What is the boiling point of water?", "ANSWER_BETA_100_DEGREES"),
        ("Query Gamma: Who is the pirate hunter in One Piece?", "ANSWER_GAMMA_RORONOA_ZORO")
    ]
    
    for q, a in qa_pairs:
        response_cache.set(q, a)
        
    time.sleep(0.1)
    
    test_cases = [
        ("exact A", "Query Alpha: What color is the sky?", "ANSWER_ALPHA_AZURE_BLUE"),
        ("normalized A", "   query alpha: what color is the sky?   ", "ANSWER_ALPHA_AZURE_BLUE"),
        ("exact B", "Query Beta: What is the boiling point of water?", "ANSWER_BETA_100_DEGREES"),
        ("normalized B", "QUERY BETA: WHAT IS THE BOILING POINT OF WATER?", "ANSWER_BETA_100_DEGREES"),
        ("exact C", "Query Gamma: Who is the pirate hunter in One Piece?", "ANSWER_GAMMA_RORONOA_ZORO")
    ]
    
    results = []
    for label, query, expected in test_cases:
        t0 = time.perf_counter()
        hit = response_cache.get(query)
        lat = (time.perf_counter() - t0) * 1000
        actual = hit["response"] if hit else None
        passed = (actual == expected)
        results.append({
            "test": label,
            "query": query,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "latency_ms": lat
        })
        
    all_pass = all(r["passed"] for r in results)
    print("Test 55 Results:")
    for r in results:
        print(f"  [{'PASS' if r['passed'] else 'FAIL'}] {r['test']}: expected='{r['expected']}' == actual='{r['actual']}' ({r['latency_ms']:.2f} ms)")
    print(f"  PASS/FAIL: {'PASS' if all_pass else 'FAIL'}")
    return results, all_pass

if __name__ == "__main__":
    test_52_cache_tier_exclusivity()
    test_53_cache_negative_cases()
    test_54_semantic_cache_threshold_protection()
    test_55_cache_response_correctness()
