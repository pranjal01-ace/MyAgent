import re
from typing import List, Tuple

# Common abbreviations that end in a dot but should NOT trigger sentence boundaries
ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "vs", "etc", "e.g", "i.e", 
    "inc", "ltd", "co", "corp", "st", "ave", "rd", "blvd", "dept", "approx", "min", "sec"
}

class LinguisticStreamBuffer:
    """Intelligent rolling text buffer that detects natural linguistic boundaries 
    while preserving abbreviations, numbers, and prosodic context."""

    def __init__(self, min_words_per_chunk: int = 5, max_context_words: int = 15, first_chunk_min_words: int = 3):
        self.min_words_per_chunk = min_words_per_chunk
        self.first_chunk_min_words = first_chunk_min_words
        self.max_context_words = max_context_words
        self.buffer = ""
        self.history_context = ""
        self.is_first_chunk = True

    def append(self, token: str) -> List[Tuple[str, str]]:
        """Append incoming LLM token to buffer and yield list of (speakable_chunk, previous_context)."""
        self.buffer += token
        chunks = []

        while True:
            boundary_idx = self._find_next_boundary(self.buffer)
            if boundary_idx == -1:
                break

            chunk_text = self.buffer[:boundary_idx].strip()
            self.buffer = self.buffer[boundary_idx:].strip()

            if chunk_text:
                context_prefix = self._get_recent_history_context()
                chunks.append((chunk_text, context_prefix))
                self._update_history_context(chunk_text)
                self.is_first_chunk = False

        return chunks

    def flush(self) -> List[Tuple[str, str]]:
        """Flush any remaining text in buffer upon stream end."""
        remaining = self.buffer.strip()
        self.buffer = ""
        self.is_first_chunk = True
        if not remaining:
            return []

        context_prefix = self._get_recent_history_context()
        self._update_history_context(remaining)
        return [(remaining, context_prefix)]

    def reset(self):
        """Reset buffer and context state."""
        self.buffer = ""
        self.history_context = ""
        self.is_first_chunk = True

    def _find_next_boundary(self, text: str) -> int:
        """Find the index of the next natural linguistic boundary (sentence or clause), 
        protecting abbreviations and numbers."""
        target_min_words = self.first_chunk_min_words if self.is_first_chunk else self.min_words_per_chunk
        words = text.split()
        if len(words) < target_min_words and not any(p in text for p in [".", "!", "?", ";"]):
            return -1

        # Search for punctuation marks: ., !, ?, ;, or ,
        pattern = re.compile(r"([.!?;,])(?:\s+|$)")
        for match in pattern.finditer(text):
            end_pos = match.end()
            punct_char = match.group(1)
            char_idx = match.start(1)

            # Check if dot is part of a number (e.g. 3.14)
            if punct_char == ".":
                if char_idx > 0 and char_idx + 1 < len(text):
                    prev_char = text[char_idx - 1]
                    next_char = text[char_idx + 1]
                    if prev_char.isdigit() and next_char.isdigit():
                        continue

                # Check if dot is part of an abbreviation (e.g. Mr., Dr., e.g.)
                word_before = text[:char_idx].split()[-1] if text[:char_idx].split() else ""
                clean_word = re.sub(r"[^\w]", "", word_before.lower())
                if clean_word in ABBREVIATIONS:
                    continue

            # Ensure chunk has enough substance unless strong sentence end
            prefix = text[:end_pos].strip()
            prefix_words = prefix.split()
            if len(prefix_words) >= target_min_words or punct_char in [".", "!", "?", ";"]:
                return end_pos

        return -1

    def _update_history_context(self, chunk_text: str):
        words = chunk_text.split()
        combined = (self.history_context + " " + chunk_text).strip().split()
        self.history_context = " ".join(combined[-self.max_context_words:])

    def _get_recent_history_context(self) -> str:
        return self.history_context
