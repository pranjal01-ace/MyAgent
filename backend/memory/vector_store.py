import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from backend.memory.database import SessionLocal, KnowledgeVectorModel, engine

logger = logging.getLogger("ace.vector_store")


class PostgresVectorStore:
    """PostgreSQL-native vector store using in-database cosine similarity."""

    def __init__(self, collection_name: str = "knowledge"):
        self.collection_name = collection_name

    def ensure_collection(self, vector_size: int = None):
        """Placeholder for API compatibility with Qdrant."""
        pass

    def add_documents(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
        collection_name: Optional[str] = None
    ):
        """Insert embedded document chunks into PostgreSQL vector store."""
        if not chunks or not embeddings:
            return

        target_coll = collection_name or self.collection_name
        db = SessionLocal()
        try:
            records = []
            for chunk, vector in zip(chunks, embeddings):
                meta = chunk.get("metadata", {})
                rec = KnowledgeVectorModel(
                    collection_name=target_coll,
                    text=chunk.get("text", ""),
                    metadata_json=json.dumps(meta),
                    embedding=vector
                )
                records.append(rec)

            db.bulk_save_objects(records)
            db.commit()
            logger.info(f"Successfully stored {len(records)} vector chunks into PostgreSQL collection '{target_coll}'.")
        except Exception as e:
            db.rollback()
            logger.error(f"Error inserting vector documents into PostgreSQL: {e}")
            raise
        finally:
            db.close()

    def search_similarity(
        self,
        query_vector: List[float],
        top_k: int = 5,
        collection_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search top-K most similar chunks using in-database cosine similarity."""
        if not query_vector:
            return []

        target_coll = collection_name or self.collection_name
        db = SessionLocal()
        try:
            # Query using accelerated in-database vector_dot_product function
            query_sql = text("""
                SELECT
                    id,
                    text,
                    metadata_json,
                    COALESCE(vector_dot_product(embedding, :query_vec), cosine_similarity(embedding, :query_vec)) AS score
                FROM knowledge_vectors
                WHERE collection_name = :coll
                ORDER BY score DESC
                LIMIT :k
            """)

            res = db.execute(
                query_sql,
                {
                    "query_vec": query_vector,
                    "coll": target_coll,
                    "k": top_k
                }
            )

            hits = []
            for row in res:
                meta = {}
                try:
                    meta = json.loads(row.metadata_json) if row.metadata_json else {}
                except Exception:
                    pass

                hits.append({
                    "id": row.id,
                    "text": row.text,
                    "score": float(row.score or 0.0),
                    "metadata": {
                        "source": meta.get("source", ""),
                        "filename": meta.get("filename", ""),
                        "page": meta.get("page", 1),
                        "chunk_id": meta.get("chunk_id", 0)
                    }
                })

            return hits
        except Exception as e:
            logger.error(f"Error during vector similarity search in PostgreSQL: {e}")
            return []
        finally:
            db.close()

    def get_total_chunks(self, collection_name: Optional[str] = None) -> int:
        """Return total number of vector chunks stored in collection."""
        target_coll = collection_name or self.collection_name
        db = SessionLocal()
        try:
            return db.query(KnowledgeVectorModel).filter(
                KnowledgeVectorModel.collection_name == target_coll
            ).count()
        finally:
            db.close()

    def clear_collection(self, collection_name: Optional[str] = None):
        """Delete all vectors for given collection."""
        target_coll = collection_name or self.collection_name
        db = SessionLocal()
        try:
            deleted = db.query(KnowledgeVectorModel).filter(
                KnowledgeVectorModel.collection_name == target_coll
            ).delete()
            db.commit()
            logger.info(f"Cleared {deleted} vectors from collection '{target_coll}'.")
        finally:
            db.close()
