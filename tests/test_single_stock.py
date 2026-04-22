from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from overnight_bt.models import SingleStockBacktestRequest
from overnight_bt.single_stock import run_single_stock_backtest


class SingleStockBacktestTest(unittest.TestCase):
    def test_run_single_stock_backtest_returns_summary_trades_and_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            excel_path = Path(tmpdir) / "000001_平安银行.xlsx"
            frame = pd.DataFrame(
                [
                    {"trade_date": "20240102", "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1, "vol": 1000, "m20": 0.2, "m5": 0.1},
                    {"trade_date": "20240103", "open": 10.3, "high": 10.5, "low": 10.2, "close": 10.4, "vol": 1100, "m20": 0.1, "m5": 0.1},
                    {"trade_date": "20240104", "open": 10.6, "high": 10.7, "low": 10.4, "close": 10.5, "vol": 1200, "m20": -0.1, "m5": -0.1},
                    {"trade_date": "20240105", "open": 10.2, "high": 10.3, "low": 10.0, "close": 10.1, "vol": 1300, "m20": -0.2, "m5": -0.2},
                ]
            )
            frame.to_excel(excel_path, index=False)

            result = run_single_stock_backtest(
                SingleStockBacktestRequest(
                    excel_path=str(excel_path),
                    start_date="20240102",
                    end_date="20240105",
                    buy_condition="m20>0",
                    buy_confirm_days=1,
                    buy_cooldown_days=0,
                    sell_condition="m20<0",
                    sell_confirm_days=1,
                    initial_cash=100000.0,
                    per_trade_budget=10000.0,
                    lot_size=100,
                    execution_timing="next_day_open",
                    buy_fee_rate=0.0,
                    sell_fee_rate=0.0,
                    stamp_tax_sell=0.0,
                )
            )

            self.assertEqual(result["stock_code"], "000001")
            self.assertEqual(result["stock_name"], "平安银行")
            self.assertEqual(len(result["trade_rows"]), 2)
            self.assertEqual(result["trade_rows"][0]["action"], "BUY")
            self.assertEqual(result["trade_rows"][1]["action"], "SELL")
            self.assertEqual(len(result["signal_rows"]), 4)
            self.assertTrue(any(item["key"] == "annualized_return" for item in result["metric_definitions"]))


if __name__ == "__main__":
    unittest.main()
