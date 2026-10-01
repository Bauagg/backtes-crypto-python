"""Custom error + handler. Service cukup `raise NotFoundError(...)`, tidak perlu tahu HTTP.

Body error tetap {"detail": "..."} (format bawaan FastAPI) supaya client Rust yang
sudah ada tidak perlu diubah.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BadRequestError(AppError):
    status_code = 400


class NotFoundError(AppError):
    status_code = 404


class UnprocessableError(AppError):
    status_code = 422


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})
