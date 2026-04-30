from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from overnight_bt.sector_dashboard import build_sector_dashboard_payload


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


class SectorDashboardTest(unittest.TestCase):
    def test_build_sector_dashboard_payload_reads_latest_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            processed = base / "sector_research" / "data" / "processed"
            reports = base / "sector_research" / "reports"
            processed.mkdir(parents=True)
            reports.mkdir(parents=True)

            _write_csv(
                processed / "theme_strength_daily.csv",
                [
                    {"trade_date": "20240102", "theme_name": "AI", "theme_score": "0.40", "theme_rank": "1", "strongest_board": "AI服务器"},
                    {"trade_date": "20240103", "theme_name": "AI", "theme_score": "0.70", "theme_rank": "2", "strongest_board": "AI服务器"},
                    {"trade_date": "20240103", "theme_name": "锂矿锂电", "theme_score": "0.92", "theme_rank": "1", "strongest_board": "锂电池"},
                ],
            )
            _write_csv(
                processed / "sector_board_daily.csv",
                [
                    {"trade_date": "20240103", "theme_name": "AI", "board_name": "AI服务器", "board_type": "concept", "theme_board_score": "0.70"},
                    {"trade_date": "20240103", "theme_name": "锂矿锂电", "board_name": "锂电池", "board_type": "concept", "theme_board_score": "0.95"},
                ],
            )
            _write_csv(
                processed / "stock_theme_exposure.csv",
                [
                    {"stock_code": "300001", "stock_name": "锂电龙头", "theme_names": "锂矿锂电", "theme_count": "1", "board_count": "2", "exposure_score": "1"},
                    {"stock_code": "300002", "stock_name": "算力龙头", "theme_names": "AI", "theme_count": "1", "board_count": "1", "exposure_score": "0.5"},
                ],
            )
            _write_csv(
                processed / "theme_board_mapping.csv",
                [
                    {"theme_name": "锂矿锂电", "subtheme_name": "锂电池", "matched_keyword": "锂电池", "board_type": "concept", "board_name": "锂电池"},
                    {"theme_name": "AI", "subtheme_name": "算力", "matched_keyword": "AI服务器", "board_type": "concept", "board_name": "AI服务器"},
                ],
            )
            _write_csv(reports / "sector_research_errors.csv", [{"stage": "fetch_fund_flow_rank", "board_type": "concept", "error": "timeout"}])
            (reports / "sector_research_summary.json").write_text(
                json.dumps({"latest_trade_date": "20240103", "error_count": 1}, ensure_ascii=False),
                encoding="utf-8",
            )

            payload = build_sector_dashboard_payload(base_dir=base)

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["summary"]["latest_trade_date"], "20240103")
        self.assertEqual(payload["summary"]["theme_count"], 2)
        self.assertEqual(payload["latest_themes"][0]["theme_name"], "锂矿锂电")
        self.assertEqual(payload["latest_boards"][0]["board_name"], "锂电池")
        self.assertEqual(payload["stock_exposure"][0]["stock_code"], "300001")
        self.assertEqual(payload["stock_exposure"][0]["stock_name"], "锂电龙头")
        self.assertEqual(payload["error_rows"][0]["stage"], "fetch_fund_flow_rank")
        self.assertTrue(payload["paths"]["files"]["theme_strength_daily"]["exists"])

    def test_build_sector_dashboard_payload_rejects_paths_outside_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                build_sector_dashboard_payload(base_dir=tmpdir, processed_dir="../outside")


if __name__ == "__main__":
    unittest.main()
