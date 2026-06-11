from __future__ import annotations

import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd

from overnight_bt.main_universe import MainUniverseSaveRequest, save_main_universe
from overnight_bt.market_data_store import upsert_feature_rows
from overnight_bt.app import (
    admin_stock_indicator_compute_api,
    admin_stock_daily_collect_api,
    admin_stock_indicator_range_api,
    admin_stock_indicator_today_api,
    admin_stock_daily_range_api,
    admin_stock_daily_today_api,
    admin_page,
    daily_plan_api,
    daily_plan_page,
    export_backtest_api,
    export_backtest_table_api,
    portfolio_console_page,
    paper_template_api,
    paper_template_delete_api,
    paper_template_manager_page,
    paper_template_save_api,
    paper_trading_page,
    run_backtest_api,
    run_signal_quality_api,
    run_single_stock_api,
    single_stock_page,
    sector_research_page,
    stock_pool_template_delete_api,
    stock_pool_template_page,
    stock_pool_template_refresh_api,
    stock_pool_template_save_api,
    stock_pool_template_validate_api,
    stock_pool_update_job_api,
    stock_pool_update_jobs_api,
    users_page,
    sector_overview_api,
)
from overnight_bt.models import (
    AdminStockDataTaskRequest,
    BacktestRequest,
    DailyHolding,
    DailyPlanRequest,
    PaperTemplateSaveRequest,
    SignalQualityRequest,
    SingleStockBacktestRequest,
    StockPoolRefreshRequest,
    StockPoolTemplateSaveRequest,
    StockPoolValidateRequest,
)
from tests.helpers import make_processed_stock, write_stock_pool_db, write_stock_pool_template_symbols_db


class ApiIntegrationTest(unittest.TestCase):
    def assert_console_html(self, html: str) -> None:
        self.assertIn('<div id="root"></div>', html)
        self.assertIn('/static/console/assets/', html)
        self.assertIn('T_0 \u91cf\u5316\u63a7\u5236\u53f0', html)

    def test_console_page_routes_render_react_shell(self) -> None:
        with patch("overnight_bt.app.ensure_default_stock_pool_templates"):
            pages = [
                portfolio_console_page(),
                single_stock_page(),
                daily_plan_page(),
                paper_trading_page(),
                paper_template_manager_page(),
                stock_pool_template_page(),
                admin_page(),
                users_page(),
                sector_research_page(),
            ]
        for html in pages:
            self.assert_console_html(html)

    def test_sector_page_and_api_default_to_sqlite_source(self) -> None:
        self.assert_console_html(sector_research_page())

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("overnight_bt.app.BASE_DIR", Path(tmpdir)):
                body = sector_overview_api()
        self.assertEqual(body["status"], "empty")
        self.assertEqual(body["summary"]["source"], "sqlite")
        self.assertEqual(body["paths"]["storage"], "SQLite")

    def test_static_pages_render_when_default_template_initialization_is_locked(self) -> None:
        locked = sqlite3.OperationalError("database is locked")
        with patch("overnight_bt.app.ensure_default_stock_pool_templates", side_effect=locked):
            stock_pool_html = stock_pool_template_page()
            admin_html = admin_page()

        self.assert_console_html(stock_pool_html)
        self.assert_console_html(admin_html)

    def test_stock_pool_page_and_validation_api(self) -> None:
        self.assert_console_html(stock_pool_template_page())

        with tempfile.TemporaryDirectory() as tmpdir:
            market_db_path = Path(tmpdir) / "market_data.sqlite"
            save_main_universe(
                MainUniverseSaveRequest(
                    mode="append",
                    rows=[
                        {"symbol": "300750", "name": "CATL"},
                        {"symbol": "600941", "name": "CMCC"},
                    ],
                ),
                db_path=market_db_path,
            )
            with patch("overnight_bt.app.MAIN_UNIVERSE_DB_PATH", market_db_path):
                validation = stock_pool_template_validate_api(StockPoolValidateRequest(stock_text="300750 300750 xxx 600941"))
        self.assertEqual(validation["valid_count"], 2)
        self.assertEqual(validation["duplicate_symbols"], ["300750"])
        self.assertEqual(validation["invalid_items"], ["xxx(不在主股票池)"])

    def test_admin_page_and_stock_data_api(self) -> None:
        self.assert_console_html(admin_page())

        fake_summary = {"status": "success", "job_type": "admin_daily_collect", "stock_count": 0, "items": []}
        with patch("overnight_bt.app.ensure_default_stock_pool_templates") as seed_mock, patch(
            "overnight_bt.app.run_stock_daily_raw_collection", return_value=fake_summary
        ) as mocked:
            result = admin_stock_daily_collect_api(
                AdminStockDataTaskRequest(username="admin", start_date="20240108", end_date="20240108")
            )
            self.assertEqual(result["status"], "success")
            config = mocked.call_args.args[0]
            self.assertEqual(config.source, "all")
            self.assertTrue(config.force_full_rebuild)
            self.assertFalse(config.only_missing)
            seed_mock.assert_not_called()

        with patch("overnight_bt.app.ensure_default_stock_pool_templates"), patch(
            "overnight_bt.app.run_stock_daily_feature_computation", return_value={**fake_summary, "job_type": "admin_indicator_compute"}
        ) as mocked:
            admin_stock_indicator_compute_api(
                AdminStockDataTaskRequest(username="admin", start_date="20240108", end_date="20240108")
            )
            self.assertEqual(mocked.call_args.args[0].job_type, "admin_indicator_compute")

    def test_admin_stock_data_today_and_range_wrappers_bind_dates_and_job_type(self) -> None:
        fake_summary = {"status": "success", "stock_count": 0, "items": []}
        cases = [
            (
                admin_stock_daily_today_api,
                "run_stock_daily_raw_collection",
                AdminStockDataTaskRequest(username="admin", start_date="20240101", end_date="20240131"),
                "admin_daily_collect_today",
                "20260523",
                "20260523",
            ),
            (
                admin_stock_indicator_today_api,
                "run_stock_daily_feature_computation",
                AdminStockDataTaskRequest(username="admin", start_date="20240101", end_date="20240131"),
                "admin_indicator_compute_today",
                "20260523",
                "20260523",
            ),
            (
                admin_stock_daily_range_api,
                "run_stock_daily_raw_collection",
                AdminStockDataTaskRequest(username="admin", start_date="20240108", end_date="20240112"),
                "admin_daily_collect_range",
                "20240108",
                "20240112",
            ),
            (
                admin_stock_indicator_range_api,
                "run_stock_daily_feature_computation",
                AdminStockDataTaskRequest(username="admin", start_date="20240108", end_date="20240112"),
                "admin_indicator_compute_range",
                "20240108",
                "20240112",
            ),
        ]
        for endpoint, runner_name, request, expected_job_type, expected_start, expected_end in cases:
            with self.subTest(job_type=expected_job_type), patch(
                "overnight_bt.app._today_yyyymmdd", return_value="20260523"
            ), patch(f"overnight_bt.app.{runner_name}", return_value={**fake_summary, "job_type": expected_job_type}) as mocked:
                result = endpoint(request, current_user={"username": "admin", "role": "admin"})

            self.assertEqual(result["status"], "success")
            config = mocked.call_args.args[0]
            self.assertEqual(config.source, "all")
            self.assertEqual(config.job_type, expected_job_type)
            self.assertEqual(config.start_date, expected_start)
            self.assertEqual(config.end_date, expected_end)
            self.assertTrue(config.force_full_rebuild)
            self.assertFalse(config.only_missing)

    def test_admin_stock_data_http_api_binds_json_body(self) -> None:
        from fastapi.testclient import TestClient
        from overnight_bt import app as app_module

        fake_summary = {"status": "success", "job_type": "admin_daily_collect", "stock_count": 0, "items": []}
        app_module.app.dependency_overrides[app_module.auth.require_user] = lambda: app_module._direct_user()
        try:
            client = TestClient(app_module.app)
            with patch("overnight_bt.app.ensure_default_stock_pool_templates"), patch(
                "overnight_bt.app.run_stock_daily_raw_collection", return_value=fake_summary
            ) as mocked:
                response = client.post(
                    "/api/admin/stock-data/daily",
                    json={"username": "admin", "start_date": "20240108", "end_date": "20240108"},
                )
        finally:
            app_module.app.dependency_overrides.pop(app_module.auth.require_user, None)

        self.assertEqual(response.status_code, 200, msg=response.text)
        self.assertEqual(response.json()["status"], "success")
        config = mocked.call_args.args[0]
        self.assertEqual(config.job_type, "admin_daily_collect")
        self.assertEqual(config.start_date, "20240108")
        self.assertEqual(config.end_date, "20240108")

    def test_admin_stock_data_today_and_range_http_api_bind_json_body(self) -> None:
        from fastapi.testclient import TestClient
        from overnight_bt import app as app_module

        fake_summary = {"status": "success", "stock_count": 0, "items": []}
        app_module.app.dependency_overrides[app_module.auth.require_user] = lambda: app_module._direct_user()
        try:
            client = TestClient(app_module.app)
            with patch("overnight_bt.app._today_yyyymmdd", return_value="20260523"), patch(
                "overnight_bt.app.run_stock_daily_raw_collection", return_value=fake_summary
            ) as daily_mock, patch(
                "overnight_bt.app.run_stock_daily_feature_computation", return_value=fake_summary
            ) as indicator_mock:
                today_response = client.post(
                    "/api/admin/stock-data/daily/today",
                    json={"username": "admin", "start_date": "20240108", "end_date": "20240112"},
                )
                today_config = daily_mock.call_args.args[0]
                range_response = client.post(
                    "/api/admin/stock-data/indicators/range",
                    json={"username": "admin", "start_date": "20240108", "end_date": "20240112"},
                )
                range_config = indicator_mock.call_args.args[0]
        finally:
            app_module.app.dependency_overrides.pop(app_module.auth.require_user, None)

        self.assertEqual(today_response.status_code, 200, msg=today_response.text)
        self.assertEqual(range_response.status_code, 200, msg=range_response.text)
        self.assertEqual(today_config.job_type, "admin_daily_collect_today")
        self.assertEqual(today_config.start_date, "20260523")
        self.assertEqual(today_config.end_date, "20260523")
        self.assertEqual(range_config.job_type, "admin_indicator_compute_range")
        self.assertEqual(range_config.start_date, "20240108")
        self.assertEqual(range_config.end_date, "20240112")

    def test_admin_operations_http_api_exposes_overview_scheduler_and_universe(self) -> None:
        from fastapi.testclient import TestClient
        from overnight_bt import app as app_module
        from overnight_bt.scheduler import record_run_end, record_run_start

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            market_db_path = base / "market_data.sqlite"
            scheduler_db_path = base / "scheduler.sqlite"
            save_main_universe(
                MainUniverseSaveRequest(
                    mode="append",
                    rows=[{"symbol": "000001", "name": "平安银行"}],
                ),
                db_path=market_db_path,
            )
            failed_run = record_run_start("daily_sync", target_date="20260521", db_path=scheduler_db_path)
            record_run_end(failed_run["run_id"], "failed", failed_stage="sync", error_summary="同步失败", db_path=scheduler_db_path)

            app_module.app.dependency_overrides[app_module.auth.require_user] = lambda: app_module._direct_user()
            try:
                with (
                    patch("overnight_bt.app.MAIN_UNIVERSE_DB_PATH", market_db_path),
                    patch("overnight_bt.app.SCHEDULER_DB_PATH", scheduler_db_path),
                ):
                    client = TestClient(app_module.app)
                    overview_response = client.get("/api/admin/overview")
                    runs_response = client.get("/api/admin/scheduler/runs")
                    universe_response = client.get("/api/admin/main-universe")
            finally:
                app_module.app.dependency_overrides.pop(app_module.auth.require_user, None)

        self.assertEqual(overview_response.status_code, 200, msg=overview_response.text)
        overview = overview_response.json()
        self.assertIn("scheduler", overview)
        self.assertIn("core_tasks", overview)
        self.assertIn("daily_sync", overview["core_tasks"])
        self.assertEqual(runs_response.status_code, 200, msg=runs_response.text)
        self.assertIsInstance(runs_response.json().get("runs"), list)
        self.assertEqual(universe_response.status_code, 200, msg=universe_response.text)
        universe = universe_response.json()
        self.assertEqual(universe["count"], 1)
        self.assertEqual(universe["rows"][0]["symbol"], "000001")

    def test_admin_operations_page_uses_console_shell(self) -> None:
        self.assert_console_html(admin_page())

    def test_admin_scheduler_retry_http_rejects_non_failed_runs(self) -> None:
        from fastapi.testclient import TestClient
        from overnight_bt import app as app_module
        from overnight_bt.scheduler import record_run_start

        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler_db_path = Path(tmpdir) / "scheduler.sqlite"
            success_run = record_run_start("daily_sync", target_date="20260521", status="success", db_path=scheduler_db_path)
            app_module.app.dependency_overrides[app_module.auth.require_user] = lambda: app_module._direct_user()
            try:
                with patch("overnight_bt.app.SCHEDULER_DB_PATH", scheduler_db_path):
                    client = TestClient(app_module.app)
                    response = client.post(f"/api/admin/scheduler/runs/{success_run['run_id']}/retry", json={"reason": "pytest"})
            finally:
                app_module.app.dependency_overrides.pop(app_module.auth.require_user, None)

        self.assertEqual(response.status_code, 400, msg=response.text)
        self.assertIn("只有失败", response.json()["detail"])

    def test_main_universe_save_normalizes_exchange_suffix_from_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "market_data.sqlite"
            result = save_main_universe(
                MainUniverseSaveRequest(
                    mode="append",
                    rows=[{"symbol": "000001.SZ", "name": "Ping An Bank"}],
                ),
                db_path=db_path,
            )

        self.assertEqual(result["saved_count"], 1)
        self.assertEqual(result["saved"][0]["symbol"], "000001")
        self.assertEqual(result["saved"][0]["ts_code"], "000001.SZ")

    def test_stock_pool_template_api_save_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            market_db_path = Path(tmpdir) / "market_data.sqlite"
            template_db_path = Path(tmpdir) / "stock_pool.sqlite"
            save_main_universe(
                MainUniverseSaveRequest(
                    mode="append",
                    rows=[
                        {"symbol": "300750", "name": "CATL"},
                        {"symbol": "600941", "name": "CMCC"},
                    ],
                ),
                db_path=market_db_path,
            )

            with (
                patch("overnight_bt.app.MAIN_UNIVERSE_DB_PATH", market_db_path),
                patch("overnight_bt.stock_pool_templates.DEFAULT_DB_PATH", template_db_path),
            ):
                saved = stock_pool_template_save_api(
                    StockPoolTemplateSaveRequest(
                        username="api_test_user",
                        template_name="API_STOCK_POOL",
                        description="api test",
                        stock_text="300750\n600941",
                    )
                )
                self.assertEqual(saved["template"]["stock_count"], 2)
                self.assertIn("模板只保存股票集合", saved["message"])
                deleted = stock_pool_template_delete_api(template_name="API_STOCK_POOL", username="api_test_user")
                self.assertIn("主行情库数据保留", deleted["message"])


    def test_stock_pool_admin_only_update_apis_reject_non_admin(self) -> None:
        with self.assertRaises(Exception) as jobs_ctx:
            stock_pool_update_jobs_api(limit=5, username="normal_user")
        self.assertEqual(getattr(jobs_ctx.exception, "status_code", None), 403)

        with self.assertRaises(Exception) as detail_ctx:
            stock_pool_update_job_api(job_id="missing", username="normal_user")
        self.assertEqual(getattr(detail_ctx.exception, "status_code", None), 403)

        with self.assertRaises(Exception) as refresh_ctx:
            stock_pool_template_refresh_api(
                StockPoolRefreshRequest(
                    username="normal_user",
                    source="template",
                    template_name="任意模板",
                    max_symbols=1,
                )
            )
        self.assertEqual(getattr(refresh_ctx.exception, "status_code", None), 403)

    def test_stock_pool_legacy_refresh_api_marks_response(self) -> None:
        fake_summary = {"status": "success", "job_type": "manual_refresh", "stock_count": 0, "items": []}
        with patch("overnight_bt.app.run_stock_pool_feature_update", return_value=fake_summary) as mocked:
            result = stock_pool_template_refresh_api(
                StockPoolRefreshRequest(
                    username="admin",
                    source="template",
                    template_name="legacy_template",
                    max_symbols=1,
                )
            )

        self.assertTrue(result["legacy"])
        self.assertEqual(result["status"], "success")
        config = mocked.call_args.args[0]
        self.assertEqual(config.source, "template")
        self.assertEqual(config.template_name, "legacy_template")

    def test_stock_pool_update_job_api_returns_existing_jobs(self) -> None:
        jobs = stock_pool_update_jobs_api(limit=5)
        self.assertIn("jobs", jobs)
        if jobs["jobs"]:
            detail = stock_pool_update_job_api(jobs["jobs"][0]["job_id"])
            self.assertIn("items", detail)

    def test_paper_template_api_save_read_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_dir = base / "configs" / "paper_accounts"
            stock = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m20": 0.8, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "接口股票池", [stock])
            saved = paper_template_save_api(
                PaperTemplateSaveRequest(
                    config_dir=str(config_dir),
                    file_name="api_editor.yaml",
                    account_id="API账户",
                    account_name="API模拟账户",
                    stock_pool_username="admin",
                    stock_pool_template_name="接口股票池",
                    stock_pool_db_path=str(db_path),
                    buy_condition="m20>0",
                    score_expression="m20",
                    ledger_path=str(base / "paper_trading" / "accounts" / "api_editor.xlsx"),
                    log_dir=str(base / "paper_trading" / "logs"),
                )
            )

            config_path = saved["template"]["config_path"]
            loaded = paper_template_api(config_path=config_path, config_dir=str(config_dir))
            self.assertEqual(loaded["account_name"], "API模拟账户")
            self.assertEqual(loaded["stock_pool_template_name"], "接口股票池")
            deleted = paper_template_delete_api(config_path=config_path, config_dir=str(config_dir))
            self.assertIn("SQLite 账本数据保留", deleted["message"])

    def test_api_run_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m5": 0.3, "m20": 0.8, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 10.5, "raw_high": 10.6, "raw_low": 10.4, "raw_close": 10.5, "m5": 0.1, "m20": 0.7, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240104", "raw_open": 10.8, "raw_high": 10.9, "raw_low": 10.7, "raw_close": 10.8, "m5": 0.0, "m20": 0.6, "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            template_db = write_stock_pool_template_symbols_db(
                base / "stock_pool.sqlite",
                "api_pool",
                [{"symbol": "000001", "stock_name": "Alpha Bank"}],
                username="api_user",
            )
            market_db = base / "market_data.sqlite"
            upsert_feature_rows(stock.to_dict("records"), db_path=market_db)
            payload = BacktestRequest(
                data_source="stock_pool",
                processed_dir="",
                stock_pool_username="api_user",
                stock_pool_template_name="api_pool",
                stock_pool_db_path=str(template_db),
                stock_pool_market_db_path=str(market_db),
                start_date="20240102",
                end_date="20240102",
                buy_condition="m20>0",
                score_expression="m20 + m5",
                top_n=1,
                initial_cash=100000.0,
                per_trade_budget=10000.0,
                lot_size=100,
                buy_fee_rate=0.0,
                sell_fee_rate=0.0,
                stamp_tax_sell=0.0,
                entry_offset=1,
                exit_offset=2,
                realistic_execution=True,
                slippage_bps=0.0,
                min_commission=0.0,
                settlement_mode="complete",
            )
            body = run_backtest_api(payload)
            self.assertIn("summary", body)
            self.assertEqual(body["summary"]["buy_count"], 1)
            self.assertEqual(body["summary"]["sell_count"], 1)

            export_response = export_backtest_api(payload)
            self.assertEqual(export_response.status_code, 200)
            self.assertEqual(export_response.media_type, "application/zip")
            self.assertGreater(len(export_response.body), 100)
            with zipfile.ZipFile(BytesIO(export_response.body)) as archive:
                names = set(archive.namelist())
                summary_csv = archive.read("汇总.csv").decode("utf-8-sig")
                trades_csv = archive.read("交易流水.csv").decode("utf-8-sig")
            self.assertIn("条件诊断.csv", names)
            self.assertIn("年度稳定性.csv", names)
            self.assertIn("月度表现.csv", names)
            self.assertIn("退出原因统计.csv", names)
            self.assertIn("期末持仓.csv", names)
            self.assertIn("截止日卖出提醒.csv", names)
            self.assertIn("期末权益", summary_csv.splitlines()[0])
            self.assertIn("股票名称", trades_csv.splitlines()[0])
            self.assertIn("交易日期", trades_csv.splitlines()[0])

            table_response = export_backtest_table_api(payload, mode="account", table="trade_rows")
            self.assertEqual(table_response.status_code, 200)
            self.assertEqual(table_response.media_type, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            sheets = pd.read_excel(BytesIO(table_response.body), sheet_name=None)
            self.assertIn("口径说明", sheets)
            exported = None
            for sheet_name in ["真实交易流水", "交易流水"]:
                if sheet_name in sheets:
                    exported = sheets[sheet_name]
                    break
            self.assertIsNotNone(exported)
            assert exported is not None
            for column in ["交易日期", "信号日期", "股票代码", "股票名称", "动作", "价格", "股数", "盈亏"]:
                self.assertIn(column, exported.columns.tolist())


    def test_api_run_with_stock_pool_template_source(self) -> None:

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock_a = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m5": 0.3, "m20": 0.8, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 10.5, "raw_high": 10.6, "raw_low": 10.4, "raw_close": 10.5, "m5": 0.1, "m20": 0.7, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240104", "raw_open": 10.8, "raw_high": 10.9, "raw_low": 10.7, "raw_close": 10.8, "m5": 0.0, "m20": 0.6, "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            stock_b = make_processed_stock(
                "000002",
                "万科A",
                [
                    {"trade_date": "20240102", "raw_open": 20.0, "raw_high": 20.2, "raw_low": 19.8, "raw_close": 20.0, "m5": 0.1, "m20": 0.4, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 20.2, "raw_high": 20.4, "raw_low": 20.0, "raw_close": 20.3, "m5": 0.1, "m20": 0.3, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240104", "raw_open": 20.5, "raw_high": 20.6, "raw_low": 20.1, "raw_close": 20.4, "m5": 0.0, "m20": 0.2, "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            template_db = write_stock_pool_template_symbols_db(
                base / "stock_pool.sqlite",
                "接口股票池",
                [
                    {"symbol": "000001", "stock_name": "平安银行"},
                    {"symbol": "000002", "stock_name": "万科A"},
                ],
                username="api_user",
            )
            market_db = base / "market_data.sqlite"
            upsert_feature_rows(stock_a.to_dict("records") + stock_b.to_dict("records"), db_path=market_db)
            payload = BacktestRequest(
                data_source="stock_pool",
                processed_dir="",
                stock_pool_username="api_user",
                stock_pool_template_name="接口股票池",
                stock_pool_db_path=str(template_db),
                stock_pool_market_db_path=str(market_db),
                start_date="20240102",
                end_date="20240102",
                buy_condition="m20>0",
                score_expression="m20 + m5",
                top_n=1,
                initial_cash=100000.0,
                per_trade_budget=10000.0,
                lot_size=100,
                buy_fee_rate=0.0,
                sell_fee_rate=0.0,
                stamp_tax_sell=0.0,
                entry_offset=1,
                exit_offset=2,
                realistic_execution=True,
                slippage_bps=0.0,
                min_commission=0.0,
                settlement_mode="complete",
            )

            body = run_backtest_api(payload)
            self.assertEqual(body["diagnostics"]["data_source"], "stock_pool")
            self.assertEqual(body["diagnostics"]["stock_pool_template_name"], "接口股票池")
            self.assertEqual(body["summary"]["buy_count"], 1)
            self.assertEqual(body["pick_rows"][0]["symbol"], "000001")

            quality = run_signal_quality_api(SignalQualityRequest(**payload.model_dump()))
            self.assertEqual(quality["diagnostics"]["data_source"], "stock_pool")
            self.assertEqual(quality["summary"]["signal_count"], 1)

            export_response = export_backtest_api(payload)
            self.assertEqual(export_response.status_code, 200)
            self.assertGreater(len(export_response.body), 100)

    def test_stock_pool_template_reads_market_data_without_template_features(self) -> None:

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock_a = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m5": 0.3, "m20": 0.8, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 10.5, "raw_high": 10.8, "raw_low": 10.4, "raw_close": 10.8, "m5": 0.1, "m20": 0.7, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240104", "raw_open": 11.0, "raw_high": 11.2, "raw_low": 10.9, "raw_close": 11.1, "m5": 0.1, "m20": 0.5, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            stock_b = make_processed_stock(
                "000002",
                "万科A",
                [
                    {"trade_date": "20240102", "raw_open": 20.0, "raw_high": 20.2, "raw_low": 19.8, "raw_close": 20.0, "m5": 0.2, "m20": 0.6, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 20.2, "raw_high": 20.4, "raw_low": 20.0, "raw_close": 20.3, "m5": 0.2, "m20": 0.9, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240104", "raw_open": 20.5, "raw_high": 20.7, "raw_low": 20.4, "raw_close": 20.6, "m5": 0.2, "m20": 0.8, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            template_db = write_stock_pool_template_symbols_db(
                base / "stock_pool.sqlite",
                "接口股票池",
                [
                    {"symbol": "000001", "stock_name": "平安银行"},
                    {"symbol": "000002", "stock_name": "万科A"},
                ],
                username="api_user",
            )
            market_db = base / "market_data.sqlite"
            upsert_feature_rows(stock_a.to_dict("records") + stock_b.to_dict("records"), db_path=market_db)

            with patch("overnight_bt.market_data_store.DEFAULT_DB_PATH", market_db):
                backtest_body = run_backtest_api(
                    BacktestRequest(
                        data_source="stock_pool",
                        processed_dir="",
                        stock_pool_username="api_user",
                        stock_pool_template_name="接口股票池",
                        stock_pool_db_path=str(template_db),
                        start_date="20240102",
                        end_date="20240103",
                        buy_condition="m20>0",
                        score_expression="m20 + m5",
                        top_n=1,
                        initial_cash=100000.0,
                        per_trade_budget=10000.0,
                        lot_size=100,
                        buy_fee_rate=0.0,
                        sell_fee_rate=0.0,
                        stamp_tax_sell=0.0,
                        entry_offset=1,
                        exit_offset=2,
                        realistic_execution=True,
                        slippage_bps=0.0,
                        min_commission=0.0,
                        settlement_mode="complete",
                    )
                )
                daily_body = daily_plan_api(
                    DailyPlanRequest(
                        data_source="stock_pool",
                        processed_dir="",
                        stock_pool_username="api_user",
                        stock_pool_template_name="接口股票池",
                        stock_pool_db_path=str(template_db),
                        signal_date="20240103",
                        buy_condition="m20>0",
                        sell_condition="holding_return>0.05",
                        score_expression="m20",
                        top_n=1,
                        min_hold_days=0,
                        holdings=[DailyHolding(symbol="000001", buy_date="20240102", buy_price=10.0, shares=100, name="平安银行")],
                    )
                )

            self.assertEqual(backtest_body["diagnostics"]["data_source"], "stock_pool")
            self.assertEqual(backtest_body["diagnostics"]["template_stock_count"], 2)
            self.assertEqual(backtest_body["summary"]["buy_count"], 1)
            self.assertEqual(backtest_body["pick_rows"][0]["symbol"], "000001")
            self.assertEqual(daily_body["diagnostics"]["data_source"], "stock_pool")
            self.assertEqual(daily_body["buy_rows"][0]["symbol"], "000002")
            self.assertEqual(daily_body["sell_rows"][0]["symbol"], "000001")

    def test_daily_plan_api_returns_buy_and_sell_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock_a = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m5": 0.3, "m20": 0.8, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 10.5, "raw_high": 10.8, "raw_low": 10.4, "raw_close": 10.8, "m5": 0.1, "m20": 0.7, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            stock_b = make_processed_stock(
                "000002",
                "万科A",
                [
                    {"trade_date": "20240102", "raw_open": 20.0, "raw_high": 20.2, "raw_low": 19.8, "raw_close": 20.0, "m5": 0.2, "m20": 0.6, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 20.2, "raw_high": 20.4, "raw_low": 20.0, "raw_close": 20.3, "m5": 0.2, "m20": 0.9, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            template_db = write_stock_pool_template_symbols_db(
                base / "stock_pool.sqlite",
                "api_pool",
                [
                    {"symbol": "000001", "stock_name": "Alpha Bank"},
                    {"symbol": "000002", "stock_name": "Beta A"},
                ],
                username="api_user",
            )
            market_db = base / "market_data.sqlite"
            upsert_feature_rows(stock_a.to_dict("records") + stock_b.to_dict("records"), db_path=market_db)
            body = daily_plan_api(
                DailyPlanRequest(
                    data_source="stock_pool",
                    processed_dir="",
                    stock_pool_username="api_user",
                    stock_pool_template_name="api_pool",
                    stock_pool_db_path=str(template_db),
                    stock_pool_market_db_path=str(market_db),
                    signal_date="20240103",
                    buy_condition="m20>0",
                    sell_condition="holding_return>0.05",
                    score_expression="m20",
                    top_n=1,
                    min_hold_days=0,
                    holdings=[
                        DailyHolding(symbol="000001", buy_date="20240102", buy_price=10.0, shares=100, name="平安银行")
                    ],
                )
            )
            self.assertEqual(body["summary"]["signal_date"], "20240103")
            self.assertEqual(body["buy_rows"][0]["symbol"], "000002")
            self.assertEqual(body["sell_rows"][0]["symbol"], "000001")

    def test_daily_plan_api_with_stock_pool_template_source(self) -> None:

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock_a = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m5": 0.3, "m20": 0.8, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 10.5, "raw_high": 10.8, "raw_low": 10.4, "raw_close": 10.8, "m5": 0.1, "m20": 0.7, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            stock_b = make_processed_stock(
                "000002",
                "万科A",
                [
                    {"trade_date": "20240102", "raw_open": 20.0, "raw_high": 20.2, "raw_low": 19.8, "raw_close": 20.0, "m5": 0.2, "m20": 0.6, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 20.2, "raw_high": 20.4, "raw_low": 20.0, "raw_close": 20.3, "m5": 0.2, "m20": 0.9, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            template_db = write_stock_pool_template_symbols_db(
                base / "stock_pool.sqlite",
                "接口股票池",
                [
                    {"symbol": "000001", "stock_name": "平安银行"},
                    {"symbol": "000002", "stock_name": "万科A"},
                ],
                username="api_user",
            )
            market_db = base / "market_data.sqlite"
            upsert_feature_rows(stock_a.to_dict("records") + stock_b.to_dict("records"), db_path=market_db)
            body = daily_plan_api(
                DailyPlanRequest(
                    data_source="stock_pool",
                    processed_dir="",
                    stock_pool_username="api_user",
                    stock_pool_template_name="接口股票池",
                    stock_pool_db_path=str(template_db),
                    stock_pool_market_db_path=str(market_db),
                    signal_date="20240103",
                    buy_condition="m20>0",
                    sell_condition="holding_return>0.05",
                    score_expression="m20",
                    top_n=1,
                    min_hold_days=0,
                    holdings=[
                        DailyHolding(symbol="000001", buy_date="20240102", buy_price=10.0, shares=100, name="平安银行")
                    ],
                )
            )
            self.assertEqual(body["diagnostics"]["data_source"], "stock_pool")
            self.assertEqual(body["diagnostics"]["stock_pool_template_name"], "接口股票池")
            self.assertEqual(body["summary"]["signal_date"], "20240103")
            self.assertEqual(body["buy_rows"][0]["symbol"], "000002")
            self.assertEqual(body["sell_rows"][0]["symbol"], "000001")

    def test_signal_quality_api_ignores_cash_constraints(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock_a = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m5": 0.1, "m20": 0.2, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240103", "raw_open": 10.2, "raw_high": 10.4, "raw_low": 10.1, "raw_close": 10.3, "m5": 0.1, "m20": 0.18, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240104", "raw_open": 10.5, "raw_high": 10.7, "raw_low": 10.4, "raw_close": 10.6, "m5": 0.1, "m20": 0.05, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240105", "raw_open": 10.7, "raw_high": 10.8, "raw_low": 10.6, "raw_close": 10.7, "m5": 0.1, "m20": 0.04, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            stock_b = make_processed_stock(
                "000002",
                "万科A",
                [
                    {"trade_date": "20240102", "raw_open": 20.0, "raw_high": 20.2, "raw_low": 19.8, "raw_close": 20.0, "m5": 0.1, "m20": 0.3, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240103", "raw_open": 20.2, "raw_high": 20.4, "raw_low": 20.1, "raw_close": 20.3, "m5": 0.1, "m20": 0.28, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240104", "raw_open": 20.4, "raw_high": 20.6, "raw_low": 20.3, "raw_close": 20.4, "m5": 0.1, "m20": 0.22, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240105", "raw_open": 20.5, "raw_high": 20.8, "raw_low": 20.4, "raw_close": 20.7, "m5": 0.1, "m20": 0.21, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            template_db = write_stock_pool_template_symbols_db(
                base / "stock_pool.sqlite",
                "api_pool",
                [
                    {"symbol": "000001", "stock_name": "Alpha Bank"},
                    {"symbol": "000002", "stock_name": "Beta A"},
                ],
                username="api_user",
            )
            market_db = base / "market_data.sqlite"
            upsert_feature_rows(stock_a.to_dict("records") + stock_b.to_dict("records"), db_path=market_db)
            body = run_signal_quality_api(
                SignalQualityRequest(
                    data_source="stock_pool",
                    processed_dir="",
                    stock_pool_username="api_user",
                    stock_pool_template_name="api_pool",
                    stock_pool_db_path=str(template_db),
                    stock_pool_market_db_path=str(market_db),
                    start_date="20240102",
                    end_date="20240102",
                    buy_condition="m20>0",
                    sell_condition="m20<0.1",
                    score_expression="m20",
                    top_n=2,
                    entry_offset=1,
                    exit_offset=2,
                    min_hold_days=0,
                    max_hold_days=2,
                    settlement_mode="complete",
                    realistic_execution=True,
                    slippage_bps=0.0,
                )
            )
            self.assertEqual(body["summary"]["result_mode"], "signal_quality")
            self.assertEqual(body["summary"]["signal_count"], 2)
            self.assertEqual(body["summary"]["completed_signal_count"], 2)
            self.assertEqual(len(body["rank_rows"]), 2)
            self.assertEqual(body["rank_rows"][0]["rank"], 1)
            self.assertEqual([row["top_k"] for row in body["topk_rows"]], [1, 2])
            self.assertEqual(body["topk_rows"][-1]["completed_signal_count"], 2)
            self.assertTrue(any(row["recommended"] == "建议" for row in body["topk_rows"]))
            self.assertEqual(body["pick_rows"][0]["status"], "已完成")
            self.assertEqual([row["action"] for row in body["trade_rows"]], ["BUY", "BUY", "SELL", "SELL"])
            self.assertIn("price_basis", body["trade_rows"][0])
            self.assertIn("pnl", body["trade_rows"][-1])

    def test_single_stock_api_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock = make_processed_stock(
                "000001",
                "Alpha Bank",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.9, "raw_close": 10.1, "vol": 1000, "m20": 0.2, "m5": 0.1, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240103", "raw_open": 10.3, "raw_high": 10.5, "raw_low": 10.2, "raw_close": 10.4, "vol": 1100, "m20": 0.1, "m5": 0.1, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240104", "raw_open": 10.6, "raw_high": 10.7, "raw_low": 10.4, "raw_close": 10.5, "vol": 1200, "m20": -0.1, "m5": -0.1, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240105", "raw_open": 10.2, "raw_high": 10.3, "raw_low": 10.0, "raw_close": 10.1, "vol": 1300, "m20": -0.2, "m5": -0.2, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            template_db = write_stock_pool_template_symbols_db(
                base / "stock_pool.sqlite",
                "api_pool",
                [{"symbol": "000001", "stock_name": "Alpha Bank"}],
                username="api_user",
            )
            market_db = base / "market_data.sqlite"
            upsert_feature_rows(stock.to_dict("records"), db_path=market_db)

            with patch("overnight_bt.market_data_store.DEFAULT_DB_PATH", market_db):
                body = run_single_stock_api(
                    SingleStockBacktestRequest(
                        symbol="000001",
                        stock_pool_username="api_user",
                        stock_pool_template_name="api_pool",
                        stock_pool_db_path=str(template_db),
                        start_date="20240102",
                        end_date="20240105",
                        buy_condition="m20>0",
                        sell_condition="m20<0",
                        buy_confirm_days=1,
                        buy_cooldown_days=0,
                        sell_confirm_days=1,
                        initial_cash=100000,
                        per_trade_budget=10000,
                        lot_size=100,
                        execution_timing="next_day_open",
                        buy_fee_rate=0.0,
                        sell_fee_rate=0.0,
                        stamp_tax_sell=0.0,
                    )
                )
        self.assertEqual(body["stock_code"], "000001")
        self.assertIn("summary", body)
        self.assertEqual(len(body["trade_rows"]), 2)
        self.assertEqual(len(body["signal_rows"]), 4)
        self.assertGreater(len(body["metric_definitions"]), 0)


if __name__ == "__main__":
    unittest.main()
