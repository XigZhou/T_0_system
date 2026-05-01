from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_sector_rotation_grid import (
    build_rotation_grid_cases,
    load_rotation_daily,
    merge_rotation_features,
    parse_args,
    run_rotation_grid,
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
            {"trade_date": "20240102", "top_theme": "AI", "top_cluster": "科技成长", "rotation_state": "新主线启动", "top_score": 0.7, "top_rank_pct": 0.0, "top_gap": 0.1, "top_theme_run_days": 1, "top_cluster_run_days": 1},
            {"trade_date": "20240103", "top_theme": "AI", "top_cluster": "科技成长", "rotation_state": "主线退潮", "top_score": 0.6, "top_rank_pct": 0.0, "top_gap": 0.08, "top_theme_run_days": 2, "top_cluster_run_days": 2},
            {"trade_date": "20240104", "top_theme": "AI", "top_cluster": "科技成长", "rotation_state": "轮动观察", "top_score": 0.62, "top_rank_pct": 0.0, "top_gap": 0.05, "top_theme_run_days": 3, "top_cluster_run_days": 3},
            {"trade_date": "20240105", "top_theme": "锂矿锂电", "top_cluster": "新能源", "rotation_state": "主线延续", "top_score": 0.55, "top_rank_pct": 0.0, "top_gap": 0.03, "top_theme_run_days": 1, "top_cluster_run_days": 1},
            {"trade_date": "20240108", "top_theme": "锂矿锂电", "top_cluster": "新能源", "rotation_state": "无明确主线", "top_score": 0.3, "top_rank_pct": 0.5, "top_gap": 0.01, "top_theme_run_days": 2, "top_cluster_run_days": 2},
        ]
    ).to_csv(path, index=False, encoding="utf-8-sig")


class SectorRotationGridTest(unittest.TestCase):
    def test_build_rotation_grid_cases_contains_rotation_filters(self) -> None:
        cases = build_rotation_grid_cases(base_processed_dir="base", sector_processed_dir="sector")
        names = {case.name for case in cases}
        self.assertIn("候选_退潮或观察", names)
        self.assertTrue(any("rotation_is_favorable_state>0" in case.buy_condition for case in cases))

    def test_load_and_merge_rotation_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rotation_path = root / "rotation.csv"
            _write_rotation_daily(rotation_path)
            rotation = load_rotation_daily(rotation_path)
            stock = _add_sector(make_processed_stock("000001", "AI股", _rows(10.0, 0.12)), "AI", 0.8, 0.2)
            processed_dir = write_processed_dir(root / "sector", [stock])
            loaded, _ = __import__("overnight_bt.backtest", fromlist=["load_processed_folder"]).load_processed_folder(str(processed_dir))

            merged = merge_rotation_features(loaded, rotation)
            frame = merged[0].df
            self.assertIn("rotation_is_favorable_state", frame.columns)
            self.assertIn("stock_matches_rotation_top_cluster", frame.columns)
            self.assertEqual(float(frame.loc[1, "rotation_is_favorable_state"]), 1.0)

    def test_run_rotation_grid_writes_summary(self) -> None:
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
            out_dir = root / "runs" / "rotation_grid"

            result_dir = run_rotation_grid(
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
            summary = pd.read_csv(out_dir / "sector_rotation_grid_summary.csv", encoding="utf-8-sig")
            self.assertIn("候选_新主线启动", set(summary["case"]))
            self.assertTrue((out_dir / "sector_rotation_grid_report.md").exists())
            trades = pd.read_csv(out_dir / "sector_rotation_grid_trade_records.csv", encoding="utf-8-sig")
            self.assertIn("case", trades.columns)


if __name__ == "__main__":
    unittest.main()
