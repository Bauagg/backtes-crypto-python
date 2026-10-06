"""Custom error + handler. Service cukup `raise NotFoundError(...)`, tidak perlu tahu HTTP.

Body error tetap {"detail": "..."} (format bawaan FastAPI) supaya client Rust yang
sudah ada tidak perlu diubah.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.config.logger import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    status_code = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BadRequestError(AppError):
    status_code = 400


class NotFoundError(AppError):
    status_code = 404


class UnauthorizedError(AppError):
    status_code = 401


class UnprocessableError(AppError):
    status_code = 422


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Detail error (stack trace, query, path file) hanya ke log server, tidak pernah ke client.
        logger.exception("Error tak terduga di %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Terjadi kesalahan di server"})
