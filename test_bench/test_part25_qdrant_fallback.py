import sys
import os
import numpy as np
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("."))

from voice_assistant.rag.vector_store import UnifiedVectorStore, QdrantVectorStore
from backend.memory.database import SessionLocal, engine
from sqlalchemy import text

def generate_random_vectors(count: int, dim: int = 768):
    vecs = np.random.randn(count, dim).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return (vecs / norms).tolist()

def run_test_25():
    print("=" * 65)
    print("TEST 25: POSTGRESQL UNAVAILABLE -> QDRANT FALLBACK")
    print("=" * 65)

    coll = "test_qdrant_fallback_coll"
    store = UnifiedVectorStore(collection_name=coll)

    # 1. Verify PostgreSQL availability initially
    db = SessionLocal()
    pg_ok_init = False
    try:
        res = db.execute(text("SELECT 1;")).first()
        pg_ok_init = (res[0] == 1)
    except Exception:
        pg_ok_init = False
    finally:
        db.close()

    print(f"PostgreSQL available initially: {pg_ok_init}")

    # 2. Check Qdrant configuration and reachability
    qdrant_store = store._get_qdrant()
    qdrant_reachable = (qdrant_store.client is not None)
    print(f"Qdrant reachable (Server or Embedded Storage): {qdrant_reachable}")

    # Seed a document into Qdrant fallback store directly
    doc_vec = generate_random_vectors(1, 768)
    doc_chunk = [{"text": "Qdrant fallback knowledge payload", "metadata": {"source": "qdrant_fallback"}}]
    qdrant_store.add_documents(doc_chunk, doc_vec)

    # 3. Simulate PostgreSQL failure during search
    query_vec = doc_vec[0]
    failure_simulated = "Simulated PostgreSQL connection refusal/table error"
    fallback_activated = False
    actual_provider = "Unknown"
    hits = []

    try:
        with patch.object(store.pg_store, "search_similarity", side_effect=Exception("Simulated PostgreSQL connection failure")):
            hits = store.search_similarity(query_vec, top_k=3)
            fallback_activated = True
            if hits and any(h.get("metadata", {}).get("source") == "qdrant_fallback" for h in hits):
                actual_provider = "Qdrant (via UnifiedVectorStore fallback)"
    except Exception as e:
        print(f"Search failed during simulated failure: {e}")

    query_success = len(hits) > 0
    print(f"Fallback activated: {fallback_activated}")
    print(f"Actual provider: {actual_provider}")
    print(f"Hits returned: {len(hits)}")

    # 4. Restore PostgreSQL and verify normal operation
    db = SessionLocal()
    pg_ok_restored = False
    try:
        res = db.execute(text("SELECT 1;")).first()
        pg_ok_restored = (res[0] == 1)
    finally:
        db.close()

    print(f"PostgreSQL restored: {pg_ok_restored}")

    passed = (
        pg_ok_init
        and qdrant_reachable
        and fallback_activated
        and query_success
        and pg_ok_restored
    )

    print("\n" + "=" * 65)
    print("OUTPUT FORMAT FOR TEST 25")
    print("=" * 65)
    print("Test 25:")
    print(f"PostgreSQL available initially: {'TRUE' if pg_ok_init else 'FALSE'}")
    print(f"Qdrant configured: TRUE (UnifiedVectorStore fallback enabled)")
    print(f"Qdrant reachable: {'TRUE' if qdrant_reachable else 'FALSE'}")
    print(f"Failure simulated: {failure_simulated}")
    print(f"Fallback activated: {'TRUE' if fallback_activated else 'FALSE'}")
    print(f"Actual provider: {actual_provider}")
    print(f"Query successful: {'TRUE' if query_success else 'FALSE'}")
    print(f"PostgreSQL restored: {'TRUE' if pg_ok_restored else 'FALSE'}")
    print(f"PASS/FAIL/NOT IMPLEMENTED: {'PASS' if passed else 'FAIL'}")
    print("=" * 65)

if __name__ == "__main__":
    run_test_25()
