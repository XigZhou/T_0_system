from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .main_universe import DEFAULT_DB_PATH, normalize_symbol, ts_code_from_symbol

FACTOR_TABLE = "stock_daily_features"
RAW_TABLE = "stock_daily_raw"
STOCK_BASIC_TABLE = "stock_basic"
MAIN_UNIVERSE_TABLE = "main_stock_universe"

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MARKET_PREFIX_RE = re.compile(r"^(sh|hs300|cyb)_.+$")
_FACTOR_PATTERNS = (
    re.compile(r"^m(?:5|10|20|30|60|120)$"),
    re.compile(r"^ma(?:5|10|20)$"),
    re.compile(r"^avg(?:5|10)m(?:5|10|20|30|60|120)$"),
    re.compile(r"^ret[123]$"),
    re.compile(r"^bias_ma(?:5|10)$"),
    re.compile(r"^high_(?:5|10|20)$"),
    re.compile(r"^low_(?:5|10|20)$"),
    _MARKET_PREFIX_RE,
)
_EXCLUDED_FACTOR_COLUMNS = {
    "symbol", "ts_code", "name", "stock_name", "trade_date", "created_at", "updated_at",
    "raw_open", "raw_high", "raw_low", "raw_close", "qfq_open", "qfq_high", "qfq_low", "qfq_close",
    "next_open", "next_close", "next_raw_open", "next_raw_close", "r_on", "r_on_raw",
    "adj_factor", "up_limit", "down_limit",
}


@dataclass(frozen=True)
class FactorMeta:
    field: str
    name: str
    category: str
    purpose: str
    inputs: str
    formula: str
    window: str
    boundary: str
    example: str


Z = {
    "momentum": "\u52a8\u91cf",
    "ma": "\u5747\u7ebf",
    "smooth_momentum": "\u5e73\u6ed1\u52a8\u91cf",
    "return": "\u6536\u76ca",
    "range": "\u533a\u95f4",
    "volatility": "\u6ce2\u52a8",
    "volume": "\u91cf\u80fd",
    "amount": "\u6210\u4ea4\u989d",
    "bar": "\u5f62\u6001",
    "fundamental": "\u57fa\u7840\u9762",
    "constraint": "\u4ea4\u6613\u7ea6\u675f",
    "market": "\u6307\u6570\u73af\u5883",
    "db_field": "\u5e93\u5185\u5b57\u6bb5",
    "boundary": "\u8f93\u5165\u5b57\u6bb5\u7f3a\u5931\u3001\u7a97\u53e3\u6837\u672c\u4e0d\u8db3\u6216\u5206\u6bcd\u4e3a 0 \u65f6\u4e3a\u7a7a\uff1b\u53ea\u4f7f\u7528 T \u65e5\u53ca\u5386\u53f2\u6570\u636e\u3002",
    "example": "\u6309\u516c\u5f0f\u4f7f\u7528\u5f53\u524d\u4ea4\u6613\u65e5\u548c\u5386\u53f2\u7a97\u53e3\u8ba1\u7b97\uff0c\u4e0d\u8bfb\u53d6\u672a\u6765\u6570\u636e\u3002",
    "readonly_factor": "\u5df2\u53ea\u8bfb\u83b7\u53d6\u56e0\u5b50\u5e93\uff1b\u672c\u63a5\u53e3\u672a\u5199\u5165\u6570\u636e\u3002",
    "readonly_stock": "\u5df2\u53ea\u8bfb\u83b7\u53d6\u80a1\u7968\u65e5\u7ebf\u6570\u636e\u6458\u8981\uff1b\u672c\u63a5\u53e3\u672a\u5199\u5165\u6570\u636e\u3002",
    "db_missing": "\u4e3b\u884c\u60c5\u5e93\u4e0d\u5b58\u5728\uff1b\u672c\u63a5\u53e3\u4ec5\u505a\u53ea\u8bfb\u68c0\u67e5\uff0c\u672a\u5199\u5165\u6570\u636e\u3002",
    "feature_missing": "stock_daily_features \u8868\u4e0d\u5b58\u5728\uff1b\u672c\u63a5\u53e3\u4ec5\u505a\u53ea\u8bfb\u68c0\u67e5\uff0c\u672a\u5199\u5165\u6570\u636e\u3002",
    "empty_name": "\u80a1\u7968\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a",
    "available": "\u5728\u5f53\u524d\u7cfb\u7edf\u53ef\u7528\u3002",
    "unavailable": "\u5728\u5f53\u524d\u7cfb\u7edf\u4e0d\u53ef\u7528\u3002",
}


def _quote_identifier(identifier: str) -> str:
    if not _IDENTIFIER_RE.match(identifier):
        raise ValueError(f"invalid SQL identifier: {identifier}")
    return f'"{identifier}"'


def _db_path(db_path: str | Path | None = None) -> Path:
    return Path(db_path) if db_path is not None else DEFAULT_DB_PATH


def _connect_existing(db_path: str | Path | None = None) -> sqlite3.Connection | None:
    path = _db_path(db_path)
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    if not _table_exists(conn, table_name):
        return []
    return [str(row["name"]) for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})")]


def _one_row(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row is not None else {}


def _date_span(conn: sqlite3.Connection, table_name: str) -> dict[str, str]:
    if not _table_exists(conn, table_name) or "trade_date" not in _table_columns(conn, table_name):
        return {"start_date": "", "end_date": ""}
    row = _one_row(
        conn,
        f"""
        SELECT MIN(trade_date) AS start_date, MAX(trade_date) AS end_date
        FROM {_quote_identifier(table_name)}
        WHERE trade_date IS NOT NULL AND TRIM(trade_date) <> ''
        """,
    )
    return {"start_date": str(row.get("start_date") or ""), "end_date": str(row.get("end_date") or "")}


def _factor_meta(field: str, name: str, category: str, purpose: str, inputs: str, formula: str, window: str, example: str = "") -> FactorMeta:
    return FactorMeta(
        field=field,
        name=name,
        category=category,
        purpose=purpose,
        inputs=inputs,
        formula=formula,
        window=window,
        boundary=Z["boundary"],
        example=example or Z["example"],
    )


def _factor_meta_by_field() -> dict[str, FactorMeta]:
    rows: list[FactorMeta] = []
    for n in (5, 10, 20, 30, 60, 120):
        rows.append(_factor_meta(
            f"m{n}", f"{n}\u65e5\u4ef7\u683c\u52a8\u91cf", Z["momentum"],
            "\u8861\u91cf\u5f53\u524d\u524d\u590d\u6743\u6536\u76d8\u4ef7\u76f8\u5bf9\u7a97\u53e3\u8d77\u70b9\u7684\u6da8\u8dcc\u5e45\u3002",
            "close", f"m{n}(T) = [close(T) - close(T-{n}+1)] / close(T-{n}+1)", f"{n}\u4e2a\u4ea4\u6613\u65e5",
            "close(T)=11.00, close(T-4)=10.00, m5=0.10" if n == 5 else "",
        ))
    for n in (5, 10, 20):
        rows.append(_factor_meta(f"ma{n}", f"{n}\u65e5\u79fb\u52a8\u5747\u7ebf", Z["ma"], "\u5e73\u6ed1\u524d\u590d\u6743\u4ef7\u683c\u6ce2\u52a8\u3002", "close", f"ma{n}(T) = mean(close(T), ..., close(T-{n}+1))", f"{n}\u4e2a\u4ea4\u6613\u65e5"))
    for prefix, base in (("avg5m", "ma5"), ("avg10m", "ma10")):
        for n in (5, 10, 20, 30, 60, 120):
            rows.append(_factor_meta(f"{prefix}{n}", f"{base}{n}\u65e5\u5e73\u6ed1\u52a8\u91cf", Z["smooth_momentum"], "\u7528\u5747\u7ebf\u52a8\u91cf\u4ee3\u66ff\u539f\u59cb\u4ef7\u683c\u52a8\u91cf\uff0c\u964d\u4f4e\u77ed\u671f\u566a\u97f3\u3002", base, f"{prefix}{n}(T) = [{base}(T) - {base}(T-{n}+1)] / {base}(T-{n}+1)", f"{n}\u4e2a\u4ea4\u6613\u65e5"))
    for k in (1, 2, 3):
        rows.append(_factor_meta(f"ret{k}", f"{k}\u65e5\u77ed\u671f\u6536\u76ca", Z["return"], "\u63cf\u8ff0\u6781\u77ed\u5468\u671f\u6536\u76ca\u8282\u594f\u3002", "close", f"ret{k}(T) = close(T) / close(T-{k}) - 1", f"{k}\u4e2a\u4ea4\u6613\u65e5"))
    for n in (5, 10):
        rows.append(_factor_meta(f"bias_ma{n}", f"{n}\u65e5\u5747\u7ebf\u504f\u79bb\u7387", Z["ma"], "\u8861\u91cf\u4ef7\u683c\u8ddd\u79bb\u5747\u7ebf\u7684\u504f\u79bb\u7a0b\u5ea6\u3002", f"close, ma{n}", f"bias_ma{n}(T) = [close(T) - ma{n}(T)] / ma{n}(T)", f"{n}\u65e5\u5747\u7ebf"))
    for kind, label, agg in (("high", "\u533a\u95f4\u6700\u9ad8\u4ef7", "max"), ("low", "\u533a\u95f4\u6700\u4f4e\u4ef7", "min")):
        for n in (5, 10, 20):
            rows.append(_factor_meta(f"{kind}_{n}", f"{n}\u65e5{label}", Z["range"], "\u7528\u4e8e\u5224\u65ad\u7a81\u7834\u3001\u56de\u64a4\u548c\u76f8\u5bf9\u4f4d\u7f6e\u3002", kind, f"{kind}_{n}(T) = {agg}({kind}(T), ..., {kind}(T-{n}+1))", f"{n}\u4e2a\u4ea4\u6613\u65e5"))
    rows.extend([
        _factor_meta("pct_chg", "\u65e5\u6da8\u8dcc\u5e45", Z["return"], "\u8fc7\u6ee4\u6781\u7aef\u6da8\u8dcc\u65e5\u3002", "close or Tushare daily.pct_chg", "pct_chg(T) = [close(T) / close(T-1) - 1] * 100", "1\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("amp", "\u5355\u65e5\u632f\u5e45", Z["volatility"], "\u8861\u91cf\u65e5\u5185\u6ce2\u52a8\u3002", "high, low, close", "amp(T) = [high(T) - low(T)] / close(T)", "1\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("amp5", "5\u65e5\u5e73\u5747\u632f\u5e45", Z["volatility"], "\u8861\u91cf\u8fd1 5 \u65e5\u5e73\u5747\u6ce2\u52a8\u3002", "amp", "amp5(T) = mean(amp(T), ..., amp(T-4))", "5\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("vol5", "5\u65e5\u5747\u91cf", Z["volume"], "\u8861\u91cf\u6210\u4ea4\u91cf\u57fa\u51c6\u3002", "vol", "vol5(T) = mean(vol(T), ..., vol(T-4))", "5\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("vol10", "10\u65e5\u5747\u91cf", Z["volume"], "\u8861\u91cf\u6210\u4ea4\u91cf\u57fa\u51c6\u3002", "vol", "vol10(T) = mean(vol(T), ..., vol(T-9))", "10\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("vr", "\u91cf\u6bd4", Z["volume"], "\u8861\u91cf\u5f53\u524d\u6210\u4ea4\u91cf\u76f8\u5bf9 5 \u65e5\u5747\u91cf\u7684\u653e\u5927\u6216\u7f29\u5c0f\u3002", "vol, vol5", "vr(T) = vol(T) / vol5(T)", "5\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("amount5", "5\u65e5\u5747\u6210\u4ea4\u989d", Z["amount"], "\u8861\u91cf\u91d1\u989d\u7ef4\u5ea6\u6d41\u52a8\u6027\u3002", "amount", "amount5(T) = mean(amount(T), ..., amount(T-4))", "5\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("amount10", "10\u65e5\u5747\u6210\u4ea4\u989d", Z["amount"], "\u8861\u91cf\u91d1\u989d\u7ef4\u5ea6\u6d41\u52a8\u6027\u3002", "amount", "amount10(T) = mean(amount(T), ..., amount(T-9))", "10\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("close_to_up_limit", "\u6536\u76d8\u4ef7\u63a5\u8fd1\u6da8\u505c\u6bd4\u4f8b", Z["bar"], "\u8861\u91cf\u6536\u76d8\u4ef7\u8ddd\u79bb\u6da8\u505c\u4ef7\u7684\u4f4d\u7f6e\u3002", "raw_close, up_limit", "close_to_up_limit = raw_close / up_limit", "1\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("high_to_up_limit", "\u6700\u9ad8\u4ef7\u63a5\u8fd1\u6da8\u505c\u6bd4\u4f8b", Z["bar"], "\u8861\u91cf\u65e5\u5185\u6700\u9ad8\u4ef7\u8ddd\u79bb\u6da8\u505c\u4ef7\u7684\u4f4d\u7f6e\u3002", "raw_high, up_limit", "high_to_up_limit = raw_high / up_limit", "1\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("close_pos_in_bar", "\u6536\u76d8\u5728\u65e5\u5185\u533a\u95f4\u4f4d\u7f6e", Z["bar"], "\u63cf\u8ff0\u6536\u76d8\u4ef7\u5728\u5f53\u65e5\u9ad8\u4f4e\u70b9\u533a\u95f4\u4e2d\u7684\u4f4d\u7f6e\u3002", "raw_close, raw_low, raw_high", "close_pos_in_bar = (raw_close - raw_low) / (raw_high - raw_low)", "1\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("body_pct", "K\u7ebf\u5b9e\u4f53\u5360\u6bd4", Z["bar"], "\u63cf\u8ff0\u65e5\u5185\u5b9e\u4f53\u5f3a\u5f31\u3002", "raw_open, raw_close", "body_pct = (raw_close - raw_open) / raw_open", "1\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("upper_shadow_pct", "\u4e0a\u5f71\u7ebf\u5360\u6bd4", Z["bar"], "\u63cf\u8ff0\u4e0a\u5f71\u7ebf\u76f8\u5bf9\u5f00\u76d8\u4ef7\u7684\u957f\u5ea6\u3002", "raw_open, raw_high, raw_close", "upper_shadow_pct = (raw_high - max(raw_open, raw_close)) / raw_open", "1\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("lower_shadow_pct", "\u4e0b\u5f71\u7ebf\u5360\u6bd4", Z["bar"], "\u63cf\u8ff0\u4e0b\u5f71\u7ebf\u76f8\u5bf9\u5f00\u76d8\u4ef7\u7684\u957f\u5ea6\u3002", "raw_open, raw_low, raw_close", "lower_shadow_pct = (min(raw_open, raw_close) - raw_low) / raw_open", "1\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("vol_ratio_3", "3\u65e5\u91cf\u6bd4", Z["volume"], "\u8861\u91cf\u6210\u4ea4\u91cf\u76f8\u5bf9 3 \u65e5\u5747\u91cf\u3002", "vol", "vol_ratio_3 = vol / mean(vol, 3 days)", "3\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("amount_ratio_3", "3\u65e5\u6210\u4ea4\u989d\u6bd4", Z["amount"], "\u8861\u91cf\u6210\u4ea4\u989d\u76f8\u5bf9 3 \u65e5\u5747\u989d\u3002", "amount", "amount_ratio_3 = amount / mean(amount, 3 days)", "3\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("body_pct_3avg", "3\u65e5\u5e73\u5747\u5b9e\u4f53\u5360\u6bd4", Z["bar"], "\u5e73\u6ed1 K \u7ebf\u5b9e\u4f53\u5f3a\u5f31\u3002", "body_pct", "body_pct_3avg = mean(body_pct, 3 days)", "3\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("close_to_up_limit_3max", "3\u65e5\u6700\u9ad8\u63a5\u8fd1\u6da8\u505c\u6bd4\u4f8b", Z["bar"], "\u89c2\u5bdf\u8fd1 3 \u65e5\u662f\u5426\u63a5\u8fd1\u6da8\u505c\u3002", "close_to_up_limit", "close_to_up_limit_3max = max(close_to_up_limit, 3 days)", "3\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("vol_ratio_5", "5\u65e5\u91cf\u6bd4", Z["volume"], "\u8861\u91cf\u6210\u4ea4\u91cf\u76f8\u5bf9 5 \u65e5\u5747\u91cf\u3002", "vol, vol5", "vol_ratio_5 = vol / vol5", "5\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("ret_accel_3", "3\u65e5\u6536\u76ca\u52a0\u901f\u5ea6", Z["return"], "\u8861\u91cf\u77ed\u671f\u6536\u76ca\u662f\u5426\u52a0\u901f\u3002", "ret1, ret3", "ret_accel_3 = ret1 - ret3 / 3", "3\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("listed_days", "\u4e0a\u5e02\u5929\u6570", Z["fundamental"], "\u8fc7\u6ee4\u65b0\u80a1\u548c\u4e0a\u5e02\u65f6\u95f4\u4e0d\u8db3\u7684\u80a1\u7968\u3002", "trade_date, list_date", "listed_days = trade_date - list_date", "\u622a\u81f3\u5f53\u524d\u4ea4\u6613\u65e5"),
        _factor_meta("total_mv_snapshot", "\u603b\u5e02\u503c\u5feb\u7167", Z["fundamental"], "\u7528\u4e8e\u5e02\u503c\u8fc7\u6ee4\u548c\u5206\u5c42\u3002", "daily_basic.total_mv", "from daily_basic.total_mv snapshot", "\u5feb\u7167\u65e5"),
        _factor_meta("turnover_rate_snapshot", "\u6362\u624b\u7387\u5feb\u7167", Z["fundamental"], "\u7528\u4e8e\u6d41\u52a8\u6027\u6216\u6362\u624b\u8fc7\u6ee4\u3002", "daily_basic.turnover_rate_f", "from daily_basic.turnover_rate_f snapshot", "\u5feb\u7167\u65e5"),
        _factor_meta("can_buy_open_t", "T\u65e5\u5f00\u76d8\u53ef\u4e70", Z["constraint"], "\u907f\u514d\u5728\u505c\u724c\u3001\u6da8\u505c\u6216\u8dcc\u505c\u5f00\u76d8\u65f6\u4e70\u5165\u3002", "raw_open, up_limit, down_limit, suspend_d", "not suspended and raw_open valid and not near limit-up/down", "1\u4e2a\u4ea4\u6613\u65e5"),
        _factor_meta("can_sell_t", "T\u65e5\u5f00\u76d8\u53ef\u5356", Z["constraint"], "\u907f\u514d\u5728\u505c\u724c\u6216\u8dcc\u505c\u5f00\u76d8\u65f6\u5356\u51fa\u3002", "raw_open, down_limit, suspend_d", "not suspended and raw_open valid and not near down-limit", "1\u4e2a\u4ea4\u6613\u65e5"),
    ])
    return {row.field: row for row in rows}


def _is_factor_column(column: str) -> bool:
    if column in _EXCLUDED_FACTOR_COLUMNS:
        return False
    if column in {"open", "high", "low", "close", "vol", "amount"}:
        return False
    if column in {"industry", "market", "board"}:
        return True
    meta = _factor_meta_by_field()
    return column in meta or any(pattern.match(column) for pattern in _FACTOR_PATTERNS)


def _fallback_meta(field: str) -> FactorMeta:
    if _MARKET_PREFIX_RE.match(field):
        return _factor_meta(field, f"{field} \u6307\u6570\u73af\u5883\u5b57\u6bb5", Z["market"], "\u628a\u5927\u76d8\u72b6\u6001\u7eb3\u5165\u4e70\u5165\u6761\u4ef6\u548c\u8bc4\u5206\u3002", "market_context", "computed from index daily data", "\u968f\u5b57\u6bb5\u540e\u7f00\u53d8\u5316")
    return _factor_meta(field, field, Z["db_field"], "\u4e3b\u5e93\u4e2d\u5b58\u5728\u4e14\u53ef\u4f9b\u8868\u8fbe\u5f0f\u6216\u8bca\u65ad\u4f7f\u7528\u7684\u5b57\u6bb5\u3002", FACTOR_TABLE, "from stock_daily_features", "\u968f\u5b57\u6bb5\u53e3\u5f84\u53d8\u5316")


def list_market_factors(db_path: str | Path | None = None) -> dict[str, Any]:
    conn = _connect_existing(db_path)
    if conn is None:
        return {"db_path": str(_db_path(db_path)), "summary": {"factor_count": 0, "start_date": "", "end_date": "", "row_count": 0, "source_table": FACTOR_TABLE}, "factors": [], "message": Z["db_missing"]}
    try:
        if not _table_exists(conn, FACTOR_TABLE):
            return {"db_path": str(_db_path(db_path)), "summary": {"factor_count": 0, "start_date": "", "end_date": "", "row_count": 0, "source_table": FACTOR_TABLE}, "factors": [], "message": Z["feature_missing"]}
        meta = _factor_meta_by_field()
        factors = []
        for field in [column for column in _table_columns(conn, FACTOR_TABLE) if _is_factor_column(column)]:
            item = meta.get(field) or _fallback_meta(field)
            factors.append(item.__dict__)
        factors.sort(key=lambda row: (str(row["category"]), str(row["field"])))
        span = _date_span(conn, FACTOR_TABLE)
        row_count = int(_one_row(conn, f"SELECT COUNT(*) AS count FROM {_quote_identifier(FACTOR_TABLE)}").get("count") or 0)
        return {"db_path": str(_db_path(db_path)), "summary": {"factor_count": len(factors), "start_date": span["start_date"], "end_date": span["end_date"], "row_count": row_count, "source_table": FACTOR_TABLE}, "factors": factors, "message": Z["readonly_factor"]}
    finally:
        conn.close()


def _table_row_count(conn: sqlite3.Connection, table_name: str) -> int:
    if not _table_exists(conn, table_name):
        return 0
    try:
        return int(_one_row(conn, f"SELECT COUNT(*) AS count FROM {_quote_identifier(table_name)}").get("count") or 0)
    except sqlite3.Error:
        return 0


def _data_table(conn: sqlite3.Connection) -> str:
    if _table_row_count(conn, RAW_TABLE) > 0:
        return RAW_TABLE
    if _table_exists(conn, FACTOR_TABLE):
        return FACTOR_TABLE
    return RAW_TABLE


def _stock_display(row: sqlite3.Row | dict[str, Any]) -> dict[str, str]:
    item = dict(row)
    symbol = normalize_symbol(item.get("symbol") or item.get("ts_code"))
    return {"symbol": symbol, "ts_code": str(item.get("ts_code") or ts_code_from_symbol(symbol)).strip() if symbol else str(item.get("ts_code") or "").strip(), "name": str(item.get("name") or item.get("stock_name") or "").strip()}


def _stock_names(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for table in (STOCK_BASIC_TABLE, MAIN_UNIVERSE_TABLE):
        if not _table_exists(conn, table):
            continue
        columns = set(_table_columns(conn, table))
        if "symbol" not in columns:
            continue
        name_expr = "name" if "name" in columns else "''"
        ts_expr = "ts_code" if "ts_code" in columns else "''"
        for row in conn.execute(f"SELECT symbol, {ts_expr} AS ts_code, {name_expr} AS name FROM {_quote_identifier(table)} ORDER BY symbol"):
            item = _stock_display(row)
            if not item["symbol"]:
                continue
            current = result.get(item["symbol"], {})
            result[item["symbol"]] = {"symbol": item["symbol"], "ts_code": item["ts_code"] or current.get("ts_code") or ts_code_from_symbol(item["symbol"]), "name": item["name"] or current.get("name") or ""}
    return result


def _stock_ranges(conn: sqlite3.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    if not _table_exists(conn, table_name):
        return {}
    columns = set(_table_columns(conn, table_name))
    if not {"symbol", "trade_date"} <= columns:
        return {}
    name_sql = "MAX(COALESCE(NULLIF(name, ''), '')) AS name," if "name" in columns else "'' AS name,"
    ts_sql = "MAX(COALESCE(NULLIF(ts_code, ''), '')) AS ts_code," if "ts_code" in columns else "'' AS ts_code,"
    rows = conn.execute(
        f"""
        SELECT symbol, {ts_sql} {name_sql}
               MIN(trade_date) AS start_date, MAX(trade_date) AS end_date, COUNT(*) AS row_count
        FROM {_quote_identifier(table_name)}
        WHERE symbol IS NOT NULL AND TRIM(symbol) <> '' AND trade_date IS NOT NULL AND TRIM(trade_date) <> ''
        GROUP BY symbol
        ORDER BY symbol
        """
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        symbol = normalize_symbol(item.get("symbol"))
        if symbol:
            result[symbol] = {"symbol": symbol, "ts_code": str(item.get("ts_code") or ts_code_from_symbol(symbol)).strip() or ts_code_from_symbol(symbol), "name": str(item.get("name") or "").strip(), "start_date": str(item.get("start_date") or ""), "end_date": str(item.get("end_date") or ""), "row_count": int(item.get("row_count") or 0)}
    return result


def list_market_stocks(limit: int = 500, db_path: str | Path | None = None) -> dict[str, Any]:
    clean_limit = max(1, min(int(limit or 500), 5000))
    conn = _connect_existing(db_path)
    if conn is None:
        return {"db_path": str(_db_path(db_path)), "summary": {"stock_count": 0, "start_date": "", "end_date": "", "row_count": 0, "source_table": RAW_TABLE}, "stocks": [], "limit": 0, "message": Z["db_missing"]}
    try:
        table_name = _data_table(conn)
        ranges = _stock_ranges(conn, table_name)
        names = _stock_names(conn)
        stocks = []
        for symbol, row in sorted(ranges.items()):
            basic = names.get(symbol, {})
            stocks.append({"symbol": symbol, "ts_code": row.get("ts_code") or basic.get("ts_code") or ts_code_from_symbol(symbol), "name": row.get("name") or basic.get("name") or "", "start_date": row.get("start_date") or "", "end_date": row.get("end_date") or "", "row_count": int(row.get("row_count") or 0)})
        span = _date_span(conn, table_name)
        row_count = int(_one_row(conn, f"SELECT COUNT(*) AS count FROM {_quote_identifier(table_name)}").get("count") or 0) if _table_exists(conn, table_name) else 0
        return {"db_path": str(_db_path(db_path)), "summary": {"stock_count": len(stocks), "start_date": span["start_date"], "end_date": span["end_date"], "row_count": row_count, "source_table": table_name}, "stocks": stocks[:clean_limit], "limit": clean_limit, "message": Z["readonly_stock"]}
    finally:
        conn.close()


def _name_matches(conn: sqlite3.Connection, stock_name: str) -> list[dict[str, str]]:
    matches: dict[str, dict[str, str]] = {}
    for table in (STOCK_BASIC_TABLE, MAIN_UNIVERSE_TABLE):
        if not _table_exists(conn, table):
            continue
        columns = set(_table_columns(conn, table))
        if "name" not in columns or "symbol" not in columns:
            continue
        active_clause = " AND COALESCE(is_active, 1) = 1" if "is_active" in columns else ""
        for row in conn.execute(f"SELECT symbol, ts_code, name FROM {_quote_identifier(table)} WHERE TRIM(name)=?{active_clause} ORDER BY symbol", (stock_name,)):
            item = _stock_display(row)
            if item["symbol"]:
                matches.setdefault(item["symbol"], item)
    return sorted(matches.values(), key=lambda row: row["symbol"])


def check_market_stock(stock_name: str, db_path: str | Path | None = None) -> dict[str, Any]:
    name = str(stock_name or "").strip()
    if not name:
        raise ValueError(Z["empty_name"])
    conn = _connect_existing(db_path)
    if conn is None:
        return {"stock_name": name, "available": False, "matches": [], "message": f"{name} {Z['unavailable']}"}
    try:
        table_name = _data_table(conn)
        ranges = _stock_ranges(conn, table_name)
        matches = []
        for item in _name_matches(conn, name):
            data = ranges.get(item["symbol"])
            matches.append({**item, "available": data is not None, "start_date": str((data or {}).get("start_date") or ""), "end_date": str((data or {}).get("end_date") or ""), "row_count": int((data or {}).get("row_count") or 0)})
        available = any(bool(item.get("available")) for item in matches)
        return {"stock_name": name, "available": available, "matches": matches, "source_table": table_name, "message": f"{name} {Z['available'] if available else Z['unavailable']}"}
    finally:
        conn.close()
