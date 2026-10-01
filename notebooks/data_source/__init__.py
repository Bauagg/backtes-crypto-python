"""Sumber data untuk analisis (CSV Binance Vision + Fear & Greed alternative.me).

Backend (src/) TIDAK memakai modul ini -- backend baca dari DB.
.env dimuat di sini supaya FNG_API_URL / BINANCE_VISION_URL terbaca di notebook.
"""

from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass
