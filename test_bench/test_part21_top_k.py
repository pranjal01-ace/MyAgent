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

def run_test_21():
    print("=" * 65)
    print("TEST 21: TOP_K BEHAVIOR BENCHMARK")
    print("=" * 65)

    coll = "test_topk_coll"
    store = PostgresVectorStore(collection_name=coll)

    db = SessionLocal()
    try:
        db.query(KnowledgeVectorModel).filter(KnowledgeVectorModel.collection_name == coll).delete()
        db.commit()
    finally:
        db.close()

    # Seed 20 distinct vectors
    total_docs = 20
    vecs = generate_random_vectors(total_docs, 768)
    chunks = [{"text": f"Document context payload #{i}", "metadata": {"doc_id": i}} for i in range(1, total_docs + 1)]
    store.add_documents(chunks, vecs, collection_name=coll)
    print(f"Seeded {total_docs} distinct vectors into PostgreSQL.")

    # Generate a random query vector
    query_vec = generate_random_vectors(1, 768)[0]

    top_k_values = [1, 3, 5, 10]
    reports = []

    try:
        for k in top_k_values:
            t0 = time.perf_counter()
            hits = store.search_similarity(query_vec, top_k=k, collection_name=coll)
            lat_ms = (time.perf_counter() - t0) * 1000

            returned_count = len(hits)
            scores = [round(h.get("score", 0.0), 4) for h in hits]
            ids = [h.get("id") for h in hits]
            no_duplicates = (len(ids) == len(set(ids)))
            correct_ordering = all(scores[i] >= scores[i+1] for i in range(len(scores)-1)) if len(scores) > 1 else True

            passed = (returned_count == k and correct_ordering and no_duplicates)
            print(f"top_k={k:2d} | Returned: {returned_count:2d} | Order OK: {correct_ordering} | No Dupes: {no_duplicates} | Latency: {lat_ms:5.2f} ms")

            reports.append({
                "top_k": k,
                "returned": returned_count,
                "scores": scores,
                "correct_ordering": correct_ordering,
                "latency": lat_ms,
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
    print("OUTPUT FORMAT FOR TEST 21")
    print("=" * 65)
    for r in reports:
        print(f"Test 21 (top_k={r['top_k']}):")
        print(f"top_k: {r['top_k']}")
        print(f"Returned count: {r['returned']}")
        print(f"Scores: {r['scores']}")
        print(f"Correct ordering: {'TRUE' if r['correct_ordering'] else 'FALSE'}")
        print(f"Latency: {r['latency']:.2f} ms")
        print(f"PASS/FAIL: {'PASS' if r['passed'] else 'FAIL'}")
        print("")
    print("=" * 65)

if __name__ == "__main__":
    run_test_21()
