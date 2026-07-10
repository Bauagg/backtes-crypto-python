"""Download historical daily klines from Binance Vision (data.binance.vision).

Binance's REST API (api.binance.com) is often SSL-blocked on Indonesian
networks, but the public data archive at data.binance.vision is not. This
module downloads monthly kline ZIPs from that archive and writes them out in
the same CSV layout as data/raw/BTCUSD_1d_1y.csv so they drop straight into
the existing loader/notebook.

Usage (from project root, inside the venv):
    python -m crypto_backtest.data.download_binance_vision BTCUSDT --start 2018-01
    python -m crypto_backtest.data.download_binance_vision BTCUSDT ETHUSDT --start 2021-01

Note: Binance Vision only has USDT (and a few other) quote pairs -- no IDR.
For a % -based strategy (MA/RSI/volume/correlation) BTCUSDT daily returns are
effectively identical to BTCIDR, so this is fine for backtesting.
"""

from __future__ import annotations

import argparse
import io
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"

# Binance Vision monthly kline CSVs have no header; these are the documented columns.
BINANCE_RAW_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
]

# Output layout must match data/raw/BTCUSD_1d_1y.csv exactly.
OUTPUT_COLUMNS = [
    "date", "open_time", "open", "high", "low", "close", "volume",
    "close_time", "is_closed",
]


def _month_range(start: str, end: str | None) -> list[str]:
    """Yield 'YYYY-MM' strings from start to end (inclusive)."""
    start_dt = datetime.strptime(start, "%Y-%m")
    end_dt = datetime.strptime(end, "%Y-%m") if end else datetime.today()
    months = []
    y, m = start_dt.year, start_dt.month
    while (y, m) <= (end_dt.year, end_dt.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def _fetch_month(symbol: str, interval: str, month: str) -> pd.DataFrame | None:
    """Download and parse one monthly kline ZIP; return None if that month is absent (404)."""
    url = f"{BASE_URL}/{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
    resp = requests.get(url, timeout=60)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    csv_name = zf.namelist()[0]
    df = pd.read_csv(zf.open(csv_name), header=None, names=BINANCE_RAW_COLUMNS)
    # Some months ship with a header row ("open_time,...") -- drop it if present.
    df = df[pd.to_numeric(df["open_time"], errors="coerce").notna()]
    return df


def download_symbol(symbol: str, interval: str = "1d", start: str = "2018-01",
                     end: str | None = None, raw_dir: Path = RAW_DATA_DIR,
                     lookback_label: str = "full") -> Path:
    """Download a symbol's full daily history and write it to raw_dir.

    Output filename: {symbol}_{interval}_{lookback_label}.csv, e.g.
    BTCUSDT_1d_full.csv -- picked up by discover_symbols() automatically.
    """
    frames = []
    missing_streak = 0
    for month in _month_range(start, end):
        df = _fetch_month(symbol, interval, month)
        if df is None:
            missing_streak += 1
            # Allow gaps at the very start (before listing) but stop after a long
            # trailing run of missing months (we've passed the latest available).
            if frames and missing_streak >= 2:
                break
            continue
        missing_streak = 0
        frames.append(df)
        print(f"  {symbol} {month}: {len(df)} baris")

    if not frames:
        raise RuntimeError(f"Tidak ada data untuk {symbol} sejak {start}. Cek nama simbol.")

    raw = pd.concat(frames, ignore_index=True)
    raw = raw.astype({"open_time": "int64", "close_time": "int64"})

    # Binance switched some newer monthly files from millisecond to microsecond
    # timestamps (16-digit instead of 13). Normalize everything back to ms so the
    # date conversion and downstream loader stay consistent.
    def _to_ms(series: pd.Series) -> pd.Series:
        # A daily open_time in ms is ~1.3e12-1.8e12 (13 digits); in us it's ~1e15+.
        return series.where(series < 1_000_000_000_000_0, series // 1000)

    raw["open_time"] = _to_ms(raw["open_time"])
    raw["close_time"] = _to_ms(raw["close_time"])

    out = pd.DataFrame()
    out["open_time"] = raw["open_time"]
    out["date"] = pd.to_datetime(raw["open_time"], unit="ms").dt.strftime("%Y-%m-%d %H:%M:%S")
    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = raw[col]
    out["close_time"] = raw["close_time"]
    out["is_closed"] = True

    out = out[OUTPUT_COLUMNS].drop_duplicates(subset="open_time").sort_values("open_time")

    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = raw_dir / f"{symbol}_{interval}_{lookback_label}.csv"
    out.to_csv(out_path, index=False)
    print(f"-> {out_path}  ({len(out)} baris, {out['date'].iloc[0][:10]} s/d {out['date'].iloc[-1][:10]})")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download daily klines from Binance Vision.")
    parser.add_argument("symbols", nargs="+", help="e.g. BTCUSDT ETHUSDT")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--start", default="2018-01", help="YYYY-MM (default 2018-01)")
    parser.add_argument("--end", default=None, help="YYYY-MM (default: latest available)")
    args = parser.parse_args()

    for symbol in args.symbols:
        print(f"Downloading {symbol} ...")
        download_symbol(symbol, interval=args.interval, start=args.start, end=args.end)


if __name__ == "__main__":
    main()
