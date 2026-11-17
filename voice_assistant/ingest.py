import sys
import argparse
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR.parent))

from voice_assistant.config import settings
from voice_assistant.rag.document_loader import DocumentLoader
from voice_assistant.rag.chunker import RecursiveTextChunker
from voice_assistant.rag.embeddings import OllamaEmbeddingGenerator
from voice_assistant.rag.vector_store import UnifiedVectorStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("assistant.ingest")

def ingest_documents(docs_path: str):
    path = Path(docs_path)
    if not path.exists():
        print(f"Error: Path '{docs_path}' does not exist.")
        return

    supported_exts = {".txt", ".md", ".pdf", ".docx"}
    files_to_process = []
    
    if path.is_file():
        if path.suffix.lower() in supported_exts:
            files_to_process.append(path)
    else:
        for p in path.rglob("*"):
            if p.is_file() and p.suffix.lower() in supported_exts:
                files_to_process.append(p)

    if not files_to_process:
        print(f"No supported document files (.txt, .md, .pdf, .docx) found in {docs_path}.")
        return

    print(f"\n==================================================")
    print(f" RAG DOCUMENT INGESTION PIPELINE")
    print(f"==================================================")
    print(f"Target Path:       {docs_path}")
    print(f"Files Found:       {len(files_to_process)}")
    print(f"Embedding Model:   {settings.OLLAMA_EMBED_MODEL}")
    print(f"Vector Database:   PostgreSQL (Collection: {settings.QDRANT_COLLECTION})")
    print("--------------------------------------------------\n")

    chunker = RecursiveTextChunker()
    embedder = OllamaEmbeddingGenerator()
    vector_store = UnifiedVectorStore()


    total_chunks = 0
    all_chunks = []

    for file_path in files_to_process:
        logger.info(f"Loading document: {file_path.name}")
        docs = DocumentLoader.load_document(file_path)
        if not docs:
            continue

        file_chunks = chunker.chunk_documents(docs)
        total_chunks += len(file_chunks)
        all_chunks.extend(file_chunks)
        logger.info(f" -> Extracted {len(file_chunks)} text chunks from {file_path.name}")

    if not all_chunks:
        print("No text content could be extracted from documents.")
        return

    print(f"\nGenerating Ollama vector embeddings for {total_chunks} chunks...")
    embeddings = []
    for idx, chunk in enumerate(all_chunks):
        if (idx + 1) % 5 == 0 or (idx + 1) == total_chunks:
            print(f"Embedding progress: {idx + 1}/{total_chunks} chunks processed...")
        
        vec = embedder.get_embedding_sync(chunk["text"])
        embeddings.append(vec)

    print("\nUpserting vector points into PostgreSQL database...")
    vector_store.add_documents(all_chunks, embeddings)

    print("\n==================================================")
    print(f" SUCCESS: Ingested {total_chunks} chunks from {len(files_to_process)} files!")
    print(f"==================================================\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest documents into PostgreSQL RAG vector database.")
    parser.add_argument("--path", type=str, default="voice_assistant/data/documents", help="Directory or file path to ingest")
    args = parser.parse_args()

    ingest_documents(args.path)
