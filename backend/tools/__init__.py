"""
Tools Domain Module Exports.
"""

from backend.tools.schemas import (
    ActionRequest,
    ToolResult,
    ToolContext,
    ToolMetadata,
    ToolIntentSchema,
    ToolResultSchema,
    PermissionLevel
)
from backend.tools.base import BaseTool
from backend.tools.errors import (
    ToolError,
    ToolNotFound,
    ToolValidationError,
    ToolPermissionDenied,
    ToolConfirmationRequired,
    ToolExecutionError,
    ToolTimeout,
    ToolUnavailable,
    ToolCancelled
)
from backend.tools.registry import tool_registry, ToolRegistry
from backend.tools.permissions import permission_engine, permission_manager, PermissionEngine
from backend.tools.audit import audit_logger, AuditLogger
from backend.tools.executor import tool_executor, ToolExecutor
from backend.tools.initialize import initialize_tools
from backend.tools.helpers import TOOL_MAP, execute_safe_tool


def __getattr__(name: str):
    if name in ("agent_router", "AgentRouter"):
        from backend.agent.agent import agent_router, AgentRouter
        return agent_router if name == "agent_router" else AgentRouter
    if name == "PermissionManager":
        return PermissionEngine
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "TOOL_MAP",
    "execute_safe_tool",
    "permission_manager",
    "permission_engine",
    "PermissionEngine",
    "PermissionLevel",
    "tool_registry",
    "ToolRegistry",
    "tool_executor",
    "ToolExecutor",
    "audit_logger",
    "AuditLogger",
    "initialize_tools",
    "BaseTool",
    "ActionRequest",
    "ToolResult",
    "ToolContext",
    "ToolMetadata",
    "ToolIntentSchema",
    "ToolResultSchema",
    "ToolError",
    "ToolNotFound",
    "ToolValidationError",
    "ToolPermissionDenied",
    "ToolConfirmationRequired",
    "ToolExecutionError",
    "ToolTimeout",
    "ToolUnavailable",
    "ToolCancelled"
]
