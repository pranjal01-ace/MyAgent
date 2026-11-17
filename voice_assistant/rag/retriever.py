import logging
from typing import List, Dict, Any, Tuple
from voice_assistant.config import settings
from voice_assistant.rag.embeddings import OllamaEmbeddingGenerator
from voice_assistant.rag.vector_store import UnifiedVectorStore

logger = logging.getLogger("assistant.rag.retriever")

class RAGRetriever:
    """RAG Context Retriever querying vector database for relevant knowledge chunks."""

    def __init__(self, top_k: int = None):
        self.top_k = top_k or settings.RAG_TOP_K
        self.embedding_generator = OllamaEmbeddingGenerator()
        self.vector_store = UnifiedVectorStore()


    async def retrieve_context(self, query: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Embeds user query and searches Qdrant for top-K context.
        Returns (formatted_context_string, list_of_metadata_sources).
        """
        if not query or not query.strip():
            return "", []

        # Generate query embedding
        query_vector = await self.embedding_generator.get_embedding(query)
        
        # Search Qdrant similarity
        hits = self.vector_store.search_similarity(query_vector, top_k=self.top_k)
        if not hits:
            return "", []

        context_blocks = []
        sources = []
        for i, hit in enumerate(hits):
            meta = hit["metadata"]
            src_name = meta.get("filename", "unknown")
            page_num = meta.get("page", 1)
            text_chunk = hit["text"]

            context_blocks.append(f"[Source {i+1}: {src_name} (Page {page_num})]\n{text_chunk}")
            sources.append(meta)

        formatted_context = "\n\n".join(context_blocks)
        logger.info(f"Retrieved {len(hits)} RAG context chunks for query '{query[:30]}...'")
        return formatted_context, sources

    def retrieve(self, query: str, top_k: int = 3):
        """Synchronous retrieval interface for desktop tools."""
        import asyncio
        class RAGHit:
            def __init__(self, content, source):
                self.content = content
                self.source = source

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    formatted, sources = pool.submit(asyncio.run, self.retrieve_context(query)).result()
            else:
                formatted, sources = asyncio.run(self.retrieve_context(query))
        except Exception as e:
            logger.error(f"Error in synchronous retrieve: {e}")
            return []

        if not formatted:
            return []
        return [RAGHit(content=formatted, source="PostgreSQL Knowledge Base")]

