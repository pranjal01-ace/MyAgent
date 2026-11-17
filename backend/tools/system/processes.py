"""
Process Inspection, Management, and Window Detection Tools.

Provides safe discovery of active processes, detailed process metrics,
safe process termination with critical system guardrails, and active window inspection.
"""

import os
import sys
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
import psutil

from backend.tools.base import BaseTool
from backend.tools.schemas import PermissionLevel, ToolResult, ToolContext
from backend.tools.errors import ToolValidationError, ToolPermissionDenied

logger = logging.getLogger("ace.tools.processes")

# Critical Windows and core companion processes that must NEVER be terminated
PROTECTED_PROCESS_NAMES = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "explorer.exe",
    "dwm.exe", "fontdrvhost.exe", "python.exe", "ollama.exe", "postgres.exe"
}


class GetProcessesTool(BaseTool):
    """Returns a safe, sorted list of top active system processes."""

    name = "get_processes"
    description = "Returns active system processes with PID, name, CPU %, and memory %."
    category = "system"
    version = "2.0"
    permission_level = PermissionLevel.READ_ONLY
    requires_confirmation = False
    cacheable = False
    timeout_seconds = 5.0

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of processes to return (default: 20, max: 50)",
                    "default": 20
                },
                "sort_by": {
                    "type": "string",
                    "description": "Sort metric: 'memory', 'cpu', 'name', or 'pid'",
                    "default": "memory"
                }
            },
            "required": []
        }

    def validate(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = dict(arguments or {})
        limit = cleaned.get("limit", 20)
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 20
        cleaned["limit"] = min(max(1, limit), 50)

        sort_by = str(cleaned.get("sort_by", "memory")).lower().strip()
        if sort_by not in ("memory", "cpu", "name", "pid"):
            sort_by = "memory"
        cleaned["sort_by"] = sort_by
        return cleaned

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        limit = arguments.get("limit", 20)
        sort_by = arguments.get("sort_by", "memory")

        def _list_processes():
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
                try:
                    info = p.info
                    name = info.get('name') or "unknown"
                    if not name or name == "System Idle Process":
                        continue
                    procs.append({
                        "pid": info.get("pid"),
                        "name": name,
                        "cpu_percent": round(info.get("cpu_percent") or 0.0, 1),
                        "memory_percent": round(info.get("memory_percent") or 0.0, 1),
                        "status": info.get("status") or "running"
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if sort_by == "cpu":
                sorted_procs = sorted(procs, key=lambda x: x["cpu_percent"], reverse=True)
            elif sort_by == "name":
                sorted_procs = sorted(procs, key=lambda x: x["name"].lower())
            elif sort_by == "pid":
                sorted_procs = sorted(procs, key=lambda x: x["pid"])
            else:  # memory default
                sorted_procs = sorted(procs, key=lambda x: x["memory_percent"], reverse=True)

            return sorted_procs[:limit]

        proc_list = await asyncio.to_thread(_list_processes)

        # Build clean markdown table
        table_lines = [
            f"### 📊 Active Processes (Top {len(proc_list)}, sorted by {sort_by})\n",
            "| PID | Process Name | CPU % | RAM % | Status |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]
        for p in proc_list:
            table_lines.append(f"| `{p['pid']}` | **{p['name']}** | {p['cpu_percent']}% | {p['memory_percent']}% | {p['status']} |")

        formatted_table = "\n".join(table_lines)

        return ToolResult(
            success=True,
            tool=self.name,
            data={"processes": proc_list, "total_returned": len(proc_list), "sort_by": sort_by},
            message=formatted_table
        )


class SearchProcessesTool(BaseTool):
    """Searches active processes matching a name or PID query."""

    name = "search_processes"
    description = "Finds running processes matching a given name or PID."
    category = "system"
    version = "1.0"
    permission_level = PermissionLevel.READ_ONLY
    requires_confirmation = False
    cacheable = False
    timeout_seconds = 5.0

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Process name or PID substring to search for (e.g. 'python', 'chrome', '1234')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max matches to return (default: 20)",
                    "default": 20
                }
            },
            "required": ["query"]
        }

    def validate(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        q = arguments.get("query") or arguments.get("name") or arguments.get("process")
        if not q or not isinstance(q, str) or not q.strip():
            raise ToolValidationError("Argument 'query' must be a non-empty string.")
        limit = arguments.get("limit", 20)
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 20
        return {"query": q.strip(), "limit": min(max(1, limit), 50)}

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        query = arguments["query"].lower()
        limit = arguments["limit"]

        def _search():
            matches = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
                try:
                    info = p.info
                    name = (info.get('name') or "").lower()
                    pid_str = str(info.get('pid'))
                    if query in name or query in pid_str:
                        matches.append({
                            "pid": info.get("pid"),
                            "name": info.get("name"),
                            "cpu_percent": round(info.get("cpu_percent") or 0.0, 1),
                            "memory_percent": round(info.get("memory_percent") or 0.0, 1),
                            "status": info.get("status") or "running"
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return sorted(matches, key=lambda x: x["memory_percent"], reverse=True)[:limit]

        results = await asyncio.to_thread(_search)

        if not results:
            return ToolResult(
                success=True,
                tool=self.name,
                data={"matches": [], "query": arguments["query"]},
                message=f"No active processes found matching '{arguments['query']}'."
            )

        table_lines = [
            f"### 🔍 Processes Matching '{arguments['query']}' ({len(results)} found)\n",
            "| PID | Process Name | CPU % | RAM % | Status |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]
        for p in results:
            table_lines.append(f"| `{p['pid']}` | **{p['name']}** | {p['cpu_percent']}% | {p['memory_percent']}% | {p['status']} |")

        return ToolResult(
            success=True,
            tool=self.name,
            data={"matches": results, "total": len(results), "query": arguments["query"]},
            message="\n".join(table_lines)
        )


class GetProcessDetailsTool(BaseTool):
    """Retrieves in-depth metrics and status for a specific process PID."""

    name = "get_process_details"
    description = "Returns detailed metrics (CPU, RAM, threads, create time, status) for a process by PID."
    category = "system"
    version = "1.0"
    permission_level = PermissionLevel.READ_ONLY
    requires_confirmation = False
    cacheable = False
    timeout_seconds = 4.0

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pid": {
                    "type": "integer",
                    "description": "Process ID (PID) to inspect"
                }
            },
            "required": ["pid"]
        }

    def validate(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        pid = arguments.get("pid")
        try:
            pid = int(pid)
        except (ValueError, TypeError):
            raise ToolValidationError("Argument 'pid' must be a valid integer PID.")
        if pid < 0:
            raise ToolValidationError("Argument 'pid' must be non-negative.")
        return {"pid": pid}

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        pid = arguments["pid"]

        def _get_details():
            try:
                proc = psutil.Process(pid)
                with proc.oneshot():
                    name = proc.name()
                    status = proc.status()
                    cpu_pct = round(proc.cpu_percent(interval=0.1), 1)
                    mem_info = proc.memory_info()
                    mem_pct = round(proc.memory_percent(), 1)
                    mem_rss_mb = round(mem_info.rss / (1024 ** 2), 1)
                    num_threads = proc.num_threads()
                    create_time_dt = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(proc.create_time()))

                    # Safe exe path inspection
                    try:
                        exe_path = proc.exe()
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        exe_path = "Access Restricted"

                    # Safe username
                    try:
                        username = proc.username()
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        username = "System/Restricted"

                    return {
                        "pid": pid,
                        "name": name,
                        "status": status,
                        "cpu_percent": cpu_pct,
                        "memory_percent": mem_pct,
                        "memory_rss_mb": mem_rss_mb,
                        "threads": num_threads,
                        "create_time": create_time_dt,
                        "exe": exe_path,
                        "user": username
                    }
            except psutil.NoSuchProcess:
                return None
            except psutil.AccessDenied as e:
                return {"error": f"Access denied inspecting PID {pid}: {e}"}

        details = await asyncio.to_thread(_get_details)

        if details is None:
            return ToolResult(
                success=False,
                tool=self.name,
                error="Process Not Found",
                error_code="PROCESS_NOT_FOUND",
                message=f"Process with PID {pid} was not found or has already terminated."
            )

        if "error" in details:
            return ToolResult(
                success=False,
                tool=self.name,
                error=details["error"],
                error_code="ACCESS_DENIED",
                message=details["error"]
            )

        summary = (
            f"### 📌 Process Details: {details['name']} (PID: `{pid}`)\n\n"
            f"- **Status**: `{details['status']}`\n"
            f"- **Memory**: {details['memory_rss_mb']} MB ({details['memory_percent']}%)\n"
            f"- **CPU Usage**: {details['cpu_percent']}%\n"
            f"- **Threads**: {details['threads']}\n"
            f"- **User**: `{details['user']}`\n"
            f"- **Started**: {details['create_time']}\n"
            f"- **Executable**: `{details['exe']}`"
        )

        return ToolResult(
            success=True,
            tool=self.name,
            data=details,
            message=summary
        )


class TerminateProcessTool(BaseTool):
    """Safely terminates a process with critical system process protection and confirmation checks."""

    name = "terminate_process"
    description = "Safely terminates a process by PID or name. Protected system processes are strictly blocked."
    category = "system"
    version = "1.0"
    permission_level = PermissionLevel.CONFIRMATION_REQUIRED
    requires_confirmation = True
    cacheable = False
    timeout_seconds = 8.0

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pid": {
                    "type": "integer",
                    "description": "Process ID (PID) to terminate"
                },
                "process_name": {
                    "type": "string",
                    "description": "Process name to terminate (e.g. 'notepad.exe', 'calculator')"
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Explicit confirmation flag for termination",
                    "default": False
                }
            },
            "required": []
        }

    def validate(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = dict(arguments or {})
        pid = cleaned.get("pid")
        pname = cleaned.get("process_name") or cleaned.get("name") or cleaned.get("application")

        if pid is None and not pname:
            raise ToolValidationError("Must provide either 'pid' or 'process_name' to terminate.")

        if pid is not None:
            try:
                cleaned["pid"] = int(pid)
            except (ValueError, TypeError):
                raise ToolValidationError("Argument 'pid' must be a valid integer.")

        if pname:
            cleaned["process_name"] = str(pname).strip()

        cleaned["confirmed"] = bool(cleaned.get("confirmed", False))
        return cleaned

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        target_pid = arguments.get("pid")
        target_name = arguments.get("process_name")
        is_confirmed = arguments.get("confirmed", False) or getattr(context, "confirmed", False)

        # 1. Resolve Target Process
        def _resolve_and_check():
            if target_pid is not None:
                try:
                    p = psutil.Process(target_pid)
                    return [p], None
                except psutil.NoSuchProcess:
                    return [], f"Process with PID {target_pid} does not exist."
                except psutil.AccessDenied:
                    return [], f"Access denied inspecting PID {target_pid}."
            else:
                clean_target = target_name.lower().replace(".exe", "").strip()
                matches = []
                for p in psutil.process_iter(['pid', 'name']):
                    try:
                        pname = (p.info.get('name') or "").lower()
                        base_pname = pname.replace(".exe", "").strip()
                        if clean_target == base_pname or clean_target in base_pname:
                            matches.append(p)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                if not matches:
                    return [], f"No active process found matching '{target_name}'."
                return matches, None

        procs, err_msg = await asyncio.to_thread(_resolve_and_check)
        if err_msg:
            return ToolResult(
                success=False,
                tool=self.name,
                error=err_msg,
                error_code="PROCESS_NOT_FOUND",
                message=err_msg
            )

        # 2. Check Protected Process Guardrails
        for p in procs:
            try:
                pname = (p.name() or "").lower()
                pid = p.pid
                # Protect current companion python process
                if pid == os.getpid():
                    return ToolResult(
                        success=False,
                        tool=self.name,
                        error="Protected Process: Cannot terminate Ace AI Companion process.",
                        error_code="PROTECTED_PROCESS_BLOCKED",
                        message="🛑 **Action Blocked**: Cannot terminate the active Ace AI Companion process."
                    )
                if pname in PROTECTED_PROCESS_NAMES or pname.replace(".exe", "") in PROTECTED_PROCESS_NAMES:
                    return ToolResult(
                        success=False,
                        tool=self.name,
                        error=f"Protected Process: {pname} (PID {pid}) is critical to system stability.",
                        error_code="PROTECTED_PROCESS_BLOCKED",
                        message=f"🛑 **Action Blocked**: `{pname}` (PID `{pid}`) is an essential system/service process and cannot be terminated."
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # 3. Confirmation Safety Gate
        proc_summaries = []
        for p in procs:
            try:
                proc_summaries.append(f"`{p.name()}` (PID: `{p.pid}`)")
            except Exception:
                pass

        summary_target = ", ".join(proc_summaries)

        if not is_confirmed:
            return ToolResult(
                success=False,
                tool=self.name,
                error="Confirmation Required",
                error_code="CONFIRMATION_REQUIRED",
                message=(
                    f"⚠️ **Confirmation Required**: Are you sure you want to terminate {summary_target}?\n\n"
                    f"Please confirm by replying: *'Yes, terminate {target_name or target_pid}'*."
                ),
                data={"pending_confirmation": True, "target": summary_target}
            )

        # 4. Perform Termination
        def _terminate_all():
            terminated_list = []
            failed_list = []
            for p in procs:
                try:
                    pname = p.name()
                    pid = p.pid
                    p.terminate()
                    try:
                        p.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        p.kill()
                        p.wait(timeout=2)
                    terminated_list.append({"pid": pid, "name": pname})
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    failed_list.append({"pid": getattr(p, "pid", None), "error": str(e)})
            return terminated_list, failed_list

        terminated, failed = await asyncio.to_thread(_terminate_all)

        if terminated:
            term_str = ", ".join([f"`{t['name']}` (PID `{t['pid']}`)" for t in terminated])
            fail_str = f" (Failed to stop: {len(failed)})" if failed else ""
            return ToolResult(
                success=True,
                tool=self.name,
                data={"terminated": terminated, "failed": failed},
                message=f"✓ Successfully terminated: {term_str}{fail_str}."
            )
        else:
            err = failed[0]["error"] if failed else "Could not terminate process."
            return ToolResult(
                success=False,
                tool=self.name,
                error=err,
                error_code="TERMINATION_FAILED",
                message=f"✕ Failed to terminate process: {err}"
            )


class IsApplicationRunningTool(BaseTool):
    """Detects if a specified desktop application or executable is currently running."""

    name = "is_application_running"
    description = "Checks if an application or process is currently active."
    category = "system"
    version = "1.0"
    permission_level = PermissionLevel.READ_ONLY
    requires_confirmation = False
    cacheable = False
    timeout_seconds = 4.0

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "application": {
                    "type": "string",
                    "description": "Name or alias of application to check (e.g. 'chrome', 'code', 'notepad')"
                }
            },
            "required": ["application"]
        }

    def validate(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        app = arguments.get("application") or arguments.get("app_name") or arguments.get("name")
        if not app or not isinstance(app, str) or not app.strip():
            raise ToolValidationError("Argument 'application' must be a non-empty string.")
        return {"application": app.strip()}

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        target = arguments["application"].lower()

        alias_map = {
            "chrome": "chrome",
            "google chrome": "chrome",
            "vscode": "code",
            "vs code": "code",
            "code": "code",
            "notepad": "notepad",
            "calculator": "calculator",
            "calc": "calc",
            "explorer": "explorer",
            "edge": "msedge",
            "terminal": "windowsterminal",
            "cmd": "cmd",
            "powershell": "powershell",
            "task manager": "taskmgr",
            "taskmgr": "taskmgr",
            "blender": "blender"
        }
        search_target = alias_map.get(target, target)

        def _check_running():
            matches = []
            for p in psutil.process_iter(['pid', 'name']):
                try:
                    pname = (p.info.get('name') or "").lower()
                    base_pname = pname.replace(".exe", "").strip()
                    if base_pname and (search_target == base_pname or search_target in base_pname):
                        matches.append({
                            "pid": p.info.get('pid'),
                            "name": p.info.get('name')
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return matches

        matches = await asyncio.to_thread(_check_running)
        is_running = len(matches) > 0
        status_text = (
            f"Yes, **{arguments['application']}** is currently running ({len(matches)} process(es) found: "
            + ", ".join([f"PID `{m['pid']}`" for m in matches[:3]])
            + ")." if is_running else f"No, **{arguments['application']}** is not currently running."
        )

        return ToolResult(
            success=True,
            tool=self.name,
            data={
                "running": is_running,
                "application": arguments["application"],
                "matches": matches[:5]
            },
            message=status_text
        )


class GetActiveWindowTool(BaseTool):
    """Retrieves the title and application of the currently active/focused desktop window."""

    name = "get_active_window"
    description = "Returns the title and application of the currently active desktop window."
    category = "system"
    version = "1.0"
    permission_level = PermissionLevel.READ_ONLY
    requires_confirmation = False
    cacheable = False
    timeout_seconds = 3.0

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        def _get_active():
            try:
                import win32gui
                import win32process
                hwnd = win32gui.GetForegroundWindow()
                if not hwnd:
                    return {"title": "Desktop / No window active", "process": "explorer.exe", "pid": None}

                title = win32gui.GetWindowText(hwnd) or "Untitled Window"
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc_name = "unknown"
                try:
                    proc_name = psutil.Process(pid).name()
                except Exception:
                    pass

                return {"title": title, "process": proc_name, "pid": pid}
            except Exception as e:
                return {"error": str(e)}

        res = await asyncio.to_thread(_get_active)

        if "error" in res:
            return ToolResult(
                success=False,
                tool=self.name,
                error=res["error"],
                error_code="ACTIVE_WINDOW_ERROR",
                message=f"Could not determine active window: {res['error']}"
            )

        title = res["title"]
        pname = res["process"]
        pid_str = f" (PID `{res['pid']}`)" if res.get("pid") else ""

        return ToolResult(
            success=True,
            tool=self.name,
            data=res,
            message=f"**Active Window**: {title}\n**Application**: `{pname}`{pid_str}"
        )
