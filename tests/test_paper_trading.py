from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from overnight_bt.models import PaperTemplateSaveRequest, PaperTradingRunRequest
from overnight_bt.paper_trading import (
    PriceQuote,
    delete_paper_account_template,
    list_paper_account_templates,
    read_paper_account_template,
    read_paper_trading_ledger,
    run_paper_trading,
    save_paper_account_template,
)
from tests.helpers import make_processed_stock, write_stock_pool_db, write_stock_pool_template_symbols_db


class PaperTradingTest(unittest.TestCase):
    def _one_stock(self) -> pd.DataFrame:
        return make_processed_stock(
            "000001",
            "平安银行",
            [
                {
                    "trade_date": "20240102",
                    "raw_open": 10.0,
                    "raw_high": 10.2,
                    "raw_low": 9.8,
                    "raw_close": 10.0,
                    "m20": 0.8,
                    "can_buy_open_t": True,
                    "can_sell_t": True,
                }
            ],
        )

    def _write_config(
        self,
        base: Path,
        db_path: Path,
        initial_capital: float = 100000,
        buy_shares: int = 200,
        top_n: int = 1,
        min_buy_amount: float = 0,
        lot_size: int = 100,
        min_close: float = 0,
        max_close: float = 0,
        seed_market_data_from_template: bool = True,
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
股票池:
  用户: admin
  模板名称: 测试股票池
  数据库路径: {db_path.as_posix()}
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
        if seed_market_data_from_template:
            self._seed_market_data_from_template_db(base, db_path)
        return config_path


    def _seed_market_data_from_template_db(self, base: Path, template_db: Path) -> None:
        try:
            with sqlite3.connect(template_db) as conn:
                rows = pd.read_sql_query("SELECT * FROM stock_daily_features", conn)
        except Exception:
            return
        if rows.empty:
            return
        from overnight_bt.market_data_store import upsert_feature_rows

        market_db = base / "data_store" / "market_data.sqlite"
        payload = rows.astype(object).where(pd.notna(rows), None).to_dict("records")
        upsert_feature_rows(payload, db_path=market_db)
        old_value = os.environ.get("MARKET_DATA_DB_PATH")
        os.environ["MARKET_DATA_DB_PATH"] = str(market_db)

        def restore_env() -> None:
            if old_value is None:
                os.environ.pop("MARKET_DATA_DB_PATH", None)
            else:
                os.environ["MARKET_DATA_DB_PATH"] = old_value

        self.addCleanup(restore_env)

    def _sqlite_count(self, path: Path, table: str, account_id: str) -> int:
        with sqlite3.connect(path) as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE account_id=?", (account_id,)).fetchone()
        return int(row[0])

    def test_generate_execute_sell_and_sqlite_ledger(self) -> None:
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
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "测试股票池", [stock_a, stock_b])
            config_path = self._write_config(base, db_path)

            generated = run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240102"))
            self.assertEqual(generated["summary"]["added_order_count"], 1)
            self.assertEqual(generated["pending_order_rows"][0]["订单方向"], "买入")
            self.assertEqual(generated["summary"]["stock_pool_template_name"], "测试股票池")

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
            self.assertEqual(ledger_path.name, "paper_trading.sqlite")
            with sqlite3.connect(ledger_path) as conn:
                table_names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
            for table_name in [
                "paper_config_snapshot",
                "paper_pending_orders",
                "paper_trades",
                "paper_holdings",
                "paper_assets",
                "paper_logs",
                "paper_account_ledgers",
            ]:
                self.assertIn(table_name, table_names)
            self.assertGreater(self._sqlite_count(ledger_path, "paper_config_snapshot", "测试账户"), 0)
            self.assertGreaterEqual(self._sqlite_count(ledger_path, "paper_pending_orders", "测试账户"), 2)
            self.assertEqual(self._sqlite_count(ledger_path, "paper_trades", "测试账户"), 2)
            self.assertEqual(self._sqlite_count(ledger_path, "paper_holdings", "测试账户"), 0)
            self.assertGreaterEqual(self._sqlite_count(ledger_path, "paper_assets", "测试账户"), 1)
            self.assertGreaterEqual(self._sqlite_count(ledger_path, "paper_logs", "测试账户"), 1)

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
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "测试股票池", [stock_a, stock_b])
            config_path = self._write_config(base, db_path, initial_capital=1000, buy_shares=100)

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
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "测试股票池", [stock])
            config_path = self._write_config(base, db_path)

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
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "测试股票池", [high_price, normal_price])
            config_path = self._write_config(base, db_path, max_close=100)

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
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "测试股票池", [stock_a, stock_b])
            config_path = self._write_config(base, db_path, buy_shares=300, top_n=2, min_buy_amount=10000, lot_size=100)

            generated = run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240102"))

            planned = {row["股票代码"]: row["计划股数"] for row in generated["pending_order_rows"]}
            self.assertEqual(planned["000001.SZ"], 400)
            self.assertEqual(planned["000002.SZ"], 300)

    def test_list_templates_reads_chinese_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "测试股票池", [self._one_stock()])
            config_path = self._write_config(base, db_path)
            templates = list_paper_account_templates(config_path.parent)
            self.assertEqual(templates[0]["account_id"], "测试账户")
            self.assertEqual(templates[0]["stock_pool_template_name"], "测试股票池")
            self.assertEqual(templates[0]["buy_shares"], 200)


    def test_sqlite_only_does_not_auto_import_legacy_yaml_when_sqlite_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "测试股票池", [self._one_stock()])
            config_path = self._write_config(base, db_path)
            old_value = os.environ.get("T0_SQLITE_ONLY")
            os.environ["T0_SQLITE_ONLY"] = "1"
            try:
                templates = list_paper_account_templates(config_path.parent)
            finally:
                if old_value is None:
                    os.environ.pop("T0_SQLITE_ONLY", None)
                else:
                    os.environ["T0_SQLITE_ONLY"] = old_value

            self.assertEqual(templates, [])

    def test_sqlite_only_filters_previously_imported_legacy_yaml_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "测试股票池", [self._one_stock()])
            config_path = self._write_config(base, db_path)
            legacy_templates = list_paper_account_templates(config_path.parent)
            self.assertEqual([item["account_id"] for item in legacy_templates], ["测试账户"])

            save_paper_account_template(
                PaperTemplateSaveRequest(
                    config_dir=str(config_path.parent),
                    account_id="sqlite_account",
                    account_name="SQLite账户",
                    stock_pool_username="admin",
                    stock_pool_template_name="测试股票池",
                    stock_pool_db_path=str(db_path),
                    buy_condition="m20>0",
                    score_expression="m20",
                )
            )

            old_value = os.environ.get("T0_SQLITE_ONLY")
            os.environ["T0_SQLITE_ONLY"] = "1"
            try:
                templates = list_paper_account_templates(config_path.parent)
            finally:
                if old_value is None:
                    os.environ.pop("T0_SQLITE_ONLY", None)
                else:
                    os.environ["T0_SQLITE_ONLY"] = old_value

            self.assertEqual([item["account_id"] for item in templates], ["sqlite_account"])

    def test_list_templates_does_not_reimport_legacy_yaml_when_sqlite_has_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "\u8fc1\u79fb\u6d4b\u8bd5\u6c60", [self._one_stock()])
            config_path = self._write_config(base, db_path)
            save_paper_account_template(
                PaperTemplateSaveRequest(
                    config_dir=str(config_path.parent),
                    account_id="sqlite_account",
                    account_name="SQLite\u8d26\u6237",
                    stock_pool_username="admin",
                    stock_pool_template_name="\u8fc1\u79fb\u6d4b\u8bd5\u6c60",
                    stock_pool_db_path=str(db_path),
                    buy_condition="m20>0",
                    score_expression="m20",
                )
            )

            templates = list_paper_account_templates(config_path.parent)

            self.assertEqual([item["account_id"] for item in templates], ["sqlite_account"])

    def test_generate_latest_signal_falls_back_to_next_weekday_when_template_has_no_next_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240104", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m20": 0.8, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "测试股票池", [stock])
            config_path = self._write_config(base, db_path)

            generated = run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240104"))

            self.assertEqual(generated["summary"]["added_order_count"], 1)
            self.assertEqual(generated["pending_order_rows"][0]["计划执行日期"], "20240105")

    def test_generate_signal_date_skips_empty_latest_feature_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240104", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m20": 0.8, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240105", "raw_open": None, "raw_high": None, "raw_low": None, "raw_close": None, "m20": None, "can_buy_open_t": False, "can_sell_t": False},
                ],
            )
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "测试股票池", [stock])
            config_path = self._write_config(base, db_path)

            generated = run_paper_trading(PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240105"))

            self.assertEqual(generated["summary"]["signal_date"], "20240104")
            self.assertEqual(generated["summary"]["added_order_count"], 1)
            self.assertEqual(generated["pending_order_rows"][0]["信号日期"], "20240104")
            self.assertEqual(generated["pending_order_rows"][0]["计划执行日期"], "20240105")

    def test_after_close_generates_orders_from_market_data_store_when_template_has_only_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            template_db = write_stock_pool_template_symbols_db(
                base / "stock_pool_templates.sqlite",
                "测试股票池",
                [{"symbol": "000001", "stock_name": "平安银行"}],
            )
            market_db = base / "market_data.sqlite"
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
                        "m20": 0.8,
                        "can_buy_open_t": True,
                        "can_sell_t": True,
                    }
                ],
            )
            rows = stock.astype(object).where(pd.notna(stock), None).to_dict("records")
            config_path = self._write_config(base, template_db)

            from overnight_bt.market_data_store import upsert_feature_rows

            upsert_feature_rows(rows, db_path=market_db)

            with patch("overnight_bt.market_data_store.DEFAULT_DB_PATH", market_db):
                generated = run_paper_trading(
                    PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240102")
                )

            self.assertEqual(generated["summary"]["signal_date"], "20240102")
            self.assertEqual(generated["summary"]["added_order_count"], 1)
            self.assertEqual(generated["pending_order_rows"][0]["股票代码"], "000001.SZ")
            self.assertEqual(generated["pending_order_rows"][0]["计划执行日期"], "20240103")

    def test_after_close_does_not_fall_back_to_template_feature_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stale_stock = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {
                        "trade_date": "20240102",
                        "raw_open": 10.0,
                        "raw_high": 10.2,
                        "raw_low": 9.8,
                        "raw_close": 10.0,
                        "m20": 0.8,
                        "can_buy_open_t": True,
                        "can_sell_t": True,
                    }
                ],
            )
            template_db = write_stock_pool_db(base / "stock_pool_templates.sqlite", "测试股票池", [stale_stock])
            market_db = base / "empty_market_data.sqlite"
            config_path = self._write_config(base, template_db, seed_market_data_from_template=False)

            with patch("overnight_bt.market_data_store.DEFAULT_DB_PATH", market_db), patch(
                "overnight_bt.market_data_store.LEGACY_STOCK_POOL_DB_PATH", template_db
            ), patch.dict(os.environ, {"MARKET_DATA_DB_PATH": str(market_db)}):
                with self.assertRaises(ValueError) as ctx:
                    run_paper_trading(
                        PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240102")
                    )

            self.assertIn("没有可用日线数据", str(ctx.exception))

    def test_market_data_db_env_is_used_for_paper_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            template_db = write_stock_pool_template_symbols_db(
                base / "stock_pool_templates.sqlite",
                "测试股票池",
                [{"symbol": "000001", "stock_name": "平安银行"}],
            )
            env_market_db = base / "env_market_data.sqlite"
            default_market_db = base / "empty_default_market_data.sqlite"
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
                        "m20": 0.8,
                        "can_buy_open_t": True,
                        "can_sell_t": True,
                    }
                ],
            )
            rows = stock.astype(object).where(pd.notna(stock), None).to_dict("records")
            config_path = self._write_config(base, template_db)

            from overnight_bt.market_data_store import upsert_feature_rows

            upsert_feature_rows(rows, db_path=env_market_db)

            with patch("overnight_bt.market_data_store.DEFAULT_DB_PATH", default_market_db), patch.dict(
                os.environ, {"MARKET_DATA_DB_PATH": str(env_market_db)}
            ):
                generated = run_paper_trading(
                    PaperTradingRunRequest(config_path=str(config_path), action="generate", trade_date="20240102")
                )

            self.assertEqual(generated["summary"]["added_order_count"], 1)
            self.assertEqual(generated["pending_order_rows"][0]["股票代码"], "000001.SZ")

    def test_save_template_writes_sqlite_and_reads_editor_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_dir = base / "configs" / "paper_accounts"
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "测试股票池", [self._one_stock()])
            result = save_paper_account_template(
                PaperTemplateSaveRequest(
                    config_dir=str(config_dir),
                    file_name="editor_account.yaml",
                    account_id="编辑账户",
                    account_name="编辑模拟账户",
                    stock_pool_username="admin",
                    stock_pool_template_name="测试股票池",
                    stock_pool_db_path=str(db_path),
                    buy_condition="m20>0.1",
                    sell_condition="m20<0",
                    score_expression="m20",
                    ledger_path=str(base / "paper_trading" / "accounts" / "editor_account.xlsx"),
                    log_dir=str(base / "paper_trading" / "logs"),
                )
            )

            self.assertEqual(result["template"]["config_path"], "编辑账户")
            self.assertEqual(result["template"]["ledger_storage"], "SQLite")
            self.assertEqual(Path(result["template"]["ledger_path"]), base / "data_store" / "paper_trading.sqlite")
            loaded = read_paper_account_template(account_id="编辑账户", config_dir=str(config_dir))
            self.assertEqual(loaded["account_id"], "编辑账户")
            self.assertEqual(loaded["stock_pool_template_name"], "测试股票池")
            self.assertEqual(loaded["buy_condition"], "m20>0.1")
            self.assertEqual(loaded["ledger_storage"], "SQLite")
            self.assertEqual(Path(loaded["ledger_path"]), base / "data_store" / "paper_trading.sqlite")

    def test_save_template_rejects_conflicting_identity_and_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "测试股票池", [self._one_stock()])
            existing = self._write_config(base, db_path)
            config_dir = existing.parent
            list_paper_account_templates(config_dir)

            with self.assertRaises(ValueError):
                save_paper_account_template(
                    PaperTemplateSaveRequest(
                        config_dir=str(config_dir),
                        file_name="duplicate_id.yaml",
                        account_id="测试账户",
                        account_name="另一个账户",
                        stock_pool_username="admin",
                        stock_pool_template_name="测试股票池",
                        stock_pool_db_path=str(db_path),
                        buy_condition="m20>0",
                        score_expression="m20",
                        ledger_path=str(base / "paper_trading" / "accounts" / "duplicate_id.xlsx"),
                    )
                )

            with self.assertRaises(ValueError):
                save_paper_account_template(
                    PaperTemplateSaveRequest(
                        config_dir=str(config_dir),
                        file_name="duplicate_name.yaml",
                        account_id="新账户",
                        account_name="测试模拟账户",
                        stock_pool_username="admin",
                        stock_pool_template_name="测试股票池",
                        stock_pool_db_path=str(db_path),
                        buy_condition="m20>0",
                        score_expression="m20",
                        ledger_path=str(base / "paper_trading" / "accounts" / "ignored.xlsx"),
                    )
                )

    def test_delete_template_deactivates_sqlite_template_and_keeps_legacy_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "测试股票池", [self._one_stock()])
            config_path = self._write_config(base, db_path)
            ledger_path = base / "paper_trading" / "accounts" / "test_account.xlsx"
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            ledger_path.write_bytes(b"ledger placeholder")

            result = delete_paper_account_template(str(config_path), str(config_path.parent))

            self.assertTrue(config_path.exists())
            self.assertTrue(ledger_path.exists())
            self.assertEqual(result["ledger_storage"], "SQLite")
            self.assertFalse(result["ledger_exists"])
            self.assertEqual(list_paper_account_templates(config_path.parent), [])
            with self.assertRaises(FileNotFoundError):
                read_paper_account_template(account_id="测试账户", config_dir=str(config_path.parent))

    def test_overwrite_template_ignores_old_ledger_path_and_keeps_sqlite_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "测试股票池", [self._one_stock()])
            config_path = self._write_config(base, db_path)
            old_ledger = base / "paper_trading" / "accounts" / "old_strategy.xlsx"
            old_ledger.parent.mkdir(parents=True, exist_ok=True)
            old_ledger.write_bytes(b"old ledger")

            result = save_paper_account_template(
                PaperTemplateSaveRequest(
                    config_dir=str(config_path.parent),
                    config_path=str(config_path),
                    file_name=config_path.name,
                    overwrite_existing=True,
                    account_id="测试账户",
                    account_name="测试模拟账户",
                    stock_pool_username="admin",
                    stock_pool_template_name="测试股票池",
                    stock_pool_db_path=str(db_path),
                    buy_condition="m20>0",
                    score_expression="m20",
                    ledger_path=str(old_ledger),
                )
            )
            self.assertEqual(result["template"]["ledger_storage"], "SQLite")
            self.assertEqual(Path(result["template"]["ledger_path"]), base / "data_store" / "paper_trading.sqlite")
            self.assertEqual(old_ledger.read_bytes(), b"old ledger")


if __name__ == "__main__":
    unittest.main()
