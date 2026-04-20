from __future__ import annotations

import unittest

from overnight_bt.expressions import evaluate_conditions, parse_condition_expr


class ConditionParserTest(unittest.TestCase):
    def test_parse_and_evaluate(self) -> None:
        rules = parse_condition_expr("m20>0,m5>m5[1],vr<1.2,hs300_pct_chg>-1.0")
        payload = {
            "m20": 0.4,
            "m5": 0.12,
            "m5[1]": 0.05,
            "vol": 1000,
            "vol5": 1100,
            "hs300_pct_chg": -0.3,
        }
        ok, reason = evaluate_conditions(payload, rules)
        self.assertTrue(ok)
        self.assertEqual(reason, "satisfied")

    def test_range_and_scaled_rhs(self) -> None:
        rules = parse_condition_expr("1.0<=vr<=1.5,close<high*0.99")
        payload = {"vol": 1200, "vol5": 1000, "close": 9.8, "high": 10.0}
        ok, _ = evaluate_conditions(payload, rules)
        self.assertTrue(ok)

    def test_unsupported_field(self) -> None:
        with self.assertRaises(ValueError):
            parse_condition_expr("foo>1")

    def test_amp_field_is_supported(self) -> None:
        rules = parse_condition_expr("amp<0.04,amp5<0.05")
        payload = {"amp": 0.03, "amp5": 0.04}
        ok, reason = evaluate_conditions(payload, rules)
        self.assertTrue(ok)
        self.assertEqual(reason, "satisfied")

    def test_categorical_fields_support_equality(self) -> None:
        rules = parse_condition_expr("board=主板,market!=创业板")
        payload = {"board": "主板", "market": "主板"}
        ok, reason = evaluate_conditions(payload, rules)
        self.assertTrue(ok)
        self.assertEqual(reason, "satisfied")

    def test_categorical_fields_reject_order_operator(self) -> None:
        with self.assertRaises(ValueError):
            parse_condition_expr("board>主板")

    def test_overnight_numeric_fields_supported(self) -> None:
        rules = parse_condition_expr("close_to_up_limit<0.99,close_pos_in_bar>0.6,body_pct>0.01,vol_ratio_5<1.5")
        payload = {
            "close_to_up_limit": 0.97,
            "close_pos_in_bar": 0.8,
            "body_pct": 0.02,
            "vol_ratio_5": 1.2,
        }
        ok, reason = evaluate_conditions(payload, rules)
        self.assertTrue(ok)
        self.assertEqual(reason, "satisfied")

    def test_short_cycle_v4_fields_supported(self) -> None:
        rules = parse_condition_expr("ret_accel_3>-0.01,vol_ratio_3<1.2,amount_ratio_3<1.2,body_pct_3avg>0.01,close_to_up_limit_3max<1.0")
        payload = {
            "ret_accel_3": 0.002,
            "vol_ratio_3": 1.05,
            "amount_ratio_3": 1.08,
            "body_pct_3avg": 0.015,
            "close_to_up_limit_3max": 0.99,
        }
        ok, reason = evaluate_conditions(payload, rules)
        self.assertTrue(ok)
        self.assertEqual(reason, "satisfied")


if __name__ == "__main__":
    unittest.main()
