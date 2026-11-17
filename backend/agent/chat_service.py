"""Legacy facade re-exporting ChatService from the conversations domain module."""
from backend.conversations.service import ChatService, chat_service, DYNAMIC_TOOLS

__all__ = ["ChatService", "chat_service", "DYNAMIC_TOOLS"]
