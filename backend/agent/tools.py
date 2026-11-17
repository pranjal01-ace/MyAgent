import os
import re
import sys
import shutil
import urllib.parse
import datetime
import subprocess
import webbrowser
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from backend.config import settings

logger = logging.getLogger("ace.tools")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Safe directory anchors - strictly canonicalized
ALLOWED_ROOTS = [
    BASE_DIR.resolve(),
    (Path.home() / "Desktop").resolve(),
    (Path.home() / "Documents").resolve(),
    (Path.home() / "Downloads").resolve()
]

def resolve_workspace_path(path_str: str) -> Path:
    """Canonical path validator ensuring paths never escape the approved workspace boundaries.
    
    Rejects:
      - Null bytes and encoded traversal characters
      - Relative traversal (e.g., ../, ..\\)
      - Absolute paths outside allowed roots
      - Symlinks pointing outside allowed roots
    """
    if not path_str or not isinstance(path_str, str):
        raise ValueError("Invalid path input: path must be a non-empty string.")

    if "\x00" in path_str:
        raise PermissionError("Null byte injection detected in path.")

    # URL-decode any percent-encoded traversal sequences
    decoded_path = urllib.parse.unquote(path_str).strip()
    if "\x00" in decoded_path:
        raise PermissionError("Null byte injection detected in decoded path.")

    p = Path(decoded_path).expanduser()
    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (BASE_DIR / p).resolve()

    # Check that resolved canonical path resides strictly inside an allowed root
    for root in ALLOWED_ROOTS:
        try:
            if root.exists() and (resolved == root or resolved.is_relative_to(root)):
                return resolved
        except Exception:
            pass

    raise PermissionError(f"Access denied: Path '{path_str}' is outside approved workspace directories.")

def _is_path_allowed(path_str: str) -> Tuple[bool, Path]:
    """Helper preserving backward compatibility for existing callers returning (is_allowed, resolved_path)."""
    try:
        resolved = resolve_workspace_path(path_str)
        return True, resolved
    except (PermissionError, ValueError) as e:
        logger.warning(f"Path access restriction triggered: {e}")
        # Return fallback safe path or attempted path with False
        try:
            fallback = Path(path_str).resolve()
        except Exception:
            fallback = BASE_DIR
        return False, fallback

# ----------------- Tool Implementations -----------------

def get_current_time() -> str:
    """Returns current date and time."""
    now = datetime.datetime.now()
    return f"Current time is {now.strftime('%A, %B %d, %Y at %I:%M %p')}."

def get_system_info() -> str:
    """Returns CPU, RAM, disk usage, and battery statistics."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.3)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        battery = psutil.sensors_battery()
        bat_str = f" | Battery: {battery.percent}%" if battery else ""
        return (
            f"CPU: {cpu}% | RAM: {ram.percent}% ({ram.used // (1024**2)}MB / {ram.total // (1024**2)}MB) | "
            f"Disk: {disk.percent}% used{bat_str}"
        )
    except Exception as e:
        return f"Error fetching system metrics: {e}"

def open_website(url: str) -> str:
    """Opens a website URL in the default web browser."""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    webbrowser.open(url)
    return f"Opened website: {url}"

def search_web(query: str) -> str:
    """Performs a web search using default browser."""
    url = f"https://www.google.com/search?q={query}"
    webbrowser.open(url)
    return f"Searched web for: {query}"

# Explicit application allowlist: maps app aliases to safe executable command lists
ALLOWED_APPLICATIONS: Dict[str, List[str]] = {
    "calculator": ["calc.exe"],
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
    "edge": ["msedge"],
    "browser": ["https://www.google.com"]
}

# Dangerous shell metacharacters prohibited in any application input
SHELL_METACHAR_PATTERN = re.compile(r"[&|;$`><\r\n\(\)]")

def open_application(app_name: str) -> str:
    """Launches common Windows desktop applications safely without shell execution."""
    if not app_name or not isinstance(app_name, str):
        return "Invalid application name."

    # Immediate rejection of command chaining, redirection, or substitution metacharacters
    if SHELL_METACHAR_PATTERN.search(app_name):
        logger.warning(f"Security Alert: Blocked suspicious shell metacharacters in open_application: '{app_name}'")
        return f"Access denied: Invalid application target '{app_name}' contains prohibited characters."

    clean_name = app_name.strip()
    clean_lower = clean_name.lower()

    if clean_lower in ALLOWED_APPLICATIONS:
        cmd_target = ALLOWED_APPLICATIONS[clean_lower]
        if cmd_target[0].startswith("http"):
            webbrowser.open(cmd_target[0])
            return f"Opened {app_name} in browser."

        try:
            # shell=False is strictly enforced with argument list
            subprocess.Popen(cmd_target, shell=False)
            return f"Launched application: {app_name}"
        except Exception as e:
            return f"Failed to launch '{app_name}': {e}"

    # If an explicit executable name was supplied, verify it strictly matches safe pattern [a-zA-Z0-9_\-\.]+
    if re.fullmatch(r"^[a-zA-Z0-9_\-\.]+\.(exe|bat|cmd)$", clean_name, re.IGNORECASE) or re.fullmatch(r"^[a-zA-Z0-9_\-]+$", clean_name):
        # Resolve via PATH safely
        resolved_exe = shutil.which(clean_name)
        if resolved_exe:
            try:
                subprocess.Popen([resolved_exe], shell=False)
                return f"Launched application: {clean_name}"
            except Exception as e:
                return f"Failed to launch '{clean_name}': {e}"

    return f"Application '{app_name}' is not in the approved application allowlist."

def read_clipboard() -> str:
    """Reads text content from Windows clipboard."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                return f"Clipboard text: {data}"
            return "Clipboard is empty or contains non-text content."
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        try:
            from tkinter import Tk
            r = Tk()
            r.withdraw()
            data = r.clipboard_get()
            r.destroy()
            return f"Clipboard text: {data}"
        except Exception as e:
            return f"Could not read clipboard: {e}"

def write_clipboard(text: str) -> str:
    """Copies text to Windows clipboard."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            return "Successfully copied text to clipboard."
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        try:
            from tkinter import Tk
            r = Tk()
            r.withdraw()
            r.clipboard_clear()
            r.clipboard_append(text)
            r.update()
            r.destroy()
            return "Copied text to clipboard."
        except Exception as e:
            return f"Failed to write clipboard: {e}"

def take_screenshot() -> str:
    """Captures a screenshot of the desktop and saves it to data/screenshots/."""
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = SCREENSHOTS_DIR / f"screenshot_{timestamp}.png"
        img.save(file_path)
        return f"Screenshot saved successfully to {file_path.name}"
    except Exception as e:
        return f"Failed to capture screenshot: {e}"

def list_files(directory: str = ".") -> str:
    """Lists files and folders inside specified directory."""
    allowed, path = _is_path_allowed(directory)
    if not allowed or not path.exists():
        return f"Directory not found or access restricted: {directory}"

    try:
        entries = []
        for p in list(path.iterdir())[:40]:
            kind = "[DIR]" if p.is_dir() else "[FILE]"
            entries.append(f"{kind} {p.name}")
        return f"Files in {path.name}:\n" + "\n".join(entries) if entries else f"{path.name} is empty."
    except Exception as e:
        return f"Error listing directory: {e}"

def read_file(filepath: str) -> str:
    """Reads text content of a file (up to 4000 characters)."""
    allowed, path = _is_path_allowed(filepath)
    if not allowed or not path.exists() or not path.is_file():
        return f"File does not exist or access restricted: {filepath}"

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(4000)
            return f"Content of {path.name}:\n{content}"
    except Exception as e:
        return f"Error reading file {filepath}: {e}"

def create_file(filepath: str, content: str = "") -> str:
    """Creates a new text file with optional initial content."""
    allowed, path = _is_path_allowed(filepath)
    if not allowed:
        return f"Access restricted for path: {filepath}"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully created file: {path.name}"
    except Exception as e:
        return f"Error creating file {filepath}: {e}"

def write_file(filepath: str, content: str = "") -> str:
    """Writes or appends text to a file."""
    return create_file(filepath, content)

def copy_file(source: str, destination: str) -> str:
    """Copies a file to a new destination."""
    allow_src, src = _is_path_allowed(source)
    allow_dst, dst = _is_path_allowed(destination)
    if not allow_src or not src.exists():
        return f"Source file does not exist or access denied: {source}"
    if not allow_dst:
        return f"Destination path access denied: {destination}"

    try:
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return f"Successfully copied from {src.name} to {dst.name}"
    except Exception as e:
        return f"Failed to copy file: {e}"

def move_file(source: str, destination: str) -> str:
    """Moves a file or folder to a new location."""
    allow_src, src = _is_path_allowed(source)
    allow_dst, dst = _is_path_allowed(destination)
    if not allow_src or not src.exists():
        return f"Source file does not exist: {source}"
    if not allow_dst:
        return f"Destination path access denied: {destination}"

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dst)
        return f"Successfully moved {src.name} to {dst.name}"
    except Exception as e:
        return f"Failed to move file: {e}"

def search_knowledge_base(query: str) -> str:
    """Searches indexed documents and RAG vector store for context."""
    try:
        from voice_assistant.rag.retriever import RAGRetriever
        retriever = RAGRetriever()
        results = retriever.retrieve(query, top_k=3)
        if results:
            context = "\n---\n".join([f"Source: {r.source}\n{r.content}" for r in results])
            return f"Relevant Knowledge:\n{context}"
        return f"No matching documents found in knowledge base for: {query}"
    except Exception as e:
        logger.warning(f"RAG search error: {e}")
        return f"Knowledge base lookup unavailable: {e}"

# Tool registry
TOOL_MAP = {
    "get_time": get_current_time,
    "get_system_info": get_system_info,
    "open_website": open_website,
    "search_web": search_web,
    "open_application": open_application,
    "read_clipboard": read_clipboard,
    "write_clipboard": write_clipboard,
    "get_clipboard": read_clipboard,
    "set_clipboard": write_clipboard,
    "take_screenshot": take_screenshot,
    "list_files": list_files,
    "read_file": read_file,
    "create_file": create_file,
    "write_file": write_file,
    "copy_file": copy_file,
    "move_file": move_file,
    "search_knowledge_base": search_knowledge_base
}


def execute_safe_tool(tool_name: str, **kwargs) -> Tuple[bool, str]:
    """Executes a desktop tool with safety checking."""
    from backend.agent.permissions import permission_manager
    if tool_name not in TOOL_MAP:
        return False, f"Unknown tool: '{tool_name}'"

    allowed, level, reason = permission_manager.check_permission(tool_name, kwargs)
    if not allowed:
        return False, f"[Permission Required: {level.value}] {reason}"

    try:
        func = TOOL_MAP[tool_name]
        result = func(**kwargs)
        return True, str(result)
    except Exception as e:
        logger.error(f"Error executing safe tool '{tool_name}': {e}")
        return False, f"Tool execution failed: {e}"

