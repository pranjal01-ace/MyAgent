import logging
from typing import List, Dict
from voice_assistant.config import settings

logger = logging.getLogger("assistant.memory")

class ConversationMemory:
    """Sliding-window conversation memory enforcing MAX_HISTORY_MESSAGES limit."""

    def __init__(self, max_messages: int = None):
        self.max_messages = max_messages or settings.MAX_HISTORY_MESSAGES
        self.history: List[Dict[str, str]] = []

    def add_user_message(self, text: str):
        if text and text.strip():
            self.history.append({"role": "user", "content": text.strip()})
            self._trim()

    def add_assistant_message(self, text: str):
        if text and text.strip():
            self.history.append({"role": "assistant", "content": text.strip()})
            self._trim()

    def get_history(self) -> List[Dict[str, str]]:
        return list(self.history)

    def _trim(self):
        if len(self.history) > self.max_messages:
            excess = len(self.history) - self.max_messages
            self.history = self.history[excess:]
            logger.debug(f"Trimmed conversation history down to {len(self.history)} messages.")

    def clear(self):
        self.history.clear()
        logger.info("Conversation history cleared.")
