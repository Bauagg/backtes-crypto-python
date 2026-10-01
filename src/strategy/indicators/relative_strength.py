"""Bagian 1.5 -- Relative Strength vs BTC (independence-of-signal factor)."""

from __future__ import annotations

import pandas as pd

RS_WINDOW = 7  # selaras dengan horizon target 7 hari (Bagian 2.1)


def relative_strength_vs_btc(coin_close: pd.Series, btc_close: pd.Series,
                              window: int = RS_WINDOW) -> pd.Series:
    """Relative Strength = Return Koin(%) - Return BTC(%) over `window` periods.

    Both series must share the same DatetimeIndex; misaligned dates are aligned
    via inner join before computing returns.
    """
    coin_close, btc_close = coin_close.align(btc_close, join="inner")
    coin_return = coin_close.pct_change(window)
    btc_return = btc_close.pct_change(window)
    return coin_return - btc_return
