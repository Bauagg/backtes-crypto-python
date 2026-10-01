"""Bangun tabel fitur indikator (MA, RSI mingguan, volume, relative strength, Fear & Greed)
untuk satu coin -- dasar fitur strategi V5 (v5.build_features)."""

from __future__ import annotations

import pandas as pd

from src.strategy.indicators.moving_average import ma_trend_state
from src.strategy.indicators.rsi import rsi
from src.strategy.indicators.volume import volume_trend
from src.strategy.indicators.relative_strength import relative_strength_vs_btc

RSI_WEEKLY_WINDOW = 7  # "RSI mingguan" per Bagian 2.2 -- RSI dihitung di atas
                        # rolling window mingguan pada data harian.


def build_feature_frame(coin_close: pd.Series, coin_volume: pd.Series,
                         btc_close: pd.Series, fng: pd.Series) -> pd.DataFrame:
    """Assemble all raw indicator values (Bagian 1) into one aligned DataFrame."""
    ma = ma_trend_state(coin_close)
    rsi_weekly = rsi(coin_close, window=RSI_WEEKLY_WINDOW).rename("rsi")
    vol = volume_trend(coin_volume)
    rel_strength = relative_strength_vs_btc(coin_close, btc_close).rename("relative_strength")
    price_change_pct = coin_close.pct_change().rename("price_change_pct")

    frame = pd.concat(
        [ma, rsi_weekly, vol, rel_strength, price_change_pct], axis=1
    )
    # fng is a DataFrame with 'fng_value' column; just join directly
    frame = frame.join(fng, how="left")
    frame["fng_value"] = frame["fng_value"].ffill()
    return frame
