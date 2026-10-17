"""
AWS Remote MCP Observability Provider.

Delegates remote tool calls to the shared RemoteMCPClient (which owns
the Streamable HTTP connection to https://aws-mcp.<region>.api.aws/mcp).

Falls back to MockObservabilityProvider if the remote call fails or
OBSERVABILITY_BACKEND is set to mock.
"""

import logging
from typing import Any, Optional

from agents.config import AgentSettings
from .base import ObservabilityProvider
from .mock import MockObservabilityProvider

logger = logging.getLogger(__name__)


class AWSRemoteMCPProvider:
    """Observability provider routing calls through RemoteMCPClient to AWS MCP."""

    def __init__(
        self,
        config: AgentSettings,
        mcp_client: Optional[Any] = None,
        mock_fallback: Optional[MockObservabilityProvider] = None,
    ) -> None:
        self._config = config
        self._region = config.AWS_REGION
        self._log_group_prefix = config.CLOUDWATCH_LOG_GROUP_PREFIX
        self._mcp_client = mcp_client
        self._mock = mock_fallback or MockObservabilityProvider(
            data_dir=config.DATA_DIR
        )

    def _resolve_log_group(self, service: str) -> str:
        """Map service ID to CloudWatch log group path."""
        prefix = self._log_group_prefix.rstrip("/")
        return f"{prefix}/{service}"

    async def _call_aws_mcp(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """Route tool call through RemoteMCPClient's AWS endpoint."""
        if self._mcp_client is None:
            raise RuntimeError(
                "AWSRemoteMCPProvider requires an initialized "
                "RemoteMCPClient. Pass mcp_client at construction."
            )
        return await self._mcp_client.call_tool(
            "observability", tool_name, arguments
        )

    async def search_logs(
        self,
        service: str,
        query: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search logs via AWS MCP CloudWatch tool, falling back to mock."""
        log_group = self._resolve_log_group(service)
        insights_query = (
            f"fields @timestamp, @message "
            f"| filter @message like /{query}/ "
            f"| limit {limit}"
        )
        try:
            res = await self._call_aws_mcp(
                "query_cloudwatch_logs",
                {
                    "log_group": log_group,
                    "query": insights_query,
                    "limit": limit,
                },
            )
            if isinstance(res, list):
                return res
            if isinstance(res, dict) and "results" in res:
                return res["results"]
        except Exception as e:
            logger.info(
                "AWS MCP search_logs remote call failed, "
                "falling back to mock provider: %s", e,
            )

        return await self._mock.search_logs(service, query, limit)

    async def get_errors(
        self,
        service: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get ERROR-level logs via AWS MCP, falling back to mock."""
        log_group = self._resolve_log_group(service)
        insights_query = (
            f"fields @timestamp, @message "
            f"| filter @message like /ERROR/ "
            f"| limit {limit}"
        )
        try:
            res = await self._call_aws_mcp(
                "query_cloudwatch_logs",
                {
                    "log_group": log_group,
                    "query": insights_query,
                    "limit": limit,
                },
            )
            if isinstance(res, list):
                return res
            if isinstance(res, dict) and "results" in res:
                return res["results"]
        except Exception as e:
            logger.info(
                "AWS MCP get_errors remote call failed, "
                "falling back to mock provider: %s", e,
            )

        return await self._mock.get_errors(service, limit)

    async def get_traces(
        self,
        service: str,
        trace_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Retrieve trace spans via AWS MCP, falling back to mock."""
        try:
            args: dict[str, Any] = {"service": service}
            if trace_id:
                args["trace_id"] = trace_id
            res = await self._call_aws_mcp("get_xray_traces", args)
            if isinstance(res, list):
                return res
            if isinstance(res, dict) and "traces" in res:
                return res["traces"]
        except Exception as e:
            logger.info(
                "AWS MCP get_traces remote call failed, "
                "falling back to mock provider: %s", e,
            )

        return await self._mock.get_traces(service, trace_id)

    async def get_metrics(
        self,
        service: str,
        metric_name: Optional[str] = None,
        minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Retrieve CloudWatch metrics via AWS MCP, falling back to mock."""
        try:
            res = await self._call_aws_mcp(
                "get_cloudwatch_metrics",
                {
                    "namespace": "Microservices",
                    "dimensions": {"ServiceName": service},
                    "metric_name": metric_name or "latency_ms",
                    "period_minutes": minutes,
                },
            )
            if isinstance(res, list):
                return res
            if isinstance(res, dict) and "datapoints" in res:
                return res["datapoints"]
        except Exception as e:
            logger.info(
                "AWS MCP get_metrics remote call failed, "
                "falling back to mock provider: %s", e,
            )

        return await self._mock.get_metrics(service, metric_name, minutes)

    async def get_anomalies(
        self,
        service: str,
        minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Retrieve metric anomalies via AWS MCP, falling back to mock."""
        try:
            res = await self._call_aws_mcp(
                "get_cloudwatch_alarms",
                {
                    "namespace": "Microservices",
                    "service": service,
                    "state": "ALARM",
                },
            )
            if isinstance(res, list):
                return res
        except Exception as e:
            logger.info(
                "AWS MCP get_anomalies remote call failed, "
                "falling back to mock provider: %s", e,
            )

        return await self._mock.get_anomalies(service, minutes)
