"""Mesin backtest portofolio multi-coin dengan rebalance terjadwal (notebook 15+).

Beda dengan single_position.run(): di sini banyak coin dipegang bersamaan dengan porsi target.
"""

import numpy as np
import pandas as pd

COST = 0.0015   # fee 0.1% + slippage 0.05% per sisi


def inverse_vol_weights(panel, syms, lookback=60, caps=None):
    """Porsi berbasis kebalikan volatilitas (coin liar -> porsi kecil), total 1 per hari.

    caps: {simbol: porsi maksimum} (mis. {"DOGEUSDT": 0.10}); kelebihan dibagi ke coin lain.
    Coin tanpa data (belum listing) -> porsi 0.
    """
    vol = panel.close[syms].pct_change().rolling(lookback, min_periods=lookback).std()
    raw = (1 / vol).replace([np.inf, -np.inf], np.nan)
    w = raw.div(raw.sum(axis=1), axis=0).fillna(0.0)
    return apply_caps(w, caps)


def equal_weights(panel, syms, caps=None):
    avail = panel.close[syms].notna() & panel.close[syms].pct_change().rolling(60, min_periods=60).std().notna()
    w = avail.astype(float).div(avail.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return apply_caps(w, caps)


def apply_caps(w, caps):
    if not caps:
        return w
    w = w.copy()
    for _ in range(5):   # iterasi: potong yang melebihi batas, bagi sisanya ke yang tidak dibatasi
        excess = pd.Series(0.0, index=w.index)
        for s, cap in caps.items():
            if s in w:
                over = (w[s] - cap).clip(lower=0)
                excess += over
                w[s] -= over
        free = [c for c in w.columns if c not in caps]
        tot = w[free].sum(axis=1).replace(0, np.nan)
        w[free] = w[free].add(w[free].div(tot, axis=0).fillna(0).mul(excess, axis=0))
    return w


def rebalance_days(dates, freq):
    """Hari rebalance: 'D' tiap hari, 'W' tiap Senin, 'M' tanggal 1 (atau hari pertama tersedia)."""
    s = pd.Series(False, index=dates)
    if freq == "D":
        s[:] = True
    elif freq == "W":
        s[dates.dayofweek == 0] = True
    elif freq == "M":
        s[~dates.to_period("M").duplicated()] = True
    return s


def run_portfolio(panel, target_w, start, end, freq="M", cost=COST, capital_usd=None, min_order_usd=None):
    """Simulasi portofolio. target_w: DataFrame [tanggal x simbol] porsi target (jumlah <= 1, sisa = cash),
    diputuskan di close hari itu dan dieksekusi di OPEN hari berikutnya.

    Rebalance penuh ke target terjadi kalau: hari rebalance terjadwal, ATAU daftar coin yang dipegang
    berubah (ada coin masuk/keluar karena filter), ATAU filter pasar berubah (semua cash / masuk lagi).
    capital_usd + min_order_usd: meniru order minimum exchange -- transaksi per coin yang nilainya
    < min_order_usd dilewati (posisi coin itu tidak berubah); pembelian diperkecil kalau cash kurang.
    Return (equity Series, info dict: turnover, jumlah rebalance, kontribusi per coin).
    """
    dates = panel.dates[(panel.dates >= start) & (panel.dates <= end)]
    syms = list(target_w.columns)
    O = panel.open[syms].loc[dates].to_numpy()
    C = panel.close[syms].loc[dates].to_numpy()
    W = target_w.reindex(panel.dates).fillna(0).shift(1).fillna(0).loc[dates].to_numpy()   # berlaku di open hari t
    sched = rebalance_days(dates, freq).to_numpy()

    cash, units = 1.0, np.zeros(len(syms))
    last_px = np.where(np.isnan(C[0]), 0, C[0])
    eq, traded, n_reb = np.empty(len(dates)), 0.0, 0
    pnl = np.zeros(len(syms))
    prev_active = np.zeros(len(syms), bool)
    skipped = 0
    pnl_daily = np.zeros((len(dates), len(syms)))     # untung/rugi harian per coin (termasuk fee)
    values = np.zeros((len(dates), len(syms)))        # nilai posisi tiap coin di close
    cash_hist = np.zeros(len(dates))
    fills = []                                        # log transaksi: (tanggal, simbol, nilai +beli/-jual, harga, fee)
    if min_order_usd is not None and capital_usd is None:
        raise ValueError("min_order_usd butuh capital_usd (modal awal dalam USD)")
    for i in range(len(dates)):
        pnl_start = pnl.copy()
        px_open = np.where(np.isnan(O[i]), last_px, O[i])
        # PnL overnight (close kemarin -> open hari ini) per coin
        pnl += units * (px_open - last_px)
        active = W[i] > 1e-9
        trigger = sched[i] or (active != prev_active).any()
        if trigger:
            value = cash + (units * px_open).sum()
            want = np.where(px_open > 0, W[i] * value / np.where(px_open > 0, px_open, 1), 0.0)
            if min_order_usd is not None:
                # order < minimum exchange ditolak: coin itu tidak ditransaksikan (posisi lama tetap)
                delta_usd = np.abs(want - units) * px_open * capital_usd
                too_small = (delta_usd > 1e-9) & (delta_usd < min_order_usd)
                skipped += int(too_small.sum())
                want = np.where(too_small, units, want)
            trade = (want - units) * px_open
            if trade.sum() + (np.abs(trade) * cost).sum() > cash + 1e-12:
                # dana cash tidak cukup (karena penjualan kecil dilewati) -> perkecil pembelian secara proporsional
                buys = trade > 0
                room = cash + (-trade[~buys]).sum() * (1 - cost)
                scale = max(0.0, room / ((trade[buys] * (1 + cost)).sum() or 1))
                want = np.where(buys, units + (want - units) * min(1.0, scale), want)
                trade = (want - units) * px_open
            fee = np.abs(trade) * cost
            for j in np.nonzero(np.abs(trade) > 1e-12)[0]:
                fills.append((dates[i], syms[j], float(trade[j]), float(px_open[j]), float(fee[j])))
            cash -= trade.sum() + fee.sum()
            pnl -= fee
            traded += np.abs(trade).sum()
            units = want
            n_reb += 1
        prev_active = active
        px_close = np.where(np.isnan(C[i]), px_open, C[i])
        pnl += units * (px_close - px_open)
        last_px = px_close
        eq[i] = cash + (units * px_close).sum()
        pnl_daily[i] = pnl - pnl_start
        values[i] = units * px_close
        cash_hist[i] = cash
    out = pd.Series(eq, index=dates)
    out.attrs["exposure"] = float((W.sum(axis=1) > 1e-9).mean())
    info = dict(turnover=traded, n_rebalance=n_reb, pnl_per_coin=pd.Series(pnl, index=syms), order_dilewati=skipped,
                pnl_daily=pd.DataFrame(pnl_daily, index=dates, columns=syms),
                values=pd.DataFrame(values, index=dates, columns=syms),
                cash=pd.Series(cash_hist, index=dates),
                fills=pd.DataFrame(fills, columns=["date", "sym", "value", "price", "fee"]))
    return out, info
