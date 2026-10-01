"""Konfigurasi aplikasi, dibaca sekali dari .env (satu-satunya tempat baca os.getenv di backend)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


@dataclass(frozen=True)
class Settings:
    api_host: str
    api_port: int
    database_url: str | None
    db_connect_timeout: int   # detik per percobaan koneksi DB
    market_cache_ttl: int     # detik sebelum data pasar dari DB dimuat ulang
    usdt_idr_rate: float      # kurs default IDR per USDT kalau request tidak mengirim kurs


settings = Settings(
    api_host=os.getenv("API_HOST", "0.0.0.0"),
    api_port=int(os.getenv("API_PORT", "8000")),
    database_url=os.getenv("DATABASE_URL"),
    db_connect_timeout=int(os.getenv("DB_CONNECT_TIMEOUT", "5")),
    market_cache_ttl=int(os.getenv("MARKET_CACHE_TTL", "3600")),
    usdt_idr_rate=float(os.getenv("USDT_IDR_RATE", "16300")),
)
