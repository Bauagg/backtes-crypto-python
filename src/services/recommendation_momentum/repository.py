"""Query data rekomendasi momentum: universe flex_params, candle harian, Fear & Greed (read-only).

Tabel DB dikelola backend Rust -- modul ini TIDAK menulis ke DB.
"""

from __future__ import annotations

import pandas as pd

from src.databases import get_connection

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def find_symbols(categories: tuple[str, ...]) -> dict[str, dict]:
    """Simbol aktif di flex_params (SIMBOL_CRYPTO) dengan kategori market cap tertentu.

    Returns {symbol: {"id": UUID baris flex_params (str), "category": "Large"/"Mid", "image_url": URL logo / None}}.
    `photo_url` = logo coin dari CoinGecko yang disimpan & disajikan backend Rust (/files/...).
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, value_param, description, photo_url
            FROM flex_params
            WHERE type_param = 'SIMBOL_CRYPTO'
              AND deleted_at IS NULL
              AND is_active
              AND description = ANY(%s)
            """,
            (list(categories),),
        ).fetchall()
    return {sym: {"id": str(fid), "category": desc, "image_url": url} for fid, sym, desc, url in rows}


def find_daily_candles(symbols: list[str], since: pd.Timestamp) -> dict[str, pd.DataFrame]:
    """Candle harian `symbols` sejak `since` -> {symbol: OHLCV DataFrame indexed by date}."""
    since_ms = int(since.timestamp() * 1000)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT symbol, open_time, open, high, low, close, volume
            FROM candle_ohlcv
            WHERE interval = '1d' AND symbol = ANY(%s) AND open_time >= %s
              AND close_time < EXTRACT(EPOCH FROM now()) * 1000   -- hanya candle yang sudah tutup
            ORDER BY symbol, open_time
            """,
            (symbols, since_ms),
        ).fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "open_time", *OHLCV_COLUMNS])
    df["date"] = pd.to_datetime(df["open_time"], unit="ms")
    out = {}
    for sym, g in df.groupby("symbol", sort=True):
        g = g.set_index("date")
        out[sym] = g[~g.index.duplicated(keep="last")][OHLCV_COLUMNS].astype(float)
    return out


def find_fear_greed(since: pd.Timestamp) -> pd.Series:
    """Nilai Fear & Greed harian sejak `since`, indexed by date."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, fng_value FROM fear_greed_index WHERE date >= %s ORDER BY date",
            (since.date(),),
        ).fetchall()
    return pd.Series({pd.Timestamp(d): float(v) for d, v in rows}, name="fng_value").sort_index()
