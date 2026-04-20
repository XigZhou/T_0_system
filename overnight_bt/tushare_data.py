from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import DEFAULT_INDEXES
from .processing import build_market_context_from_indexes
from .utils import ensure_dir, latest_open_trade_date, load_env


@dataclass
class SnapshotBuildConfig:
    env_path: Path
    out_csv: Path
    as_of: str
    min_mv_yi: float = 500.0


@dataclass
class SyncConfig:
    env_path: Path
    bundle_dir: Path
    snapshot_csv: Path
    start_date: str
    end_date: str
    sleep_seconds: float = 0.2


def _create_pro_client(env_path: Path):
    import tushare as ts

    env = load_env(env_path)
    token = env.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise ValueError(f"TUSHARE_TOKEN is empty in {env_path}")
    return ts.pro_api(token)


def build_universe_snapshot(config: SnapshotBuildConfig) -> Path:
    pro = _create_pro_client(config.env_path)
    trade_date = latest_open_trade_date(pro, config.as_of)
    basic = pro.stock_basic(
        exchange="",
        list_status="L",
        fields="ts_code,symbol,name,area,industry,market,list_date",
    )
    daily = pro.daily_basic(
        trade_date=trade_date,
        fields="ts_code,close,total_mv,turnover_rate_f,pe_ttm,pb",
    )
    if basic is None or basic.empty or daily is None or daily.empty:
        raise RuntimeError("failed to build universe snapshot from tushare")
    merged = basic.merge(daily, on="ts_code", how="inner")
    filtered = merged[~merged["name"].astype(str).str.contains("ST", case=False, na=False)].copy()
    filtered = filtered[pd.to_numeric(filtered["total_mv"], errors="coerce").fillna(0) >= config.min_mv_yi * 10000.0].copy()
    filtered = filtered.sort_values(["total_mv", "turnover_rate_f"], ascending=[False, False]).reset_index(drop=True)
    ensure_dir(config.out_csv.parent)
    filtered.to_csv(config.out_csv, index=False, encoding="utf-8-sig")
    return config.out_csv


def sync_tushare_bundle(config: SyncConfig) -> dict[str, str]:
    pro = _create_pro_client(config.env_path)
    bundle_dir = ensure_dir(config.bundle_dir)
    raw_dir = ensure_dir(bundle_dir / "raw_daily")
    adj_dir = ensure_dir(bundle_dir / "adj_factor")

    snapshot = pd.read_csv(config.snapshot_csv, dtype=str, encoding="utf-8-sig")

    cal = pro.trade_cal(
        exchange="",
        start_date=config.start_date,
        end_date=config.end_date,
        is_open="1",
        fields="exchange,cal_date,is_open,pretrade_date",
    )
    cal = cal.rename(columns={"cal_date": "trade_date"})
    cal.to_csv(bundle_dir / "trade_calendar.csv", index=False, encoding="utf-8-sig")

    index_frames: dict[str, pd.DataFrame] = {}
    for alias, ts_code, _ in DEFAULT_INDEXES:
        frame = pro.index_daily(ts_code=ts_code, start_date=config.start_date, end_date=config.end_date)
        if frame is None or frame.empty:
            raise RuntimeError(f"index_daily returned empty data for {ts_code}")
        index_frames[alias] = frame
    market_context = build_market_context_from_indexes(index_frames)
    market_context.to_csv(bundle_dir / "market_context.csv", index=False, encoding="utf-8-sig")

    stk_limit_frames: list[pd.DataFrame] = []
    suspend_frames: list[pd.DataFrame] = []
    for row in snapshot.to_dict(orient="records"):
        symbol = str(row["symbol"]).strip()
        ts_code = str(row["ts_code"]).strip()
        daily = pro.daily(ts_code=ts_code, start_date=config.start_date, end_date=config.end_date)
        adj = pro.adj_factor(ts_code=ts_code, start_date=config.start_date, end_date=config.end_date)
        stk_limit = pro.stk_limit(ts_code=ts_code, start_date=config.start_date, end_date=config.end_date)
        suspend_d = pro.suspend_d(ts_code=ts_code, start_date=config.start_date, end_date=config.end_date)
        if daily is None or daily.empty:
            continue
        if adj is None or adj.empty:
            raise RuntimeError(f"adj_factor returned empty data for {ts_code}")
        if stk_limit is not None and not stk_limit.empty:
            stk_limit_frames.append(stk_limit)
        if suspend_d is not None and not suspend_d.empty:
            suspend_frames.append(suspend_d)
        daily.sort_values("trade_date").to_csv(raw_dir / f"{symbol}.csv", index=False, encoding="utf-8-sig")
        adj.sort_values("trade_date").to_csv(adj_dir / f"{symbol}.csv", index=False, encoding="utf-8-sig")
        time.sleep(config.sleep_seconds)

    stk_limit_all = (
        pd.concat(stk_limit_frames, ignore_index=True)
        if stk_limit_frames
        else pd.DataFrame(columns=["ts_code", "trade_date", "up_limit", "down_limit"])
    )
    stk_limit_all = stk_limit_all.drop_duplicates(subset=["ts_code", "trade_date"]).sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    stk_limit_all.to_csv(bundle_dir / "stk_limit.csv", index=False, encoding="utf-8-sig")

    suspend_all = (
        pd.concat(suspend_frames, ignore_index=True)
        if suspend_frames
        else pd.DataFrame(columns=["ts_code", "trade_date", "suspend_type", "suspend_timing"])
    )
    suspend_all = suspend_all.drop_duplicates(subset=["ts_code", "trade_date"]).sort_values(["trade_date", "ts_code"]).reset_index(drop=True)
    suspend_all.to_csv(bundle_dir / "suspend_d.csv", index=False, encoding="utf-8-sig")

    return {
        "bundle_dir": str(bundle_dir),
        "raw_daily_dir": str(raw_dir),
        "adj_factor_dir": str(adj_dir),
        "snapshot_csv": str(config.snapshot_csv),
        "trade_calendar_csv": str(bundle_dir / "trade_calendar.csv"),
        "market_context_csv": str(bundle_dir / "market_context.csv"),
        "stk_limit_csv": str(bundle_dir / "stk_limit.csv"),
        "suspend_d_csv": str(bundle_dir / "suspend_d.csv"),
    }
