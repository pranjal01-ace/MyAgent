from typing import Any, Optional, Dict


class AppException(Exception):
    """Base exception for all application-level errors."""
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class EntityNotFoundError(AppException):
    """Raised when a requested resource or entity is not found."""
    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(
            message=f"{entity_name} with identifier '{entity_id}' not found.",
            status_code=404,
            details={"entity": entity_name, "identifier": str(entity_id)}
        )


class SecurityValidationError(AppException):
    """Raised when an operation violates security boundaries (e.g. path traversal, command injection)."""
    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=403,
            details={"type": "security_violation"}
        )


class ToolExecutionError(AppException):
    """Raised when desktop tool execution fails."""
    def __init__(self, tool_name: str, error_msg: str):
        super().__init__(
            message=f"Failed to execute tool '{tool_name}': {error_msg}",
            status_code=500,
            details={"tool": tool_name, "error": error_msg}
        )
