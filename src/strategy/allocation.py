"""Rumus inti strategi portofolio (hasil riset notebook 13, 15, 17, 19, 20).

Fungsi murni tanpa I/O -- dipakai service `signal`. Perilakunya harus identik dengan
notebooks/research/portfolio.py (inverse_vol_weights / apply_caps) yang dipakai saat backtest.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BTC = "BTCUSDT"

# Filter pasar H8b (notebook 13): risk-on kalau close BTC > SMA100 ATAU rata-rata FGI 14 hari > 50.
MARKET_SMA = 100
FGI_WINDOW = 14
FGI_THRESHOLD = 50

VOL_LOOKBACK = 60                 # hari untuk volatilitas inverse-vol
INVESTED_PORTION = 0.60           # 60% modal di coin, 40% USDT (V2-60 & BTC-60)
V2_COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT", "TRXUSDT", "DOGEUSDT"]
V2_CAPS = {"DOGEUSDT": 0.10}      # porsi maksimum DOGE (dari total bagian coin)
MIN_ORDER_USDT = 5.0              # order minimum Binance spot
KILL_SWITCH_DRAWDOWN = 0.30       # modal turun 30% dari modal awal -> berhenti


def market_filter(btc_close: pd.Series, fgi: pd.Series) -> pd.DataFrame:
    """Status filter pasar per hari + komponennya."""
    sma = btc_close.rolling(MARKET_SMA, min_periods=MARKET_SMA).mean()
    fgi14 = fgi.reindex(btc_close.index).ffill().rolling(FGI_WINDOW).mean()
    return pd.DataFrame({
        "btc_close": btc_close, "btc_sma100": sma, "fgi": fgi.reindex(btc_close.index).ffill(), "fgi_14h": fgi14,
        "trend_ok": btc_close > sma, "sentiment_ok": fgi14 > FGI_THRESHOLD,
        "risk_on": (btc_close > sma) | (fgi14 > FGI_THRESHOLD),
    })


def apply_caps(w: pd.DataFrame, caps: dict[str, float] | None) -> pd.DataFrame:
    """Potong porsi yang melebihi batas, bagi kelebihannya ke coin lain (sama dengan notebook)."""
    if not caps:
        return w
    w = w.copy()
    for _ in range(5):
        excess = pd.Series(0.0, index=w.index)
        for s, cap in caps.items():
            if s in w:
                over = (w[s] - cap).clip(lower=0)
                excess += over
                w[s] -= over
        free = [c for c in w.columns if c not in caps]
        tot = w[free].sum(axis=1).replace(0, np.nan)
        w[free] = w[free].add(w[free].div(tot, axis=0).fillna(0).mul(excess, axis=0))
    return w


def inverse_vol_weights(closes: pd.DataFrame, lookback: int = VOL_LOOKBACK,
                        caps: dict[str, float] | None = None) -> pd.DataFrame:
    """Porsi berbanding terbalik dengan volatilitas harian `lookback` hari; total 1 per hari."""
    vol = closes.pct_change().rolling(lookback, min_periods=lookback).std()
    raw = (1 / vol).replace([np.inf, -np.inf], np.nan)
    w = raw.div(raw.sum(axis=1), axis=0).fillna(0.0)
    return apply_caps(w, caps)
