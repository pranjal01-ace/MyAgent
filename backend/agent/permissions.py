import enum
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger("ace.permissions")

class PermissionLevel(str, enum.Enum):
    SAFE = "SAFE"           # Auto-execute without prompt (read-only, harmless)
    CONFIRM = "CONFIRM"     # Requires explicit confirmation (file writes/moves)
    DANGEROUS = "DANGEROUS" # Requires high-alert confirmation (deletions, execution)

# Permission policy registry for all desktop mate tools
TOOL_PERMISSIONS: Dict[str, PermissionLevel] = {
    "get_time": PermissionLevel.SAFE,
    "get_system_info": PermissionLevel.SAFE,
    "get_resource_usage": PermissionLevel.SAFE,
    "get_processes": PermissionLevel.SAFE,
    "is_application_running": PermissionLevel.SAFE,
    "open_website": PermissionLevel.SAFE,
    "search_web": PermissionLevel.SAFE,
    "open_application": PermissionLevel.SAFE,
    "read_clipboard": PermissionLevel.SAFE,
    "get_clipboard": PermissionLevel.SAFE,
    "take_screenshot": PermissionLevel.SAFE,
    "show_notification": PermissionLevel.SAFE,
    "list_files": PermissionLevel.SAFE,
    "read_file": PermissionLevel.SAFE,
    "search_knowledge_base": PermissionLevel.SAFE,
    "analyze_screen": PermissionLevel.SAFE,

    # File modification tools
    "set_clipboard": PermissionLevel.CONFIRM,
    "write_clipboard": PermissionLevel.CONFIRM,
    "create_file": PermissionLevel.CONFIRM,
    "write_file": PermissionLevel.CONFIRM,
    "move_file": PermissionLevel.CONFIRM,
    "copy_file": PermissionLevel.CONFIRM,

    # Dangerous tools
    "delete_file": PermissionLevel.DANGEROUS,
    "run_shell_command": PermissionLevel.DANGEROUS
}

class PermissionManager:
    """Validates tool execution permissions and maintains confirmation state."""

    def __init__(self):
        self.always_allowed: set[str] = set()

    def check_permission(self, tool_name: str, arguments: dict) -> Tuple[bool, PermissionLevel, str]:
        """Check if tool can be executed automatically or needs confirmation."""
        level = TOOL_PERMISSIONS.get(tool_name, PermissionLevel.CONFIRM)

        if level == PermissionLevel.SAFE:
            return True, level, "Auto-approved safe operation."

        if tool_name in self.always_allowed:
            return True, level, f"Approved by 'Always Allow' rule for {tool_name}."

        desc = f"Action requires user confirmation: {tool_name} with arguments {arguments}"
        return False, level, desc

    def grant_always_allow(self, tool_name: str):
        self.always_allowed.add(tool_name)
        logger.info(f"Granted 'always allow' permission to tool: {tool_name}")

permission_manager = PermissionManager()
