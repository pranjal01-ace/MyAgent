import sys
import os
import time
import concurrent.futures
import numpy as np

sys.path.insert(0, os.path.abspath("."))

from backend.memory.database import engine, SessionLocal, ConversationModel
from sqlalchemy import text

def db_query_task(task_id: int):
    t0 = time.perf_counter()
    err = None
    timeout = False
    try:
        db = SessionLocal()
        try:
            # Query actual table with lock-free SELECT
            res = db.query(ConversationModel.id).order_by(ConversationModel.id.desc()).limit(10).all()
        finally:
            db.close()
    except Exception as e:
        err = str(e)
        if "timeout" in err.lower():
            timeout = True
    lat_ms = (time.perf_counter() - t0) * 1000
    return {"id": task_id, "lat_ms": lat_ms, "error": err, "timeout": timeout}

def run_concurrency_batch(concurrency: int):
    print("=" * 65)
    print(f"TEST 15: {concurrency} CONCURRENT DATABASE REQUESTS")
    print("=" * 65)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(db_query_task, i) for i in range(concurrency)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    successful = [r for r in results if r["error"] is None]
    failed = [r for r in results if r["error"] is not None]
    timeouts = [r for r in results if r["timeout"]]
    latencies = [r["lat_ms"] for r in results]

    avg_lat = np.mean(latencies)
    p95_lat = np.percentile(latencies, 95)
    max_lat = np.max(latencies)
    pool_errors = len(failed)

    passed = (len(successful) == concurrency and pool_errors == 0 and len(timeouts) == 0)

    print("\n" + "=" * 65)
    print(f"OUTPUT FORMAT FOR TEST 15 (Concurrency={concurrency})")
    print("=" * 65)
    print("Test 15:")
    print(f"Concurrency: {concurrency}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    print(f"Timeouts: {len(timeouts)}")
    print(f"Average latency: {avg_lat:.2f} ms")
    print(f"P95 latency: {p95_lat:.2f} ms")
    print(f"Maximum latency: {max_lat:.2f} ms")
    print(f"Pool errors: {pool_errors}")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 65)

    return passed

if __name__ == "__main__":
    p1 = run_concurrency_batch(30)
    p2 = run_concurrency_batch(50)
