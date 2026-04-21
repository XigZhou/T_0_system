from __future__ import annotations

import unittest

from scripts.run_sell_condition_grid import build_sell_grid_cases


class SellGridTest(unittest.TestCase):
    def test_build_basic_sell_grid_cases(self) -> None:
        cases = build_sell_grid_cases("sell_grid_basic_v1")
        self.assertEqual(len(cases), 9)
        self.assertTrue(any(case.name == "fixed_exit_t5" for case in cases))

    def test_build_advanced_sell_grid_cases(self) -> None:
        cases = build_sell_grid_cases("sell_grid_advanced_v1")
        self.assertEqual(len(cases), 8)
        self.assertTrue(any("holding_return<" in case.sell_condition for case in cases))
        self.assertTrue(any("drawdown_from_peak" in case.sell_condition for case in cases))


if __name__ == "__main__":
    unittest.main()
