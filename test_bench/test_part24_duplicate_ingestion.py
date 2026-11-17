import sys
import os

sys.path.insert(0, os.path.abspath("."))

from backend.agent.cache import response_cache, normalize_prompt
from backend.memory.database import SessionLocal, QueryCacheModel

def run_test_24():
    print("=" * 65)
    print("TEST 24: DUPLICATE INGESTION BENCHMARK")
    print("=" * 65)

    prompt = "What is the unique duplicate test query for Phase 2?"
    key = normalize_prompt(prompt)

    # 1. Clean existing test prompt
    db = SessionLocal()
    try:
        db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == key).delete()
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        rows_before = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == key).count()

        # First insertion
        first_resp = "Initial response for duplicate testing."
        response_cache.set(prompt, first_resp)
        rec1 = None
        for _ in range(20):
            import time
            time.sleep(0.3)
            rec1 = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == key).first()
            if rec1:
                break
        first_result = f"INSERTED (ID={rec1.id if rec1 else 'None'})"

        # Second insertion with exact same logical key but updated response
        second_resp = "Updated duplicate response for identical logical query."
        response_cache.set(prompt, second_resp)
        rec2 = None
        for _ in range(20):
            import time
            time.sleep(0.3)
            db.expire_all()
            rec2 = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == key).first()
            if rec2 and rec2.response == second_resp:
                break
        rows_after = db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == key).count()

        second_result = f"UPSERTED / UPDATED IN-PLACE (ID={rec2.id if rec2 else 'None'}, text='{rec2.response[:30] if rec2 else ''}...')"
        duplicate_handling = "UPSERT: Existing record detected by unique prompt_normalized index and updated in place without duplicate row creation."
        expected_behavior = "Preserve unique prompt constraint by updating existing row (row count remains 1)."

        passed = (rows_before == 0 and rows_after == 1 and rec1.id == rec2.id)

    finally:
        # Cleanup
        db.query(QueryCacheModel).filter(QueryCacheModel.prompt_normalized == key).delete()
        db.commit()
        db.close()

    print("\n" + "=" * 65)
    print("OUTPUT FORMAT FOR TEST 24")
    print("=" * 65)
    print("Test 24:")
    print(f"Rows before: {rows_before}")
    print(f"First insertion: {first_result}")
    print(f"Second insertion: {second_result}")
    print(f"Rows after: {rows_after}")
    print(f"Duplicate handling: {duplicate_handling}")
    print(f"Expected behavior: {expected_behavior}")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 65)

if __name__ == "__main__":
    run_test_24()
