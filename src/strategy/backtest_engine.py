"""Alat backtest strategi V5 (dipakai v5.py, notebooks 03/04/06 dan train_v5_model.py).

- simulate_trades: simulasi exit day-by-day (SL/TP intraday) untuk sinyal entry.
- add_forward_return_target: label return N hari ke depan untuk training / evaluasi.
"""

from __future__ import annotations

import pandas as pd

TARGET_HORIZON_DAYS = 7


def simulate_trades(feature_frame: pd.DataFrame, ohlc: pd.DataFrame, entry_mask: pd.Series,
                     sl_pct_fn, tp_pct_fn, horizon: int) -> pd.DataFrame:
    """Simulasi exit day-by-day: cek high/low intraday tiap hari untuk SL/TP tersentuh.

    Dibangun & divalidasi di notebooks/research_signal_trading/04_atr_based_exit.ipynb, menggantikan metode lama
    (clamp forward_return di akhir horizon) yang terbukti BUG -- metode lama tidak pernah
    mengecek apakah stop-loss tersentuh di tengah holding period, cuma melihat harga di hari
    terakhir. Perbandingan langsung pada data sama: metode lama mencatat win rate 58.4%,
    metode ini (realistis) mencatat 22.6% -- 42% trade hasilnya bertolak belakang.

    Args:
        feature_frame: DataFrame fitur (indexed by date), dipakai untuk evaluasi sl_pct_fn/tp_pct_fn.
        ohlc: DataFrame dengan kolom high, low, close (indexed sama dengan feature_frame).
        entry_mask: boolean Series, True di tanggal entry (sinyal BUY sudah lolos semua gate).
        sl_pct_fn: callable(row) -> float negatif, mis. -0.02 (fixed) atau -1.5*row["atr_pct"].
        tp_pct_fn: callable(row) -> float positif, mis. 0.05 (fixed) atau 2.0*row["atr_pct"].
        horizon: jumlah hari maksimal holding sebelum keluar otomatis di harga close.

    Returns:
        DataFrame satu baris per entry: entry_date, exit_day, exit_reason (SL/TP/HORIZON),
        sl_pct, tp_pct, realized_return. Entry yang datanya tidak cukup (dekat akhir data,
        atau sl_pct_fn/tp_pct_fn mengembalikan NaN) dilewati.
    """
    close = ohlc["close"].reindex(feature_frame.index)
    high = ohlc["high"].reindex(feature_frame.index)
    low = ohlc["low"].reindex(feature_frame.index)
    idx = feature_frame.index
    n = len(idx)
    pos_of = {d: i for i, d in enumerate(idx)}
    entry_dates = feature_frame.index[entry_mask.fillna(False)]

    rows = []
    for entry_date in entry_dates:
        i_entry = pos_of[entry_date]
        i_horizon_end = i_entry + horizon
        if i_horizon_end >= n:
            continue
        row = feature_frame.loc[entry_date]
        price_entry = close.iloc[i_entry]
        if pd.isna(price_entry):
            continue
        sl_pct = sl_pct_fn(row)
        tp_pct = tp_pct_fn(row)
        if pd.isna(sl_pct) or pd.isna(tp_pct):
            continue
        sl_price = price_entry * (1 + sl_pct)
        tp_price = price_entry * (1 + tp_pct)

        exit_day = None
        exit_reason = "HORIZON"
        exit_price = close.iloc[i_horizon_end]
        for k in range(1, horizon + 1):
            i_check = i_entry + k
            if i_check >= n:
                break
            hi = high.iloc[i_check]
            lo = low.iloc[i_check]
            if pd.isna(hi) or pd.isna(lo):
                continue
            hit_sl = lo <= sl_price
            hit_tp = hi >= tp_price
            if hit_sl:
                # Konservatif: kalau SL & TP sama-sama tersentuh hari yang sama, asumsikan SL duluan.
                exit_day, exit_reason, exit_price = k, "SL", sl_price
                break
            elif hit_tp:
                exit_day, exit_reason, exit_price = k, "TP", tp_price
                break
        if exit_day is None:
            exit_day = horizon
            if pd.isna(exit_price):
                continue

        realized_return = (exit_price - price_entry) / price_entry
        rows.append({
            "entry_date": entry_date, "exit_day": exit_day, "exit_reason": exit_reason,
            "sl_pct": sl_pct, "tp_pct": tp_pct, "realized_return": realized_return,
        })

    return pd.DataFrame(rows)


def add_forward_return_target(scored_frame: pd.DataFrame, close: pd.Series,
                                horizon: int = TARGET_HORIZON_DAYS) -> pd.DataFrame:
    """Attach the realized forward return / label used to grade each verdict.

    forward_return: (close[t+horizon] - close[t]) / close[t]
    actual_direction: "UP" if forward_return > 0 else "DOWN" (NaN if flat/unknown)
    """
    df = scored_frame.copy()
    aligned_close = close.reindex(df.index)
    forward_close = aligned_close.shift(-horizon)
    df["forward_return"] = (forward_close - aligned_close) / aligned_close

    actual_direction = pd.Series(index=df.index, dtype=object)
    actual_direction[df["forward_return"] > 0] = "UP"
    actual_direction[df["forward_return"] < 0] = "DOWN"
    actual_direction[df["forward_return"].isna()] = pd.NA
    df["actual_direction"] = actual_direction
    return df
