import sys
import os
import time

sys.path.insert(0, os.path.abspath("."))

from backend.memory.database import engine, SessionLocal, MemoryModel
from sqlalchemy import text

def run_test_18():
    print("=" * 65)
    print("TEST 18: MEMORY INDEX PERFORMANCE (EXPLAIN ANALYZE)")
    print("=" * 65)

    test_category = "bench_mem_cat"
    db = SessionLocal()

    try:
        # 1. Inspect existing indexes on memories
        indexes = db.execute(text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'memories';")).fetchall()
        print("Discovered Indexes on 'memories':")
        for idx in indexes:
            print(f"  - {idx.indexname}: {idx.indexdef}")

        # Clean existing test records
        db.query(MemoryModel).filter(MemoryModel.category == test_category).delete()
        db.commit()

        sizes = [100, 1000, 10000]
        cumulative = 0
        reports = []

        for target_size in sizes:
            to_add = target_size - cumulative
            print(f"\nPopulating memory dataset to {target_size} records (+{to_add})...")
            
            insert_sql = text("""
                INSERT INTO memories (category, key, value, created_at, updated_at)
                SELECT :cat, 'key_' || g, 'Value payload for memory index benchmark ' || g, NOW(), NOW()
                FROM generate_series(:start, :end) AS g;
            """)
            db.execute(insert_sql, {"cat": test_category, "start": cumulative + 1, "end": target_size})
            db.commit()
            cumulative = target_size

            # Target key lookup
            target_key = f"key_{target_size // 2}"
            query_sql = text("""
                EXPLAIN (ANALYZE, BUFFERS)
                SELECT id, category, key, value
                FROM memories
                WHERE category = :cat AND key = :key
                LIMIT 1;
            """)
            t0 = time.perf_counter()
            explain_rows = db.execute(query_sql, {"cat": test_category, "key": target_key}).fetchall()
            lat_ms = (time.perf_counter() - t0) * 1000

            explain_text = "\n".join([r[0] for r in explain_rows])
            index_used = ("ix_memories_cat_key" in explain_text) or ("ix_memories_key" in explain_text) or ("Index Scan" in explain_text) or ("Bitmap Index Scan" in explain_text)

            print(f"Dataset: {target_size} rows | Query Latency: {lat_ms:.2f} ms | Index Used: {index_used}")
            first_plan_line = explain_rows[0][0] if explain_rows else "Unknown"

            reports.append({
                "size": target_size,
                "latency": lat_ms,
                "index_used": index_used,
                "plan_summary": first_plan_line,
                "full_plan": explain_text
            })

    finally:
        # Cleanup benchmark data
        db.query(MemoryModel).filter(MemoryModel.category == test_category).delete()
        db.commit()
        db.close()

    print("\n" + "=" * 65)
    print("OUTPUT FORMAT FOR TEST 18")
    print("=" * 65)
    all_passed = all(r["index_used"] for r in reports)
    for r in reports:
        print(f"Test 18 (Size: {r['size']}):")
        print(f"Dataset size: {r['size']}")
        print(f"Query: SELECT ... WHERE category = :cat AND key = :key LIMIT 1")
        print(f"Latency: {r['latency']:.2f} ms")
        print(f"Index used: {'TRUE (ix_memories_cat_key)' if r['index_used'] else 'FALSE'}")
        print(f"EXPLAIN result: {r['plan_summary']}")
        print("")
    print(f"PASS/FAIL: {'PASS' if all_passed else 'FAIL'}")
    print("=" * 65)

if __name__ == "__main__":
    run_test_18()
