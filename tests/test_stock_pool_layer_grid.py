from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_stock_pool_layer_grid import build_layer_constituents, summarize_layer_constituents
from tests.helpers import make_processed_stock


def _rows(total_mv: float) -> list[dict]:
    return [
        {
            "trade_date": "20240102",
            "raw_open": 10.0,
            "raw_high": 10.5,
            "raw_low": 9.8,
            "raw_close": 10.2,
            "total_mv_snapshot": total_mv,
        }
    ]


class StockPoolLayerGridTest(unittest.TestCase):
    def test_build_layer_constituents_uses_backtestable_theme_intersection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            processed = root / "processed"
            processed.mkdir()
            for symbol, name, total_mv in [
                ("000001", "大市值AI", 5000.0),
                ("000002", "中市值锂电", 3000.0),
                ("000003", "小市值医药", 1000.0),
                ("000004", "无主题股票", 8000.0),
            ]:
                make_processed_stock(symbol, name, _rows(total_mv)).to_csv(processed / f"{symbol}.csv", index=False, encoding="utf-8-sig")
            exposure = pd.DataFrame(
                [
                    {"stock_code": "000001", "stock_name": "大市值AI", "theme_names": "AI", "primary_theme": "AI", "exposure_score": 1.0},
                    {"stock_code": "000002", "stock_name": "中市值锂电", "theme_names": "锂矿锂电", "primary_theme": "锂矿锂电", "exposure_score": 0.8},
                    {"stock_code": "000003", "stock_name": "小市值医药", "theme_names": "医药", "primary_theme": "医药", "exposure_score": 0.6},
                    {"stock_code": "000099", "stock_name": "无行情股票", "theme_names": "机器人", "primary_theme": "机器人", "exposure_score": 0.5},
                ]
            )
            exposure_path = root / "stock_theme_exposure.csv"
            exposure.to_csv(exposure_path, index=False, encoding="utf-8-sig")

            constituents = build_layer_constituents(
                processed_dir=processed,
                exposure_path=exposure_path,
                layer_count=3,
                layer_method="quantile",
            )

            self.assertEqual(constituents["symbol"].tolist(), ["000001", "000002", "000003"])
            self.assertEqual(constituents["layer"].tolist(), ["L0", "L1", "L2"])
            self.assertEqual(constituents["market_cap_rank"].tolist(), [1, 2, 3])

    def test_summarize_layer_constituents_counts_multi_theme_hits(self) -> None:
        frame = pd.DataFrame(
            [
                {"layer": "L0", "layer_name": "最大市值主题股层", "market_cap_rank": 1, "total_mv_snapshot": 100.0, "theme_names": "AI、半导体芯片", "primary_theme": "AI", "exposure_score": 1.0},
                {"layer": "L0", "layer_name": "最大市值主题股层", "market_cap_rank": 2, "total_mv_snapshot": 80.0, "theme_names": "AI", "primary_theme": "AI", "exposure_score": 0.8},
                {"layer": "L1", "layer_name": "偏大市值主题股层", "market_cap_rank": 3, "total_mv_snapshot": 60.0, "theme_names": "医药", "primary_theme": "医药", "exposure_score": 0.5},
            ]
        )

        summary = summarize_layer_constituents(frame)

        l0 = summary[summary["layer"] == "L0"].iloc[0]
        self.assertEqual(l0["stock_count"], 2)
        self.assertIn('"AI": 2', l0["theme_hit_counts"])
        self.assertIn('"半导体芯片": 1', l0["theme_hit_counts"])


if __name__ == "__main__":
    unittest.main()
