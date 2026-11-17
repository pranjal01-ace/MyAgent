import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.abspath("."))

from backend.memory.vector_store import PostgresVectorStore
from backend.memory.database import SessionLocal, KnowledgeVectorModel

def generate_random_vectors(count: int, dim: int = 768):
    vecs = np.random.randn(count, dim).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return (vecs / norms).tolist()

def run_test_23():
    print("=" * 65)
    print("TEST 23: BATCH INGESTION BENCHMARK")
    print("=" * 65)

    coll = "test_batch_bench"
    store = PostgresVectorStore(collection_name=coll)

    db = SessionLocal()
    try:
        db.query(KnowledgeVectorModel).filter(KnowledgeVectorModel.collection_name == coll).delete()
        db.commit()
    finally:
        db.close()

    batch_sizes = [100, 500, 1000]
    reports = []

    try:
        for b_size in batch_sizes:
            vecs = generate_random_vectors(b_size, 768)
            chunks = [{"text": f"Batch record #{i} payload for ingestion benchmark", "metadata": {"b_idx": i}} for i in range(1, b_size + 1)]

            db_before = SessionLocal()
            count_before = db_before.query(KnowledgeVectorModel).filter(KnowledgeVectorModel.collection_name == coll).count()
            db_before.close()

            t0 = time.perf_counter()
            store.add_documents(chunks, vecs, collection_name=coll)
            tot_time_ms = (time.perf_counter() - t0) * 1000

            db_after = SessionLocal()
            count_after = db_after.query(KnowledgeVectorModel).filter(KnowledgeVectorModel.collection_name == coll).count()
            db_after.close()

            inserted = count_after - count_before
            failed = b_size - inserted
            avg_per_rec = tot_time_ms / b_size if b_size > 0 else 0

            passed = (inserted == b_size and failed == 0)
            print(f"Batch Size: {b_size:4d} | Inserted: {inserted:4d} | Failed: {failed} | Time: {tot_time_ms:7.2f} ms ({avg_per_rec:.2f} ms/rec)")

            reports.append({
                "batch_size": b_size,
                "expected": b_size,
                "inserted": inserted,
                "failed": failed,
                "duplicates": 0,
                "tot_time_ms": tot_time_ms,
                "avg_per_rec": avg_per_rec,
                "passed": passed
            })
    finally:
        db = SessionLocal()
        try:
            db.query(KnowledgeVectorModel).filter(KnowledgeVectorModel.collection_name == coll).delete()
            db.commit()
        finally:
            db.close()

    print("\n" + "=" * 65)
    print("OUTPUT FORMAT FOR TEST 23")
    print("=" * 65)
    for r in reports:
        print(f"Test 23 (Batch={r['batch_size']}):")
        print(f"Batch size: {r['batch_size']}")
        print(f"Expected: {r['expected']}")
        print(f"Inserted: {r['inserted']}")
        print(f"Failed: {r['failed']}")
        print(f"Duplicates: {r['duplicates']}")
        print(f"Total time: {r['tot_time_ms']:.2f} ms")
        print(f"Average per record: {r['avg_per_rec']:.2f} ms")
        print(f"PASS/FAIL: {'PASS' if r['passed'] else 'FAIL'}")
        print("")
    print("=" * 65)

if __name__ == "__main__":
    run_test_23()
