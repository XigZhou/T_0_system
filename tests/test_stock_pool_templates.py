from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from overnight_bt.models import StockPoolTemplateSaveRequest
from overnight_bt.stock_pool_feature_store import (
    StockPoolFeatureUpdateConfig,
    list_stock_pool_update_jobs,
    read_stock_pool_update_job,
    run_stock_pool_feature_update,
)
from overnight_bt.stock_pool_templates import (
    DEFAULT_USERNAME,
    delete_stock_pool_template,
    init_stock_pool_db,
    list_stock_pool_templates,
    read_stock_pool_template,
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
    def test_validate_stock_list_normalizes_and_reports_errors(self) -> None:
        result = validate_stock_pool_symbols("300750\n600941.SH, 300750  abc 688981")
        self.assertEqual([row["symbol"] for row in result["valid_stocks"]], ["300750", "600941", "688981"])
        self.assertEqual(result["duplicate_symbols"], ["300750"])
        self.assertEqual(result["invalid_items"], ["abc"])
        self.assertEqual(result["valid_count"], 3)

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
            self.assertIn("第二阶段已支持行情与指标入库", saved["message"])
            loaded = read_stock_pool_template("手工测试股票池", db_path=db_path)
            self.assertEqual(loaded["stock_count"], 3)
            self.assertEqual([row["symbol"] for row in loaded["stocks"]], ["300750", "600941", "688981"])
            self.assertTrue(loaded["is_active"])

            listed = list_stock_pool_templates(db_path=db_path)
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["template_name"], "手工测试股票池")

            deleted = delete_stock_pool_template("手工测试股票池", db_path=db_path)
            self.assertIn("日线数据保留", deleted["message"])
            self.assertEqual(list_stock_pool_templates(db_path=db_path), [])

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

    def test_feature_store_update_writes_daily_features_and_job_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "stock_pool.sqlite"
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
