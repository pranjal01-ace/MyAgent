"""
Structured Tool Exception Hierarchy.

Provides controlled, user-safe error types for the Ace AI Tool & Action System.
These exceptions prevent raw Python stack traces from leaking to end users or LLMs.
"""


class ToolError(Exception):
    """Base exception for all tool system errors."""

    def __init__(self, message: str, code: str = "TOOL_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code

    def __str__(self) -> str:
        return self.message


class ToolNotFound(ToolError):
    """Raised when a requested tool does not exist in the ToolRegistry."""

    def __init__(self, tool_name: str):
        super().__init__(f"Tool '{tool_name}' not found.", code="TOOL_NOT_FOUND")
        self.tool_name = tool_name


class ToolValidationError(ToolError):
    """Raised when provided tool arguments fail schema or type validation."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(f"Argument validation failed: {message}", code="TOOL_VALIDATION_ERROR")
        self.details = details or {}


class ToolPermissionDenied(ToolError):
    """Raised when a tool execution is rejected by the PermissionEngine."""

    def __init__(self, tool_name: str, reason: str = "Permission denied"):
        super().__init__(f"Permission denied for tool '{tool_name}': {reason}", code="TOOL_PERMISSION_DENIED")
        self.tool_name = tool_name
        self.reason = reason


class ToolConfirmationRequired(ToolError):
    """Raised when a tool requires explicit user confirmation before executing."""

    def __init__(self, tool_name: str, permission_level: str, description: str):
        super().__init__(
            f"Tool '{tool_name}' requires confirmation ({permission_level}): {description}",
            code="TOOL_CONFIRMATION_REQUIRED"
        )
        self.tool_name = tool_name
        self.permission_level = permission_level
        self.description = description


class ToolExecutionError(ToolError):
    """Raised when an internal error occurs during tool execution."""

    def __init__(self, tool_name: str, original_error: Exception):
        super().__init__(f"Error executing tool '{tool_name}': {original_error}", code="TOOL_EXECUTION_ERROR")
        self.tool_name = tool_name
        self.original_error = original_error


class ToolTimeout(ToolError):
    """Raised when tool execution exceeds its configured timeout limit."""

    def __init__(self, tool_name: str, timeout_seconds: float):
        super().__init__(
            f"Tool '{tool_name}' timed out after {timeout_seconds}s.",
            code="TOOL_TIMEOUT"
        )
        self.tool_name = tool_name
        self.timeout_seconds = timeout_seconds


class ToolUnavailable(ToolError):
    """Raised when required OS features, devices, or dependencies are unavailable."""

    def __init__(self, tool_name: str, reason: str):
        super().__init__(f"Tool '{tool_name}' is currently unavailable: {reason}", code="TOOL_UNAVAILABLE")
        self.tool_name = tool_name
        self.reason = reason


class ToolCancelled(ToolError):
    """Raised when a user explicitly rejects or cancels a tool confirmation."""

    def __init__(self, tool_name: str):
        super().__init__(f"Tool '{tool_name}' execution was cancelled by user.", code="TOOL_CANCELLED")
        self.tool_name = tool_name
