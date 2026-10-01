"""Average True Range -- ukuran volatilitas per-coin untuk SL/TP dinamis.

Dibangun & divalidasi di notebooks/research_signal_trading/04_atr_based_exit.ipynb: SL/TP fixed percentage
(-2%/+5%) terbukti signifikan negatif saat disimulasikan realistis (stop-loss ketat
kena noise harian di mayoritas coin volatile). ATR-based menyesuaikan tiap coin.
"""

from __future__ import annotations

import pandas as pd

ATR_WINDOW = 14


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True Range: rentang terbesar antara high-low, high-prev_close, low-prev_close."""
    prev_close = close.shift(1)
    return pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = ATR_WINDOW) -> pd.Series:
    """Average True Range: rolling mean dari True Range."""
    return true_range(high, low, close).rolling(window=window, min_periods=window).mean()


def atr_pct(high: pd.Series, low: pd.Series, close: pd.Series,
            window: int = ATR_WINDOW) -> pd.Series:
    """ATR sebagai persentase dari harga -- bisa dibandingkan lintas coin & waktu."""
    return atr(high, low, close, window) / close
