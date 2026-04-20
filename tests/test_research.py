from __future__ import annotations

import unittest

import pandas as pd

from overnight_bt.research import build_neighborhood_cases, select_train_top_cases, summarize_case_result


class ResearchTest(unittest.TestCase):
    def test_build_neighborhood_cases_contains_baseline_and_unique_names(self) -> None:
        cases = build_neighborhood_cases()
        names = [case.name for case in cases]
        self.assertIn("baseline", names)
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(any("listed_days>250" in case.buy_condition for case in cases))
        self.assertTrue(any(case.top_n == 3 for case in cases))

    def test_build_swing_v1_cases_use_multi_day_features(self) -> None:
        cases = build_neighborhood_cases(preset="swing_v1")
        self.assertTrue(any("close_pos_in_bar" in case.score_expression for case in cases))
        self.assertTrue(any("turnover_rate_snapshot" in case.buy_condition for case in cases))

    def test_summarize_case_result_adds_activity_and_month_stats(self) -> None:
        result = {
            "summary": {
                "annualized_return": 0.2,
                "max_drawdown": 0.1,
                "sell_count": 10,
                "buy_count": 10,
                "win_rate": 0.4,
                "trade_days": 4,
                "entry_offset": 1,
                "exit_offset": 3,
            },
            "daily_rows": [
                {"trade_date": "20240102", "equity": 100.0, "candidate_count": 1, "picked_count": 1},
                {"trade_date": "20240131", "equity": 110.0, "candidate_count": 1, "picked_count": 1},
                {"trade_date": "20240201", "equity": 110.0, "candidate_count": 0, "picked_count": 0},
                {"trade_date": "20240229", "equity": 105.0, "candidate_count": 1, "picked_count": 1},
            ],
            "trade_rows": [
                {"action": "SELL", "trade_return": 0.05},
                {"action": "SELL", "trade_return": 0.01},
            ],
            "diagnostics": {"candidate_days": 3, "picked_days": 3},
        }
        row = summarize_case_result("baseline", "train", "cond", "score", 5, result)
        self.assertAlmostEqual(row["active_day_ratio"], 0.75, places=6)
        self.assertAlmostEqual(row["positive_month_ratio"], 0.5, places=6)
        self.assertEqual(row["positive_months"], 1)
        self.assertEqual(row["months"], 2)
        self.assertEqual(row["case_key"], "baseline_n3")
        self.assertEqual(row["exit_offset"], 3)

    def test_select_train_top_cases_applies_stability_filters(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "case": "weak_activity",
                    "annualized_return": 0.8,
                    "max_drawdown": 0.1,
                    "positive_month_ratio": 0.7,
                    "active_day_ratio": 0.1,
                    "sell_count": 500,
                },
                {
                    "case": "balanced_a",
                    "annualized_return": 0.6,
                    "max_drawdown": 0.12,
                    "positive_month_ratio": 0.7,
                    "active_day_ratio": 0.4,
                    "sell_count": 500,
                },
                {
                    "case": "balanced_b",
                    "annualized_return": 0.55,
                    "max_drawdown": 0.08,
                    "positive_month_ratio": 0.8,
                    "active_day_ratio": 0.5,
                    "sell_count": 600,
                },
            ]
        )
        selected = select_train_top_cases(frame, top_k=2)
        self.assertEqual(selected["case"].tolist(), ["balanced_a", "balanced_b"])


if __name__ == "__main__":
    unittest.main()
