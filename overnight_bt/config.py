from __future__ import annotations

from pathlib import Path


DEFAULT_HORIZONS = [120, 60, 30, 20, 10, 5]
DEFAULT_MA_WINDOWS = [5, 10, 20]
DEFAULT_INDEXES = [
    ("sh", "000001.SH", "上证指数"),
    ("hs300", "000300.SH", "沪深300"),
    ("cyb", "399006.SZ", "创业板指"),
]
REQUIRED_PROCESSED_COLUMNS = {
    "trade_date",
    "symbol",
    "name",
    "open",
    "high",
    "low",
    "close",
    "raw_open",
    "raw_high",
    "raw_low",
    "raw_close",
    "qfq_open",
    "qfq_high",
    "qfq_low",
    "qfq_close",
    "can_buy_t",
    "can_buy_open_t",
    "can_sell_t",
}


def root_dir() -> Path:
    return Path(__file__).resolve().parent.parent
