from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_sector_rotation_followup import (
    build_comparison_cases,
    build_periods,
    build_weighted_score_cases,
    parse_args,
    run_followup,
)
from tests.helpers import make_processed_stock, write_processed_dir


def _rows(base_price: float, m20: float) -> list[dict]:
    dates = ["20240102", "20240103", "20240104", "20240105", "20240108"]
    rows: list[dict] = []
    for idx, trade_date in enumerate(dates):
        price = base_price + idx * 0.2
        rows.append(
            {
                "trade_date": trade_date,
                "raw_open": price,
                "raw_high": price + 0.2,
                "raw_low": price - 0.2,
                "raw_close": price + 0.1,
                "m5": 0.04,
                "m10": 0.08,
                "m20": m20,
                "m60": 0.03,
                "m120": 0.05,
                "hs300_m20": 0.03,
                "can_buy_t": True,
                "can_buy_open_t": True,
                "can_sell_t": True,
                "can_sell_t1": True,
                "is_suspended_t": False,
                "is_suspended_t1": False,
            }
        )
    return rows


def _add_sector(frame: pd.DataFrame, theme: str, score: float, rank_pct: float) -> pd.DataFrame:
    frame = frame.copy()
    frame["sector_theme_names"] = theme
    frame["sector_exposure_score"] = 0.8
    frame["sector_strongest_theme"] = theme
    frame["sector_strongest_theme_score"] = score
    frame["sector_strongest_theme_rank_pct"] = rank_pct
    frame["sector_strongest_theme_m20"] = 0.12
    return frame


def _write_manifest(processed_dir: Path) -> None:
    pd.DataFrame([{"stock_code": "000001", "matched": True}, {"stock_code": "000002", "matched": True}]).to_csv(
        processed_dir / "sector_feature_manifest.csv",
        index=False,
        encoding="utf-8-sig",
    )


def _write_rotation_daily(path: Path) -> None:
    pd.DataFrame(
        [
            {"trade_date": "20240102", "top_theme": "AI", "top_cluster": "科技成长", "rotation_state": "新主线启动", "top_score": 0.7, "top_rank_pct": 0.0, "top_gap": 0.1},
            {"trade_date": "20240103", "top_theme": "AI", "top_cluster": "科技成长", "rotation_state": "主线退潮", "top_score": 0.6, "top_rank_pct": 0.0, "top_gap": 0.08},
            {"trade_date": "20240104", "top_theme": "AI", "top_cluster": "科技成长", "rotation_state": "轮动观察", "top_score": 0.62, "top_rank_pct": 0.0, "top_gap": 0.05},
            {"trade_date": "20240105", "top_theme": "锂矿锂电", "top_cluster": "新能源", "rotation_state": "主线延续", "top_score": 0.55, "top_rank_pct": 0.0, "top_gap": 0.03},
            {"trade_date": "20240108", "top_theme": "锂矿锂电", "top_cluster": "新能源", "rotation_state": "无明确主线", "top_score": 0.3, "top_rank_pct": 0.5, "top_gap": 0.01},
        ]
    ).to_csv(path, index=False, encoding="utf-8-sig")


class SectorRotationFollowupTest(unittest.TestCase):
    def test_build_cases_and_periods(self) -> None:
        comparison = build_comparison_cases(base_processed_dir="base", sector_processed_dir="sector")
        self.assertEqual([case.name for case in comparison], ["基准动量", "板块候选_score0.4_rank0.7", "候选_避开新能源主线"])

        weighted = build_weighted_score_cases(
            sector_processed_dir="sector",
            tech_bonuses=[0.0, 2.0],
            new_energy_penalties=[0.0],
            new_start_penalties=[0.0, 1.0],
        )
        self.assertEqual(len(weighted), 4)
        self.assertIn("rotation_top_cluster_tech", weighted[-1].score_expression)

        periods = build_periods("20230101", "20260429")
        self.assertIn("最近一年", {period.label for period in periods})
        self.assertIn("2026YTD", {period.label for period in periods})

    def test_run_followup_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stock_a = make_processed_stock("000001", "AI股", _rows(10.0, 0.12))
            stock_b = make_processed_stock("000002", "新能源股", _rows(20.0, 0.09))
            base_dir = write_processed_dir(root / "base", [stock_a, stock_b])
            sector_dir = write_processed_dir(
                root / "sector",
                [
                    _add_sector(stock_a, "AI", 0.8, 0.2),
                    _add_sector(stock_b, "锂矿锂电", 0.7, 0.4),
                ],
            )
            _write_manifest(sector_dir)
            rotation_path = root / "rotation.csv"
            _write_rotation_daily(rotation_path)
            out_dir = root / "runs" / "followup"

            result_dir = run_followup(
                parse_args(
                    [
                        "--base-processed-dir",
                        str(base_dir),
                        "--sector-processed-dir",
                        str(sector_dir),
                        "--rotation-daily-path",
                        str(rotation_path),
                        "--start-date",
                        "20240102",
                        "--end-date",
                        "20240105",
                        "--out-dir",
                        str(out_dir),
                        "--tech-bonuses",
                        "0,1",
                        "--new-energy-penalties",
                        "0",
                        "--new-start-penalties",
                        "0",
                        "--top-n",
                        "1",
                        "--exit-offset",
                        "2",
                        "--max-hold-days",
                        "0",
                        "--settlement-mode",
                        "complete",
                        "--buy-fee-rate",
                        "0",
                        "--sell-fee-rate",
                        "0",
                        "--slippage-bps",
                        "0",
                    ]
                )
            )

            self.assertEqual(result_dir, out_dir)
            period = pd.read_csv(out_dir / "sector_rotation_period_comparison.csv", encoding="utf-8-sig")
            weighted = pd.read_csv(out_dir / "sector_rotation_weighted_score_summary.csv", encoding="utf-8-sig")
            self.assertIn("最近一年", set(period["period_label"]))
            self.assertEqual(len(weighted), 2)
            self.assertTrue((out_dir / "sector_rotation_followup_report.md").exists())

            result_dir = run_followup(
                parse_args(
                    [
                        "--base-processed-dir",
                        str(base_dir),
                        "--sector-processed-dir",
                        str(sector_dir),
                        "--rotation-daily-path",
                        str(rotation_path),
                        "--start-date",
                        "20240102",
                        "--end-date",
                        "20240105",
                        "--out-dir",
                        str(out_dir),
                        "--tech-bonuses",
                        "0,1",
                        "--new-energy-penalties",
                        "0",
                        "--new-start-penalties",
                        "0",
                        "--top-n",
                        "1",
                        "--exit-offset",
                        "2",
                        "--max-hold-days",
                        "0",
                        "--settlement-mode",
                        "complete",
                        "--buy-fee-rate",
                        "0",
                        "--sell-fee-rate",
                        "0",
                        "--slippage-bps",
                        "0",
                        "--resume",
                    ]
                )
            )
            self.assertEqual(result_dir, out_dir)
            weighted_after_resume = pd.read_csv(out_dir / "sector_rotation_weighted_score_summary.csv", encoding="utf-8-sig")
            self.assertEqual(len(weighted_after_resume), 2)


if __name__ == "__main__":
    unittest.main()
