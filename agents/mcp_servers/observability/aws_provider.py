"""
AWS CloudWatch observability provider for logs and metrics.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiobotocore.session

logger = logging.getLogger(__name__)


class AWSObservabilityProvider:
    """Production provider using AWS CloudWatch to fetch real logs and metrics."""

    def __init__(
        self,
        region_name: str,
        log_group_prefix: str = "/ecs",
    ) -> None:
        """Initialise the AWS provider.

        Args:
            region_name: AWS region (e.g. us-east-1).
            log_group_prefix: Log group naming prefix.
        """
        self._region_name = region_name
        self._log_group_prefix = log_group_prefix
        self._session = aiobotocore.session.get_session()

    def _get_log_group_name(self, service: str) -> str:
        """Derive log group name for service."""
        return f"{self._log_group_prefix}/{service}"

    async def search_logs(
        self,
        service: str,
        query: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Query CloudWatch log group for logs matching query keyword."""
        log_group = self._get_log_group_name(service)
        logger.info("Searching CloudWatch Logs for %s with query '%s'", log_group, query)

        results = []
        try:
            async with self._session.create_client("logs", region_name=self._region_name) as client:
                paginator = client.get_paginator("filter_log_events")
                # Search last 1 hour
                start_time = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp() * 1000)
                async for page in paginator.paginate(
                    logGroupName=log_group,
                    filterPattern=query,
                    startTime=start_time,
                    limit=limit,
                ):
                    for event in page.get("events", []):
                        results.append({
                            "service": service,
                            "timestamp": datetime.fromtimestamp(event["timestamp"] / 1000, tz=timezone.utc).isoformat(),
                            "level": "INFO",  # CloudWatch filter_log_events doesn't parse levels natively
                            "message": event["message"],
                        })
                        if len(results) >= limit:
                            break
                    if len(results) >= limit:
                        break
        except Exception as e:
            logger.error("Failed to query CloudWatch Logs for %s: %s", service, e)

        return results[:limit]

    async def get_errors(
        self,
        service: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Query CloudWatch Logs Insights for ERROR patterns."""
        log_group = self._get_log_group_name(service)
        logger.info("Running CloudWatch Logs Insights query for errors on %s", log_group)

        query = "fields @timestamp, @message | filter @message like /ERROR/ | sort @timestamp desc | limit " + str(limit)
        results = []

        try:
            async with self._session.create_client("logs", region_name=self._region_name) as client:
                start_time = int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp())
                end_time = int(datetime.now(timezone.utc).timestamp())

                # Start query
                start_resp = await client.start_query(
                    logGroupName=log_group,
                    startTime=start_time,
                    endTime=end_time,
                    queryString=query,
                )
                query_id = start_resp["queryId"]

                # Poll query results (wait up to 10 seconds)
                import asyncio
                for _ in range(20):
                    status_resp = await client.get_query_results(queryId=query_id)
                    status = status_resp["status"]
                    if status in ("Complete", "Failed", "Cancelled"):
                        if status == "Complete":
                            for row in status_resp.get("results", []):
                                timestamp = ""
                                message = ""
                                for field in row:
                                    if field["field"] == "@timestamp":
                                        timestamp = field["value"]
                                    elif field["field"] == "@message":
                                        message = field["value"]
                                results.append({
                                    "service": service,
                                    "timestamp": timestamp,
                                    "level": "ERROR",
                                    "message": message,
                                })
                        break
                    await asyncio.sleep(0.5)
        except Exception as e:
            logger.error("Failed to query CloudWatch Insights for %s: %s", service, e)

        return results[:limit]

    async def get_traces(
        self,
        service: str,
        trace_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return log-based distributed trace spans by checking structured logs."""
        # AWS X-Ray is dropped from scope per user request; we parse structured log trace tags if present
        query_pattern = f'"{trace_id}"' if trace_id else '"trace_id"'
        return await self.search_logs(service, query_pattern, limit=50)

    async def get_metrics(
        self,
        service: str,
        metric_name: Optional[str] = None,
        minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Query CloudWatch Metrics for service latency, error rate, etc."""
        logger.info("Querying CloudWatch Metrics for %s", service)
        metrics_to_query = [metric_name] if metric_name else ["latency_ms", "error_rate", "cpu_usage"]
        results = []

        try:
            async with self._session.create_client("cloudwatch", region_name=self._region_name) as client:
                end_time = datetime.now(timezone.utc)
                start_time = end_time - timedelta(minutes=minutes)

                queries = []
                for idx, name in enumerate(metrics_to_query):
                    queries.append({
                        "Id": f"m{idx}",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": "AWS/ECS", # Example ECS metrics namespace
                                "MetricName": name,
                                "Dimensions": [{"Name": "ServiceName", "Value": service}],
                            },
                            "Period": 60,
                            "Stat": "Average",
                        },
                        "ReturnData": True,
                    })

                resp = await client.get_metric_data(
                    MetricDataQueries=queries,
                    StartTime=start_time,
                    EndTime=end_time,
                )

                for idx, name in enumerate(metrics_to_query):
                    stat_results = resp.get("MetricDataResults", [])
                    matching_result = next((r for r in stat_results if r["Id"] == f"m{idx}"), None)
                    if matching_result:
                        timestamps = matching_result.get("Timestamps", [])
                        values = matching_result.get("Values", [])
                        for ts, val in zip(timestamps, values):
                            results.append({
                                "service": service,
                                "timestamp": ts.isoformat(),
                                "metric": name,
                                "value": val,
                                "unit": "N/A",
                            })
        except Exception as e:
            logger.error("Failed to query CloudWatch Metrics for %s: %s", service, e)

        return results

    async def get_anomalies(
        self,
        service: str,
        minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Simulate or query metric anomalies on CloudWatch."""
        metrics = await self.get_metrics(service, minutes=minutes)
        anomalies = []
        # Fallback anomaly detection based on baseline thresholds:
        for m in metrics:
            metric = m.get("metric")
            val = m.get("value", 0)
            is_anomaly = False
            desc = ""
            if metric == "latency_ms" and val > 200:
                is_anomaly = True
                desc = f"Latency spike: {val}ms exceeds baseline"
            elif metric == "error_rate" and val > 0.02:
                is_anomaly = True
                desc = f"Error rate spike: {val * 100}% errors"
            elif metric == "cpu_usage" and val > 80.0:
                is_anomaly = True
                desc = f"CPU utilization spike: {val}%"

            if is_anomaly:
                anomalies.append({
                    "service": service,
                    "timestamp": m.get("timestamp"),
                    "metric": metric,
                    "value": val,
                    "unit": m.get("unit"),
                    "description": desc,
                })
        return anomalies
