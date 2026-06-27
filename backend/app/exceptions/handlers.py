import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..schemas.errors import ErrorResponse
from .base import AppException

logger = logging.getLogger(__name__)


class ExceptionHandlerRegistry:
    def register(self, app: FastAPI) -> None:
        app.add_exception_handler(AppException, self.handle_app_exception)
        app.add_exception_handler(StarletteHTTPException, self.handle_http_exception)
        app.add_exception_handler(RequestValidationError, self.handle_validation_error)
        app.add_exception_handler(Exception, self.handle_unexpected_error)

    async def handle_app_exception(
        self,
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
        self._log_app_exception(request, exc)

        return self._response(
            status_code=exc.status_code,
            message=exc.message,
            error_code=exc.error_code,
        )

    async def handle_http_exception(
        self,
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        status_code = HTTPStatus(exc.status_code)
        message = exc.detail if isinstance(exc.detail, str) else status_code.phrase

        return self._response(
            status_code=status_code,
            message=message,
            error_code=exc.__class__.__name__,
        )

    async def handle_validation_error(
        self,
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.info(
            "Request validation failed.",
            extra={
                "path": request.url.path,
                "method": request.method,
                "validation_errors": exc.errors(),
            },
        )

        return self._response(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            message="Request validation failed.",
            error_code="VALIDATION_ERROR",
        )

    async def handle_unexpected_error(
        self,
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception(
            "Unhandled exception while processing request.",
            extra={
                "path": request.url.path,
                "method": request.method,
            },
        )

        return self._response(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An unexpected server error occurred.",
            error_code="UNEXPECTED_ERROR",
        )

    def _response(
        self,
        *,
        status_code: HTTPStatus,
        message: str,
        error_code: str | None = None,
        error_details: list[dict] | None = None,
    ) -> JSONResponse:
        response = ErrorResponse(message=message, error_code=error_code, error_details=error_details)

        return JSONResponse(
            status_code=int(status_code),
            content=response.model_dump(mode="json"),
        )

    def _log_app_exception(self, request: Request, exc: AppException) -> None:
        log_level = logging.ERROR if exc.status_code.value >= 500 else logging.WARNING
        logger.log(
            log_level,
            exc.log_message,
            extra={
                "path": request.url.path,
                "method": request.method,
                "error": exc.to_log_payload(),
            },
            exc_info=exc.cause,
        )
