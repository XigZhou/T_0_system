from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .market_data_store import DEFAULT_DB_PATH

ROW_TABLE = "sector_dashboard_rows"
META_TABLE = "sector_dashboard_meta"

DATASET_THEME_STRENGTH = "theme_strength"
DATASET_BOARD_STRENGTH = "board_strength"
DATASET_STOCK_EXPOSURE = "stock_exposure"
DATASET_MAPPING = "mapping"
DATASET_ERRORS = "errors"
DATASET_MARKET_CONTEXT = "market_context"

DATASET_TABLE_LABELS = {
    DATASET_THEME_STRENGTH: "sector_theme_strength_daily",
    DATASET_BOARD_STRENGTH: "sector_board_strength_daily",
    DATASET_STOCK_EXPOSURE: "sector_stock_theme_exposure",
    DATASET_MAPPING: "sector_theme_board_mapping",
    DATASET_ERRORS: "sector_research_errors",
    DATASET_MARKET_CONTEXT: "sector_market_context",
}


def _db_path(db_path: str | Path | None = None) -> Path:
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    return path


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_sector_dashboard_db(db_path: str | Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS {ROW_TABLE} (
                dataset TEXT NOT NULL,
                row_key TEXT NOT NULL,
                position INTEGER NOT NULL,
                row_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(dataset, row_key)
            );

            CREATE INDEX IF NOT EXISTS idx_{ROW_TABLE}_dataset_position
                ON {ROW_TABLE}(dataset, position);

            CREATE TABLE IF NOT EXISTS {META_TABLE} (
                meta_key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


def _json_default(value: Any) -> str:
    return str(value)


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in row.items()}


def _replace_dataset(conn: sqlite3.Connection, dataset: str, rows: list[dict[str, Any]], now: str) -> None:
    conn.execute(f"DELETE FROM {ROW_TABLE} WHERE dataset=?", (dataset,))
    for position, row in enumerate(rows):
        row_key = f"{position:010d}"
        conn.execute(
            f"""
            INSERT INTO {ROW_TABLE}(dataset, row_key, position, row_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (dataset, row_key, position, json.dumps(_clean_row(row), ensure_ascii=False, default=_json_default), now),
        )


def upsert_sector_dashboard_rows(
    *,
    db_path: str | Path | None = None,
    theme_strength_rows: list[dict[str, Any]] | None = None,
    board_strength_rows: list[dict[str, Any]] | None = None,
    stock_exposure_rows: list[dict[str, Any]] | None = None,
    mapping_rows: list[dict[str, Any]] | None = None,
    error_rows: list[dict[str, Any]] | None = None,
    market_context_rows: list[dict[str, Any]] | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_sector_dashboard_db(db_path)
    datasets = {
        DATASET_THEME_STRENGTH: theme_strength_rows or [],
        DATASET_BOARD_STRENGTH: board_strength_rows or [],
        DATASET_STOCK_EXPOSURE: stock_exposure_rows or [],
        DATASET_MAPPING: mapping_rows or [],
        DATASET_ERRORS: error_rows or [],
        DATASET_MARKET_CONTEXT: market_context_rows or [],
    }
    now = _now_text()
    with _connect(db_path) as conn:
        for dataset, rows in datasets.items():
            _replace_dataset(conn, dataset, rows, now)
        if summary is not None:
            conn.execute(
                f"""
                INSERT INTO {META_TABLE}(meta_key, value_json, updated_at)
                VALUES ('summary', ?, ?)
                ON CONFLICT(meta_key) DO UPDATE SET
                    value_json=excluded.value_json,
                    updated_at=excluded.updated_at
                """,
                (json.dumps(summary, ensure_ascii=False, default=_json_default), now),
            )
    return {
        "db_path": str(_db_path(db_path)),
        "rows_written": {dataset: len(rows) for dataset, rows in datasets.items()},
        "summary_written": summary is not None,
    }


def read_sector_dashboard_rows(db_path: str | Path | None = None) -> dict[str, Any]:
    init_sector_dashboard_db(db_path)
    datasets = {key: [] for key in DATASET_TABLE_LABELS}
    summary: dict[str, Any] = {}
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT dataset, row_json
            FROM {ROW_TABLE}
            ORDER BY dataset, position
            """
        ).fetchall()
        for row in rows:
            dataset = str(row["dataset"] or "")
            if dataset not in datasets:
                datasets[dataset] = []
            try:
                item = json.loads(str(row["row_json"] or "{}"))
            except json.JSONDecodeError:
                item = {}
            if isinstance(item, dict):
                datasets[dataset].append(item)
        meta = conn.execute(f"SELECT value_json FROM {META_TABLE} WHERE meta_key='summary'").fetchone()
        if meta is not None:
            try:
                loaded = json.loads(str(meta["value_json"] or "{}"))
                if isinstance(loaded, dict):
                    summary = loaded
            except json.JSONDecodeError:
                summary = {}
    return {"datasets": datasets, "summary": summary, "db_path": str(_db_path(db_path))}
