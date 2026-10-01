"""Mesin backtest 1 posisi + strategi F2 (Tren + Momentum Rotasi).

Dipakai bersama oleh notebook riset (07 memuat salinan kode yang sama secara inline,
notebook 08+ mengimpor modul ini). Jangan ubah perilaku tanpa menjalankan ulang notebook terkait.
"""

import numpy as np
import pandas as pd

COST = 0.0015   # fee 0.1% + slippage 0.05% per sisi
BTC = "BTCUSDT"


class Panel:
    """Data semua coin sebagai tabel [tanggal x coin]."""

    def __init__(self, ohlc: dict, start, end):
        self.syms = sorted(ohlc)
        self.dates = pd.date_range(start, end, freq="D")
        g = lambda col: pd.DataFrame({s: ohlc[s][col] for s in self.syms}).reindex(self.dates)
        self.open, self.high, self.low, self.close = (g(c) for c in ["open", "high", "low", "close"])
        prev = self.close.shift(1)
        # True Range = max(high-low, |high-close kemarin|, |low-close kemarin|); dibungkus DataFrame
        # supaya tipe hasilnya jelas (np.maximum pada DataFrame mengembalikan DataFrame saat runtime).
        tr = pd.DataFrame(np.maximum(self.high - self.low, np.maximum((self.high - prev).abs(), (self.low - prev).abs())),
                          index=self.dates, columns=self.syms)
        self.atr = tr.rolling(14, min_periods=14).mean()
        self.atr_pct = self.atr / self.close

    def ma(self, n):
        return self.close.rolling(n, min_periods=n).mean()

    def ret(self, n):
        return self.close / self.close.shift(n) - 1

    def vol(self, n):
        return self.close.pct_change().rolling(n, min_periods=n).std()

    def rsi(self, n):
        d = self.close.diff()
        up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
        dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
        return 100 - 100 / (1 + up / dn)


def run(panel, target, start, end, stop_pct=None, trail_atr=None, size=None,
        circuit_dd=None, cooldown=30, cost=COST, circuit_next_open=False):
    """Simulasi 1 posisi. target: Series[tanggal] -> simbol (None = cash), dieksekusi di open besok.

    circuit_next_open: False (default, perilaku notebook 07) = circuit breaker jual di close hari
    pemicu. True = jual di open hari berikutnya (lebih realistis: kondisi baru diketahui saat close).
    """
    dates = panel.dates[(panel.dates >= start) & (panel.dates <= end)]
    col = {s: i for i, s in enumerate(panel.syms)}
    O, L, C = (x.loc[dates].to_numpy() for x in (panel.open, panel.low, panel.close))
    ATR = panel.atr.loc[dates].to_numpy()
    SZ = size.reindex(index=dates, columns=panel.syms).to_numpy() if size is not None else None
    tgt = target.reindex(dates).to_numpy(dtype=object)

    cash, units, sym, entry, stop, peak_close, entry_i = 1.0, 0.0, None, 0.0, -np.inf, 0.0, -1
    blocked, pending, peak_eq, pause_until = None, None, 1.0, -1
    trades, eq, inpos = [], np.empty(len(dates)), np.zeros(len(dates), bool)

    def sell(price, i, reason):
        nonlocal cash, units, sym
        cash += units * price * (1 - cost)
        trades.append((sym, dates[entry_i], dates[i], i - entry_i, entry, price, reason))
        old, units, sym = sym, 0.0, None
        return old

    for i in range(len(dates)):
        # 1. eksekusi order (keputusan close kemarin) di open hari ini
        if i > 0:
            want = pending if (pending != blocked and i > pause_until) else None
            if want != sym:
                if sym is not None:
                    px = O[i, col[sym]]
                    sell(px if not np.isnan(px) else C[i - 1, col[sym]], i, "SIGNAL")
                if want is not None and not np.isnan(O[i, col[want]]):
                    j = col[want]
                    frac = 1.0 if SZ is None or np.isnan(SZ[i - 1, j]) else float(np.clip(SZ[i - 1, j], 0, 1))
                    if frac > 0:
                        invest = cash * frac
                        entry, entry_i, sym = O[i, j], i, want
                        units, cash = invest * (1 - cost) / entry, cash - invest
                        peak_close = entry
                        stop = entry * (1 + stop_pct) if stop_pct is not None else -np.inf
                        if trail_atr is not None and not np.isnan(ATR[i - 1, j]):
                            stop = max(stop, entry - trail_atr * ATR[i - 1, j])
        # 2. stop intraday (gap di open -> keluar di open)
        if sym is not None:
            j = col[sym]
            o, lo, c = O[i, j], L[i, j], C[i, j]
            if not np.isnan(lo) and lo <= stop:
                blocked = sell(o if (i > entry_i and o <= stop) else stop, i, "STOP")
            elif not np.isnan(c):
                peak_close = max(peak_close, c)
                if trail_atr is not None and not np.isnan(ATR[i, j]):
                    stop = max(stop, peak_close - trail_atr * ATR[i, j])
        # 3. target dari close hari ini (dieksekusi besok)
        pending = tgt[i] if isinstance(tgt[i], str) else None
        if blocked is not None and pending != blocked:
            blocked = None
        # 4. mark-to-market + circuit breaker
        px = C[i, col[sym]] if sym is not None else 0.0
        eq[i] = cash + (units * (px if not np.isnan(px) else entry) * (1 - cost) if sym is not None else 0.0)
        if circuit_dd is not None and eq[i] <= peak_eq * (1 - circuit_dd):
            if circuit_next_open:
                # posisi dijual di open besok lewat langkah 1 (entry diblokir selama jeda)
                pause_until, peak_eq = i + cooldown, eq[i]
            else:
                if sym is not None and not np.isnan(px):
                    sell(px, i, "CIRCUIT")
                eq[i], pause_until, peak_eq = cash, i + cooldown, cash
        peak_eq = max(peak_eq, eq[i])
        inpos[i] = sym is not None

    if sym is not None:
        sell(C[-1, col[sym]], len(dates) - 1, "END")
        eq[-1] = cash
    tr = pd.DataFrame(trades, columns=["sym", "entry_date", "exit_date", "days", "entry", "exit", "reason"])
    if len(tr):
        tr["ret"] = tr["exit"] * (1 - cost) / (tr["entry"] / (1 - cost)) - 1
    out = pd.Series(eq, index=dates)
    out.attrs["exposure"] = inpos.mean()
    return tr, out


def metrics(tr, eq):
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    total = eq.iloc[-1] / eq.iloc[0] - 1
    dr = eq.pct_change().dropna()
    dd = (eq / eq.cummax() - 1).min()
    cagr = (1 + total) ** (1 / years) - 1 if total > -1 else -1
    return dict(total_return=total, cagr=cagr, max_dd=dd,
                sharpe=dr.mean() / dr.std() * np.sqrt(365) if dr.std() > 0 else np.nan,
                calmar=cagr / abs(dd) if dd < 0 else np.nan,
                n_trades=len(tr), win_rate=(tr["ret"] > 0).mean() if len(tr) else np.nan,
                exposure=eq.attrs.get("exposure", np.nan))


def pretty(df, pct=(), dec=()):
    out = df.copy()
    for c in pct:
        out[c] = out[c].map(lambda v: f"{v:+.1%}" if pd.notna(v) else "-")
    for c in dec:
        out[c] = out[c].map(lambda v: f"{v:.2f}" if pd.notna(v) else "-")
    return out



def f2_target(P, ma_n, L, R):
    """F2: saat BTC > MA(ma_n), pegang coin skor momentum risk-adjusted tertinggi (di atas MA sendiri).
    R = minimal hari sebelum boleh ganti coin (kecuali coin keluar dari tren / rezim BTC mati)."""
    bc = P.close[BTC]
    regime = (bc > bc.rolling(ma_n, min_periods=ma_n).mean()).to_numpy()
    own = P.close > P.ma(ma_n)
    score = (P.ret(L) / P.vol(L)).where(own & (P.ret(L) > 0))
    best = score.fillna(-np.inf).idxmax(axis=1).where(score.notna().any(axis=1)).to_numpy(dtype=object)
    valid, cols = own.to_numpy(), {s: i for i, s in enumerate(P.syms)}
    out, cur, age = [], None, 0
    for t in range(len(P.dates)):
        age += 1
        b = best[t] if isinstance(best[t], str) else None
        if not regime[t]:
            cur = None
        elif cur is None or not valid[t, cols[cur]] or age >= R:
            if b != cur:
                cur = b
            age = 0
        out.append(cur)
    return pd.Series(out, index=P.dates)



# ---------------------------------------------------------------------------
# Keluarga strategi lain (kode sama dengan screening notebook 07/08)
# ---------------------------------------------------------------------------

def ranked_target(P, ma_n, L, R, score):
    """Sama dengan f2_target, tapi skor pemilihan coin bisa diganti (momentum / acak)."""
    bc = P.close[BTC]
    regime = (bc > bc.rolling(ma_n, min_periods=ma_n).mean()).to_numpy()
    own = P.close > P.ma(ma_n)
    sc = score.where(own & (P.ret(L) > 0))
    best = sc.fillna(-np.inf).idxmax(axis=1).where(sc.notna().any(axis=1)).to_numpy(dtype=object)
    valid, cols = own.to_numpy(), {s: i for i, s in enumerate(P.syms)}
    out, cur, age = [], None, 0
    for t in range(len(P.dates)):
        age += 1
        b = best[t] if isinstance(best[t], str) else None
        if not regime[t]:
            cur = None
        elif cur is None or not valid[t, cols[cur]] or age >= R:
            if b != cur:
                cur = b
            age = 0
        out.append(cur)
    return pd.Series(out, index=P.dates)


def f1_target(P, n, kind="sma"):
    """F1: pegang BTC kalau close > MA(n), else cash."""
    bc = P.close[BTC]
    ma = bc.rolling(n, min_periods=n).mean() if kind == "sma" else bc.ewm(span=n, min_periods=n).mean()
    return pd.Series(BTC, index=P.dates).where(bc > ma)


def f3_target(P, N, M):
    """F3: breakout Donchian BTC -- masuk close > high N hari, keluar close < low M hari."""
    bc = P.close[BTC]
    hi = P.high[BTC].rolling(N, min_periods=N).max().shift(1)
    lo = P.low[BTC].rolling(M, min_periods=M).min().shift(1)
    state, s = [], None
    for c, h, l in zip(bc, hi, lo):
        if s is None and c > h:
            s = BTC
        elif s is not None and c < l:
            s = None
        state.append(s)
    return pd.Series(state, index=P.dates)


def f4_target(P, k, th, H):
    """F4: dip dalam uptrend -- BTC & coin > MA200, beli coin RSI(k) terendah < th, keluar RSI>60 / H hari."""
    bc = P.close[BTC]
    regime = bc > bc.rolling(200, min_periods=200).mean()
    rsi = P.rsi(k)
    cand = rsi.where((rsi < th) & (P.close > P.ma(200)))
    pick = cand.fillna(np.inf).idxmin(axis=1).where(cand.notna().any(axis=1)).where(regime)
    state, s, age = [], None, 0
    for t in P.dates:
        if s is not None:
            age += 1
            if rsi.at[t, s] > 60 or age >= H:
                s = None
        if s is None and isinstance(pick.at[t], str):
            s, age = pick.at[t], 0
        state.append(s)
    return pd.Series(state, index=P.dates)


# ---------------------------------------------------------------------------
# Mesin eksposur harian (porsi BTC 0-100% bisa berubah tiap hari) -- notebook 13
# ---------------------------------------------------------------------------

def run_exposure(panel, weight, start, end, sym=BTC, cost=COST):
    """Backtest satu aset dengan porsi harian w (0..1), keputusan di close t -> berlaku dari open t+1.

    Return hari t = (1 + w[t-1]*gap_t) * (1 + w[t]*intraday_t) - 1, dengan
    gap_t = open_t/close_{t-1} - 1 (masih porsi lama), intraday_t = close_t/open_t - 1 (porsi baru).
    Biaya = |w_baru - w_lama| * cost, dibebankan di open saat porsi berubah.
    Return: (trades DataFrame kosong-kompatibel, equity Series) -- trades = periode w > 0 berturut-turut.
    """
    dates = panel.dates[(panel.dates >= start) & (panel.dates <= end)]
    o, c = panel.open[sym].loc[dates].to_numpy(), panel.close[sym].loc[dates].to_numpy()
    w_dec = weight.reindex(panel.dates).fillna(0).clip(0, 1)
    w_exec = w_dec.shift(1).fillna(0).loc[dates].to_numpy()        # porsi yang berlaku hari t
    eq = np.empty(len(dates)); v = 1.0
    for i in range(len(dates)):
        w_prev = w_exec[i - 1] if i > 0 else 0.0
        if i > 0:
            gap = o[i] / c[i - 1] - 1
            v *= 1 + w_prev * gap
        v *= 1 - abs(w_exec[i] - w_prev) * cost
        v *= 1 + w_exec[i] * (c[i] / o[i] - 1)
        eq[i] = v
    eq = pd.Series(eq, index=dates)
    # "trade" = blok hari berturut-turut dengan porsi > 0 (untuk win rate / rugi per trade)
    on = pd.Series(w_exec > 0, index=dates)
    blocks = on.ne(on.shift()).cumsum()
    rows = []
    for _, blk in on.groupby(blocks):
        if not blk.iloc[0]:
            continue
        a, b = blk.index[0], blk.index[-1]
        prev = eq.shift(1).fillna(1.0)
        rows.append(dict(sym=sym, entry_date=a, exit_date=b, days=len(blk),
                         entry=prev.loc[a], exit=eq.loc[b], reason="EXPOSURE", ret=eq.loc[b] / prev.loc[a] - 1))
    tr = pd.DataFrame(rows, columns=["sym", "entry_date", "exit_date", "days", "entry", "exit", "reason", "ret"])
    eq.attrs["exposure"] = float((w_exec > 0).mean())
    eq.attrs["avg_weight"] = float(w_exec.mean())
    return tr, eq
