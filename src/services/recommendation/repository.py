"""Akses data untuk rekomendasi: model V5 (folder models/) + data pasar (DB, read-only).

Tabel DB dikelola migrasi backend-treding-rust (sqlx) -- modul ini TIDAK menulis ke DB.
Format hasil identik dengan loader CSV di notebooks/data_source, jadi strategi V5
menerima data yang sama persis dari kedua sumber.
"""

from __future__ import annotations

import pandas as pd

from src.databases import get_connection
from src.strategy import v5

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def find_model():
    """(model, scaler) RandomForest V5 (dihasilkan notebooks/train_v5_model.py)."""
    return v5.load_model()


def find_symbol_categories(categories: tuple[str, ...]) -> dict[str, str]:
    """Simbol aktif di flex_params (SIMBOL_CRYPTO) dengan description (kategori market cap) tertentu.

    Returns {symbol: kategori}, mis. {"TRXUSDT": "Large", "DOTUSDT": "Mid"}.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT value_param, description
            FROM flex_params
            WHERE type_param = 'SIMBOL_CRYPTO'
              AND deleted_at IS NULL
              AND is_active
              AND description = ANY(%s)
            """,
            (list(categories),),
        ).fetchall()
    return {sym: desc for sym, desc in rows}


def find_all_candles(interval: str = "1d") -> dict[str, pd.DataFrame]:
    """Semua candle di market_candles (satu query) -> {symbol: OHLCV DataFrame indexed by date}."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT symbol, open_time, open, high, low, close, volume
            FROM market_candles
            WHERE interval = %s
            ORDER BY symbol, open_time
            """,
            (interval,),
        ).fetchall()

    df = pd.DataFrame(rows, columns=["symbol", "open_time", *OHLCV_COLUMNS])
    df["date"] = pd.to_datetime(df["open_time"], unit="ms")
    out = {}
    for sym, g in df.groupby("symbol", sort=True):
        g = g.set_index("date")
        g = g[~g.index.duplicated(keep="last")]
        # Kolom NUMERIC Postgres datang sebagai Decimal -> konversi ke float.
        out[sym] = g[OHLCV_COLUMNS].astype(float)
    return out


def find_fear_greed_index() -> pd.DataFrame:
    """Fear & Greed Index dari tabel fear_greed_index, indexed by date, kolom fng_value."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, fng_value FROM fear_greed_index ORDER BY date"
        ).fetchall()

    df = pd.DataFrame(rows, columns=["date", "fng_value"])
    df["date"] = pd.to_datetime(df["date"])
    df["fng_value"] = df["fng_value"].astype(int)
    return df.set_index("date")
