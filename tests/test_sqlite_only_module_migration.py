from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from overnight_bt.backtest import run_portfolio_backtest
from overnight_bt.daily_plan import build_daily_plan
from overnight_bt.market_data_store import upsert_feature_rows
from overnight_bt.models import BacktestRequest, DailyPlanRequest, SignalQualityRequest, SingleStockBacktestRequest
from overnight_bt.single_stock import run_single_stock_backtest
from tests.helpers import make_processed_stock, write_stock_pool_db, write_stock_pool_template_symbols_db


@contextmanager
def _sqlite_only_enabled():
    old_value = os.environ.get("T0_SQLITE_ONLY")
    os.environ["T0_SQLITE_ONLY"] = "1"
    try:
        yield
    finally:
        if old_value is None:
            os.environ.pop("T0_SQLITE_ONLY", None)
        else:
            os.environ["T0_SQLITE_ONLY"] = old_value


def _feature_frame():
    return make_processed_stock(
        "000001",
        "????",
        [
            {
                "trade_date": "20240102",
                "raw_open": 10.0,
                "raw_high": 10.2,
                "raw_low": 9.8,
                "raw_close": 10.0,
                "m20": 0.2,
                "m5": 0.1,
                "can_buy_t": True,
                "can_buy_open_t": True,
                "can_sell_t": True,
                "can_sell_t1": True,
                "is_suspended_t": False,
                "is_suspended_t1": False,
            },
            {
                "trade_date": "20240103",
                "raw_open": 10.2,
                "raw_high": 10.4,
                "raw_low": 10.1,
                "raw_close": 10.3,
                "m20": 0.1,
                "m5": 0.05,
                "can_buy_t": True,
                "can_buy_open_t": True,
                "can_sell_t": True,
                "can_sell_t1": True,
                "is_suspended_t": False,
                "is_suspended_t1": False,
            },
            {
                "trade_date": "20240104",
                "raw_open": 10.4,
                "raw_high": 10.5,
                "raw_low": 10.0,
                "raw_close": 10.1,
                "m20": -0.1,
                "m5": -0.05,
                "can_buy_t": True,
                "can_buy_open_t": True,
                "can_sell_t": True,
                "can_sell_t1": True,
                "is_suspended_t": False,
                "is_suspended_t1": False,
            },
        ],
    )


def _seed_template_and_market(base: Path, template_name: str = "SQLite???") -> tuple[Path, Path]:
    frame = _feature_frame()
    template_db = write_stock_pool_template_symbols_db(
        base / "stock_pool_templates.sqlite",
        template_name,
        [{"symbol": "000001", "stock_name": "????"}],
    )
    market_db = base / "market_data.sqlite"
    upsert_feature_rows(frame.to_dict("records"), db_path=market_db)
    return template_db, market_db


def test_strategy_request_defaults_are_sqlite_first():
    backtest = BacktestRequest(stock_pool_template_name="SQLite???", buy_condition="m20>0", score_expression="m20")
    quality = SignalQualityRequest(stock_pool_template_name="SQLite???", buy_condition="m20>0", score_expression="m20")
    daily = DailyPlanRequest(stock_pool_template_name="SQLite???", buy_condition="m20>0", score_expression="m20")

    assert backtest.data_source == "stock_pool"
    assert quality.data_source == "stock_pool"
    assert daily.data_source == "stock_pool"
    assert backtest.stock_pool_feature_legacy_fallback is False
    assert quality.stock_pool_feature_legacy_fallback is False
    assert daily.stock_pool_feature_legacy_fallback is False


def test_strategy_requests_reject_legacy_csv_mode():
    import pytest
    from pydantic import ValidationError

    base = {"buy_condition": "m20>0", "score_expression": "m20", "data_source": "csv"}
    for model in (BacktestRequest, SignalQualityRequest, DailyPlanRequest):
        with pytest.raises(ValidationError):
            model(**base)
    with pytest.raises(ValidationError):
        SingleStockBacktestRequest(data_source="csv", symbol="000001", buy_condition="m20>0")


def test_backtest_and_daily_plan_defaults_read_stock_pool_market_sqlite():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        template_db, market_db = _seed_template_and_market(base)

        backtest = run_portfolio_backtest(
            BacktestRequest(
                stock_pool_template_name="SQLite???",
                stock_pool_db_path=str(template_db),
                stock_pool_market_db_path=str(market_db),
                start_date="20240102",
                end_date="20240102",
                buy_condition="m20>0",
                sell_condition="m20<0",
                score_expression="m20",
                top_n=1,
                buy_fee_rate=0.0,
                sell_fee_rate=0.0,
                stamp_tax_sell=0.0,
                settlement_mode="complete",
            )
        )
        plan = build_daily_plan(
            DailyPlanRequest(
                stock_pool_template_name="SQLite???",
                stock_pool_db_path=str(template_db),
                stock_pool_market_db_path=str(market_db),
                signal_date="20240102",
                buy_condition="m20>0",
                score_expression="m20",
                top_n=1,
            )
        )

        assert backtest["diagnostics"]["data_source"] == "stock_pool"
        assert backtest["pick_rows"][0]["symbol"] == "000001"
        assert plan["diagnostics"]["data_source"] == "stock_pool"
        assert plan["buy_rows"][0]["symbol"] == "000001"


def test_sqlite_only_ignores_explicit_backtest_legacy_feature_fallback():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        template_db = write_stock_pool_db(base / "stock_pool_templates.sqlite", "legacy_pool", [_feature_frame()])
        empty_market_db = base / "market_data.sqlite"

        with _sqlite_only_enabled(), pytest.raises(ValueError, match="没有可回测数据"):
            run_portfolio_backtest(
                BacktestRequest(
                    data_source="stock_pool",
                    stock_pool_template_name="legacy_pool",
                    stock_pool_db_path=str(template_db),
                    stock_pool_market_db_path=str(empty_market_db),
                    stock_pool_feature_legacy_fallback=True,
                    start_date="20240102",
                    end_date="20240102",
                    buy_condition="m20>0",
                    score_expression="m20",
                )
            )


def test_sqlite_only_single_stock_reads_market_db_without_legacy_feature_fallback():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        template_db, market_db = _seed_template_and_market(base, template_name="single_stock_pool")

        with _sqlite_only_enabled(), patch("overnight_bt.market_data_store.DEFAULT_DB_PATH", market_db):
            result = run_single_stock_backtest(
                SingleStockBacktestRequest(
                    symbol="000001",
                    stock_pool_template_name="single_stock_pool",
                    stock_pool_db_path=str(template_db),
                    start_date="20240102",
                    end_date="20240104",
                    buy_condition="m20>0",
                    sell_condition="m20<0",
                    buy_fee_rate=0.0,
                    sell_fee_rate=0.0,
                    stamp_tax_sell=0.0,
                )
            )

        assert result["stock_code"] == "000001"
        assert result["stock_name"]
