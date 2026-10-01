"""Rumus inti rekomendasi momentum harian (riset notebooks/research_recomendatio_trading 01-06).

Fungsi murni tanpa I/O -- dipakai service `recommendation_momentum` DAN notebook 06 (cek paritas),
supaya angka di API sama persis dengan yang diuji di notebook.

Skor  : rata-rata rank-percentile RSI(14) dan RSI(7) antar coin universe (0-1, makin tinggi makin kuat).
Daftar: 10 coin skor tertinggi -- peringkat 1-5 "UTAMA", 6-10 "PELENGKAP".
Rencana per rekomendasi (notebook 05): beli di open besok, pegang 14 hari, stop keras -25%.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RSI_FAST, RSI_SLOW = 7, 14
TOP_MAIN = 5                    # peringkat 1-5 = UTAMA
MAX_RECOMMENDATIONS = 10        # peringkat 6-10 = PELENGKAP
HOLD_DAYS = 14
HARD_STOP = 0.25
COST_PER_SIDE = 0.0015          # fee + slippage, sama dengan riset

# Bukan coin yang "bergerak" -- dikeluarkan dari universe walau ada di flex_params.
EXCLUDED = {
    # stablecoin
    "USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "USDPUSDT", "DAIUSDT", "BUSDUSDT", "AEURUSDT", "EURIUSDT",
    "BFUSDUSDT", "RLUSDUSDT", "USD1USDT", "USDEUSDT", "USDSUSDT", "UUSDT",
    # token emas
    "PAXGUSDT", "XAUTUSDT",
    # duplikat ETH
    "WBETHUSDT",
}


def rsi(close: pd.Series, n: int) -> pd.Series:
    """RSI Wilder (ewm alpha 1/n), identik dengan notebook 01-05."""
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn)


def momentum_score(closes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(skor, rsi14, rsi7) per hari x coin. Skor dihitung antar SEMUA kolom `closes`."""
    rsi14 = closes.apply(rsi, n=RSI_SLOW)
    rsi7 = closes.apply(rsi, n=RSI_FAST)
    score = (rsi14.rank(axis=1, pct=True) + rsi7.rank(axis=1, pct=True)) / 2
    return score, rsi14, rsi7


def rank_day(score_row: pd.Series, limit: int = MAX_RECOMMENDATIONS) -> list[str]:
    """Simbol urut skor tertinggi (NaN dibuang), maksimal `limit`. Seri diputus alfabetis supaya stabil."""
    s = score_row.dropna()
    return sorted(s.index, key=lambda sym: (-s[sym], sym))[:limit]


def group_of(rank: int) -> str:
    return "UTAMA" if rank <= TOP_MAIN else "PELENGKAP"


def simulate_trade(opens: np.ndarray, lows: np.ndarray, closes: np.ndarray, i: int) -> dict | None:
    """Hasil satu rekomendasi hari ke-i (index array): beli open i+1, stop keras -25%, jual close i+14.

    Kalau data belum sampai hari ke-14, status BERJALAN dan return dihitung dari close terakhir.
    Return sudah dipotong biaya 2 sisi. None kalau belum ada harga masuk.
    """
    n = len(closes)
    if i + 1 >= n or np.isnan(opens[i + 1]) or opens[i + 1] <= 0:
        return None
    entry = opens[i + 1]
    stop = entry * (1 - HARD_STOP)
    last = min(i + HOLD_DAYS, n - 1)
    for day in range(i + 1, last + 1):
        if not np.isnan(lows[day]) and lows[day] <= stop:
            op = opens[day]
            px = op if (day != i + 1 and not np.isnan(op) and op <= stop) else stop
            return dict(entry=entry, exit_idx=day, exit_price=px, status="STOP_KERAS",
                        ret=px * (1 - COST_PER_SIDE) / (entry * (1 + COST_PER_SIDE)) - 1)
    px = closes[last]
    if np.isnan(px):
        return None
    done = last == i + HOLD_DAYS
    return dict(entry=entry, exit_idx=last, exit_price=px, status="SELESAI" if done else "BERJALAN",
                ret=px * (1 - COST_PER_SIDE) / (entry * (1 + COST_PER_SIDE)) - 1)
