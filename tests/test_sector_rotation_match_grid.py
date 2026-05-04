from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_sector_rotation_match_grid import build_rotation_match_cases, parse_args, run_rotation_match_grid
from tests.helpers import make_processed_stock, write_processed_dir


def _rows(base_price: float, m20: float, score_boost: float = 0.0) -> list[dict]:
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
                "m20": m20 + score_boost,
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
    frame["sector_strongest_theme_m20"] = 0.08
    frame["sector_strongest_theme_amount_ratio_20"] = 1.2
    frame["sector_strongest_theme_board_up_ratio"] = 0.7
    frame["sector_strongest_theme_positive_m20_ratio"] = 0.8
    return frame


def _write_manifest(processed_dir: Path) -> None:
    pd.DataFrame(
        [
            {"stock_code": "000001", "matched": True},
            {"stock_code": "000002", "matched": True},
            {"stock_code": "000003", "matched": True},
        ]
    ).to_csv(processed_dir / "sector_feature_manifest.csv", index=False, encoding="utf-8-sig")


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


class SectorRotationMatchGridTest(unittest.TestCase):
    def test_build_cases_contains_match_filters_and_score_weights(self) -> None:
        cases = build_rotation_match_cases(
            base_processed_dir="base",
            sector_processed_dir="sector",
            cluster_weights=[5.0],
            theme_weights=[8.0],
            penalty_weights=[3.0],
        )
        names = {case.name for case in cases}
        self.assertIn("候选_股票匹配主线簇", names)
        self.assertIn("主线簇匹配加权_w5", names)
        self.assertIn("主线匹配加权_新启动惩罚_p3", names)
        weighted = [case for case in cases if case.name == "主线簇匹配加权_w5"][0]
        self.assertIn("stock_matches_rotation_top_cluster * 5", weighted.score_expression)

    def test_run_rotation_match_grid_writes_outputs_and_changes_topn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # 非主线股票给更高基础动量，使匹配加权有机会改变 TopN。
            stock_a = make_processed_stock("000001", "AI股", _rows(10.0, 0.10))
            stock_b = make_processed_stock("000002", "新能源股", _rows(20.0, 0.16))
            stock_c = make_processed_stock("000003", "医药股", _rows(30.0, 0.13))
            base_dir = write_processed_dir(root / "base", [stock_a, stock_b, stock_c])
            sector_dir = write_processed_dir(
                root / "sector",
                [
                    _add_sector(stock_a, "AI", 0.8, 0.2),
                    _add_sector(stock_b, "锂矿锂电", 0.7, 0.4),
                    _add_sector(stock_c, "医药", 0.7, 0.4),
                ],
            )
            _write_manifest(sector_dir)
            rotation_path = root / "rotation.csv"
            _write_rotation_daily(rotation_path)
            out_dir = root / "runs" / "rotation_match"

            result_dir = run_rotation_match_grid(
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
                        "20240102",
                        "--out-dir",
                        str(out_dir),
                        "--cluster-weights",
                        "20",
                        "--theme-weights",
                        "25",
                        "--penalty-weights",
                        "5",
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
            summary = pd.read_csv(out_dir / "sector_rotation_match_grid_summary.csv", encoding="utf-8-sig")
            self.assertIn("主线簇匹配加权_w20", set(summary["case"]))
            self.assertIn("pick_overlap_rate_vs_sector_candidate", summary.columns)
            weighted = summary[summary["case"] == "主线簇匹配加权_w20"].iloc[0]
            self.assertLess(float(weighted["pick_overlap_rate_vs_sector_candidate"]), 1.0)

            picks = pd.read_csv(out_dir / "sector_rotation_match_grid_pick_records.csv", encoding="utf-8-sig")
            self.assertIn("stock_matches_rotation_top_cluster", picks.columns)
            trades = pd.read_csv(out_dir / "sector_rotation_match_grid_trade_records.csv", encoding="utf-8-sig")
            self.assertIn("case", trades.columns)
            self.assertTrue((out_dir / "sector_rotation_match_grid_report.md").exists())


if __name__ == "__main__":
    unittest.main()
