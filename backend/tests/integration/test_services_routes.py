from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_health_check_uses_dev_environment() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "environment": "dev",
    }


def test_list_services_route() -> None:
    response = client.get("/services")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 11
    assert body[0]["id"] == "frontend"


def test_service_detail_route_has_no_api_prefix() -> None:
    response = client.get("/services/frontend")

    assert response.status_code == 200
    assert response.json()["dependencies"] == [
        "cart-service",
        "product-catalog-service",
        "currency-service",
        "checkout-service",
        "recommendation-service",
        "ad-service",
        "shipping-service",
    ]


def test_dependencies_route() -> None:
    response = client.get("/services/cart-service/dependencies")

    assert response.status_code == 200
    assert response.json() == {
        "service_id": "cart-service",
        "dependencies": [
            {
                "id": "redis-cart",
                "dependency_type": "database",
                "owner_team": None,
                "repo": None,
                "language": None,
                "alert_threshold": None,
                "oncall_slack": None,
            }
        ],
    }


def test_blast_radius_route() -> None:
    response = client.get("/services/product-catalog-service/blast-radius")

    assert response.status_code == 200
    body = response.json()
    affected_ids = {service["id"] for service in body["affected_services"]}
    assert body["target_id"] == "product-catalog-service"
    assert affected_ids == {
        "checkout-service",
        "frontend",
        "load-generator",
        "recommendation-service",
    }
    assert body["impact_count"] == 4


def test_unknown_service_returns_404() -> None:
    response = client.get("/services/missing-service")

    assert response.status_code == 404
    res_json = response.json()
    assert res_json["success"] is False
    assert res_json["message"] == "Unknown service: missing-service"
