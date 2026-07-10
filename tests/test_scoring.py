"""Unit tests for Bagian 2.5 classification rules in crypto_backtest.scoring.score."""

import pandas as pd

from crypto_backtest.scoring.score import _classify


def test_zero_total_score_is_netral_not_directional():
    """Regression test: total_score == 0 must classify as NETRAL even when the
    MA trend filter itself is BULLISH/BEARISH (Bagian 2.5). A prior bug set
    verdict = dir_label unconditionally, so a fully-cancelled-out score (e.g.
    votes +1/-1/+1/-1) was reported as a confident directional verdict.
    """
    total_score = pd.Series([0, 0, -2, 3], index=[0, 1, 2, 3])
    direction = pd.Series(["BEARISH", "BULLISH", "BEARISH", "BULLISH"], index=[0, 1, 2, 3])

    result = _classify(total_score, direction)

    assert result.loc[0, "verdict"] == "NETRAL"
    assert result.loc[0, "confidence"] is None
    assert result.loc[1, "verdict"] == "NETRAL"
    assert result.loc[1, "confidence"] is None
    assert result.loc[2, "verdict"] == "BEARISH"
    assert result.loc[2, "confidence"] == "MEDIUM"
    assert result.loc[3, "verdict"] == "BULLISH"
    assert result.loc[3, "confidence"] == "HIGH"


def test_ma_neutral_direction_always_netral_regardless_of_score():
    total_score = pd.Series([4, -4, 0])
    direction = pd.Series(["NEUTRAL", "NEUTRAL", "NEUTRAL"])

    result = _classify(total_score, direction)

    assert (result["verdict"] == "NETRAL").all()
    assert result["confidence"].isna().all()
