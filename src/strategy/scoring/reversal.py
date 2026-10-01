"""Strategi reversal bottoming (alternative ke 5-faktor).

Berbeda dari 5-faktor scoring (Bagian 2), strategi ini fokus pada signal kontrarian:
- Bottoming: RSI < 30 AND FGI < 25 (extreme oversold + fear) → BULLISH reversal
- Topping: RSI > 70 AND FGI > 75 (extreme overbought + greed) → BEARISH reversal
- Else: NETRAL (tidak ada reversal opportunity)

Target: menangkap mean reversion di extreme condition. Tanpa filter MA trend
(karena reversal bisa terjadi di trend apapun).
"""

from __future__ import annotations

import pandas as pd

from src.strategy.indicators.rsi import RSI_OVERBOUGHT, RSI_OVERSOLD
from src.strategy.indicators.fear_greed import FNG_EXTREME_FEAR, FNG_EXTREME_GREED
from src.strategy.indicators.moving_average import moving_average


def compute_reversal_scores(feature_frame: pd.DataFrame) -> pd.DataFrame:
    """Detect bottoming/topping reversal opportunities.

    Returns feature_frame augmented with:
    - bottoming: bool, True if RSI < 30 AND FGI < 25
    - topping: bool, True if RSI > 70 AND FGI > 75
    - reversal_verdict: "BULLISH" (bottoming), "BEARISH" (topping), or "NETRAL"
    - reversal_confidence: "HIGH" if bottoming/topping, else None
    """
    df = feature_frame.copy()

    rsi = df.get("rsi", pd.Series(float("nan"), index=df.index))
    fng = df.get("fng_value", pd.Series(float("nan"), index=df.index))

    bottoming = (rsi <= RSI_OVERSOLD) & (fng <= FNG_EXTREME_FEAR)
    topping = (rsi >= RSI_OVERBOUGHT) & (fng >= FNG_EXTREME_GREED)

    df["bottoming"] = bottoming
    df["topping"] = topping

    verdict = pd.Series(index=df.index, dtype=object)
    confidence = pd.Series(index=df.index, dtype=object)

    verdict[bottoming] = "BULLISH"
    confidence[bottoming] = "HIGH"

    verdict[topping] = "BEARISH"
    confidence[topping] = "HIGH"

    not_reversal = ~(bottoming | topping)
    verdict[not_reversal] = "NETRAL"
    confidence[not_reversal] = None

    df["reversal_verdict"] = verdict
    df["reversal_confidence"] = confidence

    return df


def add_reversal_confirmation(feature_frame: pd.DataFrame,
                              high: pd.Series,
                              low: pd.Series,
                              close: pd.Series) -> pd.DataFrame:
    """Tambah konfirmasi pembalikan (Perbaikan #1 - anti falling knife).

    Bottoming saja (RSI<30 + FGI<25) bisa bertahan berhari-hari saat downtrend.
    Fungsi ini menambah bukti bahwa pembalikan SEDANG terjadi, bukan cuma oversold:

    - confirm_higher_close: close hari ini > close kemarin (harga mulai naik)
    - confirm_break_high:   close hari ini > high kemarin (menembus resistance harian)
    - confirm_rsi_rising:   RSI hari ini > RSI kemarin (momentum berbalik naik)
    - confirm_bullish_div:  harga bikin lower low tapi RSI bikin higher low (divergence)
    - confirm_not_falling:  bukan lower low 2 hari beruntun (falling knife berhenti)

    Kolom `reversal_confirmed`: True hanya jika bottoming AND minimal 2 dari sinyal
    konfirmasi di atas terpenuhi. Ini yang dipakai untuk gate entry.
    """
    df = feature_frame.copy()
    rsi_series = df.get("rsi", pd.Series(float("nan"), index=df.index))

    close = close.reindex(df.index)
    high = high.reindex(df.index)
    low = low.reindex(df.index)

    prev_close = close.shift(1)
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_rsi = rsi_series.shift(1)

    # 1. Close hari ini > close kemarin (harga berbalik naik)
    confirm_higher_close = close > prev_close

    # 2. Close menembus high kemarin (break resistance harian)
    confirm_break_high = close > prev_high

    # 3. RSI naik dari kemarin (momentum berbalik)
    confirm_rsi_rising = rsi_series > prev_rsi

    # 4. Bullish divergence: harga lower low, tapi RSI higher low
    confirm_bullish_div = (low < prev_low) & (rsi_series > prev_rsi)

    # 5. Bukan lower low beruntun (pisau jatuh berhenti)
    confirm_not_falling = ~((low < prev_low) & (prev_low < low.shift(2)))

    df["confirm_higher_close"] = confirm_higher_close.fillna(False)
    df["confirm_break_high"] = confirm_break_high.fillna(False)
    df["confirm_rsi_rising"] = confirm_rsi_rising.fillna(False)
    df["confirm_bullish_div"] = confirm_bullish_div.fillna(False)
    df["confirm_not_falling"] = confirm_not_falling.fillna(False)

    # Hitung berapa banyak konfirmasi terpenuhi
    confirm_count = (
        df["confirm_higher_close"].astype(int)
        + df["confirm_break_high"].astype(int)
        + df["confirm_rsi_rising"].astype(int)
        + df["confirm_bullish_div"].astype(int)
        + df["confirm_not_falling"].astype(int)
    )
    df["confirm_count"] = confirm_count

    # Reversal terkonfirmasi: bottoming AND minimal 2 konfirmasi
    bottoming = df.get("bottoming", pd.Series(False, index=df.index))
    df["reversal_confirmed"] = bottoming & (confirm_count >= 2)

    return df


def add_regime_filter(feature_frame: pd.DataFrame,
                      close: pd.Series,
                      ma_window: int = 200,
                      crash_lookback: int = 5,
                      crash_threshold: float = -0.15,
                      stable_days: int = 2) -> pd.DataFrame:
    """Perbaikan #3 - Filter rezim pasar (jangan trade di tengah kejatuhan).

    Bottoming works di sideways/akhir bear, BUKAN di tengah downtrend kuat.
    Fungsi ini menandai kondisi pasar:

    - below_ma200:     harga di bawah MA200 (downtrend struktural)
    - crashing:        turun > 15% dalam 5 hari terakhir (kejatuhan tajam)
    - price_stable:    harga tidak bikin lower low >= 2 hari (mulai stabil)
    - regime_ok:       AMAN untuk bottoming entry:
                       BUKAN crashing DAN harga sudah stabil >= stable_days

    Catatan: below_ma200 saja tidak memblokir (bottoming justru sering di bawah
    MA200 di akhir bear). Yang diblokir adalah CRASHING + belum stabil.
    """
    df = feature_frame.copy()
    close = close.reindex(df.index)

    ma_long = moving_average(close, ma_window)
    df["below_ma200"] = (close < ma_long).fillna(False)

    # Kejatuhan tajam: return crash_lookback hari
    roll_return = close.pct_change(crash_lookback)
    df["crashing"] = (roll_return < crash_threshold).fillna(False)

    # Harga stabil: tidak lower low selama `stable_days` hari beruntun
    is_lower_low = close < close.shift(1)
    # rolling sum of lower-low flags over stable_days; stable jika < stable_days
    lower_low_streak = is_lower_low.rolling(stable_days, min_periods=stable_days).sum()
    df["price_stable"] = (lower_low_streak < stable_days).fillna(False)

    df["regime_ok"] = (~df["crashing"]) & df["price_stable"]

    return df
