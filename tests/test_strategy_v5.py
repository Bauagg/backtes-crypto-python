"""Test strategi V5: fitur, gate, training, dan model produksi."""

import pandas as pd
import numpy as np
import pytest

from crypto_backtest.data.loader import load_symbol
from crypto_backtest.indicators.fear_greed import load_fear_greed_index
from crypto_backtest import strategy_v5 as v5


@pytest.fixture(scope="module")
def data():
    btc = load_symbol("BTCUSDT", "1d", "full")
    fng = load_fear_greed_index()
    return btc, fng


def test_build_features_has_required_columns(data):
    btc, fng = data
    feat = v5.build_features(btc["close"], btc["high"], btc["low"], btc["volume"],
                             btc["close"], fng)
    # Semua kolom yang dibutuhkan gate & ML harus ada
    for col in v5.FEATURE_COLS + ["bottoming", "reversal_confirmed", "regime_ok"]:
        assert col in feat.columns, f"kolom {col} hilang"


def test_model_loads_and_scores(data):
    btc, fng = data
    model, scaler = v5.load_model()
    feat = v5.build_features(btc["close"], btc["high"], btc["low"], btc["volume"],
                             btc["close"], fng)
    # Ambil satu baris bottoming untuk skor
    bottoming = feat[feat["bottoming"]]
    assert len(bottoming) > 0
    row = bottoming.iloc[-1]
    conf = v5.ml_confidence(row, model, scaler)
    assert 0.0 <= conf <= 1.0


def test_evaluate_signal_verdict(data):
    btc, fng = data
    model, scaler = v5.load_model()
    feat = v5.build_features(btc["close"], btc["high"], btc["low"], btc["volume"],
                             btc["close"], fng)
    row = feat.iloc[-1]
    sig = v5.evaluate_signal(row, "BTCUSDT", str(feat.index[-1].date()),
                             float(btc["close"].iloc[-1]), model, scaler)
    assert sig.verdict in ("BUY", "SKIP")


def test_non_bottoming_is_skipped(data):
    btc, fng = data
    model, scaler = v5.load_model()
    feat = v5.build_features(btc["close"], btc["high"], btc["low"], btc["volume"],
                             btc["close"], fng)
    # Baris yang jelas bukan bottoming (RSI tinggi)
    high_rsi = feat[(feat["rsi"] > 60) & feat["rsi"].notna()]
    assert len(high_rsi) > 0
    row = high_rsi.iloc[0]
    sig = v5.evaluate_signal(row, "BTCUSDT", "2024-01-01", 50000.0, model, scaler)
    assert sig.verdict == "SKIP"
