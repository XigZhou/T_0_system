from __future__ import annotations

from pathlib import Path

import pandas as pd


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
    for col in ["is_suspended_t", "is_suspended_t1", "can_buy_t", "can_sell_t", "can_sell_t1"]:
        frame[col] = frame[col].astype(bool)
    return frame


def write_processed_dir(base_dir: Path, frames: list[pd.DataFrame]) -> Path:
    target = base_dir / "processed_qfq"
    target.mkdir(parents=True, exist_ok=True)
    for frame in frames:
        symbol = str(frame.iloc[0]["symbol"])
        frame.to_csv(target / f"{symbol}.csv", index=False, encoding="utf-8-sig")
    return target
