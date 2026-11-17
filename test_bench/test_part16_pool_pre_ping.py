import sys
import os
import time

sys.path.insert(0, os.path.abspath("."))

from backend.memory.database import engine, SessionLocal
from sqlalchemy import text

def run_test_16():
    print("=" * 65)
    print("TEST 16: STALE CONNECTION / POOL_PRE_PING RECOVERY")
    print(f"Engine pool_pre_ping configured: {getattr(engine.pool, '_pre_ping', False)}")
    print("=" * 65)

    # 1. Initial connection - check out connection 1
    conn1 = engine.connect()
    initial_pid = None
    initial_ok = False
    try:
        res = conn1.execute(text("SELECT 1 AS alive, pg_backend_pid() AS pid;")).first()
        initial_pid = res.pid
        initial_ok = (res.alive == 1)
        print(f"Initial query succeeded on conn1. Backend PID: {initial_pid}")
    except Exception as e:
        print(f"Initial query error: {e}")

    # 2. Open distinct connection 2 and terminate conn1's backend PID
    conn2 = engine.connect()
    stale_simulated = False
    try:
        kill_res = conn2.execute(
            text("SELECT pg_terminate_backend(:pid);"),
            {"pid": initial_pid}
        ).first()
        stale_simulated = bool(kill_res[0])
        print(f"Server-side backend PID {initial_pid} terminated from conn2: {stale_simulated}")
    except Exception as e:
        print(f"Could not terminate backend PID from conn2: {e}")
    finally:
        conn2.close()

    # Close conn1 so its terminated raw socket is returned to the pool
    try:
        conn1.close()
    except Exception:
        pass

    time.sleep(0.3)

    # 3. Subsequent query - pool_pre_ping detects dead connection and seamlessly reconnects
    subsequent_ok = False
    new_pid = None
    app_survived = False
    recovery = False

    try:
        db_sub = SessionLocal()
        try:
            sub_res = db_sub.execute(text("SELECT 1 AS alive, pg_backend_pid() AS pid;")).first()
            new_pid = sub_res.pid
            subsequent_ok = (sub_res.alive == 1)
            app_survived = True
            recovery = (new_pid != initial_pid and subsequent_ok)
            print(f"Subsequent query succeeded seamlessly! New Backend PID: {new_pid}")
        finally:
            db_sub.close()
    except Exception as e:
        app_survived = False
        print(f"Query after termination failed: {e}")

    passed = initial_ok and stale_simulated and recovery and subsequent_ok and app_survived

    print("\n" + "=" * 65)
    print("OUTPUT FORMAT FOR TEST 16")
    print("=" * 65)
    print("Test 16:")
    print(f"Initial connection: {'SUCCESS' if initial_ok else 'FAILED'} (PID={initial_pid})")
    print(f"Stale connection simulated: {'TRUE' if stale_simulated else 'FALSE'} (pg_terminate_backend({initial_pid}))")
    print(f"Recovery: {'SUCCESS' if recovery else 'FAILED'} (new connection PID={new_pid})")
    print(f"Subsequent query: {'SUCCESS' if subsequent_ok else 'FAILED'}")
    print(f"Application survived: {'TRUE' if app_survived else 'FALSE'}")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 65)

if __name__ == "__main__":
    run_test_16()
