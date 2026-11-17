import uuid
import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

from voice_assistant.config import settings
from backend.memory.vector_store import PostgresVectorStore

logger = logging.getLogger("assistant.rag.vector_store")

_shared_qdrant_client = None


class QdrantVectorStore:
    """Manages vector storage and similarity search via Qdrant Client (Server or Local Disk)."""

    def __init__(self, collection_name: str = None):
        self.collection_name = collection_name or settings.QDRANT_COLLECTION
        self.client = None
        self._init_client()

    def _init_client(self):
        global _shared_qdrant_client
        if _shared_qdrant_client is not None:
            self.client = _shared_qdrant_client
            return

        try:
            # Try connecting to local Qdrant server first
            client = QdrantClient(url=settings.QDRANT_URL, timeout=2.0, check_compatibility=False)
            client.get_collections()
            logger.info(f"Connected to Qdrant Server at {settings.QDRANT_URL}")
            _shared_qdrant_client = client
        except Exception:
            logger.info(f"Qdrant server at {settings.QDRANT_URL} unavailable; using local disk storage at {settings.QDRANT_STORAGE_PATH}")
            _shared_qdrant_client = QdrantClient(path=settings.QDRANT_STORAGE_PATH, check_compatibility=False)

        self.client = _shared_qdrant_client

    def ensure_collection(self, vector_size: int = 768):
        """Creates Qdrant vector collection if it does not exist."""
        try:
            collections = [c.name for c in self.client.get_collections().collections]
            if self.collection_name not in collections:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
                )
                logger.info(f"Created Qdrant collection '{self.collection_name}' (dim={vector_size}).")
        except Exception as e:
            logger.error(f"Error ensuring Qdrant collection: {e}")

    def add_documents(self, chunks: List[Dict[str, Any]], embeddings: List[List[float]]):
        """Insert embedded document chunks into Qdrant vector store."""
        if not chunks or not embeddings:
            return

        dim = len(embeddings[0])
        self.ensure_collection(vector_size=dim)

        points = []
        for chunk, vector in zip(chunks, embeddings):
            payload = {
                "text": chunk["text"],
                "source": chunk["metadata"].get("source", ""),
                "filename": chunk["metadata"].get("filename", ""),
                "page": chunk["metadata"].get("page", 1),
                "chunk_id": chunk["metadata"].get("chunk_id", 0)
            }
            point_id = str(uuid.uuid4())
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        self.client.upsert(collection_name=self.collection_name, points=points)
        logger.info(f"Successfully upserted {len(points)} chunks into Qdrant collection '{self.collection_name}'.")

    def search_similarity(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """Search top K most similar context chunks for query vector."""
        if not query_vector:
            return []

        try:
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k
            ).points

            hits = []
            for res in results:
                payload = res.payload or {}
                hits.append({
                    "text": payload.get("text", ""),
                    "score": getattr(res, "score", 0.0),
                    "metadata": {
                        "source": payload.get("source", ""),
                        "filename": payload.get("filename", ""),
                        "page": payload.get("page", 1),
                        "chunk_id": payload.get("chunk_id", 0)
                    }
                })
            return hits
        except Exception as e:
            logger.error(f"Error searching Qdrant vector store: {e}")
            return []


class UnifiedVectorStore:
    """Primary Vector Store: uses PostgreSQL as primary store with automatic fallback to Qdrant."""

    def __init__(self, collection_name: str = None):
        self.collection_name = collection_name or settings.QDRANT_COLLECTION
        self.pg_store = PostgresVectorStore(collection_name=self.collection_name)
        self._qdrant_store = None

    def _get_qdrant(self) -> QdrantVectorStore:
        if self._qdrant_store is None:
            self._qdrant_store = QdrantVectorStore(collection_name=self.collection_name)
        return self._qdrant_store

    def ensure_collection(self, vector_size: int = 768):
        self.pg_store.ensure_collection(vector_size)

    def add_documents(self, chunks: List[Dict[str, Any]], embeddings: List[List[float]]):
        try:
            self.pg_store.add_documents(chunks, embeddings)
        except Exception as e:
            logger.warning(f"PostgreSQL vector store failed, falling back to Qdrant: {e}")
            self._get_qdrant().add_documents(chunks, embeddings)

    def search_similarity(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        try:
            hits = self.pg_store.search_similarity(query_vector, top_k=top_k)
            if hits:
                return hits
        except Exception as e:
            logger.warning(f"PostgreSQL vector similarity search error, checking Qdrant fallback: {e}")

        # Fallback
        return self._get_qdrant().search_similarity(query_vector, top_k=top_k)


# Alias default VectorStore to UnifiedVectorStore
VectorStore = UnifiedVectorStore
