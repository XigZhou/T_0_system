from __future__ import annotations

import sqlite3

from overnight_bt.trade_calendar import is_a_share_trade_day


def _seed_feature_date(db_path, trade_date: str = "20260521") -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE stock_daily_features (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                raw_close REAL,
                close REAL,
                PRIMARY KEY(symbol, trade_date)
            )
            """
        )
        conn.execute(
            "INSERT INTO stock_daily_features(symbol, trade_date, raw_close, close) VALUES (?, ?, ?, ?)",
            ("601138", trade_date, 65.5, 65.5),
        )


def test_trade_day_falls_back_to_market_data_sqlite_when_token_is_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    db_path = tmp_path / "market_data.sqlite"
    _seed_feature_date(db_path)

    assert is_a_share_trade_day("20260521", env_path=env_path, market_db_path=db_path) is True
