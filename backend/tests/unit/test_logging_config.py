import io
import json
import logging

from backend.app.core.config import Settings
from backend.app.core.logging import JsonLogFormatter, configure_logging


def test_json_log_formatter_outputs_structured_payload() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("tests.json_formatter")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info("incident created", extra={"incident_id": "inc-123"})

    payload = json.loads(stream.getvalue())
    assert payload["level"] == "INFO"
    assert payload["logger"] == "tests.json_formatter"
    assert payload["message"] == "incident created"
    assert payload["incident_id"] == "inc-123"
    assert "timestamp" in payload


def test_json_log_formatter_includes_exception_stack() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("tests.json_exception")
    logger.handlers = [handler]
    logger.setLevel(logging.ERROR)
    logger.propagate = False

    try:
        raise RuntimeError("connection failed")
    except RuntimeError:
        logger.exception("external dependency failed")

    payload = json.loads(stream.getvalue())
    assert payload["message"] == "external dependency failed"
    assert "RuntimeError: connection failed" in payload["exception"]


def test_configure_logging_uses_plain_formatter_in_dev() -> None:
    settings = Settings(_env_file=None, ENVIRONMENT="dev", LOG_LEVEL="INFO")

    configure_logging(settings)

    root_handler = logging.getLogger().handlers[0]
    assert not isinstance(root_handler.formatter, JsonLogFormatter)


def test_configure_logging_uses_json_formatter_in_prod() -> None:
    settings = Settings(_env_file=None, ENVIRONMENT="prod", LOG_LEVEL="WARNING")

    configure_logging(settings)

    root_logger = logging.getLogger()
    root_handler = root_logger.handlers[0]
    assert isinstance(root_handler.formatter, JsonLogFormatter)
    assert root_logger.level == logging.WARNING
