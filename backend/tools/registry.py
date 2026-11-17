"""
Tool Registry Module for Centralized Tool Management.

Provides the single source of truth for tool discovery, lookup, and metadata listing.
Guarantees unique tool registration and controlled rejection of duplicates.
"""

import logging
from typing import Dict, List, Optional
from backend.tools.base import BaseTool
from backend.tools.errors import ToolError

logger = logging.getLogger("ace.tools.registry")


class ToolRegistry:
    """
    Central repository of executable tools.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool, overwrite: bool = False) -> None:
        """
        Registers a tool in the registry.

        Raises ToolError if a tool with the same name already exists and overwrite is False.
        """
        if not tool.name or not isinstance(tool.name, str):
            raise ToolError("Tool name must be a non-empty string.")

        name = tool.name.strip().lower()

        if name in self._tools and not overwrite:
            raise ToolError(f"Duplicate tool registration: '{name}' is already registered.")

        self._tools[name] = tool
        logger.debug(f"Registered tool: '{name}' [category: {tool.category}, permission: {tool.permission_level.value}]")

    def unregister(self, name: str) -> Optional[BaseTool]:
        """Removes and returns a tool from the registry by name."""
        name = name.strip().lower()
        return self._tools.pop(name, None)

    def get(self, name: str) -> Optional[BaseTool]:
        """Retrieves a tool by name, or None if not found."""
        return self._tools.get(name.strip().lower())

    def has(self, name: str) -> bool:
        """Checks whether a tool is registered."""
        return name.strip().lower() in self._tools

    def list(self) -> List[BaseTool]:
        """Returns list of all registered tools."""
        return list(self._tools.values())

    def find_by_category(self, category: str) -> List[BaseTool]:
        """Returns all tools belonging to a specific category."""
        cat_lower = category.strip().lower()
        return [t for t in self._tools.values() if t.category.lower() == cat_lower]

    def clear(self) -> None:
        """Removes all tools from the registry (primarily for testing)."""
        self._tools.clear()


# Global Singleton Registry
tool_registry = ToolRegistry()
