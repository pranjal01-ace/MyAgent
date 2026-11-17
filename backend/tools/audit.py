"""
Audit Logging and Observability Module for Tool Execution.

Guarantees full traceability of every tool invocation while enforcing strict security rules:
- Secret redaction (passwords, tokens, keys)
- Zero-persistence for clipboard text
- Real-time telemetry counters
"""

import re
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("ace.tools.audit")

# Sensitive argument key pattern
SENSITIVE_KEY_PATTERN = re.compile(
    r"(pass(word)?|token|secret|key|auth(orization)?|credential|cert|bearer)",
    re.IGNORECASE
)

# Tools whose arguments or data must NEVER appear in audit logs
ZERO_LOG_TOOLS = {"get_clipboard", "set_clipboard", "read_clipboard", "write_clipboard"}


class AuditLogger:
    """
    Sanitizes, records, and exposes telemetry for all tool executions.
    """

    def __init__(self):
        self.metrics: Dict[str, Any] = {
            "tool_calls_total": 0,
            "tool_success_total": 0,
            "tool_failure_total": 0,
            "tool_denied_total": 0,
            "tool_confirmation_total": 0,
            "tool_duration_ms_total": 0.0,
        }

    def sanitize_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitizes argument dictionary:
        - Completely redacts text for clipboard tools.
        - Redacts values corresponding to credential keys.
        """
        if tool_name.lower() in ZERO_LOG_TOOLS:
            return {"[REDACTED]": "<clipboard content protected>"}

        if not isinstance(arguments, dict):
            return {"raw": "<non-dict arguments>"}

        sanitized = {}
        for k, v in arguments.items():
            if SENSITIVE_KEY_PATTERN.search(k):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = self.sanitize_arguments(tool_name, v)
            elif isinstance(v, str) and len(v) > 200:
                sanitized[k] = v[:200] + "... [truncated]"
            else:
                sanitized[k] = v
        return sanitized

    def log_execution(
        self,
        request_id: str,
        session_id: str,
        tool: str,
        arguments: Dict[str, Any],
        permission_level: str,
        confirmation_status: str,
        start_time: datetime,
        end_time: datetime,
        duration_ms: float,
        success: bool,
        error_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Records structured audit record and increments telemetry metrics.
        """
        # Update metrics
        self.metrics["tool_calls_total"] += 1
        self.metrics["tool_duration_ms_total"] += duration_ms
        if success:
            self.metrics["tool_success_total"] += 1
        else:
            self.metrics["tool_failure_total"] += 1

        if confirmation_status == "REQUIRED":
            self.metrics["tool_confirmation_total"] += 1
        elif confirmation_status == "DENIED":
            self.metrics["tool_denied_total"] += 1

        sanitized_args = self.sanitize_arguments(tool, arguments)

        audit_entry = {
            "request_id": request_id,
            "session_id": session_id,
            "tool": tool,
            "arguments": sanitized_args,
            "permission_level": permission_level,
            "confirmation_status": confirmation_status,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_ms": round(duration_ms, 2),
            "success": success,
            "error_code": error_code
        }

        log_msg = (
            f"TOOL AUDIT | req={request_id} tool={tool} perm={permission_level} "
            f"conf={confirmation_status} success={success} dur={duration_ms:.1f}ms "
            f"args={sanitized_args}"
        )
        if success:
            logger.info(log_msg)
        else:
            logger.warning(f"{log_msg} err={error_code}")

        return audit_entry

    def get_metrics(self) -> Dict[str, Any]:
        """Returns snapshot copy of tool execution metrics."""
        return dict(self.metrics)


# Global Singleton Audit Logger
audit_logger = AuditLogger()
