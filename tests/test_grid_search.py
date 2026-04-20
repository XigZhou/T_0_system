from __future__ import annotations

import unittest

import pandas as pd

from overnight_bt.grid_search import add_stability_columns, build_grid_cases


class GridSearchTest(unittest.TestCase):
    def test_build_grid_cases_returns_expected_case_count(self) -> None:
        cases, preset = build_grid_cases()
        self.assertEqual(preset.name, "buy_condition_grid_v1")
        self.assertEqual(len(cases), 32)
        self.assertEqual(len({case.name for case in cases}), 32)
        self.assertTrue(all("m20>" in case.case.buy_condition for case in cases))

    def test_build_focus_grid_cases_returns_expected_case_count(self) -> None:
        cases, preset = build_grid_cases("buy_condition_focus_grid_v1")
        self.assertEqual(preset.name, "buy_condition_focus_grid_v1")
        self.assertEqual(len(cases), 4)
        self.assertTrue(all("board=主板" in case.case.buy_condition for case in cases))

    def test_build_fine_focus_grid_cases_returns_expected_case_count(self) -> None:
        cases, preset = build_grid_cases("buy_condition_focus_grid_v2")
        self.assertEqual(preset.name, "buy_condition_focus_grid_v2")
        self.assertEqual(len(cases), 16)
        self.assertTrue(all("vr<" in case.case.buy_condition for case in cases))

    def test_add_stability_columns_marks_stable_case(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "annualized_return": 0.22,
                    "positive_month_ratio": 0.7,
                    "win_rate": 0.58,
                    "max_drawdown": 0.12,
                    "sell_count": 180,
                    "active_day_ratio": 0.16,
                    "median_trade_return": 0.012,
                },
                {
                    "annualized_return": -0.05,
                    "positive_month_ratio": 0.4,
                    "win_rate": 0.45,
                    "max_drawdown": 0.35,
                    "sell_count": 30,
                    "active_day_ratio": 0.03,
                    "median_trade_return": -0.01,
                },
            ]
        )
        ranked = add_stability_columns(frame)
        self.assertTrue(bool(ranked.loc[0, "stable_pass"]))
        self.assertFalse(bool(ranked.loc[1, "stable_pass"]))
        self.assertGreater(float(ranked.loc[0, "stability_score"]), float(ranked.loc[1, "stability_score"]))


if __name__ == "__main__":
    unittest.main()
