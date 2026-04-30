from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from sector_research.integration import merge_sector_features_to_processed_dir
from sector_research.pipeline import run_sector_research
from sector_research.providers import SectorDataProvider


class FakeSectorProvider(SectorDataProvider):
    def list_boards(self, board_type: str) -> pd.DataFrame:
        if board_type == "industry":
            rows = [
                {"board_type": "industry", "board_code": "BK001", "board_name": "半导体", "source": "fake", "fetched_at": "now"},
                {"board_type": "industry", "board_code": "BK002", "board_name": "医疗器械", "source": "fake", "fetched_at": "now"},
            ]
        else:
            rows = [
                {"board_type": "concept", "board_code": "BK101", "board_name": "锂电池", "source": "fake", "fetched_at": "now"},
                {"board_type": "concept", "board_code": "BK102", "board_name": "光伏设备", "source": "fake", "fetched_at": "now"},
                {"board_type": "concept", "board_code": "BK103", "board_name": "AI服务器", "source": "fake", "fetched_at": "now"},
                {"board_type": "concept", "board_code": "BK104", "board_name": "人形机器人", "source": "fake", "fetched_at": "now"},
            ]
        return pd.DataFrame(rows)

    def fetch_board_history(self, board_name: str, board_type: str, start_date: str, end_date: str) -> pd.DataFrame:
        base = {
            "锂电池": 20.0,
            "光伏设备": 30.0,
            "AI服务器": 40.0,
            "人形机器人": 50.0,
            "半导体": 60.0,
            "医疗器械": 70.0,
        }[board_name]
        dates = pd.bdate_range("2024-01-02", periods=80)
        rows = []
        for idx, dt in enumerate(dates):
            close = base + idx * (0.12 if board_name != "医疗器械" else -0.03)
            rows.append(
                {
                    "trade_date": dt.strftime("%Y%m%d"),
                    "board_type": board_type,
                    "board_name": board_name,
                    "open": close - 0.1,
                    "close": close,
                    "high": close + 0.2,
                    "low": close - 0.3,
                    "pct_chg": 1.0 if idx % 2 == 0 else -0.2,
                    "vol": 100000 + idx,
                    "amount": 10000000 + idx * 200000,
                    "turnover_rate": 1.2,
                    "source": "fake",
                }
            )
        return pd.DataFrame(rows)

    def fetch_board_constituents(self, board_name: str, board_type: str) -> pd.DataFrame:
        stock_code = {
            "锂电池": "300001",
            "光伏设备": "300002",
            "AI服务器": "300003",
            "人形机器人": "300004",
            "半导体": "300005",
            "医疗器械": "300006",
        }[board_name]
        return pd.DataFrame(
            [
                {
                    "board_type": board_type,
                    "board_name": board_name,
                    "stock_code": stock_code,
                    "stock_name": f"{board_name}龙头",
                    "latest_price": 10.0,
                    "pct_chg": 1.0,
                    "amount": 1000000,
                    "turnover_rate": 2.0,
                    "source": "fake",
                    "fetched_at": "now",
                }
            ]
        )

    def fetch_fund_flow_rank(self, board_type: str, indicator: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "board_type": board_type,
                    "fund_flow_indicator": indicator,
                    "board_name": "锂电池",
                    "pct_chg": 1.0,
                    "main_net_inflow": 10000000,
                    "main_net_inflow_ratio": 3.5,
                    "super_net_inflow": 5000000,
                    "source": "fake",
                    "fetched_at": "now",
                }
            ]
        )


class SectorResearchTest(unittest.TestCase):
    def test_run_sector_research_writes_theme_strength_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_path = base / "themes.yaml"
            config_path.write_text(
                """
themes:
  锂矿锂电:
    subthemes:
      锂电池: ["锂电池"]
  光伏新能源:
    subthemes:
      光伏: ["光伏"]
  半导体芯片:
    subthemes:
      半导体: ["半导体"]
  AI:
    subthemes:
      算力: ["AI服务器"]
  机器人:
    subthemes:
      机器人本体: ["人形机器人"]
  医药:
    subthemes:
      医疗器械: ["医疗器械"]
""".strip(),
                encoding="utf-8",
            )

            result = run_sector_research(
                config_path=config_path,
                start_date="20240101",
                end_date="20240501",
                raw_dir=base / "raw",
                processed_dir=base / "processed",
                report_dir=base / "reports",
                provider=FakeSectorProvider(),
            )

            self.assertGreaterEqual(result.board_count, 6)
            self.assertGreater(result.board_daily_rows, 0)
            self.assertGreater(result.theme_daily_rows, 0)
            self.assertGreater(result.constituent_rows, 0)

            theme_strength = pd.read_csv(base / "processed" / "theme_strength_daily.csv", dtype=str, encoding="utf-8-sig")
            self.assertIn("锂矿锂电", set(theme_strength["theme_name"]))
            self.assertIn("theme_score", theme_strength.columns)
            self.assertIn("volume_price_score", theme_strength.columns)
            self.assertIn("reversal_score", theme_strength.columns)
            self.assertIn("theme_rank", theme_strength.columns)
            self.assertIn("theme_rank_pct", theme_strength.columns)

            board_daily = pd.read_csv(base / "processed" / "sector_board_daily.csv", dtype=str, encoding="utf-8-sig")
            latest_lithium = board_daily[board_daily["board_name"] == "锂电池"].tail(1).iloc[0]
            self.assertGreater(float(latest_lithium["m20"]), 0)
            self.assertGreater(float(latest_lithium["amount_ratio_20"]), 1)
            self.assertIn("board_rank_in_theme", board_daily.columns)

            exposure = pd.read_csv(base / "processed" / "stock_theme_exposure.csv", dtype=str, encoding="utf-8-sig")
            self.assertIn("stock_name", exposure.columns)
            self.assertIn("primary_theme", exposure.columns)
            self.assertTrue((base / "reports" / "theme_strength_report.md").exists())
            self.assertTrue((base / "reports" / "theme_strength_latest.xlsx").exists())

    def test_merge_sector_features_writes_isolated_processed_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config_path = base / "themes.yaml"
            config_path.write_text(
                """
themes:
  锂矿锂电:
    subthemes:
      锂电池: ["锂电池"]
""".strip(),
                encoding="utf-8",
            )
            run_sector_research(
                config_path=config_path,
                start_date="20240101",
                end_date="20240501",
                raw_dir=base / "raw",
                processed_dir=base / "sector_processed",
                report_dir=base / "reports",
                provider=FakeSectorProvider(),
            )

            processed_dir = base / "processed_qfq"
            processed_dir.mkdir()
            dates = pd.bdate_range("2024-01-02", periods=80)
            stock_frame = pd.DataFrame(
                {
                    "trade_date": [dt.strftime("%Y%m%d") for dt in dates],
                    "close": [10 + idx * 0.1 for idx in range(80)],
                }
            )
            stock_frame.to_csv(processed_dir / "300001.csv", index=False, encoding="utf-8-sig")
            stock_frame.to_csv(processed_dir / "000999.csv", index=False, encoding="utf-8-sig")

            result = merge_sector_features_to_processed_dir(
                processed_dir=processed_dir,
                sector_processed_dir=base / "sector_processed",
                output_dir=base / "processed_qfq_sector",
            )

            self.assertEqual(result.stock_files, 2)
            self.assertEqual(result.matched_files, 1)
            enriched = pd.read_csv(base / "processed_qfq_sector" / "300001.csv", dtype=str, encoding="utf-8-sig")
            self.assertIn("sector_theme_names", enriched.columns)
            self.assertIn("sector_strongest_theme_score", enriched.columns)
            self.assertEqual(enriched["sector_theme_names"].dropna().iloc[0], "锂矿锂电")
            self.assertTrue(enriched["sector_strongest_theme_score"].notna().any())

            original = pd.read_csv(processed_dir / "300001.csv", dtype=str, encoding="utf-8-sig")
            self.assertNotIn("sector_theme_names", original.columns)
            self.assertTrue((base / "processed_qfq_sector" / "sector_feature_manifest.csv").exists())


if __name__ == "__main__":
    unittest.main()
