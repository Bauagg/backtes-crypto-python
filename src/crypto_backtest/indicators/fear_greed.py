"""Bagian 1.4 -- Fear & Greed Index (market sentiment context factor).

Source: https://api.alternative.me/fng/ (Bagian 6). Historical values are
cached to data/raw/fear_greed_index.csv so backtests don't need network
access on every run.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_PATH = PROJECT_ROOT / "data" / "raw" / "fear_greed_index.csv"

# URL API dibaca dari environment (.env), dengan default kalau tidak diset.
FNG_API_URL = os.getenv("FNG_API_URL", "https://api.alternative.me/fng/")

FNG_EXTREME_FEAR = 25
FNG_EXTREME_GREED = 75


def fetch_fear_greed_index(limit: int = 0) -> pd.DataFrame:
    """Fetch historical Fear & Greed Index values from alternative.me.

    limit=0 requests the full available history. Returns a DataFrame indexed
    by date with a single `fng_value` column (0-100).
    """
    resp = requests.get(
        FNG_API_URL,
        params={"limit": limit, "format": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()["data"]

    df = pd.DataFrame(payload)
    df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s").dt.normalize()
    df["fng_value"] = pd.to_numeric(df["value"])
    df = df.set_index("date").sort_index()
    return df[["fng_value"]]


def load_fear_greed_index(cache_path: str | Path = DEFAULT_CACHE_PATH,
                           refresh: bool = False) -> pd.DataFrame:
    """Load Fear & Greed Index from local cache, fetching + caching if missing."""
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        df = pd.read_csv(cache_path, index_col="date", parse_dates=True)
        return df

    df = fetch_fear_greed_index()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path)
    return df
