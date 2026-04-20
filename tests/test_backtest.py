from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from overnight_bt.backtest import load_processed_folder, run_portfolio_backtest, run_portfolio_backtest_loaded
from overnight_bt.models import BacktestRequest
from tests.helpers import make_processed_stock, write_processed_dir


class BacktestEngineTest(unittest.TestCase):
    def test_topn_portfolio_backtest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock_a = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {
                        "trade_date": "20240102",
                        "raw_open": 10.0,
                        "raw_high": 10.2,
                        "raw_low": 9.8,
                        "raw_close": 10.0,
                        "next_open": 11.0,
                        "next_close": 11.0,
                        "r_on": 0.1,
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
                        "raw_open": 11.0,
                        "raw_high": 11.1,
                        "raw_low": 10.8,
                        "raw_close": 11.0,
                        "next_open": 11.0,
                        "next_close": 11.0,
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
            stock_b = make_processed_stock(
                "000002",
                "万科A",
                [
                    {
                        "trade_date": "20240102",
                        "raw_open": 10.0,
                        "raw_high": 10.1,
                        "raw_low": 9.9,
                        "raw_close": 10.0,
                        "next_open": 10.1,
                        "next_close": 10.1,
                        "r_on": 0.01,
                        "m5": 0.2,
                        "m20": 0.6,
                        "can_buy_t": True,
                        "can_sell_t": True,
                        "can_sell_t1": True,
                        "is_suspended_t": False,
                        "is_suspended_t1": False,
                    },
                    {
                        "trade_date": "20240103",
                        "raw_open": 10.1,
                        "raw_high": 10.2,
                        "raw_low": 10.0,
                        "raw_close": 10.1,
                        "next_open": 10.1,
                        "next_close": 10.1,
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
            stock_c = make_processed_stock(
                "000003",
                "测试三号",
                [
                    {
                        "trade_date": "20240102",
                        "raw_open": 10.0,
                        "raw_high": 10.0,
                        "raw_low": 9.9,
                        "raw_close": 10.0,
                        "next_open": 9.8,
                        "next_close": 9.8,
                        "r_on": -0.02,
                        "m5": 0.1,
                        "m20": 0.2,
                        "can_buy_t": True,
                        "can_sell_t": True,
                        "can_sell_t1": True,
                        "is_suspended_t": False,
                        "is_suspended_t1": False,
                    },
                    {
                        "trade_date": "20240103",
                        "raw_open": 9.8,
                        "raw_high": 9.9,
                        "raw_low": 9.7,
                        "raw_close": 9.8,
                        "next_open": 9.8,
                        "next_close": 9.8,
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
            processed_dir = write_processed_dir(base, [stock_a, stock_b, stock_c])

            result = run_portfolio_backtest(
                BacktestRequest(
                    processed_dir=str(processed_dir),
                    buy_condition="m20>0",
                    score_expression="m20 + m5",
                    top_n=2,
                    initial_cash=100000.0,
                    lot_size=100,
                    buy_fee_rate=0.0,
                    sell_fee_rate=0.0,
                    stamp_tax_sell=0.0,
                    realistic_execution=False,
                    slippage_bps=0.0,
                    min_commission=0.0,
                )
            )
            self.assertEqual(result["summary"]["buy_count"], 2)
            self.assertEqual(result["summary"]["sell_count"], 2)
            self.assertGreater(result["summary"]["ending_equity"], 100000.0)
            self.assertEqual([row["symbol"] for row in result["pick_rows"]], ["000001", "000002"])

    def test_strict_mode_blocks_sell(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock_a = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {
                        "trade_date": "20240102",
                        "raw_open": 10.0,
                        "raw_high": 10.2,
                        "raw_low": 9.8,
                        "raw_close": 10.0,
                        "next_open": 10.0,
                        "next_close": 10.0,
                        "r_on": 0.0,
                        "m5": 0.3,
                        "m20": 0.8,
                        "can_buy_t": True,
                        "can_sell_t": True,
                        "can_sell_t1": False,
                        "is_suspended_t": False,
                        "is_suspended_t1": True,
                    },
                    {
                        "trade_date": "20240103",
                        "raw_open": 10.0,
                        "raw_high": 10.1,
                        "raw_low": 9.9,
                        "raw_close": 10.0,
                        "next_open": 10.2,
                        "next_close": 10.2,
                        "r_on": 0.02,
                        "m5": -0.1,
                        "m20": -0.2,
                        "can_buy_t": False,
                        "can_sell_t": False,
                        "can_sell_t1": True,
                        "is_suspended_t": True,
                        "is_suspended_t1": False,
                    },
                    {
                        "trade_date": "20240104",
                        "raw_open": 10.2,
                        "raw_high": 10.3,
                        "raw_low": 10.0,
                        "raw_close": 10.2,
                        "next_open": 10.2,
                        "next_close": 10.2,
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
            processed_dir = write_processed_dir(base, [stock_a])
            result = run_portfolio_backtest(
                BacktestRequest(
                    processed_dir=str(processed_dir),
                    buy_condition="m20>0",
                    score_expression="m20",
                    top_n=1,
                    initial_cash=10000.0,
                    lot_size=100,
                    buy_fee_rate=0.0,
                    sell_fee_rate=0.0,
                    stamp_tax_sell=0.0,
                    realistic_execution=True,
                    slippage_bps=0.0,
                    min_commission=0.0,
                )
            )
            self.assertEqual(result["summary"]["blocked_sell_count"], 1)
            self.assertEqual(result["summary"]["sell_count"], 1)

    def test_backtest_supports_categorical_and_snapshot_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock_main = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {
                        "trade_date": "20240102",
                        "raw_open": 10.0,
                        "raw_high": 10.2,
                        "raw_low": 9.8,
                        "raw_close": 10.0,
                        "next_open": 10.3,
                        "next_close": 10.3,
                        "r_on": 0.03,
                        "m5": 0.3,
                        "m20": 0.8,
                        "listed_days": 800,
                        "total_mv_snapshot": 900000.0,
                        "turnover_rate_snapshot": 1.2,
                        "board": "主板",
                        "market": "主板",
                        "can_buy_t": True,
                        "can_sell_t": True,
                        "can_sell_t1": True,
                        "is_suspended_t": False,
                        "is_suspended_t1": False,
                    },
                    {
                        "trade_date": "20240103",
                        "raw_open": 10.3,
                        "raw_high": 10.4,
                        "raw_low": 10.2,
                        "raw_close": 10.3,
                        "next_open": 10.3,
                        "next_close": 10.3,
                        "r_on": 0.0,
                        "m5": -0.1,
                        "m20": -0.2,
                        "listed_days": 801,
                        "total_mv_snapshot": 900000.0,
                        "turnover_rate_snapshot": 1.2,
                        "board": "主板",
                        "market": "主板",
                        "can_buy_t": False,
                        "can_sell_t": True,
                        "can_sell_t1": True,
                        "is_suspended_t": False,
                        "is_suspended_t1": False,
                    },
                ],
            )
            stock_cyb = make_processed_stock(
                "300001",
                "测试创业板",
                [
                    {
                        "trade_date": "20240102",
                        "raw_open": 10.0,
                        "raw_high": 10.2,
                        "raw_low": 9.9,
                        "raw_close": 10.0,
                        "next_open": 10.8,
                        "next_close": 10.8,
                        "r_on": 0.08,
                        "m5": 0.6,
                        "m20": 1.0,
                        "listed_days": 120,
                        "total_mv_snapshot": 700000.0,
                        "turnover_rate_snapshot": 2.5,
                        "board": "创业板",
                        "market": "创业板",
                        "can_buy_t": True,
                        "can_sell_t": True,
                        "can_sell_t1": True,
                        "is_suspended_t": False,
                        "is_suspended_t1": False,
                    },
                    {
                        "trade_date": "20240103",
                        "raw_open": 10.8,
                        "raw_high": 10.9,
                        "raw_low": 10.7,
                        "raw_close": 10.8,
                        "next_open": 10.8,
                        "next_close": 10.8,
                        "r_on": 0.0,
                        "m5": -0.1,
                        "m20": -0.2,
                        "listed_days": 121,
                        "total_mv_snapshot": 700000.0,
                        "turnover_rate_snapshot": 2.5,
                        "board": "创业板",
                        "market": "创业板",
                        "can_buy_t": False,
                        "can_sell_t": True,
                        "can_sell_t1": True,
                        "is_suspended_t": False,
                        "is_suspended_t1": False,
                    },
                ],
            )
            processed_dir = write_processed_dir(base, [stock_main, stock_cyb])

            result = run_portfolio_backtest(
                BacktestRequest(
                    processed_dir=str(processed_dir),
                    buy_condition="board=主板,listed_days>250,total_mv_snapshot>800000,turnover_rate_snapshot<2,m20>0",
                    score_expression="m20 + listed_days / 1000",
                    top_n=2,
                    initial_cash=100000.0,
                    lot_size=100,
                    buy_fee_rate=0.0,
                    sell_fee_rate=0.0,
                    stamp_tax_sell=0.0,
                    realistic_execution=False,
                    slippage_bps=0.0,
                    min_commission=0.0,
                )
            )
            self.assertEqual(result["summary"]["buy_count"], 1)
            self.assertEqual([row["symbol"] for row in result["pick_rows"]], ["000001"])

    def test_loaded_dataset_runner_matches_regular_runner(self) -> None:
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
                        "next_open": 10.4,
                        "next_close": 10.4,
                        "r_on": 0.04,
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
                        "raw_open": 10.4,
                        "raw_high": 10.5,
                        "raw_low": 10.3,
                        "raw_close": 10.4,
                        "next_open": 10.4,
                        "next_close": 10.4,
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
            req = BacktestRequest(
                processed_dir=str(processed_dir),
                buy_condition="m20>0",
                score_expression="m20 + m5",
                top_n=1,
                initial_cash=10000.0,
                lot_size=100,
                buy_fee_rate=0.0,
                sell_fee_rate=0.0,
                stamp_tax_sell=0.0,
                realistic_execution=False,
                slippage_bps=0.0,
                min_commission=0.0,
            )
            loaded, diagnostics = load_processed_folder(str(processed_dir))
            regular = run_portfolio_backtest(req)
            cached = run_portfolio_backtest_loaded(loaded, diagnostics, req)
            self.assertEqual(regular["summary"]["ending_equity"], cached["summary"]["ending_equity"])
            self.assertEqual(regular["summary"]["buy_count"], cached["summary"]["buy_count"])

    def test_raw_execution_uses_raw_prices_and_adj_factor_ratio(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {
                        "trade_date": "20240102",
                        "raw_open": 10.0,
                        "raw_high": 10.0,
                        "raw_low": 10.0,
                        "raw_close": 10.0,
                        "qfq_open": 8.3333,
                        "qfq_high": 8.3333,
                        "qfq_low": 8.3333,
                        "qfq_close": 8.3333,
                        "adj_factor": 1.0,
                        "next_open": 9.0,
                        "next_close": 9.0,
                        "r_on": 0.08,
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
                        "raw_open": 9.0,
                        "raw_high": 9.0,
                        "raw_low": 9.0,
                        "raw_close": 9.0,
                        "qfq_open": 9.0,
                        "qfq_high": 9.0,
                        "qfq_low": 9.0,
                        "qfq_close": 9.0,
                        "adj_factor": 1.2,
                        "next_open": 9.0,
                        "next_close": 9.0,
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
            result = run_portfolio_backtest(
                BacktestRequest(
                    processed_dir=str(processed_dir),
                    buy_condition="m20>0",
                    score_expression="m20",
                    top_n=1,
                    initial_cash=10000.0,
                    lot_size=100,
                    buy_fee_rate=0.0,
                    sell_fee_rate=0.0,
                    stamp_tax_sell=0.0,
                    realistic_execution=False,
                    slippage_bps=0.0,
                    min_commission=0.0,
                )
            )
            buy_row = next(row for row in result["trade_rows"] if row["action"] == "BUY")
            sell_row = next(row for row in result["trade_rows"] if row["action"] == "SELL")
            self.assertEqual(buy_row["price"], 10.0)
            self.assertEqual(buy_row["shares"], 1000)
            self.assertEqual(sell_row["price"], 9.0)
            self.assertEqual(sell_row["shares"], 1200.0)
            self.assertAlmostEqual(result["summary"]["ending_equity"], 10800.0, places=2)


if __name__ == "__main__":
    unittest.main()
