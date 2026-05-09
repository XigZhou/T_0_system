from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from overnight_bt.theme_universe import (
    ThemeUniverseBuildConfig,
    assign_market_cap_layers,
    build_current_top100_compare,
    build_theme_tradeable_universe,
    summarize_layered_pool,
    write_theme_tradeable_outputs,
)


def _sample_exposure() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"stock_code": "000001", "stock_name": "平安银行", "theme_names": "AI", "primary_theme": "AI", "primary_subtheme": "算力", "exposure_score": "0.8"},
            {"stock_code": "000002", "stock_name": "万科A", "theme_names": "机器人、AI", "primary_theme": "机器人", "primary_subtheme": "本体", "exposure_score": "0.7"},
            {"stock_code": "000003", "stock_name": "测试ST", "theme_names": "医药", "primary_theme": "医药", "primary_subtheme": "创新药", "exposure_score": "0.6"},
            {"stock_code": "000004", "stock_name": "北交样本", "theme_names": "半导体芯片", "primary_theme": "半导体芯片", "primary_subtheme": "设备", "exposure_score": "0.6"},
            {"stock_code": "000005", "stock_name": "新股样本", "theme_names": "光伏新能源", "primary_theme": "光伏新能源", "primary_subtheme": "储能", "exposure_score": "0.6"},
        ]
    )


def _sample_basic() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "symbol": "000001", "name": "平安银行", "area": "深圳", "industry": "银行", "market": "主板", "list_date": "19910403", "list_status": "L"},
            {"ts_code": "000002.SZ", "symbol": "000002", "name": "万科A", "area": "深圳", "industry": "房地产", "market": "主板", "list_date": "19910129", "list_status": "L"},
            {"ts_code": "000003.SZ", "symbol": "000003", "name": "测试ST", "area": "深圳", "industry": "医药", "market": "主板", "list_date": "19920101", "list_status": "L"},
            {"ts_code": "000004.BJ", "symbol": "000004", "name": "北交样本", "area": "北京", "industry": "半导体", "market": "北交所", "list_date": "20200101", "list_status": "L"},
            {"ts_code": "000005.SZ", "symbol": "000005", "name": "新股样本", "area": "深圳", "industry": "电气设备", "market": "主板", "list_date": "20260101", "list_status": "L"},
        ]
    )


def _sample_daily() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "trade_date": "20260508", "close": 10, "total_mv": 1000000, "turnover_rate_f": 1.0},
            {"ts_code": "000002.SZ", "trade_date": "20260508", "close": 11, "total_mv": 800000, "turnover_rate_f": 2.0},
            {"ts_code": "000003.SZ", "trade_date": "20260508", "close": 9, "total_mv": 700000, "turnover_rate_f": 1.0},
            {"ts_code": "000004.BJ", "trade_date": "20260508", "close": 8, "total_mv": 600000, "turnover_rate_f": 1.0},
            {"ts_code": "000005.SZ", "trade_date": "20260508", "close": 7, "total_mv": 500000, "turnover_rate_f": 1.0},
        ]
    )


class ThemeTradeableUniverseTest(unittest.TestCase):
    def test_build_theme_tradeable_universe_filters_st_bj_and_short_listing(self) -> None:
        universe = build_theme_tradeable_universe(
            exposure=_sample_exposure(),
            stock_basic=_sample_basic(),
            daily_basic=_sample_daily(),
            as_of_trade_date="20260508",
            current_top100_symbols=["000001"],
            config=ThemeUniverseBuildConfig(min_total_mv_yi=30, min_listed_days=250),
        )
        tradeable = universe[universe["is_tradeable_base"]]
        self.assertEqual(tradeable["symbol"].tolist(), ["000001", "000002"])
        self.assertTrue(bool(universe.loc[universe["symbol"] == "000001", "current_top100_symbol"].iloc[0]))
        self.assertIn("ST", universe.loc[universe["symbol"] == "000003", "filter_reasons"].iloc[0])
        self.assertIn("排除市场", universe.loc[universe["symbol"] == "000004", "filter_reasons"].iloc[0])
        self.assertIn("上市天数", universe.loc[universe["symbol"] == "000005", "filter_reasons"].iloc[0])

    def test_assign_market_cap_layers_uses_tradeable_subset_only(self) -> None:
        universe = build_theme_tradeable_universe(
            exposure=_sample_exposure(),
            stock_basic=_sample_basic(),
            daily_basic=_sample_daily(),
            as_of_trade_date="20260508",
            config=ThemeUniverseBuildConfig(min_total_mv_yi=30, min_listed_days=250),
        )
        layered = assign_market_cap_layers(universe, top_n=2, layer_count=2)
        self.assertEqual(layered["symbol"].tolist(), ["000001", "000002"])
        self.assertEqual(layered["layer"].tolist(), ["L0", "L1"])
        summary = summarize_layered_pool(layered)
        self.assertEqual(summary["stock_count"].sum(), 2)

    def test_current_top100_compare_marks_missing_and_layers(self) -> None:
        universe = build_theme_tradeable_universe(
            exposure=_sample_exposure(),
            stock_basic=_sample_basic(),
            daily_basic=_sample_daily(),
            as_of_trade_date="20260508",
            current_top100_symbols=["000001", "000999"],
            config=ThemeUniverseBuildConfig(min_total_mv_yi=30, min_listed_days=250),
        )
        layered = assign_market_cap_layers(universe, top_n=2, layer_count=2)
        current = pd.DataFrame([{"symbol": "000001", "name": "平安银行"}, {"symbol": "000999", "name": "缺失样本"}])
        compare = build_current_top100_compare(current_top100=current, universe=universe, layered_by_top_n={2: layered})
        self.assertTrue(bool(compare.loc[compare["symbol"] == "000001", "in_tradeable_universe"].iloc[0]))
        self.assertFalse(bool(compare.loc[compare["symbol"] == "000999", "in_tradeable_universe"].iloc[0]))
        self.assertEqual(compare.loc[compare["symbol"] == "000001", "top2_layer"].iloc[0], "L0")

    def test_write_outputs_creates_expected_files(self) -> None:
        universe = build_theme_tradeable_universe(
            exposure=_sample_exposure(),
            stock_basic=_sample_basic(),
            daily_basic=_sample_daily(),
            as_of_trade_date="20260508",
            current_top100_symbols=["000001"],
            config=ThemeUniverseBuildConfig(min_total_mv_yi=30, min_listed_days=250),
        )
        current = pd.DataFrame([{"symbol": "000001", "name": "平安银行"}])
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = write_theme_tradeable_outputs(
                universe=universe,
                current_top100=current,
                out_dir=Path(tmpdir),
                top_sizes=[2],
                layer_count=2,
            )
            self.assertTrue(Path(outputs["universe_snapshot"]).exists())
            self.assertTrue(Path(outputs["top2_layers"]).exists())
            self.assertTrue(Path(outputs["current_top100_layer_compare"]).exists())


if __name__ == "__main__":
    unittest.main()
