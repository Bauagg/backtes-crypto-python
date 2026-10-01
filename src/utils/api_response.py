"""Helper untuk membentuk nilai response JSON."""

from __future__ import annotations

import numpy as np
import pandas as pd


def clean_number(v, digits=None):
    """Bersihkan nilai untuk JSON: NaN -> None, numpy -> python, bulatkan."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.floating, float)):
        return round(float(v), digits) if digits is not None else float(v)
    return v
