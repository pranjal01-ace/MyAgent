"""
Windows Clipboard Read and Write Tools.

Enforces zero-persistence privacy rules:
Clipboard contents are marked sensitive=True, store_in_memory=False, cacheable=False.
Neither read nor written clipboard texts are ever written to audit logs, memory, or persistent database.
"""

import asyncio
import logging
from typing import Dict, Any

from backend.tools.base import BaseTool
from backend.tools.schemas import PermissionLevel, ToolResult, ToolContext
from backend.tools.errors import ToolValidationError, ToolUnavailable

logger = logging.getLogger("ace.tools.clipboard")


class GetClipboardTool(BaseTool):
    """Reads text content from the Windows clipboard safely."""

    name = "get_clipboard"
    description = "Reads current text content from the desktop clipboard."
    category = "clipboard"
    version = "1.0"
    permission_level = PermissionLevel.AUTOMATIC
    requires_confirmation = False

    # Zero-Persistence Policy
    sensitive = True
    store_in_memory = False
    cacheable = False
    timeout_seconds = 4.0

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        def _read():
            # 1. Try pywin32 win32clipboard
            try:
                import win32clipboard
                win32clipboard.OpenClipboard()
                try:
                    if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                        text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                        return True, text
                    return False, "Clipboard is empty or contains non-text data."
                finally:
                    win32clipboard.CloseClipboard()
            except Exception:
                pass

            # 2. Try Tkinter fallback
            try:
                from tkinter import Tk
                r = Tk()
                r.withdraw()
                text = r.clipboard_get()
                r.destroy()
                return True, text
            except Exception as e:
                return False, f"Could not access clipboard: {e}"

        success, content = await asyncio.to_thread(_read)
        if success:
            display_preview = content[:60] + "..." if len(content) > 60 else content
            return ToolResult(
                success=True,
                tool=self.name,
                data={"text": content, "character_count": len(content)},
                message=f"Clipboard contents: {content}"
            )
        else:
            return ToolResult(
                success=False,
                tool=self.name,
                error=content,
                error_code="CLIPBOARD_READ_FAILED",
                message=content
            )


class SetClipboardTool(BaseTool):
    """Copies text to the Windows clipboard."""

    name = "set_clipboard"
    description = "Copies specified text string to the desktop clipboard."
    category = "clipboard"
    version = "1.0"
    permission_level = PermissionLevel.LOW
    requires_confirmation = False

    # Zero-Persistence Policy
    sensitive = True
    store_in_memory = False
    cacheable = False
    timeout_seconds = 4.0

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to write to the clipboard"
                }
            },
            "required": ["text"]
        }

    def validate(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        text = arguments.get("text")
        if text is None or not isinstance(text, str):
            raise ToolValidationError("Argument 'text' must be a string.")
        return {"text": text}

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        text_to_copy = arguments["text"]

        def _write():
            # 1. Try pywin32 win32clipboard
            try:
                import win32clipboard
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardText(text_to_copy, win32clipboard.CF_UNICODETEXT)
                    return True, None
                finally:
                    win32clipboard.CloseClipboard()
            except Exception:
                pass

            # 2. Try Tkinter fallback
            try:
                from tkinter import Tk
                r = Tk()
                r.withdraw()
                r.clipboard_clear()
                r.clipboard_append(text_to_copy)
                r.update()
                r.destroy()
                return True, None
            except Exception as e:
                return False, f"Could not write to clipboard: {e}"

        success, err = await asyncio.to_thread(_write)
        if success:
            return ToolResult(
                success=True,
                tool=self.name,
                data={"copied": True, "character_count": len(text_to_copy)},
                message=f"Successfully copied {len(text_to_copy)} characters to clipboard."
            )
        else:
            return ToolResult(
                success=False,
                tool=self.name,
                error=err,
                error_code="CLIPBOARD_WRITE_FAILED",
                message=f"Failed to copy to clipboard: {err}"
            )


class ClearClipboardTool(BaseTool):
    """Clears all content from the Windows clipboard safely."""

    name = "clear_clipboard"
    description = "Clears all text and data from the desktop clipboard."
    category = "clipboard"
    version = "1.0"
    permission_level = PermissionLevel.CONFIRMATION_REQUIRED
    requires_confirmation = True

    # Zero-Persistence Policy
    sensitive = True
    store_in_memory = False
    cacheable = False
    timeout_seconds = 4.0

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "confirmed": {
                    "type": "boolean",
                    "description": "Confirmation flag to clear clipboard",
                    "default": False
                }
            },
            "required": []
        }

    def validate(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = dict(arguments or {})
        cleaned["confirmed"] = bool(cleaned.get("confirmed", False))
        return cleaned

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        is_confirmed = arguments.get("confirmed", False) or getattr(context, "confirmed", False)
        if not is_confirmed:
            return ToolResult(
                success=False,
                tool=self.name,
                error="Confirmation Required",
                error_code="CONFIRMATION_REQUIRED",
                message="⚠️ **Confirmation Required**: Are you sure you want to clear the clipboard? Please reply *'Yes, clear clipboard'* to confirm.",
                data={"pending_confirmation": True}
            )

        def _clear():
            # 1. Try win32clipboard
            try:
                import win32clipboard
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    return True, None
                finally:
                    win32clipboard.CloseClipboard()
            except Exception:
                pass

            # 2. Try Tkinter fallback
            try:
                from tkinter import Tk
                r = Tk()
                r.withdraw()
                r.clipboard_clear()
                r.update()
                r.destroy()
                return True, None
            except Exception as e:
                return False, f"Could not clear clipboard: {e}"

        success, err = await asyncio.to_thread(_clear)
        if success:
            return ToolResult(
                success=True,
                tool=self.name,
                data={"cleared": True},
                message="✓ Desktop clipboard has been cleared."
            )
        else:
            return ToolResult(
                success=False,
                tool=self.name,
                error=err,
                error_code="CLIPBOARD_CLEAR_FAILED",
                message=f"✕ Failed to clear clipboard: {err}"
            )
