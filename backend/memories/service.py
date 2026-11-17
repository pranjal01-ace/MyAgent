"""
Memories Service Layer
======================
Implements business rules, input sanitization, and orchestration for the memories domain.
Provides higher-level abstractions consumed by API routers and internal agents.
"""

import logging
from typing import List, Dict, Any, Optional

from backend.memories.repository import memory_repository, MemoryRepository
from backend.memories.models import MemoryModel
from backend.common.exceptions import EntityNotFoundError

logger = logging.getLogger("ace.memories.service")


class MemoryService:
    """
    Business service layer managing user memory entities.
    """

    def __init__(self, repo: Optional[MemoryRepository] = None):
        """
        Initialize service with injected or default repository.
        """
        self.repo = repo or memory_repository

    def create_or_update_memory(
        self,
        key: str,
        value: str,
        category: str = "general"
    ) -> MemoryModel:
        """
        Validates, sanitizes, and stores or updates a long-term user memory.

        Args:
            key (str): Unique memory identifier.
            value (str): Fact or preference string.
            category (str): Optional grouping category.

        Returns:
            MemoryModel: Persisted database model.
        """
        cleaned_key = key.strip()
        cleaned_value = value.strip()
        cleaned_cat = category.strip() or "general"
        logger.info(f"MemoryService: Storing memory key='{cleaned_key}' [category='{cleaned_cat}']")
        return self.repo.add_or_update_memory(
            key=cleaned_key,
            value=cleaned_value,
            category=cleaned_cat
        )

    def get_memory(self, key: str) -> MemoryModel:
        """
        Retrieve a specific memory by key.

        Args:
            key (str): Identifier to search.

        Raises:
            EntityNotFoundError: If the key does not exist or is inactive.

        Returns:
            MemoryModel: The active record.
        """
        memory = self.repo.get_memory_by_key(key.strip())
        if not memory:
            raise EntityNotFoundError("Memory", key)
        return memory

    def list_memories(self, category: Optional[str] = None) -> List[MemoryModel]:
        """
        List all active memories, optionally filtered by category.

        Args:
            category (Optional[str]): Optional category filter.

        Returns:
            List[MemoryModel]: List of memories.
        """
        return self.repo.get_all_memories(category=category)

    def list_memories_detailed(self) -> List[Dict[str, Any]]:
        """
        List active memories with formatted ISO audit timestamps for client inspection.

        Returns:
            List[Dict[str, Any]]: Detailed serialized memory records.
        """
        return self.repo.get_all_memories_detailed()

    def remove_memory(self, key: str) -> bool:
        """
        Deletes a memory by key.

        Args:
            key (str): Identifier to remove.

        Raises:
            EntityNotFoundError: If memory does not exist.

        Returns:
            bool: True on successful deletion.
        """
        deleted = self.repo.delete_memory(key.strip())
        if not deleted:
            raise EntityNotFoundError("Memory", key)
        logger.info(f"MemoryService: Deleted memory key='{key}'")
        return True


# Global service singleton instance
memory_service = MemoryService()
