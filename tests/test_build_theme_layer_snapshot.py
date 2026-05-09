from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.build_theme_layer_snapshot import build_theme_layer_snapshot


class BuildThemeLayerSnapshotTest(unittest.TestCase):
    def test_builds_tushare_snapshot_from_selected_layers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            layers_csv = root / "layers.csv"
            out_csv = root / "bundle" / "snapshot.csv"
            pd.DataFrame(
                [
                    {
                        "pool_name": "Top500",
                        "pool_rank": "2",
                        "layer": "L0",
                        "ts_code": "000002.SZ",
                        "symbol": "000002",
                        "name": "万科A",
                        "area": "深圳",
                        "industry": "房地产",
                        "market": "主板",
                        "list_date": "19910129",
                        "close": "8.8",
                        "total_mv": "800000",
                        "turnover_rate_f": "1.2",
                        "pe_ttm": "9.1",
                        "pb": "0.8",
                    },
                    {
                        "pool_name": "Top500",
                        "pool_rank": "1",
                        "layer": "L2",
                        "ts_code": "",
                        "symbol": "000001",
                        "name": "平安银行",
                        "area": "深圳",
                        "industry": "银行",
                        "market": "主板",
                        "list_date": "19910403",
                        "close": "10.5",
                        "total_mv": "1000000",
                        "turnover_rate_f": "1.8",
                        "pe_ttm": "5.5",
                        "pb": "0.6",
                    },
                    {
                        "pool_name": "Top500",
                        "pool_rank": "3",
                        "layer": "L3",
                        "ts_code": "000003.SZ",
                        "symbol": "000003",
                        "name": "过滤样本",
                        "area": "深圳",
                        "industry": "测试",
                        "market": "主板",
                        "list_date": "19920101",
                        "close": "7.7",
                        "total_mv": "700000",
                        "turnover_rate_f": "1.0",
                        "pe_ttm": "12.0",
                        "pb": "1.1",
                    },
                ]
            ).to_csv(layers_csv, index=False, encoding="utf-8-sig")

            manifest = build_theme_layer_snapshot(
                layers_csv=layers_csv,
                out_csv=out_csv,
                layers={"L0", "L2"},
                pool_name="Top500",
            )

            self.assertEqual(manifest["rows"], 2)
            snapshot = pd.read_csv(out_csv, encoding="utf-8-sig", dtype=str)
            self.assertEqual(snapshot["symbol"].tolist(), ["000001", "000002"])
            self.assertEqual(snapshot.loc[0, "ts_code"], "000001.SZ")
            self.assertTrue(out_csv.with_suffix(".manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
