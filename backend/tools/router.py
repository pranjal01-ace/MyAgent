"""
Tools Domain Router.

Defines HTTP REST endpoints for inspecting registered tools, viewing metadata/schemas,
validating arguments, and safely executing actions.
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.tools.registry import tool_registry
from backend.tools.executor import tool_executor
from backend.tools.schemas import ActionRequest, ToolResult, ToolContext, ToolMetadata
from backend.tools.errors import ToolNotFound, ToolValidationError, ToolError

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolSummaryResponse(BaseModel):
    """Safe tool summary item."""
    name: str
    description: str
    category: str
    version: str
    permission: str
    requires_confirmation: bool


class ToolListResponse(BaseModel):
    """Listing of all available desktop tools."""
    total: int
    tools: List[ToolSummaryResponse]


class ExecuteToolRequest(BaseModel):
    """Payload for executing a tool via API."""
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments for tool invocation")
    session_id: str = Field(default="default", max_length=64)
    confirmed: bool = Field(default=False, description="Explicit user confirmation flag")


@router.get("", response_model=ToolListResponse, summary="List all registered tools")
async def list_tools_endpoint():
    """Returns a list of all registered tools and their public metadata."""
    tools = tool_registry.list()
    summaries = [
        ToolSummaryResponse(
            name=t.name,
            description=t.description,
            category=t.category,
            version=t.version,
            permission=t.permission_level.value,
            requires_confirmation=t.requires_confirmation
        )
        for t in tools
    ]
    return ToolListResponse(total=len(summaries), tools=summaries)


@router.get("/{name}", response_model=ToolMetadata, summary="Get tool details and schema")
async def get_tool_endpoint(name: str):
    """Returns full metadata and JSON input schema for a specific tool."""
    tool = tool_registry.get(name)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{name}' not found."
        )
    return tool.describe()


@router.post("/{name}/validate", summary="Validate arguments for a tool")
async def validate_tool_arguments_endpoint(name: str, payload: ExecuteToolRequest):
    """Validates provided arguments against the tool's schema without executing it."""
    tool = tool_registry.get(name)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{name}' not found."
        )

    try:
        validated = tool.validate(payload.arguments)
        return {
            "valid": True,
            "tool": name,
            "validated_arguments": validated
        }
    except ToolValidationError as e:
        return {
            "valid": False,
            "tool": name,
            "error": str(e),
            "details": e.details
        }


@router.post("/{name}/execute", response_model=ToolResult, summary="Execute a tool safely")
async def execute_tool_endpoint(name: str, payload: ExecuteToolRequest):
    """
    Executes a tool through the ToolExecutor.
    Enforces permission checks, argument validation, confirmation rules, and audit logging.
    """
    tool = tool_registry.get(name)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{name}' not found."
        )

    request = ActionRequest(
        tool=name,
        arguments=payload.arguments,
        session_id=payload.session_id,
        source="api"
    )

    context = ToolContext(
        request_id=request.request_id,
        session_id=request.session_id,
        source="api",
        confirmed=payload.confirmed
    )

    result = await tool_executor.execute(request, context)
    return result
