"""Unit tests for ServiceResolver — CloudWatch alarm → service_id resolution."""

import pytest

from backend.app.services.service_resolver import (
    ServiceResolver,
    _extract_from_alb_dimensions,
    _extract_from_apigateway_dimensions,
    _extract_from_custom_dimensions,
    _extract_from_ecs_dimensions,
    _extract_from_eks_dimensions,
    _extract_service_from_alarm_name,
    _extract_service_from_description,
)


# ── Known services fixture ──────────────────────────────────

KNOWN = [
    "cart-service",
    "payment-service",
    "frontend",
    "checkout-service",
    "shipping-service",
    "email-service",
    "product-catalog-service",
    "currency-service",
    "recommendation-service",
    "ad-service",
    "load-generator",
]


# ── Dimension extractor unit tests ──────────────────────────


def test_ecs_dimension_extraction() -> None:
    dims = [
        {"name": "ClusterName", "value": "prod-cluster"},
        {"name": "ServiceName", "value": "cart-service"},
    ]
    assert _extract_from_ecs_dimensions(dims) == "cart-service"


def test_ecs_dimension_missing_service() -> None:
    dims = [{"name": "ClusterName", "value": "prod"}]
    assert _extract_from_ecs_dimensions(dims) is None


def test_ecs_dimension_capital_keys() -> None:
    """AWS may send Name/Value or name/value."""
    dims = [
        {"Name": "ServiceName", "Value": "payment-service"},
    ]
    assert _extract_from_ecs_dimensions(dims) == "payment-service"


def test_alb_dimension_standard_convention() -> None:
    dims = [
        {
            "name": "TargetGroup",
            "value": "tg/cart-service/abc123",
        },
    ]
    assert _extract_from_alb_dimensions(dims) == "cart-service"


def test_alb_dimension_targetgroup_prefix() -> None:
    dims = [
        {
            "name": "TargetGroup",
            "value": "targetgroup/payment-service/xyz",
        },
    ]
    assert _extract_from_alb_dimensions(dims) == "payment-service"


def test_alb_dimension_no_targetgroup() -> None:
    dims = [{"name": "LoadBalancer", "value": "app/alb/123"}]
    assert _extract_from_alb_dimensions(dims) is None


def test_eks_dimension_service() -> None:
    dims = [
        {"name": "ClusterName", "value": "eks-prod"},
        {"name": "Service", "value": "checkout-service"},
    ]
    assert _extract_from_eks_dimensions(dims) == "checkout-service"


def test_eks_dimension_missing() -> None:
    dims = [{"name": "ClusterName", "value": "eks-prod"}]
    assert _extract_from_eks_dimensions(dims) is None


def test_apigateway_full_dimensions() -> None:
    dims = [
        {"name": "ApiName", "value": "my-monolith-api"},
        {"name": "Stage", "value": "prod"},
        {"name": "Resource", "value": "/users"},
        {"name": "Method", "value": "GET"},
    ]
    result = _extract_from_apigateway_dimensions(dims)
    assert result["service_name"] == "my-monolith-api"
    assert result["entry_point"] == "GET /users"


def test_apigateway_resource_only() -> None:
    dims = [
        {"name": "ApiName", "value": "my-api"},
        {"name": "Resource", "value": "/orders"},
    ]
    result = _extract_from_apigateway_dimensions(dims)
    assert result["service_name"] == "my-api"
    assert result["entry_point"] == "/orders"


def test_apigateway_no_resource() -> None:
    dims = [{"name": "ApiName", "value": "my-api"}]
    result = _extract_from_apigateway_dimensions(dims)
    assert result["service_name"] == "my-api"
    assert result["entry_point"] is None


def test_custom_dimension_module() -> None:
    dims = [
        {"name": "Module", "value": "payments.stripe_client"},
        {"name": "ServiceName", "value": "payment-service"},
    ]
    result = _extract_from_custom_dimensions(dims)
    assert result["service_name"] == "payment-service"
    assert result["entry_point"] == "payments.stripe_client"


def test_custom_dimension_function_name() -> None:
    dims = [{"name": "FunctionName", "value": "email-service"}]
    result = _extract_from_custom_dimensions(dims)
    assert result["service_name"] == "email-service"
    assert result["entry_point"] is None


# ── AlarmName / Description fallbacks ───────────────────────


def test_alarm_name_prefix_match() -> None:
    assert (
        _extract_service_from_alarm_name(
            "cart-service-5xx-alarm", KNOWN
        )
        == "cart-service"
    )


def test_alarm_name_longer_match_wins() -> None:
    """product-catalog-service should match before shorter names."""
    assert (
        _extract_service_from_alarm_name(
            "product-catalog-service-latency-alarm", KNOWN
        )
        == "product-catalog-service"
    )


def test_alarm_name_no_match() -> None:
    assert (
        _extract_service_from_alarm_name(
            "unknown-thing-alarm", KNOWN
        )
        is None
    )


def test_description_match() -> None:
    assert (
        _extract_service_from_description(
            "High error rate on payment-service in us-east-1",
            KNOWN,
        )
        == "payment-service"
    )


def test_description_no_match() -> None:
    assert (
        _extract_service_from_description(
            "Something went wrong", KNOWN
        )
        is None
    )


# ── Full ServiceResolver integration ────────────────────────


class TestServiceResolver:
    """End-to-end resolver tests with realistic CloudWatch payloads."""

    def setup_method(self) -> None:
        self.resolver = ServiceResolver(KNOWN)

    def test_ecs_alarm(self) -> None:
        alarm = {
            "AlarmName": "cart-service-cpu-alarm",
            "AlarmDescription": "CPU > 80%",
            "Trigger": {
                "Namespace": "AWS/ECS",
                "MetricName": "CPUUtilization",
                "Dimensions": [
                    {"name": "ClusterName", "value": "prod"},
                    {
                        "name": "ServiceName",
                        "value": "cart-service",
                    },
                ],
            },
        }
        result = self.resolver.resolve(alarm)
        assert result["service_id"] == "cart-service"
        assert result["entry_point"] is None

    def test_alb_alarm(self) -> None:
        alarm = {
            "AlarmName": "payment-5xx",
            "Trigger": {
                "Namespace": "AWS/ApplicationELB",
                "MetricName": "HTTPCode_Target_5XX_Count",
                "Dimensions": [
                    {
                        "name": "TargetGroup",
                        "value": "tg/payment-service/abc",
                    },
                ],
            },
        }
        result = self.resolver.resolve(alarm)
        assert result["service_id"] == "payment-service"

    def test_apigateway_alarm_monolith(self) -> None:
        alarm = {
            "AlarmName": "monolith-users-5xx",
            "AlarmDescription": "5xx on checkout-service API",
            "Trigger": {
                "Namespace": "AWS/ApiGateway",
                "MetricName": "5XXError",
                "Dimensions": [
                    {
                        "name": "ApiName",
                        "value": "checkout-service",
                    },
                    {"name": "Resource", "value": "/orders"},
                    {"name": "Method", "value": "POST"},
                ],
            },
        }
        result = self.resolver.resolve(alarm)
        assert result["service_id"] == "checkout-service"
        assert result["entry_point"] == "POST /orders"

    def test_custom_namespace(self) -> None:
        alarm = {
            "AlarmName": "custom-error-alarm",
            "Trigger": {
                "Namespace": "Custom/MyApp",
                "MetricName": "ErrorCount",
                "Dimensions": [
                    {
                        "name": "Module",
                        "value": "payments.stripe_client",
                    },
                    {
                        "name": "ServiceName",
                        "value": "payment-service",
                    },
                ],
            },
        }
        result = self.resolver.resolve(alarm)
        assert result["service_id"] == "payment-service"
        assert (
            result["entry_point"] == "payments.stripe_client"
        )

    def test_fallback_alarm_name(self) -> None:
        alarm = {
            "AlarmName": "shipping-service-timeout-alarm",
            "Trigger": {
                "Namespace": "SomeUnknownNamespace",
                "Dimensions": [],
            },
        }
        result = self.resolver.resolve(alarm)
        assert result["service_id"] == "shipping-service"

    def test_fallback_description(self) -> None:
        alarm = {
            "AlarmName": "random-alarm-xyz",
            "AlarmDescription": "Errors in email-service module",
            "Trigger": {
                "Namespace": "SomeOther",
                "Dimensions": [],
            },
        }
        result = self.resolver.resolve(alarm)
        assert result["service_id"] == "email-service"

    def test_unresolvable_returns_none(self) -> None:
        alarm = {
            "AlarmName": "totally-unknown-alarm",
            "AlarmDescription": "Something broke",
            "Trigger": {
                "Namespace": "AWS/EC2",
                "Dimensions": [
                    {
                        "name": "InstanceId",
                        "value": "i-0123456789",
                    },
                ],
            },
        }
        result = self.resolver.resolve(alarm)
        assert result["service_id"] is None

    def test_case_insensitive_validation(self) -> None:
        """Dimension value with different casing still resolves."""
        alarm = {
            "AlarmName": "alarm",
            "Trigger": {
                "Namespace": "AWS/ECS",
                "Dimensions": [
                    {
                        "name": "ServiceName",
                        "value": "Cart-Service",
                    },
                ],
            },
        }
        result = self.resolver.resolve(alarm)
        assert result["service_id"] == "cart-service"

    def test_eks_container_insights(self) -> None:
        alarm = {
            "AlarmName": "eks-alarm",
            "Trigger": {
                "Namespace": "ContainerInsights",
                "Dimensions": [
                    {
                        "name": "Service",
                        "value": "frontend",
                    },
                ],
            },
        }
        result = self.resolver.resolve(alarm)
        assert result["service_id"] == "frontend"
