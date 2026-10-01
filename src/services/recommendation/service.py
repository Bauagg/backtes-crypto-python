"""Rekomendasi coin: kembalikan N coin teratas (default 10) + detail semua indikator.

Kandidat = simbol aktif di flex_params dengan description Large/Mid (kategori market cap),
yang korelasinya ke BTC < 0.7 dan bukan stablecoin.

Urutan ranking:
  1. BUY   -- lolos SEMUA gate V5 (bottoming + reversal + regime + ML >= 0.55),
              diurutkan ml_confidence tertinggi. Dilengkapi stop-loss & take-profit.
  2. WATCH -- belum lolos semua gate. Diurutkan dari yang paling dekat ke sinyal:
              jumlah gate yang sudah lolos (berurutan), lalu RSI terendah (paling oversold).

Model & data pasar disimpan di memori. Data pasar otomatis dimuat ulang dari DB
kalau umurnya melewati MARKET_CACHE_TTL (DB terus di-update backend Rust).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import pandas as pd

from src.config.logger import get_logger
from src.config.settings import settings
from src.services.recommendation import repository
from src.strategy import v5
from src.strategy.indicators.fear_greed import FNG_EXTREME_FEAR
from src.strategy.indicators.rsi import RSI_OVERSOLD
from src.utils.api_response import clean_number as _num
from src.utils.app_error import NotFoundError

logger = get_logger(__name__)

BTC_SYMBOL = "BTCUSDT"

# Kategori market cap (flex_params.description) yang boleh direkomendasikan.
ALLOWED_CATEGORIES = ("Large", "Mid")

# Median ATR% 30 hari di bawah ini = harga hampir tidak bergerak (stablecoin).
# Data DB: TUSD 0.04%, USDC 0.07%, AEUR 0.98% -- coin asli paling tenang (TRX) 1.56%.
MIN_VOLATILITY = 0.012
VOLATILITY_LOOKBACK = 30

CONFIRM_LABELS = {
    "confirm_higher_close": "close hari ini > close kemarin",
    "confirm_break_high": "close menembus high kemarin",
    "confirm_rsi_rising": "RSI naik dari kemarin",
    "confirm_bullish_div": "bullish divergence (harga lower low, RSI higher low)",
    "confirm_not_falling": "tidak lower low 2 hari beruntun",
}


# ==== Model V5 di memori (dimuat sekali saat startup) ====
_model = None


def load_model():
    global _model
    _model = repository.find_model()
    return _model


def is_model_loaded() -> bool:
    return _model is not None


# ==== Data pasar di memori: candle + FNG dari DB, plus fitur V5 yang sudah dihitung ====
@dataclass
class MarketSnapshot:
    coin_dfs: dict[str, pd.DataFrame]   # OHLCV per coin
    feats: dict[str, pd.DataFrame]      # fitur + gate V5 per coin
    corr: pd.Series                     # korelasi return harian ke BTC
    tradeable: list[str]                # coin dgn korelasi < CORRELATION_MAX
    categories: dict[str, str]          # {symbol: Large/Mid} dari flex_params
    loaded_at: float


_snapshot: MarketSnapshot | None = None
_lock = threading.Lock()


def load_snapshot() -> MarketSnapshot:
    """Baca DB, hitung fitur semua coin, simpan sebagai snapshot aktif."""
    global _snapshot
    coin_dfs = repository.find_all_candles("1d")
    if BTC_SYMBOL not in coin_dfs:
        raise RuntimeError(f"{BTC_SYMBOL} tidak ada di market_candles -- dibutuhkan untuk relative strength.")
    fng = repository.find_fear_greed_index()
    btc_close = coin_dfs[BTC_SYMBOL]["close"]

    coin_data = {s: {"close": d["close"], "high": d["high"], "low": d["low"], "volume": d["volume"]}
                 for s, d in coin_dfs.items()}
    feats = {s: v5.build_features(d["close"], d["high"], d["low"], d["volume"], btc_close, fng)
             for s, d in coin_data.items()}
    corr = v5.correlation_to_btc(coin_data, btc_close)
    tradeable = corr[corr < v5.CORRELATION_MAX].index.tolist()
    categories = repository.find_symbol_categories(ALLOWED_CATEGORIES)

    _snapshot = MarketSnapshot(coin_dfs, feats, corr, tradeable, categories, time.time())
    logger.info("Data pasar dimuat dari DB: %d coin, %d tradeable, %d Large/Mid",
                len(coin_dfs), len(tradeable), len(categories))
    return _snapshot


def get_snapshot() -> MarketSnapshot:
    """Snapshot aktif; dimuat ulang dulu kalau belum ada atau sudah kedaluwarsa."""
    with _lock:
        if _snapshot is None or time.time() - _snapshot.loaded_at > settings.market_cache_ttl:
            return load_snapshot()
        return _snapshot


def peek_snapshot() -> MarketSnapshot | None:
    """Snapshot aktif tanpa memicu reload (untuk health check)."""
    return _snapshot


# ==== Ranking rekomendasi ====


def _is_stablecoin(feat: pd.DataFrame, date: pd.Timestamp) -> bool:
    recent = feat.loc[:date, "atr_pct"].iloc[-VOLATILITY_LOOKBACK:]
    return pd.isna(recent.median()) or recent.median() < MIN_VOLATILITY


def _gates(row: pd.Series, sig: v5.Signal) -> dict:
    return {
        "bottoming": bool(row.get("bottoming", False)),                 # RSI<=30 & FGI<=25
        "reversal_confirmed": bool(row.get("reversal_confirmed", False)),
        "regime_ok": bool(row.get("regime_ok", False)),
        "ml_passed": sig.verdict == "BUY",                              # ML >= 0.55
    }


def _stage(gates: dict) -> int:
    """Jumlah gate yang lolos BERURUTAN (0-4). Makin tinggi = makin dekat ke BUY."""
    stage = 0
    for passed in gates.values():
        if not passed:
            break
        stage += 1
    return stage


def _default_date(feats: dict[str, pd.DataFrame]) -> pd.Timestamp:
    """Tanggal terakhir yang dimiliki MAYORITAS coin (update tiap coin di DB bisa tidak serentak)."""
    return pd.Series([f.index.max() for f in feats.values()]).mode().max()


def _explain(row: pd.Series, sig: v5.Signal, corr: float | None) -> list[str]:
    """Alasan per indikator dalam bahasa manusia, urut sesuai gate strategi V5."""
    rsi, fng = sig.rsi, sig.fng
    out = []

    # 1. Bottoming
    if pd.notna(rsi) and pd.notna(fng):
        rsi_ok, fng_ok = rsi <= RSI_OVERSOLD, fng <= FNG_EXTREME_FEAR
        out.append(
            f"[Bottoming {'LOLOS' if rsi_ok and fng_ok else 'GAGAL'}] "
            f"RSI {rsi:.1f} ({'oversold' if rsi_ok else 'belum oversold'}, batas <= {RSI_OVERSOLD}); "
            f"Fear & Greed {fng:.0f} ({'pasar panik' if fng_ok else 'pasar belum panik'}, batas <= {FNG_EXTREME_FEAR})"
        )

    # 2. Konfirmasi reversal
    met = [label for col, label in CONFIRM_LABELS.items() if bool(row.get(col, False))]
    out.append(
        f"[Reversal {'LOLOS' if row.get('reversal_confirmed') else 'GAGAL'}] "
        f"{len(met)}/5 tanda pembalikan (butuh >= 2 + bottoming)"
        + (f": {', '.join(met)}" if met else "")
    )

    # 3. Regime pasar
    if row.get("crashing"):
        regime = "harga turun > 15% dalam 5 hari (crash)"
    elif not row.get("price_stable"):
        regime = "harga masih turun 2 hari beruntun (belum stabil)"
    else:
        regime = "tidak crash dan harga mulai stabil"
    out.append(f"[Regime {'LOLOS' if row.get('regime_ok') else 'GAGAL'}] {regime}")

    # 4. ML
    if pd.notna(sig.ml_confidence):
        out.append(
            f"[ML {'LOLOS' if sig.ml_confidence >= v5.ML_THRESHOLD else 'GAGAL'}] "
            f"peluang naik 5 hari {sig.ml_confidence:.1%} (batas >= {v5.ML_THRESHOLD:.0%})"
        )
    else:
        out.append("[ML -] tidak dihitung karena gate sebelumnya belum lolos")

    # Konteks (tidak menentukan BUY, tapi dipakai model / untuk dibaca user)
    trend, diff = row.get("trend_state"), row.get("ma_diff_pct")
    if trend and pd.notna(diff):
        out.append(f"[Tren] MA20 vs MA50 {diff:+.1%} -> {trend}"
                   + ("; harga di bawah MA200" if row.get("below_ma200") else "; harga di atas MA200"))
    vr = row.get("volume_ratio")
    if pd.notna(vr):
        out.append(f"[Volume] {vr:.2f}x rata-rata 20 hari"
                   + (" (melonjak)" if vr >= 1.2 else " (sepi)" if vr <= 0.8 else " (normal)"))
    rs = row.get("relative_strength")
    if pd.notna(rs):
        out.append(f"[Relative strength] {rs:+.1%} vs BTC dalam 7 hari "
                   f"({'lebih kuat' if rs > 0 else 'lebih lemah'} dari BTC)")
    if corr is not None and pd.notna(corr):
        out.append(f"[Korelasi BTC] {corr:.2f} (batas < {v5.CORRELATION_MAX})")
    atr = row.get("atr_pct")
    if pd.notna(atr):
        out.append(f"[Volatilitas] ATR 14 hari {atr:.1%} per hari")
    return out


def _detail(rank: int, symbol: str, category: str, row: pd.Series, sig: v5.Signal,
            gates: dict, corr: float | None) -> dict:
    """Satu item rekomendasi: keputusan + SEMUA indikator + alasannya."""
    is_buy = sig.verdict == "BUY"
    return {
        # ---- Keputusan ----
        "rank": rank,
        "symbol": symbol,
        "market_cap_category": category,              # Large / Mid (flex_params.description)
        "status": "BUY" if is_buy else "WATCH",
        "reason": sig.reason,                         # alasan singkat (gate pertama yang gagal)
        "explanations": _explain(row, sig, corr),     # alasan lengkap per indikator
        "close": _num(sig.close, 6),
        "ml_confidence": _num(sig.ml_confidence, 3),  # 0-1 (None kalau tak dihitung)
        "gates": gates,

        # ---- Moving Average (tren) ----
        "ma": {
            "ma_fast": _num(row.get("ma_fast"), 6),          # MA20
            "ma_slow": _num(row.get("ma_slow"), 6),          # MA50
            "ma_diff_pct": _num(row.get("ma_diff_pct"), 4),  # (fast-slow)/slow
            "trend_state": _num(row.get("trend_state")),     # BULLISH/BEARISH/NEUTRAL
            "below_ma200": _num(row.get("below_ma200")),     # harga < MA200?
        },

        # ---- Momentum & sentimen ----
        "momentum": {
            "rsi": _num(row.get("rsi"), 2),                  # RSI(7)
            "fng_value": _num(row.get("fng_value"), 0),      # Fear & Greed 0-100
            "price_change_pct": _num(row.get("price_change_pct"), 4),
        },

        # ---- Volume ----
        "volume": {
            "volume_avg": _num(row.get("volume_avg"), 2),    # rata2 20 hari
            "volume_ratio": _num(row.get("volume_ratio"), 3), # vol / rata2
        },

        # ---- Kekuatan relatif vs BTC ----
        "relative_strength": _num(row.get("relative_strength"), 4),
        "correlation_to_btc": _num(corr, 3),

        # ---- Deteksi reversal (bottoming) ----
        "reversal": {
            "bottoming": _num(row.get("bottoming")),
            "reversal_confirmed": _num(row.get("reversal_confirmed")),
            "confirm_count": _num(row.get("confirm_count")),
            "confirm_higher_close": _num(row.get("confirm_higher_close")),
            "confirm_break_high": _num(row.get("confirm_break_high")),
            "confirm_rsi_rising": _num(row.get("confirm_rsi_rising")),
            "confirm_bullish_div": _num(row.get("confirm_bullish_div")),
            "confirm_not_falling": _num(row.get("confirm_not_falling")),
        },

        # ---- Filter rezim pasar ----
        "regime": {
            "regime_ok": _num(row.get("regime_ok")),
            "crashing": _num(row.get("crashing")),            # turun >15%/5hari
            "price_stable": _num(row.get("price_stable")),    # tidak lower-low beruntun
        },

        # ---- Rencana exit (hanya terisi kalau status == "BUY") ----
        "exit_plan": {
            "method": "atr_based",
            "atr_pct": _num(row.get("atr_pct"), 6),
            "atr_sl_multiplier": v5.ATR_SL_MULTIPLIER,
            "atr_tp_multiplier": v5.ATR_TP_MULTIPLIER,
            "stop_loss_price": _num(sig.stop_loss_price, 6),
            "take_profit_price": _num(sig.take_profit_price, 6),
            "horizon_days": v5.FORWARD_HORIZON,
        } if is_buy else None,
    }


def get_recommendations(limit: int, date_str: str | None) -> dict:
    snapshot = get_snapshot()
    model, scaler = _model if _model is not None else load_model()
    symbols = [s for s in snapshot.tradeable if s in snapshot.categories]
    feats = {s: snapshot.feats[s] for s in symbols}
    if not feats:
        raise NotFoundError("Tidak ada simbol Large/Mid aktif yang punya candle di market_candles")
    date = pd.Timestamp(date_str) if date_str else _default_date(feats)

    candidates = []
    for symbol, feat in feats.items():
        if date not in feat.index or _is_stablecoin(feat, date):
            continue
        row = feat.loc[date]
        close = float(snapshot.coin_dfs[symbol].loc[date, "close"])
        sig = v5.evaluate_signal(row, symbol, str(date.date()), close, model, scaler)
        gates = _gates(row, sig)
        candidates.append((symbol, row, sig, gates, _stage(gates)))

    if not candidates:
        raise NotFoundError(f"Tidak ada data coin untuk tanggal {date.date()}")

    # BUY dulu (stage 4), lalu makin banyak gate lolos, ML confidence, lalu paling oversold.
    candidates.sort(key=lambda c: (
        -c[4],
        -(c[2].ml_confidence if pd.notna(c[2].ml_confidence) else 0),
        c[2].rsi if pd.notna(c[2].rsi) else float("inf"),
    ))

    recommendations = [
        _detail(rank, symbol, snapshot.categories[symbol], row, sig, gates, snapshot.corr.get(symbol))
        for rank, (symbol, row, sig, gates, _stage_) in enumerate(candidates[:limit], start=1)
    ]

    return {
        "date": str(date.date()),
        "fng_value": _num(candidates[0][1].get("fng_value"), 0),   # Fear & Greed pasar hari itu
        "buy_count": sum(1 for c in candidates if c[2].verdict == "BUY"),   # total, bisa > limit
        "total_candidates": len(candidates),
        "candidate_filter": {
            "market_cap_category": list(ALLOWED_CATEGORIES),
            "correlation_to_btc_max": v5.CORRELATION_MAX,
            "exclude_stablecoin": True,
        },
        "recommendations": recommendations,
    }
