from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


def load_env(env_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if os.environ.get("TUSHARE_TOKEN", "").strip():
        out["TUSHARE_TOKEN"] = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not env_path.exists():
        return out
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        clean_key = key.strip()
        if clean_key == "TUSHARE_TOKEN" and out.get("TUSHARE_TOKEN"):
            continue
        out[clean_key] = value.strip().strip('"').strip("'")
    return out


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_date_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if len(text) == 8 and text.isdigit():
        return text
    dt = pd.to_datetime(text, errors="coerce")
    if pd.isna(dt):
        raise ValueError(f"invalid date value: {value}")
    return dt.strftime("%Y%m%d")


def normalize_date_series(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    parsed = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    return parsed


def latest_open_trade_date(pro, end_date: str) -> str:
    start_date = (datetime.strptime(end_date, "%Y%m%d") - timedelta(days=45)).strftime("%Y%m%d")
    cal = pro.trade_cal(exchange="", start_date=start_date, end_date=end_date, is_open="1", fields="cal_date")
    if cal is None or cal.empty:
        raise RuntimeError("failed to fetch trade calendar")
    return str(cal.iloc[-1]["cal_date"])


def infer_board(symbol: str) -> str:
    code = str(symbol).strip()
    if code.startswith(("300", "301")):
        return "创业板"
    if code.startswith("688"):
        return "科创板"
    if code.startswith(("8", "4")):
        return "北交所"
    return "主板"


def to_float(value: Any) -> float | None:
    if pd.isna(value):
        return None
    try:
        return float(value)
    except Exception:
        return None


def pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) * 100.0, 4)
