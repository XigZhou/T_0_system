from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data_store" / "market_data.sqlite"
LEGACY_STOCK_POOL_DB_PATH = PROJECT_ROOT / "data_store" / "stock_pool_templates.sqlite"


@dataclass
class MainUniverseSaveRequest:
    mode: Literal["append", "replace"]
    rows: list[dict[str, str]]
    source: str = "admin_upload"


def _db_path(db_path: str | Path | None = None) -> Path:
    return Path(db_path) if db_path is not None else DEFAULT_DB_PATH


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_existing(path: str | Path) -> sqlite3.Connection | None:
    db_path = Path(path)
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_symbol(symbol: object) -> str:
    text = str(symbol or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return ""
    if len(digits) <= 6:
        return digits.zfill(6)
    return digits[-6:].zfill(6)


def ts_code_from_symbol(symbol: object) -> str:
    normalized = normalize_symbol(symbol)
    if not normalized:
        return ""
    if normalized.startswith("6"):
        suffix = "SH"
    elif normalized.startswith(("4", "8", "9")):
        suffix = "BJ"
    else:
        suffix = "SZ"
    return f"{normalized}.{suffix}"


def init_main_universe_db(db_path: str | Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS main_stock_universe (
                symbol TEXT PRIMARY KEY,
                ts_code TEXT NOT NULL,
                name TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'admin_upload',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_main_stock_universe_name ON main_stock_universe(name)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_main_stock_universe_active ON main_stock_universe(is_active)"
        )


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _stock_basic_matches_in_conn(conn: sqlite3.Connection, name: str) -> list[dict[str, str]]:
    if not _table_exists(conn, "stock_basic"):
        return []
    columns = _table_columns(conn, "stock_basic")
    name_column = "name" if "name" in columns else "stock_name" if "stock_name" in columns else ""
    if not name_column:
        return []
    active_clause = ""
    params: list[Any] = [name]
    if "is_active" in columns:
        active_clause = " AND COALESCE(is_active, 1) = 1"
    rows = conn.execute(
        f"""
        SELECT symbol, ts_code, {name_column} AS name
        FROM stock_basic
        WHERE TRIM({name_column}) = ?{active_clause}
        ORDER BY symbol
        """,
        params,
    ).fetchall()
    matches: list[dict[str, str]] = []
    for row in rows:
        symbol = normalize_symbol(row["symbol"] or row["ts_code"])
        if not symbol:
            continue
        matches.append(
            {
                "name": str(row["name"] or "").strip(),
                "symbol": symbol,
                "ts_code": str(row["ts_code"] or ts_code_from_symbol(symbol)).strip() or ts_code_from_symbol(symbol),
            }
        )
    return matches


def _stock_basic_matches(conn: sqlite3.Connection, name: str, db_path: str | Path | None = None) -> list[dict[str, str]]:
    matches = _stock_basic_matches_in_conn(conn, name)
    if matches:
        return matches

    primary_path = _db_path(db_path).resolve()
    legacy_path = Path(LEGACY_STOCK_POOL_DB_PATH).resolve()
    if legacy_path == primary_path:
        return []

    legacy_conn = _connect_existing(legacy_path)
    if legacy_conn is None:
        return []
    try:
        return _stock_basic_matches_in_conn(legacy_conn, name)
    finally:
        legacy_conn.close()


def resolve_stock_names(names: list[str], db_path: str | Path | None = None) -> dict[str, Any]:
    init_main_universe_db(db_path)
    seen: set[str] = set()
    duplicate_inputs: list[str] = []
    unique_names: list[str] = []
    for raw_name in names:
        name = str(raw_name or "").strip()
        if not name:
            continue
        if name in seen:
            if name not in duplicate_inputs:
                duplicate_inputs.append(name)
            continue
        seen.add(name)
        unique_names.append(name)

    resolved: list[dict[str, str]] = []
    unresolved: list[str] = []
    ambiguous: list[dict[str, Any]] = []
    with _connect(db_path) as conn:
        for name in unique_names:
            matches = _stock_basic_matches(conn, name, db_path=db_path)
            if not matches:
                unresolved.append(name)
            elif len(matches) > 1:
                ambiguous.append({"name": name, "matches": matches})
            else:
                resolved.append(matches[0])
    return {
        "resolved": resolved,
        "unresolved": unresolved,
        "duplicate_inputs": duplicate_inputs,
        "ambiguous": ambiguous,
    }


def _row_to_resolved(
    row: dict[str, str],
    conn: sqlite3.Connection,
    db_path: str | Path | None = None,
) -> tuple[dict[str, str] | None, str | None, dict[str, Any] | None]:
    name = str(row.get("name") or row.get("stock_name") or "").strip()
    symbol = normalize_symbol(row.get("symbol") or row.get("stock_code") or row.get("ts_code"))
    ts_code = str(row.get("ts_code") or "").strip()
    if symbol:
        return {
            "name": name,
            "symbol": symbol,
            "ts_code": ts_code or ts_code_from_symbol(symbol),
        }, None, None
    if not name:
        return None, "", None
    matches = _stock_basic_matches(conn, name, db_path=db_path)
    if not matches:
        return None, name, None
    if len(matches) > 1:
        return None, None, {"name": name, "matches": matches}
    return matches[0], None, None


def save_main_universe(req: MainUniverseSaveRequest, db_path: str | Path | None = None) -> dict[str, Any]:
    if req.mode not in {"append", "replace"}:
        raise ValueError("mode must be append or replace")
    init_main_universe_db(db_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    saved: list[dict[str, str]] = []
    unresolved: list[str] = []
    ambiguous: list[dict[str, Any]] = []
    duplicate_inputs: list[str] = []
    seen_names: set[str] = set()
    seen_symbols: set[str] = set()

    with _connect(db_path) as conn:
        for row in req.rows:
            resolved, missing_name, ambiguous_item = _row_to_resolved(row, conn, db_path=db_path)
            if missing_name is not None:
                if missing_name:
                    unresolved.append(missing_name)
                continue
            if ambiguous_item is not None:
                ambiguous.append(ambiguous_item)
                continue
            assert resolved is not None
            input_name = str(row.get("name") or row.get("stock_name") or resolved["name"]).strip()
            if input_name in seen_names or resolved["symbol"] in seen_symbols:
                if input_name and input_name not in duplicate_inputs:
                    duplicate_inputs.append(input_name)
                continue
            seen_names.add(input_name)
            seen_symbols.add(resolved["symbol"])
            saved.append(resolved)

        if req.mode == "replace" and saved:
            placeholders = ",".join("?" for _ in saved)
            conn.execute(
                f"""
                UPDATE main_stock_universe
                SET is_active = 0, updated_at = ?
                WHERE symbol NOT IN ({placeholders})
                """,
                [now, *[row["symbol"] for row in saved]],
            )

        for row in saved:
            conn.execute(
                """
                INSERT INTO main_stock_universe(symbol, ts_code, name, source, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    ts_code = excluded.ts_code,
                    name = excluded.name,
                    source = excluded.source,
                    is_active = 1,
                    updated_at = excluded.updated_at
                """,
                (row["symbol"], row["ts_code"], row["name"], req.source, now, now),
            )

    return {
        "saved_count": len(saved),
        "saved": saved,
        "unresolved": unresolved,
        "duplicate_inputs": duplicate_inputs,
        "ambiguous": ambiguous,
    }


def list_main_universe(db_path: str | Path | None = None, include_inactive: bool = False) -> list[dict[str, Any]]:
    init_main_universe_db(db_path)
    where = "" if include_inactive else "WHERE is_active = 1"
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT symbol, ts_code, name, source, is_active, created_at, updated_at
            FROM main_stock_universe
            {where}
            ORDER BY is_active DESC, name, symbol
            """
        ).fetchall()
    return [dict(row) for row in rows]
