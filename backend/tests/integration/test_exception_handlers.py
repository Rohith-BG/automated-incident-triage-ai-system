import logging

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.exceptions import BadRequestException, ExceptionHandlerRegistry


def create_test_app() -> FastAPI:
    app = FastAPI()
    ExceptionHandlerRegistry().register(app)

    @app.get("/app-error")
    async def app_error() -> None:
        raise BadRequestException(
            "Invalid incident payload.",
            log_message="Incident payload failed domain validation.",
            context={"field": "service_name"},
        )

    @app.get("/http-error")
    async def http_error() -> None:
        raise HTTPException(status_code=403, detail="Access denied.")

    @app.get("/validation/{item_id}")
    async def validation_error(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.get("/unexpected")
    async def unexpected_error() -> None:
        raise RuntimeError("database connection pool failed")

    return app


def test_app_exception_uses_minimal_error_response(caplog) -> None:
    client = TestClient(create_test_app())

    with caplog.at_level(logging.WARNING):
        response = client.get("/app-error")

    assert response.status_code == 400
    res_json = response.json()
    assert res_json["success"] is False
    assert res_json["message"] == "Invalid incident payload."
    assert "Incident payload failed domain validation." in caplog.text
    assert "field" not in response.text


def test_framework_http_exception_uses_minimal_error_response() -> None:
    client = TestClient(create_test_app())

    response = client.get("/http-error")

    assert response.status_code == 403
    res_json = response.json()
    assert res_json["success"] is False
    assert res_json["message"] == "Access denied."


def test_validation_error_does_not_expose_validation_details() -> None:
    client = TestClient(create_test_app())

    response = client.get("/validation/not-an-int")

    assert response.status_code == 422
    res_json = response.json()
    assert res_json["success"] is False
    assert res_json["message"] == "Request validation failed."
    assert "not-an-int" not in response.text


def test_unexpected_error_returns_generic_message_and_logs_stack_trace(
    caplog,
) -> None:
    client = TestClient(create_test_app(), raise_server_exceptions=False)

    with caplog.at_level(logging.ERROR):
        response = client.get("/unexpected")

    assert response.status_code == 500
    res_json = response.json()
    assert res_json["success"] is False
    assert res_json["message"] == "An unexpected server error occurred."
    assert "Unhandled exception while processing request." in caplog.text
    assert "RuntimeError: database connection pool failed" in caplog.text
