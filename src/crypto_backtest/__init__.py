"""Crypto analysis backtest package.

Implements the 5-factor scoring strategy described in
docs/panduan_strategi_analisis_crypto.md.
"""

# Muat .env sekali saat package di-import, sebelum modul lain baca os.getenv.
# Ini memastikan URL pihak ketiga (FNG_API_URL, BINANCE_VISION_URL) dan
# konfigurasi lain terbaca konsisten baik dari api.py maupun train_v5_model.py.
try:
    from pathlib import Path as _Path
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

__version__ = "0.1.0"
