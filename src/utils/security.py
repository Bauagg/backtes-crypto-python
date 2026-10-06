"""Autentikasi sederhana antar-server: backend Rust mengirim header `X-API-Key`.

Aktif hanya kalau `API_KEY` diisi di .env (kalau kosong, API terbuka -- hanya untuk development).
"""

from __future__ import annotations

import hmac

from fastapi import Security
from fastapi.security import APIKeyHeader

from src.config.settings import settings
from src.utils.app_error import UnauthorizedError

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    """Tolak request tanpa / dengan API key salah. Perbandingan constant-time (anti timing attack)."""
    if not settings.api_key:
        return
    if not api_key or not hmac.compare_digest(api_key.encode(), settings.api_key.encode()):
        raise UnauthorizedError("API key tidak valid atau tidak dikirim (header X-API-Key)")
