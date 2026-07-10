"""Strategi V5 - PRODUKSI. Satu sumber kebenaran untuk training + scoring + backtest.

Strategi V5 (final, terpilih):
  - Entry candidate: bottoming EKSTREM (RSI<30 + FGI<25)
  - Fitur ML (6): rsi, volume_ratio, fng_value, relative_strength,
                  confirm_count, ma_diff_pct
  - Model: RandomForest depth=3, leaf=40, dilatih di SEMUA coin
  - Gate entry: reversal_confirmed AND regime_ok AND ml_confidence >= 0.55
  - Exit: stop -2%, target +5%, horizon 5 hari
  - Coin ditrade: korelasi ke BTC < 0.7 (buang redundant)

Divalidasi: walk-forward gap +5.7%, leave-one-coin-out 56.2%, 5-fold 57.9%.
Backtest 2024-2026: 73.7% win rate, +8.97% return.

Modul ini TIDAK bergantung pada daftar coin tertentu -- terima dict coin apa saja,
jadi scalable untuk menambah coin baru (10 -> N).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from crypto_backtest.scoring.score import build_feature_frame
from crypto_backtest.scoring.reversal import (
    compute_reversal_scores, add_reversal_confirmation, add_regime_filter
)
from crypto_backtest.backtest.engine import add_forward_return_target

# ==== Parameter strategi V5 (jangan diubah tanpa re-validasi) ====
FEATURE_COLS = ["rsi", "volume_ratio", "fng_value", "relative_strength",
                "confirm_count", "ma_diff_pct"]
BOTTOMING_RSI = 30
BOTTOMING_FGI = 25
FORWARD_HORIZON = 5
ML_THRESHOLD = 0.55
CORRELATION_MAX = 0.70    # coin dgn korelasi >= ini dibuang (redundant)
STOP_LOSS = -0.02
TAKE_PROFIT = 0.05
RF_PARAMS = dict(n_estimators=100, max_depth=3, min_samples_leaf=40, random_state=42)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = PROJECT_ROOT / "models"
MODEL_FILE = MODEL_DIR / "strategy_v5_rf.pkl"
SCALER_FILE = MODEL_DIR / "strategy_v5_scaler.pkl"


def build_features(coin_close: pd.Series, coin_high: pd.Series, coin_low: pd.Series,
                   coin_volume: pd.Series, btc_close: pd.Series,
                   fng: pd.Series) -> pd.DataFrame:
    """Bangun semua fitur + gate (reversal, regime) untuk satu coin.

    Semua kolom yang dibutuhkan strategi V5 dihasilkan di sini. Fungsi ini
    dipakai identik saat training maupun scoring live -> tidak ada train/serve skew.
    """
    feat = build_feature_frame(coin_close, coin_volume, btc_close, fng)
    feat = compute_reversal_scores(feat)
    feat = add_reversal_confirmation(feat, coin_high, coin_low, coin_close)
    feat = add_regime_filter(feat, coin_close)
    return feat


def collect_training_data(coin_data: dict[str, dict], btc_close: pd.Series,
                          fng: pd.Series, end_date: str | pd.Timestamp | None = None,
                          start_date: str | pd.Timestamp | None = None) -> pd.DataFrame:
    """Kumpulkan sinyal bottoming dari SEMUA coin untuk training.

    Args:
        coin_data: {symbol: {"close":.., "high":.., "low":.., "volume":..}}
        btc_close: seri harga BTC (untuk relative strength)
        fng: seri Fear & Greed Index
        end_date/start_date: filter periode (walk-forward)

    Returns:
        DataFrame sinyal bottoming dgn FEATURE_COLS + forward_return, bersih dari NaN.
    """
    rows = []
    for sym, d in coin_data.items():
        feat = build_features(d["close"], d["high"], d["low"], d["volume"], btc_close, fng)
        feat = add_forward_return_target(feat, d["close"], horizon=FORWARD_HORIZON)
        cand = feat[feat["bottoming"] & feat["forward_return"].notna()].copy()
        if start_date is not None:
            cand = cand[cand.index >= pd.Timestamp(start_date)]
        if end_date is not None:
            cand = cand[cand.index < pd.Timestamp(end_date)]
        for col in FEATURE_COLS:
            if col not in cand.columns:
                cand[col] = np.nan
        cand["symbol"] = sym
        rows.append(cand)
    return pd.concat(rows).dropna(subset=FEATURE_COLS)


def train_model(training_df: pd.DataFrame) -> tuple[RandomForestClassifier, StandardScaler]:
    """Latih model V5 pada data bottoming yang sudah dikumpulkan."""
    X = training_df[FEATURE_COLS].values
    y = (training_df["forward_return"] > 0).astype(int).values
    scaler = StandardScaler().fit(X)
    model = RandomForestClassifier(**RF_PARAMS)
    model.fit(scaler.transform(X), y)
    return model, scaler


def save_model(model, scaler, model_file: Path = MODEL_FILE, scaler_file: Path = SCALER_FILE):
    model_file.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_file)
    joblib.dump(scaler, scaler_file)


def load_model(model_file: Path = MODEL_FILE, scaler_file: Path = SCALER_FILE):
    return joblib.load(model_file), joblib.load(scaler_file)


def ml_confidence(feature_row: pd.Series | dict, model, scaler) -> float:
    """Probabilitas 5-hari menang untuk satu baris fitur (0-1). NaN jika fitur kurang."""
    vals = [feature_row.get(c, np.nan) for c in FEATURE_COLS]
    if any(pd.isna(v) for v in vals):
        return float("nan")
    return float(model.predict_proba(scaler.transform([vals]))[0, 1])


@dataclass
class Signal:
    symbol: str
    date: str
    verdict: str          # "BUY" atau "SKIP"
    ml_confidence: float
    reason: str
    rsi: float
    fng: float
    close: float


def evaluate_signal(feature_row: pd.Series, symbol: str, date: str, close: float,
                    model, scaler) -> Signal:
    """Terapkan semua gate strategi V5 ke satu baris -> keputusan BUY/SKIP.

    Ini fungsi inti yang dipakai API: kasih satu baris fitur, dapat verdict.
    """
    rsi = float(feature_row.get("rsi", np.nan))
    fng = float(feature_row.get("fng_value", np.nan))

    def mk(verdict, reason, conf=float("nan")):
        return Signal(symbol, date, verdict, conf, reason, rsi, fng, close)

    if not bool(feature_row.get("bottoming", False)):
        return mk("SKIP", "bukan bottoming (RSI>=30 atau FGI>=25)")
    if not bool(feature_row.get("reversal_confirmed", False)):
        return mk("SKIP", "belum ada konfirmasi reversal (falling knife?)")
    if not bool(feature_row.get("regime_ok", False)):
        return mk("SKIP", "rezim pasar buruk (crash / belum stabil)")

    conf = ml_confidence(feature_row, model, scaler)
    if pd.isna(conf):
        return mk("SKIP", "fitur tidak lengkap")
    if conf < ML_THRESHOLD:
        return mk("SKIP", f"ML confidence {conf:.2f} < {ML_THRESHOLD}", conf)

    return mk("BUY", "semua gate lolos (bottoming + reversal + regime + ML)", conf)


def correlation_to_btc(coin_data: dict[str, dict], btc_close: pd.Series) -> pd.Series:
    """Hitung korelasi return harian tiap coin ke BTC. Untuk seleksi tradeable."""
    closes = {"BTCUSDT": btc_close}
    for sym, d in coin_data.items():
        closes[sym] = d["close"]
    mn = max(s.index.min() for s in closes.values())
    mx = min(s.index.max() for s in closes.values())
    aligned = {s: v[(v.index >= mn) & (v.index <= mx)] for s, v in closes.items()}
    rets = pd.DataFrame({s: v.pct_change() for s, v in aligned.items()})
    corr = rets.corr()["BTCUSDT"].drop("BTCUSDT")
    return corr.sort_values()


def tradeable_coins(coin_data: dict[str, dict], btc_close: pd.Series,
                    max_corr: float = CORRELATION_MAX) -> list[str]:
    """Coin yang boleh ditrade: korelasi ke BTC < max_corr (buang redundant)."""
    corr = correlation_to_btc(coin_data, btc_close)
    return corr[corr < max_corr].index.tolist()
