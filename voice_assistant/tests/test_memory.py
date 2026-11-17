import pytest
from voice_assistant.conversation.memory import ConversationMemory

def test_conversation_memory_windowing():
    mem = ConversationMemory(max_messages=4)
    
    mem.add_user_message("Hello")
    mem.add_assistant_message("Hi there!")
    mem.add_user_message("What is Python?")
    mem.add_assistant_message("Python is a programming language.")
    mem.add_user_message("Explain decorators.")

    history = mem.get_history()
    assert len(history) == 4
    assert history[0]["content"] == "Hi there!"
    assert history[-1]["content"] == "Explain decorators."

def test_memory_clear():
    mem = ConversationMemory()
    mem.add_user_message("Test")
    assert len(mem.get_history()) == 1
    mem.clear()
    assert len(mem.get_history()) == 0
