from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from overnight_bt.app import export_backtest_api, run_backtest_api, run_single_stock_api
from overnight_bt.models import BacktestRequest, SingleStockBacktestRequest
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
            )
            body = run_backtest_api(payload)
            self.assertIn("summary", body)
            self.assertEqual(body["summary"]["buy_count"], 1)
            self.assertEqual(body["summary"]["sell_count"], 1)

            export_response = export_backtest_api(payload)
            self.assertEqual(export_response.status_code, 200)
            self.assertEqual(export_response.media_type, "application/zip")
            self.assertGreater(len(export_response.body), 100)

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
