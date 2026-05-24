from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .sqlite_only_guard import assert_sqlite_only_allowed
from .main_universe import (
    DEFAULT_DB_PATH,
    LEGACY_STOCK_POOL_DB_PATH,
    init_main_universe_db,
    normalize_symbol,
    ts_code_from_symbol,
)

TABLE_NAME = "stock_daily_features"
DISABLE_LEGACY_FALLBACK = object()
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_BASE_COLUMNS: dict[str, str] = {
    "symbol": "TEXT NOT NULL",
    "trade_date": "TEXT NOT NULL",
    "ts_code": "TEXT",
    "name": "TEXT",
    "raw_open": "REAL",
    "raw_close": "REAL",
    "close": "REAL",
    "can_buy_open_t": "INTEGER",
    "can_sell_t": "INTEGER",
    "m5": "REAL",
    "m10": "REAL",
    "m20": "REAL",
    "amount": "REAL",
}


def _db_path(db_path: str | Path | None = None) -> Path:
    return Path(db_path) if db_path is not None else DEFAULT_DB_PATH


def _legacy_db_path(legacy_db_path: str | Path | None = None) -> Path:
    return Path(legacy_db_path) if legacy_db_path is not None else LEGACY_STOCK_POOL_DB_PATH


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_existing(db_path: str | Path | None = None) -> sqlite3.Connection | None:
    path = _db_path(db_path)
    if not path.exists():
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _legacy_connect_existing(legacy_db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _legacy_db_path(legacy_db_path)
    if not path.exists():
        raise FileNotFoundError(f"legacy stock pool db not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _quote_identifier(identifier: str) -> str:
    if not _IDENTIFIER_RE.match(identifier):
        raise ValueError(f"invalid SQL identifier: {identifier}")
    return f'"{identifier}"'


def _table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (TABLE_NAME,),
    ).fetchone()
    return row is not None


def _named_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection) -> dict[str, str]:
    columns: dict[str, str] = {}
    for row in conn.execute(f"PRAGMA table_info({_quote_identifier(TABLE_NAME)})"):
        name = str(row["name"])
        columns[name] = str(row["type"] or "")
    return columns


def _sqlite_type_for_value(value: Any) -> str:
    if isinstance(value, bool):
        return "INTEGER"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "REAL"
    return "TEXT"


def _sqlite_type_for_column(column: str, rows: list[dict[str, Any]]) -> str:
    if column in _BASE_COLUMNS:
        return _BASE_COLUMNS[column]
    for row in rows:
        value = row.get(column)
        if value is not None:
            return _sqlite_type_for_value(value)
    return "TEXT"


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _table_column_info(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {str(row["name"]): dict(row) for row in conn.execute(f"PRAGMA table_info({_quote_identifier(TABLE_NAME)})")}


def _fill_required_columns(row: dict[str, Any], column_info: dict[str, dict[str, Any]]) -> dict[str, Any]:
    completed = dict(row)
    now = ""
    for name, info in column_info.items():
        if name in completed:
            continue
        is_required = bool(info.get("notnull")) and not info.get("pk") and info.get("dflt_value") is None
        if not is_required:
            continue
        if name in {"created_at", "updated_at"}:
            if not now:
                now = _now_text()
            completed[name] = now
            continue
        raise ValueError(f"stock_daily_features column {name} is required but was not provided")
    return completed


def _validate_row_keys(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        for key in row:
            _quote_identifier(str(key))


def init_market_data_db(db_path: str | Path | None = None) -> None:
    with _connect(db_path) as conn:
        column_sql = ",\n                ".join(
            f"{_quote_identifier(name)} {definition}" for name, definition in _BASE_COLUMNS.items()
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_quote_identifier(TABLE_NAME)} (
                {column_sql},
                PRIMARY KEY(symbol, trade_date)
            )
            """
        )
        existing_columns = _table_columns(conn)
        for name, definition in _BASE_COLUMNS.items():
            if name in existing_columns:
                continue
            add_definition = definition.replace(" NOT NULL", "")
            conn.execute(
                f"ALTER TABLE {_quote_identifier(TABLE_NAME)} ADD COLUMN {_quote_identifier(name)} {add_definition}"
            )

        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_trade_date ON {_quote_identifier(TABLE_NAME)}(trade_date)"
        )


def _ensure_extra_columns(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> list[str]:
    existing = _table_columns(conn)
    added: list[str] = []
    for row in rows:
        for key, value in row.items():
            column = str(key)
            if column in existing:
                continue
            column_type = _sqlite_type_for_column(column, rows)
            conn.execute(
                f"ALTER TABLE {_quote_identifier(TABLE_NAME)} ADD COLUMN {_quote_identifier(column)} {column_type}"
            )
            existing[column] = column_type
            added.append(column)
    return added


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["symbol"] = normalize_symbol(normalized.get("symbol") or normalized.get("ts_code"))
    normalized["trade_date"] = str(normalized.get("trade_date") or "").strip()
    if not normalized["symbol"]:
        raise ValueError("stock_daily_features row missing valid symbol")
    if not normalized["trade_date"]:
        raise ValueError("stock_daily_features row missing trade_date")
    return normalized


def upsert_feature_rows(rows: list[dict[str, Any]], db_path: str | Path | None = None) -> dict[str, Any]:
    if not rows:
        init_market_data_db(db_path)
        return {"rows_written": 0, "columns_added": []}

    normalized_rows = [_normalize_row(row) for row in rows]
    _validate_row_keys(normalized_rows)
    init_market_data_db(db_path)

    with _connect(db_path) as conn:
        columns_added = _ensure_extra_columns(conn, normalized_rows)
        column_info = _table_column_info(conn)
        for row in normalized_rows:
            writable_row = _fill_required_columns(row, column_info)
            writable_columns = list(writable_row)
            placeholders = ", ".join("?" for _ in writable_columns)
            column_sql = ", ".join(_quote_identifier(column) for column in writable_columns)
            update_columns = [column for column in writable_columns if column not in {"symbol", "trade_date", "created_at"}]
            update_sql = ", ".join(
                f"{_quote_identifier(column)} = excluded.{_quote_identifier(column)}" for column in update_columns
            )
            if not update_sql:
                update_sql = "symbol = excluded.symbol"
            sql = f"""
                INSERT INTO {_quote_identifier(TABLE_NAME)} ({column_sql})
                VALUES ({placeholders})
                ON CONFLICT(symbol, trade_date) DO UPDATE SET {update_sql}
            """
            values = tuple(writable_row[column] for column in writable_columns)
            conn.execute(sql, values)
    return {"rows_written": len(normalized_rows), "columns_added": columns_added}


def _legacy_feature_rows(conn: sqlite3.Connection, batch_size: int) -> Iterable[list[dict[str, Any]]]:
    if not _named_table_exists(conn, TABLE_NAME):
        return
    offset = 0
    clean_batch_size = max(1, int(batch_size or 5000))
    while True:
        rows = conn.execute(
            f"""
            SELECT *
            FROM {_quote_identifier(TABLE_NAME)}
            ORDER BY symbol, trade_date
            LIMIT ? OFFSET ?
            """,
            (clean_batch_size, offset),
        ).fetchall()
        if not rows:
            break
        yield [dict(row) for row in rows]
        offset += len(rows)


def _active_template_universe_rows(conn: sqlite3.Connection) -> list[dict[str, str]]:
    if not _named_table_exists(conn, "stock_pool_template_stocks"):
        return []
    template_join = ""
    active_filter = ""
    if _named_table_exists(conn, "stock_pool_templates"):
        template_join = """
            JOIN stock_pool_templates t
              ON t.username = s.username
             AND t.template_name = s.template_name
        """
        active_filter = "WHERE COALESCE(t.is_active, 1) = 1"
    rows = conn.execute(
        f"""
        SELECT
            s.symbol AS symbol,
            MAX(COALESCE(NULLIF(s.ts_code, ''), '')) AS ts_code,
            MAX(COALESCE(NULLIF(s.stock_name, ''), '')) AS name
        FROM stock_pool_template_stocks s
        {template_join}
        {active_filter}
        GROUP BY s.symbol
        ORDER BY s.symbol
        """
    ).fetchall()
    result: list[dict[str, str]] = []
    for row in rows:
        symbol = normalize_symbol(row["symbol"])
        if not symbol:
            continue
        ts_code = str(row["ts_code"] or "").strip() or ts_code_from_symbol(symbol)
        name = str(row["name"] or "").strip()
        result.append({"symbol": symbol, "ts_code": ts_code, "name": name})
    return result


def _upsert_main_universe_rows(
    rows: list[dict[str, str]],
    db_path: str | Path | None,
    source: str,
) -> int:
    if not rows:
        init_main_universe_db(db_path)
        return 0
    now = _now_text()
    init_main_universe_db(db_path)
    with _connect(db_path) as conn:
        for row in rows:
            symbol = normalize_symbol(row.get("symbol"))
            if not symbol:
                continue
            ts_code = str(row.get("ts_code") or "").strip() or ts_code_from_symbol(symbol)
            name = str(row.get("name") or "").strip() or symbol
            conn.execute(
                """
                INSERT INTO main_stock_universe(symbol, ts_code, name, source, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    ts_code = excluded.ts_code,
                    name = CASE
                        WHEN excluded.name <> '' THEN excluded.name
                        ELSE main_stock_universe.name
                    END,
                    source = excluded.source,
                    is_active = 1,
                    updated_at = excluded.updated_at
                """,
                (symbol, ts_code, name, source, now, now),
            )
    return len({normalize_symbol(row.get("symbol")) for row in rows if normalize_symbol(row.get("symbol"))})


def migrate_legacy_stock_pool_to_market_data(
    legacy_db_path: str | Path | None = None,
    market_db_path: str | Path | None = None,
    source: str = "legacy_template_migration",
    batch_size: int = 5000,
) -> dict[str, Any]:
    legacy_path = _legacy_db_path(legacy_db_path)
    market_path = _db_path(market_db_path)
    feature_rows_copied = 0
    columns_added: set[str] = set()

    init_market_data_db(market_path)
    with _legacy_connect_existing(legacy_path) as legacy_conn:
        for batch in _legacy_feature_rows(legacy_conn, batch_size):
            result = upsert_feature_rows(batch, db_path=market_path)
            feature_rows_copied += int(result.get("rows_written") or 0)
            columns_added.update(str(item) for item in result.get("columns_added") or [])
        universe_rows = _active_template_universe_rows(legacy_conn)

    main_universe_rows_upserted = _upsert_main_universe_rows(universe_rows, market_path, source)
    return {
        "legacy_db_path": str(legacy_path),
        "market_db_path": str(market_path),
        "feature_rows_copied": feature_rows_copied,
        "columns_added": sorted(columns_added),
        "main_universe_rows_upserted": main_universe_rows_upserted,
    }


def _read_from_conn(
    conn: sqlite3.Connection,
    symbols: list[str],
    start_date: str = "",
    end_date: str = "",
) -> list[dict[str, Any]]:
    if not _table_exists(conn):
        return []

    clauses: list[str] = []
    params: list[Any] = []
    if symbols:
        placeholders = ", ".join("?" for _ in symbols)
        clauses.append(f"symbol IN ({placeholders})")
        params.extend(symbols)
    if start_date:
        clauses.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("trade_date <= ?")
        params.append(end_date)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT *
        FROM {_quote_identifier(TABLE_NAME)}
        {where_sql}
        ORDER BY trade_date, symbol
        """,
        params,
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["symbol"] = normalize_symbol(item.get("symbol"))
        result.append(item)
    return result


def _read_primary_rows(
    symbols: list[str],
    start_date: str,
    end_date: str,
    db_path: str | Path | None,
) -> list[dict[str, Any]]:
    conn = _connect_existing(db_path)
    if conn is None:
        return []
    try:
        return _read_from_conn(conn, symbols, start_date=start_date, end_date=end_date)
    finally:
        conn.close()


def _read_legacy_rows(
    symbols: list[str],
    start_date: str,
    end_date: str,
    legacy_db_path: Any = None,
) -> list[dict[str, Any]]:
    if legacy_db_path is DISABLE_LEGACY_FALLBACK:
        return []
    assert_sqlite_only_allowed("legacy stock pool feature fallback", str(_legacy_db_path(legacy_db_path)))
    path = _legacy_db_path(legacy_db_path)
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return _read_from_conn(conn, symbols, start_date=start_date, end_date=end_date)
    finally:
        conn.close()


def read_feature_rows(
    symbols: list[str],
    start_date: str = "",
    end_date: str = "",
    db_path: str | Path | None = None,
    legacy_db_path: Any = None,
) -> list[dict[str, Any]]:
    normalized_symbols = [symbol for symbol in (normalize_symbol(item) for item in symbols) if symbol]
    if not normalized_symbols:
        return []

    start = str(start_date or "").strip()
    end = str(end_date or "").strip()

    primary_rows = _read_primary_rows(normalized_symbols, start, end, db_path)
    legacy_rows = _read_legacy_rows(normalized_symbols, start, end, legacy_db_path)

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in legacy_rows:
        merged[(str(row.get("symbol") or ""), str(row.get("trade_date") or ""))] = row
    for row in primary_rows:
        merged[(str(row.get("symbol") or ""), str(row.get("trade_date") or ""))] = row
    return sorted(merged.values(), key=lambda row: (str(row.get("trade_date") or ""), str(row.get("symbol") or "")))


def read_feature_row(
    symbol: str,
    trade_date: str,
    db_path: str | Path | None = None,
    legacy_db_path: Any = None,
) -> dict[str, Any] | None:
    rows = read_feature_rows(
        [symbol],
        start_date=trade_date,
        end_date=trade_date,
        db_path=db_path,
        legacy_db_path=legacy_db_path,
    )
    return rows[0] if rows else None

# --- SQLite raw market-data inputs -------------------------------------------------
# The definitions below intentionally sit after the legacy feature-table helpers so
# existing callers keep working while new admin/scheduler tasks can split raw data
# collection from feature computation.
STOCK_BASIC_TABLE = "stock_basic"
DAILY_RAW_TABLE = "stock_daily_raw"
ADJ_FACTOR_TABLE = "stock_adj_factor"
STK_LIMIT_TABLE = "stock_stk_limit"
SUSPEND_TABLE = "stock_suspend_d"
DAILY_BASIC_TABLE = "stock_daily_basic"
TRADE_CALENDAR_TABLE = "trade_calendar"
MARKET_CONTEXT_TABLE = "market_context"

_STOCK_BASIC_COLUMNS: dict[str, str] = {
    "symbol": "TEXT NOT NULL",
    "ts_code": "TEXT NOT NULL",
    "name": "TEXT",
    "industry": "TEXT",
    "market": "TEXT",
    "list_date": "TEXT",
    "is_active": "INTEGER",
    "updated_at": "TEXT NOT NULL",
}
_DAILY_RAW_COLUMNS: dict[str, str] = {
    "symbol": "TEXT NOT NULL",
    "trade_date": "TEXT NOT NULL",
    "ts_code": "TEXT",
    "open": "REAL",
    "high": "REAL",
    "low": "REAL",
    "close": "REAL",
    "vol": "REAL",
    "amount": "REAL",
    "pre_close": "REAL",
    "change": "REAL",
    "pct_chg": "REAL",
    "created_at": "TEXT NOT NULL",
    "updated_at": "TEXT NOT NULL",
}
_ADJ_FACTOR_COLUMNS: dict[str, str] = {
    "symbol": "TEXT NOT NULL",
    "trade_date": "TEXT NOT NULL",
    "ts_code": "TEXT",
    "adj_factor": "REAL",
    "created_at": "TEXT NOT NULL",
    "updated_at": "TEXT NOT NULL",
}
_STK_LIMIT_COLUMNS: dict[str, str] = {
    "symbol": "TEXT NOT NULL",
    "trade_date": "TEXT NOT NULL",
    "ts_code": "TEXT",
    "up_limit": "REAL",
    "down_limit": "REAL",
    "created_at": "TEXT NOT NULL",
    "updated_at": "TEXT NOT NULL",
}
_SUSPEND_COLUMNS: dict[str, str] = {
    "symbol": "TEXT NOT NULL",
    "trade_date": "TEXT NOT NULL",
    "ts_code": "TEXT",
    "suspend_type": "TEXT",
    "suspend_timing": "TEXT",
    "created_at": "TEXT NOT NULL",
    "updated_at": "TEXT NOT NULL",
}
_DAILY_BASIC_COLUMNS: dict[str, str] = {
    "symbol": "TEXT NOT NULL",
    "trade_date": "TEXT NOT NULL",
    "ts_code": "TEXT",
    "close": "REAL",
    "total_mv": "REAL",
    "turnover_rate_f": "REAL",
    "pe_ttm": "REAL",
    "pb": "REAL",
    "created_at": "TEXT NOT NULL",
    "updated_at": "TEXT NOT NULL",
}
_TRADE_CALENDAR_COLUMNS: dict[str, str] = {
    "trade_date": "TEXT NOT NULL",
    "exchange": "TEXT",
    "is_open": "TEXT",
    "pretrade_date": "TEXT",
    "created_at": "TEXT NOT NULL",
    "updated_at": "TEXT NOT NULL",
}
_MARKET_CONTEXT_COLUMNS: dict[str, str] = {
    "trade_date": "TEXT NOT NULL",
    "created_at": "TEXT NOT NULL",
    "updated_at": "TEXT NOT NULL",
}


def _table_columns_for(conn: sqlite3.Connection, table_name: str) -> dict[str, str]:
    columns: dict[str, str] = {}
    for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})"):
        columns[str(row["name"])] = str(row["type"] or "")
    return columns


def _table_column_info_for(conn: sqlite3.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    return {str(row["name"]): dict(row) for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})")}


def _ensure_table(conn: sqlite3.Connection, table_name: str, columns: dict[str, str], primary_key: str) -> None:
    column_sql = ",\n                ".join(
        f"{_quote_identifier(name)} {definition}" for name, definition in columns.items()
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_quote_identifier(table_name)} (
            {column_sql},
            PRIMARY KEY({primary_key})
        )
        """
    )
    existing = _table_columns_for(conn, table_name)
    for name, definition in columns.items():
        if name in existing:
            continue
        conn.execute(
            f"ALTER TABLE {_quote_identifier(table_name)} ADD COLUMN {_quote_identifier(name)} {definition.replace(' NOT NULL', '')}"
        )


def init_market_data_db(db_path: str | Path | None = None) -> None:  # type: ignore[no-redef]
    with _connect(db_path) as conn:
        _ensure_table(conn, STOCK_BASIC_TABLE, _STOCK_BASIC_COLUMNS, "symbol")
        _ensure_table(conn, DAILY_RAW_TABLE, _DAILY_RAW_COLUMNS, "symbol, trade_date")
        _ensure_table(conn, ADJ_FACTOR_TABLE, _ADJ_FACTOR_COLUMNS, "symbol, trade_date")
        _ensure_table(conn, STK_LIMIT_TABLE, _STK_LIMIT_COLUMNS, "symbol, trade_date")
        _ensure_table(conn, SUSPEND_TABLE, _SUSPEND_COLUMNS, "symbol, trade_date")
        _ensure_table(conn, DAILY_BASIC_TABLE, _DAILY_BASIC_COLUMNS, "symbol, trade_date")
        _ensure_table(conn, TRADE_CALENDAR_TABLE, _TRADE_CALENDAR_COLUMNS, "trade_date")
        _ensure_table(conn, MARKET_CONTEXT_TABLE, _MARKET_CONTEXT_COLUMNS, "trade_date")
        _ensure_table(conn, TABLE_NAME, _BASE_COLUMNS, "symbol, trade_date")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_trade_date ON {_quote_identifier(TABLE_NAME)}(trade_date)")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{DAILY_RAW_TABLE}_trade_date ON {_quote_identifier(DAILY_RAW_TABLE)}(trade_date)")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{DAILY_BASIC_TABLE}_trade_date ON {_quote_identifier(DAILY_BASIC_TABLE)}(trade_date)")


def _normalize_ts_code_from_row(row: dict[str, Any]) -> tuple[str, str]:
    symbol = normalize_symbol(row.get("symbol") or row.get("ts_code"))
    if not symbol:
        raise ValueError("market data row missing valid symbol")
    ts_code = str(row.get("ts_code") or "").strip()
    if ts_code:
        suffix = ts_code.split(".", 1)[1] if "." in ts_code else ts_code_from_symbol(symbol).split(".", 1)[1]
        ts_code = f"{symbol}.{suffix}"
    else:
        ts_code = ts_code_from_symbol(symbol)
    return symbol, ts_code


def _normalize_symbol_date_row(row: dict[str, Any], *, require_symbol: bool = True) -> dict[str, Any]:
    normalized = dict(row)
    if require_symbol:
        symbol, ts_code = _normalize_ts_code_from_row(normalized)
        normalized["symbol"] = symbol
        normalized["ts_code"] = ts_code
    normalized["trade_date"] = str(normalized.get("trade_date") or normalized.get("cal_date") or "").strip()
    if not normalized["trade_date"]:
        raise ValueError("market data row missing trade_date")
    return normalized


def _ensure_extra_columns_for(
    conn: sqlite3.Connection,
    table_name: str,
    rows: list[dict[str, Any]],
    base_columns: dict[str, str],
) -> list[str]:
    existing = _table_columns_for(conn, table_name)
    added: list[str] = []
    for row in rows:
        for key, value in row.items():
            column = str(key)
            if column in existing:
                continue
            column_type = base_columns.get(column) or _sqlite_type_for_column(column, rows)
            conn.execute(f"ALTER TABLE {_quote_identifier(table_name)} ADD COLUMN {_quote_identifier(column)} {column_type}")
            existing[column] = column_type
            added.append(column)
    return added


def _upsert_rows(
    table_name: str,
    rows: list[dict[str, Any]],
    base_columns: dict[str, str],
    key_columns: tuple[str, ...],
    db_path: str | Path | None,
    *,
    require_symbol: bool = True,
) -> dict[str, Any]:
    init_market_data_db(db_path)
    if not rows:
        return {"rows_written": 0, "columns_added": []}
    now = _now_text()
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized = _normalize_symbol_date_row(row, require_symbol=require_symbol)
        normalized.setdefault("created_at", now)
        normalized["updated_at"] = now
        normalized_rows.append(normalized)
    _validate_row_keys(normalized_rows)
    with _connect(db_path) as conn:
        columns_added = _ensure_extra_columns_for(conn, table_name, normalized_rows, base_columns)
        column_info = _table_column_info_for(conn, table_name)
        for row in normalized_rows:
            writable_row = _fill_required_columns(row, column_info)
            writable_columns = list(writable_row)
            placeholders = ", ".join("?" for _ in writable_columns)
            column_sql = ", ".join(_quote_identifier(column) for column in writable_columns)
            key_set = set(key_columns)
            update_columns = [column for column in writable_columns if column not in key_set | {"created_at"}]
            update_sql = ", ".join(
                f"{_quote_identifier(column)} = excluded.{_quote_identifier(column)}" for column in update_columns
            ) or f"{_quote_identifier(key_columns[0])} = excluded.{_quote_identifier(key_columns[0])}"
            conflict_sql = ", ".join(_quote_identifier(column) for column in key_columns)
            conn.execute(
                f"""
                INSERT INTO {_quote_identifier(table_name)} ({column_sql})
                VALUES ({placeholders})
                ON CONFLICT({conflict_sql}) DO UPDATE SET {update_sql}
                """,
                tuple(writable_row[column] for column in writable_columns),
            )
    return {"rows_written": len(normalized_rows), "columns_added": columns_added}


def _read_symbol_rows(table_name: str, symbol: str, start_date: str, end_date: str, db_path: str | Path | None) -> list[dict[str, Any]]:
    normalized_symbol = normalize_symbol(symbol)
    if not normalized_symbol:
        return []
    conn = _connect_existing(db_path)
    if conn is None:
        return []
    try:
        if not _named_table_exists(conn, table_name):
            return []
        rows = conn.execute(
            f"""
            SELECT *
            FROM {_quote_identifier(table_name)}
            WHERE symbol = ? AND trade_date >= ? AND trade_date <= ?
            ORDER BY trade_date
            """,
            (normalized_symbol, str(start_date or ""), str(end_date or "99999999")),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _read_date_rows(table_name: str, start_date: str, end_date: str, db_path: str | Path | None) -> list[dict[str, Any]]:
    conn = _connect_existing(db_path)
    if conn is None:
        return []
    try:
        if not _named_table_exists(conn, table_name):
            return []
        rows = conn.execute(
            f"""
            SELECT *
            FROM {_quote_identifier(table_name)}
            WHERE trade_date >= ? AND trade_date <= ?
            ORDER BY trade_date
            """,
            (str(start_date or ""), str(end_date or "99999999")),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def upsert_stock_basic_rows(rows: list[dict[str, Any]], db_path: str | Path | None = None) -> dict[str, Any]:
    init_market_data_db(db_path)
    if not rows:
        return {"rows_written": 0, "columns_added": []}
    now = _now_text()
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized = dict(row)
        symbol, ts_code = _normalize_ts_code_from_row(normalized)
        normalized["symbol"] = symbol
        normalized["ts_code"] = ts_code
        normalized.setdefault("name", "")
        normalized.setdefault("industry", "")
        normalized.setdefault("market", "")
        normalized.setdefault("list_date", "")
        normalized.setdefault("is_active", 1)
        normalized["updated_at"] = now
        normalized_rows.append(normalized)
    _validate_row_keys(normalized_rows)
    with _connect(db_path) as conn:
        columns_added = _ensure_extra_columns_for(conn, STOCK_BASIC_TABLE, normalized_rows, _STOCK_BASIC_COLUMNS)
        for row in normalized_rows:
            writable_columns = list(row)
            placeholders = ", ".join("?" for _ in writable_columns)
            column_sql = ", ".join(_quote_identifier(column) for column in writable_columns)
            update_columns = [column for column in writable_columns if column != "symbol"]
            update_parts: list[str] = []
            for column in update_columns:
                quoted = _quote_identifier(column)
                if column in {"ts_code", "name", "industry", "market", "list_date"}:
                    update_parts.append(f"{quoted} = COALESCE(NULLIF(excluded.{quoted}, ''), {STOCK_BASIC_TABLE}.{quoted})")
                else:
                    update_parts.append(f"{quoted} = excluded.{quoted}")
            update_sql = ", ".join(update_parts)
            conn.execute(
                f"""
                INSERT INTO {_quote_identifier(STOCK_BASIC_TABLE)} ({column_sql})
                VALUES ({placeholders})
                ON CONFLICT(symbol) DO UPDATE SET {update_sql}
                """,
                tuple(row[column] for column in writable_columns),
            )
    return {"rows_written": len(normalized_rows), "columns_added": columns_added}


def read_stock_basic_rows(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    conn = _connect_existing(db_path)
    if conn is None:
        return []
    try:
        if not _named_table_exists(conn, STOCK_BASIC_TABLE):
            return []
        rows = conn.execute(
            f"""
            SELECT *
            FROM {_quote_identifier(STOCK_BASIC_TABLE)}
            WHERE COALESCE(is_active, 1) = 1
            ORDER BY symbol
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def upsert_daily_raw_rows(rows: list[dict[str, Any]], db_path: str | Path | None = None) -> dict[str, Any]:
    return _upsert_rows(DAILY_RAW_TABLE, rows, _DAILY_RAW_COLUMNS, ("symbol", "trade_date"), db_path)


def upsert_adj_factor_rows(rows: list[dict[str, Any]], db_path: str | Path | None = None) -> dict[str, Any]:
    return _upsert_rows(ADJ_FACTOR_TABLE, rows, _ADJ_FACTOR_COLUMNS, ("symbol", "trade_date"), db_path)


def upsert_stk_limit_rows(rows: list[dict[str, Any]], db_path: str | Path | None = None) -> dict[str, Any]:
    return _upsert_rows(STK_LIMIT_TABLE, rows, _STK_LIMIT_COLUMNS, ("symbol", "trade_date"), db_path)


def upsert_suspend_rows(rows: list[dict[str, Any]], db_path: str | Path | None = None) -> dict[str, Any]:
    return _upsert_rows(SUSPEND_TABLE, rows, _SUSPEND_COLUMNS, ("symbol", "trade_date"), db_path)


def upsert_daily_basic_rows(rows: list[dict[str, Any]], db_path: str | Path | None = None) -> dict[str, Any]:
    return _upsert_rows(DAILY_BASIC_TABLE, rows, _DAILY_BASIC_COLUMNS, ("symbol", "trade_date"), db_path)


def upsert_trade_calendar_rows(rows: list[dict[str, Any]], db_path: str | Path | None = None) -> dict[str, Any]:
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized = dict(row)
        normalized["trade_date"] = str(normalized.get("trade_date") or normalized.get("cal_date") or "").strip()
        normalized.setdefault("exchange", "")
        normalized.pop("cal_date", None)
        normalized_rows.append(normalized)
    return _upsert_rows(TRADE_CALENDAR_TABLE, normalized_rows, _TRADE_CALENDAR_COLUMNS, ("trade_date",), db_path, require_symbol=False)


def upsert_market_context_rows(rows: list[dict[str, Any]], db_path: str | Path | None = None) -> dict[str, Any]:
    return _upsert_rows(MARKET_CONTEXT_TABLE, rows, _MARKET_CONTEXT_COLUMNS, ("trade_date",), db_path, require_symbol=False)


def read_daily_raw_rows(symbol: str, start_date: str, end_date: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_symbol_rows(DAILY_RAW_TABLE, symbol, start_date, end_date, db_path)


def read_adj_factor_rows(symbol: str, start_date: str, end_date: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_symbol_rows(ADJ_FACTOR_TABLE, symbol, start_date, end_date, db_path)


def read_stk_limit_rows(symbol: str, start_date: str, end_date: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_symbol_rows(STK_LIMIT_TABLE, symbol, start_date, end_date, db_path)


def read_suspend_rows(symbol: str, start_date: str, end_date: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_symbol_rows(SUSPEND_TABLE, symbol, start_date, end_date, db_path)


def read_trade_calendar_rows(start_date: str, end_date: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    rows = _read_date_rows(TRADE_CALENDAR_TABLE, start_date, end_date, db_path)
    return [
        {
            "trade_date": str(row.get("trade_date") or ""),
            "exchange": str(row.get("exchange") or ""),
            "is_open": str(row.get("is_open") or ""),
            "pretrade_date": str(row.get("pretrade_date") or ""),
        }
        for row in rows
    ]


def read_market_context_rows(start_date: str, end_date: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_date_rows(MARKET_CONTEXT_TABLE, start_date, end_date, db_path)


def read_daily_basic_snapshot(trade_date: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_date_rows(DAILY_BASIC_TABLE, trade_date, trade_date, db_path)


def latest_daily_raw_dates(symbols: list[str], db_path: str | Path | None = None) -> dict[str, str]:
    normalized_symbols = [symbol for symbol in (normalize_symbol(item) for item in symbols) if symbol]
    if not normalized_symbols:
        return {}
    conn = _connect_existing(db_path)
    if conn is None:
        return {}
    try:
        if not _named_table_exists(conn, DAILY_RAW_TABLE):
            return {}
        placeholders = ", ".join("?" for _ in normalized_symbols)
        rows = conn.execute(
            f"""
            SELECT symbol, MAX(trade_date) AS latest_trade_date
            FROM {_quote_identifier(DAILY_RAW_TABLE)}
            WHERE symbol IN ({placeholders}) AND close IS NOT NULL AND close > 0
            GROUP BY symbol
            """,
            normalized_symbols,
        ).fetchall()
        return {str(row["symbol"]): str(row["latest_trade_date"] or "") for row in rows}
    finally:
        conn.close()
