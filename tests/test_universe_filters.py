from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from overnight_bt.universe_filters import build_theme_focus_frame, write_theme_focus_outputs


class UniverseFiltersTest(unittest.TestCase):
    def test_build_theme_focus_frame_includes_theme_industries_and_keywords(self) -> None:
        frame = pd.DataFrame(
            [
                {"symbol": "300274", "name": "阳光电源", "industry": "电气设备", "market": "创业板", "total_mv": 1000},
                {"symbol": "600406", "name": "国电南瑞", "industry": "电气设备", "market": "主板", "total_mv": 900},
                {"symbol": "601398", "name": "工商银行", "industry": "银行", "market": "主板", "total_mv": 2000},
                {"symbol": "002230", "name": "科大讯飞", "industry": "软件服务", "market": "主板", "total_mv": 800},
            ]
        )
        filtered = build_theme_focus_frame(frame)
        self.assertEqual(filtered["symbol"].tolist(), ["300274", "600406", "002230"])
        self.assertTrue(any("new_energy" in tags or "grid" in tags for tags in filtered["theme_tags"].tolist()))

    def test_write_theme_focus_outputs_copies_processed_subset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot = pd.DataFrame(
                [
                    {"symbol": "300274", "name": "阳光电源", "industry": "电气设备", "market": "创业板", "total_mv": 1000},
                    {"symbol": "601398", "name": "工商银行", "industry": "银行", "market": "主板", "total_mv": 2000},
                ]
            )
            processed_dir = root / "processed_qfq"
            processed_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame([{"symbol": "300274", "trade_date": "20240102"}]).to_csv(processed_dir / "300274.csv", index=False, encoding="utf-8-sig")
            pd.DataFrame([{"symbol": "601398", "trade_date": "20240102"}]).to_csv(processed_dir / "601398.csv", index=False, encoding="utf-8-sig")
            pd.DataFrame([{"symbol": "300274"}, {"symbol": "601398"}]).to_csv(processed_dir / "processing_manifest.csv", index=False, encoding="utf-8-sig")

            out_snapshot = root / "universe_snapshot_theme_focus.csv"
            out_processed_dir = root / "processed_qfq_theme_focus"
            result = write_theme_focus_outputs(snapshot, processed_dir, out_snapshot, out_processed_dir)

            self.assertEqual(result.selected_count, 1)
            self.assertTrue((out_processed_dir / "300274.csv").exists())
            self.assertFalse((out_processed_dir / "601398.csv").exists())
            self.assertTrue(out_snapshot.exists())

    def test_build_theme_focus_frame_preserves_symbol_zero_padding(self) -> None:
        frame = pd.DataFrame(
            [
                {"symbol": 2594, "name": "比亚迪", "industry": "汽车整车", "market": "主板", "total_mv": 1000},
            ]
        )
        filtered = build_theme_focus_frame(frame)
        self.assertEqual(filtered.iloc[0]["symbol"], "002594")


if __name__ == "__main__":
    unittest.main()
