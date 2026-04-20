from __future__ import annotations

import math
import unittest

from overnight_bt.expressions import ScoreExpressionError, compile_score_expression, evaluate_score_expression


class ScoreExpressionTest(unittest.TestCase):
    def test_arithmetic_expression(self) -> None:
        tree, _ = compile_score_expression("m20 + m5 - abs(pct_chg) * 0.1")
        score = evaluate_score_expression({"m20": 0.4, "m5": 0.2, "pct_chg": -1.0}, tree)
        self.assertAlmostEqual(score, 0.5, places=6)

    def test_lag_expression(self) -> None:
        tree, _ = compile_score_expression("m5 - m5[1]")
        score = evaluate_score_expression({"m5": 0.3, "m5[1]": 0.1}, tree)
        self.assertAlmostEqual(score, 0.2, places=6)

    def test_missing_lag_returns_nan(self) -> None:
        tree, _ = compile_score_expression("m5 - m5[1]")
        score = evaluate_score_expression({"m5": 0.3}, tree)
        self.assertTrue(math.isnan(score))

    def test_reject_unsupported_function(self) -> None:
        with self.assertRaises(ScoreExpressionError):
            compile_score_expression("eval(m20)")

    def test_amp_fields_supported_in_score(self) -> None:
        tree, _ = compile_score_expression("pct_chg - amp * 100 - amp5 * 50")
        score = evaluate_score_expression({"pct_chg": 2.0, "amp": 0.01, "amp5": 0.02}, tree)
        self.assertAlmostEqual(score, 0.0, places=6)

    def test_snapshot_numeric_fields_supported_in_score(self) -> None:
        tree, _ = compile_score_expression("listed_days / 100 + total_mv_snapshot / 1000000 - turnover_rate_snapshot")
        score = evaluate_score_expression(
            {"listed_days": 365, "total_mv_snapshot": 8000000, "turnover_rate_snapshot": 1.5},
            tree,
        )
        self.assertAlmostEqual(score, 10.15, places=6)

    def test_overnight_fields_supported_in_score(self) -> None:
        tree, _ = compile_score_expression("close_pos_in_bar * 10 + body_pct * 100 - upper_shadow_pct * 50")
        score = evaluate_score_expression(
            {
                "close_pos_in_bar": 0.8,
                "body_pct": 0.02,
                "upper_shadow_pct": 0.01,
            },
            tree,
        )
        self.assertAlmostEqual(score, 9.5, places=6)

    def test_short_cycle_v4_fields_supported_in_score(self) -> None:
        tree, _ = compile_score_expression("body_pct_3avg * 100 - abs(ret_accel_3) * 50 - abs(vol_ratio_3 - 1.0) * 10")
        score = evaluate_score_expression(
            {
                "body_pct_3avg": 0.02,
                "ret_accel_3": 0.01,
                "vol_ratio_3": 1.1,
            },
            tree,
        )
        self.assertAlmostEqual(score, 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
