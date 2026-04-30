from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from overnight_bt.models import PaperTradingRunRequest
from overnight_bt.paper_trading import PriceQuote, list_paper_account_templates, read_paper_trading_ledger, run_paper_trading
from tests.helpers import make_processed_stock, write_processed_dir


class PaperTradingTest(unittest.TestCase):
    def _write_config(
        self,
        base: Path,
        processed_dir: Path,
        initial_capital: float = 100000,
        buy_shares: int = 200,
        top_n: int = 1,
        min_buy_amount: float = 0,
        lot_size: int = 100,
        min_close: float = 0,
        max_close: float = 0,
    ) -> Path:
        config_dir = base / "configs" / "paper_accounts"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "test_account.yaml"
        ledger_path = base / "paper_trading" / "accounts" / "test_account.xlsx"
        config_path.write_text(
            f"""
账户编号: 测试账户
账户名称: 测试模拟账户
初始资金: {initial_capital}
处理后数据目录: {processed_dir.as_posix()}
买入条件: "m20>0.5"
卖出条件: "m20<0.2"
评分表达式: "m20"
买入排名数量: {top_n}
买入偏移: 1
最短持有天数: 0
最大持有天数: 15
买入数量:
  方式: 固定股数
  股数: {buy_shares}
  每手股数: {lot_size}
  最低买入金额: {min_buy_amount}
买入价格筛选:
  最低收盘价: {min_close}
  最高收盘价: {max_close}
行情源:
  首选: 本地日线
  备用: 腾讯股票
  价格字段: 开盘价
交易规则:
  持仓时不重复买入: 是
  有待成交订单时不重复买入: 是
  严格成交: 是
费用:
  买卖费率: 0
  印花税: 0
  滑点bps: 0
  最低佣金: 0
输出:
  账本路径: {ledger_path.as_posix()}
  日志目录: {(base / "paper_trading" / "logs").as_posix()}
""".strip(),
            encoding="utf-8",
        )
        return config_path

    def test_generate_execute_sell_and_excel_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock_a = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m20": 0.8, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240103", "raw_open": 10.5, "raw_high": 10.8, "raw_low": 10.4, "raw_close": 10.7, "m20": 0.1, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240104", "raw_open": 11.0, "raw_high": 11.2, "raw_low": 10.9, "raw_close": 11.1, "m20": 0.1, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            stock_b = make_processed_stock(
                "000002",
                "万科A",
                [
                    {"trade_date": "20240102", "raw_open": 20.0, "raw_high": 20.2, "raw_low": 19.8, "raw_close": 20.0, "m20": 0.4, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240103", "raw_open": 20.2, "raw_high": 20.4, "raw_low": 20.0, "raw_close": 20.3, "m20": 0.3, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240104", "raw_open": 20.4, "raw_high": 20.6, "raw_low": 20.3, "raw_close": 20.4, "m20": 0.3, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            processed_dir = write_processed_dir(base, [stock_a, stock_b])
            config_path = self._write_config(base, processed_dir)

            generated = run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240102"))
            self.assertEqual(generated["summary"]["added_order_count"], 1)
            self.assertEqual(generated["pending_order_rows"][0]["订单方向"], "买入")

            executed = run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="execute", trade_date="20240103"))
            self.assertEqual(executed["summary"]["executed_count"], 1)
            self.assertEqual(executed["holding_rows"][0]["股票代码"], "000001.SZ")
            self.assertEqual(executed["holding_rows"][0]["股数"], 200)

            sell_signal = run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240103"))
            self.assertEqual(sell_signal["summary"]["planned_sell_count"], 1)

            sold = run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="execute", trade_date="20240104"))
            self.assertGreaterEqual(sold["summary"]["executed_count"], 1)
            self.assertEqual(sold["holding_rows"], [])
            sell_trades = [row for row in sold["trade_rows"] if row["交易方向"] == "卖出"]
            self.assertEqual(len(sell_trades), 1)
            self.assertEqual(sell_trades[0]["实现盈亏"], 100.0)

            loaded = read_paper_trading_ledger(PaperTradingRunRequest(config_path=str(config_path)))
            self.assertEqual(loaded["summary"]["action"], "读取账本")
            self.assertEqual(loaded["summary"]["trade_count"], 2)
            self.assertGreaterEqual(loaded["summary"]["log_count"], 1)

            ledger_path = Path(sold["summary"]["ledger_path"])
            self.assertTrue(ledger_path.exists())
            sheets = pd.read_excel(ledger_path, sheet_name=None)
            self.assertIn("待执行订单", sheets)
            self.assertIn("成交流水", sheets)
            self.assertIn("当前持仓", sheets)
            self.assertIn("每日资产", sheets)

    def test_execute_sells_before_buys_to_release_cash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock_a = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 5.0, "raw_high": 5.2, "raw_low": 4.8, "raw_close": 5.0, "m20": 0.8, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240103", "raw_open": 5.0, "raw_high": 5.2, "raw_low": 4.8, "raw_close": 5.0, "m20": 0.1, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240104", "raw_open": 6.0, "raw_high": 6.2, "raw_low": 5.8, "raw_close": 6.0, "m20": 0.1, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            stock_b = make_processed_stock(
                "000002",
                "万科A",
                [
                    {"trade_date": "20240102", "raw_open": 8.0, "raw_high": 8.2, "raw_low": 7.8, "raw_close": 8.0, "m20": 0.1, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240103", "raw_open": 8.0, "raw_high": 8.2, "raw_low": 7.8, "raw_close": 8.0, "m20": 0.8, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240104", "raw_open": 8.0, "raw_high": 8.2, "raw_low": 7.8, "raw_close": 8.0, "m20": 0.8, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            processed_dir = write_processed_dir(base, [stock_a, stock_b])
            config_path = self._write_config(base, processed_dir, initial_capital=1000, buy_shares=100)

            run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240102"))
            run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="execute", trade_date="20240103"))
            generated = run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240103"))
            self.assertEqual(generated["summary"]["planned_buy_count"], 1)
            self.assertEqual(generated["summary"]["planned_sell_count"], 1)

            executed = run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="execute", trade_date="20240104"))

            self.assertEqual(executed["summary"]["executed_count"], 2)
            self.assertEqual(executed["summary"]["failed_count"], 0)
            self.assertEqual(executed["holding_rows"][0]["股票代码"], "000002.SZ")
            executed_directions = [row["交易方向"] for row in executed["trade_rows"][-2:]]
            self.assertEqual(executed_directions, ["卖出", "买入"])

    def test_refresh_realtime_positions_updates_holding_and_asset_value(self) -> None:
        class FakeRealtimeQuoteProvider:
            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def quote(self, symbol: str, trade_date: str) -> PriceQuote:
                return PriceQuote(symbol=symbol, name="平安银行", trade_date=trade_date, price=12.34, close_price=12.34, can_buy=True, can_sell=True, source="测试行情")

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m20": 0.8, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240103", "raw_open": 10.5, "raw_high": 10.8, "raw_low": 10.4, "raw_close": 10.7, "m20": 0.8, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            processed_dir = write_processed_dir(base, [stock])
            config_path = self._write_config(base, processed_dir)

            run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240102"))
            run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="execute", trade_date="20240103"))
            with patch("overnight_bt.paper_trading.RealtimeQuoteProvider", FakeRealtimeQuoteProvider):
                refreshed = run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="refresh", trade_date="20240103"))

            self.assertEqual(refreshed["summary"]["action"], "实时刷新持仓价格")
            self.assertEqual(refreshed["summary"]["updated_holding_count"], 1)
            self.assertEqual(refreshed["summary"]["quote_source"], "测试行情")
            self.assertEqual(refreshed["holding_rows"][0]["当前价格"], 12.34)
            self.assertEqual(refreshed["holding_rows"][0]["当前市值"], 2468.0)
            self.assertEqual(refreshed["summary"]["market_value"], 2468.0)
            self.assertIn("实时行情估值", refreshed["asset_rows"][-1]["备注"])
            self.assertEqual(refreshed["log_rows"][-1]["动作"], "实时估值")

    def test_generate_filters_buy_candidates_by_signal_close_price(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            high_price = make_processed_stock(
                "000001",
                "高价股",
                [
                    {"trade_date": "20240102", "raw_open": 120.0, "raw_high": 121.0, "raw_low": 119.0, "raw_close": 120.0, "m20": 0.9, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240103", "raw_open": 120.0, "raw_high": 121.0, "raw_low": 119.0, "raw_close": 120.0, "m20": 0.9, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            normal_price = make_processed_stock(
                "000002",
                "普通股",
                [
                    {"trade_date": "20240102", "raw_open": 50.0, "raw_high": 51.0, "raw_low": 49.0, "raw_close": 50.0, "m20": 0.8, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240103", "raw_open": 50.0, "raw_high": 51.0, "raw_low": 49.0, "raw_close": 50.0, "m20": 0.8, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            processed_dir = write_processed_dir(base, [high_price, normal_price])
            config_path = self._write_config(base, processed_dir, max_close=100)

            generated = run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240102"))

            self.assertEqual(generated["summary"]["price_filtered_count"], 1)
            self.assertEqual(generated["summary"]["planned_buy_count"], 1)
            self.assertEqual(generated["pending_order_rows"][0]["股票代码"], "000002.SZ")
            self.assertEqual(generated["pending_order_rows"][0]["信号收盘价"], 50.0)

    def test_min_buy_amount_rounds_shares_up_by_signal_close_and_lot_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock_a = make_processed_stock(
                "000001",
                "二十五元股",
                [
                    {"trade_date": "20240102", "raw_open": 25.0, "raw_high": 26.0, "raw_low": 24.0, "raw_close": 25.0, "m20": 0.9, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240103", "raw_open": 25.0, "raw_high": 26.0, "raw_low": 24.0, "raw_close": 25.0, "m20": 0.9, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            stock_b = make_processed_stock(
                "000002",
                "七十元股",
                [
                    {"trade_date": "20240102", "raw_open": 70.0, "raw_high": 71.0, "raw_low": 69.0, "raw_close": 70.0, "m20": 0.8, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240103", "raw_open": 70.0, "raw_high": 71.0, "raw_low": 69.0, "raw_close": 70.0, "m20": 0.8, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            processed_dir = write_processed_dir(base, [stock_a, stock_b])
            config_path = self._write_config(base, processed_dir, buy_shares=300, top_n=2, min_buy_amount=10000, lot_size=100)

            generated = run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240102"))

            planned = {row["股票代码"]: row["计划股数"] for row in generated["pending_order_rows"]}
            self.assertEqual(planned["000001.SZ"], 400)
            self.assertEqual(planned["000002.SZ"], 300)

    def test_list_templates_reads_chinese_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            processed_dir = base / "processed_qfq"
            processed_dir.mkdir()
            config_path = self._write_config(base, processed_dir)
            templates = list_paper_account_templates(config_path.parent)
            self.assertEqual(templates[0]["account_id"], "测试账户")
            self.assertEqual(templates[0]["buy_shares"], 200)

    def test_generate_latest_signal_uses_trade_calendar_next_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240104", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m20": 0.8, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            processed_dir = write_processed_dir(base, [stock])
            pd.DataFrame(
                [
                    {"exchange": "SSE", "trade_date": "20240104", "is_open": "1", "pretrade_date": "20240103"},
                    {"exchange": "SSE", "trade_date": "20240105", "is_open": "1", "pretrade_date": "20240104"},
                ]
            ).to_csv(base / "trade_calendar.csv", index=False)
            config_path = self._write_config(base, processed_dir)

            generated = run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240104"))

            self.assertEqual(generated["summary"]["added_order_count"], 1)
            self.assertEqual(generated["pending_order_rows"][0]["计划执行日期"], "20240105")


if __name__ == "__main__":
    unittest.main()
