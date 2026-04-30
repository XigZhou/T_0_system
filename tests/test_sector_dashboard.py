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
            data_bundle = base / "data_bundle"
            processed.mkdir(parents=True)
            reports.mkdir(parents=True)
            data_bundle.mkdir(parents=True)

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
            _write_csv(
                data_bundle / "market_context.csv",
                [
                    {
                        "trade_date": "20240102",
                        "sh_close": "2900",
                        "sh_pct_chg": "0.20",
                        "sh_m5": "0.01",
                        "sh_m20": "-0.01",
                        "sh_m60": "-0.04",
                        "hs300_close": "3300",
                        "hs300_pct_chg": "0.50",
                        "hs300_m5": "0.02",
                        "hs300_m20": "0.01",
                        "hs300_m60": "-0.02",
                        "cyb_close": "1800",
                        "cyb_pct_chg": "1.20",
                        "cyb_m5": "0.03",
                        "cyb_m20": "0.02",
                        "cyb_m60": "0.01",
                    },
                    {
                        "trade_date": "20240103",
                        "sh_close": "3000",
                        "sh_pct_chg": "0.80",
                        "sh_m5": "0.02",
                        "sh_m20": "0.04",
                        "sh_m60": "0.01",
                        "hs300_close": "3400",
                        "hs300_pct_chg": "1.10",
                        "hs300_m5": "0.03",
                        "hs300_m20": "0.05",
                        "hs300_m60": "0.02",
                        "cyb_close": "1900",
                        "cyb_pct_chg": "1.50",
                        "cyb_m5": "0.04",
                        "cyb_m20": "0.07",
                        "cyb_m60": "0.05",
                    },
                    {
                        "trade_date": "20240104",
                        "sh_close": "3100",
                        "sh_pct_chg": "0.30",
                        "sh_m5": "0.03",
                        "sh_m20": "0.05",
                        "sh_m60": "0.02",
                        "hs300_close": "3500",
                        "hs300_pct_chg": "0.40",
                        "hs300_m5": "0.04",
                        "hs300_m20": "0.06",
                        "hs300_m60": "0.03",
                        "cyb_close": "2000",
                        "cyb_pct_chg": "0.60",
                        "cyb_m5": "0.05",
                        "cyb_m20": "0.08",
                        "cyb_m60": "0.06",
                    },
                ],
            )

            payload = build_sector_dashboard_payload(base_dir=base)

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["summary"]["latest_trade_date"], "20240103")
        self.assertEqual(payload["market_context"]["status"], "ready")
        self.assertEqual(payload["market_context"]["latest_trade_date"], "20240103")
        self.assertTrue(payload["market_context"]["is_aligned"])
        self.assertEqual(payload["market_context"]["indexes"][1]["name"], "沪深300")
        self.assertEqual(payload["market_context"]["indexes"][1]["m20"], 0.05)
        self.assertEqual(payload["summary"]["theme_count"], 2)
        self.assertEqual(payload["latest_themes"][0]["theme_name"], "锂矿锂电")
        self.assertEqual(payload["latest_boards"][0]["board_name"], "锂电池")
        self.assertEqual(payload["stock_exposure"][0]["stock_code"], "300001")
        self.assertEqual(payload["stock_exposure"][0]["stock_name"], "锂电龙头")
        self.assertEqual(payload["error_rows"][0]["stage"], "fetch_fund_flow_rank")
        self.assertTrue(payload["paths"]["files"]["theme_strength_daily"]["exists"])
        self.assertTrue(payload["paths"]["files"]["market_context"]["exists"])

    def test_build_sector_dashboard_payload_rejects_paths_outside_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                build_sector_dashboard_payload(base_dir=tmpdir, processed_dir="../outside")

            with self.assertRaises(ValueError):
                build_sector_dashboard_payload(base_dir=tmpdir, market_context_path="../outside")


if __name__ == "__main__":
    unittest.main()
