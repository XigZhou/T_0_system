from __future__ import annotations

import os
from unittest.mock import patch

from fastapi.testclient import TestClient

import overnight_bt.app as app_module
from overnight_bt.market_data_store import upsert_daily_raw_rows, upsert_feature_rows, upsert_stock_basic_rows
from overnight_bt.market_data_view import check_market_stock, list_market_factors, list_market_stocks

PING_AN = "\u5e73\u5b89\u94f6\u884c"
VANKE = "\u4e07\u79d1A"
BANK = "\u94f6\u884c"
MAIN_BOARD = "\u4e3b\u677f"


def _seed_market_db(db_path):
    upsert_stock_basic_rows(
        [
            {
                "ts_code": "000001.SZ",
                "name": PING_AN,
                "industry": BANK,
                "market": MAIN_BOARD,
                "list_date": "19910403",
                "is_active": 1,
            },
            {
                "ts_code": "000002.SZ",
                "name": VANKE,
                "industry": "\u623f\u5730\u4ea7",
                "market": MAIN_BOARD,
                "list_date": "19910129",
                "is_active": 1,
            },
        ],
        db_path=db_path,
    )
    upsert_feature_rows(
        [
            {
                "symbol": "000001",
                "ts_code": "000001.SZ",
                "name": PING_AN,
                "trade_date": "20240506",
                "raw_open": 10.0,
                "raw_close": 10.6,
                "close": 10.6,
                "can_buy_open_t": 1,
                "can_sell_t": 1,
                "m5": 0.06,
                "ma5": 10.2,
                "vol_ratio_5": 1.3,
                "industry": BANK,
                "market": MAIN_BOARD,
            },
            {
                "symbol": "000001",
                "ts_code": "000001.SZ",
                "name": PING_AN,
                "trade_date": "20240507",
                "raw_open": 10.7,
                "raw_close": 11.0,
                "close": 11.0,
                "can_buy_open_t": 1,
                "can_sell_t": 1,
                "m5": 0.10,
                "ma5": 10.5,
                "vol_ratio_5": 1.6,
                "industry": BANK,
                "market": MAIN_BOARD,
            },
        ],
        db_path=db_path,
    )


def test_list_market_factors_reports_available_columns_and_span(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    _seed_market_db(db_path)

    payload = list_market_factors(db_path=db_path)

    summary = payload["summary"]
    fields = {item["field"] for item in payload["factors"]}
    m5 = next(item for item in payload["factors"] if item["field"] == "m5")
    assert summary["factor_count"] >= 5
    assert summary["start_date"] == "20240506"
    assert summary["end_date"] == "20240507"
    assert summary["source_table"] == "stock_daily_features"
    assert {"m5", "ma5", "vol_ratio_5", "industry", "market"} <= fields
    assert "close(T) - close(T-5+1)" in m5["formula"]
    assert "T \u65e5\u53ca\u5386\u53f2\u6570\u636e" in m5["boundary"]
    assert "\u53ea\u8bfb" in payload["message"]


def test_list_market_stocks_falls_back_to_feature_table_when_raw_is_empty(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    _seed_market_db(db_path)

    payload = list_market_stocks(db_path=db_path)

    assert payload["summary"] == {
        "stock_count": 1,
        "start_date": "20240506",
        "end_date": "20240507",
        "row_count": 2,
        "source_table": "stock_daily_features",
    }
    assert payload["stocks"] == [
        {
            "symbol": "000001",
            "ts_code": "000001.SZ",
            "name": PING_AN,
            "start_date": "20240506",
            "end_date": "20240507",
            "row_count": 2,
        }
    ]


def test_list_market_stocks_prefers_raw_table_when_it_has_rows(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    _seed_market_db(db_path)
    upsert_daily_raw_rows(
        [
            {"ts_code": "000002.SZ", "trade_date": "20240508", "open": 8.1, "high": 8.5, "low": 8.0, "close": 8.4, "vol": 1000, "amount": 8400},
            {"ts_code": "000002.SZ", "trade_date": "20240509", "open": 8.4, "high": 8.8, "low": 8.3, "close": 8.7, "vol": 1200, "amount": 10440},
        ],
        db_path=db_path,
    )

    payload = list_market_stocks(db_path=db_path)

    assert payload["summary"]["source_table"] == "stock_daily_raw"
    assert payload["summary"]["stock_count"] == 1
    assert payload["stocks"][0]["symbol"] == "000002"
    assert payload["stocks"][0]["name"] == VANKE


def test_check_market_stock_reports_available_and_unavailable(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    _seed_market_db(db_path)

    available = check_market_stock(PING_AN, db_path=db_path)
    unavailable = check_market_stock(VANKE, db_path=db_path)

    assert available["available"] is True
    assert available["matches"][0]["start_date"] == "20240506"
    assert "\u53ef\u7528" in available["message"]
    assert unavailable["available"] is False
    assert unavailable["matches"][0]["available"] is False
    assert "\u4e0d\u53ef\u7528" in unavailable["message"]


def test_market_data_api_uses_read_only_endpoints(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    _seed_market_db(db_path)
    app_module.app.dependency_overrides[app_module.auth.require_user] = lambda: app_module._direct_user(role="user")
    try:
        with patch("overnight_bt.app.MAIN_UNIVERSE_DB_PATH", db_path):
            client = TestClient(app_module.app)
            factors = client.get("/api/market-data/factors")
            stocks = client.get("/api/market-data/stocks")
            check = client.get("/api/market-data/stocks/check", params={"stock_name": PING_AN})
            bad = client.get("/api/market-data/stocks/check", params={"stock_name": ""})
    finally:
        app_module.app.dependency_overrides.pop(app_module.auth.require_user, None)

    assert factors.status_code == 200
    assert factors.json()["summary"]["factor_count"] >= 5
    assert stocks.status_code == 200
    assert stocks.json()["summary"]["stock_count"] == 1
    assert check.status_code == 200
    assert check.json()["available"] is True
    assert bad.status_code == 400

def test_market_data_api_can_use_read_only_env_db_override(tmp_path):
    default_db_path = tmp_path / "default_market_data.sqlite"
    override_db_path = tmp_path / "override_market_data.sqlite"
    _seed_market_db(override_db_path)

    app_module.app.dependency_overrides[app_module.auth.require_user] = lambda: app_module._direct_user(role="user")
    try:
        with patch("overnight_bt.app.MAIN_UNIVERSE_DB_PATH", default_db_path), patch.dict(
            os.environ, {app_module.MARKET_DATA_DB_ENV: str(override_db_path)}
        ):
            client = TestClient(app_module.app)
            factors = client.get("/api/market-data/factors")
            stocks = client.get("/api/market-data/stocks")
            check = client.get("/api/market-data/stocks/check", params={"stock_name": PING_AN})
    finally:
        app_module.app.dependency_overrides.pop(app_module.auth.require_user, None)

    assert factors.status_code == 200
    assert factors.json()["summary"]["factor_count"] >= 5
    assert factors.json()["db_path"] == str(override_db_path)
    assert stocks.status_code == 200
    assert stocks.json()["summary"]["stock_count"] == 1
    assert stocks.json()["db_path"] == str(override_db_path)
    assert check.status_code == 200
    assert check.json()["available"] is True
