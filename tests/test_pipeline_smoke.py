"""Smoke test: full pipeline runs end-to-end on the bundled BTCUSDT data."""

import pandas as pd

from crypto_backtest.data.loader import load_symbol
from crypto_backtest.scoring.score import build_feature_frame, compute_scores
from crypto_backtest.backtest.engine import run_backtest


def test_full_pipeline_runs_on_btcusd():
    df = load_symbol("BTCUSDT", "1d", "full")
    assert not df.empty

    # No live FGI in unit tests -- use a flat neutral series aligned to the data.
    fng = pd.Series(50, index=df.index, name="fng_value")

    features = build_feature_frame(
        coin_close=df["close"],
        coin_volume=df["volume"],
        btc_close=df["close"],
        fng=fng,
    )
    scored = compute_scores(features)
    assert "total_score" in scored.columns
    assert scored["total_score"].dropna().between(-4, 4).all()

    results = run_backtest(scored, df["close"])
    # New API: results[strategy_name][sample_name]
    assert "5-factor" in results
    assert "in_sample" in results["5-factor"] and "out_sample" in results["5-factor"]
    assert results["5-factor"]["in_sample"].n_signals >= 0
