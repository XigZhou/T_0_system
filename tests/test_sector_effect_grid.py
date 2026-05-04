from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_sector_effect_grid import (
    build_sector_effect_cases,
    parse_args,
    run_effect_grid,
    validate_effect_feature_set,
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


def _add_sector(frame: pd.DataFrame, theme: str, score: float, rank_pct: float, exposure: float = 0.8) -> pd.DataFrame:
    frame = frame.copy()
    frame["sector_theme_names"] = theme
    frame["sector_exposure_score"] = exposure
    frame["sector_strongest_theme"] = theme
    frame["sector_strongest_theme_score"] = score
    frame["sector_strongest_theme_rank_pct"] = rank_pct
    frame["sector_strongest_theme_m20"] = 0.08
    frame["sector_strongest_theme_amount_ratio_20"] = 1.2
    frame["sector_strongest_theme_board_up_ratio"] = 0.7
    frame["sector_strongest_theme_positive_m20_ratio"] = 0.8
    return frame


def _write_manifest(processed_dir: Path) -> None:
    pd.DataFrame([{"stock_code": "000001", "matched": True}, {"stock_code": "000002", "matched": True}]).to_csv(
        processed_dir / "sector_feature_manifest.csv",
        index=False,
        encoding="utf-8-sig",
    )


class SectorEffectGridTest(unittest.TestCase):
    def test_build_cases_contains_hard_filter_and_weight(self) -> None:
        cases = build_sector_effect_cases(
            base_processed_dir="base",
            sector_processed_dir="sector",
            score_thresholds=[0.4],
            rank_pcts=[0.7],
            exposure_mins=[0.0, 0.3],
            theme_m20_mins=[None, 0.0],
            amount_ratio_mins=[None],
            score_weights=[5.0],
        )
        names = {case.name for case in cases}
        self.assertIn("基准动量", names)
        self.assertIn("板块候选_score0.4_rank0.7", names)
        self.assertIn("板块效应评分_w5", names)
        weighted = [case for case in cases if case.family == "score_weight"][0]
        self.assertIn("sector_strongest_theme_amount_ratio_20", weighted.score_expression)
        hard = [case for case in cases if case.name == "板块候选_score0.4_rank0.7"][0]
        self.assertIn("sector_strongest_theme_score>=0.4", hard.buy_condition)

    def test_run_effect_grid_writes_outputs_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stock_a = make_processed_stock("000001", "AI股", _rows(10.0, 0.12))
            stock_b = make_processed_stock("000002", "新能源股", _rows(20.0, 0.09))
            base_dir = write_processed_dir(root / "base", [stock_a, stock_b])
            sector_dir = write_processed_dir(
                root / "sector",
                [
                    _add_sector(stock_a, "AI", 0.8, 0.2, exposure=0.8),
                    _add_sector(stock_b, "锂矿锂电", 0.5, 0.7, exposure=0.25),
                ],
            )
            _write_manifest(sector_dir)
            out_dir = root / "runs" / "effect_grid"

            result_dir = run_effect_grid(
                parse_args(
                    [
                        "--base-processed-dir",
                        str(base_dir),
                        "--sector-processed-dir",
                        str(sector_dir),
                        "--start-date",
                        "20240102",
                        "--end-date",
                        "20240105",
                        "--out-dir",
                        str(out_dir),
                        "--score-thresholds",
                        "0.4",
                        "--rank-pcts",
                        "0.7",
                        "--exposure-mins",
                        "0,0.3",
                        "--theme-m20-mins",
                        "any,0",
                        "--amount-ratio-mins",
                        "any",
                        "--score-weights",
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

            summary = pd.read_csv(out_dir / "sector_effect_grid_summary.csv", encoding="utf-8-sig")
            self.assertIn("baseline", set(summary["family"]))
            self.assertIn("hard_filter", set(summary["family"]))
            self.assertIn("score_weight", set(summary["family"]))
            trades = pd.read_csv(out_dir / "sector_effect_grid_trade_records.csv", encoding="utf-8-sig")
            self.assertFalse(trades.empty)
            self.assertIn("case", trades.columns)
            self.assertIn("rank", trades.columns)
            self.assertIn("trade_return", trades.columns)
            self.assertTrue((out_dir / "sector_effect_grid_report.md").exists())

            resumed = run_effect_grid(
                parse_args(
                    [
                        "--base-processed-dir",
                        str(base_dir),
                        "--sector-processed-dir",
                        str(sector_dir),
                        "--start-date",
                        "20240102",
                        "--end-date",
                        "20240105",
                        "--out-dir",
                        str(out_dir),
                        "--score-thresholds",
                        "0.4",
                        "--rank-pcts",
                        "0.7",
                        "--exposure-mins",
                        "0,0.3",
                        "--theme-m20-mins",
                        "any,0",
                        "--amount-ratio-mins",
                        "any",
                        "--score-weights",
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
                        "--resume",
                    ]
                )
            )
            self.assertEqual(resumed, out_dir)
            summary_after = pd.read_csv(out_dir / "sector_effect_grid_summary.csv", encoding="utf-8-sig")
            self.assertEqual(len(summary_after), len(summary))
            trades_after = pd.read_csv(out_dir / "sector_effect_grid_trade_records.csv", encoding="utf-8-sig")
            self.assertEqual(len(trades_after), len(trades))

    def test_validate_effect_feature_set_reports_missing_extended_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stock = make_processed_stock("000001", "AI股", _rows(10.0, 0.12))
            sector = _add_sector(stock, "AI", 0.8, 0.2).drop(columns=["sector_strongest_theme_amount_ratio_20"])
            sector_dir = write_processed_dir(root / "sector", [sector])
            _write_manifest(sector_dir)
            loaded, diagnostics = __import__("overnight_bt.backtest", fromlist=["load_processed_folder"]).load_processed_folder(str(sector_dir))
            with self.assertRaisesRegex(ValueError, "sector_strongest_theme_amount_ratio_20"):
                validate_effect_feature_set(loaded_items=loaded, processed_dir=diagnostics["processed_dir"])


if __name__ == "__main__":
    unittest.main()
