"""
Tool Initialization and Auto-Discovery Module.

Registers all Phase 1 tools and wraps existing legacy tools into the central ToolRegistry.
Ensures unified lifecycle management across all tools.
"""

import inspect
import asyncio
import logging
from typing import Callable, Dict, Any

from backend.tools.base import BaseTool
from backend.tools.registry import tool_registry, ToolRegistry
from backend.tools.schemas import PermissionLevel, ToolResult, ToolContext

# Import Phase 1 & Phase 2 concrete tools
from backend.tools.system.info import GetSystemInfoTool, GetResourceUsageTool
from backend.tools.system.processes import (
    GetProcessesTool,
    IsApplicationRunningTool,
    SearchProcessesTool,
    GetProcessDetailsTool,
    TerminateProcessTool,
    GetActiveWindowTool
)
from backend.tools.applications.launcher import OpenApplicationTool, OpenFolderTool, OpenFileTool
from backend.tools.clipboard.clipboard import GetClipboardTool, SetClipboardTool, ClearClipboardTool
from backend.tools.notifications.notification import ShowNotificationTool

logger = logging.getLogger("ace.tools.init")


class LegacyFunctionToolAdapter(BaseTool):
    """Adapts existing legacy synchronous or asynchronous tool functions to BaseTool."""

    def __init__(
        self,
        name: str,
        func: Callable,
        description: str,
        category: str = "legacy",
        permission_level: PermissionLevel = PermissionLevel.AUTOMATIC,
        requires_confirmation: bool = False,
        cacheable: bool = False,
        sensitive: bool = False,
        store_in_memory: bool = True
    ):
        super().__init__()
        self.name = name
        self.func = func
        self.description = description or f"Legacy function tool {name}"
        self.category = category
        self.permission_level = permission_level
        self.requires_confirmation = requires_confirmation
        self.cacheable = cacheable
        self.sensitive = sensitive
        self.store_in_memory = store_in_memory

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            if inspect.iscoroutinefunction(self.func):
                res = await self.func(**arguments)
            else:
                res = await asyncio.to_thread(self.func, **arguments)

            return ToolResult(
                success=True,
                tool=self.name,
                data=res,
                message=str(res)
            )
        except Exception as e:
            return ToolResult(
                success=False,
                tool=self.name,
                error=str(e),
                error_code="EXECUTION_ERROR",
                message=f"Legacy tool execution failed: {e}"
            )


def initialize_tools(registry: ToolRegistry = tool_registry) -> None:
    """Registers all Phase 1 and Phase 2 PC tools into the central registry."""

    # 1. Register Phase 1 & Phase 2 Native Tools
    native_tools = [
        GetSystemInfoTool(),
        GetResourceUsageTool(),
        GetProcessesTool(),
        SearchProcessesTool(),
        GetProcessDetailsTool(),
        TerminateProcessTool(),
        IsApplicationRunningTool(),
        GetActiveWindowTool(),
        OpenApplicationTool(),
        OpenFolderTool(),
        OpenFileTool(),
        GetClipboardTool(),
        SetClipboardTool(),
        ClearClipboardTool(),
        ShowNotificationTool(),
    ]

    for tool in native_tools:
        try:
            registry.register(tool, overwrite=True)
        except Exception as e:
            logger.warning(f"Error registering tool '{tool.name}': {e}")

    # 2. Register Legacy Tools from backend.agent.tools
    try:
        from backend.agent import tools as legacy_tools

        legacy_specs = [
            ("get_time", legacy_tools.get_current_time, "Returns current date and time", "system", PermissionLevel.AUTOMATIC, False, True),
            ("open_website", legacy_tools.open_website, "Opens website in browser", "applications", PermissionLevel.AUTOMATIC, False, False),
            ("search_web", legacy_tools.search_web, "Searches the web via browser", "applications", PermissionLevel.AUTOMATIC, False, False),
            ("take_screenshot", legacy_tools.take_screenshot, "Captures a desktop screenshot", "system", PermissionLevel.AUTOMATIC, False, False),
            ("list_files", legacy_tools.list_files, "Lists files inside approved workspace", "filesystem", PermissionLevel.AUTOMATIC, False, False),
            ("read_file", legacy_tools.read_file, "Reads text content of a file in approved workspace", "filesystem", PermissionLevel.AUTOMATIC, False, False),
            ("create_file", legacy_tools.create_file, "Creates a new text file", "filesystem", PermissionLevel.MEDIUM, True, False),
            ("write_file", legacy_tools.write_file, "Writes or appends text to a file", "filesystem", PermissionLevel.MEDIUM, True, False),
            ("copy_file", legacy_tools.copy_file, "Copies a file within workspace", "filesystem", PermissionLevel.MEDIUM, True, False),
            ("move_file", legacy_tools.move_file, "Moves a file within workspace", "filesystem", PermissionLevel.MEDIUM, True, False),
            ("search_knowledge_base", legacy_tools.search_knowledge_base, "Searches local RAG knowledge base", "knowledge", PermissionLevel.AUTOMATIC, False, False),
        ]

        for name, func, desc, cat, perm, conf, cache in legacy_specs:
            if not registry.has(name):
                adapter = LegacyFunctionToolAdapter(
                    name=name,
                    func=func,
                    description=desc,
                    category=cat,
                    permission_level=perm,
                    requires_confirmation=conf,
                    cacheable=cache
                )
                registry.register(adapter, overwrite=True)

        # Clipboard aliases for backward compatibility
        if not registry.has("read_clipboard"):
            registry.register(
                LegacyFunctionToolAdapter(
                    name="read_clipboard",
                    func=legacy_tools.read_clipboard,
                    description="Alias for get_clipboard",
                    category="clipboard",
                    permission_level=PermissionLevel.AUTOMATIC,
                    sensitive=True,
                    store_in_memory=False
                ),
                overwrite=True
            )
        if not registry.has("write_clipboard"):
            registry.register(
                LegacyFunctionToolAdapter(
                    name="write_clipboard",
                    func=legacy_tools.write_clipboard,
                    description="Alias for set_clipboard",
                    category="clipboard",
                    permission_level=PermissionLevel.LOW,
                    sensitive=True,
                    store_in_memory=False
                ),
                overwrite=True
            )

    except Exception as e:
        logger.error(f"Failed to bridge legacy tools into registry: {e}")

    logger.info(f"Tool registry initialized with {len(registry.list())} tools.")
