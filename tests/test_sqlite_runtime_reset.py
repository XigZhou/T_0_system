
from __future__ import annotations

import sqlite3
from pathlib import Path

from overnight_bt.main_universe import MainUniverseSaveRequest, init_main_universe_db, save_main_universe
from overnight_bt.market_data_store import init_market_data_db
from overnight_bt.models import StockPoolTemplateSaveRequest
from overnight_bt.paper_trading import init_paper_trading_db
from overnight_bt.scheduler import init_scheduler_db, record_run_start
from overnight_bt.sqlite_runtime_reset import RuntimeResetPaths, soft_reset_runtime
from overnight_bt.stock_pool_templates import init_stock_pool_db, save_stock_pool_template


def _count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0])


def _seed_databases(base: Path) -> RuntimeResetPaths:
    market_db = base / "market_data.sqlite"
    template_db = base / "stock_pool_templates.sqlite"
    paper_db = base / "paper_trading.sqlite"
    scheduler_db = base / "scheduler.sqlite"

    init_main_universe_db(market_db)
    init_market_data_db(market_db)
    save_main_universe(
        MainUniverseSaveRequest(
            mode="replace",
            rows=[{"symbol": "300750", "ts_code": "300750.SZ", "name": "\u5b81\u5fb7\u65f6\u4ee3"}],
            source="old",
        ),
        db_path=market_db,
    )
    with sqlite3.connect(market_db) as conn:
        conn.execute(
            "INSERT INTO stock_daily_features(symbol, trade_date, raw_close, close) VALUES('300750', '20240108', 100, 100)"
        )

    init_stock_pool_db(template_db)
    save_stock_pool_template(
        StockPoolTemplateSaveRequest(
            username="admin",
            template_name="old_template",
            stock_text="300750",
            description="old",
        ),
        db_path=template_db,
    )
    with sqlite3.connect(template_db) as conn:
        conn.execute(
            "INSERT INTO stock_daily_features(symbol, trade_date, raw_close, close, created_at, updated_at) VALUES('300750', '20240108', 100, 100, '2024-01-01', '2024-01-01')"
        )
        conn.execute(
            "INSERT INTO stock_pool_update_jobs(job_id, job_type, username, template_name, status, start_date, end_date, stock_count, created_at) VALUES('old-job', 'daily_update', 'admin', '', 'success', '20240101', '20240108', 1, '2024-01-01 00:00:00')"
        )
        conn.execute(
            "INSERT INTO stock_pool_update_job_items(job_id, symbol, status) VALUES('old-job', '300750', 'success')"
        )

    init_paper_trading_db(paper_db)
    with sqlite3.connect(paper_db) as conn:
        conn.execute(
            """
            INSERT INTO paper_account_templates(
                template_id, username, account_id, account_name, stock_pool_template_name,
                buy_condition, score_expression, created_at, updated_at
            ) VALUES('old-template', 'admin', 'old_account', 'old_account_name', 'old_template', 'm20>0', 'm20', '2024-01-01', '2024-01-01')
            """
        )
        conn.execute(
            "INSERT INTO paper_pending_orders(username, account_id, row_key, position, row_json, updated_at) VALUES('admin', 'old_account', 'old-order', 1, '{}', '2024-01-01')"
        )

    init_scheduler_db(scheduler_db)
    record_run_start("core_after_close_generate", target_date="20240108", db_path=scheduler_db)

    return RuntimeResetPaths(
        market_db_path=market_db,
        stock_pool_db_path=template_db,
        paper_db_path=paper_db,
        scheduler_db_path=scheduler_db,
        backup_root=base / "backups",
    )


def test_soft_reset_runtime_preserves_users_and_seeds_single_stock(tmp_path: Path) -> None:
    paths = _seed_databases(tmp_path)

    summary = soft_reset_runtime(paths=paths, execute=True, timestamp="20260523_130000")

    assert summary["execute"] is True
    assert summary["seeded_symbol"] == "601138"
    assert summary["seeded_template_name"] == "SQLite\u521d\u59cb\u5316\u6d4b\u8bd5\u6c60"
    assert summary["seeded_account_id"] == "sqlite_smoke_601138"
    for backup_path in summary["backups"].values():
        assert Path(backup_path).exists()

    with sqlite3.connect(paths.market_db_path) as conn:
        rows = conn.execute("SELECT symbol, ts_code, name, is_active FROM main_stock_universe").fetchall()
        assert rows == [("601138", "601138.SH", "\u5de5\u4e1a\u5bcc\u8054", 1)]
        assert conn.execute("SELECT COUNT(*) FROM stock_daily_features").fetchone()[0] == 0

    with sqlite3.connect(paths.stock_pool_db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE username='admin'").fetchone()[0] == 1
        templates = conn.execute("SELECT template_name FROM stock_pool_templates").fetchall()
        assert templates == [("SQLite\u521d\u59cb\u5316\u6d4b\u8bd5\u6c60",)]
        stocks = conn.execute("SELECT symbol, ts_code, stock_name FROM stock_pool_template_stocks").fetchall()
        assert stocks == [("601138", "601138.SH", "\u5de5\u4e1a\u5bcc\u8054")]
        assert conn.execute("SELECT COUNT(*) FROM stock_daily_features").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM stock_pool_update_jobs").fetchone()[0] == 0

    with sqlite3.connect(paths.paper_db_path) as conn:
        accounts = conn.execute(
            "SELECT account_id, account_name, stock_pool_template_name FROM paper_account_templates"
        ).fetchall()
        assert accounts == [("sqlite_smoke_601138", "SQLite\u4e3b\u94fe\u8def\u5de5\u4e1a\u5bcc\u8054\u6d4b\u8bd5\u8d26\u6237", "SQLite\u521d\u59cb\u5316\u6d4b\u8bd5\u6c60")]
        assert conn.execute("SELECT COUNT(*) FROM paper_pending_orders").fetchone()[0] == 0

    assert _count(paths.scheduler_db_path, "scheduler_job_runs") == 0
    assert _count(paths.scheduler_db_path, "scheduler_jobs") == 0


def test_soft_reset_runtime_dry_run_does_not_change_counts(tmp_path: Path) -> None:
    paths = _seed_databases(tmp_path)

    before_templates = _count(paths.stock_pool_db_path, "stock_pool_templates")
    before_universe = _count(paths.market_db_path, "main_stock_universe")
    summary = soft_reset_runtime(paths=paths, execute=False, timestamp="20260523_130000")

    assert summary["execute"] is False
    assert summary["backups"] == {}
    assert _count(paths.stock_pool_db_path, "stock_pool_templates") == before_templates
    assert _count(paths.market_db_path, "main_stock_universe") == before_universe


def test_soft_reset_runtime_can_skip_backup_when_space_is_limited(tmp_path: Path) -> None:
    paths = _seed_databases(tmp_path)

    summary = soft_reset_runtime(paths=paths, execute=True, timestamp="20260523_150000", backup=False)

    assert summary["execute"] is True
    assert summary["backup_enabled"] is False
    assert summary["backups"] == {}
    assert not (paths.backup_root / "sqlite_soft_reset_20260523_150000").exists()
    with sqlite3.connect(paths.market_db_path) as conn:
        rows = conn.execute("SELECT symbol, ts_code, name, is_active FROM main_stock_universe").fetchall()
    assert rows == [("601138", "601138.SH", "工业富联", 1)]
