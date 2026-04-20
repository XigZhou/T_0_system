from __future__ import annotations

from typing import Iterable

import pandas as pd

from .config import DEFAULT_HORIZONS, DEFAULT_MA_WINDOWS


def normalize_columns(df: pd.DataFrame) -> dict[str, str]:
    return {str(col).strip().lower(): str(col) for col in df.columns}


def compute_indicators(df: pd.DataFrame, horizons: Iterable[int] | None = None) -> pd.DataFrame:
    use_horizons = list(horizons or DEFAULT_HORIZONS)
    out = df.copy()
    cols = normalize_columns(out)
    if "trade_date" not in cols or "close" not in cols:
        raise ValueError("indicator input missing required columns: trade_date/close")

    date_col = cols["trade_date"]
    close_col = cols["close"]
    open_col = cols.get("open")
    high_col = cols.get("high")
    low_col = cols.get("low")
    vol_col = cols.get("vol")
    amount_col = cols.get("amount")

    out[date_col] = pd.to_datetime(out[date_col].astype(str).str.strip(), format="%Y%m%d", errors="coerce")
    out = out.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)

    for col in [close_col, open_col, high_col, low_col, vol_col, amount_col]:
        if col:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    for n in use_horizons:
        base = out[close_col].shift(n - 1)
        out[f"m{n}"] = ((out[close_col] - base) / base).where(base != 0).round(4)

    for n in DEFAULT_MA_WINDOWS:
        out[f"ma{n}"] = out[close_col].rolling(window=n, min_periods=n).mean().round(4)

    out["ret1"] = out[close_col].pct_change(1).round(4)
    out["ret2"] = out[close_col].pct_change(2).round(4)
    out["ret3"] = out[close_col].pct_change(3).round(4)
    out["pct_chg"] = (out[close_col].pct_change(1) * 100.0).round(4)

    for n in (5, 10):
        ma_col = f"ma{n}"
        out[f"bias_ma{n}"] = ((out[close_col] - out[ma_col]) / out[ma_col]).where(out[ma_col] != 0).round(4)

    if high_col and low_col:
        out["amp"] = ((out[high_col] - out[low_col]) / out[close_col]).where(out[close_col] != 0).round(4)
        out["amp5"] = out["amp"].rolling(window=5, min_periods=5).mean().round(4)
        for n in (5, 10, 20):
            out[f"high_{n}"] = out[high_col].rolling(window=n, min_periods=n).max().round(4)
            out[f"low_{n}"] = out[low_col].rolling(window=n, min_periods=n).min().round(4)

    for n in use_horizons:
        base_ma5 = out["ma5"].shift(n - 1)
        base_ma10 = out["ma10"].shift(n - 1)
        out[f"avg5m{n}"] = ((out["ma5"] - base_ma5) / base_ma5).where(base_ma5 != 0).round(4)
        out[f"avg10m{n}"] = ((out["ma10"] - base_ma10) / base_ma10).where(base_ma10 != 0).round(4)

    if vol_col:
        out["vol5"] = out[vol_col].rolling(window=5, min_periods=5).mean().round(4)
        out["vol10"] = out[vol_col].rolling(window=10, min_periods=10).mean().round(4)
        out["vr"] = (out[vol_col] / out["vol5"]).where(out["vol5"] != 0).round(4)

    if amount_col:
        out["amount5"] = out[amount_col].rolling(window=5, min_periods=5).mean().round(4)
        out["amount10"] = out[amount_col].rolling(window=10, min_periods=10).mean().round(4)

    out[date_col] = out[date_col].dt.strftime("%Y%m%d")
    return out
