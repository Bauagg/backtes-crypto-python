"""Bagian 2 -- Strategi Skoring: MA sebagai filter arah + 4 faktor vote.

Total Skor = vote(RSI) + vote(Volume) + vote(FearGreed) + vote(RelativeStrength)
Rentang: -4 sampai +4 (lihat Bagian 2.4 dan 2.5).
"""

from __future__ import annotations

import pandas as pd

from crypto_backtest.indicators.moving_average import ma_trend_state
from crypto_backtest.indicators.rsi import rsi, RSI_OVERBOUGHT, RSI_OVERSOLD
from crypto_backtest.indicators.volume import volume_trend
from crypto_backtest.indicators.relative_strength import relative_strength_vs_btc
from crypto_backtest.indicators.fear_greed import FNG_EXTREME_FEAR, FNG_EXTREME_GREED

RSI_WEEKLY_WINDOW = 7  # "RSI mingguan" per Bagian 2.2 -- RSI dihitung di atas
                        # rolling window mingguan pada data harian.
VOLUME_RATIO_BULLISH = 1.2  # volume > 120% rata-rata dianggap konfirmasi kuat
VOLUME_RATIO_BEARISH = 0.8  # volume < 80% rata-rata dianggap lemah


def _vote_rsi(rsi_value: float, direction: str) -> int:
    """RSI trigger vote (Bagian 1.2): overbought favors bearish, oversold favors bullish."""
    if pd.isna(rsi_value) or direction is None or pd.isna(direction):
        return 0
    if direction == "BULLISH":
        if rsi_value <= RSI_OVERSOLD:
            return 1
        if rsi_value >= RSI_OVERBOUGHT:
            return -1
        return 0
    if direction == "BEARISH":
        if rsi_value >= RSI_OVERBOUGHT:
            return 1
        if rsi_value <= RSI_OVERSOLD:
            return -1
        return 0
    return 0


def _vote_volume(volume_ratio: float, price_change: float, direction: str) -> int:
    """Volume confirmation vote (Bagian 1.3): high volume backing the trend's own price move."""
    if pd.isna(volume_ratio) or pd.isna(price_change) or direction is None or pd.isna(direction):
        return 0
    strong = volume_ratio >= VOLUME_RATIO_BULLISH
    weak = volume_ratio <= VOLUME_RATIO_BEARISH
    moving_up = price_change > 0
    moving_down = price_change < 0

    if direction == "BULLISH":
        if strong and moving_up:
            return 1
        if weak or moving_down:
            return -1
        return 0
    if direction == "BEARISH":
        if strong and moving_down:
            return 1
        if weak or moving_up:
            return -1
        return 0
    return 0


def _vote_fear_greed(fng_value: float, direction: str) -> int:
    """Fear & Greed contrarian vote (Bagian 1.4): extreme fear favors bullish, extreme greed favors bearish."""
    if pd.isna(fng_value) or direction is None or pd.isna(direction):
        return 0
    if direction == "BULLISH":
        if fng_value <= FNG_EXTREME_FEAR:
            return 1
        if fng_value >= FNG_EXTREME_GREED:
            return -1
        return 0
    if direction == "BEARISH":
        if fng_value >= FNG_EXTREME_GREED:
            return 1
        if fng_value <= FNG_EXTREME_FEAR:
            return -1
        return 0
    return 0


def _vote_relative_strength(rs_value: float, direction: str) -> int:
    """Relative strength vs BTC vote (Bagian 1.5): outperformance backs bullish, underperformance backs bearish."""
    if pd.isna(rs_value) or direction is None or pd.isna(direction):
        return 0
    if direction == "BULLISH":
        return 1 if rs_value > 0 else (-1 if rs_value < 0 else 0)
    if direction == "BEARISH":
        return 1 if rs_value < 0 else (-1 if rs_value > 0 else 0)
    return 0


def _classify(total_score: pd.Series, direction: pd.Series) -> pd.DataFrame:
    """Bagian 2.5 -- Klasifikasi Confidence."""
    verdict = pd.Series(index=total_score.index, dtype=object)
    confidence = pd.Series(index=total_score.index, dtype=object)

    is_neutral_dir = direction == "NEUTRAL"
    verdict[is_neutral_dir] = "NETRAL"
    confidence[is_neutral_dir] = None

    for dir_label, score_sign in (("BULLISH", 1), ("BEARISH", -1)):
        mask = direction == dir_label
        abs_score = total_score[mask].abs()

        verd = pd.Series(index=total_score[mask].index, dtype=object)
        conf = pd.Series(index=total_score[mask].index, dtype=object)

        verd[abs_score == 0] = "NETRAL"
        conf[abs_score == 0] = None

        nonzero = abs_score > 0
        verd[nonzero] = dir_label
        conf[nonzero & (abs_score >= 3)] = "HIGH"
        conf[nonzero & (abs_score >= 1) & (abs_score <= 2)] = "MEDIUM"

        verdict.loc[mask] = verd
        confidence.loc[mask] = conf

    unknown = direction.isna()
    verdict[unknown] = None
    confidence[unknown] = None

    return pd.DataFrame({"verdict": verdict, "confidence": confidence})


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


def compute_scores(feature_frame: pd.DataFrame) -> pd.DataFrame:
    """Apply Bagian 2.3-2.5 scoring rules to a feature frame from build_feature_frame().

    Returns feature_frame augmented with per-factor votes, total_score,
    verdict, and confidence columns.
    """
    df = feature_frame.copy()
    direction = df["trend_state"]

    df["vote_rsi"] = [
        _vote_rsi(r, d) for r, d in zip(df["rsi"], direction)
    ]
    df["vote_volume"] = [
        _vote_volume(vr, pc, d)
        for vr, pc, d in zip(df["volume_ratio"], df["price_change_pct"], direction)
    ]
    df["vote_fear_greed"] = [
        _vote_fear_greed(f, d) for f, d in zip(df["fng_value"], direction)
    ]
    df["vote_relative_strength"] = [
        _vote_relative_strength(rs, d) for rs, d in zip(df["relative_strength"], direction)
    ]

    df["total_score"] = (
        df["vote_rsi"] + df["vote_volume"] + df["vote_fear_greed"] + df["vote_relative_strength"]
    )

    classification = _classify(df["total_score"], direction)
    df["verdict"] = classification["verdict"]
    df["confidence"] = classification["confidence"]

    return df
