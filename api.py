"""FastAPI untuk strategi V5 - dipanggil backend Rust.

Endpoint:
  GET  /health                    -> cek API hidup
  GET  /strategy                  -> metadata & parameter strategi V5
  GET  /coins                     -> daftar coin tersedia + korelasi ke BTC
  POST /score                     -> skor 1 coin pada 1 tanggal (verdict BUY/SKIP)
  POST /scan                      -> scan semua coin tradeable, kembalikan sinyal BUY hari terbaru
  POST /backtest                  -> jalankan backtest V5 pada rentang tanggal

Jalankan:  uvicorn api:app --host 0.0.0.0 --port 8000
Rust panggil endpoint ini via HTTP, dapat respons JSON.
"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import warnings
warnings.filterwarnings("ignore")

import json
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from crypto_backtest.data.loader import load_symbol, discover_symbols
from crypto_backtest.indicators.fear_greed import load_fear_greed_index
from crypto_backtest.backtest.engine import add_forward_return_target
from crypto_backtest import strategy_v5 as v5

app = FastAPI(
    title="Crypto Strategy V5 API",
    description="API strategi bottoming V5 (ML + reversal + regime filter) untuk backend Rust",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ==== State global: dimuat sekali saat startup ====
STATE: dict = {}


def _load_state():
    """Muat data coin, FNG, dan model V5 ke memori (sekali)."""
    coins = discover_symbols("1d", "full")
    btc_df = load_symbol("BTCUSDT", "1d", "full")
    fng = load_fear_greed_index()

    coin_dfs = {}
    coin_data = {}
    for s in coins:
        try:
            df = load_symbol(s, "1d", "full")
            coin_dfs[s] = df
            coin_data[s] = {"close": df["close"], "high": df["high"],
                            "low": df["low"], "volume": df["volume"]}
        except Exception:
            pass

    model, scaler = v5.load_model()
    meta_file = v5.MODEL_DIR / "strategy_v5_meta.json"
    meta = json.load(open(meta_file)) if meta_file.exists() else {}

    # Precompute fitur tiap coin (untuk scoring cepat)
    feats = {}
    for s, d in coin_data.items():
        feats[s] = v5.build_features(d["close"], d["high"], d["low"], d["volume"],
                                     btc_df["close"], fng)

    corr = v5.correlation_to_btc(coin_data, btc_df["close"])
    tradeable = corr[corr < v5.CORRELATION_MAX].index.tolist()

    STATE.update(dict(coin_dfs=coin_dfs, coin_data=coin_data, btc_df=btc_df, fng=fng,
                      model=model, scaler=scaler, meta=meta, feats=feats,
                      corr=corr, tradeable=tradeable))


@app.on_event("startup")
def startup():
    _load_state()


# ==== Skema request/response ====
class ScoreRequest(BaseModel):
    symbol: str = Field(..., examples=["BNBUSDT"])
    date: str = Field(..., examples=["2025-11-22"], description="YYYY-MM-DD")


class ScanRequest(BaseModel):
    date: str | None = Field(None, examples=["2026-06-30"],
                             description="Tanggal scan; default = tanggal terbaru")
    only_tradeable: bool = Field(True, description="Hanya coin korelasi<0.7 ke BTC")


class BacktestRequest(BaseModel):
    start: str = Field("2024-01-01", examples=["2024-01-01"])
    end: str = Field("2026-06-30", examples=["2026-06-30"])
    initial_capital: float = Field(1000.0, gt=0)
    position_fraction: float = Field(0.20, gt=0, le=1)
    only_tradeable: bool = True


def normalize_symbol(symbol: str) -> str:
    """Normalisasi simbol ke format internal (BTCUSDT).

    Menerima berbagai format dari Tokocrypto/Binance:
      BTCUSDT / btcusdt / BTC_USDT / BTC-USDT / BTC/USDT  -> BTCUSDT
    Tokocrypto memakai BTCUSDT (tanpa pemisah), tapi adapter ini defensif
    agar backend Rust tidak perlu khawatir soal format.
    """
    return symbol.upper().replace("_", "").replace("-", "").replace("/", "").strip()


# ==== Endpoints ====
@app.get("/health")
def health():
    return {"status": "ok", "coins_loaded": len(STATE.get("coin_data", {})),
            "model_loaded": "model" in STATE}


@app.get("/strategy")
def strategy():
    """Metadata & parameter strategi V5 (untuk dokumentasi Rust)."""
    return {
        "strategy": "V5",
        "feature_cols": v5.FEATURE_COLS,
        "bottoming_rsi": v5.BOTTOMING_RSI,
        "bottoming_fgi": v5.BOTTOMING_FGI,
        "ml_threshold": v5.ML_THRESHOLD,
        "forward_horizon_days": v5.FORWARD_HORIZON,
        "stop_loss": v5.STOP_LOSS,
        "take_profit": v5.TAKE_PROFIT,
        "correlation_max": v5.CORRELATION_MAX,
        "meta": STATE.get("meta", {}),
    }


@app.get("/coins")
def coins():
    """Daftar coin + korelasi ke BTC + status tradeable.

    'symbol' memakai format Tokocrypto/Binance (BTCUSDT). Kirim balik
    simbol ini apa adanya ke endpoint /score atau /scan.
    """
    corr = STATE["corr"]
    tradeable = set(STATE["tradeable"])
    return {
        "symbol_format": "BTCUSDT (Tokocrypto/Binance, tanpa pemisah)",
        "coins": [
            {"symbol": s, "correlation_to_btc": round(float(v), 3),
             "tradeable": s in tradeable}
            for s, v in corr.items()
        ],
        "tradeable_count": len(tradeable),
        "total": len(corr),
    }


def _score_one(symbol: str, date: pd.Timestamp) -> v5.Signal:
    symbol = normalize_symbol(symbol)
    feats = STATE["feats"].get(symbol)
    if feats is None:
        raise HTTPException(404, f"Symbol {symbol} tidak ditemukan. "
                            f"Tersedia: {list(STATE['feats'].keys())}")
    if date not in feats.index:
        raise HTTPException(404, f"Tanggal {date.date()} tidak ada untuk {symbol}")
    row = feats.loc[date]
    close = float(STATE["coin_dfs"][symbol].loc[date, "close"])
    return v5.evaluate_signal(row, symbol, str(date.date()), close,
                              STATE["model"], STATE["scaler"])


@app.post("/score")
def score(req: ScoreRequest):
    """Skor satu coin pada satu tanggal -> verdict BUY/SKIP + alasan.

    Simbol menerima format Tokocrypto/Binance (BTCUSDT) dan varian
    (BTC_USDT, btc-usdt) -- otomatis dinormalisasi.
    """
    date = pd.Timestamp(req.date)
    sig = _score_one(req.symbol, date)
    return {
        "symbol": sig.symbol, "date": sig.date, "verdict": sig.verdict,
        "ml_confidence": None if pd.isna(sig.ml_confidence) else round(sig.ml_confidence, 3),
        "reason": sig.reason, "rsi": None if pd.isna(sig.rsi) else round(sig.rsi, 1),
        "fng": None if pd.isna(sig.fng) else round(sig.fng, 0), "close": sig.close,
    }


@app.post("/scan")
def scan(req: ScanRequest):
    """Scan semua coin tradeable pada satu tanggal -> daftar sinyal BUY."""
    symbols = STATE["tradeable"] if req.only_tradeable else list(STATE["coin_data"].keys())

    # Tentukan tanggal
    if req.date:
        date = pd.Timestamp(req.date)
    else:
        date = max(STATE["feats"][s].index.max() for s in symbols)

    signals = []
    for s in symbols:
        feats = STATE["feats"][s]
        if date not in feats.index:
            continue
        row = feats.loc[date]
        close = float(STATE["coin_dfs"][s].loc[date, "close"])
        sig = v5.evaluate_signal(row, s, str(date.date()), close,
                                 STATE["model"], STATE["scaler"])
        signals.append({
            "symbol": sig.symbol, "verdict": sig.verdict,
            "ml_confidence": None if pd.isna(sig.ml_confidence) else round(sig.ml_confidence, 3),
            "reason": sig.reason, "rsi": None if pd.isna(sig.rsi) else round(sig.rsi, 1),
            "close": sig.close,
        })

    buys = [s for s in signals if s["verdict"] == "BUY"]
    buys.sort(key=lambda x: x["ml_confidence"] or 0, reverse=True)
    return {"date": str(date.date()), "buy_signals": buys,
            "total_scanned": len(signals), "buy_count": len(buys)}


@app.post("/backtest")
def backtest(req: BacktestRequest):
    """Jalankan backtest V5 pada rentang tanggal -> statistik & daftar trade."""
    symbols = STATE["tradeable"] if req.only_tradeable else list(STATE["coin_data"].keys())
    start, end = pd.Timestamp(req.start), pd.Timestamp(req.end)

    trades = []
    for s in symbols:
        feats = STATE["feats"][s]
        labeled = add_forward_return_target(feats, STATE["coin_dfs"][s]["close"],
                                            horizon=v5.FORWARD_HORIZON)
        period = labeled[(labeled.index >= start) & (labeled.index <= end)
                         & labeled["forward_return"].notna()]
        for date, row in period.iterrows():
            sig = v5.evaluate_signal(row, s, str(date.date()),
                                     float(STATE["coin_dfs"][s].loc[date, "close"]),
                                     STATE["model"], STATE["scaler"])
            if sig.verdict != "BUY":
                continue
            fwd = float(row["forward_return"])
            realized = max(v5.STOP_LOSS, min(v5.TAKE_PROFIT, fwd))
            trades.append({"symbol": s, "date": str(date.date()),
                           "ml_confidence": round(sig.ml_confidence, 3),
                           "forward_return": round(fwd, 4),
                           "realized_return": round(realized, 4),
                           "win": realized > 0})

    trades.sort(key=lambda x: x["date"])

    # Simulasi modal
    cap = req.initial_capital
    for t in trades:
        pnl = cap * req.position_fraction * t["realized_return"]
        cap += pnl
        t["pnl"] = round(pnl, 2)
        t["capital"] = round(cap, 2)

    wins = sum(1 for t in trades if t["win"])
    return {
        "period": f"{req.start} to {req.end}",
        "n_trades": len(trades),
        "win_rate": round(wins / len(trades), 3) if trades else None,
        "initial_capital": req.initial_capital,
        "final_capital": round(cap, 2),
        "return_pct": round((cap - req.initial_capital) / req.initial_capital, 4),
        "trades": trades,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
