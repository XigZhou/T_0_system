from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
import os
from pathlib import Path

import pandas as pd

from overnight_bt.models import SingleStockBacktestRequest
from overnight_bt.single_stock import _resolve_excel_path, run_single_stock_backtest
from tests.helpers import make_processed_stock, write_stock_pool_db, write_stock_pool_template_symbols_db


class SingleStockBacktestTest(unittest.TestCase):
    def _sqlite_request(self, db_path: Path | None, **overrides) -> SingleStockBacktestRequest:
        payload = {
            "data_source": "stock_pool",
            "symbol": "000001",
            "stock_pool_template_name": "test_template",
            "stock_pool_db_path": str(db_path) if db_path is not None else "",
            "start_date": "20240102",
            "end_date": "20240108",
            "buy_condition": "m20>0",
            "buy_confirm_days": 1,
            "buy_cooldown_days": 0,
            "sell_condition": "m20<0",
            "sell_confirm_days": 1,
            "initial_cash": 100000.0,
            "per_trade_budget": 10000.0,
            "lot_size": 100,
            "execution_timing": "next_day_open",
            "buy_fee_rate": 0.0,
            "sell_fee_rate": 0.0,
            "stamp_tax_sell": 0.0,
            "strict_execution": True,
        }
        payload.update(overrides)
        return SingleStockBacktestRequest(**payload)

    def _write_sqlite_stock(self, tmpdir: str, rows: list[dict]) -> Path:
        db_path = Path(tmpdir) / "stock_pool_templates.sqlite"
        frame = make_processed_stock("000001", "Ping An Bank", rows)
        return write_stock_pool_db(db_path, "test_template", [frame])

    def test_run_single_stock_backtest_reads_stock_pool_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = self._write_sqlite_stock(
                tmpdir,
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.9, "raw_close": 10.1, "ma5": 10.05, "ma10": 10.00, "ma20": 9.95, "m20": 0.2, "m10": 0.12, "m5": 0.1},
                    {"trade_date": "20240103", "raw_open": 10.3, "raw_high": 10.5, "raw_low": 10.2, "raw_close": 10.4, "ma5": 10.15, "ma10": 10.08, "ma20": 10.01, "m20": 0.1, "m10": 0.11, "m5": 0.1},
                    {"trade_date": "20240104", "raw_open": 10.6, "raw_high": 10.7, "raw_low": 10.4, "raw_close": 10.5, "ma5": 10.25, "ma10": 10.16, "ma20": 10.04, "m20": -0.1, "m10": -0.02, "m5": -0.1},
                    {"trade_date": "20240105", "raw_open": 10.2, "raw_high": 10.3, "raw_low": 10.0, "raw_close": 10.1, "ma5": 10.20, "ma10": 10.17, "ma20": 10.06, "m20": -0.2, "m10": -0.05, "m5": -0.2},
                ],
            )

            result = run_single_stock_backtest(self._sqlite_request(db_path, end_date="20240105"))

            self.assertEqual(result["stock_code"], "000001")
            self.assertEqual(result["stock_name"], "Ping An Bank")
            self.assertEqual([row["action"] for row in result["trade_rows"]], ["BUY", "SELL"])
            self.assertEqual(result["trade_rows"][0]["trade_date"], "20240103")
            self.assertEqual(result["trade_rows"][1]["trade_date"], "20240105")
            self.assertEqual(result["signal_rows"][0]["ma5"], 10.05)
            self.assertEqual(result["signal_rows"][0]["ma10"], 10.0)
            self.assertEqual(result["signal_rows"][0]["ma20"], 9.95)
            self.assertEqual(result["signal_rows"][0]["m10"], 0.12)
            self.assertEqual(result["signal_rows"][0]["m20"], 0.2)
            self.assertEqual(result["signal_rows"][0]["m5"], 0.1)

    def test_template_stock_list_reads_market_data_by_symbol_and_name(self) -> None:
        from overnight_bt.market_data_store import upsert_feature_rows

        rows = [
            {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.9, "raw_close": 10.1, "ma5": 10.05, "ma10": 10.00, "ma20": 9.95, "m20": 0.2, "m10": 0.12, "m5": 0.1},
            {"trade_date": "20240103", "raw_open": 10.3, "raw_high": 10.5, "raw_low": 10.2, "raw_close": 10.4, "ma5": 10.15, "ma10": 10.08, "ma20": 10.01, "m20": 0.1, "m10": 0.11, "m5": 0.1},
            {"trade_date": "20240104", "raw_open": 10.6, "raw_high": 10.7, "raw_low": 10.4, "raw_close": 10.5, "ma5": 10.25, "ma10": 10.16, "ma20": 10.04, "m20": -0.1, "m10": -0.02, "m5": -0.1},
            {"trade_date": "20240105", "raw_open": 10.2, "raw_high": 10.3, "raw_low": 10.0, "raw_close": 10.1, "ma5": 10.20, "ma10": 10.17, "ma20": 10.06, "m20": -0.2, "m10": -0.05, "m5": -0.2},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            template_db = write_stock_pool_template_symbols_db(
                base / "stock_pool_templates.sqlite",
                "test_template",
                [{"symbol": "000001", "stock_name": "Ping An Bank"}],
            )
            market_db = base / "market_data.sqlite"
            frame = make_processed_stock("000001", "Ping An Bank", rows)
            upsert_feature_rows(frame.to_dict("records"), db_path=market_db)

            with patch("overnight_bt.market_data_store.DEFAULT_DB_PATH", market_db):
                by_symbol = run_single_stock_backtest(self._sqlite_request(template_db, symbol="000001", end_date="20240105"))
                by_name = run_single_stock_backtest(self._sqlite_request(template_db, symbol="Ping An Bank", end_date="20240105"))

            self.assertEqual(by_symbol["stock_code"], "000001")
            self.assertEqual(by_symbol["stock_name"], "Ping An Bank")
            self.assertEqual([row["action"] for row in by_symbol["trade_rows"]], ["BUY", "SELL"])
            self.assertGreaterEqual(len(by_symbol["signal_rows"]), 1)
            self.assertEqual(by_name["stock_code"], "000001")
            self.assertEqual([row["action"] for row in by_name["trade_rows"]], ["BUY", "SELL"])

    def test_stock_pool_default_db_path_resolves_at_runtime(self) -> None:
        from overnight_bt.market_data_store import upsert_feature_rows

        rows = [
            {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.9, "raw_close": 10.1, "ma5": 10.05, "ma10": 10.00, "ma20": 9.95, "m20": 0.2, "m10": 0.12, "m5": 0.1},
            {"trade_date": "20240103", "raw_open": 10.3, "raw_high": 10.5, "raw_low": 10.2, "raw_close": 10.4, "ma5": 10.15, "ma10": 10.08, "ma20": 10.01, "m20": 0.1, "m10": 0.11, "m5": 0.1},
            {"trade_date": "20240104", "raw_open": 10.6, "raw_high": 10.7, "raw_low": 10.4, "raw_close": 10.5, "ma5": 10.25, "ma10": 10.16, "ma20": 10.04, "m20": -0.1, "m10": -0.02, "m5": -0.1},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            template_name = "runtime_default_template"
            stale_db = base / "stale_default.sqlite"
            template_db = write_stock_pool_template_symbols_db(
                base / "stock_pool_templates.sqlite",
                template_name,
                [{"symbol": "000001", "stock_name": "Ping An Bank"}],
            )
            market_db = base / "market_data.sqlite"
            frame = make_processed_stock("000001", "Ping An Bank", rows)
            upsert_feature_rows(frame.to_dict("records"), db_path=market_db)

            with (
                patch("overnight_bt.single_stock.DEFAULT_DB_PATH", stale_db, create=True),
                patch("overnight_bt.stock_pool_templates.DEFAULT_DB_PATH", template_db),
                patch("overnight_bt.market_data_store.DEFAULT_DB_PATH", market_db),
            ):
                result = run_single_stock_backtest(self._sqlite_request(None, stock_pool_template_name=template_name, end_date="20240104"))

            self.assertEqual(result["stock_code"], "000001")
            self.assertFalse(stale_db.exists())

    def test_chart_ohlc_uses_qfq_prices_while_trade_prices_stay_raw(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = self._write_sqlite_stock(
                tmpdir,
                [
                    {
                        "trade_date": "20240102",
                        "raw_open": 10.0,
                        "raw_high": 10.4,
                        "raw_low": 9.8,
                        "raw_close": 10.2,
                        "qfq_open": 20.0,
                        "qfq_high": 20.8,
                        "qfq_low": 19.6,
                        "qfq_close": 20.4,
                        "ma5": 20.2,
                        "ma10": 20.1,
                        "ma20": 20.0,
                        "m20": 0.2,
                    },
                    {
                        "trade_date": "20240103",
                        "raw_open": 11.0,
                        "raw_high": 11.4,
                        "raw_low": 10.8,
                        "raw_close": 11.2,
                        "qfq_open": 22.0,
                        "qfq_high": 22.8,
                        "qfq_low": 21.6,
                        "qfq_close": 22.4,
                        "ma5": 21.4,
                        "ma10": 21.0,
                        "ma20": 20.8,
                        "m20": 0.1,
                    },
                    {
                        "trade_date": "20240104",
                        "raw_open": 12.0,
                        "raw_high": 12.4,
                        "raw_low": 11.8,
                        "raw_close": 12.2,
                        "qfq_open": 24.0,
                        "qfq_high": 24.8,
                        "qfq_low": 23.6,
                        "qfq_close": 24.4,
                        "ma5": 22.4,
                        "ma10": 21.8,
                        "ma20": 21.2,
                        "m20": -0.1,
                    },
                ],
            )

            result = run_single_stock_backtest(self._sqlite_request(db_path, end_date="20240104"))

            self.assertEqual(result["chart_price_basis"], "前复权价格")
            self.assertEqual(result["signal_rows"][0]["open"], 20.0)
            self.assertEqual(result["signal_rows"][0]["high"], 20.8)
            self.assertEqual(result["signal_rows"][0]["low"], 19.6)
            self.assertEqual(result["signal_rows"][0]["close"], 20.4)
            self.assertEqual(result["signal_rows"][1]["open"], 22.0)
            self.assertEqual(result["trade_rows"][0]["price"], 11.0)

    def test_strict_execution_blocks_unsellable_buy_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = self._write_sqlite_stock(
                tmpdir,
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.9, "raw_close": 10.1, "m20": 0.2, "can_buy_open_t": True},
                    {"trade_date": "20240103", "raw_open": 10.3, "raw_high": 10.5, "raw_low": 10.2, "raw_close": 10.4, "m20": 0.1, "can_buy_open_t": False},
                    {"trade_date": "20240104", "raw_open": 10.6, "raw_high": 10.7, "raw_low": 10.4, "raw_close": 10.5, "m20": -0.1, "can_buy_open_t": True},
                ],
            )

            result = run_single_stock_backtest(self._sqlite_request(db_path, end_date="20240104"))

            self.assertEqual(result["trade_rows"][0]["action"], "BUY_BLOCKED")
            self.assertEqual(result["trade_rows"][0]["trade_date"], "20240103")
            self.assertEqual(result["summary"]["blocked_buy_count"], 1)

    def test_strict_execution_retries_blocked_sell_even_when_signal_turns_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = self._write_sqlite_stock(
                tmpdir,
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.9, "raw_close": 10.1, "m20": 0.2},
                    {"trade_date": "20240103", "raw_open": 10.3, "raw_high": 10.5, "raw_low": 10.2, "raw_close": 10.4, "m20": 0.1},
                    {"trade_date": "20240104", "raw_open": 10.6, "raw_high": 10.7, "raw_low": 10.4, "raw_close": 10.5, "m20": -0.1},
                    {"trade_date": "20240105", "raw_open": 10.2, "raw_high": 10.3, "raw_low": 10.0, "raw_close": 10.1, "m20": 0.2, "can_sell_t": False},
                    {"trade_date": "20240108", "raw_open": 9.9, "raw_high": 10.0, "raw_low": 9.8, "raw_close": 9.9, "m20": 0.2, "can_sell_t": True},
                ],
            )

            result = run_single_stock_backtest(self._sqlite_request(db_path))

            self.assertEqual([row["action"] for row in result["trade_rows"]], ["BUY", "SELL_BLOCKED", "SELL"])
            self.assertEqual(result["trade_rows"][-1]["trade_date"], "20240108")
            self.assertEqual(result["summary"]["blocked_sell_count"], 1)

    def test_max_hold_days_forces_sell_when_sell_condition_never_triggers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = self._write_sqlite_stock(
                tmpdir,
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.9, "raw_close": 10.1, "m20": 0.2},
                    {"trade_date": "20240103", "raw_open": 10.3, "raw_high": 10.5, "raw_low": 10.2, "raw_close": 10.4, "m20": 0.2},
                    {"trade_date": "20240104", "raw_open": 10.6, "raw_high": 10.7, "raw_low": 10.4, "raw_close": 10.5, "m20": 0.2},
                    {"trade_date": "20240105", "raw_open": 10.2, "raw_high": 10.3, "raw_low": 10.0, "raw_close": 10.1, "m20": 0.2},
                ],
            )

            result = run_single_stock_backtest(
                self._sqlite_request(db_path, end_date="20240105", sell_condition="m20<0", max_hold_days=2)
            )

            self.assertEqual([row["action"] for row in result["trade_rows"]], ["BUY", "SELL"])
            self.assertEqual(result["trade_rows"][-1]["trade_date"], "20240105")
            self.assertIn("max hold", result["trade_rows"][-1]["reason"])


    def test_single_stock_request_rejects_legacy_csv_mode(self) -> None:
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            SingleStockBacktestRequest(
                data_source="csv",
                symbol="000001",
                buy_condition="m20>0",
            )

    def test_single_stock_requires_symbol_for_sqlite_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "stock code is required"):
            run_single_stock_backtest(
                SingleStockBacktestRequest(
                    excel_path="legacy.xlsx",
                    start_date="20240102",
                    end_date="20240105",
                    buy_condition="m20>0",
                    sell_condition="m20<0",
                )
            )

    def test_windows_runtime_accepts_wsl_style_excel_path(self) -> None:
        if os.name != "nt":
            self.skipTest("WSL mount path compatibility is only meaningful on Windows")

        with tempfile.TemporaryDirectory() as tmpdir:
            excel_path = Path(tmpdir) / "000001_平安银行.xlsx"
            pd.DataFrame(
                [
                    {"trade_date": "20240102", "open": 10.0, "close": 10.1, "m20": 0.2},
                    {"trade_date": "20240103", "open": 10.3, "close": 10.4, "m20": -0.1},
                    {"trade_date": "20240104", "open": 10.2, "close": 10.1, "m20": -0.2},
                ]
            ).to_excel(excel_path, index=False)

            resolved = excel_path.resolve()
            drive = resolved.drive.rstrip(":").lower()
            rest = resolved.relative_to(resolved.anchor).as_posix()
            wsl_style_path = f"/mnt/{drive}/{rest}"

            self.assertEqual(_resolve_excel_path(wsl_style_path), resolved)

            result = run_single_stock_backtest(
                SingleStockBacktestRequest(
                    excel_path=wsl_style_path,
                    start_date="20240102",
                    end_date="20240104",
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


if __name__ == "__main__":
    unittest.main()
