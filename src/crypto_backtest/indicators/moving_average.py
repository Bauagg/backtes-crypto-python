"""Bagian 1.1 -- Moving Average filter (Golden Cross / Death Cross).

MA is treated as a LAGGING trend filter, not an equal vote alongside the
other four factors (see docs/panduan_strategi_analisis_crypto.md, Bagian 2.3).
"""

from __future__ import annotations

import pandas as pd

MA_FAST_WINDOW = 20
MA_SLOW_WINDOW = 50
NEUTRAL_BAND_PCT = 0.01  # selisih < 1% dianggap NETRAL


def moving_average(close: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average (SMA) over `window` periods."""
    return close.rolling(window=window, min_periods=window).mean()


def ma_trend_state(close: pd.Series, fast_window: int = MA_FAST_WINDOW,
                    slow_window: int = MA_SLOW_WINDOW,
                    neutral_band_pct: float = NEUTRAL_BAND_PCT) -> pd.DataFrame:
    """Compute MA fast/slow and classify the trend filter state per Bagian 2.3.

    Default windows are MA20/MA50 rather than the MA50/MA200 named in the guide's
    worked example -- with ~1y of daily data, MA200 only warms up in the last
    ~19 rows, leaving too few signals to backtest. MA20/MA50 keeps the same
    "fast crosses slow" trend-filter logic while yielding a usable sample size.
    Pass fast_window=50, slow_window=200 explicitly to reproduce the original spec.

    Returns a DataFrame with columns: ma_fast, ma_slow, ma_diff_pct, trend_state.
    trend_state is one of "BULLISH", "BEARISH", "NEUTRAL" (or NaN while MAs warm up).
    """
    ma_fast = moving_average(close, fast_window)
    ma_slow = moving_average(close, slow_window)
    diff_pct = (ma_fast - ma_slow) / ma_slow

    trend_state = pd.Series(index=close.index, dtype=object)
    trend_state[diff_pct > neutral_band_pct] = "BULLISH"
    trend_state[diff_pct < -neutral_band_pct] = "BEARISH"
    trend_state[diff_pct.abs() <= neutral_band_pct] = "NEUTRAL"
    trend_state[diff_pct.isna()] = None

    return pd.DataFrame({
        "ma_fast": ma_fast,
        "ma_slow": ma_slow,
        "ma_diff_pct": diff_pct,
        "trend_state": trend_state,
    })
