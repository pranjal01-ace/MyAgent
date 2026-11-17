import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath("."))

from backend.memory.vector_store import PostgresVectorStore
from voice_assistant.rag.embeddings import OllamaEmbeddingGenerator
from backend.memory.database import SessionLocal, KnowledgeVectorModel

async def run_test_19():
    print("=" * 65)
    print("TEST 19: VECTOR SEARCH CORRECTNESS")
    print("=" * 65)

    coll_name = "test_correctness_bench"
    store = PostgresVectorStore(collection_name=coll_name)
    embedder = OllamaEmbeddingGenerator()

    # Clean existing test collection
    db = SessionLocal()
    try:
        db.query(KnowledgeVectorModel).filter(KnowledgeVectorModel.collection_name == coll_name).delete()
        db.commit()
    finally:
        db.close()

    # 1. Ingest controlled conceptual documents
    docs = [
        {
            "id_tag": "A",
            "topic": "Python garbage collection",
            "text": "Python garbage collection automatically cleans up unused objects and deallocates memory using reference counting and a cyclic garbage collector."
        },
        {
            "id_tag": "B",
            "topic": "Python virtual environments",
            "text": "Python virtual environments isolate project dependencies, preventing version conflicts between different Python software applications."
        },
        {
            "id_tag": "C",
            "topic": "FastAPI dependency injection",
            "text": "FastAPI dependency injection allows web route handlers to inject database sessions, authentication credentials, and shared application services."
        }
    ]

    print("Generating embeddings for 3 conceptual records...")
    chunks = []
    embeddings = []
    for d in docs:
        vec = await embedder.get_embedding(d["text"])
        chunks.append({
            "text": d["text"],
            "metadata": {"source": f"[{d['id_tag']}] {d['topic']}"}
        })
        embeddings.append(vec)

    store.add_documents(chunks, embeddings, collection_name=coll_name)
    print(f"Stored {len(chunks)} records in PostgreSQL collection '{coll_name}'.")

    # 2. Query with semantic query
    query = "How does Python clean unused objects?"
    query_vec = await embedder.get_embedding(query)

    print(f"\nSearching for query: '{query}' (top_k=3)...")
    hits = store.search_similarity(query_vec, top_k=3, collection_name=coll_name)

    top_results_desc = []
    scores = []
    for rank, h in enumerate(hits, 1):
        src = h.get("metadata", {}).get("source", "Unknown")
        score = h.get("score", 0.0)
        scores.append(score)
        top_results_desc.append(f"Rank {rank}: {src} (Score: {score:.4f})")
        print(f"  Rank {rank} | Score: {score:.4f} | {src}: {h['text'][:75]}...")

    # Check ordering
    correct_ordering = all(scores[i] >= scores[i+1] for i in range(len(scores)-1))
    best_hit = hits[0] if hits else {}
    best_source = best_hit.get("metadata", {}).get("source", "")

    passed = (
        len(hits) == 3
        and "[A]" in best_source
        and correct_ordering
        and scores[0] > scores[1]
    )

    # Clean up test collection
    db = SessionLocal()
    try:
        db.query(KnowledgeVectorModel).filter(KnowledgeVectorModel.collection_name == coll_name).delete()
        db.commit()
    finally:
        db.close()

    print("\n" + "=" * 65)
    print("OUTPUT FORMAT FOR TEST 19")
    print("=" * 65)
    print("Test 19:")
    print(f"Query: {query}")
    print(f"Top results: {'; '.join(top_results_desc)}")
    print(f"Similarity scores: {[round(s, 4) for s in scores]}")
    print("Expected relevant topic: Python garbage collection (Doc A)")
    print(f"Actual result: {best_source}")
    print(f"Correct ordering: {'TRUE' if correct_ordering else 'FALSE'}")
    print(f"PASS/FAIL: {'PASS' if passed else 'FAIL'}")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(run_test_19())
