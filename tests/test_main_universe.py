from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

import overnight_bt.main_universe as main_universe
from overnight_bt.main_universe import (
    MainUniverseSaveRequest,
    init_main_universe_db,
    list_main_universe,
    normalize_symbol,
    resolve_stock_names,
    save_main_universe,
    ts_code_from_symbol,
)


def _create_stock_basic(path, rows):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE stock_basic (
                symbol TEXT PRIMARY KEY,
                ts_code TEXT,
                name TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO stock_basic(symbol, ts_code, name, is_active)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "market_data.sqlite"
    _create_stock_basic(
        path,
        [
            ("300750", "300750.SZ", "宁德时代", 1),
            ("601138", "601138.SH", "工业富联", 1),
            ("000001", "000001.SZ", "平安银行", 0),
        ],
    )
    return path


@pytest.fixture()
def empty_main_db_path(tmp_path):
    path = tmp_path / "market_data.sqlite"
    init_main_universe_db(path)
    return path


@pytest.fixture()
def legacy_db_path(tmp_path):
    path = tmp_path / "stock_pool_templates.sqlite"
    _create_stock_basic(
        path,
        [
            ("300750", "300750.SZ", "宁德时代", 1),
            ("601138", "601138.SH", "工业富联", 1),
        ],
    )
    return path


def test_resolve_stock_names_returns_resolved_and_unresolved(db_path):
    init_main_universe_db(db_path)

    result = resolve_stock_names(["宁德时代", "不存在公司"], db_path=db_path)

    assert result["duplicate_inputs"] == []
    assert result["unresolved"] == ["不存在公司"]
    assert result["resolved"] == [
        {"name": "宁德时代", "symbol": "300750", "ts_code": "300750.SZ"}
    ]


def test_resolve_stock_names_falls_back_to_legacy_stock_pool_db(
    empty_main_db_path, legacy_db_path, monkeypatch
):
    monkeypatch.setattr(main_universe, "LEGACY_STOCK_POOL_DB_PATH", legacy_db_path)

    result = resolve_stock_names(["宁德时代"], db_path=empty_main_db_path)

    assert result["unresolved"] == []
    assert result["resolved"] == [
        {"name": "宁德时代", "symbol": "300750", "ts_code": "300750.SZ"}
    ]


def test_save_main_universe_replace_marks_missing_rows_inactive(db_path):
    init_main_universe_db(db_path)
    save_main_universe(
        MainUniverseSaveRequest(
            mode="replace",
            rows=[{"name": "宁德时代"}, {"name": "工业富联"}],
        ),
        db_path=db_path,
    )

    save_main_universe(
        MainUniverseSaveRequest(mode="replace", rows=[{"name": "宁德时代"}]),
        db_path=db_path,
    )

    rows = {row["name"]: row for row in list_main_universe(db_path=db_path, include_inactive=True)}
    assert rows["宁德时代"]["is_active"] == 1
    assert rows["工业富联"]["is_active"] == 0


def test_save_main_universe_replace_all_unresolved_keeps_existing_active(db_path):
    init_main_universe_db(db_path)
    save_main_universe(
        MainUniverseSaveRequest(mode="replace", rows=[{"name": "宁德时代"}]),
        db_path=db_path,
    )

    result = save_main_universe(
        MainUniverseSaveRequest(mode="replace", rows=[{"name": "不存在公司"}]),
        db_path=db_path,
    )

    rows = {row["name"]: row for row in list_main_universe(db_path=db_path, include_inactive=True)}
    assert result["saved_count"] == 0
    assert result["unresolved"] == ["不存在公司"]
    assert rows["宁德时代"]["is_active"] == 1


def test_save_main_universe_append_reactivates_inactive_symbol(db_path):
    init_main_universe_db(db_path)
    save_main_universe(
        MainUniverseSaveRequest(mode="replace", rows=[{"name": "宁德时代"}, {"name": "工业富联"}]),
        db_path=db_path,
    )
    save_main_universe(
        MainUniverseSaveRequest(mode="replace", rows=[{"name": "宁德时代"}]),
        db_path=db_path,
    )

    save_main_universe(
        MainUniverseSaveRequest(mode="append", rows=[{"name": "工业富联"}]),
        db_path=db_path,
    )

    rows = {row["name"]: row for row in list_main_universe(db_path=db_path, include_inactive=True)}
    assert rows["工业富联"]["is_active"] == 1


def test_save_main_universe_accepts_direct_symbol_without_stock_basic(empty_main_db_path):
    result = save_main_universe(
        MainUniverseSaveRequest(mode="append", rows=[{"symbol": "1", "stock_name": "平安银行"}]),
        db_path=empty_main_db_path,
    )

    assert result["saved"] == [
        {"name": "平安银行", "symbol": "000001", "ts_code": "000001.SZ"}
    ]
    assert list_main_universe(db_path=empty_main_db_path)[0]["name"] == "平安银行"


def test_normalize_symbol_and_ts_code_from_symbol():
    assert normalize_symbol("1") == "000001"
    assert normalize_symbol("300750.SZ") == "300750"
    assert ts_code_from_symbol("601138") == "601138.SH"
    assert ts_code_from_symbol("300750") == "300750.SZ"
    assert ts_code_from_symbol("430047") == "430047.BJ"


def test_resolve_stock_names_reports_duplicate_input_names(db_path):
    init_main_universe_db(db_path)

    result = resolve_stock_names(["宁德时代", "宁德时代"], db_path=db_path)

    assert result["duplicate_inputs"] == ["宁德时代"]
    assert result["unresolved"] == []
    assert result["resolved"] == [
        {"name": "宁德时代", "symbol": "300750", "ts_code": "300750.SZ"}
    ]


class FakeUniversePro:
    def stock_basic(self, exchange="", list_status="L", fields=""):
        return pd.DataFrame(
            [
                {"ts_code": "300750.SZ", "symbol": "300750", "name": "宁德时代", "industry": "电池", "market": "创业板", "list_date": "20180611"},
                {"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行", "industry": "银行", "market": "主板", "list_date": "19991110"},
                {"ts_code": "000001.SZ", "symbol": "000001", "name": "平安银行", "industry": "银行", "market": "主板", "list_date": "19910403"},
                {"ts_code": "600001.SH", "symbol": "600001", "name": "ST示例", "industry": "测试", "market": "主板", "list_date": "20000101"},
                {"ts_code": "600002.SH", "symbol": "600002", "name": "退市示例", "industry": "测试", "market": "主板", "list_date": "20000101"},
            ]
        )

    def daily_basic(self, trade_date="", fields=""):
        return pd.DataFrame(
            [
                {"ts_code": "300750.SZ", "total_mv": 12000000.0},
                {"ts_code": "600000.SH", "total_mv": 3000000.0},
                {"ts_code": "000001.SZ", "total_mv": 2999999.0},
                {"ts_code": "600001.SH", "total_mv": 9000000.0},
                {"ts_code": "600002.SH", "total_mv": 9000000.0},
            ]
        )

    def trade_cal(self, exchange="", start_date="", end_date="", is_open="1", fields=""):
        return pd.DataFrame([{"cal_date": "20240520"}])


def test_initialize_main_universe_by_market_cap_filters_non_st_above_300y(tmp_path):
    from scripts.init_main_universe_from_tushare import initialize_main_universe_by_market_cap

    result = initialize_main_universe_by_market_cap(
        pro=FakeUniversePro(),
        db_path=tmp_path / "market_data.sqlite",
        as_of="20240523",
        market_cap_min_yi=300.0,
    )

    rows = list_main_universe(db_path=tmp_path / "market_data.sqlite")
    assert result["trade_date"] == "20240520"
    assert result["candidate_count"] == 5
    assert result["selected_count"] == 1
    assert [row["symbol"] for row in rows] == ["300750"]
    assert rows[0]["source"] == "tushare_non_st_total_mv_gt_300y"
