"""
Schemas and Data Contracts for Tool & Action Framework.

Defines PermissionLevel, ActionRequest, ToolResult, ToolContext, and ToolMetadata.
Maintains backward compatibility with legacy schemas.
"""

from __future__ import annotations
import enum
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field


class PermissionLevel(str, enum.Enum):
    """
    Tiered permission classification for tool execution.
    - AUTOMATIC: Safe read-only operations executed without user prompt.
    - LOW: Minor local actions (notifications, allowlisted apps).
    - MEDIUM: Actions that modify local state (clipboard write, file create).
    - HIGH: Potentially dangerous operations (terminal, file deletion, shutdown).
    - CRITICAL: Irreversible or highly destructive operations (wipes, format).
    """
    AUTOMATIC = "AUTOMATIC"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    # Backward compatibility aliases for legacy code
    SAFE = "AUTOMATIC"
    CONFIRM = "MEDIUM"
    DANGEROUS = "HIGH"

    # Phase 2 aliases
    READ_ONLY = "AUTOMATIC"
    SAFE_ACTION = "LOW"
    CONFIRMATION_REQUIRED = "MEDIUM"
    HIGH_RISK = "HIGH"


class ActionRequest(BaseModel):
    """Structured request to execute an action via the ToolRegistry."""
    tool: str = Field(..., description="Unique registered name of tool to execute")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool invocation arguments")
    source: str = Field(default="user", description="Originator of the action (user, agent, system)")
    session_id: str = Field(default="default", max_length=64, description="Active chat session identifier")
    request_id: str = Field(
        default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}",
        description="Unique request tracing ID"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Action request timestamp"
    )


class ToolResult(BaseModel):
    """Standardized result returned by tool execution."""
    success: bool = Field(..., description="Whether execution succeeded")
    tool: str = Field(..., description="Name of executed tool")
    data: Any = Field(default=None, description="Structured payload or returned value")
    message: str = Field(default="", description="Human-readable status or summary message")
    error: Optional[str] = Field(default=None, description="User-safe error description if failed")
    error_code: Optional[str] = Field(default=None, description="Machine-readable error code")
    duration_ms: float = Field(default=0.0, description="Execution elapsed time in milliseconds")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Auxiliary execution metadata")


class ToolContext(BaseModel):
    """Safe execution context provided to tools during execution."""
    request_id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")
    session_id: str = Field(default="default")
    user_id: Optional[str] = Field(default=None)
    source: str = Field(default="user")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    workspace: Path = Field(default_factory=lambda: Path.cwd())
    confirmed: bool = Field(default=False, description="Whether user explicitly confirmed this action")

    model_config = {
        "arbitrary_types_allowed": True
    }


class ToolMetadata(BaseModel):
    """Public metadata describing a registered tool."""
    name: str
    description: str
    category: str
    version: str = "1.0"
    permission_level: PermissionLevel
    requires_confirmation: bool = False
    cacheable: bool = False
    cache_ttl: int = 0
    sensitive: bool = False
    store_in_memory: bool = True
    timeout_seconds: float = 10.0
    argument_schema: Dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# Legacy Schemas (Preserved for backward compatibility)
# ==============================================================================

class ToolIntentSchema(BaseModel):
    """Legacy detected intent schema."""
    tool_name: str = Field(..., description="Name of tool to execute")
    tool_args: str = Field(default="", description="Arguments string")


class ToolResultSchema(BaseModel):
    """Legacy result of tool execution with execution status."""
    tool_name: str
    success: bool
    result: Any
    error: Optional[str] = None
