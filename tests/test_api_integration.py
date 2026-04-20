from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from overnight_bt.app import export_backtest_api, run_backtest_api
from overnight_bt.models import BacktestRequest
from tests.helpers import make_processed_stock, write_processed_dir


class ApiIntegrationTest(unittest.TestCase):
    def test_api_run_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {
                        "trade_date": "20240102",
                        "raw_open": 10.0,
                        "raw_high": 10.2,
                        "raw_low": 9.8,
                        "raw_close": 10.0,
                        "next_open": 10.5,
                        "next_close": 10.5,
                        "r_on": 0.05,
                        "m5": 0.3,
                        "m20": 0.8,
                        "can_buy_t": True,
                        "can_sell_t": True,
                        "can_sell_t1": True,
                        "is_suspended_t": False,
                        "is_suspended_t1": False,
                    },
                    {
                        "trade_date": "20240103",
                        "raw_open": 10.5,
                        "raw_high": 10.6,
                        "raw_low": 10.4,
                        "raw_close": 10.5,
                        "next_open": 10.5,
                        "next_close": 10.5,
                        "r_on": 0.0,
                        "m5": -0.1,
                        "m20": -0.2,
                        "can_buy_t": False,
                        "can_sell_t": True,
                        "can_sell_t1": True,
                        "is_suspended_t": False,
                        "is_suspended_t1": False,
                    },
                ],
            )
            processed_dir = write_processed_dir(base, [stock])
            payload = BacktestRequest(
                processed_dir=str(processed_dir),
                buy_condition="m20>0",
                score_expression="m20 + m5",
                top_n=1,
                initial_cash=10000,
                lot_size=100,
                buy_fee_rate=0.0,
                sell_fee_rate=0.0,
                stamp_tax_sell=0.0,
                realistic_execution=False,
                slippage_bps=0.0,
                min_commission=0.0,
            )
            body = run_backtest_api(payload)
            self.assertIn("summary", body)
            self.assertEqual(body["summary"]["buy_count"], 1)

            export_response = export_backtest_api(payload)
            self.assertEqual(export_response.status_code, 200)
            self.assertEqual(export_response.media_type, "application/zip")
            self.assertGreater(len(export_response.body), 100)


if __name__ == "__main__":
    unittest.main()
