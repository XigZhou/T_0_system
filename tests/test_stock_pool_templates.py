from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from overnight_bt.models import StockPoolTemplateSaveRequest
from overnight_bt.market_data_store import read_stock_basic_rows, upsert_stock_basic_rows
from overnight_bt.main_universe import MainUniverseSaveRequest, init_main_universe_db, save_main_universe
from overnight_bt.stock_pool_feature_store import (
    StockPoolFeatureUpdateConfig,
    list_stock_pool_update_jobs,
    read_stock_pool_update_job,
    run_stock_daily_feature_computation,
    run_stock_daily_raw_collection,
    run_stock_pool_feature_update,
)
from overnight_bt.stock_pool_templates import (
    DEFAULT_USERNAME,
    delete_stock_pool_template,
    init_stock_pool_db,
    list_stock_pool_templates,
    read_stock_pool_template,
    read_template_symbols,
    save_stock_pool_template,
    seed_default_stock_pool_templates,
    validate_stock_pool_symbols,
)


class FakeStockPoolDataSource:
    dates = ["20240102", "20240103", "20240104", "20240105", "20240108"]
    stock_rows = [
        {
            "ts_code": "000001.SZ",
            "symbol": "000001",
            "name": "平安银行",
            "industry": "银行",
            "market": "主板",
            "list_date": "19910403",
        },
        {
            "ts_code": "000002.SZ",
            "symbol": "000002",
            "name": "万科A",
            "industry": "房地产",
            "market": "主板",
            "list_date": "19910129",
        },
        {
            "ts_code": "300750.SZ",
            "symbol": "300750",
            "name": "宁德时代",
            "industry": "电气设备",
            "market": "创业板",
            "list_date": "20180611",
        },
    ]

    def __init__(self, fail_daily_once: set[str] | None = None) -> None:
        self.fail_daily_once = set(fail_daily_once or set())
        self.daily_calls: list[str] = []
        self.daily_attempts: dict[str, int] = {}

    def latest_trade_date(self, end_date: str) -> str:
        return "20240108"

    def load_stock_basic(self) -> pd.DataFrame:
        return pd.DataFrame(self.stock_rows)

    def load_daily_basic_snapshot(self, trade_date: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"ts_code": row["ts_code"], "total_mv": 1000000.0, "turnover_rate_f": 1.5}
                for row in self.stock_rows
            ]
        )

    def load_trade_calendar(self, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame({"trade_date": self.dates, "is_open": ["1"] * len(self.dates)})

    def load_market_context(self, start_date: str, end_date: str) -> pd.DataFrame:
        rows = {"trade_date": self.dates}
        for alias in ["sh", "hs300", "cyb"]:
            rows[f"{alias}_open"] = [3000.0, 3010.0, 3020.0, 3030.0, 3040.0]
            rows[f"{alias}_close"] = [3010.0, 3020.0, 3030.0, 3040.0, 3050.0]
            rows[f"{alias}_m5"] = [None, None, None, None, 0.0133]
        return pd.DataFrame(rows)

    def load_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.daily_calls.append(ts_code)
        self.daily_attempts[ts_code] = self.daily_attempts.get(ts_code, 0) + 1
        if ts_code in self.fail_daily_once and self.daily_attempts[ts_code] == 1:
            raise RuntimeError(f"模拟 daily 首次失败：{ts_code}")
        return pd.DataFrame(
            {
                "ts_code": [ts_code] * len(self.dates),
                "trade_date": self.dates,
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "high": [101.0, 102.0, 103.0, 104.0, 106.0],
                "low": [99.0, 100.0, 101.0, 102.0, 103.0],
                "close": [100.0, 101.0, 102.0, 103.0, 105.0],
                "vol": [1000.0, 1100.0, 1200.0, 1300.0, 1500.0],
                "amount": [100000.0, 111100.0, 122400.0, 133900.0, 157500.0],
                "pre_close": [99.0, 100.0, 101.0, 102.0, 103.0],
                "change": [1.0, 1.0, 1.0, 1.0, 2.0],
                "pct_chg": [1.01, 1.0, 0.99, 0.98, 1.94],
            }
        )

    def load_adj_factor(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame({"ts_code": [ts_code] * len(self.dates), "trade_date": self.dates, "adj_factor": [1.0] * len(self.dates)})

    def load_stk_limit(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "ts_code": [ts_code] * len(self.dates),
                "trade_date": self.dates,
                "up_limit": [110.0, 111.1, 112.2, 113.3, 115.5],
                "down_limit": [90.0, 90.9, 91.8, 92.7, 94.5],
            }
        )

    def load_suspend_d(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame(columns=["ts_code", "trade_date", "suspend_type", "suspend_timing"])


class StockPoolTemplateTest(unittest.TestCase):
    def _insert_stock_basic(
        self,
        db_path: Path,
        symbol: str,
        name: str,
        ts_code: str | None = None,
    ) -> None:
        init_stock_pool_db(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO stock_basic(symbol, ts_code, name, updated_at)
                VALUES (?, ?, ?, '2024-01-01 00:00:00')
                ON CONFLICT(symbol) DO UPDATE SET
                    ts_code=excluded.ts_code,
                    name=excluded.name,
                    updated_at=excluded.updated_at
                """,
                (symbol, ts_code or f"{symbol}.SZ", name),
            )

    def test_validate_stock_list_normalizes_and_reports_errors(self) -> None:
        result = validate_stock_pool_symbols("300750\n600941.SH, 300750  abc 688981")
        self.assertEqual([row["symbol"] for row in result["valid_stocks"]], ["300750", "600941", "688981"])
        self.assertEqual(result["duplicate_symbols"], ["300750"])
        self.assertEqual(result["invalid_items"], ["abc(名称未匹配)"])
        self.assertEqual(result["valid_count"], 3)

    def test_validate_stock_list_against_main_universe_matches_save_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            market_db_path = Path(tmpdir) / "market_data.sqlite"
            catl_name = "\u5b81\u5fb7\u65f6\u4ee3"
            missing_name = "\u4e0d\u5b58\u5728\u516c\u53f8"
            save_main_universe(
                MainUniverseSaveRequest(mode="append", rows=[{"symbol": "300750", "name": catl_name}]),
                db_path=market_db_path,
            )

            result = validate_stock_pool_symbols(
                f"{catl_name}\n{missing_name}\n{catl_name}",
                main_universe_db_path=market_db_path,
            )

        self.assertEqual([row["symbol"] for row in result["valid_stocks"]], ["300750"])
        self.assertEqual(result["duplicate_symbols"], ["300750"])
        self.assertEqual(result["invalid_items"], [f"{missing_name}(\u4e0d\u5728\u4e3b\u80a1\u7968\u6c60)"])

    def test_save_read_delete_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock_pool.sqlite"
            init_stock_pool_db(db_path)
            saved = save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="手工测试股票池",
                    description="测试保存",
                    stock_text="300750\n600941\n688981",
                ),
                db_path=db_path,
            )
            self.assertIn("模板只保存股票集合", saved["message"])
            loaded = read_stock_pool_template("手工测试股票池", db_path=db_path)
            self.assertEqual(loaded["stock_count"], 3)
            self.assertEqual([row["symbol"] for row in loaded["stocks"]], ["300750", "600941", "688981"])
            self.assertTrue(loaded["is_active"])

            listed = list_stock_pool_templates(db_path=db_path)
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["template_name"], "手工测试股票池")

            deleted = delete_stock_pool_template("手工测试股票池", db_path=db_path)
            self.assertIn("主行情库数据保留", deleted["message"])
            self.assertEqual(list_stock_pool_templates(db_path=db_path), [])

    def test_read_template_symbols_missing_db_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "missing" / "stock_pool.sqlite"

            with self.assertRaises(FileNotFoundError):
                read_template_symbols(DEFAULT_USERNAME, "missing_template", db_path=db_path)

            self.assertFalse(db_path.exists())
            self.assertFalse(db_path.parent.exists())

    def test_save_template_rejects_stock_missing_from_main_universe_without_partial_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            market_db_path = base / "market_data.sqlite"
            catl_name = "\u5b81\u5fb7\u65f6\u4ee3"
            missing_name = "\u4e0d\u5b58\u5728\u516c\u53f8"
            self._insert_stock_basic(db_path, "300750", catl_name)
            self._insert_stock_basic(db_path, "000001", missing_name)
            save_main_universe(
                MainUniverseSaveRequest(mode="append", rows=[{"symbol": "300750", "name": catl_name}]),
                db_path=market_db_path,
            )

            with self.assertRaises(ValueError) as ctx:
                save_stock_pool_template(
                    StockPoolTemplateSaveRequest(
                        username=DEFAULT_USERNAME,
                        template_name="main_universe_validation_failed",
                        description="contains stock outside main universe",
                        stock_text=f"{catl_name}\n{missing_name}",
                    ),
                    db_path=db_path,
                    main_universe_db_path=market_db_path,
                )

            self.assertIn("\u4e0d\u5728\u4e3b\u80a1\u7968\u6c60", str(ctx.exception))
            with self.assertRaises(FileNotFoundError):
                read_stock_pool_template("main_universe_validation_failed", db_path=db_path)

    def test_save_template_accepts_active_main_universe_name_and_writes_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            market_db_path = base / "market_data.sqlite"
            catl_name = "\u5b81\u5fb7\u65f6\u4ee3"
            self._insert_stock_basic(db_path, "300750", catl_name)
            save_main_universe(
                MainUniverseSaveRequest(mode="append", rows=[{"symbol": "300750", "name": catl_name}]),
                db_path=market_db_path,
            )

            saved = save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="main_universe_validation_success",
                    description="only active main universe stock",
                    stock_text=catl_name,
                ),
                db_path=db_path,
                main_universe_db_path=market_db_path,
            )

            self.assertEqual([row["symbol"] for row in saved["template"]["stocks"]], ["300750"])

    def test_save_template_rejects_inactive_main_universe_stock(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            market_db_path = base / "market_data.sqlite"
            vanke_name = "\u4e07\u79d1A"
            self._insert_stock_basic(db_path, "000002", vanke_name)
            save_main_universe(
                MainUniverseSaveRequest(
                    mode="append",
                    rows=[
                        {"symbol": "300750", "name": "CATL"},
                        {"symbol": "000002", "name": vanke_name},
                    ],
                ),
                db_path=market_db_path,
            )
            with sqlite3.connect(market_db_path) as conn:
                conn.execute("UPDATE main_stock_universe SET is_active=0 WHERE symbol='000002'")

            with self.assertRaises(ValueError) as ctx:
                save_stock_pool_template(
                    StockPoolTemplateSaveRequest(
                        username=DEFAULT_USERNAME,
                        template_name="inactive_stock_pool",
                        description="contains inactive main universe stock",
                        stock_text=vanke_name,
                    ),
                    db_path=db_path,
                    main_universe_db_path=market_db_path,
                )

            self.assertIn("\u4e0d\u5728\u4e3b\u80a1\u7968\u6c60", str(ctx.exception))
            with self.assertRaises(FileNotFoundError):
                read_stock_pool_template("inactive_stock_pool", db_path=db_path)

    def test_strict_validation_failure_does_not_create_missing_template_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            market_db_path = base / "market_data.sqlite"
            save_main_universe(
                MainUniverseSaveRequest(mode="append", rows=[{"symbol": "300750", "name": "CATL"}]),
                db_path=market_db_path,
            )

            with self.assertRaises(ValueError) as ctx:
                save_stock_pool_template(
                    StockPoolTemplateSaveRequest(
                        username=DEFAULT_USERNAME,
                        template_name="strict_no_partial_db",
                        description="strict validation should fail before template db init",
                        stock_text="000001",
                    ),
                    db_path=db_path,
                    main_universe_db_path=market_db_path,
                )

            self.assertIn("\u4e0d\u5728\u4e3b\u80a1\u7968\u6c60", str(ctx.exception))
            self.assertFalse(db_path.exists())

    def test_strict_validation_missing_main_universe_db_does_not_create_any_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            market_db_path = base / "missing_market_data.sqlite"

            with self.assertRaises(ValueError) as ctx:
                save_stock_pool_template(
                    StockPoolTemplateSaveRequest(
                        username=DEFAULT_USERNAME,
                        template_name="missing_main_universe",
                        description="strict validation should not initialize databases",
                        stock_text="300750",
                    ),
                    db_path=db_path,
                    main_universe_db_path=market_db_path,
                )

            message = str(ctx.exception)
            self.assertTrue("\u4e3b\u80a1\u7968\u6c60\u5c1a\u672a\u521d\u59cb\u5316" in message or "\u7ef4\u62a4\u4e3b\u80a1\u7968\u6c60" in message)
            self.assertFalse(db_path.exists())
            self.assertFalse(market_db_path.exists())

    def test_strict_validation_resolves_name_from_main_universe_without_stock_basic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            market_db_path = base / "market_data.sqlite"
            main_only_name = "\u53ea\u9760\u4e3b\u6c60\u516c\u53f8"
            save_main_universe(
                MainUniverseSaveRequest(mode="append", rows=[{"symbol": "123456", "name": main_only_name}]),
                db_path=market_db_path,
            )

            saved = save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="main_universe_name_only",
                    description="name is resolved from main universe only",
                    stock_text=main_only_name,
                ),
                db_path=db_path,
                main_universe_db_path=market_db_path,
            )

            self.assertEqual([row["symbol"] for row in saved["template"]["stocks"]], ["123456"])
            self.assertEqual(saved["template"]["stocks"][0]["stock_name"], main_only_name)

    def test_rename_template_rewrites_stock_relations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock_pool.sqlite"
            save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="原股票池",
                    description="改名前",
                    stock_text="300750\n600941",
                ),
                db_path=db_path,
            )
            renamed = save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    original_template_name="原股票池",
                    template_name="新股票池",
                    description="改名后",
                    stock_text="688981\n600941",
                    overwrite_existing=True,
                ),
                db_path=db_path,
            )
            self.assertEqual(renamed["template"]["template_name"], "新股票池")
            self.assertEqual([row["symbol"] for row in renamed["template"]["stocks"]], ["688981", "600941"])
            self.assertEqual(read_stock_pool_template("新股票池", db_path=db_path)["stock_count"], 2)
            with self.assertRaises(FileNotFoundError):
                read_stock_pool_template("原股票池", db_path=db_path)

    def test_seed_default_templates_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock_pool.sqlite"
            first = seed_default_stock_pool_templates(db_path=db_path)
            second = seed_default_stock_pool_templates(db_path=db_path)
            templates = list_stock_pool_templates(db_path=db_path)
            self.assertGreaterEqual(first["created_count"], 0)
            self.assertEqual(second["created_count"], 0)
            self.assertEqual(len(templates), first["created_count"])
            names = {row["template_name"] for row in templates}
            expected = {
                "L0_最大市值主题股层",
                "L1_偏大市值主题股层",
                "L2_中等市值主题股层",
                "L3_偏小市值主题股层",
                "L4_最小市值主题股层",
                "当前多账户模拟股票池",
            }
            self.assertTrue(names.issubset(expected))


    def test_raw_collection_and_feature_computation_are_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            market_db_path = base / "market_data.sqlite"
            save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="split_pipeline_pool",
                    description="split raw and feature computation",
                    stock_text="300750",
                ),
                db_path=db_path,
            )
            collect_source = FakeStockPoolDataSource()
            collect = run_stock_daily_raw_collection(
                StockPoolFeatureUpdateConfig(
                    source="template",
                    job_type="raw_daily_collect",
                    username=DEFAULT_USERNAME,
                    template_name="split_pipeline_pool",
                    start_date="20240108",
                    end_date="20240108",
                    db_path=db_path,
                    market_db_path=market_db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                    force_full_rebuild=True,
                    only_missing=False,
                ),
                data_source=collect_source,
            )
            self.assertEqual(collect["status"], "success")
            self.assertEqual(collect_source.daily_calls, ["300750.SZ"])

            compute_source = FakeStockPoolDataSource()
            compute_source.load_daily = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("compute must read raw daily from SQLite"))
            compute = run_stock_daily_feature_computation(
                StockPoolFeatureUpdateConfig(
                    source="template",
                    job_type="feature_compute",
                    username=DEFAULT_USERNAME,
                    template_name="split_pipeline_pool",
                    start_date="20240108",
                    end_date="20240108",
                    db_path=db_path,
                    market_db_path=market_db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                    force_full_rebuild=True,
                    only_missing=False,
                ),
                data_source=compute_source,
            )
            self.assertEqual(compute["status"], "success")
            with sqlite3.connect(market_db_path) as conn:
                raw_count = conn.execute("SELECT COUNT(*) FROM stock_daily_raw WHERE symbol='300750'").fetchone()[0]
                feature_row = conn.execute(
                    "SELECT raw_close, close, m5 FROM stock_daily_features WHERE symbol='300750' AND trade_date='20240108'"
                ).fetchone()
            self.assertGreater(raw_count, 0)
            self.assertIsNotNone(feature_row)
            self.assertEqual(feature_row[0], 105.0)
            self.assertEqual(feature_row[1], 105.0)
            self.assertEqual(feature_row[2], 0.05)


    def test_raw_collection_all_source_uses_only_active_main_universe(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            market_db_path = base / "market_data.sqlite"
            save_main_universe(
                MainUniverseSaveRequest(
                    mode="replace",
                    source="unit_test",
                    rows=[
                        {"symbol": "300750", "ts_code": "300750.SZ", "name": "宁德时代"},
                        {"symbol": "000002", "ts_code": "000002.SZ", "name": "万科A"},
                    ],
                ),
                db_path=market_db_path,
            )
            with sqlite3.connect(market_db_path) as conn:
                conn.execute("UPDATE main_stock_universe SET is_active=0 WHERE symbol='000002'")

            source = FakeStockPoolDataSource()
            stock_basic_calls = {"count": 0}

            def fail_stock_basic() -> pd.DataFrame:
                stock_basic_calls["count"] += 1
                raise AssertionError("source=all must not load full-market stock_basic")

            source.load_stock_basic = fail_stock_basic
            summary = run_stock_daily_raw_collection(
                StockPoolFeatureUpdateConfig(
                    source="all",
                    job_type="raw_daily_collect",
                    start_date="20240108",
                    end_date="20240108",
                    db_path=db_path,
                    market_db_path=market_db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                    force_full_rebuild=True,
                    only_missing=False,
                ),
                data_source=source,
            )

            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["resolved_stock_count"], 1)
            self.assertEqual(summary["stock_count"], 1)
            self.assertEqual(source.daily_calls, ["300750.SZ"])
            self.assertEqual(stock_basic_calls["count"], 0)


    def test_raw_collection_all_source_preserves_existing_stock_basic_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            market_db_path = base / "market_data.sqlite"
            save_main_universe(
                MainUniverseSaveRequest(
                    mode="replace",
                    source="unit_test",
                    rows=[{"symbol": "300750", "ts_code": "300750.SZ", "name": "宁德时代"}],
                ),
                db_path=market_db_path,
            )
            upsert_stock_basic_rows(
                [
                    {
                        "symbol": "300750",
                        "ts_code": "300750.SZ",
                        "name": "宁德时代",
                        "industry": "电池",
                        "market": "创业板",
                        "list_date": "20180611",
                    }
                ],
                db_path=market_db_path,
            )

            source = FakeStockPoolDataSource()
            source.load_stock_basic = lambda: (_ for _ in ()).throw(AssertionError("source=all must not refresh full-market stock_basic"))
            summary = run_stock_daily_raw_collection(
                StockPoolFeatureUpdateConfig(
                    source="all",
                    job_type="raw_daily_collect",
                    start_date="20240108",
                    end_date="20240108",
                    db_path=db_path,
                    market_db_path=market_db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                    force_full_rebuild=True,
                    only_missing=False,
                ),
                data_source=source,
            )

            self.assertEqual(summary["status"], "success")
            row = {item["symbol"]: item for item in read_stock_basic_rows(db_path=market_db_path)}["300750"]
            self.assertEqual(row["industry"], "电池")
            self.assertEqual(row["market"], "创业板")
            self.assertEqual(row["list_date"], "20180611")


    def test_feature_computation_all_source_uses_active_main_universe_from_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            market_db_path = base / "market_data.sqlite"
            save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="all_source_sqlite_compute_pool",
                    description="collect through template, compute all source from SQLite stock_basic",
                    stock_text="300750",
                ),
                db_path=db_path,
            )
            collect = run_stock_daily_raw_collection(
                StockPoolFeatureUpdateConfig(
                    source="template",
                    job_type="raw_daily_collect",
                    username=DEFAULT_USERNAME,
                    template_name="all_source_sqlite_compute_pool",
                    start_date="20240108",
                    end_date="20240108",
                    db_path=db_path,
                    market_db_path=market_db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                    force_full_rebuild=True,
                    only_missing=False,
                ),
                data_source=FakeStockPoolDataSource(),
            )
            self.assertEqual(collect["status"], "success")
            save_main_universe(
                MainUniverseSaveRequest(
                    mode="replace",
                    source="unit_test",
                    rows=[{"symbol": "300750", "ts_code": "300750.SZ", "name": "宁德时代"}],
                ),
                db_path=market_db_path,
            )

            compute = run_stock_daily_feature_computation(
                StockPoolFeatureUpdateConfig(
                    source="all",
                    job_type="feature_compute",
                    start_date="20240108",
                    end_date="20240108",
                    db_path=db_path,
                    market_db_path=market_db_path,
                    log_dir=base / "logs",
                    max_symbols=1,
                    sleep_seconds=0.0,
                    force_full_rebuild=True,
                    only_missing=False,
                ),
                data_source=None,
            )

            self.assertEqual(compute["status"], "success")
            self.assertEqual(compute["stock_count"], 1)
            with sqlite3.connect(market_db_path) as conn:
                feature_row = conn.execute(
                    "SELECT raw_close, m5 FROM stock_daily_features WHERE symbol='300750' AND trade_date='20240108'"
                ).fetchone()
            self.assertEqual(feature_row[0], 105.0)
            self.assertEqual(feature_row[1], 0.05)

    def test_feature_store_update_writes_daily_features_and_job_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            market_db_path = base / "market_data.sqlite"
            log_dir = base / "logs"
            save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="数据入库测试池",
                    description="第二阶段测试",
                    stock_text="300750",
                ),
                db_path=db_path,
            )

            summary = run_stock_pool_feature_update(
                StockPoolFeatureUpdateConfig(
                    source="template",
                    job_type="manual_refresh",
                    username=DEFAULT_USERNAME,
                    template_name="数据入库测试池",
                    start_date="20240102",
                    end_date="20240108",
                    db_path=db_path,
                    market_db_path=market_db_path,
                    log_dir=log_dir,
                    sleep_seconds=0.0,
                ),
                data_source=FakeStockPoolDataSource(),
            )
            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["stock_count"], 1)
            self.assertEqual(summary["success_count"], 1)
            self.assertTrue(Path(summary["log_file"]).exists())
            self.assertTrue(Path(summary["item_csv"]).exists())
            self.assertTrue(Path(summary["summary_json"]).exists())

            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT symbol, trade_date, name, close, raw_close, m5, ma5, can_buy_t
                    FROM stock_daily_features
                    WHERE symbol='300750' AND trade_date='20240108'
                    """
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["name"], "宁德时代")
                self.assertAlmostEqual(row["close"], 105.0)
                self.assertAlmostEqual(row["raw_close"], 105.0)
                self.assertAlmostEqual(row["m5"], 0.05)
                self.assertAlmostEqual(row["ma5"], 102.2)
                self.assertEqual(row["can_buy_t"], 1)
                stored_job = conn.execute(
                    "SELECT log_file, item_csv, summary_json FROM stock_pool_update_jobs WHERE job_id=?",
                    (summary["job_id"],),
                ).fetchone()
                self.assertIn("log_file", stored_job.keys())
                self.assertTrue(stored_job["log_file"])
                self.assertTrue(stored_job["item_csv"])
                self.assertTrue(stored_job["summary_json"])

            jobs = list_stock_pool_update_jobs(db_path=db_path)
            self.assertEqual(jobs[0]["job_id"], summary["job_id"])
            detail = read_stock_pool_update_job(summary["job_id"], db_path=db_path)
            self.assertEqual(detail["status"], "success")
            self.assertEqual(detail["items"][0]["status"], "success")
            self.assertEqual(detail["items"][0]["rows_written"], 5)

            with sqlite3.connect(market_db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT symbol, trade_date, name, close, raw_close, m5, ma5, can_buy_t
                    FROM stock_daily_features
                    WHERE symbol='300750' AND trade_date='20240108'
                    """
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["name"], "宁德时代")
                self.assertAlmostEqual(row["close"], 105.0)
                self.assertAlmostEqual(row["raw_close"], 105.0)
                self.assertAlmostEqual(row["m5"], 0.05)
                self.assertAlmostEqual(row["ma5"], 102.2)
                self.assertEqual(row["can_buy_t"], 1)

    def test_feature_store_update_same_day_writes_only_target_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="单日测试池",
                    description="单日采集测试",
                    stock_text="300750",
                ),
                db_path=db_path,
            )
            source = FakeStockPoolDataSource()
            summary = run_stock_pool_feature_update(
                StockPoolFeatureUpdateConfig(
                    source="template",
                    job_type="manual_refresh",
                    username=DEFAULT_USERNAME,
                    template_name="单日测试池",
                    start_date="20240108",
                    end_date="20240108",
                    db_path=db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                    force_full_rebuild=True,
                    only_missing=False,
                ),
                data_source=source,
            )
            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["items"][0]["rows_written"], 1)
            with sqlite3.connect(db_path) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM stock_daily_features WHERE symbol='300750'"
                ).fetchone()[0]
                self.assertEqual(count, 1)

    def test_feature_store_update_supports_batch_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="批次测试池",
                    description="第二阶段批次测试",
                    stock_text="000001\n000002\n300750",
                ),
                db_path=db_path,
            )
            source = FakeStockPoolDataSource()
            summary = run_stock_pool_feature_update(
                StockPoolFeatureUpdateConfig(
                    source="template",
                    job_type="manual_refresh",
                    username=DEFAULT_USERNAME,
                    template_name="批次测试池",
                    start_date="20240102",
                    end_date="20240108",
                    db_path=db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                    batch_size=1,
                    batch_index=1,
                ),
                data_source=source,
            )
            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["resolved_stock_count"], 3)
            self.assertEqual(summary["due_stock_count"], 3)
            self.assertEqual(summary["stock_count"], 1)
            self.assertEqual(summary["batch_start"], 1)
            self.assertEqual(source.daily_calls, ["000002.SZ"])

            detail = read_stock_pool_update_job(summary["job_id"], db_path=db_path)
            self.assertEqual(detail["stock_count"], 1)
            self.assertEqual(detail["items"][0]["symbol"], "000002")

    def test_feature_store_update_skips_up_to_date_before_batching(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="只补缺失测试池",
                    description="第二阶段只补缺失测试",
                    stock_text="000001\n000002\n300750",
                ),
                db_path=db_path,
            )
            first_source = FakeStockPoolDataSource()
            first = run_stock_pool_feature_update(
                StockPoolFeatureUpdateConfig(
                    source="template",
                    job_type="manual_refresh",
                    username=DEFAULT_USERNAME,
                    template_name="只补缺失测试池",
                    start_date="20240102",
                    end_date="20240108",
                    db_path=db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                ),
                data_source=first_source,
            )
            self.assertEqual(first["stock_count"], 3)
            self.assertEqual(len(first_source.daily_calls), 3)

            second_source = FakeStockPoolDataSource()
            second = run_stock_pool_feature_update(
                StockPoolFeatureUpdateConfig(
                    source="template",
                    job_type="manual_refresh",
                    username=DEFAULT_USERNAME,
                    template_name="只补缺失测试池",
                    start_date="20240102",
                    end_date="20240108",
                    db_path=db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                ),
                data_source=second_source,
            )
            self.assertEqual(second["status"], "success")
            self.assertEqual(second["stock_count"], 0)
            self.assertEqual(second["prefilter_skipped_count"], 3)
            self.assertEqual(second["due_stock_count"], 0)
            self.assertEqual(second_source.daily_calls, [])

    def test_feature_store_update_include_up_to_date_refetches_latest_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="强制刷新测试池",
                    description="已最新仍需重采",
                    stock_text="300750",
                ),
                db_path=db_path,
            )
            first = run_stock_pool_feature_update(
                StockPoolFeatureUpdateConfig(
                    source="template",
                    job_type="manual_refresh",
                    username=DEFAULT_USERNAME,
                    template_name="强制刷新测试池",
                    start_date="20240102",
                    end_date="20240108",
                    db_path=db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                ),
                data_source=FakeStockPoolDataSource(),
            )
            self.assertEqual(first["status"], "success")

            source = FakeStockPoolDataSource()
            second = run_stock_pool_feature_update(
                StockPoolFeatureUpdateConfig(
                    source="template",
                    job_type="manual_refresh",
                    username=DEFAULT_USERNAME,
                    template_name="强制刷新测试池",
                    start_date="20240102",
                    end_date="20240108",
                    db_path=db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                    only_missing=False,
                ),
                data_source=source,
            )

            self.assertEqual(second["status"], "success")
            self.assertEqual(second["stock_count"], 1)
            self.assertEqual(second["skipped_count"], 0)
            self.assertEqual(second["items"][0]["status"], "success")
            self.assertEqual(source.daily_calls, ["300750.SZ"])

    def test_feature_store_update_can_use_main_universe_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            template_db = base / "stock_pool.sqlite"
            market_db = base / "market_data.sqlite"
            init_stock_pool_db(template_db)
            init_main_universe_db(market_db)
            save_main_universe(
                MainUniverseSaveRequest(
                    mode="replace",
                    rows=[
                        {"symbol": "300750", "ts_code": "300750.SZ", "name": "CATL"},
                        {"symbol": "000002", "ts_code": "000002.SZ", "name": "VankeA"},
                    ],
                    source="test",
                ),
                db_path=market_db,
            )
            with sqlite3.connect(market_db) as conn:
                conn.execute("UPDATE main_stock_universe SET is_active=0 WHERE symbol='000002'")

            source = FakeStockPoolDataSource()
            summary = run_stock_pool_feature_update(
                StockPoolFeatureUpdateConfig(
                    source="main_universe",
                    job_type="manual_refresh",
                    start_date="20240102",
                    end_date="20240108",
                    db_path=template_db,
                    market_db_path=market_db,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                ),
                data_source=source,
            )

            self.assertEqual(summary["status"], "success")
            self.assertEqual(source.daily_calls, ["300750.SZ"])
            with sqlite3.connect(market_db) as conn:
                active_count = conn.execute(
                    "SELECT COUNT(*) FROM stock_daily_features WHERE symbol='300750'"
                ).fetchone()[0]
                inactive_count = conn.execute(
                    "SELECT COUNT(*) FROM stock_daily_features WHERE symbol='000002'"
                ).fetchone()[0]
            self.assertGreater(active_count, 0)
            self.assertEqual(inactive_count, 0)

    def test_feature_store_update_with_temp_db_does_not_write_default_market_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            default_market_db_path = base / "default_market_data.sqlite"
            save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="隔离测试池",
                    description="临时库不写默认主库",
                    stock_text="300750",
                ),
                db_path=db_path,
            )

            with patch("overnight_bt.stock_pool_feature_store.DEFAULT_MARKET_DB_PATH", default_market_db_path):
                summary = run_stock_pool_feature_update(
                    StockPoolFeatureUpdateConfig(
                        source="template",
                        job_type="manual_refresh",
                        username=DEFAULT_USERNAME,
                        template_name="隔离测试池",
                        start_date="20240102",
                        end_date="20240108",
                        db_path=db_path,
                        log_dir=base / "logs",
                        sleep_seconds=0.0,
                    ),
                    data_source=FakeStockPoolDataSource(),
                )

            self.assertEqual(summary["status"], "success")
            self.assertFalse(default_market_db_path.exists())

    def test_feature_store_update_treats_empty_latest_row_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="空行情补数测试池",
                    description="最新日空行情需要重采",
                    stock_text="300750",
                ),
                db_path=db_path,
            )
            run_stock_pool_feature_update(
                StockPoolFeatureUpdateConfig(
                    source="template",
                    job_type="manual_refresh",
                    username=DEFAULT_USERNAME,
                    template_name="空行情补数测试池",
                    start_date="20240102",
                    end_date="20240108",
                    db_path=db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                ),
                data_source=FakeStockPoolDataSource(),
            )
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    UPDATE stock_daily_features
                    SET raw_open=NULL, raw_close=NULL, qfq_close=NULL, close=NULL, m20=NULL, m5=NULL, hs300_m5=NULL, can_buy_t=0, can_buy_open_t=0
                    WHERE symbol='300750' AND trade_date='20240108'
                    """
                )

            source = FakeStockPoolDataSource()
            second = run_stock_pool_feature_update(
                StockPoolFeatureUpdateConfig(
                    source="template",
                    job_type="manual_refresh",
                    username=DEFAULT_USERNAME,
                    template_name="空行情补数测试池",
                    start_date="20240102",
                    end_date="20240108",
                    db_path=db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                ),
                data_source=source,
            )

            self.assertEqual(second["status"], "success")
            self.assertEqual(second["stock_count"], 1)
            self.assertEqual(second["prefilter_skipped_count"], 0)
            self.assertEqual(source.daily_calls, ["300750.SZ"])
            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT raw_close, m5 FROM stock_daily_features WHERE symbol='300750' AND trade_date='20240108'"
                ).fetchone()
            self.assertEqual(row[0], 105.0)
            self.assertEqual(row[1], 0.05)

    def test_feature_store_update_retries_single_stock_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="重试测试池",
                    description="第二阶段重试测试",
                    stock_text="300750",
                ),
                db_path=db_path,
            )
            source = FakeStockPoolDataSource(fail_daily_once={"300750.SZ"})
            summary = run_stock_pool_feature_update(
                StockPoolFeatureUpdateConfig(
                    source="template",
                    job_type="manual_refresh",
                    username=DEFAULT_USERNAME,
                    template_name="重试测试池",
                    start_date="20240102",
                    end_date="20240108",
                    db_path=db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                    retry_attempts=2,
                    retry_sleep_seconds=0.0,
                ),
                data_source=source,
            )
            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["retry_attempts"], 2)
            self.assertEqual(source.daily_attempts["300750.SZ"], 2)
            self.assertEqual(summary["items"][0]["status"], "success")

    def test_feature_store_update_resume_after_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
            save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="续跑测试池",
                    description="第二阶段续跑测试",
                    stock_text="000001\n000002\n300750",
                ),
                db_path=db_path,
            )
            source = FakeStockPoolDataSource()
            summary = run_stock_pool_feature_update(
                StockPoolFeatureUpdateConfig(
                    source="template",
                    job_type="manual_refresh",
                    username=DEFAULT_USERNAME,
                    template_name="续跑测试池",
                    start_date="20240102",
                    end_date="20240108",
                    db_path=db_path,
                    log_dir=base / "logs",
                    sleep_seconds=0.0,
                    resume_after_symbol="000001",
                    max_symbols=1,
                ),
                data_source=source,
            )
            self.assertEqual(summary["status"], "success")
            self.assertEqual(summary["resume_skipped_count"], 1)
            self.assertEqual(source.daily_calls, ["000002.SZ"])


if __name__ == "__main__":
    unittest.main()
