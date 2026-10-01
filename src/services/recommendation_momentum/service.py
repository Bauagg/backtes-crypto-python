"""Rekomendasi coin harian berbasis momentum (riset notebooks/research_recomendatio_trading 01-06).

Daftar PANTAUAN untuk trader (bukan sinyal bot): bot menyaring universe Large/Mid jadi 5-10 coin,
trader menganalisis lagi sendiri. Urutan dihitung ulang tiap candle harian tutup, jadi bisa berubah
tiap hari (hari ini BTC no 1, besok ETH).

  Skor    : rata-rata rank-percentile RSI(14) + RSI(7) antar coin universe.
  Daftar  : peringkat 1-5 UTAMA, 6-10 PELENGKAP. BTC ikut diranking.
  Rencana : beli di open besok, pegang 14 hari, stop keras -25% (notebook 05).
  Pasar   : filter H8b (BTC > SMA100 ATAU rata-rata FGI 14 hari > 50); risk-off -> peringatan.

Riwayat (paper trading) dihitung ulang dari candle -- tidak ada yang ditulis ke DB.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.services.recommendation_momentum import repository
from src.strategy import allocation as al
from src.strategy import momentum as mo
from src.utils.api_response import clean_number as _num
from src.utils.app_error import NotFoundError, UnprocessableError

ALLOWED_CATEGORIES = ("Large", "Mid")
HISTORY_DAYS = 260          # SMA100 BTC + pemanasan RSI
STALE_DAYS = 2              # candle terakhir lebih tua dari ini -> peringatan data tertinggal
MIN_COVERAGE = 0.8          # tanggal sinyal = hari terakhir yang candle-nya lengkap >= 80% universe
RESEARCH_DATA_END = pd.Timestamp("2026-06-30")   # sinyal setelah ini = out-of-sample murni

# Notebook 06, universe live 21 coin + BTC ikut, periode uji 2024-01 -> 2026-06, hold 14 hari + stop -25%.
HISTORICAL_STATS = {
    "UTAMA_risk_on": dict(win_rate=0.453, avg_win=0.166, avg_loss=-0.113, expectancy=0.013, hit_stop=0.114, n=2855),
    "PELENGKAP_risk_on": dict(win_rate=0.456, avg_win=0.162, avg_loss=-0.116, expectancy=0.011, hit_stop=0.119, n=2855),
    "UTAMA_risk_off": dict(win_rate=0.418, avg_win=0.085, avg_loss=-0.106, expectancy=-0.026, hit_stop=0.096, n=1637),
}
RECENT_WARNING = ("Performa historis melemah: UTAMA risk-on 2025 rata-rata -0,23%/sinyal, "
                  "2026 (s/d Juni) -6,05% (notebook 06). Pakai sebagai daftar pantauan, bukan jaminan.")


@dataclass
class _Market:
    universe: list[str]
    symbols: dict[str, dict]        # {simbol: {id, category, image_url}} dari flex_params
    opens: pd.DataFrame
    lows: pd.DataFrame
    closes: pd.DataFrame
    score: pd.DataFrame
    rsi14: pd.DataFrame
    rsi7: pd.DataFrame
    filt: pd.DataFrame
    date: pd.Timestamp
    no_candles: list[str]           # aktif di flex_params tapi tidak ada candle sama sekali
    lagging: dict[str, str]         # {simbol: tanggal candle terakhir} yang tertinggal dari candle terbaru


def _today_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()


def _load(date_str: str | None, extra_days: int = 0) -> _Market:
    symbols = repository.find_symbols(ALLOWED_CATEGORIES)
    universe = sorted(s for s in symbols if s not in mo.EXCLUDED)
    if not universe:
        raise NotFoundError("Tidak ada simbol Large/Mid aktif di flex_params")

    requested = pd.Timestamp(date_str) if date_str else None
    anchor = requested if requested is not None else _today_utc()
    since = anchor - pd.Timedelta(days=HISTORY_DAYS + extra_days)
    candles = repository.find_daily_candles(sorted(set(universe) | {al.BTC}), since)
    if requested is not None and not any(requested in d.index for d in candles.values()):
        raise NotFoundError(f"Tidak ada candle untuk {requested.date()} di database")
    if al.BTC not in candles:
        raise NotFoundError("Candle BTCUSDT tidak ada di candle_ohlcv -- dibutuhkan untuk filter pasar")
    no_candles = [s for s in universe if s not in candles]
    universe = [s for s in universe if s in candles]

    days = pd.date_range(min(d.index.min() for d in candles.values()),
                         max(d.index.max() for d in candles.values()), freq="D")
    field = lambda f: pd.DataFrame({s: candles[s][f].reindex(days) for s in candles})
    opens, lows, closes = field("open"), field("low"), field("close")

    coverage = closes[universe].notna().mean(axis=1)
    usable = coverage[(coverage >= MIN_COVERAGE) & closes[al.BTC].notna()].index
    if usable.empty:
        raise NotFoundError("Tidak ada tanggal dengan candle cukup lengkap untuk universe rekomendasi")
    if requested is not None:
        if requested not in usable:
            raise NotFoundError(f"Candle untuk {requested.date()} tidak lengkap / tidak ada di database")
        date = requested
    else:
        date = usable.max()

    fgi = repository.find_fear_greed(since - pd.Timedelta(days=30))
    filt = al.market_filter(closes[al.BTC], fgi)
    if pd.isna(filt.at[date, "btc_sma100"]):
        raise UnprocessableError(f"Histori BTC kurang dari {al.MARKET_SMA} hari untuk SMA{al.MARKET_SMA}")
    score, rsi14, rsi7 = mo.momentum_score(closes[universe])
    latest = days.max()
    lagging = {s: str(candles[s].index.max().date()) for s in universe if candles[s].index.max() < latest}
    return _Market(universe, symbols, opens, lows, closes, score, rsi14, rsi7, filt, date, no_candles, lagging)


def _coin_id(m: _Market, symbol: str) -> str | None:
    """UUID baris flex_params coin ini -- penghubung ke data coin di backend Rust."""
    return m.symbols.get(symbol, {}).get("id")


def _image(m: _Market, symbol: str) -> str | None:
    """URL logo coin (flex_params.photo_url, disajikan backend Rust)."""
    return m.symbols.get(symbol, {}).get("image_url")


def _market_info(m: _Market, date: pd.Timestamp) -> dict:
    r = m.filt.loc[date]
    risk_on = bool(r["risk_on"])
    return {
        "status": "RISK_ON" if risk_on else "RISK_OFF",
        "btc_close": _num(r["btc_close"], 2),
        "btc_sma100": _num(r["btc_sma100"], 2),
        "btc_above_sma100": bool(r["trend_ok"]),
        "fear_greed": _num(r["fgi"], 0),
        "fear_greed_avg_14d": _num(r["fgi_14h"], 1),
        "explanation": (
            f"BTC {'di atas' if r['trend_ok'] else 'di bawah'} SMA100 dan rata-rata Fear & Greed 14 hari "
            f"{r['fgi_14h']:.0f} ({'>' if r['sentiment_ok'] else '<='} 50) -> "
            + ("pasar RISK-ON: sinyal momentum historis rata-rata positif."
               if risk_on else "pasar RISK-OFF: secara historis rata-rata sinyal RUGI.")
        ),
    }


def _pct_change(s: pd.Series, date: pd.Timestamp, days: int):
    prev = date - pd.Timedelta(days=days)
    if prev not in s.index or pd.isna(s[prev]) or s[prev] == 0 or pd.isna(s[date]):
        return None
    return float(s[date] / s[prev] - 1)


def _explain(rank: int, rsi14: float, rsi7: float, score: float, prev_rank: int | None, n: int) -> list[str]:
    group = mo.group_of(rank)
    out = [f"[Peringkat] #{rank} dari {n} coin ({group}) -- skor momentum {score:.2f} "
           f"(0 = terlemah, 1 = terkuat di antara {n} coin)"]
    out.append(f"[RSI 14 hari] {rsi14:.1f}" + (" -- sudah tinggi (>70), rawan koreksi" if rsi14 > 70 else ""))
    out.append(f"[RSI 7 hari] {rsi7:.1f}" + (" -- momentum jangka pendek kuat" if rsi7 > 60 else ""))
    if prev_rank is None:
        out.append("[Perubahan] BARU masuk 10 besar hari ini")
    elif prev_rank != rank:
        out.append(f"[Perubahan] {'naik' if prev_rank > rank else 'turun'} dari #{prev_rank} kemarin")
    else:
        out.append("[Perubahan] posisi sama dengan kemarin")
    return out


def get_recommendations(limit: int, date_str: str | None) -> dict:
    m = _load(date_str)
    date = m.date
    top = mo.rank_day(m.score.loc[date], limit)
    if len(top) < mo.TOP_MAIN:
        raise UnprocessableError(f"Hanya {len(top)} coin punya skor di {date.date()} (butuh minimal {mo.TOP_MAIN})")
    yesterday = date - pd.Timedelta(days=1)
    prev = mo.rank_day(m.score.loc[yesterday], mo.MAX_RECOMMENDATIONS) if yesterday in m.score.index else []
    prev_rank = {s: k for k, s in enumerate(prev, start=1)}
    n_scored = int(m.score.loc[date].notna().sum())
    risk_on = bool(m.filt.at[date, "risk_on"])
    entry_date = date + pd.Timedelta(days=1)

    items = []
    for rank, sym in enumerate(top, start=1):
        close = float(m.closes.at[date, sym])
        sc, r14, r7 = float(m.score.at[date, sym]), float(m.rsi14.at[date, sym]), float(m.rsi7.at[date, sym])
        pr = prev_rank.get(sym)
        group = mo.group_of(rank)
        items.append({
            "rank": rank,
            "id": _coin_id(m, sym),
            "symbol": sym,
            "group": group,
            "image_url": _image(m, sym),
            "market_cap_category": m.symbols.get(sym, {}).get("category"),
            "score": _num(sc, 3),
            "previous_rank": pr,                                   # None = baru masuk 10 besar
            "rank_change": (pr - rank) if pr is not None else None,  # + naik, - turun
            "close": _num(close, 8),
            "change_1d": _num(_pct_change(m.closes[sym], date, 1), 4),
            "change_7d": _num(_pct_change(m.closes[sym], date, 7), 4),
            "rsi14": _num(r14, 2),
            "rsi7": _num(r7, 2),
            "plan": {
                "entry": f"open {entry_date.date()} (07:00 WIB)",
                "hold_days": mo.HOLD_DAYS,
                "sell_on": f"close {(date + pd.Timedelta(days=mo.HOLD_DAYS)).date()}",
                "hard_stop_pct": -mo.HARD_STOP,
                "stop_loss_price_estimate": _num(close * (1 - mo.HARD_STOP), 8),  # dari close; hitung ulang dari harga beli
            },
            "historical_stats": HISTORICAL_STATS[f"{group}_risk_on" if risk_on else "UTAMA_risk_off"],
            "explanations": _explain(rank, r14, r7, sc, pr, n_scored),
        })

    warnings = [RECENT_WARNING]
    if not risk_on:
        warnings.insert(0, "PASAR RISK-OFF: historis rata-rata sinyal -2,59% (win rate 41,8%). "
                           "Daftar tetap ditampilkan untuk dipantau, pertimbangkan menunggu.")
    age = (_today_utc() - date).days
    if date_str is None and age > STALE_DAYS:
        warnings.insert(0, f"Data tertinggal: candle terakhir {date.date()} ({age} hari lalu) -- cek collector Rust.")
    if date_str is None and m.lagging:
        warnings.insert(0, "Candle coin ini tertinggal (collector Rust berhenti mengisi): "
                           + ", ".join(f"{s} s/d {d}" for s, d in m.lagging.items())
                           + " -- daftar memakai tanggal terakhir yang candle-nya lengkap.")
    if m.no_candles:
        warnings.append(f"Aktif di flex_params tapi belum ada candle sama sekali (tidak ikut diranking): "
                        f"{', '.join(m.no_candles)}")

    return {
        "date": str(date.date()),
        "next_update": "setiap candle harian tutup (07:00 WIB)",
        "market": _market_info(m, date),
        "warnings": warnings,
        "universe": {"categories": list(ALLOWED_CATEGORIES), "count": n_scored, "btc_included": True},
        "method": {
            "score": "rata-rata rank-percentile RSI(14) + RSI(7) antar coin universe",
            "groups": "peringkat 1-5 UTAMA, 6-10 PELENGKAP",
            "plan": f"beli open besok, pegang {mo.HOLD_DAYS} hari, stop keras -{mo.HARD_STOP:.0%}",
            "research": "notebooks/research_recomendatio_trading 01-06",
        },
        "dropped_from_top": [{"id": _coin_id(m, s), "symbol": s, "image_url": _image(m, s)}     # kemarin ada di top-`limit`, hari ini tidak
                             for s in prev[:limit] if s not in top],
        "recommendations": items,
    }


def _summary(trades: list[dict]) -> dict:
    done = [t for t in trades if t["status"] in ("SELESAI", "STOP_KERAS")]
    if not done:
        return {"finished": 0, "running": len(trades), "win_rate": None, "expectancy": None, "hit_stop": None}
    rets = np.array([t["return"] for t in done])
    return {"finished": len(done), "running": len(trades) - len(done),
            "win_rate": _num((rets > 0).mean(), 3), "expectancy": _num(rets.mean(), 4),
            "hit_stop": _num(np.mean([t["status"] == "STOP_KERAS" for t in done]), 3)}


def get_history(days: int, date_str: str | None) -> dict:
    """Paper trading: rekomendasi `days` hari terakhir + hasilnya (dihitung ulang dari candle)."""
    m = _load(date_str, extra_days=days)
    end = m.date
    idx = m.closes.index
    pos = {d: k for k, d in enumerate(idx)}
    arrays = {s: (m.opens[s].to_numpy(float), m.lows[s].to_numpy(float), m.closes[s].to_numpy(float))
              for s in m.universe}
    closes_end = m.closes.loc[:end]
    n_end = len(closes_end)

    out_days, trades_all = [], []
    for d in pd.date_range(end - pd.Timedelta(days=days - 1), end, freq="D"):
        if d not in pos or m.score.loc[d].notna().sum() < mo.TOP_MAIN:
            continue
        i = pos[d]
        risk_on = bool(m.filt.at[d, "risk_on"])
        recs = []
        for rank, sym in enumerate(mo.rank_day(m.score.loc[d]), start=1):
            o, lo, c = (a[:n_end] for a in arrays[sym])        # tidak melihat data setelah `end`
            t = mo.simulate_trade(o, lo, c, i)
            rec = {"rank": rank, "id": _coin_id(m, sym), "symbol": sym, "image_url": _image(m, sym),
                   "group": mo.group_of(rank)}
            if t is None:
                rec.update(status="MENUNGGU_ENTRY")
            else:
                rec.update(status=t["status"], entry_price=_num(t["entry"], 8),
                           exit_or_last_price=_num(t["exit_price"], 8),
                           exit_or_last_date=str(idx[t["exit_idx"]].date()), **{"return": _num(t["ret"], 4)})
                trades_all.append(dict(rec, risk_on=risk_on))
            recs.append(rec)
        out_days.append({"date": str(d.date()), "market": "RISK_ON" if risk_on else "RISK_OFF",
                         "out_of_sample": bool(d > RESEARCH_DATA_END), "recommendations": recs})

    pick = lambda g, on: [t for t in trades_all if t["group"] == g and t["risk_on"] == on]
    return {
        "until": str(end.date()),
        "days": days,
        "rule": f"beli open hari berikutnya, jual close hari ke-{mo.HOLD_DAYS}, stop keras -{mo.HARD_STOP:.0%}, "
                f"biaya {mo.COST_PER_SIDE:.2%}/sisi",
        "note": "Dihitung ulang dari candle harian (tidak disimpan ke DB). Sinyal setelah "
                f"{RESEARCH_DATA_END.date()} belum pernah dilihat riset = paper trading jujur.",
        "summary": {
            "UTAMA_risk_on": _summary(pick("UTAMA", True)),
            "PELENGKAP_risk_on": _summary(pick("PELENGKAP", True)),
            "UTAMA_risk_off": _summary(pick("UTAMA", False)),
            "PELENGKAP_risk_off": _summary(pick("PELENGKAP", False)),
        },
        "historical_stats": HISTORICAL_STATS,
        "history": out_days[::-1],      # terbaru di atas
    }
