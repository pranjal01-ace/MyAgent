import hashlib
import logging
import httpx
from typing import List
from voice_assistant.config import settings

logger = logging.getLogger("assistant.rag.embeddings")

class OllamaEmbeddingGenerator:
    """Generates vector embeddings using Ollama's local embedding API with fallback."""

    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_EMBED_MODEL

    def _fallback_embedding(self, text: str, dim: int = 768) -> List[float]:
        """Deterministic local hash-based embedding fallback when model is missing."""
        vec = [0.0] * dim
        tokens = text.lower().split()
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            val = ((h >> 8) % 1000) / 1000.0 - 0.5
            vec[idx] += val
        
        # Normalize
        norm = sum(x*x for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    async def get_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for a single text string."""
        if not text or not text.strip():
            return [0.0] * 768

        # Try /api/embed (Ollama 0.3+)
        payload_new = {"model": self.model, "input": text.strip()}
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.post(f"{self.base_url}/api/embed", json=payload_new)
                if res.status_code == 200:
                    data = res.json()
                    embeds = data.get("embeddings", [])
                    if embeds:
                        return embeds[0]
        except Exception:
            pass

        # Try /api/embeddings (Ollama 0.2+)
        payload_old = {"model": self.model, "prompt": text.strip()}
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.post(f"{self.base_url}/api/embeddings", json=payload_old)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("embedding", [])
        except Exception:
            pass

        # Fallback local embedding if Ollama embed model not pulled
        return self._fallback_embedding(text)

    def get_embedding_sync(self, text: str) -> List[float]:
        """Synchronous embedding generator for document ingestion pipeline."""
        if not text or not text.strip():
            return [0.0] * 768

        payload_new = {"model": self.model, "input": text.strip()}
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.post(f"{self.base_url}/api/embed", json=payload_new)
                if res.status_code == 200:
                    data = res.json()
                    embeds = data.get("embeddings", [])
                    if embeds:
                        return embeds[0]
        except Exception:
            pass

        payload_old = {"model": self.model, "prompt": text.strip()}
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.post(f"{self.base_url}/api/embeddings", json=payload_old)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("embedding", [])
        except Exception:
            pass

        return self._fallback_embedding(text)
