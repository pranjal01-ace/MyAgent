"""
Automated Test Suite for Phase 2 PC Tools & Security Boundaries.

Tests:
- System Information Tool (get_system_info)
- Process Manager Tool (get_processes, search_processes, get_process_details, terminate_process)
- Critical Process Safety Guardrails
- Application Launcher Tool & Aliases (open_application)
- Folder & File Opener Tools (open_folder, open_file)
- Clipboard Tool (get_clipboard, set_clipboard, clear_clipboard) with Zero-Persistence
- Active Window Inspection Tool (get_active_window)
- Agent Natural Language Router Integration
"""

import os
import sys
import pytest
import asyncio
from unittest.mock import patch, MagicMock

from backend.tools.registry import tool_registry
from backend.tools.executor import tool_executor
from backend.tools.initialize import initialize_tools
from backend.tools.schemas import ActionRequest, ToolContext, PermissionLevel
from backend.tools.errors import ToolValidationError, ToolPermissionDenied, ToolConfirmationRequired
from backend.agent.agent import AgentRouter


@pytest.fixture(scope="module", autouse=True)
def init_registry():
    initialize_tools(tool_registry)


class TestSystemInfoTool:

    @pytest.mark.anyio
    async def test_get_system_info_success(self):
        req = ActionRequest(tool="get_system_info")
        res = await tool_executor.execute(req)

        assert res.success is True
        assert res.tool == "get_system_info"
        assert res.data is not None

        # Verify CPU metrics
        cpu = res.data.get("cpu", {})
        assert "processor" in cpu
        assert "physical_cores" in cpu
        assert "logical_cores" in cpu
        assert "usage_percent" in cpu

        # Verify Memory metrics
        mem = res.data.get("memory", {})
        assert "total_gb" in mem
        assert "used_gb" in mem
        assert "available_gb" in mem
        assert "usage_percent" in mem

        # Verify Drives metrics
        drives = res.data.get("drives", [])
        assert len(drives) > 0
        assert "drive" in drives[0]
        assert "total_gb" in drives[0]
        assert "free_gb" in drives[0]

        # Verify OS metrics
        os_info = res.data.get("os", {})
        assert "name" in os_info
        assert "release" in os_info
        assert "hostname" in os_info

        # Verify clean human-readable summary
        assert "### 🖥️ System Information" in res.message
        assert "Operating System" in res.message
        assert "CPU" in res.message
        assert "Memory" in res.message


class TestProcessManagerTools:

    @pytest.mark.anyio
    async def test_get_processes_sorting(self):
        for sort_metric in ["memory", "cpu", "name", "pid"]:
            req = ActionRequest(tool="get_processes", arguments={"sort_by": sort_metric, "limit": 5})
            res = await tool_executor.execute(req)
            assert res.success is True
            assert res.data["total_returned"] <= 5
            assert res.data["sort_by"] == sort_metric
            assert "| PID | Process Name |" in res.message

    @pytest.mark.anyio
    async def test_search_processes(self):
        req = ActionRequest(tool="search_processes", arguments={"query": "python"})
        res = await tool_executor.execute(req)
        assert res.success is True
        assert "matches" in res.data
        assert res.data["query"] == "python"

    @pytest.mark.anyio
    async def test_search_processes_empty_validation(self):
        tool = tool_registry.get("search_processes")
        with pytest.raises(ToolValidationError):
            tool.validate({"query": "   "})

    @pytest.mark.anyio
    async def test_get_process_details_valid_and_invalid(self):
        # 1. Valid current process PID
        my_pid = os.getpid()
        req_valid = ActionRequest(tool="get_process_details", arguments={"pid": my_pid})
        res_valid = await tool_executor.execute(req_valid)
        assert res_valid.success is True
        assert res_valid.data["pid"] == my_pid
        assert "python" in res_valid.data["name"].lower()
        assert res_valid.data["memory_rss_mb"] > 0

        # 2. Invalid non-existent PID
        req_invalid = ActionRequest(tool="get_process_details", arguments={"pid": 9999999})
        res_invalid = await tool_executor.execute(req_invalid)
        assert res_invalid.success is False
        assert res_invalid.error_code == "PROCESS_NOT_FOUND"

    @pytest.mark.anyio
    async def test_terminate_process_requires_confirmation(self):
        req = ActionRequest(tool="terminate_process", arguments={"process_name": "notepad.exe", "confirmed": False})
        res = await tool_executor.execute(req)
        assert res.success is False
        assert res.error_code in ("TOOL_CONFIRMATION_REQUIRED", "CONFIRMATION_REQUIRED")

    @pytest.mark.anyio
    async def test_terminate_process_blocks_protected_processes(self):
        # Explorer.exe and current python process must NEVER be terminated
        ctx = ToolContext(confirmed=True)
        for protected_target in ["explorer.exe", "System", "csrss.exe"]:
            req = ActionRequest(
                tool="terminate_process",
                arguments={"process_name": protected_target, "confirmed": True}
            )
            res = await tool_executor.execute(req, context=ctx)
            assert res.success is False
            assert res.error_code == "PROTECTED_PROCESS_BLOCKED"
            assert "Action Blocked" in res.message


class TestApplicationLauncherAndFileTools:

    @pytest.mark.anyio
    async def test_open_application_registered_and_aliases(self):
        tool = tool_registry.get("open_application")
        assert tool is not None
        assert "chrome" in tool.allowed_apps
        assert "blender" in tool.allowed_apps
        assert "calculator" in tool.allowed_apps

    @pytest.mark.anyio
    async def test_open_application_blocks_arbitrary_commands(self):
        tool = tool_registry.get("open_application")
        # Attempt command injection
        with pytest.raises(ToolValidationError):
            tool.validate({"application": "calc & dir"})
        with pytest.raises(ToolValidationError):
            tool.validate({"application": "cmd /c whoami"})

    @pytest.mark.anyio
    async def test_open_folder_validation(self):
        tool = tool_registry.get("open_folder")
        # Test shortcut resolution
        valid = tool.validate({"folder_path": "project"})
        assert os.path.isdir(valid["folder_path"])

        # Test non-existent directory rejection
        with pytest.raises(ToolValidationError):
            tool.validate({"folder_path": "C:\\non_existent_folder_xyz_123"})

        # Test shell metacharacter rejection
        with pytest.raises(ToolValidationError):
            tool.validate({"folder_path": "Downloads && echo evil"})

    @pytest.mark.anyio
    async def test_open_file_blocks_executable_scripts(self):
        tool = tool_registry.get("open_file")
        # Prohibit executable binaries and scripts
        for bad_ext in [".exe", ".bat", ".cmd", ".ps1", ".vbs", ".msi"]:
            with pytest.raises(ToolValidationError):
                tool.validate({"file_path": f"C:\\evil_file{bad_ext}"})


class TestClipboardTool:

    @pytest.mark.anyio
    async def test_clipboard_zero_persistence_metadata(self):
        get_tool = tool_registry.get("get_clipboard")
        set_tool = tool_registry.get("set_clipboard")
        clear_tool = tool_registry.get("clear_clipboard")

        assert get_tool.sensitive is True
        assert get_tool.store_in_memory is False
        assert get_tool.cacheable is False

        assert set_tool.sensitive is True
        assert set_tool.store_in_memory is False
        assert set_tool.cacheable is False

        assert clear_tool.sensitive is True
        assert clear_tool.store_in_memory is False
        assert clear_tool.cacheable is False

    @pytest.mark.anyio
    async def test_clear_clipboard_requires_confirmation(self):
        req = ActionRequest(tool="clear_clipboard", arguments={"confirmed": False})
        res = await tool_executor.execute(req)
        assert res.success is False
        assert res.error_code in ("TOOL_CONFIRMATION_REQUIRED", "CONFIRMATION_REQUIRED")


class TestActiveWindowTool:

    @pytest.mark.anyio
    async def test_get_active_window(self):
        req = ActionRequest(tool="get_active_window")
        res = await tool_executor.execute(req)
        assert res.success is True
        assert "title" in res.data
        assert "process" in res.data


class TestAgentRouterNaturalLanguage:

    def test_routing_system_specs(self):
        router = AgentRouter()
        action = router.route_action("What are my PC specs?")
        assert action is not None
        assert action.tool == "get_system_info"

    def test_routing_process_search(self):
        router = AgentRouter()
        action = router.route_action("Find all python processes")
        assert action is not None
        assert action.tool == "search_processes"
        assert action.arguments["query"] == "python"

    def test_routing_cpu_usage(self):
        router = AgentRouter()
        action = router.route_action("What is using my cpu?")
        assert action is not None
        assert action.tool == "get_processes"
        assert action.arguments["sort_by"] == "cpu"

    def test_routing_folder_open(self):
        router = AgentRouter()
        action = router.route_action("Open my Downloads folder")
        assert action is not None
        assert action.tool == "open_folder"
        assert action.arguments["folder_path"] == "downloads"

    def test_routing_clipboard_clear(self):
        router = AgentRouter()
        action = router.route_action("Clear my clipboard")
        assert action is not None
        assert action.tool == "clear_clipboard"

    def test_routing_kill_process(self):
        router = AgentRouter()
        action = router.route_action("Kill chrome")
        assert action is not None
        assert action.tool == "terminate_process"
        assert action.arguments["process_name"] == "chrome"
