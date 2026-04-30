from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from overnight_bt.backtest import run_portfolio_backtest
from overnight_bt.daily_plan import build_daily_plan
from overnight_bt.models import BacktestRequest, DailyPlanRequest
from tests.helpers import make_processed_stock, write_processed_dir


def _add_sector_features(frame: pd.DataFrame, *, score: float, exposure: float, rank_pct: float) -> pd.DataFrame:
    frame = frame.copy()
    frame["sector_theme_names"] = "AI"
    frame["sector_exposure_score"] = exposure
    frame["sector_strongest_theme"] = "AI"
    frame["sector_strongest_theme_score"] = score
    frame["sector_strongest_theme_rank_pct"] = rank_pct
    frame["sector_strongest_theme_m20"] = 0.12
    frame["sector_strongest_board"] = "AI服务器"
    return frame


def _write_manifest(processed_dir: Path) -> None:
    pd.DataFrame(
        [
            {
                "stock_code": "000001",
                "matched": True,
                "sector_exposure_score": 0.8,
            }
        ]
    ).to_csv(processed_dir / "sector_feature_manifest.csv", index=False, encoding="utf-8-sig")


class SectorFeatureProfileTest(unittest.TestCase):
    def test_backtest_and_daily_plan_use_sector_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            strong = _add_sector_features(
                make_processed_stock(
                    "000001",
                    "强主题股",
                    [
                        {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m20": 0.1, "can_buy_open_t": True, "can_sell_t": True},
                        {"trade_date": "20240103", "raw_open": 10.2, "raw_high": 10.4, "raw_low": 10.1, "raw_close": 10.3, "m20": 0.1, "can_buy_open_t": True, "can_sell_t": True},
                        {"trade_date": "20240104", "raw_open": 10.5, "raw_high": 10.8, "raw_low": 10.4, "raw_close": 10.7, "m20": 0.1, "can_buy_open_t": True, "can_sell_t": True},
                    ],
                ),
                score=0.82,
                exposure=0.8,
                rank_pct=0.2,
            )
            weak = _add_sector_features(
                make_processed_stock(
                    "000002",
                    "弱主题股",
                    [
                        {"trade_date": "20240102", "raw_open": 20.0, "raw_high": 20.2, "raw_low": 19.8, "raw_close": 20.0, "m20": 0.2, "can_buy_open_t": True, "can_sell_t": True},
                        {"trade_date": "20240103", "raw_open": 20.1, "raw_high": 20.3, "raw_low": 20.0, "raw_close": 20.2, "m20": 0.2, "can_buy_open_t": True, "can_sell_t": True},
                        {"trade_date": "20240104", "raw_open": 20.2, "raw_high": 20.4, "raw_low": 20.1, "raw_close": 20.3, "m20": 0.2, "can_buy_open_t": True, "can_sell_t": True},
                    ],
                ),
                score=0.35,
                exposure=0.7,
                rank_pct=0.7,
            )
            processed_dir = write_processed_dir(base, [strong, weak])
            _write_manifest(processed_dir)

            result = run_portfolio_backtest(
                BacktestRequest(
                    processed_dir=str(processed_dir),
                    data_profile="sector",
                    start_date="20240102",
                    end_date="20240102",
                    buy_condition="sector_exposure_score>0,sector_strongest_theme_score>=0.6,sector_strongest_theme_rank_pct<=0.5",
                    score_expression="sector_strongest_theme_score * 30 + m20",
                    top_n=1,
                    buy_fee_rate=0.0,
                    sell_fee_rate=0.0,
                    stamp_tax_sell=0.0,
                    realistic_execution=True,
                    slippage_bps=0.0,
                    min_commission=0.0,
                    settlement_mode="complete",
                )
            )
            self.assertEqual(result["diagnostics"]["data_profile"], "sector")
            self.assertEqual(result["pick_rows"][0]["symbol"], "000001")
            self.assertEqual(result["pick_rows"][0]["sector_strongest_theme"], "AI")

            plan = build_daily_plan(
                DailyPlanRequest(
                    processed_dir=str(processed_dir),
                    data_profile="sector",
                    signal_date="20240102",
                    buy_condition="sector_strongest_theme_score>=0.6",
                    score_expression="sector_strongest_theme_score",
                    top_n=1,
                )
            )
            self.assertEqual(plan["summary"]["data_profile"], "sector")
            self.assertEqual(plan["buy_rows"][0]["symbol"], "000001")
            self.assertEqual(plan["buy_rows"][0]["sector_strongest_theme_score"], 0.82)

    def test_sector_profile_requires_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock = _add_sector_features(
                make_processed_stock(
                    "000001",
                    "强主题股",
                    [
                        {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m20": 0.1, "can_buy_open_t": True, "can_sell_t": True},
                        {"trade_date": "20240103", "raw_open": 10.2, "raw_high": 10.4, "raw_low": 10.1, "raw_close": 10.3, "m20": 0.1, "can_buy_open_t": True, "can_sell_t": True},
                    ],
                ),
                score=0.82,
                exposure=0.8,
                rank_pct=0.2,
            )
            processed_dir = write_processed_dir(base, [stock])

            with self.assertRaisesRegex(ValueError, "sector_feature_manifest"):
                run_portfolio_backtest(
                    BacktestRequest(
                        processed_dir=str(processed_dir),
                        data_profile="sector",
                        start_date="20240102",
                        end_date="20240102",
                        buy_condition="sector_strongest_theme_score>=0.6",
                        score_expression="sector_strongest_theme_score",
                    )
                )


if __name__ == "__main__":
    unittest.main()
