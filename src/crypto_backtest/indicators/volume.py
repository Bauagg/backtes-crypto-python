"""Bagian 1.3 -- Volume trend, confirmation factor."""

from __future__ import annotations

import pandas as pd

VOLUME_AVG_WINDOW = 20


def volume_trend(volume: pd.Series, window: int = VOLUME_AVG_WINDOW) -> pd.DataFrame:
    """Compare recent volume against its rolling average.

    Returns a DataFrame with columns: volume_avg, volume_ratio (recent / average).
    A ratio > 1 means volume is above its recent average.
    """
    volume_avg = volume.rolling(window=window, min_periods=window).mean()
    volume_ratio = volume / volume_avg
    return pd.DataFrame({"volume_avg": volume_avg, "volume_ratio": volume_ratio})
