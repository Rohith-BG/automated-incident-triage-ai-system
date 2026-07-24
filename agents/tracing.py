"""
OpenTelemetry-compatible agent tool tracing module.

Records agent execution traces including tool inputs/outputs, latency,
token usage, and failure states. Automatically sanitizes credentials and secrets.
"""

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Regex pattern for sanitizing common secret formats in text/dict strings
_SECRET_PATTERN = re.compile(
    r"(?i)(['\"]?(?:api[_-]?key|secret|token|password|auth|bearer)['\"]?\s*[:=]\s*['\"]?)([^\s'\"&,\}]+)(['\"]?)"
)


def sanitize_text(text: str) -> str:
    """Sanitize secrets and credentials in text string."""
    if not text:
        return text
    return _SECRET_PATTERN.sub(r"\1[REDACTED]\3", text)


@dataclass
class ToolTrace:
    """Single execution trace entry for an agent tool or LLM action."""

    incident_id: str
    agent: str  # e.g., "observability", "deploy", "incident_knowledge", "code_diff", "orchestrator"
    tool: str  # e.g., "search_logs", "analyze_deployment"
    input_summary: str
    output_summary: str
    latency_ms: float
    token_usage: dict[str, int] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert trace to dictionary."""
        return asdict(self)


class TraceRecorder:
    """In-memory trace recorder storing traces per incident with sanitization."""

    def __init__(self) -> None:
        """Initialise in-memory trace store."""
        self._traces: list[ToolTrace] = []

    def record(
        self,
        incident_id: str,
        agent: str,
        tool: str,
        input_data: Any,
        output_data: Any,
        latency_ms: float,
        token_usage: Optional[dict[str, int]] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> ToolTrace:
        """Sanitize and record a tool trace entry."""
        clean_input = sanitize_text(str(input_data))[:1000]
        clean_output = sanitize_text(str(output_data))[:1000]
        clean_error = sanitize_text(error) if error else None

        trace = ToolTrace(
            incident_id=incident_id,
            agent=agent,
            tool=tool,
            input_summary=clean_input,
            output_summary=clean_output,
            latency_ms=round(latency_ms, 2),
            token_usage=token_usage or {},
            success=success,
            error=clean_error,
        )
        self._traces.append(trace)
        logger.debug(
            "Recorded trace [%s] agent=%s tool=%s latency=%.1fms success=%s",
            incident_id,
            agent,
            tool,
            latency_ms,
            success,
        )
        return trace

    def get_traces(self, incident_id: str) -> list[ToolTrace]:
        """Return all traces for an incident_id."""
        return [t for t in self._traces if t.incident_id == incident_id]

    def get_summary(self, incident_id: str) -> dict[str, Any]:
        """Compute aggregate trace summary metrics for an incident_id."""
        traces = self.get_traces(incident_id)
        if not traces:
            return {
                "incident_id": incident_id,
                "total_calls": 0,
                "total_latency_ms": 0.0,
                "total_tokens": 0,
                "failed_calls": 0,
            }

        total_latency = sum(t.latency_ms for t in traces)
        total_tokens = sum(t.token_usage.get("total_tokens", 0) for t in traces)
        failed_calls = sum(1 for t in traces if not t.success)

        return {
            "incident_id": incident_id,
            "total_calls": len(traces),
            "total_latency_ms": round(total_latency, 2),
            "total_tokens": total_tokens,
            "failed_calls": failed_calls,
        }

    def clear(self) -> None:
        """Clear all stored traces."""
        self._traces.clear()


# Global singleton instance for easy import across agents
global_trace_recorder = TraceRecorder()
