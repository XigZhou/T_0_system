from __future__ import annotations

import sqlite3

import pytest

import overnight_bt.market_data_store as market_data_store
from overnight_bt.market_data_store import (
    init_market_data_db,
    migrate_legacy_stock_pool_to_market_data,
    read_adj_factor_rows,
    read_daily_basic_snapshot,
    read_daily_raw_rows,
    read_feature_row,
    read_feature_rows,
    read_market_context_rows,
    read_trade_calendar_rows,
    upsert_adj_factor_rows,
    upsert_daily_basic_rows,
    upsert_daily_raw_rows,
    upsert_feature_rows,
    upsert_market_context_rows,
    upsert_trade_calendar_rows,
)


def _create_legacy_feature_db(path, rows):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE stock_daily_features (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                ts_code TEXT,
                name TEXT,
                raw_open REAL,
                raw_close REAL,
                close REAL,
                can_buy_open_t INTEGER,
                can_sell_t INTEGER,
                m5 REAL,
                m10 REAL,
                m20 REAL,
                amount REAL,
                PRIMARY KEY(symbol, trade_date)
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO stock_daily_features(
                symbol, trade_date, ts_code, name, raw_open, raw_close, close,
                can_buy_open_t, can_sell_t, m5, m10, m20, amount
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def test_init_market_data_db_creates_raw_input_tables(tmp_path):
    db_path = tmp_path / "market_data.sqlite"

    init_market_data_db(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        raw_columns = {row[1] for row in conn.execute("PRAGMA table_info(stock_daily_raw)")}

    assert {
        "stock_basic",
        "stock_daily_raw",
        "stock_adj_factor",
        "stock_stk_limit",
        "stock_suspend_d",
        "stock_daily_basic",
        "trade_calendar",
        "market_context",
        "stock_daily_features",
    } <= tables
    assert {"symbol", "trade_date", "ts_code", "open", "high", "low", "close", "vol", "amount"} <= raw_columns


def test_raw_input_upserts_and_reads_normalized_rows(tmp_path):
    db_path = tmp_path / "market_data.sqlite"

    raw_result = upsert_daily_raw_rows(
        [
            {
                "ts_code": "1.SZ",
                "trade_date": "20240506",
                "open": 10.1,
                "high": 10.8,
                "low": 10.0,
                "close": 10.5,
                "vol": 1000,
                "amount": 10500,
            }
        ],
        db_path=db_path,
    )
    adj_result = upsert_adj_factor_rows(
        [{"ts_code": "000001.SZ", "trade_date": "20240506", "adj_factor": 2.5}],
        db_path=db_path,
    )
    upsert_trade_calendar_rows(
        [{"trade_date": "20240506", "is_open": "1", "pretrade_date": "20240430"}],
        db_path=db_path,
    )
    upsert_market_context_rows(
        [{"trade_date": "20240506", "sh_close": 3100.0, "hs300_m5": 0.02}],
        db_path=db_path,
    )
    upsert_daily_basic_rows(
        [{"ts_code": "000001.SZ", "trade_date": "20240506", "total_mv": 123.4, "turnover_rate_f": 1.5}],
        db_path=db_path,
    )

    raw_rows = read_daily_raw_rows("000001", "20240501", "20240531", db_path=db_path)
    adj_rows = read_adj_factor_rows("000001", "20240501", "20240531", db_path=db_path)
    calendar_rows = read_trade_calendar_rows("20240501", "20240531", db_path=db_path)
    market_rows = read_market_context_rows("20240501", "20240531", db_path=db_path)
    daily_basic = read_daily_basic_snapshot("20240506", db_path=db_path)

    assert raw_result["rows_written"] == 1
    assert adj_result["rows_written"] == 1
    assert raw_rows[0]["symbol"] == "000001"
    assert raw_rows[0]["ts_code"] == "000001.SZ"
    assert raw_rows[0]["close"] == 10.5
    assert adj_rows[0]["adj_factor"] == 2.5
    assert calendar_rows == [{"trade_date": "20240506", "exchange": "", "is_open": "1", "pretrade_date": "20240430"}]
    assert market_rows[0]["sh_close"] == 3100.0
    assert daily_basic[0]["symbol"] == "000001"
    assert daily_basic[0]["total_mv"] == 123.4


def test_read_feature_rows_filters_symbols_and_dates(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    upsert_feature_rows(
        [
            {
                "symbol": "1",
                "trade_date": "20240506",
                "ts_code": "000001.SZ",
                "name": "Sample Stock",
                "raw_open": 10.1,
                "raw_close": 10.5,
                "close": 10.5,
                "can_buy_open_t": 1,
                "can_sell_t": 1,
                "m5": 0.02,
                "m10": 0.03,
                "m20": 0.04,
                "amount": 123456.7,
            },
            {
                "symbol": "600000",
                "trade_date": "20240506",
                "ts_code": "600000.SH",
                "name": "Sample Stock",
                "raw_open": 8.2,
                "raw_close": 8.4,
                "close": 8.4,
                "can_buy_open_t": 1,
                "can_sell_t": 1,
                "m5": 0.01,
                "m10": 0.02,
                "m20": 0.03,
                "amount": 765432.1,
            },
        ],
        db_path=db_path,
    )

    rows = read_feature_rows(["000001"], start_date="20240506", end_date="20240506", db_path=db_path)

    assert len(rows) == 1
    assert rows[0]["symbol"] == "000001"
    assert rows[0]["raw_open"] == 10.1
    assert rows[0]["raw_close"] == 10.5


def test_upsert_feature_rows_preserves_extra_indicator_columns(tmp_path):
    db_path = tmp_path / "market_data.sqlite"

    upsert_feature_rows(
        [
            {
                "symbol": "300750",
                "trade_date": "20240506",
                "ts_code": "300750.SZ",
                "name": "Sample Stock",
                "raw_open": 200.0,
                "raw_close": 205.5,
                "close": 205.5,
                "can_buy_open_t": 1,
                "can_sell_t": 1,
                "m5": 0.05,
                "m10": 0.08,
                "m20": 0.12,
                "amount": 888888.0,
                "custom_factor": 1.2345,
                "sector_score": 87.6,
            }
        ],
        db_path=db_path,
    )

    rows = read_feature_rows(["300750"], start_date="20240506", end_date="20240506", db_path=db_path)

    assert rows[0]["custom_factor"] == 1.2345
    assert rows[0]["sector_score"] == 87.6


def test_upsert_feature_rows_infers_extra_column_type_from_first_non_null_value(tmp_path):
    db_path = tmp_path / "market_data.sqlite"

    upsert_feature_rows(
        [
            {
                "symbol": "300750",
                "trade_date": "20240506",
                "raw_close": 200.0,
                "ma5": None,
            },
            {
                "symbol": "300750",
                "trade_date": "20240507",
                "raw_close": 205.5,
                "ma5": 202.2,
            },
        ],
        db_path=db_path,
    )

    with sqlite3.connect(db_path) as conn:
        column_types = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(stock_daily_features)")}
        value = conn.execute(
            """
            SELECT ma5
            FROM stock_daily_features
            WHERE symbol = ? AND trade_date = ?
            """,
            ("300750", "20240507"),
        ).fetchone()[0]

    assert column_types["ma5"] == "REAL"
    assert value == 202.2


def test_read_feature_rows_falls_back_to_legacy_db_without_creating_primary_db(tmp_path):
    db_path = tmp_path / "missing_primary.sqlite"
    legacy_db_path = tmp_path / "stock_pool_templates.sqlite"
    _create_legacy_feature_db(
        legacy_db_path,
        [
            (
                "000001",
                "20240506",
                "000001.SZ",
                "Sample Stock",
                10.1,
                10.5,
                10.5,
                1,
                1,
                0.02,
                0.03,
                0.04,
                123456.7,
            )
        ],
    )

    rows = read_feature_rows(["1"], start_date="20240506", end_date="20240506", db_path=db_path, legacy_db_path=legacy_db_path)

    assert rows == [
        {
            "symbol": "000001",
            "trade_date": "20240506",
            "ts_code": "000001.SZ",
            "name": "Sample Stock",
            "raw_open": 10.1,
            "raw_close": 10.5,
            "close": 10.5,
            "can_buy_open_t": 1,
            "can_sell_t": 1,
            "m5": 0.02,
            "m10": 0.03,
            "m20": 0.04,
            "amount": 123456.7,
        }
    ]
    assert not db_path.exists()


def test_read_feature_rows_can_disable_legacy_fallback(tmp_path, monkeypatch):
    db_path = tmp_path / "missing_primary.sqlite"
    legacy_db_path = tmp_path / "stock_pool_templates.sqlite"
    _create_legacy_feature_db(
        legacy_db_path,
        [
            (
                "000001",
                "20240506",
                "000001.SZ",
                "Sample Stock",
                10.1,
                10.5,
                10.5,
                1,
                1,
                0.02,
                0.03,
                0.04,
                123456.7,
            )
        ],
    )
    monkeypatch.setattr(market_data_store, "LEGACY_STOCK_POOL_DB_PATH", legacy_db_path)

    rows = read_feature_rows(
        ["1"],
        start_date="20240506",
        end_date="20240506",
        db_path=db_path,
        legacy_db_path=market_data_store.DISABLE_LEGACY_FALLBACK,
    )

    assert rows == []
    assert not db_path.exists()


def test_read_feature_row_returns_single_row(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    upsert_feature_rows(
        [
            {
                "symbol": "000001",
                "trade_date": "20240506",
                "ts_code": "000001.SZ",
                "name": "Sample Stock",
                "raw_open": 10.1,
                "raw_close": 10.5,
                "close": 10.5,
                "can_buy_open_t": 1,
                "can_sell_t": 1,
                "m5": 0.02,
                "m10": 0.03,
                "m20": 0.04,
                "amount": 123456.7,
            },
            {
                "symbol": "000001",
                "trade_date": "20240507",
                "ts_code": "000001.SZ",
                "name": "Sample Stock",
                "raw_open": 10.6,
                "raw_close": 10.8,
                "close": 10.8,
                "can_buy_open_t": 1,
                "can_sell_t": 1,
                "m5": 0.03,
                "m10": 0.04,
                "m20": 0.05,
                "amount": 223456.7,
            },
        ],
        db_path=db_path,
    )

    row = read_feature_row("1", "20240507", db_path=db_path)

    assert row is not None
    assert row["symbol"] == "000001"
    assert row["trade_date"] == "20240507"
    assert row["raw_close"] == 10.8


def test_init_market_data_db_adds_missing_base_columns(tmp_path):
    from overnight_bt.market_data_store import init_market_data_db

    db_path = tmp_path / "market_data.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE stock_daily_features (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                PRIMARY KEY(symbol, trade_date)
            )
            """
        )

    init_market_data_db(db_path)

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(stock_daily_features)")}
    assert {
        "symbol",
        "trade_date",
        "ts_code",
        "name",
        "raw_open",
        "raw_close",
        "close",
        "can_buy_open_t",
        "can_sell_t",
        "m5",
        "m10",
        "m20",
        "amount",
    } <= columns



def test_sparse_upsert_does_not_null_existing_extra_columns(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    upsert_feature_rows(
        [
            {
                "symbol": "000001",
                "trade_date": "20240506",
                "raw_open": 10.0,
                "raw_close": 10.5,
                "custom_factor": 1.2,
            }
        ],
        db_path=db_path,
    )

    upsert_feature_rows(
        [
            {
                "symbol": "000001",
                "trade_date": "20240506",
                "raw_open": 10.2,
                "raw_close": 10.6,
            },
            {
                "symbol": "000002",
                "trade_date": "20240506",
                "raw_open": 20.0,
                "raw_close": 20.5,
                "custom_factor": 2.4,
            },
        ],
        db_path=db_path,
    )

    rows = read_feature_rows(["000001", "000002"], start_date="20240506", end_date="20240506", db_path=db_path)

    by_symbol = {row["symbol"]: row for row in rows}
    assert by_symbol["000001"]["raw_open"] == 10.2
    assert by_symbol["000001"]["custom_factor"] == 1.2
    assert by_symbol["000002"]["custom_factor"] == 2.4


def test_upsert_into_existing_wide_schema_fills_audit_columns(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE stock_daily_features (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                ts_code TEXT,
                name TEXT,
                raw_open REAL,
                raw_close REAL,
                close REAL,
                can_buy_open_t INTEGER,
                can_sell_t INTEGER,
                m5 REAL,
                m10 REAL,
                m20 REAL,
                amount REAL,
                PRIMARY KEY(symbol, trade_date)
            )
            """
        )

    upsert_feature_rows(
        [
            {
                "symbol": "000001",
                "trade_date": "20240506",
                "raw_open": 10.1,
                "raw_close": 10.5,
            }
        ],
        db_path=db_path,
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT created_at, updated_at
            FROM stock_daily_features
            WHERE symbol = ? AND trade_date = ?
            """,
            ("000001", "20240506"),
        ).fetchone()
    assert row[0]
    assert row[1]


def test_read_feature_rows_merges_partial_primary_with_legacy(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    legacy_db_path = tmp_path / "stock_pool_templates.sqlite"
    upsert_feature_rows(
        [
            {
                "symbol": "000001",
                "trade_date": "20240506",
                "name": "Primary Stock",
                "raw_open": 11.1,
                "raw_close": 11.5,
            }
        ],
        db_path=db_path,
    )
    _create_legacy_feature_db(
        legacy_db_path,
        [
            (
                "000001",
                "20240506",
                "000001.SZ",
                "Legacy Stock 1",
                10.1,
                10.5,
                10.5,
                1,
                1,
                0.02,
                0.03,
                0.04,
                123456.7,
            ),
            (
                "000002",
                "20240506",
                "000002.SZ",
                "Legacy Stock 2",
                20.1,
                20.5,
                20.5,
                1,
                1,
                0.05,
                0.06,
                0.07,
                223456.7,
            ),
        ],
    )

    rows = read_feature_rows(
        ["000001", "000002"],
        start_date="20240506",
        end_date="20240506",
        db_path=db_path,
        legacy_db_path=legacy_db_path,
    )

    assert [row["symbol"] for row in rows] == ["000001", "000002"]
    by_symbol = {row["symbol"]: row for row in rows}
    assert by_symbol["000001"]["name"] == "Primary Stock"
    assert by_symbol["000001"]["raw_open"] == 11.1
    assert by_symbol["000002"]["name"] == "Legacy Stock 2"
    assert by_symbol["000002"]["raw_open"] == 20.1


def test_read_feature_rows_empty_symbols_returns_empty_without_full_scan(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    upsert_feature_rows(
        [
            {
                "symbol": "000001",
                "trade_date": "20240506",
                "raw_open": 10.1,
                "raw_close": 10.5,
            }
        ],
        db_path=db_path,
    )

    assert read_feature_rows([], db_path=db_path) == []


def test_upsert_rejects_invalid_extra_column_name(tmp_path):
    db_path = tmp_path / "market_data.sqlite"

    with pytest.raises(ValueError, match="invalid SQL identifier"):
        upsert_feature_rows(
            [
                {
                    "symbol": "000001",
                    "trade_date": "20240506",
                    "raw_open": 10.1,
                    "bad-column": 1.0,
                }
            ],
            db_path=db_path,
        )



def test_read_feature_rows_default_legacy_path_merges_partial_primary(tmp_path, monkeypatch):
    db_path = tmp_path / "market_data.sqlite"
    legacy_db_path = tmp_path / "stock_pool_templates.sqlite"
    monkeypatch.setattr(market_data_store, "LEGACY_STOCK_POOL_DB_PATH", legacy_db_path)
    upsert_feature_rows(
        [
            {
                "symbol": "000001",
                "trade_date": "20240506",
                "name": "Primary Stock",
                "raw_open": 11.1,
                "raw_close": 11.5,
            }
        ],
        db_path=db_path,
    )
    _create_legacy_feature_db(
        legacy_db_path,
        [
            (
                "000001",
                "20240506",
                "000001.SZ",
                "Legacy Stock 1",
                10.1,
                10.5,
                10.5,
                1,
                1,
                0.02,
                0.03,
                0.04,
                123456.7,
            ),
            (
                "000002",
                "20240506",
                "000002.SZ",
                "Legacy Stock 2",
                20.1,
                20.5,
                20.5,
                1,
                1,
                0.05,
                0.06,
                0.07,
                223456.7,
            ),
        ],
    )

    rows = read_feature_rows(["000001", "000002"], start_date="20240506", end_date="20240506", db_path=db_path)

    assert [row["symbol"] for row in rows] == ["000001", "000002"]
    by_symbol = {row["symbol"]: row for row in rows}
    assert by_symbol["000001"]["name"] == "Primary Stock"
    assert by_symbol["000001"]["raw_open"] == 11.1
    assert by_symbol["000002"]["name"] == "Legacy Stock 2"
    assert by_symbol["000002"]["raw_open"] == 20.1


def test_conflict_upsert_preserves_created_at_and_updates_updated_at(tmp_path):
    db_path = tmp_path / "market_data.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE stock_daily_features (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                raw_open REAL,
                raw_close REAL,
                PRIMARY KEY(symbol, trade_date)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO stock_daily_features(symbol, trade_date, created_at, updated_at, raw_open, raw_close)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("000001", "20240506", "old-created", "old-updated", 10.0, 10.5),
        )

    upsert_feature_rows(
        [
            {
                "symbol": "000001",
                "trade_date": "20240506",
                "raw_open": 10.2,
                "raw_close": 10.8,
            }
        ],
        db_path=db_path,
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT created_at, updated_at, raw_open, raw_close
            FROM stock_daily_features
            WHERE symbol = ? AND trade_date = ?
            """,
            ("000001", "20240506"),
        ).fetchone()
    assert row[0] == "old-created"
    assert row[1]
    assert row[1] != "old-updated"
    assert row[2] == 10.2
    assert row[3] == 10.8


def test_migrate_legacy_stock_pool_to_market_data_copies_features_and_seeds_universe(tmp_path):
    legacy_db_path = tmp_path / "stock_pool_templates.sqlite"
    market_db_path = tmp_path / "market_data.sqlite"
    _create_legacy_feature_db(
        legacy_db_path,
        [
            (
                "000001",
                "20240506",
                "000001.SZ",
                "平安银行",
                10.1,
                10.5,
                10.5,
                1,
                1,
                0.02,
                0.03,
                0.04,
                123456.7,
            ),
            (
                "300750",
                "20240506",
                "300750.SZ",
                "宁德时代",
                200.1,
                205.5,
                205.5,
                1,
                1,
                0.05,
                0.06,
                0.07,
                223456.7,
            ),
        ],
    )
    with sqlite3.connect(legacy_db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE stock_pool_templates (
                template_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                template_name TEXT NOT NULL,
                description TEXT DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(username, template_name)
            );
            CREATE TABLE stock_pool_template_stocks (
                username TEXT NOT NULL,
                template_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                ts_code TEXT NOT NULL,
                stock_name TEXT DEFAULT '',
                display_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                PRIMARY KEY(username, template_name, symbol)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO stock_pool_templates(template_id, username, template_name, is_active, created_at, updated_at)
            VALUES ('tpl-1', 'admin', '生产股票池', 1, '2024-01-01', '2024-01-01')
            """
        )
        conn.executemany(
            """
            INSERT INTO stock_pool_template_stocks(username, template_name, symbol, ts_code, stock_name, display_order, created_at)
            VALUES ('admin', '生产股票池', ?, ?, ?, ?, '2024-01-01')
            """,
            [
                ("000001", "000001.SZ", "平安银行", 1),
                ("300750", "300750.SZ", "宁德时代", 2),
            ],
        )

    result = migrate_legacy_stock_pool_to_market_data(
        legacy_db_path=legacy_db_path,
        market_db_path=market_db_path,
    )

    assert result["feature_rows_copied"] == 2
    assert result["main_universe_rows_upserted"] == 2
    rows = read_feature_rows(
        ["000001", "300750"],
        start_date="20240506",
        end_date="20240506",
        db_path=market_db_path,
        legacy_db_path=market_data_store.DISABLE_LEGACY_FALLBACK,
    )
    assert [row["symbol"] for row in rows] == ["000001", "300750"]
    with sqlite3.connect(market_db_path) as conn:
        universe = conn.execute(
            """
            SELECT symbol, ts_code, name, source, is_active
            FROM main_stock_universe
            ORDER BY symbol
            """
        ).fetchall()
    assert universe == [
        ("000001", "000001.SZ", "平安银行", "legacy_template_migration", 1),
        ("300750", "300750.SZ", "宁德时代", "legacy_template_migration", 1),
    ]


def test_sqlite_only_blocks_legacy_feature_fallback(tmp_path, monkeypatch):
    db_path = tmp_path / "missing_primary.sqlite"
    legacy_db_path = tmp_path / "stock_pool_templates.sqlite"
    _create_legacy_feature_db(
        legacy_db_path,
        [
            (
                "000001",
                "20240506",
                "000001.SZ",
                "Sample Stock",
                10.1,
                10.5,
                10.5,
                1,
                1,
                0.02,
                0.03,
                0.04,
                123456.7,
            )
        ],
    )
    monkeypatch.setenv("T0_SQLITE_ONLY", "1")

    with pytest.raises(RuntimeError, match="SQLite-only mode blocks legacy source"):
        read_feature_rows(["000001"], db_path=db_path, legacy_db_path=legacy_db_path)


def test_sqlite_only_allows_disabled_legacy_fallback_sentinel(tmp_path, monkeypatch):
    db_path = tmp_path / "missing_primary.sqlite"
    monkeypatch.setenv("T0_SQLITE_ONLY", "1")

    rows = read_feature_rows(
        ["000001"],
        db_path=db_path,
        legacy_db_path=market_data_store.DISABLE_LEGACY_FALLBACK,
    )

    assert rows == []
