import re
from typing import List, Dict, Any
from voice_assistant.config import settings

class RecursiveTextChunker:
    """Splits documents into overlapping chunks enforcing CHUNK_SIZE and CHUNK_OVERLAP."""

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    def chunk_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        chunks = []
        chunk_counter = 0

        for doc in documents:
            text = doc.get("text", "")
            metadata = doc.get("metadata", {}).copy()

            if not text.strip():
                continue

            text_chunks = self._split_text(text)
            for idx, chunk_text in enumerate(text_chunks):
                chunk_counter += 1
                chunk_meta = metadata.copy()
                chunk_meta["chunk_id"] = chunk_counter
                chunk_meta["sub_chunk_index"] = idx + 1
                
                chunks.append({
                    "text": chunk_text,
                    "metadata": chunk_meta
                })

        return chunks

    def _split_text(self, text: str) -> List[str]:
        if len(text) <= self.chunk_size:
            return [text]

        paragraphs = re.split(r"\n\n+", text)
        result_chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) <= self.chunk_size:
                current_chunk = f"{current_chunk}\n\n{para}".strip()
            else:
                if current_chunk:
                    result_chunks.append(current_chunk)
                
                if len(para) > self.chunk_size:
                    # Sentence-based fallback for long paragraphs
                    sentences = re.split(r"(?<=[.!?])\s+", para)
                    s_chunk = ""
                    for s in sentences:
                        if len(s_chunk) + len(s) <= self.chunk_size:
                            s_chunk = f"{s_chunk} {s}".strip()
                        else:
                            if s_chunk:
                                result_chunks.append(s_chunk)
                            s_chunk = s
                    if s_chunk:
                        current_chunk = s_chunk
                else:
                    current_chunk = para

        if current_chunk:
            result_chunks.append(current_chunk)

        # Apply overlap where applicable
        if self.chunk_overlap > 0 and len(result_chunks) > 1:
            overlapped = []
            for i, c in enumerate(result_chunks):
                if i > 0:
                    prev_tail = result_chunks[i-1][-self.chunk_overlap:]
                    c = f"{prev_tail} {c}".strip()
                overlapped.append(c)
            return overlapped

        return result_chunks
