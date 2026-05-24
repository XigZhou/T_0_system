from __future__ import annotations

import sqlite3
from pathlib import Path

from .main_universe import DEFAULT_DB_PATH
from .utils import load_env, normalize_date_text, to_float


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _sqlite_calendar_value(conn: sqlite3.Connection, run_date: str) -> bool | None:
    if not _table_exists(conn, "trade_calendar"):
        return None
    columns = _column_names(conn, "trade_calendar")
    date_col = "trade_date" if "trade_date" in columns else "cal_date" if "cal_date" in columns else ""
    if not date_col:
        return None
    open_col = "is_open" if "is_open" in columns else ""
    select_open = f", {open_col}" if open_col else ""
    row = conn.execute(
        f"SELECT {date_col}{select_open} FROM trade_calendar WHERE {date_col} = ? LIMIT 1",
        (run_date,),
    ).fetchone()
    if row is None:
        return None
    if open_col:
        return str(row[1]).strip() == "1"
    return True


def _sqlite_feature_value(conn: sqlite3.Connection, run_date: str) -> bool | None:
    if not _table_exists(conn, "stock_daily_features"):
        return None
    columns = _column_names(conn, "stock_daily_features")
    if "trade_date" not in columns:
        return None
    price_columns = [column for column in ("raw_close", "close") if column in columns]
    selected_columns = ", ".join(price_columns) if price_columns else "trade_date"
    rows = conn.execute(
        f"SELECT {selected_columns} FROM stock_daily_features WHERE trade_date = ? LIMIT 20",
        (run_date,),
    ).fetchall()
    if not rows:
        return None
    if not price_columns:
        return True
    for row in rows:
        for value in row:
            numeric = to_float(value)
            if numeric is not None and numeric > 0:
                return True
    return None


def _sqlite_trade_day(run_date: str, market_db_path: str | Path | None) -> bool | None:
    path = Path(market_db_path) if market_db_path is not None else DEFAULT_DB_PATH
    if not path.exists():
        return None
    with sqlite3.connect(path) as conn:
        calendar_value = _sqlite_calendar_value(conn, run_date)
        if calendar_value is not None:
            return calendar_value
        return _sqlite_feature_value(conn, run_date)


def _tushare_trade_day(run_date: str, env_path: str | Path) -> bool | None:
    token = load_env(Path(env_path)).get("TUSHARE_TOKEN", "").strip()
    if not token:
        return None
    try:
        import tushare as ts

        pro = ts.pro_api(token)
        cal = pro.trade_cal(exchange="", start_date=run_date, end_date=run_date, fields="cal_date,is_open")
    except Exception:
        return None
    if cal is None or cal.empty:
        return None
    return str(cal.iloc[0].get("is_open", "")).strip() == "1"


def is_a_share_trade_day(
    run_date: str,
    *,
    env_path: str | Path = DEFAULT_ENV_PATH,
    market_db_path: str | Path | None = None,
) -> bool | None:
    normalized_date = normalize_date_text(run_date)
    tushare_value = _tushare_trade_day(normalized_date, env_path)
    if tushare_value is not None:
        return tushare_value
    return _sqlite_trade_day(normalized_date, market_db_path)
