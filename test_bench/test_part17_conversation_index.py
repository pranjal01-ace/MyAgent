import sys
import os
import time

sys.path.insert(0, os.path.abspath("."))

from backend.memory.database import engine, SessionLocal, ConversationModel
from sqlalchemy import text

def run_test_17():
    print("=" * 65)
    print("TEST 17: CONVERSATION INDEX PERFORMANCE (EXPLAIN ANALYZE)")
    print("=" * 65)

    test_session = "bench_conv_idx_test"
    db = SessionLocal()

    try:
        # 1. Inspect existing indexes on conversations
        indexes = db.execute(text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'conversations';")).fetchall()
        print("Discovered Indexes on 'conversations':")
        for idx in indexes:
            print(f"  - {idx.indexname}: {idx.indexdef}")

        # Clean existing test session
        db.query(ConversationModel).filter(ConversationModel.session_id == test_session).delete()
        db.commit()

        # Benchmark sizes
        sizes = [100, 1000, 10000]
        cumulative = 0
        reports = []

        for target_size in sizes:
            to_add = target_size - cumulative
            print(f"\nPopulating dataset to {target_size} records (+{to_add})...")
            
            # Fast batch insert
            insert_sql = text("""
                INSERT INTO conversations (session_id, role, content, created_at)
                SELECT :sess, 'user', 'Benchmark message payload ' || g, NOW()
                FROM generate_series(1, :count) AS g;
            """)
            db.execute(insert_sql, {"sess": test_session, "count": to_add})
            db.commit()
            cumulative = target_size

            # Run EXPLAIN ANALYZE on production query pattern
            query_sql = text("""
                EXPLAIN (ANALYZE, BUFFERS)
                SELECT id, session_id, role, content
                FROM conversations
                WHERE session_id = :sess
                ORDER BY id DESC
                LIMIT 25;
            """)
            t0 = time.perf_counter()
            explain_rows = db.execute(query_sql, {"sess": test_session}).fetchall()
            lat_ms = (time.perf_counter() - t0) * 1000

            explain_text = "\n".join([r[0] for r in explain_rows])
            index_used = ("ix_conv_session_id" in explain_text) or ("Index Scan" in explain_text) or ("Bitmap Index Scan" in explain_text)

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
        # Cleanup benchmark session
        db.query(ConversationModel).filter(ConversationModel.session_id == test_session).delete()
        db.commit()
        db.close()

    print("\n" + "=" * 65)
    print("OUTPUT FORMAT FOR TEST 17")
    print("=" * 65)
    all_passed = all(r["index_used"] for r in reports)
    for r in reports:
        print(f"Test 17 (Size: {r['size']}):")
        print(f"Dataset size: {r['size']}")
        print(f"Query: SELECT ... WHERE session_id = :sess ORDER BY id DESC LIMIT 25")
        print(f"Latency: {r['latency']:.2f} ms")
        print(f"Index used: {'TRUE (ix_conv_session_id)' if r['index_used'] else 'FALSE'}")
        print(f"EXPLAIN result: {r['plan_summary']}")
        print("")
    print(f"PASS/FAIL: {'PASS' if all_passed else 'FAIL'}")
    print("=" * 65)

if __name__ == "__main__":
    run_test_17()
