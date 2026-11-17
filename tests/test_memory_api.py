import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.memory.conversation import (
    add_message, get_recent_messages, clear_conversation,
    add_long_term_memory, get_long_term_memories, delete_long_term_memory,
    get_all_memories_detailed
)

class TestMemorySystem(unittest.TestCase):
    def setUp(self):
        clear_conversation(session_id="test_session")

    def test_conversation_memory(self):
        add_message("user", "Hello Companion!", session_id="test_session")
        add_message("assistant", "Hello there!", session_id="test_session")

        msgs = get_recent_messages(limit=10, session_id="test_session")
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[0]["content"], "Hello Companion!")
        self.assertEqual(msgs[1]["role"], "assistant")

        clear_conversation(session_id="test_session")
        msgs_cleared = get_recent_messages(limit=10, session_id="test_session")
        self.assertEqual(len(msgs_cleared), 0)

    def test_long_term_memory(self):
        add_long_term_memory(key="user_favorite_lang", value="Python", category="preferences")
        mems = get_long_term_memories()
        self.assertTrue(any("user_favorite_lang: Python" in m for m in mems))

        detailed = get_all_memories_detailed()
        self.assertTrue(any(d["key"] == "user_favorite_lang" for d in detailed))

        # Delete memory
        deleted = delete_long_term_memory(key="user_favorite_lang")
        self.assertTrue(deleted)

if __name__ == "__main__":
    unittest.main()
