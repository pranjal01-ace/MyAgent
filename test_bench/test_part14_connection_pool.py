import sys
import os
import time
import concurrent.futures
import re

sys.path.insert(0, os.path.abspath("."))

from backend.memory.database import engine, SessionLocal
from sqlalchemy import text

def sanitize_url(raw_url: str) -> str:
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", str(raw_url))

def db_worker(worker_id: int):
    db = SessionLocal()
    try:
        res = db.execute(text("SELECT 1 AS alive, pg_backend_pid() AS pid;")).first()
        time.sleep(0.05) # Hold briefly to exercise pool concurrency
        return {"id": worker_id, "alive": res.alive, "pid": res.pid, "error": None}
    except Exception as e:
        return {"id": worker_id, "alive": None, "pid": None, "error": str(e)}
    finally:
        db.close()

def run_test_14():
    pool = engine.pool
    pool_class = pool.__class__.__name__
    pool_size = getattr(pool, "_size", 15)
    max_overflow = getattr(pool, "_max_overflow", 25)
    pool_timeout = getattr(pool, "_timeout", 15)
    pool_recycle = getattr(pool, "_recycle", 1800)
    pool_pre_ping = getattr(pool, "_pre_ping", True)
    sanitized_url = sanitize_url(str(engine.url))

    pool_config_str = (
        f"class={pool_class}, size={pool_size}, max_overflow={max_overflow}, "
        f"timeout={pool_timeout}s, recycle={pool_recycle}s, pre_ping={pool_pre_ping}, "
        f"url={sanitized_url}"
    )

    print("=" * 65)
    print("TEST 14: POSTGRESQL CONNECTION POOL BENCHMARK")
    print(f"Pool Config: {pool_config_str}")
    print("=" * 65)

    num_ops = 30
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(db_worker, i) for i in range(num_ops)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    successful = [r for r in results if r["error"] is None and r["alive"] == 1]
    failed = [r for r in results if r["error"] is not None]
    conn_errors = len(failed)

    # Check connection leaks
    checked_out = pool.checkedout()
    checked_in = pool.checkedin()
    pool_exhaustion = conn_errors > 0 or checked_out > 0

    print(f"Concurrent operations executed: {num_ops}")
    print(f"Successful: {len(successful)}/{num_ops}")
    print(f"Failed: {len(failed)}")
    print(f"Active connections still checked out: {checked_out} (must be 0)")
    print(f"Connections checked in / idle in pool: {checked_in}")

    pids_used = set(r["pid"] for r in successful if r["pid"])
    print(f"Distinct PostgreSQL backend PIDs reused: {len(pids_used)} (Pool size: {pool_size})")

    passed = (len(successful) == num_ops and conn_errors == 0 and checked_out == 0)

    print("\n" + "=" * 65)
    print("OUTPUT FORMAT FOR TEST 14")
    print("=" * 65)
    print("Test 14:")
    print(f"Pool configuration: {pool_config_str}")
    print(f"Concurrent DB operations: {num_ops}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    print(f"Connection errors: {conn_errors}")
    print(f"Pool exhaustion: {'TRUE' if pool_exhaustion else 'FALSE'}")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 65)

if __name__ == "__main__":
    run_test_14()
