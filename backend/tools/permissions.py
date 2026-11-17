"""
Permission Engine and Confirmation Policy System.

Evaluates tool permission levels and arguments to enforce strict security boundaries.
Ensures that only the Permission Engine (not the LLM) decides confirmation requirements.
"""

import logging
from typing import Dict, Any, Tuple, Optional, Set
from backend.tools.schemas import PermissionLevel

logger = logging.getLogger("ace.tools.permissions")


class PermissionEngine:
    """
    Evaluates tool execution security policies, argument constraints,
    and user confirmation requirements.
    """

    def __init__(self):
        # Tools explicitly permitted to bypass confirmation prompts by user override
        self.always_allowed: Set[str] = set()
        # Custom permission level overrides by tool name
        self.overrides: Dict[str, PermissionLevel] = {}

    def set_permission_override(self, tool_name: str, level: PermissionLevel) -> None:
        """Dynamically override default permission level for a tool."""
        self.overrides[tool_name.lower()] = level
        logger.info(f"Set permission override for '{tool_name}' to {level.value}")

    def grant_always_allow(self, tool_name: str) -> None:
        """Grant permanent confirmation bypass to a specific tool."""
        self.always_allowed.add(tool_name.lower())
        logger.info(f"Granted 'always allow' permission to tool: '{tool_name}'")

    def revoke_always_allow(self, tool_name: str) -> None:
        """Revoke permanent confirmation bypass for a tool."""
        self.always_allowed.discard(tool_name.lower())
        logger.info(f"Revoked 'always allow' permission for tool: '{tool_name}'")

    def evaluate(
        self,
        tool_name: str,
        default_level: PermissionLevel,
        requires_tool_confirmation: bool,
        arguments: Dict[str, Any],
        confirmed: bool = False
    ) -> Tuple[bool, PermissionLevel, str, bool]:
        """
        Evaluates execution request against security policies.

        Returns:
            (allowed: bool, level: PermissionLevel, reason: str, needs_confirmation: bool)
        """
        clean_name = tool_name.lower().strip()
        effective_level = self.overrides.get(clean_name, default_level)

        # 1. AUTOMATIC: Safe read-only operations always allowed without confirmation
        if effective_level == PermissionLevel.AUTOMATIC:
            return True, effective_level, "Auto-approved safe operation.", False

        # 2. Check if tool is explicitly in user 'always allowed' set
        if clean_name in self.always_allowed:
            return True, effective_level, f"Approved by user 'Always Allow' rule for '{tool_name}'.", False

        # 3. LOW level: Typically auto-allowed unless the tool explicitly requests confirmation
        if effective_level == PermissionLevel.LOW and not requires_tool_confirmation:
            return True, effective_level, "Auto-approved low-risk local action.", False

        # 4. MEDIUM, HIGH, CRITICAL, or tool-flagged requires explicit confirmation
        if confirmed:
            return True, effective_level, f"User explicitly confirmed execution of '{tool_name}'.", False

        # Confirmation is required and not yet given
        desc = f"Action requires user confirmation: '{tool_name}' ({effective_level.value})"
        return False, effective_level, desc, True

    def check_permission(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        confirmed: bool = False
    ) -> Tuple[bool, PermissionLevel, str]:
        """
        Backward-compatible check method matching the legacy PermissionManager interface.
        Returns: (allowed: bool, level: PermissionLevel, reason: str)
        """
        from backend.tools.registry import tool_registry
        tool = tool_registry.get(tool_name)
        if tool:
            default_level = tool.permission_level
            requires_conf = tool.requires_confirmation
        else:
            default_level = PermissionLevel.HIGH
            requires_conf = True

        allowed, level, reason, _ = self.evaluate(
            tool_name=tool_name,
            default_level=default_level,
            requires_tool_confirmation=requires_conf,
            arguments=arguments,
            confirmed=confirmed
        )
        return allowed, level, reason


# Global Singleton Permission Engine
permission_engine = PermissionEngine()
permission_manager = permission_engine  # Alias for backward compatibility
