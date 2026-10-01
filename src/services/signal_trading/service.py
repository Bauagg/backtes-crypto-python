"""Sinyal entry harian untuk bot trading (dieksekusi backend Rust).

Pemilihan strategi berdasarkan modal:
  modal <  Rp1.500.000 -> BTC-60 (notebook 17): BTC saja, 60% modal, filter pasar H8b.
  modal >= Rp1.500.000 -> V2-60  (notebook 20): 8 coin porsi inverse-volatilitas (DOGE maks 10%),
                                    60% modal, filter pasar H8b.
Aturan eksekusi sama dengan backtest: keputusan dari candle close hari D, eksekusi di open hari D+1;
rebalance kalau D+1 tanggal 1, filter pasar berubah, atau coin yang dipegang tidak sesuai target;
order < 5 USDT dilewati; kill switch kalau modal <= 70% modal awal.
"""

from __future__ import annotations

import pandas as pd

from src.config.settings import settings
from src.services.signal_trading import repository
from src.services.signal_trading.schemas import SignalRequest
from src.strategy import allocation as al
from src.utils.api_response import clean_number as _num
from src.utils.app_error import NotFoundError, UnprocessableError

V2_MIN_CAPITAL_IDR = 1_500_000
HISTORY_DAYS = 260          # cukup untuk SMA100 + volatilitas 60 hari
FEE = 0.001                 # fee taker spot, untuk memastikan dana beli cukup
STALE_DAYS = 2              # candle lebih tua dari ini -> peringatan data tertinggal


def _pick_strategy(modal: float) -> tuple[str, list[str], str]:
    if modal >= V2_MIN_CAPITAL_IDR:
        return "V2-60", al.V2_COINS, f"modal Rp{modal:,.0f} >= Rp{V2_MIN_CAPITAL_IDR:,.0f}"
    return "BTC-60", [al.BTC], f"modal Rp{modal:,.0f} < Rp{V2_MIN_CAPITAL_IDR:,.0f}"


def _today_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()


def _row(df: pd.DataFrame, date: pd.Timestamp) -> dict:
    """Satu baris DataFrame sebagai dict nilai Python biasa (tipe jelas, tanpa Series/DataFrame)."""
    return {str(k): v for k, v in df.loc[date].items()}


def _load(coins: list[str], date: pd.Timestamp | None):
    anchor = date if date is not None else _today_utc()
    since = anchor - pd.Timedelta(days=HISTORY_DAYS)
    candles = repository.find_daily_candles(sorted(set(coins) | {al.BTC}), since)
    if al.BTC not in candles:
        raise NotFoundError("Candle BTCUSDT tidak ada di market_candles -- dibutuhkan untuk filter pasar")
    missing = [s for s in coins if s not in candles]
    closes = pd.DataFrame({s: d["close"] for s, d in candles.items()}).sort_index()
    fgi = repository.find_fear_greed(since - pd.Timedelta(days=30))
    return closes, fgi, missing


def _signal_date(closes: pd.DataFrame, coins: list[str], requested: str | None) -> pd.Timestamp:
    usable = closes[[c for c in coins if c in closes]].dropna(how="any")
    if usable.empty:
        raise NotFoundError("Tidak ada tanggal dengan candle lengkap untuk semua coin strategi")
    if requested:
        d = pd.Timestamp(requested)
        if d not in usable.index:
            raise NotFoundError(f"Candle lengkap untuk {d.date()} tidak ada di database")
        return d
    return usable.index.max()


def get_signal(req: SignalRequest) -> dict:
    kurs = req.kurs_usdt_idr or settings.usdt_idr_rate
    strategy, coins, strategy_reason = _pick_strategy(req.modal)
    closes, fgi, missing = _load(coins, pd.Timestamp(req.tanggal) if req.tanggal else None)
    if missing:
        raise NotFoundError(f"Candle tidak ada di database untuk: {missing}")
    date = _signal_date(closes, coins, req.tanggal)
    closes = closes.loc[:date]
    if len(closes[al.BTC].dropna()) < al.MARKET_SMA + 1:
        raise UnprocessableError(f"Histori BTC kurang dari {al.MARKET_SMA + 1} hari untuk SMA{al.MARKET_SMA}")

    # ---- filter pasar H8b ----
    mf = al.market_filter(closes[al.BTC], fgi)
    today, yesterday = _row(mf, date), _row(mf, mf.index[-2])
    risk_on = bool(today["risk_on"])
    filter_changed = bool(today["risk_on"] != yesterday["risk_on"])
    exec_date = date + pd.Timedelta(days=1)
    rebalance_day = exec_date.day == 1

    # ---- kill switch ----
    kill = bool(req.modal_awal and req.modal <= req.modal_awal * (1 - al.KILL_SWITCH_DRAWDOWN))

    # ---- porsi target (dari total modal) ----
    if strategy == "V2-60":
        base = _row(al.inverse_vol_weights(closes[coins], al.VOL_LOOKBACK, al.V2_CAPS), date)
    else:
        base = {al.BTC: 1.0}
    vol = _row(closes[list(base)].pct_change().rolling(al.VOL_LOOKBACK).std(), date)
    active = risk_on and not kill
    weights = {s: float(v) * al.INVESTED_PORTION * (1.0 if active else 0.0) for s, v in base.items()}
    last_close = _row(closes, date)
    prices = {s: float(last_close[s]) for s in weights}

    # ---- nilai akun dalam USDT ----
    held = {s.upper(): q for s, q in (req.posisi or {}).items() if q}
    held_prices = {}
    if held:
        extra = [s for s in held if s not in closes]
        extra_closes, _, _ = _load(extra, date) if extra else (pd.DataFrame(), None, None)
        for s in held:
            src = closes if s in closes else extra_closes
            hist = src[s].loc[:date].dropna() if s in src else pd.Series(dtype=float)
            if hist.empty:
                raise NotFoundError(f"Harga {s} tidak ada di database untuk menghitung nilai posisi")
            held_prices[s] = float(hist.to_numpy()[-1])
    positions_given = req.posisi is not None
    if positions_given:
        equity_usdt = (req.cash_usdt or 0.0) + sum(q * held_prices[s] for s, q in held.items())
    else:
        equity_usdt = req.modal / kurs

    targets = []
    for s in weights:
        tv = weights[s] * equity_usdt
        targets.append({
            "symbol": s,
            "porsi": _num(weights[s], 4),
            "nilai_usdt": _num(tv, 2),
            "nilai_idr": _num(tv * kurs, 0),
            "harga_terakhir": _num(prices[s], 8),
            "qty_target": _num(tv / prices[s], 8) if prices[s] else None,
            "volatilitas_harian_60h": _num(float(vol.get(s, float("nan"))), 4),
            "di_bawah_order_minimum": bool(0 < tv < al.MIN_ORDER_USDT),
        })
    usdt_target = equity_usdt - sum(t["nilai_usdt"] or 0 for t in targets)

    # ---- order (hanya kalau posisi dikirim) ----
    orders, skipped, need_rebalance, rebalance_reasons = [], [], False, []
    if rebalance_day:
        rebalance_reasons.append(f"jadwal rebalance bulanan ({exec_date.date()} tanggal 1)")
    if filter_changed:
        rebalance_reasons.append("filter pasar berubah " + ("hidup" if risk_on else "mati"))
    if kill:
        rebalance_reasons.append("kill switch aktif")
    if positions_given:
        current = {s: q * held_prices[s] for s, q in held.items()}
        universe = sorted(set(current) | set(weights))
        tgt = {s: weights.get(s, 0.0) * equity_usdt for s in universe}
        mismatch = [s for s in universe if (tgt[s] >= al.MIN_ORDER_USDT) != (current.get(s, 0.0) >= al.MIN_ORDER_USDT)]
        if mismatch:
            rebalance_reasons.append(f"posisi tidak sesuai target: {mismatch}")
        need_rebalance = bool(rebalance_reasons)
        if need_rebalance:
            sells, buys = [], []
            for s in universe:
                px = held_prices.get(s) or prices[s]
                delta = tgt[s] - current.get(s, 0.0)
                if abs(delta) < 1e-9:
                    continue
                if abs(delta) < al.MIN_ORDER_USDT:
                    skipped.append({"symbol": s, "selisih_usdt": _num(delta, 2), "alasan": "di bawah order minimum 5 USDT"})
                    continue
                o = {"symbol": s, "side": "SELL" if delta < 0 else "BUY", "nilai_usdt": abs(delta), "harga_acuan": px}
                (sells if delta < 0 else buys).append(o)
            cash_after = (req.cash_usdt or 0.0) + sum(o["nilai_usdt"] * (1 - FEE) for o in sells)
            need_cash = sum(o["nilai_usdt"] * (1 + FEE) for o in buys)
            scale = min(1.0, cash_after / need_cash) if need_cash > 0 else 1.0
            for o in buys:
                o["nilai_usdt"] *= scale
            for o in sells + buys:
                if o["side"] == "BUY" and o["nilai_usdt"] < al.MIN_ORDER_USDT:
                    skipped.append({"symbol": o["symbol"], "selisih_usdt": _num(o["nilai_usdt"], 2),
                                    "alasan": "dana USDT tidak cukup setelah dibagi"})
                    continue
                orders.append({
                    "urutan": len(orders) + 1,
                    "symbol": o["symbol"], "side": o["side"], "tipe": "MARKET",
                    "nilai_usdt": _num(o["nilai_usdt"], 2),
                    "qty_perkiraan": _num(o["nilai_usdt"] / o["harga_acuan"], 8),
                    "harga_acuan": _num(o["harga_acuan"], 8),
                    "jual_semua": bool(o["side"] == "SELL" and tgt.get(o["symbol"], 0.0) < al.MIN_ORDER_USDT),
                })

    # ---- peringatan ----
    notes = []
    now = _today_utc()
    lag = (now - date).days
    if not req.tanggal and lag > STALE_DAYS:
        notes.append(f"Candle terakhir {date.date()} sudah {lag} hari lalu -- cek collector candle backend Rust sebelum trading.")
    if kill:
        notes.append("Kill switch aktif: jual semua ke USDT dan hentikan bot untuk evaluasi manual.")
    if active and any(t["di_bawah_order_minimum"] for t in targets):
        small = [t["symbol"] for t in targets if t["di_bawah_order_minimum"]]
        notes.append(f"Porsi {small} di bawah 5 USDT -- tidak bisa dibeli dengan modal ini (tetap USDT).")
    if equity_usdt * al.INVESTED_PORTION < al.MIN_ORDER_USDT:
        notes.append("Modal terlalu kecil: 60% modal < 5 USDT, tidak ada order yang bisa dijalankan.")

    return {
        "tanggal_candle": str(date.date()),
        "eksekusi_pada": f"{exec_date.date()} saat open (00:00 UTC)",
        "strategi": strategy,
        "alasan_strategi": strategy_reason,
        "status": "STOP" if kill else ("RISK_ON" if risk_on else "RISK_OFF"),
        "filter_pasar": {
            "risk_on": risk_on,
            "berubah_dari_kemarin": filter_changed,
            "btc_close": _num(float(today["btc_close"]), 2),
            "btc_sma100": _num(float(today["btc_sma100"]), 2),
            "btc_di_atas_sma100": bool(today["trend_ok"]),
            "fgi_hari_ini": _num(float(today["fgi"]), 0),
            "fgi_rata2_14h": _num(float(today["fgi_14h"]), 1),
            "fgi_14h_di_atas_50": bool(today["sentiment_ok"]),
            "alasan": ("BTC di atas SMA100" if today["trend_ok"] else "BTC di bawah SMA100")
                      + " dan " + ("FGI 14 hari > 50" if today["sentiment_ok"] else "FGI 14 hari <= 50")
                      + (" -> risk-on" if risk_on else " -> risk-off (semua USDT)"),
        },
        "kill_switch": {
            "aktif": kill,
            "batas_idr": _num(req.modal_awal * (1 - al.KILL_SWITCH_DRAWDOWN), 0) if req.modal_awal else None,
        },
        "modal": {
            "modal_idr": _num(req.modal, 0), "kurs_usdt_idr": _num(kurs, 2),
            "nilai_akun_usdt": _num(equity_usdt, 2),
            "sumber": "posisi + cash_usdt" if positions_given else "modal / kurs",
        },
        "alokasi_target": targets,
        "usdt_target": _num(usdt_target, 2),
        "perlu_rebalance": need_rebalance if positions_given else bool(rebalance_reasons),
        "alasan_rebalance": rebalance_reasons,
        "order": orders if positions_given else None,
        "order_dilewati": skipped if positions_given else None,
        "catatan": notes,
    }
