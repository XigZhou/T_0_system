from __future__ import annotations

import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd

from overnight_bt.app import daily_plan_api, export_backtest_api, run_backtest_api, run_signal_quality_api, run_single_stock_api
from overnight_bt.models import BacktestRequest, DailyHolding, DailyPlanRequest, SignalQualityRequest, SingleStockBacktestRequest
from tests.helpers import make_processed_stock, write_processed_dir


class ApiIntegrationTest(unittest.TestCase):
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
            processed_dir = write_processed_dir(base, [stock])
            payload = BacktestRequest(
                processed_dir=str(processed_dir),
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
            processed_dir = write_processed_dir(base, [stock_a, stock_b])
            body = daily_plan_api(
                DailyPlanRequest(
                    processed_dir=str(processed_dir),
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
            processed_dir = write_processed_dir(base, [stock_a, stock_b])
            body = run_signal_quality_api(
                SignalQualityRequest(
                    processed_dir=str(processed_dir),
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

    def test_single_stock_api_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            excel_path = Path(tmpdir) / "000001_平安银行.xlsx"
            pd.DataFrame(
                [
                    {"trade_date": "20240102", "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1, "vol": 1000, "m20": 0.2, "m5": 0.1},
                    {"trade_date": "20240103", "open": 10.3, "high": 10.5, "low": 10.2, "close": 10.4, "vol": 1100, "m20": 0.1, "m5": 0.1},
                    {"trade_date": "20240104", "open": 10.6, "high": 10.7, "low": 10.4, "close": 10.5, "vol": 1200, "m20": -0.1, "m5": -0.1},
                    {"trade_date": "20240105", "open": 10.2, "high": 10.3, "low": 10.0, "close": 10.1, "vol": 1300, "m20": -0.2, "m5": -0.2},
                ]
            ).to_excel(excel_path, index=False)

            body = run_single_stock_api(
                SingleStockBacktestRequest(
                    excel_path=str(excel_path),
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
