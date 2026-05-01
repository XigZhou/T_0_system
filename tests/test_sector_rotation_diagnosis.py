from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.run_sector_rotation_diagnosis import (
    build_rotation_daily,
    build_theme_run_table,
    parse_args,
    run_rotation_diagnosis,
)
from tests.helpers import make_processed_stock, write_processed_dir


def _theme_strength_rows() -> list[dict]:
    dates = ["20240102", "20240103", "20240104", "20240105", "20240108", "20240109", "20240110"]
    rows: list[dict] = []
    for idx, trade_date in enumerate(dates):
        ai_score = 0.40 + idx * 0.03
        lithium_score = 0.62 - idx * 0.02
        medicine_score = 0.35 + (0.08 if idx >= 5 else 0.0)
        scores = {
            "AI": ai_score,
            "锂矿锂电": lithium_score,
            "医药": medicine_score,
        }
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        for rank, (theme, score) in enumerate(ranked):
            rows.append(
                {
                    "trade_date": trade_date,
                    "theme_name": theme,
                    "theme_score": score,
                    "theme_rank_pct": rank / 2,
                    "m5": score - 0.35,
                    "m20": score - 0.30,
                    "m60": score - 0.40,
                    "strongest_board": f"{theme}板块",
                }
            )
    return rows


def _stock_rows() -> list[dict]:
    rows: list[dict] = []
    for idx, trade_date in enumerate(["20240102", "20240103", "20240104", "20240105", "20240108", "20240109", "20240110"]):
        price = 10.0 + idx * 0.1
        rows.append(
            {
                "trade_date": trade_date,
                "raw_open": price,
                "raw_high": price + 0.1,
                "raw_low": price - 0.1,
                "raw_close": price,
                "m20": 0.1,
                "sector_strongest_theme": "AI",
                "sector_strongest_theme_score": 0.6,
                "sector_strongest_theme_rank_pct": 0.0,
                "sector_exposure_score": 0.8,
            }
        )
    return rows


class SectorRotationDiagnosisTest(unittest.TestCase):
    def test_build_rotation_daily_identifies_top_theme_runs(self) -> None:
        frame = pd.DataFrame(_theme_strength_rows())
        daily = build_rotation_daily(frame, fresh_days=2)
        runs = build_theme_run_table(daily)

        self.assertIn("top_theme_run_days", daily.columns)
        self.assertIn("rotation_state", daily.columns)
        self.assertEqual(daily.iloc[0]["top_theme"], "锂矿锂电")
        self.assertIn("主线延续", set(daily["rotation_state"]))
        self.assertGreaterEqual(runs["run_days"].max(), 1)

    def test_run_rotation_diagnosis_writes_outputs_and_labels_trades(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            theme_path = root / "theme_strength_daily.csv"
            pd.DataFrame(_theme_strength_rows()).to_csv(theme_path, index=False, encoding="utf-8-sig")

            stock = make_processed_stock("000001", "测试AI股", _stock_rows())
            sector_dir = write_processed_dir(root / "sector", [stock])
            pd.DataFrame([{"stock_code": "000001", "matched": True}]).to_csv(
                sector_dir / "sector_feature_manifest.csv",
                index=False,
                encoding="utf-8-sig",
            )

            trades_path = root / "trade_records.csv"
            pd.DataFrame(
                [
                    {
                        "case": "基准动量",
                        "family": "baseline",
                        "trade_date": "20240103",
                        "signal_date": "20240102",
                        "symbol": "000001",
                        "name": "测试AI股",
                        "action": "BUY",
                        "price": 10.0,
                        "shares": 100,
                    },
                    {
                        "case": "基准动量",
                        "family": "baseline",
                        "trade_date": "20240108",
                        "signal_date": "20240102",
                        "symbol": "000001",
                        "name": "测试AI股",
                        "action": "SELL",
                        "price": 10.5,
                        "shares": 100,
                        "trade_return": 0.05,
                        "price_pnl": 50.0,
                    },
                ]
            ).to_csv(trades_path, index=False, encoding="utf-8-sig")

            out_dir = root / "rotation"
            result_dir = run_rotation_diagnosis(
                parse_args(
                    [
                        "--theme-strength-path",
                        str(theme_path),
                        "--trade-records-path",
                        str(trades_path),
                        "--sector-processed-dir",
                        str(sector_dir),
                        "--out-dir",
                        str(out_dir),
                        "--cases",
                        "基准动量",
                    ]
                )
            )

            self.assertEqual(result_dir, out_dir)
            self.assertTrue((out_dir / "sector_rotation_report.md").exists())
            labeled = pd.read_csv(out_dir / "sector_rotation_labeled_trades.csv", dtype=str, encoding="utf-8-sig")
            self.assertIn("signal_top_theme", labeled.columns)
            self.assertIn("sector_strongest_theme", labeled.columns)
            summary = pd.read_csv(out_dir / "sector_rotation_trade_summary.csv", encoding="utf-8-sig")
            self.assertIn("rotation_state", set(summary["group_type"]))


if __name__ == "__main__":
    unittest.main()
