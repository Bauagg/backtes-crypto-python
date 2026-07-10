"""Unit tests for reversal bottoming/topping signals."""

import pandas as pd

from crypto_backtest.scoring.reversal import compute_reversal_scores


def _make_series(values, start="2021-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.Series(values, index=idx)


def test_bottoming_signal():
    """RSI < 30 AND FGI < 25 should classify as BULLISH bottoming."""
    n = 260
    feature_frame = pd.DataFrame({
        "rsi": _make_series([20] * n),  # Oversold
        "fng_value": _make_series([20] * n),  # Extreme fear
    })

    result = compute_reversal_scores(feature_frame)

    assert (result["bottoming"] == True).all()
    assert (result["reversal_verdict"] == "BULLISH").all()
    assert (result["reversal_confidence"] == "HIGH").all()


def test_topping_signal():
    """RSI > 70 AND FGI > 75 should classify as BEARISH topping."""
    n = 260
    feature_frame = pd.DataFrame({
        "rsi": _make_series([80] * n),  # Overbought
        "fng_value": _make_series([80] * n),  # Extreme greed
    })

    result = compute_reversal_scores(feature_frame)

    assert (result["topping"] == True).all()
    assert (result["reversal_verdict"] == "BEARISH").all()
    assert (result["reversal_confidence"] == "HIGH").all()


def test_no_reversal():
    """Normal RSI & FGI should classify as NETRAL."""
    n = 260
    feature_frame = pd.DataFrame({
        "rsi": _make_series([50] * n),  # Middle range
        "fng_value": _make_series([50] * n),  # Neutral sentiment
    })

    result = compute_reversal_scores(feature_frame)

    assert (result["bottoming"] == False).all()
    assert (result["topping"] == False).all()
    assert (result["reversal_verdict"] == "NETRAL").all()
    assert result["reversal_confidence"].isna().all()
