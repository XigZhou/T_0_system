from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_sector_rotation_match_stability import (
    AVOID_NEW_ENERGY_CASE_NAME,
    SECTOR_CANDIDATE_NAME,
    WEIGHTED_CLUSTER_CASE_NAME,
    build_stability_cases,
    parse_args,
    run_sector_rotation_match_stability,
)
from tests.helpers import make_processed_stock, write_processed_dir


def _rows(base_price: float, m20: float) -> list[dict]:
    dates = [
        "20220103",
        "20220104",
        "20230103",
        "20230104",
        "20240103",
        "20240104",
        "20240403",
        "20240404",
    ]
    rows: list[dict] = []
    for idx, trade_date in enumerate(dates):
        price = base_price + idx * 0.3
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


def _add_sector(frame: pd.DataFrame, theme: str) -> pd.DataFrame:
    frame = frame.copy()
    frame["sector_theme_names"] = theme
    frame["sector_exposure_score"] = 0.8
    frame["sector_strongest_theme"] = theme
    frame["sector_strongest_theme_score"] = 0.7
    frame["sector_strongest_theme_rank_pct"] = 0.3
    frame["sector_strongest_theme_m20"] = 0.08
    frame["sector_strongest_theme_amount_ratio_20"] = 1.2
    frame["sector_strongest_theme_board_up_ratio"] = 0.7
    frame["sector_strongest_theme_positive_m20_ratio"] = 0.8
    before_2023 = frame["trade_date"].astype(str) < "20230101"
    for column in ["sector_strongest_theme_score", "sector_strongest_theme_rank_pct", "sector_strongest_theme_m20"]:
        frame.loc[before_2023, column] = pd.NA
    return frame


def _write_manifest(processed_dir: Path) -> None:
    pd.DataFrame(
        [
            {"stock_code": "000001", "matched": True},
            {"stock_code": "000002", "matched": True},
        ]
    ).to_csv(processed_dir / "sector_feature_manifest.csv", index=False, encoding="utf-8-sig")


def _write_rotation_daily(path: Path) -> None:
    pd.DataFrame(
        [
            {"trade_date": "20230103", "top_theme": "AI", "top_cluster": "科技成长", "rotation_state": "轮动观察", "top_score": 0.7, "top_rank_pct": 0.0, "top_gap": 0.1},
            {"trade_date": "20230104", "top_theme": "AI", "top_cluster": "科技成长", "rotation_state": "主线延续", "top_score": 0.6, "top_rank_pct": 0.0, "top_gap": 0.08},
            {"trade_date": "20240103", "top_theme": "锂矿锂电", "top_cluster": "新能源", "rotation_state": "轮动观察", "top_score": 0.62, "top_rank_pct": 0.0, "top_gap": 0.05},
            {"trade_date": "20240104", "top_theme": "锂矿锂电", "top_cluster": "新能源", "rotation_state": "主线延续", "top_score": 0.55, "top_rank_pct": 0.0, "top_gap": 0.03},
            {"trade_date": "20240403", "top_theme": "AI", "top_cluster": "科技成长", "rotation_state": "轮动观察", "top_score": 0.58, "top_rank_pct": 0.0, "top_gap": 0.04},
            {"trade_date": "20240404", "top_theme": "AI", "top_cluster": "科技成长", "rotation_state": "主线延续", "top_score": 0.57, "top_rank_pct": 0.0, "top_gap": 0.03},
        ]
    ).to_csv(path, index=False, encoding="utf-8-sig")


class SectorRotationMatchStabilityTest(unittest.TestCase):
    def test_build_stability_cases_contains_selected_strategies(self) -> None:
        cases = build_stability_cases(base_processed_dir="base", sector_processed_dir="sector")
        names = {case.name for case in cases}
        self.assertEqual(len(cases), 4)
        self.assertIn("基准动量", names)
        self.assertIn(SECTOR_CANDIDATE_NAME, names)
        self.assertIn(WEIGHTED_CLUSTER_CASE_NAME, names)
        self.assertIn(AVOID_NEW_ENERGY_CASE_NAME, names)

    def test_run_stability_writes_yearly_rolling_and_baseline_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stock_a = make_processed_stock("000001", "AI股", _rows(10.0, 0.12))
            stock_b = make_processed_stock("000002", "新能源股", _rows(20.0, 0.14))
            base_dir = write_processed_dir(root / "base", [stock_a, stock_b])
            sector_dir = write_processed_dir(
                root / "sector",
                [
                    _add_sector(stock_a, "AI"),
                    _add_sector(stock_b, "锂矿锂电"),
                ],
            )
            _write_manifest(sector_dir)
            rotation_path = root / "rotation.csv"
            _write_rotation_daily(rotation_path)
            out_dir = root / "runs" / "stability"

            result_dir = run_sector_rotation_match_stability(
                parse_args(
                    [
                        "--base-processed-dir",
                        str(base_dir),
                        "--sector-processed-dir",
                        str(sector_dir),
                        "--rotation-daily-path",
                        str(rotation_path),
                        "--start-date",
                        "20220101",
                        "--end-date",
                        "20240404",
                        "--out-dir",
                        str(out_dir),
                        "--rolling-months",
                        "12",
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
                        "--skip-trade-records",
                    ]
                )
            )

            self.assertEqual(result_dir, out_dir)
            summary = pd.read_csv(out_dir / "sector_rotation_match_stability_summary.csv", encoding="utf-8-sig")
            self.assertIn("可比全区间", set(summary["period_label"]))
            self.assertIn("2023", set(summary["period_label"]))
            self.assertIn("2024YTD", set(summary["period_label"]))
            self.assertTrue(any(str(label).startswith("滚动12月_") for label in summary["period_label"].unique()))
            baseline_ref = summary[summary["period_kind"] == "baseline_reference"]
            self.assertEqual(set(baseline_ref["case"]), {"基准动量"})
            comparable = summary[summary["period_kind"] != "baseline_reference"]
            self.assertIn(WEIGHTED_CLUSTER_CASE_NAME, set(comparable["case"]))

            stability = pd.read_csv(out_dir / "sector_rotation_match_stability_by_case.csv", encoding="utf-8-sig")
            self.assertIn("positive_period_ratio", stability.columns)
            coverage = pd.read_csv(out_dir / "sector_rotation_match_stability_coverage.csv", encoding="utf-8-sig")
            self.assertIn("sector_strongest_theme_score_coverage", coverage.columns)
            self.assertTrue((out_dir / "sector_rotation_match_stability_report.md").exists())


if __name__ == "__main__":
    unittest.main()
