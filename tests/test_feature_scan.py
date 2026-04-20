from __future__ import annotations

import unittest

import pandas as pd

from overnight_bt.feature_scan import FeatureBucketSpec, apply_research_net_return, build_feature_bucket_report


class FeatureScanTest(unittest.TestCase):
    def test_apply_research_net_return_is_lower_than_raw(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "entry_raw_open": 10.0,
                    "exit_raw_open": 10.2,
                }
            ]
        )
        enriched = apply_research_net_return(
            frame,
            buy_fee_rate=0.0003,
            sell_fee_rate=0.0003,
            stamp_tax_sell=0.001,
            slippage_bps=2.0,
        )
        self.assertAlmostEqual(float(enriched.loc[0, "holding_return_raw"]), 0.02, places=6)
        self.assertLess(float(enriched.loc[0, "holding_return_net"]), float(enriched.loc[0, "holding_return_raw"]))

    def test_build_feature_bucket_report_summarizes_buckets(self) -> None:
        frame = pd.DataFrame(
            [
                {"close_pos_in_bar": 0.2, "holding_return_raw": -0.01, "holding_return_net": -0.012},
                {"close_pos_in_bar": 0.4, "holding_return_raw": 0.00, "holding_return_net": -0.002},
                {"close_pos_in_bar": 0.8, "holding_return_raw": 0.02, "holding_return_net": 0.018},
                {"close_pos_in_bar": 0.9, "holding_return_raw": 0.03, "holding_return_net": 0.028},
            ]
        )
        report = build_feature_bucket_report(
            frame,
            specs=[
                FeatureBucketSpec(
                    feature="close_pos_in_bar",
                    bins=(0.0, 0.5, 1.0),
                    labels=("low", "high"),
                )
            ],
            min_count=1,
        )
        self.assertEqual(report["bucket"].tolist(), ["low", "high"])
        self.assertEqual(report["sample_count"].tolist(), [2, 2])
        self.assertAlmostEqual(float(report.loc[report["bucket"] == "high", "avg_holding_return_raw"].iloc[0]), 0.025, places=6)
        self.assertAlmostEqual(float(report.loc[report["bucket"] == "low", "win_rate_raw"].iloc[0]), 0.0, places=6)
