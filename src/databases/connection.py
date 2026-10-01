"""Koneksi PostgreSQL (DB milik backend-treding-rust).

URL dibaca dari DATABASE_URL di .env, format sama dengan project Rust:
    postgres://USER:PASSWORD@HOST:PORT/NAMA_DB
"""

from __future__ import annotations

import psycopg

from src.config.settings import settings


def get_database_url() -> str:
    """Ambil DATABASE_URL dari settings; error jelas kalau belum diset."""
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL belum diset. Salin .env.example jadi .env lalu isi DATABASE_URL."
        )
    return settings.database_url


def get_connection(url: str | None = None) -> psycopg.Connection:
    """Buka koneksi baru. Pakai dengan `with get_connection() as conn:` supaya tertutup otomatis.

    Tanpa connect_timeout, koneksi ke DB yang mati bisa menggantung >2 menit tanpa error.
    Dengan timeout, gagal cepat dengan psycopg.OperationalError.
    """
    return psycopg.connect(url or get_database_url(), connect_timeout=settings.db_connect_timeout)


def ping(url: str | None = None) -> bool:
    """Cek DB bisa dihubungi (SELECT 1). True kalau berhasil."""
    with get_connection(url) as conn:
        row = conn.execute("SELECT 1").fetchone()
        return row is not None and row[0] == 1
