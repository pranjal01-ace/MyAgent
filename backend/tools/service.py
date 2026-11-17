"""
Tools Service Module.

Exposes ToolRegistry, ToolExecutor, PermissionEngine, AuditLogger, and AgentRouter.
Uses lazy import for AgentRouter to decouple circular dependencies.
"""

from backend.tools.registry import tool_registry, ToolRegistry
from backend.tools.executor import tool_executor, ToolExecutor
from backend.tools.permissions import permission_engine, permission_manager, PermissionEngine, PermissionLevel
from backend.tools.audit import audit_logger, AuditLogger
from backend.tools.initialize import initialize_tools

# Auto-initialize tools on module import
initialize_tools(tool_registry)

# PermissionManager alias
PermissionManager = PermissionEngine


def __getattr__(name: str):
    if name in ("agent_router", "AgentRouter"):
        from backend.agent.agent import agent_router, AgentRouter
        return agent_router if name == "agent_router" else AgentRouter
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "permission_manager",
    "permission_engine",
    "PermissionManager",
    "PermissionEngine",
    "PermissionLevel",
    "tool_registry",
    "ToolRegistry",
    "tool_executor",
    "ToolExecutor",
    "audit_logger",
    "AuditLogger",
    "initialize_tools"
]
