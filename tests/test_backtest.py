from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from overnight_bt.backtest import run_portfolio_backtest
from overnight_bt.models import BacktestRequest
from tests.helpers import make_processed_stock, write_processed_dir


class BacktestEngineTest(unittest.TestCase):
    def test_signal_day_enters_t1_open_and_exits_t2_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock_a = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m5": 0.3, "m20": 0.8, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 10.2, "raw_high": 10.4, "raw_low": 10.0, "raw_close": 10.3, "m5": 0.1, "m20": 0.7, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240104", "raw_open": 10.8, "raw_high": 10.9, "raw_low": 10.6, "raw_close": 10.7, "m5": 0.0, "m20": 0.6, "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            stock_b = make_processed_stock(
                "000002",
                "万科A",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.1, "raw_low": 9.9, "raw_close": 10.0, "m5": 0.2, "m20": 0.5, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 10.1, "raw_high": 10.2, "raw_low": 10.0, "raw_close": 10.1, "m5": 0.1, "m20": 0.4, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240104", "raw_open": 10.0, "raw_high": 10.1, "raw_low": 9.9, "raw_close": 10.0, "m5": 0.0, "m20": 0.3, "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            processed_dir = write_processed_dir(base, [stock_a, stock_b])

            result = run_portfolio_backtest(
                BacktestRequest(
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
            )

            self.assertEqual(result["summary"]["buy_count"], 1)
            self.assertEqual(result["summary"]["sell_count"], 1)
            self.assertEqual(result["pick_rows"][0]["symbol"], "000001")
            self.assertEqual(result["pick_rows"][0]["planned_entry_date"], "20240103")
            self.assertEqual(result["pick_rows"][0]["planned_exit_date"], "20240104")
            buy_trade = next(row for row in result["trade_rows"] if row["action"] == "BUY")
            sell_trade = next(row for row in result["trade_rows"] if row["action"] == "SELL")
            self.assertEqual(buy_trade["trade_date"], "20240103")
            self.assertEqual(sell_trade["trade_date"], "20240104")
            self.assertGreater(result["summary"]["ending_equity"], 100000.0)

    def test_strict_mode_blocks_buy_on_entry_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m20": 0.8, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": False, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 10.5, "raw_high": 10.6, "raw_low": 10.4, "raw_close": 10.5, "m20": 0.7, "can_buy_t": True, "can_buy_open_t": False, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240104", "raw_open": 10.8, "raw_high": 10.9, "raw_low": 10.7, "raw_close": 10.8, "m20": 0.6, "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            processed_dir = write_processed_dir(base, [stock])
            result = run_portfolio_backtest(
                BacktestRequest(
                    processed_dir=str(processed_dir),
                    start_date="20240102",
                    end_date="20240102",
                    buy_condition="m20>0",
                    score_expression="m20",
                    top_n=1,
                    buy_fee_rate=0.0,
                    sell_fee_rate=0.0,
                    stamp_tax_sell=0.0,
                    realistic_execution=True,
                    slippage_bps=0.0,
                    min_commission=0.0,
                )
            )
            self.assertEqual(result["summary"]["blocked_buy_count"], 1)
            self.assertEqual(result["summary"]["buy_count"], 0)
            self.assertTrue(any(row["action"] == "BUY_BLOCKED" for row in result["trade_rows"]))

    def test_strict_mode_blocked_sell_rolls_to_next_available_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m20": 0.8, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 10.1, "raw_high": 10.2, "raw_low": 10.0, "raw_close": 10.1, "m20": 0.7, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": False, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240104", "raw_open": 9.6, "raw_high": 9.8, "raw_low": 9.5, "raw_close": 9.7, "m20": 0.5, "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": False, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240105", "raw_open": 10.4, "raw_high": 10.5, "raw_low": 10.3, "raw_close": 10.4, "m20": 0.4, "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            processed_dir = write_processed_dir(base, [stock])
            result = run_portfolio_backtest(
                BacktestRequest(
                    processed_dir=str(processed_dir),
                    start_date="20240102",
                    end_date="20240102",
                    buy_condition="m20>0",
                    score_expression="m20",
                    top_n=1,
                    buy_fee_rate=0.0,
                    sell_fee_rate=0.0,
                    stamp_tax_sell=0.0,
                    realistic_execution=True,
                    slippage_bps=0.0,
                    min_commission=0.0,
                )
            )
            self.assertEqual(result["summary"]["blocked_sell_count"], 1)
            sell_trade = next(row for row in result["trade_rows"] if row["action"] == "SELL")
            self.assertEqual(sell_trade["trade_date"], "20240105")

    def test_backtest_supports_categorical_and_snapshot_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock_main = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m20": 0.8, "listed_days": 800, "total_mv_snapshot": 9000000.0, "turnover_rate_snapshot": 1.2, "board": "主板", "market": "主板", "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 10.3, "raw_high": 10.4, "raw_low": 10.2, "raw_close": 10.3, "m20": 0.7, "listed_days": 801, "total_mv_snapshot": 9000000.0, "turnover_rate_snapshot": 1.2, "board": "主板", "market": "主板", "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240104", "raw_open": 10.5, "raw_high": 10.6, "raw_low": 10.4, "raw_close": 10.5, "m20": 0.6, "listed_days": 802, "total_mv_snapshot": 9000000.0, "turnover_rate_snapshot": 1.2, "board": "主板", "market": "主板", "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            stock_cyb = make_processed_stock(
                "300001",
                "测试创业板",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m20": 0.8, "listed_days": 120, "total_mv_snapshot": 7000000.0, "turnover_rate_snapshot": 2.5, "board": "创业板", "market": "创业板", "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 10.8, "raw_high": 10.9, "raw_low": 10.7, "raw_close": 10.8, "m20": 0.7, "listed_days": 121, "total_mv_snapshot": 7000000.0, "turnover_rate_snapshot": 2.5, "board": "创业板", "market": "创业板", "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240104", "raw_open": 11.0, "raw_high": 11.1, "raw_low": 10.9, "raw_close": 11.0, "m20": 0.6, "listed_days": 122, "total_mv_snapshot": 7000000.0, "turnover_rate_snapshot": 2.5, "board": "创业板", "market": "创业板", "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": True, "can_sell_t1": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            processed_dir = write_processed_dir(base, [stock_main, stock_cyb])
            result = run_portfolio_backtest(
                BacktestRequest(
                    processed_dir=str(processed_dir),
                    start_date="20240102",
                    end_date="20240102",
                    buy_condition="board=主板,listed_days>250,total_mv_snapshot>8000000,turnover_rate_snapshot<2,m20>0",
                    score_expression="m20",
                    top_n=2,
                    buy_fee_rate=0.0,
                    sell_fee_rate=0.0,
                    stamp_tax_sell=0.0,
                    realistic_execution=True,
                    slippage_bps=0.0,
                    min_commission=0.0,
                )
            )
            self.assertEqual([row["symbol"] for row in result["pick_rows"]], ["000001"])

    def test_sell_condition_triggers_next_open_after_min_hold(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.1, "raw_low": 9.9, "raw_close": 10.0, "m20": 0.8, "m5": 0.2, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 10.2, "raw_high": 10.3, "raw_low": 10.0, "raw_close": 10.1, "m20": 0.7, "m5": -0.1, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240104", "raw_open": 10.1, "raw_high": 10.2, "raw_low": 9.9, "raw_close": 9.95, "m20": 0.6, "m5": -0.2, "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240105", "raw_open": 9.9, "raw_high": 10.0, "raw_low": 9.8, "raw_close": 9.95, "m20": 0.5, "m5": -0.1, "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240108", "raw_open": 9.8, "raw_high": 9.9, "raw_low": 9.7, "raw_close": 9.8, "m20": 0.4, "m5": -0.1, "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            processed_dir = write_processed_dir(base, [stock])
            result = run_portfolio_backtest(
                BacktestRequest(
                    processed_dir=str(processed_dir),
                    start_date="20240102",
                    end_date="20240102",
                    buy_condition="m20>0",
                    sell_condition="m5<0",
                    score_expression="m20",
                    top_n=1,
                    initial_cash=10000.0,
                    per_trade_budget=10000.0,
                    lot_size=100,
                    buy_fee_rate=0.0,
                    sell_fee_rate=0.0,
                    stamp_tax_sell=0.0,
                    entry_offset=1,
                    exit_offset=5,
                    min_hold_days=1,
                    max_hold_days=3,
                    realistic_execution=True,
                    slippage_bps=0.0,
                    min_commission=0.0,
                )
            )
            sell_trade = next(row for row in result["trade_rows"] if row["action"] == "SELL")
            self.assertEqual(sell_trade["trade_date"], "20240105")
            self.assertEqual(sell_trade["exit_signal_date"], "20240104")
            self.assertTrue(str(sell_trade["exit_reason"]).startswith("sell_condition:"))
            self.assertEqual(result["summary"]["sell_condition_exit_count"], 1)

    def test_max_hold_exit_applies_when_sell_condition_never_triggers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.1, "raw_low": 9.9, "raw_close": 10.0, "m20": 0.8, "m5": 0.2, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240103", "raw_open": 10.1, "raw_high": 10.2, "raw_low": 10.0, "raw_close": 10.1, "m20": 0.7, "m5": 0.2, "can_buy_t": True, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240104", "raw_open": 10.2, "raw_high": 10.3, "raw_low": 10.1, "raw_close": 10.2, "m20": 0.6, "m5": 0.2, "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                    {"trade_date": "20240105", "raw_open": 10.3, "raw_high": 10.4, "raw_low": 10.2, "raw_close": 10.3, "m20": 0.5, "m5": 0.1, "can_buy_t": False, "can_buy_open_t": True, "can_sell_t": True, "is_suspended_t": False, "is_suspended_t1": False},
                ],
            )
            processed_dir = write_processed_dir(base, [stock])
            result = run_portfolio_backtest(
                BacktestRequest(
                    processed_dir=str(processed_dir),
                    start_date="20240102",
                    end_date="20240102",
                    buy_condition="m20>0",
                    sell_condition="m20>100",
                    score_expression="m20",
                    top_n=1,
                    initial_cash=10000.0,
                    per_trade_budget=10000.0,
                    lot_size=100,
                    buy_fee_rate=0.0,
                    sell_fee_rate=0.0,
                    stamp_tax_sell=0.0,
                    entry_offset=1,
                    exit_offset=5,
                    min_hold_days=1,
                    max_hold_days=2,
                    realistic_execution=True,
                    slippage_bps=0.0,
                    min_commission=0.0,
                )
            )
            sell_trade = next(row for row in result["trade_rows"] if row["action"] == "SELL")
            self.assertEqual(sell_trade["trade_date"], "20240105")
            self.assertEqual(sell_trade["exit_reason"], "fixed_or_max_exit")
            self.assertEqual(result["summary"]["max_hold_exit_count"], 1)


if __name__ == "__main__":
    unittest.main()
