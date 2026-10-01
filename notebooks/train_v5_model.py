"""Latih & simpan model V5 produksi (dilatih di SEMUA coin yang tersedia).

Jalankan sekali untuk menghasilkan models/strategy_v5_rf.pkl + scaler:
    python notebooks/train_v5_model.py
Coin training dikunci ke 10 coin (lihat variabel `coins`); ubah daftar itu kalau mau melatih ulang dengan coin lain.
"""

import sys
from pathlib import Path
NOTEBOOKS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = NOTEBOOKS_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))    # -> from src.strategy import v5
sys.path.insert(0, str(NOTEBOOKS_DIR))   # -> from data_source import ...

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import json

from data_source.loader import load_symbol, discover_symbols
from data_source.fear_greed import load_fear_greed_index
from src.strategy import v5

print("="*80)
print("TRAIN MODEL V5 PRODUKSI (semua coin)")
print("="*80)

# Load semua coin yang tersedia (scalable)
# Dikunci ke 10 coin model produksi (models/strategy_v5_meta.json -> trained_coins).
# notebooks/data/raw kini berisi 50 coin (termasuk stablecoin) -- jangan pakai discover_symbols di sini.
coins = ["ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT", "ETHUSDT", "HBARUSDT", "SOLUSDT", "SUIUSDT", "XRPUSDT"]
btc_df = load_symbol("BTCUSDT", "1d", "full")
fng = load_fear_greed_index()

coin_data = {}
for s in coins:
    try:
        df = load_symbol(s, "1d", "full")
        coin_data[s] = {"close": df["close"], "high": df["high"],
                        "low": df["low"], "volume": df["volume"]}
    except Exception as e:
        print(f"  skip {s}: {e}")

print(f"\nCoin dipakai untuk training: {list(coin_data.keys())} ({len(coin_data)} coin)")

# Kumpulkan data training (semua histori)
train_all = v5.collect_training_data(coin_data, btc_df["close"], fng)
print(f"Total sinyal bottoming: {len(train_all)}")

# Latih model final di SEMUA data
model, scaler = v5.train_model(train_all)
v5.save_model(model, scaler)
print(f"\nModel disimpan: {v5.MODEL_FILE.name} + {v5.SCALER_FILE.name}")

# Validasi walk-forward (train <2024, test >=2024) untuk laporan
train_wf = v5.collect_training_data(coin_data, btc_df["close"], fng, end_date="2024-01-01")
test_wf = v5.collect_training_data(coin_data, btc_df["close"], fng, start_date="2024-01-01")
m_wf, s_wf = v5.train_model(train_wf)
in_acc = m_wf.score(s_wf.transform(train_wf[v5.FEATURE_COLS].values),
                    (train_wf["forward_return"] > 0).astype(int).values)
out_acc = m_wf.score(s_wf.transform(test_wf[v5.FEATURE_COLS].values),
                     (test_wf["forward_return"] > 0).astype(int).values)

print(f"\nValidasi walk-forward (akurasi arah harga):")
print(f"  In-sample (2018-2023):  {in_acc:.1%} ({len(train_wf)} sinyal)")
print(f"  Out-sample (2024-2026): {out_acc:.1%} ({len(test_wf)} sinyal)")
print(f"  Gap: {in_acc-out_acc:+.1%}")

# Backtest realistis (day-by-day, ATR-based SL/TP) -- lihat notebooks/research_signal_trading/04_atr_based_exit.ipynb
# untuk investigasi kenapa metode lama (clamp forward_return) dibuang: terbukti bug,
# selisih win rate 35.8 poin persentase vs simulasi day-by-day yang sebenarnya.
print(f"\nBacktest realistis (day-by-day, ATR SL={v5.ATR_SL_MULTIPLIER}x / TP={v5.ATR_TP_MULTIPLIER}x):")
all_trades = []
for s, d in coin_data.items():
    feat = v5.build_features(d["close"], d["high"], d["low"], d["volume"], btc_df["close"], fng)
    ohlc = pd.DataFrame({"close": d["close"], "high": d["high"], "low": d["low"]})
    sim = v5.backtest_v5(feat, ohlc, model, scaler)
    if len(sim):
        all_trades.append(sim)
backtest_trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
if len(backtest_trades):
    n_bt = len(backtest_trades)
    win_rate_bt = float((backtest_trades["realized_return"] > 0).mean())
    ev_bt = float(backtest_trades["realized_return"].mean())
    print(f"  n_trades={n_bt}  win_rate={win_rate_bt:.1%}  EV(mean return)={ev_bt:+.3%}")
else:
    n_bt, win_rate_bt, ev_bt = 0, float("nan"), float("nan")
    print("  Tidak ada trade (cek data/model).")

# Simpan metadata model (untuk API & dokumentasi Rust)
meta = {
    "strategy": "V5",
    "trained_coins": list(coin_data.keys()),
    "n_training_signals": int(len(train_all)),
    "feature_cols": v5.FEATURE_COLS,
    "bottoming_rsi": v5.BOTTOMING_RSI,
    "bottoming_fgi": v5.BOTTOMING_FGI,
    "ml_threshold": v5.ML_THRESHOLD,
    "forward_horizon": v5.FORWARD_HORIZON,
    "exit_method": "atr_based",
    "atr_sl_multiplier": v5.ATR_SL_MULTIPLIER,
    "atr_tp_multiplier": v5.ATR_TP_MULTIPLIER,
    "correlation_max": v5.CORRELATION_MAX,
    "rf_params": v5.RF_PARAMS,
    "walk_forward": {"in_sample": float(in_acc), "out_sample": float(out_acc),
                     "gap": float(in_acc-out_acc)},
    "backtest_realistic": {
        "method": "day_by_day_intraday_high_low",
        "n_trades": n_bt, "win_rate": win_rate_bt, "ev_mean_return": ev_bt,
    },
    "trained_at": pd.Timestamp.now().isoformat(),
}
meta_file = v5.MODEL_DIR / "strategy_v5_meta.json"
with open(meta_file, "w", encoding="utf-8") as f:
    json.dump(meta, f, indent=2)
print(f"\nMetadata disimpan: {meta_file.name}")
print("\nSelesai. Model siap dipakai API.")
