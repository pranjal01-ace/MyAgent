"""
Agent Router and Natural Language Action Dispatcher.

Parses incoming conversational text for structured action requests or natural language intent.
Routes tool execution through the centralized ToolRegistry and ToolExecutor.
"""

import re
import json
import asyncio
import logging
from typing import Optional, Tuple, Dict, Any

from backend.tools.schemas import ActionRequest, ToolResult, ToolContext, PermissionLevel
from backend.tools.registry import tool_registry
from backend.tools.executor import tool_executor
from backend.tools.permissions import permission_engine, permission_manager
from backend.tools.initialize import initialize_tools
from backend.agent.tools import TOOL_MAP

logger = logging.getLogger("ace.agent")

# Auto-initialize tools in registry
initialize_tools(tool_registry)


class AgentRouter:
    """Parses incoming requests for tool calls and executes them safely."""

    def __init__(self):
        self.registry = tool_registry
        self.executor = tool_executor

    def check_intent(self, text: str) -> Optional[Tuple[str, dict]]:
        """Identify if a user request triggers a tool call. Returns (tool_name, args)."""
        req = self.route_action(text)
        if req:
            return (req.tool, req.arguments)
        return None

    def route_action(self, text: str) -> Optional[ActionRequest]:
        """Maps user prompt text to a structured ActionRequest."""
        if not text or not isinstance(text, str):
            return None

        clean_text = text.strip()
        lowered = clean_text.lower()

        # 1. Structured JSON tool invocation
        json_match = re.search(r"\{.*?\"tool\"\s*:\s*\"([a-zA-Z0-9_]+)\".*?\}", clean_text, flags=re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                tool_name = parsed.get("tool")
                args = parsed.get("arguments", {})
                if self.registry.has(tool_name) or tool_name in TOOL_MAP:
                    return ActionRequest(tool=tool_name, arguments=args)
            except Exception:
                pass

        # 2. Phase 1 Desktop Tools: Natural Language Routing

        # Clipboard Clear
        if any(w in lowered for w in [
            "clear my clipboard", "clear clipboard", "empty my clipboard", "empty clipboard", "wipe clipboard"
        ]):
            return ActionRequest(tool="clear_clipboard", arguments={"confirmed": "yes" in lowered or "confirm" in lowered})

        # Clipboard Read
        if any(w in lowered for w in [
            "read my clipboard", "read clipboard", "what's on my clipboard",
            "what is on my clipboard", "what's in my clipboard", "what is in my clipboard",
            "check clipboard", "get clipboard", "paste clipboard"
        ]):
            return ActionRequest(tool="get_clipboard", arguments={})

        # Clipboard Write
        copy_match = re.search(r"(?:copy (?:this (?:text|json|code|data) )?to (?:my )?clipboard|write to clipboard|set clipboard|clipboard copy)\s*[:]?\s*(.+)", clean_text, re.IGNORECASE)
        if copy_match:
            return ActionRequest(tool="set_clipboard", arguments={"text": copy_match.group(1).strip()})

        # Notification
        notify_match = re.search(r"(?:notify me that|show notification|desktop notification|notify me[:]?|send notification[:]?)\s+(.+)", clean_text, re.IGNORECASE)
        if notify_match:
            return ActionRequest(tool="show_notification", arguments={"message": notify_match.group(1).strip()})

        # Active Window
        if any(w in lowered for w in [
            "active window", "current active application", "what window is active",
            "what's my active window", "current window", "focused window", "active app"
        ]):
            return ActionRequest(tool="get_active_window", arguments={})

        # Process Termination (Kill / Terminate)
        kill_match = re.search(r"(?:kill|terminate|stop|end task)\s+(?:process\s+)?([a-zA-Z0-9_\-\.]+)(?:\s+(?:pid\s+)?(\d+))?", lowered)
        if kill_match:
            target_str = kill_match.group(1).strip()
            extra_pid = kill_match.group(2)
            is_confirmed = "confirm" in lowered or "yes" in lowered

            if target_str.isdigit():
                return ActionRequest(tool="terminate_process", arguments={"pid": int(target_str), "confirmed": is_confirmed})
            elif extra_pid and extra_pid.isdigit():
                return ActionRequest(tool="terminate_process", arguments={"pid": int(extra_pid), "process_name": target_str, "confirmed": is_confirmed})
            else:
                return ActionRequest(tool="terminate_process", arguments={"process_name": target_str, "confirmed": is_confirmed})

        # Process Details
        proc_details_match = re.search(r"(?:process details|inspect process|details for process|process info for)\s+(?:pid\s+)?(\d+)", lowered)
        if proc_details_match:
            return ActionRequest(tool="get_process_details", arguments={"pid": int(proc_details_match.group(1))})

        # Process Search (e.g. "Find all Python processes", "Show Python processes")
        proc_search_match = re.search(r"(?:find|search|show|list)\s+(?:all\s+)?([a-zA-Z0-9_\-]+)\s+processes", lowered)
        if proc_search_match:
            target_q = proc_search_match.group(1).strip()
            if target_q not in ("all", "active", "running", "top"):
                return ActionRequest(tool="search_processes", arguments={"query": target_q})

        # Process List / Sort by CPU or RAM
        if any(w in lowered for w in ["what is using my cpu", "what's using my cpu", "what is using the most cpu", "cpu processes"]):
            return ActionRequest(tool="get_processes", arguments={"sort_by": "cpu"})
        if any(w in lowered for w in ["what is using my ram", "what's using my ram", "what is using the most ram", "what is using the most memory", "ram processes"]):
            return ActionRequest(tool="get_processes", arguments={"sort_by": "memory"})

        # System Specifications (Static/Host specs)
        if any(w in lowered for w in [
            "system specifications", "system specs", "my specs", "computer specs",
            "pc specs", "hardware specs", "system specifications?", "what are my pc specs",
            "show me my system information", "system information"
        ]):
            return ActionRequest(tool="get_system_info", arguments={})

        # Resource Utilization (Real-time CPU / RAM / Disk)
        if any(w in lowered for w in [
            "how much ram am i using", "how much ram", "how much cpu",
            "what is my cpu usage", "what's my cpu usage", "cpu usage", "ram usage",
            "memory usage", "resource usage", "resource status", "hardware status", "battery level",
            "how much disk space is available", "how much disk space"
        ]):
            return ActionRequest(tool="get_resource_usage", arguments={})

        if "system info" in lowered or "specs" in lowered:
            return ActionRequest(tool="get_system_info", arguments={})

        # Is Application Running
        is_running_match = re.search(
            r"is\s+([a-zA-Z0-9_\-\. ]+?)\s+(?:currently\s+)?running",
            lowered
        )
        if is_running_match:
            app_target = is_running_match.group(1).strip().rstrip("?")
            if app_target:
                return ActionRequest(tool="is_application_running", arguments={"application": app_target})

        # What programs are running / Process List
        if any(w in lowered for w in [
            "what programs are running", "what's running on my pc", "what is running on my pc",
            "what's running", "what is running", "running processes", "running programs",
            "process list", "list processes", "show processes", "active processes"
        ]):
            return ActionRequest(tool="get_processes", arguments={})

        # Folder Opening
        folder_match = re.search(r"open\s+(?:my\s+)?(downloads|documents|desktop|project|workspace|ace)\s*(?:folder|directory)?", lowered)
        if folder_match:
            return ActionRequest(tool="open_folder", arguments={"folder_path": folder_match.group(1)})
        folder_explicit = re.search(r"open\s+folder\s+[\"']?([^\"'\n]+)[\"']?", clean_text, re.IGNORECASE)
        if folder_explicit:
            return ActionRequest(tool="open_folder", arguments={"folder_path": folder_explicit.group(1).strip()})

        # File Opening
        file_explicit = re.search(r"open\s+file\s+[\"']?([^\"'\n]+)[\"']?", clean_text, re.IGNORECASE)
        if file_explicit:
            return ActionRequest(tool="open_file", arguments={"file_path": file_explicit.group(1).strip()})

        # Open Application
        app_match = re.search(
            r"open\s+(calculator|notepad|cmd|terminal|explorer|vs code|code|vscode|chrome|google chrome|edge|task manager|calc|powershell|blender|paint)(?:\.exe)?",
            lowered
        )
        if app_match:
            return ActionRequest(tool="open_application", arguments={"application": app_match.group(1)})

        # Open Website URL
        site_match = re.search(r"open\s+(https?://\S+|www\.\S+|\S+\.(?:com|org|net|io|edu|gov))", lowered)
        if site_match:
            return ActionRequest(tool="open_website", arguments={"url": site_match.group(1)})

        if "open youtube" in lowered:
            return ActionRequest(tool="open_application", arguments={"application": "youtube"})
        if "open github" in lowered:
            return ActionRequest(tool="open_application", arguments={"application": "github"})
        if "open google" in lowered:
            return ActionRequest(tool="open_application", arguments={"application": "google"})

        # Current Time
        if any(w in lowered for w in ["what time", "current time", "what's the time", "tell me the time", "date today"]):
            return ActionRequest(tool="get_time", arguments={})

        # Screenshot
        if any(w in lowered for w in ["take a screenshot", "capture screen", "screenshot my desktop", "take screenshot"]):
            return ActionRequest(tool="take_screenshot", arguments={})

        # Search Web
        search_match = re.search(r"(?:search web for|search google for|google|search online for)\s+(.+)", lowered)
        if search_match:
            return ActionRequest(tool="search_web", arguments={"query": search_match.group(1).strip()})

        # List Files
        if "list files" in lowered or "show files" in lowered or "what files are in" in lowered:
            dir_match = re.search(r"(?:in|inside)\s+([a-zA-Z0-9_\-\./\\]+)", lowered)
            target_dir = dir_match.group(1) if dir_match else "."
            return ActionRequest(tool="list_files", arguments={"directory": target_dir})

        # Read File
        read_match = re.search(r"(?:read file|show file|open file|view file)\s+([a-zA-Z0-9_\-\./\\]+)", lowered)
        if read_match:
            return ActionRequest(tool="read_file", arguments={"filepath": read_match.group(1).strip()})

        # Knowledge Base / RAG Search
        rag_match = re.search(r"(?:search knowledge|search docs|check notes for|look up in documents)\s+(.+)", lowered)
        if rag_match:
            return ActionRequest(tool="search_knowledge_base", arguments={"query": rag_match.group(1).strip()})

        return None

    def execute_tool(self, tool_name: str, args: dict) -> Tuple[bool, str]:
        """
        Synchronous/backward-compatible execution method.
        Executes through ToolExecutor or legacy fallback, returning (success: bool, output: str).
        """
        # Run through ToolExecutor
        request = ActionRequest(tool=tool_name, arguments=args)
        tool = self.registry.get(tool_name)

        if not tool and tool_name not in TOOL_MAP:
            return False, f"Unknown tool: '{tool_name}'"

        # Permission check
        allowed, level, reason = permission_manager.check_permission(tool_name, args)
        if not allowed:
            logger.warning(f"Tool '{tool_name}' requires confirmation ({level.value}): {reason}")
            return False, f"[Permission Required: {level.value}] {reason}"

        try:
            # Check if event loop is running
            try:
                loop = asyncio.get_running_loop()
                # Run executor in loop or thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(lambda: asyncio.run(self.executor.execute(request)))
                    result: ToolResult = future.result(timeout=10.0)
            except RuntimeError:
                result: ToolResult = asyncio.run(self.executor.execute(request))

            if result.success:
                return True, result.message or str(result.data)
            else:
                return False, result.error or result.message
        except Exception as e:
            # Fallback to direct TOOL_MAP execution if registered
            if tool_name in TOOL_MAP:
                try:
                    res = TOOL_MAP[tool_name](**args)
                    return True, str(res)
                except Exception as ex:
                    return False, f"Tool execution failed: {ex}"
            return False, f"Tool execution failed: {e}"

    async def execute_action(
        self,
        request: ActionRequest,
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        """Asynchronous execution of ActionRequest via ToolExecutor."""
        return await self.executor.execute(request, context)


agent_router = AgentRouter()
