from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from overnight_bt.processing import build_processed_frame, validate_processed_frame


class ProcessingTest(unittest.TestCase):
    def test_build_processed_frame_generates_qfq_and_constraints(self) -> None:
        raw_df = pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20240102",
                    "open": 10,
                    "high": 10.2,
                    "low": 9.9,
                    "close": 10.0,
                    "pre_close": 9.8,
                    "change": 0.2,
                    "pct_chg": 2.04,
                    "vol": 1000,
                    "amount": 10000,
                },
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20240104",
                    "open": 12,
                    "high": 12.3,
                    "low": 11.8,
                    "close": 12.0,
                    "pre_close": 10.0,
                    "change": 2.0,
                    "pct_chg": 20.0,
                    "vol": 1200,
                    "amount": 12000,
                },
            ]
        )
        adj_df = pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "20240102", "adj_factor": 1.0},
                {"ts_code": "000001.SZ", "trade_date": "20240104", "adj_factor": 1.2},
            ]
        )
        snapshot_row = pd.Series(
            {
                "ts_code": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "industry": "银行",
                "market": "主板",
                "list_date": "20000101",
                "total_mv": "8000000",
                "turnover_rate_f": "1.5",
            }
        )
        trade_calendar = pd.DataFrame({"trade_date": ["20240102", "20240103", "20240104"]})
        limit_df = pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "20240102", "up_limit": 11.0, "down_limit": 9.0},
                {"ts_code": "000001.SZ", "trade_date": "20240104", "up_limit": 13.2, "down_limit": 10.8},
            ]
        )
        suspend_df = pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": "20240103"}])
        market_context = pd.DataFrame({"trade_date": ["20240102", "20240103", "20240104"], "hs300_pct_chg": [0.1, 0.0, 0.2]})

        frame = build_processed_frame(
            raw_df=raw_df,
            adj_df=adj_df,
            snapshot_row=snapshot_row,
            trade_calendar=trade_calendar,
            limit_df=limit_df,
            suspend_df=suspend_df,
            market_context=market_context,
            start_date="20240102",
            end_date="20240104",
        )
        validate_processed_frame(frame)
        self.assertEqual(len(frame), 3)
        self.assertAlmostEqual(float(frame.loc[frame["trade_date"] == "20240102", "qfq_close"].iloc[0]), 8.3333, places=4)
        self.assertTrue(bool(frame.loc[frame["trade_date"] == "20240103", "is_suspended_t"].iloc[0]))
        self.assertFalse(bool(frame.loc[frame["trade_date"] == "20240102", "can_sell_t1"].iloc[0]))
        self.assertEqual(int(frame.loc[frame["trade_date"] == "20240102", "listed_days"].iloc[0]), 8767)

    def test_build_processed_frame_blocks_buy_on_down_limit_open(self) -> None:
        raw_df = pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20240102",
                    "open": 9.0,
                    "high": 9.1,
                    "low": 8.9,
                    "close": 9.0,
                    "pre_close": 10.0,
                    "change": -1.0,
                    "pct_chg": -10.0,
                    "vol": 1000,
                    "amount": 10000,
                },
            ]
        )
        adj_df = pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": "20240102", "adj_factor": 1.0}])
        snapshot_row = pd.Series(
            {
                "ts_code": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "industry": "银行",
                "market": "主板",
                "list_date": "20000101",
                "total_mv": "8000000",
                "turnover_rate_f": "1.5",
            }
        )
        trade_calendar = pd.DataFrame({"trade_date": ["20240102"]})
        limit_df = pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": "20240102", "up_limit": 11.0, "down_limit": 9.0}])
        suspend_df = pd.DataFrame(columns=["ts_code", "trade_date"])
        market_context = pd.DataFrame({"trade_date": ["20240102"], "hs300_pct_chg": [0.1]})

        frame = build_processed_frame(
            raw_df=raw_df,
            adj_df=adj_df,
            snapshot_row=snapshot_row,
            trade_calendar=trade_calendar,
            limit_df=limit_df,
            suspend_df=suspend_df,
            market_context=market_context,
            start_date="20240102",
            end_date="20240102",
        )
        row = frame.iloc[0]
        self.assertFalse(bool(row["can_buy_open_t"]))
        self.assertFalse(bool(row["can_buy_t"]))

    def test_build_processed_frame_generates_overnight_research_features(self) -> None:
        raw_df = pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20240102",
                    "open": 10.0,
                    "high": 10.4,
                    "low": 9.8,
                    "close": 10.3,
                    "pre_close": 9.9,
                    "change": 0.4,
                    "pct_chg": 4.04,
                    "vol": 1000,
                    "amount": 10000,
                },
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20240103",
                    "open": 10.5,
                    "high": 10.8,
                    "low": 10.4,
                    "close": 10.7,
                    "pre_close": 10.3,
                    "change": 0.4,
                    "pct_chg": 3.88,
                    "vol": 1100,
                    "amount": 11000,
                },
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20240104",
                    "open": 10.8,
                    "high": 11.0,
                    "low": 10.7,
                    "close": 10.9,
                    "pre_close": 10.7,
                    "change": 0.2,
                    "pct_chg": 1.87,
                    "vol": 1200,
                    "amount": 12000,
                },
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20240105",
                    "open": 11.0,
                    "high": 11.1,
                    "low": 10.9,
                    "close": 11.0,
                    "pre_close": 10.9,
                    "change": 0.1,
                    "pct_chg": 0.92,
                    "vol": 1300,
                    "amount": 13000,
                },
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20240108",
                    "open": 11.0,
                    "high": 11.3,
                    "low": 10.9,
                    "close": 11.2,
                    "pre_close": 11.0,
                    "change": 0.2,
                    "pct_chg": 1.82,
                    "vol": 1400,
                    "amount": 14000,
                },
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20240109",
                    "open": 11.3,
                    "high": 11.5,
                    "low": 11.2,
                    "close": 11.4,
                    "pre_close": 11.2,
                    "change": 0.2,
                    "pct_chg": 1.79,
                    "vol": 1500,
                    "amount": 15000,
                },
            ]
        )
        adj_df = pd.DataFrame(
            [{"ts_code": "000001.SZ", "trade_date": row["trade_date"], "adj_factor": 1.0} for row in raw_df.to_dict(orient="records")]
        )
        snapshot_row = pd.Series(
            {
                "ts_code": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "industry": "银行",
                "market": "主板",
                "list_date": "20000101",
                "total_mv": "8000000",
                "turnover_rate_f": "1.5",
            }
        )
        trade_calendar = pd.DataFrame({"trade_date": raw_df["trade_date"].tolist()})
        limit_df = pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "20240102", "up_limit": 11.33, "down_limit": 9.27},
                {"ts_code": "000001.SZ", "trade_date": "20240103", "up_limit": 11.77, "down_limit": 9.63},
                {"ts_code": "000001.SZ", "trade_date": "20240104", "up_limit": 11.99, "down_limit": 9.81},
                {"ts_code": "000001.SZ", "trade_date": "20240105", "up_limit": 12.10, "down_limit": 9.90},
                {"ts_code": "000001.SZ", "trade_date": "20240108", "up_limit": 12.32, "down_limit": 10.08},
                {"ts_code": "000001.SZ", "trade_date": "20240109", "up_limit": 12.54, "down_limit": 10.26},
            ]
        )
        suspend_df = pd.DataFrame(columns=["ts_code", "trade_date"])
        market_context = pd.DataFrame({"trade_date": raw_df["trade_date"].tolist(), "hs300_pct_chg": [0.1] * len(raw_df)})

        frame = build_processed_frame(
            raw_df=raw_df,
            adj_df=adj_df,
            snapshot_row=snapshot_row,
            trade_calendar=trade_calendar,
            limit_df=limit_df,
            suspend_df=suspend_df,
            market_context=market_context,
            start_date="20240102",
            end_date="20240109",
        )

        row = frame.loc[frame["trade_date"] == "20240102"].iloc[0]
        self.assertAlmostEqual(float(row["next_raw_open"]), 10.5, places=6)
        self.assertAlmostEqual(float(row["next_raw_close"]), 10.7, places=6)
        self.assertAlmostEqual(float(row["r_on_raw"]), 10.5 / 10.3 - 1.0, places=6)
        self.assertAlmostEqual(float(row["close_to_up_limit"]), 10.3 / 11.33, places=6)
        self.assertAlmostEqual(float(row["high_to_up_limit"]), 10.4 / 11.33, places=6)
        self.assertAlmostEqual(float(row["close_pos_in_bar"]), (10.3 - 9.8) / (10.4 - 9.8), places=6)
        self.assertAlmostEqual(float(row["body_pct"]), (10.3 - 10.0) / 10.0, places=6)
        self.assertAlmostEqual(float(row["upper_shadow_pct"]), (10.4 - 10.3) / 10.0, places=6)
        self.assertAlmostEqual(float(row["lower_shadow_pct"]), (10.0 - 9.8) / 10.0, places=6)

        row_last = frame.loc[frame["trade_date"] == "20240109"].iloc[0]
        self.assertTrue(pd.isna(row_last["next_raw_open"]))
        self.assertAlmostEqual(float(row_last["vol_ratio_5"]), 1500.0 / 1300.0, places=6)

    def test_build_processed_frame_generates_short_cycle_v4_features(self) -> None:
        raw_df = pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "20240102", "open": 10.0, "high": 10.4, "low": 9.8, "close": 10.3, "pre_close": 9.9, "change": 0.4, "pct_chg": 4.04, "vol": 1000, "amount": 10000},
                {"ts_code": "000001.SZ", "trade_date": "20240103", "open": 10.5, "high": 10.8, "low": 10.4, "close": 10.7, "pre_close": 10.3, "change": 0.4, "pct_chg": 3.88, "vol": 1100, "amount": 11000},
                {"ts_code": "000001.SZ", "trade_date": "20240104", "open": 10.8, "high": 11.0, "low": 10.7, "close": 10.9, "pre_close": 10.7, "change": 0.2, "pct_chg": 1.87, "vol": 1200, "amount": 12000},
                {"ts_code": "000001.SZ", "trade_date": "20240105", "open": 11.0, "high": 11.1, "low": 10.9, "close": 11.0, "pre_close": 10.9, "change": 0.1, "pct_chg": 0.92, "vol": 1300, "amount": 13000},
                {"ts_code": "000001.SZ", "trade_date": "20240108", "open": 11.0, "high": 11.3, "low": 10.9, "close": 11.2, "pre_close": 11.0, "change": 0.2, "pct_chg": 1.82, "vol": 1400, "amount": 14000},
                {"ts_code": "000001.SZ", "trade_date": "20240109", "open": 11.3, "high": 11.5, "low": 11.2, "close": 11.4, "pre_close": 11.2, "change": 0.2, "pct_chg": 1.79, "vol": 1500, "amount": 15000},
            ]
        )
        adj_df = pd.DataFrame(
            [{"ts_code": "000001.SZ", "trade_date": row["trade_date"], "adj_factor": 1.0} for row in raw_df.to_dict(orient="records")]
        )
        snapshot_row = pd.Series(
            {
                "ts_code": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "industry": "银行",
                "market": "主板",
                "list_date": "20000101",
                "total_mv": "8000000",
                "turnover_rate_f": "1.5",
            }
        )
        trade_calendar = pd.DataFrame({"trade_date": raw_df["trade_date"].tolist()})
        limit_df = pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "20240102", "up_limit": 11.33, "down_limit": 9.27},
                {"ts_code": "000001.SZ", "trade_date": "20240103", "up_limit": 11.50, "down_limit": 9.63},
                {"ts_code": "000001.SZ", "trade_date": "20240104", "up_limit": 11.10, "down_limit": 9.81},
                {"ts_code": "000001.SZ", "trade_date": "20240105", "up_limit": 11.20, "down_limit": 9.90},
                {"ts_code": "000001.SZ", "trade_date": "20240108", "up_limit": 12.32, "down_limit": 10.08},
                {"ts_code": "000001.SZ", "trade_date": "20240109", "up_limit": 12.54, "down_limit": 10.26},
            ]
        )
        suspend_df = pd.DataFrame(columns=["ts_code", "trade_date"])
        market_context = pd.DataFrame({"trade_date": raw_df["trade_date"].tolist(), "hs300_pct_chg": [0.1] * len(raw_df)})

        frame = build_processed_frame(
            raw_df=raw_df,
            adj_df=adj_df,
            snapshot_row=snapshot_row,
            trade_calendar=trade_calendar,
            limit_df=limit_df,
            suspend_df=suspend_df,
            market_context=market_context,
            start_date="20240102",
            end_date="20240109",
        )

        row_0404 = frame.loc[frame["trade_date"] == "20240104"].iloc[0]
        self.assertAlmostEqual(float(row_0404["vol_ratio_3"]), 1200.0 / 1100.0, places=6)
        self.assertAlmostEqual(float(row_0404["amount_ratio_3"]), 12000.0 / 11000.0, places=6)
        self.assertAlmostEqual(float(row_0404["body_pct_3avg"]), ((10.3 - 10.0) / 10.0 + (10.7 - 10.5) / 10.5 + (10.9 - 10.8) / 10.8) / 3.0, places=6)
        self.assertAlmostEqual(float(row_0404["close_to_up_limit_3max"]), 10.9 / 11.10, places=6)

        row_0405 = frame.loc[frame["trade_date"] == "20240105"].iloc[0]
        expected_ret3 = round(11.0 / 10.3 - 1.0, 4)
        expected_ret1 = round(11.0 / 10.9 - 1.0, 4)
        self.assertAlmostEqual(float(row_0405["ret_accel_3"]), expected_ret1 - expected_ret3 / 3.0, places=6)


if __name__ == "__main__":
    unittest.main()
