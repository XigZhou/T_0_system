
from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .main_universe import DEFAULT_DB_PATH as DEFAULT_MARKET_DB_PATH
from .main_universe import MainUniverseSaveRequest, init_main_universe_db, save_main_universe
from .market_data_store import init_market_data_db
from .models import StockPoolTemplateSaveRequest
from .paper_trading import DEFAULT_PAPER_DB_PATH, init_paper_trading_db
from .scheduler import DEFAULT_DB_PATH as DEFAULT_SCHEDULER_DB_PATH
from .scheduler import init_scheduler_db
from .stock_pool_templates import DEFAULT_DB_PATH as DEFAULT_STOCK_POOL_DB_PATH
from .stock_pool_templates import DEFAULT_USERNAME, init_stock_pool_db, save_stock_pool_template

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SEED_SYMBOL = "601138"
SEED_TS_CODE = "601138.SH"
SEED_NAME = "\u5de5\u4e1a\u5bcc\u8054"
SEED_TEMPLATE_NAME = "SQLite\u521d\u59cb\u5316\u6d4b\u8bd5\u6c60"
SEED_ACCOUNT_ID = "sqlite_smoke_601138"
SEED_ACCOUNT_NAME = "SQLite\u4e3b\u94fe\u8def\u5de5\u4e1a\u5bcc\u8054\u6d4b\u8bd5\u8d26\u6237"

MARKET_RUNTIME_TABLES = ("stock_daily_features", "main_stock_universe")
STOCK_POOL_RUNTIME_TABLES = (
    "stock_pool_update_job_items",
    "stock_pool_update_jobs",
    "stock_daily_features",
    "stock_pool_template_stocks",
    "stock_pool_templates",
)
PAPER_RUNTIME_TABLES = (
    "paper_pending_orders",
    "paper_trades",
    "paper_holdings",
    "paper_assets",
    "paper_logs",
    "paper_config_snapshot",
    "paper_account_templates",
)
SCHEDULER_RUNTIME_TABLES = ("scheduler_job_runs", "scheduler_jobs")


@dataclass(frozen=True)
class RuntimeResetPaths:
    market_db_path: Path = DEFAULT_MARKET_DB_PATH
    stock_pool_db_path: Path = DEFAULT_STOCK_POOL_DB_PATH
    paper_db_path: Path = DEFAULT_PAPER_DB_PATH
    scheduler_db_path: Path = DEFAULT_SCHEDULER_DB_PATH
    backup_root: Path = PROJECT_ROOT / "data_store" / "backups"


def _now_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _delete_tables(db_path: Path, tables: tuple[str, ...], execute: bool) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not db_path.exists():
        return counts
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for table in tables:
            if not _table_exists(conn, table):
                counts[table] = 0
                continue
            count = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            counts[table] = count
            if execute:
                conn.execute(f'DELETE FROM "{table}"')
    return counts


def _backup_databases(paths: RuntimeResetPaths, timestamp: str, execute: bool) -> dict[str, str]:
    if not execute:
        return {}
    backup_dir = _resolve(paths.backup_root) / f"sqlite_soft_reset_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backups: dict[str, str] = {}
    for label, raw_path in {
        "market": paths.market_db_path,
        "stock_pool": paths.stock_pool_db_path,
        "paper": paths.paper_db_path,
        "scheduler": paths.scheduler_db_path,
    }.items():
        path = _resolve(raw_path)
        if not path.exists():
            continue
        target = backup_dir / path.name
        shutil.copy2(path, target)
        backups[label] = str(target)
    return backups


def _seed_main_universe(market_db_path: Path, execute: bool) -> dict[str, Any]:
    if not execute:
        return {"symbol": SEED_SYMBOL, "ts_code": SEED_TS_CODE, "name": SEED_NAME}
    init_main_universe_db(market_db_path)
    save_main_universe(
        MainUniverseSaveRequest(
            mode="replace",
            rows=[{"symbol": SEED_SYMBOL, "ts_code": SEED_TS_CODE, "name": SEED_NAME}],
            source="sqlite_soft_reset",
        ),
        db_path=market_db_path,
    )
    return {"symbol": SEED_SYMBOL, "ts_code": SEED_TS_CODE, "name": SEED_NAME}


def _seed_stock_pool_template(stock_pool_db_path: Path, execute: bool) -> dict[str, Any]:
    if not execute:
        return {"template_name": SEED_TEMPLATE_NAME, "symbol": SEED_SYMBOL}
    init_stock_pool_db(stock_pool_db_path)
    with sqlite3.connect(stock_pool_db_path) as conn:
        conn.execute(
            """
            INSERT INTO stock_basic(symbol, ts_code, name, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                ts_code=excluded.ts_code,
                name=excluded.name,
                updated_at=excluded.updated_at
            """,
            (SEED_SYMBOL, SEED_TS_CODE, SEED_NAME, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
    return save_stock_pool_template(
        StockPoolTemplateSaveRequest(
            username=DEFAULT_USERNAME,
            template_name=SEED_TEMPLATE_NAME,
            description="SQLite \u4e3b\u6570\u636e\u94fe\u8def\u521d\u59cb\u5316\u6d4b\u8bd5\u6a21\u677f\uff0c\u53ea\u5305\u542b\u5de5\u4e1a\u5bcc\u8054\u3002",
            stock_text=SEED_SYMBOL,
            is_active=True,
        ),
        db_path=stock_pool_db_path,
    )


def _seed_paper_account(stock_pool_db_path: Path, paper_db_path: Path, execute: bool) -> dict[str, Any]:
    if not execute:
        return {"account_id": SEED_ACCOUNT_ID, "account_name": SEED_ACCOUNT_NAME}
    init_paper_trading_db(paper_db_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(paper_db_path) as conn:
        conn.execute(
            """
            INSERT INTO paper_account_templates(
                template_id, username, account_id, account_name, initial_cash,
                stock_pool_username, stock_pool_template_name, stock_pool_db_path,
                buy_condition, sell_condition, score_expression, top_n, entry_offset,
                min_hold_days, max_hold_days, buy_quantity_mode, buy_shares, buy_lot_size,
                min_buy_amount, buy_min_close, buy_max_close, price_primary, price_fallback,
                price_field, skip_if_holding, skip_if_pending_order, strict_execution,
                buy_fee_rate, sell_fee_rate, stamp_tax_sell, slippage_bps, min_commission,
                raw_config_json, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                f"{DEFAULT_USERNAME}:{SEED_ACCOUNT_ID}",
                DEFAULT_USERNAME,
                SEED_ACCOUNT_ID,
                SEED_ACCOUNT_NAME,
                100000.0,
                DEFAULT_USERNAME,
                SEED_TEMPLATE_NAME,
                str(stock_pool_db_path),
                "m20 > -1",
                "m20 < -0.2",
                "m20",
                1,
                1,
                0,
                15,
                "\u56fa\u5b9a\u91d1\u989d",
                100,
                100,
                10000.0,
                0.0,
                500.0,
                "\u4e1c\u65b9\u8d22\u5bcc",
                "\u817e\u8baf\u80a1\u7968",
                "\u5f00\u76d8\u4ef7",
                1,
                1,
                1,
                0.00003,
                0.00003,
                0.0,
                3.0,
                0.0,
                "{}",
                now,
                now,
            ),
        )
    return {"account_id": SEED_ACCOUNT_ID, "account_name": SEED_ACCOUNT_NAME}


def soft_reset_runtime(
    paths: RuntimeResetPaths | None = None,
    execute: bool = False,
    timestamp: str | None = None,
    backup: bool = True,
) -> dict[str, Any]:
    resolved_paths = paths or RuntimeResetPaths()
    clean_paths = RuntimeResetPaths(
        market_db_path=_resolve(resolved_paths.market_db_path),
        stock_pool_db_path=_resolve(resolved_paths.stock_pool_db_path),
        paper_db_path=_resolve(resolved_paths.paper_db_path),
        scheduler_db_path=_resolve(resolved_paths.scheduler_db_path),
        backup_root=_resolve(resolved_paths.backup_root),
    )
    ts = timestamp or _now_timestamp()

    if execute:
        init_main_universe_db(clean_paths.market_db_path)
        init_market_data_db(clean_paths.market_db_path)
        init_stock_pool_db(clean_paths.stock_pool_db_path)
        init_paper_trading_db(clean_paths.paper_db_path)
        init_scheduler_db(clean_paths.scheduler_db_path)

    backups = _backup_databases(clean_paths, ts, execute and backup)
    cleared = {
        "market": _delete_tables(clean_paths.market_db_path, MARKET_RUNTIME_TABLES, execute),
        "stock_pool": _delete_tables(clean_paths.stock_pool_db_path, STOCK_POOL_RUNTIME_TABLES, execute),
        "paper": _delete_tables(clean_paths.paper_db_path, PAPER_RUNTIME_TABLES, execute),
        "scheduler": _delete_tables(clean_paths.scheduler_db_path, SCHEDULER_RUNTIME_TABLES, execute),
    }
    main_seed = _seed_main_universe(clean_paths.market_db_path, execute)
    template_seed = _seed_stock_pool_template(clean_paths.stock_pool_db_path, execute)
    account_seed = _seed_paper_account(clean_paths.stock_pool_db_path, clean_paths.paper_db_path, execute)

    return {
        "execute": bool(execute),
        "timestamp": ts,
        "paths": {
            "market_db_path": str(clean_paths.market_db_path),
            "stock_pool_db_path": str(clean_paths.stock_pool_db_path),
            "paper_db_path": str(clean_paths.paper_db_path),
            "scheduler_db_path": str(clean_paths.scheduler_db_path),
            "backup_root": str(clean_paths.backup_root),
        },
        "backup_enabled": bool(backup),
        "backups": backups,
        "cleared": cleared,
        "seeded_symbol": main_seed["symbol"],
        "seeded_ts_code": main_seed["ts_code"],
        "seeded_name": main_seed["name"],
        "seeded_template_name": SEED_TEMPLATE_NAME,
        "seeded_account_id": SEED_ACCOUNT_ID,
        "seeded_account_name": SEED_ACCOUNT_NAME,
        "template_seed": template_seed,
        "account_seed": account_seed,
    }


def summary_json(summary: dict[str, Any]) -> str:
    return json.dumps(summary, ensure_ascii=False, indent=2)
