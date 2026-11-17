"""
Tools Helpers Module.

Re-exports desktop automation tool implementations and workspace path security validators.
Enforces workspace confinement and safe command execution boundaries.
"""

from backend.agent.tools import (
    TOOL_MAP,
    execute_safe_tool,
    resolve_workspace_path,
    _is_path_allowed,
    get_current_time,
    get_system_info,
    open_application,
    create_file,
    read_file,
    list_files
)

__all__ = [
    "TOOL_MAP",
    "execute_safe_tool",
    "resolve_workspace_path",
    "_is_path_allowed",
    "get_current_time",
    "get_system_info",
    "open_application",
    "create_file",
    "read_file",
    "list_files",
]
