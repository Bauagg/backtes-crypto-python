"""Bagian 1.2 -- RSI (Relative Strength Index), the momentum trigger factor."""

from __future__ import annotations

import pandas as pd

RSI_WINDOW = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30


def rsi(close: pd.Series, window: int = RSI_WINDOW) -> pd.Series:
    """Wilder's RSI using an exponential (Wilder) moving average of gains/losses."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi_value = 100 - (100 / (1 + rs))
    rsi_value[avg_loss == 0] = 100
    rsi_value[(avg_gain == 0) & (avg_loss == 0)] = 50
    return rsi_value
