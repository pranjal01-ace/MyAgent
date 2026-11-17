"""
Tool Executor Module.

Orchestrates the entire tool execution lifecycle:
Request -> Registry Lookup -> Schema Validation -> Permission Check ->
Confirmation Check -> Async Execution with Timeout -> Result Normalization -> Audit Logging.
"""

import time
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from backend.tools.schemas import ActionRequest, ToolResult, ToolContext, PermissionLevel
from backend.tools.registry import tool_registry, ToolRegistry
from backend.tools.permissions import permission_engine, PermissionEngine
from backend.tools.audit import audit_logger, AuditLogger
from backend.tools.errors import (
    ToolError,
    ToolNotFound,
    ToolValidationError,
    ToolPermissionDenied,
    ToolConfirmationRequired,
    ToolExecutionError,
    ToolTimeout
)

logger = logging.getLogger("ace.tools.executor")


class ToolExecutor:
    """
    Validates and executes tool requests with timeout protection,
    permission enforcement, and audit telemetry.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        permissions: Optional[PermissionEngine] = None,
        audit: Optional[AuditLogger] = None
    ):
        self.registry = registry or tool_registry
        self.permissions = permissions or permission_engine
        self.audit = audit or audit_logger

    async def execute(
        self,
        request: ActionRequest,
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        """
        Executes an ActionRequest through the full validated lifecycle.
        """
        start_dt = datetime.now(timezone.utc)
        start_mono = time.monotonic()
        tool_name = request.tool
        raw_args = request.arguments

        ctx = context or ToolContext(
            request_id=request.request_id,
            session_id=request.session_id,
            source=request.source,
            timestamp=request.timestamp,
            confirmed=False
        )

        perm_level_str = PermissionLevel.AUTOMATIC.value
        conf_status = "NOT_REQUIRED"

        try:
            # 1. Tool Lookup
            if not self.registry._tools:
                from backend.tools.initialize import initialize_tools
                initialize_tools(self.registry)

            tool = self.registry.get(tool_name)
            if not tool:
                raise ToolNotFound(tool_name)

            perm_level_str = tool.permission_level.value

            # 2. Schema Validation
            validated_args = tool.validate(raw_args)

            # 3. Permission & Confirmation Check
            allowed, effective_level, reason, needs_conf = self.permissions.evaluate(
                tool_name=tool_name,
                default_level=tool.permission_level,
                requires_tool_confirmation=tool.requires_confirmation,
                arguments=validated_args,
                confirmed=ctx.confirmed
            )
            perm_level_str = effective_level.value

            if needs_conf and not ctx.confirmed:
                conf_status = "REQUIRED"
                raise ToolConfirmationRequired(
                    tool_name=tool_name,
                    permission_level=perm_level_str,
                    description=reason
                )

            if not allowed:
                conf_status = "DENIED"
                raise ToolPermissionDenied(tool_name=tool_name, reason=reason)

            # 4. Async Execution with Timeout Protection
            timeout = tool.timeout_seconds or 10.0
            try:
                result = await asyncio.wait_for(
                    tool.execute(validated_args, ctx),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                raise ToolTimeout(tool_name=tool_name, timeout_seconds=timeout)
            except ToolError:
                raise
            except Exception as ex:
                raise ToolExecutionError(tool_name=tool_name, original_error=ex)

            # Execution elapsed duration
            end_mono = time.monotonic()
            end_dt = datetime.now(timezone.utc)
            duration_ms = (end_mono - start_mono) * 1000.0
            result.duration_ms = round(duration_ms, 2)

            # 5. Audit Logging
            self.audit.log_execution(
                request_id=ctx.request_id,
                session_id=ctx.session_id,
                tool=tool_name,
                arguments=validated_args,
                permission_level=perm_level_str,
                confirmation_status="APPROVED" if ctx.confirmed else "AUTO",
                start_time=start_dt,
                end_time=end_dt,
                duration_ms=duration_ms,
                success=result.success,
                error_code=result.error_code
            )

            return result

        except ToolConfirmationRequired as e:
            end_mono = time.monotonic()
            end_dt = datetime.now(timezone.utc)
            dur = (end_mono - start_mono) * 1000.0

            self.audit.log_execution(
                request_id=ctx.request_id,
                session_id=ctx.session_id,
                tool=tool_name,
                arguments=raw_args,
                permission_level=perm_level_str,
                confirmation_status="REQUIRED",
                start_time=start_dt,
                end_time=end_dt,
                duration_ms=dur,
                success=False,
                error_code=e.code
            )
            return ToolResult(
                success=False,
                tool=tool_name,
                message=str(e),
                error=str(e),
                error_code=e.code,
                duration_ms=round(dur, 2),
                metadata={"confirmation_required": True, "permission_level": e.permission_level}
            )

        except ToolError as e:
            end_mono = time.monotonic()
            end_dt = datetime.now(timezone.utc)
            dur = (end_mono - start_mono) * 1000.0

            self.audit.log_execution(
                request_id=ctx.request_id,
                session_id=ctx.session_id,
                tool=tool_name,
                arguments=raw_args,
                permission_level=perm_level_str,
                confirmation_status="DENIED" if isinstance(e, ToolPermissionDenied) else "FAILED",
                start_time=start_dt,
                end_time=end_dt,
                duration_ms=dur,
                success=False,
                error_code=e.code
            )
            return ToolResult(
                success=False,
                tool=tool_name,
                message=str(e),
                error=str(e),
                error_code=e.code,
                duration_ms=round(dur, 2)
            )

        except Exception as unhandled:
            logger.exception(f"Unexpected unhandled error in tool '{tool_name}': {unhandled}")
            end_mono = time.monotonic()
            end_dt = datetime.now(timezone.utc)
            dur = (end_mono - start_mono) * 1000.0

            self.audit.log_execution(
                request_id=ctx.request_id,
                session_id=ctx.session_id,
                tool=tool_name,
                arguments=raw_args,
                permission_level=perm_level_str,
                confirmation_status="FAILED",
                start_time=start_dt,
                end_time=end_dt,
                duration_ms=dur,
                success=False,
                error_code="UNHANDLED_ERROR"
            )
            return ToolResult(
                success=False,
                tool=tool_name,
                message=f"Tool execution failed unexpectedly: {unhandled}",
                error=str(unhandled),
                error_code="UNHANDLED_ERROR",
                duration_ms=round(dur, 2)
            )


# Global Singleton Tool Executor
tool_executor = ToolExecutor()
