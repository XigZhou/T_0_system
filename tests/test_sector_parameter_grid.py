from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_sector_parameter_grid import build_sector_grid_cases, parse_args, run_grid
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


def _add_sector_features(frame: pd.DataFrame, *, score: float, exposure: float, rank_pct: float) -> pd.DataFrame:
    frame = frame.copy()
    frame["sector_theme_names"] = "AI"
    frame["sector_subtheme_names"] = "算力"
    frame["sector_board_names"] = "AI服务器"
    frame["sector_exposure_score"] = exposure
    frame["sector_strongest_theme"] = "AI"
    frame["sector_strongest_theme_score"] = score
    frame["sector_strongest_theme_rank_pct"] = rank_pct
    frame["sector_strongest_theme_m20"] = 0.12
    frame["sector_strongest_board"] = "AI服务器"
    return frame


def _write_sector_manifest(processed_dir: Path) -> None:
    pd.DataFrame(
        [
            {"stock_code": "000001", "matched": True, "sector_exposure_score": 0.8},
            {"stock_code": "000002", "matched": True, "sector_exposure_score": 0.4},
        ]
    ).to_csv(processed_dir / "sector_feature_manifest.csv", index=False, encoding="utf-8-sig")


class SectorParameterGridTest(unittest.TestCase):
    def test_build_sector_grid_cases_expands_families(self) -> None:
        cases = build_sector_grid_cases(
            base_processed_dir="base",
            sector_processed_dir="sector",
            score_thresholds=[0.4, 0.6],
            rank_pcts=[0.3],
            weights=[10.0],
        )

        self.assertEqual([case.family for case in cases], ["baseline", "hard_filter", "hard_filter", "score_only"])
        self.assertIn("sector_strongest_theme_score>=0.6", cases[2].buy_condition)
        self.assertIn("sector_strongest_theme_score * 10", cases[-1].score_expression)

    def test_run_grid_writes_summary_report_and_trade_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            strong = make_processed_stock("000001", "强主题股", _rows(10.0, 0.12))
            weak = make_processed_stock("000002", "弱主题股", _rows(20.0, 0.09))
            base_dir = write_processed_dir(root / "base", [strong, weak])
            sector_dir = write_processed_dir(
                root / "sector",
                [
                    _add_sector_features(strong, score=0.8, exposure=0.8, rank_pct=0.2),
                    _add_sector_features(weak, score=0.3, exposure=0.4, rank_pct=0.8),
                ],
            )
            _write_sector_manifest(sector_dir)
            out_dir = root / "runs" / "sector_grid"

            result_dir = run_grid(
                parse_args(
                    [
                        "--base-processed-dir",
                        str(base_dir),
                        "--sector-processed-dir",
                        str(sector_dir),
                        "--start-date",
                        "20240102",
                        "--end-date",
                        "20240102",
                        "--out-dir",
                        str(out_dir),
                        "--score-thresholds",
                        "0.6",
                        "--rank-pcts",
                        "0.5",
                        "--score-weights",
                        "10",
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
            summary = pd.read_csv(out_dir / "sector_parameter_grid_summary.csv", encoding="utf-8-sig")
            self.assertEqual(set(summary["family"]), {"baseline", "hard_filter", "score_only"})
            self.assertIn("grid_score", summary.columns)
            self.assertTrue((out_dir / "sector_parameter_grid_report.md").exists())
            self.assertTrue((out_dir / "sector_parameter_grid_config.json").exists())

            trades = pd.read_csv(out_dir / "sector_parameter_grid_trade_records.csv", encoding="utf-8-sig")
            self.assertIn("case", trades.columns)
            self.assertTrue((trades["action"] == "BUY").any())

    def test_run_grid_requires_sector_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            strong = make_processed_stock("000001", "强主题股", _rows(10.0, 0.12))
            base_dir = write_processed_dir(root / "base", [strong])
            sector_dir = write_processed_dir(
                root / "sector",
                [_add_sector_features(strong, score=0.8, exposure=0.8, rank_pct=0.2)],
            )

            with self.assertRaisesRegex(ValueError, "sector_feature_manifest"):
                run_grid(
                    parse_args(
                        [
                            "--base-processed-dir",
                            str(base_dir),
                            "--sector-processed-dir",
                            str(sector_dir),
                            "--start-date",
                            "20240102",
                            "--end-date",
                            "20240102",
                            "--out-dir",
                            str(root / "runs" / "missing_manifest"),
                            "--score-thresholds",
                            "0.6",
                            "--rank-pcts",
                            "0.5",
                            "--score-weights",
                            "10",
                        ]
                    )
                )


if __name__ == "__main__":
    unittest.main()
