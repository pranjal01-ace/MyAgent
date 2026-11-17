"""
Benchmark Suite Final C: Persistence, Concurrency & Data Integrity
- Test 56: Cache Persistence Across Process Restart
- Test 57: Memory Cache Restart Behavior
- Test 58: Conversation Isolation Under Concurrency (20 sessions x 5 messages)
- Test 59: Conversation History Under Extreme Load (100, 500, 1,000, 5,000 messages)
- Test 60: Unicode / International Input (Hindi, Hindi+English, Chinese, Arabic, Emojis)
"""

import sys
import os
import time
import subprocess
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.agent.cache import response_cache, normalize_prompt
from backend.memory.database import SessionLocal, QueryCacheModel, ConversationModel, engine
from backend.memory.conversation import add_message, get_recent_messages, get_budgeted_messages
from voice_assistant.rag.embeddings import OllamaEmbeddingGenerator

emb_gen = OllamaEmbeddingGenerator()

def test_56_and_57_cache_restart_persistence():
    print("\n--- TESTS 56 & 57: CACHE PERSISTENCE & MEMORY RESTART BEHAVIOR ---")
    unique_id = f"proc_restart_{int(time.time()*1000)}"
    query = f"Who was the navigator of the Spade Pirates before joining Whitebeard? #{unique_id}"
    expected_ans = f"Kotatsu the lynx and Mihar were aboard the Spade Pirates with Ace! [{unique_id}]"
    norm_key = normalize_prompt(query)
    
    # Subprocess 1: Write directly to DB cache and in-memory cache, then exit
    writer_code = f"""
import sys, os
sys.path.insert(0, r"{os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))}")
from backend.memory.database import SessionLocal, QueryCacheModel
from backend.agent.cache import normalize_prompt

db = SessionLocal()
rec = QueryCacheModel(
    prompt_normalized=normalize_prompt({json.dumps(query)}),
    response={json.dumps(expected_ans)},
    hit_count=1
)
db.add(rec)
db.commit()
db.close()
print("SUBPROCESS_1_COMMITTED")
"""
    t0 = time.perf_counter()
    p1 = subprocess.run(
        [sys.executable, "-c", writer_code],
        capture_output=True,
        text=True,
        check=True
    )
    t1_elapsed = (time.perf_counter() - t0) * 1000
    p1_confirmed = "SUBPROCESS_1_COMMITTED" in p1.stdout
    
    # Subprocess 2: Fresh Python process (Clean memory cache) retrieves the cached response
    reader_code = f"""
import sys, os, time, json
sys.path.insert(0, r"{os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))}")
from backend.agent.cache import response_cache

# Confirm memory cache starts empty in new process
mem_len_before = len(response_cache._memory_cache)

t0 = time.perf_counter()
hit = response_cache.get({json.dumps(query)})
lat = (time.perf_counter() - t0) * 1000

print(json.dumps({{
    "mem_len_before": mem_len_before,
    "hit_source": hit.get("source") if hit else None,
    "response": hit.get("response") if hit else None,
    "latency_ms": lat
}}))
"""
    p2 = subprocess.run(
        [sys.executable, "-c", reader_code],
        capture_output=True,
        text=True,
        check=True
    )
    # Filter output to find json
    lines = [line.strip() for line in p2.stdout.splitlines() if line.strip().startswith("{")]
    reader_data = json.loads(lines[-1]) if lines else {}
    
    # Cleanup DB test row
    with SessionLocal() as db:
        db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == norm_key).delete()
        db.commit()
        
    test_56_pass = (p1_confirmed and reader_data.get("hit_source") == "exact_cache" and reader_data.get("response") == expected_ans)
    test_57_pass = (reader_data.get("mem_len_before") == 0 and reader_data.get("hit_source") == "exact_cache")
    
    print(f"Test 56 (Restart Persistence):")
    print(f"  Subprocess 1 committed: {p1_confirmed} ({t1_elapsed:.2f} ms)")
    print(f"  Subprocess 2 hit source: {reader_data.get('hit_source')} ({reader_data.get('latency_ms', 0):.2f} ms)")
    print(f"  PASS/FAIL: {'PASS' if test_56_pass else 'FAIL'}")
    
    print(f"Test 57 (Memory Cache Restart Behavior):")
    print(f"  Process 2 Initial Memory Size: {reader_data.get('mem_len_before')} (Memory wiped)")
    print(f"  Retrieved from PostgreSQL: {reader_data.get('hit_source') == 'exact_cache'}")
    print(f"  PASS/FAIL: {'PASS' if test_57_pass else 'FAIL'}")
    
    return test_56_pass, test_57_pass


def test_58_conversation_isolation_under_concurrency():
    print("\n--- TEST 58: CONVERSATION ISOLATION UNDER CONCURRENCY ---")
    # 20 distinct sessions x 5 messages each = 100 messages
    num_sessions = 20
    num_msgs_per_session = 5
    sessions = [f"bench_iso_sess_{i}_{int(time.time())}" for i in range(num_sessions)]
    
    print(f"Dispatching 100 messages across {num_sessions} concurrent sessions...")
    
    def worker(session_id: str, msg_idx: int):
        role = "user" if msg_idx % 2 == 0 else "assistant"
        msg_text = f"Message #{msg_idx} for private session {session_id} - SecretToken={session_id}_X{msg_idx}"
        add_message(sender=role, message=msg_text, session_id=session_id)
        return session_id, msg_text
        
    tasks = []
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(worker, sid, mid)
            for sid in sessions
            for mid in range(num_msgs_per_session)
        ]
        for f in futures:
            tasks.append(f.result())
            
    insert_latency = (time.perf_counter() - t0) * 1000
    
    # Verify retrieval isolation for every single session
    cross_session_leaks = 0
    total_retrieved = 0
    t_verify0 = time.perf_counter()
    
    for sid in sessions:
        history = get_recent_messages(limit=30, session_id=sid)
        total_retrieved += len(history)
        for h in history:
            content = h.get("content", "")
            # Verify content strictly belongs to this session_id
            if sid not in content:
                cross_session_leaks += 1
                print(f"LEAK DETECTED: Session {sid} received: '{content}'")
                
    verify_latency = (time.perf_counter() - t_verify0) * 1000
    
    # Cleanup DB test rows
    with SessionLocal() as db:
        db.query(ConversationModel).filter(ConversationModel.session_id.in_(sessions)).delete(synchronize_session=False)
        db.commit()
        
    pass_status = (cross_session_leaks == 0 and total_retrieved == num_sessions * num_msgs_per_session)
    print("Test 58 Metrics:")
    print(f"  Sessions Tested: {num_sessions}")
    print(f"  Messages Created: {len(tasks)}")
    print(f"  Messages Retrieved: {total_retrieved}")
    print(f"  Cross-session Contamination: {cross_session_leaks}")
    print(f"  Insert Latency: {insert_latency:.2f} ms")
    print(f"  Verify Latency: {verify_latency:.2f} ms")
    print(f"  PASS/FAIL: {'PASS' if pass_status else 'FAIL'}")
    return pass_status


def test_59_conversation_history_under_extreme_load():
    print("\n--- TEST 59: CONVERSATION HISTORY UNDER EXTREME LOAD ---")
    budgets_test = [100, 500, 1000, 5000]
    results = []
    
    for count in budgets_test:
        sid = f"bench_load_{count}_{int(time.time()*1000)}"
        
        # Batch insert into DB
        with SessionLocal() as db:
            records = [
                ConversationModel(
                    session_id=sid,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"Message turn #{i:04d}: Ace wields flames with intense power and protects Luffy fiercely."
                )
                for i in range(count)
            ]
            db.bulk_save_objects(records)
            db.commit()
            
        t0 = time.perf_counter()
        budgeted = get_budgeted_messages(session_id=sid, max_tokens=1200, max_count=count)
        lat = (time.perf_counter() - t0) * 1000
        
        # Verify ordering and token budget
        est_tokens = sum(len(m["content"]) // 4 for m in budgeted)
        newest_preserved = (budgeted[-1]["content"] == f"Message turn #{count-1:04d}: Ace wields flames with intense power and protects Luffy fiercely.") if budgeted else False
        
        passed = (len(budgeted) <= count and newest_preserved and est_tokens <= 1250)
        results.append({
            "input_messages": count,
            "retained_messages": len(budgeted),
            "discarded_messages": count - len(budgeted),
            "estimated_tokens": est_tokens,
            "newest_preserved": newest_preserved,
            "latency_ms": lat,
            "pass": passed
        })
        
        # Cleanup
        with SessionLocal() as db:
            db.query(ConversationModel).filter(ConversationModel.session_id == sid).delete()
            db.commit()
        
    all_pass = all(r["pass"] for r in results)
    print("Test 59 Results:")
    for r in results:
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['input_messages']} msgs -> retained {r['retained_messages']} ({r['estimated_tokens']} toks, {r['latency_ms']:.3f} ms)")
    print(f"  PASS/FAIL: {'PASS' if all_pass else 'FAIL'}")
    return results, all_pass


def test_60_unicode_and_international_input():
    print("\n--- TEST 60: UNICODE & INTERNATIONAL INPUT VALIDATION ---")
    test_inputs = [
        ("Hindi", "Python में garbage collection कैसे काम करता है?", "पायथन में कचरा संग्रह संदर्भ गणना और चक्रीय जीसी का उपयोग करता है।"),
        ("English + Hindi", "Can you explain Mera Mera no Mi की शक्तियां?", "Mera Mera no Mi आग की Logia-type शक्ति प्रदान करता है!"),
        ("Emojis", "🔥 Portgas D. Ace 🏴‍☠️ Dai Enkai: Entei! 💥", "Fire Fist Ace unleashes the ultimate flame command! 🔥"),
        ("Chinese", "波特卡斯·D·艾斯是白胡子海贼团第二队队长吗？", "是的，艾斯是白胡子海贼团的第二队队长。"),
        ("Arabic", "من هو بورتغاس دي إيس في ون بيس؟", "إيس هو الأخ الأكبر للوفي وقائد الفرقة الثانية لقراصنة اللحية البيضاء."),
        ("Accented / French", "Comment fonctionne la mémoire virtuelle et l'adressage paginé?", "La mémoire virtuelle utilise la pagination et la table des pages."),
        ("Unicode Punctuation", "«Ace»—le poing ardent… ¡fuego total! ¿verdad?", "¡Exactamente! Ace est le feu incarné.")
    ]
    
    results = []
    for lang, prompt, expected_ans in test_inputs:
        t0 = time.perf_counter()
        
        # 1. Test normalization
        norm = normalize_prompt(prompt)
        assert len(norm) > 0, "Normalization produced empty string"
        
        # 2. Test PostgreSQL Persistence
        with SessionLocal() as db:
            rec = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == norm).first()
            if not rec:
                rec = QueryCacheModel(prompt_normalized=norm, response=expected_ans, hit_count=1)
                db.add(rec)
            else:
                rec.response = expected_ans
            db.commit()
            
        # 3. Test Retrieval from DB
        response_cache._memory_cache.clear()
        hit = response_cache.get(prompt)
        lat = (time.perf_counter() - t0) * 1000
        
        passed = (hit is not None and hit["response"] == expected_ans)
        results.append({
            "language": lang,
            "prompt": prompt,
            "normalized": norm,
            "retrieved": hit is not None,
            "latency_ms": lat,
            "pass": passed
        })
        
    # Cleanup DB test rows
    with SessionLocal() as db:
        for _, p, _ in test_inputs:
            db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == normalize_prompt(p)).delete()
        db.commit()
        
    all_pass = all(r["pass"] for r in results)
    print("Test 60 Results:")
    for r in results:
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['language']}: retrieved={r['retrieved']} ({r['latency_ms']:.2f} ms)")
    print(f"  PASS/FAIL: {'PASS' if all_pass else 'FAIL'}")
    return results, all_pass

if __name__ == "__main__":
    test_56_and_57_cache_restart_persistence()
    test_58_conversation_isolation_under_concurrency()
    test_59_conversation_history_under_extreme_load()
    test_60_unicode_and_international_input()
