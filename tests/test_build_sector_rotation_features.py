from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from overnight_bt.backtest import load_processed_folder
from scripts.build_sector_rotation_features import build_sector_rotation_features
from tests.helpers import make_processed_stock, write_processed_dir


def _rows() -> list[dict]:
    return [
        {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m20": 0.1},
        {"trade_date": "20240103", "raw_open": 10.2, "raw_high": 10.4, "raw_low": 10.1, "raw_close": 10.3, "m20": 0.1},
        {"trade_date": "20240104", "raw_open": 10.5, "raw_high": 10.8, "raw_low": 10.4, "raw_close": 10.7, "m20": 0.1},
    ]


def _add_sector_features(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["sector_theme_names"] = "AI"
    frame["sector_exposure_score"] = 0.8
    frame["sector_strongest_theme"] = "AI"
    frame["sector_strongest_theme_score"] = 0.7
    frame["sector_strongest_theme_rank_pct"] = 0.2
    frame["sector_strongest_theme_m20"] = 0.12
    return frame


class BuildSectorRotationFeaturesTest(unittest.TestCase):
    def test_build_sector_rotation_features_writes_isolated_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sector_dir = write_processed_dir(root / "source", [_add_sector_features(make_processed_stock("000001", "AI股", _rows()))])
            pd.DataFrame([{"stock_code": "000001", "matched": True}]).to_csv(
                sector_dir / "sector_feature_manifest.csv",
                index=False,
                encoding="utf-8-sig",
            )
            rotation_path = root / "rotation_daily.csv"
            pd.DataFrame(
                [
                    {"trade_date": "20240102", "top_theme": "AI", "top_cluster": "科技成长", "rotation_state": "新主线启动", "top_score": 0.6, "top_rank_pct": 0.0, "top_gap": 0.1},
                    {"trade_date": "20240103", "top_theme": "AI", "top_cluster": "科技成长", "rotation_state": "主线退潮", "top_score": 0.5, "top_rank_pct": 0.0, "top_gap": 0.05},
                ]
            ).to_csv(rotation_path, index=False, encoding="utf-8-sig")

            out_dir = root / "out" / "processed_rotation"
            result = build_sector_rotation_features(
                sector_processed_dir=sector_dir,
                rotation_daily_path=rotation_path,
                output_dir=out_dir,
            )

            self.assertEqual(result["stock_files"], 1)
            enriched = pd.read_csv(out_dir / "000001.csv", dtype=str, encoding="utf-8-sig")
            self.assertIn("rotation_state", enriched.columns)
            self.assertIn("stock_matches_rotation_top_cluster", enriched.columns)
            self.assertTrue((out_dir / "sector_feature_manifest.csv").exists())
            self.assertTrue((out_dir / "rotation_feature_manifest.csv").exists())
            loaded, diagnostics = load_processed_folder(str(out_dir))
            self.assertEqual(len(loaded), 1)
            self.assertEqual(diagnostics["file_count"], 1)

            original = pd.read_csv(sector_dir / "000001.csv", dtype=str, encoding="utf-8-sig")
            self.assertNotIn("rotation_state", original.columns)


if __name__ == "__main__":
    unittest.main()
