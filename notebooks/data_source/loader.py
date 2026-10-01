"""Load OHLCV kline data from notebooks/data/raw into clean pandas DataFrames."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

NOTEBOOKS_DIR = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = NOTEBOOKS_DIR / "data" / "raw"

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def load_klines_csv(path: str | Path) -> pd.DataFrame:
    """Load a klines CSV (as exported by the backend `/api/market/klines` proxy).

    Returns a DataFrame indexed by date (UTC, daily) with numeric OHLCV columns,
    sorted ascending and de-duplicated on the index.
    """
    path = Path(path)
    df = pd.read_csv(path)

    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    for col in OHLCV_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df[OHLCV_COLUMNS]


def load_symbol(symbol: str, timeframe: str = "1d", lookback: str = "1y",
                 raw_dir: str | Path = RAW_DATA_DIR) -> pd.DataFrame:
    """Load klines for a symbol using the `{SYMBOL}_{timeframe}_{lookback}.csv` convention."""
    raw_dir = Path(raw_dir)
    path = raw_dir / f"{symbol}_{timeframe}_{lookback}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Data file not found: {path}. Drop a CSV with the same columns as "
            f"BTCUSD_1d_1y.csv into {raw_dir} to add more symbols."
        )
    return load_klines_csv(path)


def discover_symbols(timeframe: str = "1d", lookback: str = "1y",
                      raw_dir: str | Path = RAW_DATA_DIR) -> list[str]:
    """List symbols available in raw_dir for the given timeframe/lookback suffix."""
    raw_dir = Path(raw_dir)
    suffix = f"_{timeframe}_{lookback}.csv"
    return sorted(
        p.name[: -len(suffix)]
        for p in raw_dir.glob(f"*{suffix}")
    )


def load_all_symbols(timeframe: str = "1d", lookback: str = "1y",
                      raw_dir: str | Path = RAW_DATA_DIR) -> dict[str, pd.DataFrame]:
    """Load every symbol available in raw_dir into a dict of DataFrames."""
    symbols = discover_symbols(timeframe=timeframe, lookback=lookback, raw_dir=raw_dir)
    return {sym: load_symbol(sym, timeframe, lookback, raw_dir) for sym in symbols}
