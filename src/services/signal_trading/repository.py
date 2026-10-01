"""Query data untuk sinyal entry: candle harian coin tertentu + Fear & Greed (read-only)."""

from __future__ import annotations

import pandas as pd

from src.databases import get_connection

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def find_daily_candles(symbols: list[str], since: pd.Timestamp) -> dict[str, pd.DataFrame]:
    """Candle harian `symbols` sejak `since` -> {symbol: OHLCV DataFrame indexed by date}."""
    since_ms = int(since.timestamp() * 1000)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT symbol, open_time, open, high, low, close, volume
            FROM market_candles
            WHERE interval = '1d' AND symbol = ANY(%s) AND open_time >= %s
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
    s = pd.Series({pd.Timestamp(d): float(v) for d, v in rows}, name="fng_value")
    return s.sort_index()
