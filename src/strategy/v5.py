"""Strategi V5 - PRODUKSI. Satu sumber kebenaran untuk training + scoring + backtest.

Strategi V5 (final, terpilih):
  - Entry candidate: bottoming EKSTREM (RSI<30 + FGI<25)
  - Fitur ML (6): rsi, volume_ratio, fng_value, relative_strength,
                  confirm_count, ma_diff_pct
  - Model: RandomForest depth=3, leaf=40, dilatih di SEMUA coin
  - Gate entry: reversal_confirmed AND regime_ok AND ml_confidence >= 0.55
  - Exit: SL/TP berbasis ATR (stop -1.5xATR, target +2.0xATR), horizon 5 hari
  - Coin ditrade: korelasi ke BTC < 0.7 (buang redundant)

Divalidasi: walk-forward gap +5.7%, leave-one-coin-out 56.2%, 5-fold 57.9%.
Backtest realistis (day-by-day, simulate_trades, semua gate termasuk ML): 89 trade,
61.8% win rate, EV +3.15% per trade (lihat models/strategy_v5_meta.json untuk angka
terbaru -- dihasilkan ulang tiap train_v5_model.py dijalankan).

SL/TP diubah dari fixed percentage (-2%/+5%) ke ATR-based (notebooks/research_signal_trading/04_atr_based_exit.ipynb):
simulasi day-by-day REALISTIS (cek high/low intraday tiap hari, bukan cuma clamp
forward_return di akhir horizon) membuktikan fixed -2%/+5% signifikan NEGATIF (Z=-6.41,
EV=-0.41%, win rate 22.6%) -- SL -2% terlalu ketat, kena noise harian di 77% trade sebelum
sempat reversal. ATR-based (k=1.5, m=2.0) memperbaiki ini drastis. Klaim performa lama
("73.7% win rate, +8.97% return") dihasilkan dari metodologi clamp yang sama dan TIDAK
merepresentasikan hasil nyata -- lihat notebook untuk detail investigasi bug-nya.

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

from src.strategy.indicators.atr import atr_pct
from src.strategy.scoring.score import build_feature_frame
from src.strategy.scoring.reversal import (
    compute_reversal_scores, add_reversal_confirmation, add_regime_filter
)
from src.strategy.backtest_engine import add_forward_return_target, simulate_trades

# ==== Parameter strategi V5 (jangan diubah tanpa re-validasi) ====
FEATURE_COLS = ["rsi", "volume_ratio", "fng_value", "relative_strength",
                "confirm_count", "ma_diff_pct"]
BOTTOMING_RSI = 30
BOTTOMING_FGI = 25
FORWARD_HORIZON = 5
ML_THRESHOLD = 0.55
CORRELATION_MAX = 0.70    # coin dgn korelasi >= ini dibuang (redundant)
ATR_SL_MULTIPLIER = -1.5   # stop-loss = entry - 1.5 x ATR
ATR_TP_MULTIPLIER = 2.0    # take-profit = entry + 2.0 x ATR
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
    feat["atr_pct"] = atr_pct(coin_high, coin_low, coin_close)
    return feat


def exit_prices(close: float, atr_pct_value: float) -> tuple[float, float]:
    """Harga stop-loss & take-profit ATR-based untuk satu entry.

    Returns (stop_loss_price, take_profit_price). NaN kalau atr_pct_value NaN
    (misal ATR belum warm-up -- butuh 14 hari data).
    """
    if pd.isna(atr_pct_value):
        return float("nan"), float("nan")
    sl_price = close * (1 + ATR_SL_MULTIPLIER * atr_pct_value)
    tp_price = close * (1 + ATR_TP_MULTIPLIER * atr_pct_value)
    return sl_price, tp_price


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
    stop_loss_price: float = float("nan")     # NaN kalau verdict != "BUY"
    take_profit_price: float = float("nan")   # NaN kalau verdict != "BUY"


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

    sl_price, tp_price = exit_prices(close, float(feature_row.get("atr_pct", np.nan)))
    if pd.isna(sl_price):
        return mk("SKIP", "ATR belum warm-up (butuh >=14 hari data)", conf)

    sig = mk("BUY", "semua gate lolos (bottoming + reversal + regime + ML)", conf)
    sig.stop_loss_price = sl_price
    sig.take_profit_price = tp_price
    return sig


def backtest_v5(feat: pd.DataFrame, ohlc: pd.DataFrame, model, scaler,
                horizon: int = FORWARD_HORIZON) -> pd.DataFrame:
    """Backtest V5 dengan simulasi exit REALISTIS (day-by-day, ATR-based SL/TP).

    Menggantikan metode lama (clamp forward_return) yang terbukti bug -- lihat
    notebooks/research_signal_trading/04_atr_based_exit.ipynb. entry_mask = semua gate non-ML lolos
    (bottoming + reversal_confirmed + regime_ok); ml_confidence dihitung per-baris
    untuk filter entry_mask ke yang >= ML_THRESHOLD sebelum simulasi, supaya trade
    yang disimulasikan persis sama dengan yang akan dieksekusi live (evaluate_signal).

    Returns DataFrame dari simulate_trades: entry_date, exit_day, exit_reason,
    sl_pct, tp_pct, realized_return.
    """
    base_mask = feat["bottoming"] & feat["reversal_confirmed"] & feat["regime_ok"]
    candidate_idx = feat.index[base_mask.fillna(False)]

    passes_ml = pd.Series(False, index=feat.index)
    for date in candidate_idx:
        row = feat.loc[date]
        conf = ml_confidence(row, model, scaler)
        if pd.notna(conf) and conf >= ML_THRESHOLD:
            passes_ml.loc[date] = True

    return simulate_trades(
        feat, ohlc, passes_ml,
        sl_pct_fn=lambda row: ATR_SL_MULTIPLIER * row.get("atr_pct", np.nan),
        tp_pct_fn=lambda row: ATR_TP_MULTIPLIER * row.get("atr_pct", np.nan),
        horizon=horizon,
    )


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
