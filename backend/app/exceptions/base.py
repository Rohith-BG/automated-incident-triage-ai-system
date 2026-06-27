from http import HTTPStatus
from traceback import format_stack
from typing import Any


class AppException(Exception):
    status_code: HTTPStatus = HTTPStatus.BAD_REQUEST

    def __init__(
        self,
        message: str,
        *,
        status_code: HTTPStatus | None = None,
        log_message: str | None = None,
        cause: Exception | None = None,
        capture_stack: bool = True,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code or self.status_code
        # log_message mirrors message unless overridden
        self.log_message = log_message or message
        self.cause = cause
        self.stack_trace = format_stack()[:-1] if capture_stack else []
        self.context = context or {}
        # error_code defaults to class attribute if defined, else class name
        self.error_code = getattr(self.__class__, "error_code", self.__class__.__name__)


    def to_log_payload(self) -> dict[str, Any]:
        return {
            "exception_type": self.__class__.__name__,
            "status_code": int(self.status_code),
            "status_phrase": self.status_code.phrase,
            "message": self.message,
            "log_message": self.log_message,
            "error_code": self.error_code,
            "cause": repr(self.cause) if self.cause else None,
            "stack_trace": self.stack_trace,
            "context": self.context,
        }


class BadRequestException(AppException):
    status_code = HTTPStatus.BAD_REQUEST


class UnauthorizedException(AppException):
    status_code = HTTPStatus.UNAUTHORIZED


class ForbiddenException(AppException):
    status_code = HTTPStatus.FORBIDDEN


class NotFoundException(AppException):
    status_code = HTTPStatus.NOT_FOUND


class ConflictException(AppException):
    status_code = HTTPStatus.CONFLICT


class ValidationException(AppException):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY


class TooManyRequestsException(AppException):
    status_code = HTTPStatus.TOO_MANY_REQUESTS


class ExternalDependencyException(AppException):
    status_code = HTTPStatus.BAD_GATEWAY


class ServiceUnavailableException(AppException):
    status_code = HTTPStatus.SERVICE_UNAVAILABLE


class GatewayTimeoutException(AppException):
    status_code = HTTPStatus.GATEWAY_TIMEOUT
