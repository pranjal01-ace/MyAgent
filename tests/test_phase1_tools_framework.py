"""
Phase 1 Test Suite — Tool & Action Platform + Safe Desktop Actions.

Tests:
1. ToolRegistry (registration, lookup, duplicates, categories)
2. BaseTool & Schemas (metadata, validation, serialization)
3. PermissionEngine & Confirmation (levels, confirmation flow, always_allow)
4. AuditLogger & Security (sanitization, zero-persistence for clipboard, metrics)
5. ToolExecutor (lifecycle, async execution, timeout safety, error handling)
6. Concrete Phase 1 Tools (get_system_info, get_resource_usage, get_processes,
   is_application_running, open_application, get_clipboard, set_clipboard, show_notification)
7. Security & Injection Rejection (metacharacters, allowlist enforcement, path traversal)
8. Natural Language Routing (the 10 Phase 1 acceptance scenarios)
9. Tools REST API Endpoints (GET /api/tools, GET /api/tools/{name}, validate, execute)
"""

import sys
import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.main import app
from backend.tools.base import BaseTool
from backend.tools.registry import ToolRegistry, tool_registry
from backend.tools.permissions import PermissionEngine, PermissionLevel
from backend.tools.audit import AuditLogger, audit_logger
from backend.tools.executor import ToolExecutor, tool_executor
from backend.tools.schemas import ActionRequest, ToolResult, ToolContext
from backend.tools.errors import (
    ToolError,
    ToolNotFound,
    ToolValidationError,
    ToolPermissionDenied,
    ToolConfirmationRequired,
    ToolTimeout
)
from backend.tools.initialize import initialize_tools
from backend.agent.agent import agent_router


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ==============================================================================
# 1. ToolRegistry Tests
# ==============================================================================

class DummyTestTool(BaseTool):
    name = "dummy_test_tool"
    description = "Test tool for registry verification"
    category = "testing"
    version = "1.0"
    permission_level = PermissionLevel.AUTOMATIC

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True, tool=self.name, message="Dummy executed")


def test_tool_registry_registration_and_lookup():
    reg = ToolRegistry()
    tool = DummyTestTool()

    reg.register(tool)
    assert reg.has("dummy_test_tool") is True
    assert reg.has("DUMMY_TEST_TOOL") is True  # Case insensitive
    assert reg.get("dummy_test_tool") is tool
    assert len(reg.list()) == 1
    assert len(reg.find_by_category("testing")) == 1
    assert len(reg.find_by_category("unknown")) == 0


def test_tool_registry_duplicate_registration_rejection():
    reg = ToolRegistry()
    tool = DummyTestTool()
    reg.register(tool)

    # Attempt duplicate registration without overwrite flag
    with pytest.raises(ToolError) as exc_info:
        reg.register(DummyTestTool(), overwrite=False)
    assert "Duplicate tool registration" in str(exc_info.value)


def test_tool_registry_unregister():
    reg = ToolRegistry()
    tool = DummyTestTool()
    reg.register(tool)
    removed = reg.unregister("dummy_test_tool")
    assert removed is tool
    assert reg.has("dummy_test_tool") is False
    assert reg.get("dummy_test_tool") is None


# ==============================================================================
# 2. BaseTool & Validation Tests
# ==============================================================================

class ParameterizedTool(BaseTool):
    name = "param_tool"
    description = "Tool expecting specific parameters"
    category = "testing"

    def get_schema(self):
        return {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"]
        }

    def validate(self, arguments: dict) -> dict:
        super().validate(arguments)
        if "count" not in arguments:
            raise ToolValidationError("Missing required parameter 'count'")
        try:
            return {"count": int(arguments["count"])}
        except (ValueError, TypeError):
            raise ToolValidationError("Parameter 'count' must be an integer")

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True, tool=self.name, data=arguments)


def test_tool_validation_success_and_failure():
    t = ParameterizedTool()
    desc = t.describe()
    assert desc.name == "param_tool"
    assert "count" in desc.argument_schema["properties"]

    # Valid arguments
    valid = t.validate({"count": "5"})
    assert valid["count"] == 5

    # Missing parameter
    with pytest.raises(ToolValidationError):
        t.validate({})

    # Non-dictionary argument
    with pytest.raises(ToolValidationError):
        t.validate("not a dict")  # type: ignore


# ==============================================================================
# 3. PermissionEngine & Confirmation Tests
# ==============================================================================

def test_permission_engine_evaluation():
    engine = PermissionEngine()

    # AUTOMATIC: safe read operation
    allowed, level, reason, needs_conf = engine.evaluate(
        tool_name="get_system_info",
        default_level=PermissionLevel.AUTOMATIC,
        requires_tool_confirmation=False,
        arguments={}
    )
    assert allowed is True
    assert needs_conf is False
    assert level == PermissionLevel.AUTOMATIC

    # MEDIUM / Requires Confirmation
    allowed, level, reason, needs_conf = engine.evaluate(
        tool_name="write_file",
        default_level=PermissionLevel.MEDIUM,
        requires_tool_confirmation=True,
        arguments={"filepath": "test.txt"},
        confirmed=False
    )
    assert allowed is False
    assert needs_conf is True
    assert "requires user confirmation" in reason.lower()

    # Confirmed execution
    allowed, level, reason, needs_conf = engine.evaluate(
        tool_name="write_file",
        default_level=PermissionLevel.MEDIUM,
        requires_tool_confirmation=True,
        arguments={"filepath": "test.txt"},
        confirmed=True
    )
    assert allowed is True
    assert needs_conf is False

    # Always allow override
    engine.grant_always_allow("write_file")
    allowed, _, _, needs_conf = engine.evaluate(
        tool_name="write_file",
        default_level=PermissionLevel.MEDIUM,
        requires_tool_confirmation=True,
        arguments={},
        confirmed=False
    )
    assert allowed is True
    assert needs_conf is False


# ==============================================================================
# 4. AuditLogger & Security Tests
# ==============================================================================

def test_audit_logger_sanitization():
    audit = AuditLogger()

    # Secret redaction
    args = {
        "username": "ace_user",
        "password": "SuperSecretPassword123!",
        "api_key": "sk-1234567890abcdef",
        "auth_token": "Bearer eyJhbGciOi...",
        "target": "server1"
    }
    sanitized = audit.sanitize_arguments("test_tool", args)
    assert sanitized["username"] == "ace_user"
    assert sanitized["target"] == "server1"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["auth_token"] == "[REDACTED]"

    # Zero-persistence for clipboard tools
    clip_args = {"text": "Confidential clipboard secret data"}
    clip_sanitized = audit.sanitize_arguments("set_clipboard", clip_args)
    assert "[REDACTED]" in clip_sanitized
    assert "Confidential" not in str(clip_sanitized)

    clip_get_sanitized = audit.sanitize_arguments("get_clipboard", {})
    assert "Confidential" not in str(clip_get_sanitized)


# ==============================================================================
# 5. ToolExecutor Lifecycle & Timeout Tests
# ==============================================================================

class SlowTool(BaseTool):
    name = "slow_tool"
    description = "Simulates hanging tool"
    timeout_seconds = 0.3

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        await asyncio.sleep(1.0)
        return ToolResult(success=True, tool=self.name, message="Done")


@pytest.mark.anyio
async def test_tool_executor_timeout():
    reg = ToolRegistry()
    reg.register(SlowTool())
    executor = ToolExecutor(registry=reg)

    req = ActionRequest(tool="slow_tool", arguments={})
    res = await executor.execute(req)

    assert res.success is False
    assert res.error_code == "TOOL_TIMEOUT"
    assert "timed out" in res.error.lower()


@pytest.mark.anyio
async def test_tool_executor_unknown_tool():
    reg = ToolRegistry()
    executor = ToolExecutor(registry=reg)

    req = ActionRequest(tool="secret_tool", arguments={})
    res = await executor.execute(req)

    assert res.success is False
    assert res.error_code == "TOOL_NOT_FOUND"
    assert "not found" in res.error.lower()


# ==============================================================================
# 6. Concrete Phase 1 Tools Integration Tests
# ==============================================================================

@pytest.mark.anyio
async def test_phase1_get_system_info():
    initialize_tools(tool_registry)
    req = ActionRequest(tool="get_system_info", arguments={})
    res = await tool_executor.execute(req)

    assert res.success is True
    assert res.tool == "get_system_info"
    assert "os" in res.data
    assert "cpu_count_logical" in res.data
    assert "ram_total_gb" in res.data
    assert "disk_total_gb" in res.data
    assert res.data["cpu_count_logical"] > 0


@pytest.mark.anyio
async def test_phase1_get_resource_usage():
    initialize_tools(tool_registry)
    req = ActionRequest(tool="get_resource_usage", arguments={})
    res = await tool_executor.execute(req)

    assert res.success is True
    assert res.tool == "get_resource_usage"
    assert "cpu_percent" in res.data
    assert "ram_percent" in res.data
    assert "disk_percent" in res.data
    assert res.data["ram_percent"] >= 0


@pytest.mark.anyio
async def test_phase1_get_processes():
    initialize_tools(tool_registry)
    req = ActionRequest(tool="get_processes", arguments={"limit": 10})
    res = await tool_executor.execute(req)

    assert res.success is True
    assert res.tool == "get_processes"
    assert "processes" in res.data
    assert len(res.data["processes"]) > 0
    first_proc = res.data["processes"][0]
    assert "pid" in first_proc
    assert "name" in first_proc


@pytest.mark.anyio
async def test_phase1_is_application_running():
    initialize_tools(tool_registry)
    # Python is currently running the test
    req = ActionRequest(tool="is_application_running", arguments={"application": "python"})
    res = await tool_executor.execute(req)

    assert res.success is True
    assert res.data["running"] is True

    # Nonexistent application
    req_fake = ActionRequest(tool="is_application_running", arguments={"application": "nonexistent_fake_app_xyz_123"})
    res_fake = await tool_executor.execute(req_fake)
    assert res_fake.success is True
    assert res_fake.data["running"] is False


@pytest.mark.anyio
async def test_phase1_clipboard_read_and_write():
    initialize_tools(tool_registry)
    test_text = "Ace AI Phase 1 Test Payload"

    # Write to clipboard
    req_write = ActionRequest(tool="set_clipboard", arguments={"text": test_text})
    res_write = await tool_executor.execute(req_write)
    assert res_write.success is True

    # Read from clipboard
    req_read = ActionRequest(tool="get_clipboard", arguments={})
    res_read = await tool_executor.execute(req_read)
    assert res_read.success is True
    assert test_text in res_read.data["text"]

    # Verify clipboard tool flags
    clip_tool = tool_registry.get("get_clipboard")
    assert clip_tool.sensitive is True
    assert clip_tool.store_in_memory is False
    assert clip_tool.cacheable is False


@pytest.mark.anyio
async def test_phase1_open_application_allowlist_and_injection():
    initialize_tools(tool_registry)

    # 1. Allowed application (Notepad) mocked launch to prevent popups during tests
    with patch("subprocess.Popen") as mock_popen:
        req = ActionRequest(tool="open_application", arguments={"application": "notepad"})
        res = await tool_executor.execute(req)
        assert res.success is True
        assert mock_popen.called

    # 2. Prohibited command injection payloads
    injection_payloads = [
        "notepad.exe && whoami",
        "notepad.exe | whoami",
        "notepad.exe; whoami",
        "notepad.exe $(whoami)",
        "notepad.exe `whoami`",
        "notepad.exe > output.txt",
        "notepad.exe\nwhoami",
    ]
    for payload in injection_payloads:
        req_inj = ActionRequest(tool="open_application", arguments={"application": payload})
        res_inj = await tool_executor.execute(req_inj)
        assert res_inj.success is False
        assert res_inj.error_code in ("TOOL_VALIDATION_ERROR", "TOOL_PERMISSION_DENIED")

    # 3. Unapproved application rejected
    req_unapproved = ActionRequest(tool="open_application", arguments={"application": "malicious_game.exe"})
    res_unapproved = await tool_executor.execute(req_unapproved)
    assert res_unapproved.success is False
    assert res_unapproved.error_code == "TOOL_PERMISSION_DENIED"


@pytest.mark.anyio
async def test_phase1_show_notification():
    initialize_tools(tool_registry)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        req = ActionRequest(
            tool="show_notification",
            arguments={"message": "Tests passed successfully!", "title": "Ace AI"}
        )
        res = await tool_executor.execute(req)
        assert res.success is True
        assert "Displayed desktop notification" in res.message


# ==============================================================================
# 7. Natural Language Acceptance Tests (Section 39)
# ==============================================================================

def test_acceptance_test_1_system_specifications():
    # User: "What are my system specifications?"
    intent = agent_router.check_intent("What are my system specifications?")
    assert intent is not None
    assert intent[0] == "get_system_info"


def test_acceptance_test_2_ram_usage():
    # User: "How much RAM am I using?"
    intent = agent_router.check_intent("How much RAM am I using?")
    assert intent is not None
    assert intent[0] == "get_resource_usage"


def test_acceptance_test_3_is_chrome_running():
    # User: "Is Chrome running?"
    intent = agent_router.check_intent("Is Chrome running?")
    assert intent is not None
    assert intent[0] == "is_application_running"
    assert "chrome" in intent[1]["application"].lower()


def test_acceptance_test_4_open_chrome():
    # User: "Open Chrome."
    intent = agent_router.check_intent("Open Chrome.")
    assert intent is not None
    assert intent[0] == "open_application"
    assert "chrome" in intent[1]["application"].lower()


def test_acceptance_test_5_what_programs_are_running():
    # User: "What programs are running?"
    intent = agent_router.check_intent("What programs are running?")
    assert intent is not None
    assert intent[0] == "get_processes"


def test_acceptance_test_6_read_clipboard():
    # User: "Read my clipboard."
    intent = agent_router.check_intent("Read my clipboard.")
    assert intent is not None
    assert intent[0] == "get_clipboard"


def test_acceptance_test_7_set_clipboard():
    # User: "Copy this text to my clipboard."
    intent = agent_router.check_intent("Copy this text to my clipboard: hello world")
    assert intent is not None
    assert intent[0] == "set_clipboard"
    assert intent[1]["text"] == "hello world"


def test_acceptance_test_8_show_notification():
    # User: "Notify me that the backend is ready."
    intent = agent_router.check_intent("Notify me that the backend is ready.")
    assert intent is not None
    assert intent[0] == "show_notification"
    assert "backend is ready" in intent[1]["message"]


def test_acceptance_test_9_unknown_tool_rejection():
    # Unknown tool: "Run secret_tool()"
    success, result_msg = agent_router.execute_tool("secret_tool", {})
    assert success is False
    assert "Unknown tool" in result_msg or "not found" in result_msg


def test_acceptance_test_10_malicious_request_safely_ignored():
    # User: "Delete everything on my computer."
    intent = agent_router.check_intent("Delete everything on my computer.")
    # Must NOT route to any dangerous deletion action
    assert intent is None


# ==============================================================================
# 8. Tools REST API Endpoints Tests
# ==============================================================================

def test_api_list_tools(client):
    res = client.get("/api/tools")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "tools" in data
    assert data["total"] >= 8

    names = [t["name"] for t in data["tools"]]
    assert "get_system_info" in names
    assert "get_resource_usage" in names
    assert "get_processes" in names
    assert "is_application_running" in names
    assert "open_application" in names
    assert "get_clipboard" in names
    assert "set_clipboard" in names
    assert "show_notification" in names


def test_api_get_tool_details(client):
    res = client.get("/api/tools/get_system_info")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "get_system_info"
    assert data["category"] == "system"
    assert data["permission_level"] == "AUTOMATIC"
    assert "argument_schema" in data

    # 404 for nonexistent tool
    res_404 = client.get("/api/tools/nonexistent_xyz")
    assert res_404.status_code == 404


def test_api_validate_tool_arguments(client):
    # Valid arguments
    res_valid = client.post(
        "/api/tools/is_application_running/validate",
        json={"arguments": {"application": "chrome"}}
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["valid"] is True

    # Invalid arguments (missing required application parameter)
    res_invalid = client.post(
        "/api/tools/is_application_running/validate",
        json={"arguments": {}}
    )
    assert res_invalid.status_code == 200
    assert res_invalid.json()["valid"] is False


def test_api_execute_tool(client):
    res = client.post(
        "/api/tools/get_system_info/execute",
        json={"arguments": {}}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["tool"] == "get_system_info"
    assert "os" in data["data"]
