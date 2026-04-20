from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from overnight_bt.tushare_data import SyncConfig, sync_tushare_bundle


class _FakePro:
    def __init__(self) -> None:
        self.stk_limit_calls: list[str] = []
        self.suspend_d_calls: list[str] = []

    def trade_cal(self, **kwargs):
        return pd.DataFrame(
            [
                {"exchange": "", "cal_date": "20240102", "is_open": "1", "pretrade_date": "20240101"},
                {"exchange": "", "cal_date": "20240103", "is_open": "1", "pretrade_date": "20240102"},
            ]
        )

    def index_daily(self, **kwargs):
        return pd.DataFrame(
            [
                {"ts_code": kwargs["ts_code"], "trade_date": "20240102", "open": 10, "high": 10, "low": 10, "close": 10, "vol": 100, "amount": 1000},
                {"ts_code": kwargs["ts_code"], "trade_date": "20240103", "open": 10.1, "high": 10.1, "low": 10.1, "close": 10.1, "vol": 100, "amount": 1000},
            ]
        )

    def daily(self, **kwargs):
        return pd.DataFrame(
            [
                {"ts_code": kwargs["ts_code"], "trade_date": "20240102", "open": 10, "high": 10.2, "low": 9.8, "close": 10, "pre_close": 9.8, "change": 0.2, "pct_chg": 2.04, "vol": 1000, "amount": 10000},
                {"ts_code": kwargs["ts_code"], "trade_date": "20240103", "open": 10.1, "high": 10.3, "low": 10.0, "close": 10.2, "pre_close": 10.0, "change": 0.2, "pct_chg": 2.0, "vol": 1000, "amount": 10000},
            ]
        )

    def adj_factor(self, **kwargs):
        return pd.DataFrame(
            [
                {"ts_code": kwargs["ts_code"], "trade_date": "20240102", "adj_factor": 1.0},
                {"ts_code": kwargs["ts_code"], "trade_date": "20240103", "adj_factor": 1.0},
            ]
        )

    def stk_limit(self, **kwargs):
        self.stk_limit_calls.append(kwargs["ts_code"])
        return pd.DataFrame(
            [
                {"ts_code": kwargs["ts_code"], "trade_date": "20240102", "up_limit": 11.0, "down_limit": 9.0},
                {"ts_code": kwargs["ts_code"], "trade_date": "20240103", "up_limit": 11.2, "down_limit": 9.2},
            ]
        )

    def suspend_d(self, **kwargs):
        self.suspend_d_calls.append(kwargs["ts_code"])
        return pd.DataFrame(columns=["ts_code", "trade_date", "suspend_type", "suspend_timing"])


class TushareDataTest(unittest.TestCase):
    def test_sync_tushare_bundle_fetches_limit_and_suspend_per_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            snapshot_csv = base / "snapshot.csv"
            pd.DataFrame(
                [
                    {"ts_code": "000001.SZ", "symbol": "000001", "name": "平安银行"},
                    {"ts_code": "000002.SZ", "symbol": "000002", "name": "万科A"},
                ]
            ).to_csv(snapshot_csv, index=False, encoding="utf-8-sig")

            fake = _FakePro()
            with patch("overnight_bt.tushare_data._create_pro_client", return_value=fake), patch(
                "overnight_bt.tushare_data.build_market_context_from_indexes",
                return_value=pd.DataFrame({"trade_date": ["20240102", "20240103"], "hs300_pct_chg": [0.1, 0.2]}),
            ), patch("overnight_bt.tushare_data.time.sleep", return_value=None):
                sync_tushare_bundle(
                    SyncConfig(
                        env_path=base / ".env",
                        bundle_dir=base / "bundle",
                        snapshot_csv=snapshot_csv,
                        start_date="20240101",
                        end_date="20240103",
                        sleep_seconds=0.0,
                    )
                )

            self.assertEqual(fake.stk_limit_calls, ["000001.SZ", "000002.SZ"])
            self.assertEqual(fake.suspend_d_calls, ["000001.SZ", "000002.SZ"])

            stk_limit = pd.read_csv(base / "bundle" / "stk_limit.csv", encoding="utf-8-sig", dtype=str)
            suspend_d = pd.read_csv(base / "bundle" / "suspend_d.csv", encoding="utf-8-sig", dtype=str)
            self.assertEqual(len(stk_limit), 4)
            self.assertEqual(sorted(stk_limit["ts_code"].unique().tolist()), ["000001.SZ", "000002.SZ"])
            self.assertEqual(len(suspend_d), 0)


if __name__ == "__main__":
    unittest.main()
