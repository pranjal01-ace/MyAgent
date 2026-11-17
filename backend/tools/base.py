"""
Standard BaseTool Interface for Ace AI Tool & Action System.

Every tool in the system inherits from BaseTool to ensure uniform validation,
metadata introspection, permission adherence, asynchronous execution, and telemetry.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from backend.tools.schemas import (
    PermissionLevel,
    ToolResult,
    ToolContext,
    ToolMetadata
)
from backend.tools.errors import ToolValidationError


class BaseTool(ABC):
    """
    Abstract Base Class for all Ace AI tools.

    Subclasses must define metadata attributes and implement execute().
    """

    name: str = ""
    description: str = ""
    category: str = "general"
    version: str = "1.0"
    permission_level: PermissionLevel = PermissionLevel.AUTOMATIC
    requires_confirmation: bool = False

    # Cache and Memory Policy
    cacheable: bool = False
    cache_ttl: int = 0            # Seconds before cached result expires (0 = no cache)
    sensitive: bool = False       # If True, never log argument/result payloads
    store_in_memory: bool = True  # If False, never persist in long-term dialogue memory

    # Execution safeguards
    timeout_seconds: float = 10.0

    def get_schema(self) -> Dict[str, Any]:
        """
        Returns JSON schema describing expected input arguments.
        Default implementation returns empty schema (no arguments expected).
        """
        return {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": True
        }

    def validate(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates provided arguments against the tool's schema or constraints.
        Returns cleaned/validated dictionary of arguments.
        Raises ToolValidationError on invalid input.
        """
        if not isinstance(arguments, dict):
            raise ToolValidationError(f"Arguments must be a dictionary, got {type(arguments).__name__}")
        return arguments

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        """
        Executes the tool asynchronously and returns a normalized ToolResult.

        Must not leak secrets or unhandled exceptions.
        """
        pass

    def describe(self) -> ToolMetadata:
        """Exposes standardized metadata for registry, LLM selection, and UI."""
        return ToolMetadata(
            name=self.name,
            description=self.description,
            category=self.category,
            version=self.version,
            permission_level=self.permission_level,
            requires_confirmation=self.requires_confirmation,
            cacheable=self.cacheable,
            cache_ttl=self.cache_ttl,
            sensitive=self.sensitive,
            store_in_memory=self.store_in_memory,
            timeout_seconds=self.timeout_seconds,
            argument_schema=self.get_schema()
        )
