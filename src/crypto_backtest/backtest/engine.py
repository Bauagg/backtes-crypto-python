"""Bagian 4 -- Metodologi Backtesting.

Target (Bagian 2.1): apakah close 7 hari dari sekarang lebih tinggi dari close
hari ini? Split 70% in-sample / 30% out-of-sample (Bagian 4.1), lalu hitung
win rate dan Sharpe Ratio (Bagian 4.2) dengan ambang kelayakan 55% win rate
(Bagian 4.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TARGET_HORIZON_DAYS = 7
IN_SAMPLE_FRACTION = 0.7
WIN_RATE_THRESHOLD = 0.55


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


def split_in_out_sample(df: pd.DataFrame,
                         in_sample_fraction: float = IN_SAMPLE_FRACTION) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Chronological 70/30 split (Bagian 4.1) -- no shuffling, oldest data first."""
    df = df.sort_index()
    split_idx = int(len(df) * in_sample_fraction)
    return df.iloc[:split_idx], df.iloc[split_idx:]


def _sharpe_ratio(returns: pd.Series, periods_per_year: int = 365) -> float:
    """Annualized Sharpe Ratio (Bagian 4.2): mean return / std return, scaled by sqrt(N)."""
    returns = returns.dropna()
    if len(returns) < 2 or returns.std(ddof=1) == 0:
        return float("nan")
    return (returns.mean() / returns.std(ddof=1)) * np.sqrt(periods_per_year)


@dataclass
class BacktestResult:
    sample_name: str
    n_signals: int
    n_bullish: int
    n_bearish: int
    win_rate_bullish: float
    win_rate_bearish: float
    sharpe_bullish: float
    sharpe_bearish: float
    meets_threshold: bool
    detail: pd.DataFrame = field(repr=False)
    strategy_name: str = "default"  # Distinguish 5-factor vs reversal


def evaluate_verdicts(df: pd.DataFrame, sample_name: str = "sample",
                       verdict_col: str = "verdict",
                       win_rate_threshold: float = WIN_RATE_THRESHOLD,
                       strategy_name: str = "default") -> BacktestResult:
    """Grade BULLISH/BEARISH verdicts against realized forward_return (Bagian 4.2-4.3).

    verdict_col: column to use ("verdict" for 5-factor, "reversal_verdict" for reversal).
    Win rate for BULLISH verdicts = % where forward_return > 0.
    Win rate for BEARISH verdicts = % where forward_return < 0 (correctly predicted down).
    """
    graded = df.dropna(subset=["forward_return", verdict_col])
    graded = graded[graded[verdict_col].isin(["BULLISH", "BEARISH"])]

    bullish = graded[graded[verdict_col] == "BULLISH"]
    bearish = graded[graded[verdict_col] == "BEARISH"]

    win_rate_bullish = (bullish["forward_return"] > 0).mean() if len(bullish) else float("nan")
    win_rate_bearish = (bearish["forward_return"] < 0).mean() if len(bearish) else float("nan")

    sharpe_bullish = _sharpe_ratio(bullish["forward_return"])
    # For bearish verdicts, "being right" means price fell; flip sign so a
    # correct bearish call contributes positively to the Sharpe calc.
    sharpe_bearish = _sharpe_ratio(-bearish["forward_return"])

    meets_threshold = bool(
        (pd.notna(win_rate_bullish) and win_rate_bullish > win_rate_threshold)
        or (pd.notna(win_rate_bearish) and win_rate_bearish > win_rate_threshold)
    )

    return BacktestResult(
        sample_name=sample_name,
        n_signals=len(graded),
        n_bullish=len(bullish),
        n_bearish=len(bearish),
        win_rate_bullish=win_rate_bullish,
        win_rate_bearish=win_rate_bearish,
        sharpe_bullish=sharpe_bullish,
        sharpe_bearish=sharpe_bearish,
        meets_threshold=meets_threshold,
        detail=graded,
        strategy_name=strategy_name,
    )


def run_backtest(scored_frame: pd.DataFrame, close: pd.Series,
                  horizon: int = TARGET_HORIZON_DAYS,
                  in_sample_fraction: float = IN_SAMPLE_FRACTION,
                  win_rate_threshold: float = WIN_RATE_THRESHOLD,
                  strategies: list[tuple[str, str]] | None = None) -> dict[str, dict[str, BacktestResult]]:
    """End-to-end Bagian 4 pipeline: label targets, split, evaluate multiple strategies.

    strategies: list of (verdict_col, strategy_name) tuples. Default: [("verdict", "5-factor")].
    Returns {strategy_name: {sample_name: BacktestResult}}.
    """
    if strategies is None:
        strategies = [("verdict", "5-factor")]

    labeled = add_forward_return_target(scored_frame, close, horizon=horizon)
    in_sample, out_sample = split_in_out_sample(labeled, in_sample_fraction=in_sample_fraction)

    results = {}
    for verdict_col, strategy_name in strategies:
        results[strategy_name] = {
            "in_sample": evaluate_verdicts(
                in_sample, "in_sample", verdict_col=verdict_col,
                win_rate_threshold=win_rate_threshold, strategy_name=strategy_name
            ),
            "out_sample": evaluate_verdicts(
                out_sample, "out_sample", verdict_col=verdict_col,
                win_rate_threshold=win_rate_threshold, strategy_name=strategy_name
            ),
        }
    return results
