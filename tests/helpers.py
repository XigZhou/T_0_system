from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd

from overnight_bt.stock_pool_templates import DEFAULT_USERNAME, init_stock_pool_db


def make_processed_stock(
    symbol: str,
    name: str,
    rows: list[dict],
) -> pd.DataFrame:
    frame = pd.DataFrame(rows).copy()
    frame["symbol"] = symbol
    frame["name"] = name
    frame["industry"] = frame.get("industry", "测试行业")
    frame["market"] = frame.get("market", "主板")
    frame["board"] = frame.get("board", "主板")
    frame["listed_days"] = frame.get("listed_days", 365)
    frame["total_mv_snapshot"] = frame.get("total_mv_snapshot", 800_000.0)
    frame["turnover_rate_snapshot"] = frame.get("turnover_rate_snapshot", 1.5)
    frame["raw_open"] = frame["raw_open"].astype(float)
    frame["raw_high"] = frame["raw_high"].astype(float)
    frame["raw_low"] = frame["raw_low"].astype(float)
    frame["raw_close"] = frame["raw_close"].astype(float)
    frame["qfq_open"] = frame.get("qfq_open", frame["raw_open"]).astype(float)
    frame["qfq_high"] = frame.get("qfq_high", frame["raw_high"]).astype(float)
    frame["qfq_low"] = frame.get("qfq_low", frame["raw_low"]).astype(float)
    frame["qfq_close"] = frame.get("qfq_close", frame["raw_close"]).astype(float)
    frame["open"] = frame["qfq_open"]
    frame["high"] = frame["qfq_high"]
    frame["low"] = frame["qfq_low"]
    frame["close"] = frame["qfq_close"]
    frame["adj_factor"] = frame.get("adj_factor", 1.0)
    frame["up_limit"] = frame.get("up_limit", frame["raw_close"] * 1.1).astype(float)
    frame["down_limit"] = frame.get("down_limit", frame["raw_close"] * 0.9).astype(float)
    for col in [
        "vol",
        "vol5",
        "vol10",
        "amount",
        "amount5",
        "amount10",
        "pct_chg",
        "ret1",
        "ret2",
        "ret3",
        "ma5",
        "ma10",
        "ma20",
        "bias_ma5",
        "bias_ma10",
        "amp",
        "amp5",
        "vr",
        "m5",
        "m10",
        "m20",
        "m30",
        "m60",
        "m120",
        "avg5m5",
        "avg5m10",
        "avg5m20",
        "avg5m30",
        "avg5m60",
        "avg5m120",
        "avg10m5",
        "avg10m10",
        "avg10m20",
        "avg10m30",
        "avg10m60",
        "avg10m120",
        "high_5",
        "high_10",
        "high_20",
        "low_5",
        "low_10",
        "low_20",
        "hs300_pct_chg",
        "sh_pct_chg",
        "cyb_pct_chg",
    ]:
        if col not in frame.columns:
            frame[col] = 0.0
    for col in ["next_open", "next_close", "r_on"]:
        if col not in frame.columns:
            frame[col] = pd.NA
    for col in [
        "next_raw_open",
        "next_raw_close",
        "r_on_raw",
        "close_to_up_limit",
        "high_to_up_limit",
        "close_pos_in_bar",
        "body_pct",
        "upper_shadow_pct",
        "lower_shadow_pct",
        "vol_ratio_5",
        "ret_accel_3",
        "vol_ratio_3",
        "amount_ratio_3",
        "body_pct_3avg",
        "close_to_up_limit_3max",
    ]:
        if col not in frame.columns:
            frame[col] = pd.NA
    if "can_buy_open_t" not in frame.columns:
        frame["can_buy_open_t"] = frame.get("can_buy_t", True)
    if "can_sell_t1" not in frame.columns:
        frame["can_sell_t1"] = True
    if "can_buy_open_t1" not in frame.columns:
        frame["can_buy_open_t1"] = frame.get("can_sell_t1", True)
    if "can_sell_t" not in frame.columns:
        frame["can_sell_t"] = True
    if "can_buy_t" not in frame.columns:
        frame["can_buy_t"] = True
    if "is_suspended_t" not in frame.columns:
        frame["is_suspended_t"] = False
    if "is_suspended_t1" not in frame.columns:
        frame["is_suspended_t1"] = False
    for col in ["is_suspended_t", "is_suspended_t1", "can_buy_t", "can_buy_open_t", "can_buy_open_t1", "can_sell_t", "can_sell_t1"]:
        frame[col] = frame[col].astype(bool)
    return frame


def write_processed_dir(base_dir: Path, frames: list[pd.DataFrame]) -> Path:
    target = base_dir / "processed_qfq"
    target.mkdir(parents=True, exist_ok=True)
    for frame in frames:
        symbol = str(frame.iloc[0]["symbol"])
        frame.to_csv(target / f"{symbol}.csv", index=False, encoding="utf-8-sig")
    return target



def write_stock_pool_db(
    db_path: Path,
    template_name: str,
    frames: list[pd.DataFrame],
    username: str = DEFAULT_USERNAME,
) -> Path:
    init_stock_pool_db(db_path)
    now = "2024-01-01 00:00:00"
    with sqlite3.connect(db_path) as conn:
        feature_columns = {row[1] for row in conn.execute("PRAGMA table_info(stock_daily_features)").fetchall()}
        conn.execute(
            """
            INSERT INTO users(username, password_hash, display_name, created_at, updated_at)
            VALUES(?, '', ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET updated_at=excluded.updated_at
            """,
            (username, username, now, now),
        )
        conn.execute(
            """
            INSERT INTO stock_pool_templates(template_id, username, template_name, description, is_active, created_at, updated_at)
            VALUES(?, ?, ?, '', 1, ?, ?)
            """,
            (f"test-{username}-{template_name}", username, template_name, now, now),
        )
        for order, frame in enumerate(frames):
            symbol = str(frame.iloc[0]["symbol"]).zfill(6)
            name = str(frame.iloc[0]["name"])
            ts_code = f"{symbol}.SH" if symbol.startswith(("6", "9")) else f"{symbol}.SZ"
            conn.execute(
                """
                INSERT INTO stock_pool_template_stocks(username, template_name, symbol, ts_code, stock_name, display_order, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (username, template_name, symbol, ts_code, name, order, now),
            )
            for row in frame.to_dict("records"):
                payload = dict(row)
                payload["symbol"] = symbol
                payload["ts_code"] = ts_code
                payload["name"] = str(payload.get("name") or name)
                payload["trade_date"] = str(payload["trade_date"])
                payload["created_at"] = now
                payload["updated_at"] = now
                for key in ["is_suspended_t", "can_buy_t", "can_buy_open_t", "can_sell_t", "can_sell_t1"]:
                    if key in payload:
                        payload[key] = 1 if bool(payload[key]) else 0
                payload.pop("adj_factor", None)
                payload = {key: (None if pd.isna(value) else value) for key, value in payload.items() if key in feature_columns}
                columns = ", ".join(payload.keys())
                placeholders = ", ".join(["?"] * len(payload))
                conn.execute(
                    f"INSERT OR REPLACE INTO stock_daily_features ({columns}) VALUES ({placeholders})",
                    list(payload.values()),
                )
    return db_path
