"""Latih & simpan model V5 produksi (dilatih di SEMUA coin yang tersedia).

Jalankan sekali untuk menghasilkan models/strategy_v5_rf.pkl + scaler.
Scalable: otomatis pakai semua coin di data/raw (10 sekarang, N nanti).
"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import json

from crypto_backtest.data.loader import load_symbol, discover_symbols
from crypto_backtest.indicators.fear_greed import load_fear_greed_index
from crypto_backtest import strategy_v5 as v5

print("="*80)
print("TRAIN MODEL V5 PRODUKSI (semua coin)")
print("="*80)

# Load semua coin yang tersedia (scalable)
coins = discover_symbols("1d", "full")
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

print(f"\nValidasi walk-forward:")
print(f"  In-sample (2018-2023):  {in_acc:.1%} ({len(train_wf)} sinyal)")
print(f"  Out-sample (2024-2026): {out_acc:.1%} ({len(test_wf)} sinyal)")
print(f"  Gap: {in_acc-out_acc:+.1%}")

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
    "stop_loss": v5.STOP_LOSS,
    "take_profit": v5.TAKE_PROFIT,
    "correlation_max": v5.CORRELATION_MAX,
    "rf_params": v5.RF_PARAMS,
    "walk_forward": {"in_sample": float(in_acc), "out_sample": float(out_acc),
                     "gap": float(in_acc-out_acc)},
    "trained_at": pd.Timestamp.now().isoformat(),
}
meta_file = v5.MODEL_DIR / "strategy_v5_meta.json"
with open(meta_file, "w", encoding="utf-8") as f:
    json.dump(meta, f, indent=2)
print(f"\nMetadata disimpan: {meta_file.name}")
print("\nSelesai. Model siap dipakai API.")
