"""
Desktop Notification Tool.

Displays native Windows balloon and toast notifications.
Sanitizes titles and messages against injection attacks.
"""

import re
import asyncio
import subprocess
import logging
from typing import Dict, Any

from backend.tools.base import BaseTool
from backend.tools.schemas import PermissionLevel, ToolResult, ToolContext
from backend.tools.errors import ToolValidationError

logger = logging.getLogger("ace.tools.notification")


class ShowNotificationTool(BaseTool):
    """Displays a native desktop notification balloon / toast on Windows."""

    name = "show_notification"
    description = "Displays a desktop notification with a title and message."
    category = "notifications"
    version = "1.0"
    permission_level = PermissionLevel.LOW
    requires_confirmation = False
    cacheable = False
    timeout_seconds = 6.0

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Notification body message to display"
                },
                "title": {
                    "type": "string",
                    "description": "Notification title (default: 'Ace AI')",
                    "default": "Ace AI"
                }
            },
            "required": ["message"]
        }

    def validate(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        msg = arguments.get("message") or arguments.get("text")
        if not msg or not isinstance(msg, str) or not msg.strip():
            raise ToolValidationError("Argument 'message' must be a non-empty string.")

        title = arguments.get("title") or "Ace AI"
        if not isinstance(title, str):
            title = "Ace AI"

        # Sanitize single quotes and control characters for safe PowerShell embedding
        safe_msg = re.sub(r"[\r\n\x00]", " ", msg.strip()).replace("'", "''")[:300]
        safe_title = re.sub(r"[\r\n\x00]", " ", title.strip()).replace("'", "''")[:100]

        return {
            "message": safe_msg,
            "title": safe_title,
            "raw_message": msg.strip()
        }

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        safe_title = arguments["title"]
        safe_msg = arguments["message"]
        raw_msg = arguments.get("raw_message", safe_msg)

        def _display_notification():
            ps_script = (
                "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
                "$notify = New-Object System.Windows.Forms.NotifyIcon;"
                "$notify.Icon = [System.Drawing.SystemIcons]::Information;"
                "$notify.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info;"
                f"$notify.BalloonTipTitle = '{safe_title}';"
                f"$notify.BalloonTipText = '{safe_msg}';"
                "$notify.Visible = $True;"
                "$notify.ShowBalloonTip(3000);"
                "Start-Sleep -Milliseconds 250;"
                "$notify.Dispose();"
            )

            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=5
            )
            return res.returncode == 0, res.stderr

        success, err = await asyncio.to_thread(_display_notification)
        if success:
            return ToolResult(
                success=True,
                tool=self.name,
                data={"displayed": True, "title": safe_title, "message": raw_msg},
                message=f"Displayed desktop notification: '{raw_msg}'"
            )
        else:
            return ToolResult(
                success=False,
                tool=self.name,
                error=f"Notification error: {err}",
                error_code="NOTIFICATION_FAILED",
                message=f"Could not display notification: {err}"
            )
