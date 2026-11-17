import pytest
from voice_assistant.rag.chunker import RecursiveTextChunker

def test_recursive_text_chunker():
    chunker = RecursiveTextChunker(chunk_size=40, chunk_overlap=10)
    docs = [{
        "text": "First paragraph with text content.\n\nSecond paragraph with text content that is slightly longer.",
        "metadata": {"source": "test.txt", "filename": "test.txt", "page": 1}
    }]

    chunks = chunker.chunk_documents(docs)
    assert len(chunks) >= 2
    assert "source" in chunks[0]["metadata"]
    assert chunks[0]["metadata"]["filename"] == "test.txt"
