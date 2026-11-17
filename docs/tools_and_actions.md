# Ace AI — Tool & Action Platform Documentation (Phase 1)

This document provides complete architectural, operational, and development guidelines for the **Ace AI Tool & Action System**.

---

## 1. Architectural Overview

The Tool & Action Platform decouples natural language conversational reasoning from concrete operating system interactions. The agent never executes raw shell commands or unrestricted subprocesses; instead, all interactions are mediated through typed, permissioned, and auditable tools.

```text
                                User Prompt / REST API
                                          │
                                          ▼
                                     ChatService
                                          │
                                          ▼
                                     AgentRouter
                              (Intent / Action Detection)
                                          │
                                          ▼
                                    ActionRequest
                           (Validated Structured Contract)
                                          │
                                          ▼
                                     ToolRegistry
                          (Central Catalog & Introspection)
                                          │
                                          ▼
                                  PermissionEngine
                   (AUTOMATIC / LOW / MEDIUM / HIGH / CRITICAL)
                                          │
                      ┌───────────────────┴───────────────────┐
                      │                                       │
                 [Auto-Allowed]                      [Confirmation Required]
                      │                                       │
                      │                                User Confirms / Rejects
                      │                                       │
                      └───────────────────┬───────────────────┘
                                          ▼
                                     ToolExecutor
                    (Schema Validation, Timeout, Async Concurrency)
                                          │
                                          ▼
                                  BaseTool Execution
                        (Dedicated Concrete Implementation)
                                          │
                                          ▼
                                      ToolResult
                          (Normalized Output, Secrets Scrubbed)
                                          │
                         ┌────────────────┴────────────────┐
                         ▼                                 ▼
                    AuditLogger                       ChatService
            (Zero Clipboard Persistence)        (Ollama Natural Language)
                         │                                 │
                         ▼                                 ▼
                     Telemetry                       User Response
```

---

## 2. Tool Execution Lifecycle

1. **Action Request Ingestion**: An incoming user prompt (via chat or HTTP REST API) is parsed by `AgentRouter` into a strongly-typed `ActionRequest(tool, arguments, session_id, request_id)`.
2. **Registry Lookup**: `ToolRegistry` retrieves the registered tool instance inheriting from `BaseTool`. If not found, a controlled `ToolNotFound` error is raised.
3. **Schema Validation**: The tool's `validate(arguments)` verifies parameter types, bounds, and required keys. Raises `ToolValidationError` on malformed input.
4. **Security & Permission Check**: `PermissionEngine` evaluates tool risk tier against system policy and user overrides (`always_allowed`).
5. **Confirmation Enforcement**: If the operation requires confirmation and the `ToolContext.confirmed` flag is False, execution halts with a `ToolConfirmationRequired` status.
6. **Isolated Asynchronous Execution**:
   - `ToolExecutor` executes `tool.execute(arguments, context)` inside `asyncio.wait_for`.
   - Blocking synchronous OS calls (e.g., `psutil`, `win32clipboard`) are scheduled onto worker threads using `asyncio.to_thread`, ensuring FastAPI's async event loop never hangs.
7. **Result Normalization**: Tool returns a structured `ToolResult(success, tool, data, message, duration_ms)`.
8. **Audit Logging**: `AuditLogger` sanitizes passwords, tokens, and authorization headers. **Zero-persistence rule**: Clipboard contents are strictly excluded from logs and database storage.
9. **Natural Language Response**: `ChatService` injects the sanitized tool result into Ollama's conversational context so Ace responds naturally.

---

## 3. Permission Levels & Confirmation Engine

The system organizes all capabilities into 5 discrete security tiers:

| Tier | Level | Confirmation Required? | Examples |
|---|---|---|---|
| 1 | `AUTOMATIC` | **No** | `get_system_info`, `get_resource_usage`, `get_processes`, `is_application_running`, `get_clipboard` |
| 2 | `LOW` | **No** (unless flagged) | `show_notification`, `open_application` (allowlisted apps) |
| 3 | `MEDIUM` | **Yes** | `create_file`, `write_file`, `set_clipboard`, `copy_file` |
| 4 | `HIGH` | **Yes** (Strict alert) | `run_command` (Phase 2), `delete_file` (Phase 2), `shutdown` |
| 5 | `CRITICAL` | **Yes** (Double-confirm) | System format, credential purge, irreversible deletion |

### Confirmation Decision Rule

The LLM is **strictly forbidden** from deciding whether confirmation is required. That decision is deterministic and made solely by the `PermissionEngine`:

```python
allowed, level, reason, needs_confirmation = permission_engine.evaluate(
    tool_name=tool.name,
    default_level=tool.permission_level,
    requires_tool_confirmation=tool.requires_confirmation,
    arguments=validated_args,
    confirmed=context.confirmed
)
```

---

## 4. Phase 1 Concrete Desktop Tools

### 1. `get_system_info`
- **Category**: `system`
- **Permission**: `AUTOMATIC`
- **Cacheable**: Yes (`cache_ttl=60`)
- **Description**: Returns host OS, release, architecture, CPU logical cores, RAM total/available, disk capacity, and Python version.

### 2. `get_resource_usage`
- **Category**: `system`
- **Permission**: `AUTOMATIC`
- **Cacheable**: No (Real-time)
- **Description**: Returns live CPU %, RAM %, disk % utilization, battery status, and safe GPU metrics (if Nvidia drivers present).

### 3. `get_processes`
- **Category**: `system`
- **Permission**: `AUTOMATIC`
- **Cacheable**: No
- **Arguments**: `limit: int = 20`, `sort_by: str = "memory"` ("memory" or "cpu")
- **Description**: Returns top active processes sorted by resource consumption without command-line argument secrets.

### 4. `is_application_running`
- **Category**: `system`
- **Permission**: `AUTOMATIC`
- **Arguments**: `application: str` (e.g. "chrome", "vscode", "notepad")
- **Description**: Checks whether a specified application process is currently running on the system.

### 5. `open_application`
- **Category**: `applications`
- **Permission**: `LOW`
- **Arguments**: `application: str`
- **Security**: Strictly enforces `ALLOWED_APPLICATIONS` allowlist and rejects shell metacharacters (`[&|;$><\r\n\(\)]`). Executes with `shell=False`.

### 6. `get_clipboard`
- **Category**: `clipboard`
- **Permission**: `AUTOMATIC`
- **Privacy**: `sensitive=True`, `store_in_memory=False`, `cacheable=False`. Contents never written to audit logs or database.

### 7. `set_clipboard`
- **Category**: `clipboard`
- **Permission**: `LOW`
- **Arguments**: `text: str`
- **Privacy**: Text content scrubbed from audit logs.

### 8. `show_notification`
- **Category**: `notifications`
- **Permission**: `LOW`
- **Arguments**: `message: str`, `title: str = "Ace AI"`
- **Description**: Displays native desktop notification using Windows NotifyIcon with sanitized arguments.

---

## 5. Developer Guide: How to Create a New Ace Tool

Adding a new tool requires **zero modifications** to `ChatService`, prompt templates, or the database layer. Follow this standardized workflow:

### Step 1: Create the Tool Class
Create a new file under `backend/tools/<category>/<tool_name>.py`:

```python
from typing import Dict, Any
from backend.tools.base import BaseTool
from backend.tools.schemas import PermissionLevel, ToolResult, ToolContext
from backend.tools.errors import ToolValidationError

class PingHostTool(BaseTool):
    name = "ping_host"
    description = "Pings a remote host to measure network latency."
    category = "network"
    version = "1.0"
    permission_level = PermissionLevel.AUTOMATIC
    requires_confirmation = False
    timeout_seconds = 5.0

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "Target hostname or IP address"}
            },
            "required": ["host"]
        }

    def validate(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        host = arguments.get("host", "").strip()
        if not host:
            raise ToolValidationError("Argument 'host' must not be empty.")
        # Enforce hostname regex to prevent command injection
        if not re.match(r"^[a-zA-Z0-9.-]+$", host):
            raise ToolValidationError("Host contains invalid characters.")
        return {"host": host}

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        host = arguments["host"]
        # Safe async execution
        latency_ms = await measure_ping(host)
        return ToolResult(
            success=True,
            tool=self.name,
            data={"host": host, "latency_ms": latency_ms},
            message=f"Host {host} replied in {latency_ms}ms"
        )
```

### Step 2: Register the Tool
In `backend/tools/initialize.py`, add your tool instance to `phase1_tools` (or category registration list):

```python
from backend.tools.network.ping import PingHostTool

registry.register(PingHostTool())
```

### Step 3: Add Intent Detection (Optional)
If you want natural language routing for this tool, add a rule to `AgentRouter.route_action` in `backend/agent/agent.py`:

```python
if "ping" in lowered:
    m = re.search(r"ping\s+([a-zA-Z0-9.-]+)", lowered)
    if m:
        return ActionRequest(tool="ping_host", arguments={"host": m.group(1)})
```

### Step 4: Write Unit & Integration Tests
Add automated tests in `tests/test_phase1_tools_framework.py`:

```python
@pytest.mark.anyio
async def test_ping_tool():
    req = ActionRequest(tool="ping_host", arguments={"host": "127.0.0.1"})
    res = await tool_executor.execute(req)
    assert res.success is True
```

---

## 6. Security Guarantees

1. **No Arbitrary Code/Shell Execution**: Tools are strictly parameterized Python classes. No LLM output is ever piped to `eval()`, `exec()`, or `shell=True`.
2. **Path Traversal Defense**: All file tools enforce workspace boundary canonicalization (`resolve_workspace_path`) preventing directory escape (`../`).
3. **Shell Metacharacter Sanitization**: Application targets are inspected for metacharacters (`[&|;$`><\r\n\(\)]`).
4. **Zero-Persistence Privacy**: Clipboard data is never indexed into long-term memories, SQL tables, query cache, or audit logs.
5. **Fail-Safe Timeouts**: Every tool is constrained by `timeout_seconds`.
