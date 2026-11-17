"""
Application Launcher Tool.

Launches common desktop applications safely without shell execution.
Enforces strict allowlist verification and shell metacharacter rejection.
"""

import os
import re
import shutil
import asyncio
import subprocess
import webbrowser
import logging
from typing import Dict, Any, List

from backend.tools.base import BaseTool
from backend.tools.schemas import PermissionLevel, ToolResult, ToolContext
from backend.tools.errors import ToolValidationError, ToolPermissionDenied

logger = logging.getLogger("ace.tools.launcher")

# Dangerous shell metacharacters prohibited in any application input
SHELL_METACHAR_PATTERN = re.compile(r"[&|;$`><\r\n\(\)]")

# Default controlled application registry / allowlist
DEFAULT_ALLOWED_APPLICATIONS: Dict[str, List[str]] = {
    "calculator": ["calc.exe"],
    "calc": ["calc.exe"],
    "notepad": ["notepad.exe"],
    "cmd": ["cmd.exe"],
    "terminal": ["wt.exe"],
    "powershell": ["powershell.exe"],
    "explorer": ["explorer.exe"],
    "task manager": ["taskmgr.exe"],
    "taskmgr": ["taskmgr.exe"],
    "code": ["code"],
    "vs code": ["code"],
    "vscode": ["code"],
    "chrome": ["chrome"],
    "google chrome": ["chrome"],
    "edge": ["msedge"],
    "browser": ["https://www.google.com"],
    "youtube": ["https://www.youtube.com"],
    "github": ["https://www.github.com"],
    "google": ["https://www.google.com"],
    "blender": ["blender.exe"],
    "paint": ["mspaint.exe"]
}

# Standard Windows application install directories when not present on system PATH
COMMON_APP_PATHS: Dict[str, List[str]] = {
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ],
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "code": [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
    ],
}


class OpenApplicationTool(BaseTool):
    """Launches approved desktop applications safely from a verified allowlist."""

    name = "open_application"
    description = "Launches an approved local application (e.g., Chrome, VS Code, Notepad, Calculator)."
    category = "applications"
    version = "1.0"
    permission_level = PermissionLevel.LOW
    requires_confirmation = False
    cacheable = False
    timeout_seconds = 8.0

    def __init__(self, allowed_apps: Dict[str, List[str]] = None):
        super().__init__()
        self.allowed_apps = allowed_apps or DEFAULT_ALLOWED_APPLICATIONS

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "application": {
                    "type": "string",
                    "description": "Name of approved application to launch (e.g., 'chrome', 'notepad', 'calculator')"
                }
            },
            "required": ["application"]
        }

    def validate(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        app = arguments.get("application") or arguments.get("app_name") or arguments.get("name")
        if not app or not isinstance(app, str) or not app.strip():
            raise ToolValidationError("Argument 'application' must be a non-empty string.")

        clean_name = app.strip()
        if SHELL_METACHAR_PATTERN.search(clean_name):
            logger.warning(f"Security Alert: Blocked shell metacharacters in open_application: '{clean_name}'")
            raise ToolValidationError(f"Invalid application target '{clean_name}': contains prohibited shell characters.")

        clean_lower = clean_name.lower()
        if clean_lower not in self.allowed_apps:
            # Must be a single valid executable name without arguments or flags
            if not (re.fullmatch(r"^[a-zA-Z0-9_\-\.]+\.(exe|bat|cmd)$", clean_name, re.IGNORECASE) or re.fullmatch(r"^[a-zA-Z0-9_\-]+$", clean_name)):
                raise ToolValidationError(f"Invalid application target '{clean_name}': arbitrary command line arguments are not permitted.")

        return {"application": clean_name}

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        app_name = arguments["application"]
        clean_lower = app_name.lower().strip()

        # 1. Check Allowlist
        if clean_lower in self.allowed_apps:
            cmd_target = self.allowed_apps[clean_lower]
            if cmd_target[0].startswith("http"):
                await asyncio.to_thread(webbrowser.open, cmd_target[0])
                return ToolResult(
                    success=True,
                    tool=self.name,
                    data={"launched": True, "target": cmd_target[0], "mode": "browser"},
                    message=f"Opened {app_name} in browser."
                )

            launch_args = list(cmd_target)
            exe_name = launch_args[0].lower().strip()
            if not shutil.which(exe_name) and exe_name in COMMON_APP_PATHS:
                for candidate in COMMON_APP_PATHS[exe_name]:
                    if os.path.exists(candidate):
                        launch_args[0] = candidate
                        break

            def _launch_cmd():
                # shell=False strictly enforced
                subprocess.Popen(launch_args, shell=False)

            try:
                await asyncio.to_thread(_launch_cmd)
                return ToolResult(
                    success=True,
                    tool=self.name,
                    data={"launched": True, "application": app_name, "command": launch_args},
                    message=f"Launched application: {app_name}"
                )
            except Exception as e:
                return ToolResult(
                    success=False,
                    tool=self.name,
                    error=f"Failed to launch '{app_name}': {e}",
                    error_code="LAUNCH_FAILED",
                    message=f"Could not launch application '{app_name}'."
                )

        # 2. Check explicit safe executable name resolving on PATH
        if re.fullmatch(r"^[a-zA-Z0-9_\-\.]+\.(exe|bat|cmd)$", app_name, re.IGNORECASE) or re.fullmatch(r"^[a-zA-Z0-9_\-]+$", app_name):
            resolved_exe = shutil.which(app_name)
            if resolved_exe:
                try:
                    await asyncio.to_thread(subprocess.Popen, [resolved_exe], shell=False)
                    return ToolResult(
                        success=True,
                        tool=self.name,
                        data={"launched": True, "application": app_name, "path": resolved_exe},
                        message=f"Launched application: {app_name}"
                    )
                except Exception as e:
                    return ToolResult(
                        success=False,
                        tool=self.name,
                        error=f"Failed to launch executable '{app_name}': {e}",
                        error_code="LAUNCH_FAILED",
                        message=f"Could not launch '{app_name}'."
                    )

        # Unknown or unapproved application rejected
        raise ToolPermissionDenied(
            tool_name=self.name,
            reason=f"Application '{app_name}' is not in the approved application allowlist."
        )


class OpenFolderTool(BaseTool):
    """Safely opens a local directory in Windows File Explorer."""

    name = "open_folder"
    description = "Opens a local directory or user folder (Downloads, Documents, Desktop, Project) in File Explorer."
    category = "applications"
    version = "1.0"
    permission_level = PermissionLevel.SAFE_ACTION
    requires_confirmation = False
    cacheable = False
    timeout_seconds = 5.0

    FOLDER_SHORTCUTS = {
        "downloads": lambda: os.path.expanduser("~/Downloads"),
        "download": lambda: os.path.expanduser("~/Downloads"),
        "documents": lambda: os.path.expanduser("~/Documents"),
        "docs": lambda: os.path.expanduser("~/Documents"),
        "desktop": lambda: os.path.expanduser("~/Desktop"),
        "project": lambda: r"D:\Ace_Ai",
        "ace": lambda: r"D:\Ace_Ai",
        "workspace": lambda: r"D:\Ace_Ai",
    }

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "folder_path": {
                    "type": "string",
                    "description": "Path or folder name to open (e.g. 'Downloads', 'D:\\Ace_Ai', 'Documents')"
                }
            },
            "required": ["folder_path"]
        }

    def validate(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = arguments.get("folder_path") or arguments.get("path") or arguments.get("folder")
        if not raw_path or not isinstance(raw_path, str) or not raw_path.strip():
            raise ToolValidationError("Argument 'folder_path' must be a non-empty string.")

        clean = raw_path.strip()
        if SHELL_METACHAR_PATTERN.search(clean):
            raise ToolValidationError(f"Invalid folder path '{clean}': contains prohibited shell characters.")

        # Check friendly shortcuts
        lower_clean = clean.lower()
        if lower_clean in self.FOLDER_SHORTCUTS:
            resolved = self.FOLDER_SHORTCUTS[lower_clean]()
        else:
            resolved = os.path.realpath(os.path.abspath(clean))

        if not os.path.exists(resolved):
            raise ToolValidationError(f"Folder does not exist: '{resolved}'")
        if not os.path.isdir(resolved):
            raise ToolValidationError(f"Path is not a directory: '{resolved}'")

        return {"folder_path": resolved}

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        folder = arguments["folder_path"]

        def _open():
            os.startfile(folder)

        try:
            await asyncio.to_thread(_open)
            return ToolResult(
                success=True,
                tool=self.name,
                data={"opened": True, "folder": folder},
                message=f"✓ Opened folder: `{folder}`"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                tool=self.name,
                error=str(e),
                error_code="FOLDER_OPEN_FAILED",
                message=f"✕ Could not open folder: {e}"
            )


class OpenFileTool(BaseTool):
    """Safely opens a document or data file with the default registered OS program."""

    name = "open_file"
    description = "Opens a file with the system default application. Executable scripts and binaries are prohibited."
    category = "applications"
    version = "1.0"
    permission_level = PermissionLevel.SAFE_ACTION
    requires_confirmation = False
    cacheable = False
    timeout_seconds = 5.0

    # Strict list of prohibited executable extensions to prevent arbitrary binary execution
    DISALLOWED_EXTENSIONS = {
        ".exe", ".bat", ".cmd", ".ps1", ".vbs", ".msi", ".com", ".scr", ".reg",
        ".jar", ".wsf", ".cpl", ".msc", ".hta"
    }

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to file to open (e.g. 'notes.txt', 'image.png')"
                }
            },
            "required": ["file_path"]
        }

    def validate(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = arguments.get("file_path") or arguments.get("path") or arguments.get("file")
        if not raw_path or not isinstance(raw_path, str) or not raw_path.strip():
            raise ToolValidationError("Argument 'file_path' must be a non-empty string.")

        clean = raw_path.strip()
        if SHELL_METACHAR_PATTERN.search(clean):
            raise ToolValidationError(f"Invalid file path '{clean}': contains prohibited shell characters.")

        resolved = os.path.realpath(os.path.abspath(clean))

        # Check file extension safety
        _, ext = os.path.splitext(resolved)
        if ext.lower() in self.DISALLOWED_EXTENSIONS:
            raise ToolValidationError(f"Security Alert: Cannot open executable/script file type '{ext}' via open_file.")

        if not os.path.exists(resolved):
            raise ToolValidationError(f"File does not exist: '{resolved}'")
        if not os.path.isfile(resolved):
            raise ToolValidationError(f"Path is not a file: '{resolved}'")

        return {"file_path": resolved}

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        filepath = arguments["file_path"]

        def _open():
            os.startfile(filepath)

        try:
            await asyncio.to_thread(_open)
            return ToolResult(
                success=True,
                tool=self.name,
                data={"opened": True, "file": filepath},
                message=f"✓ Opened file: `{filepath}`"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                tool=self.name,
                error=str(e),
                error_code="FILE_OPEN_FAILED",
                message=f"✕ Could not open file: {e}"
            )
