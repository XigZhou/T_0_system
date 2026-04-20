from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from .config import DEFAULT_HORIZONS, DEFAULT_INDEXES, REQUIRED_PROCESSED_COLUMNS
from .indicators import compute_indicators
from .utils import ensure_dir, infer_board, normalize_date_text


@dataclass
class ProcessingResult:
    symbol: str
    status: str
    rows: int
    output_path: str
    message: str = ""


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig")


def _merge_adj_factor(raw_df: pd.DataFrame, adj_df: pd.DataFrame) -> pd.DataFrame:
    work = raw_df.copy()
    adj = adj_df.copy()
    work["trade_date"] = work["trade_date"].astype(str).str.strip()
    adj["trade_date"] = adj["trade_date"].astype(str).str.strip()
    adj["adj_factor"] = pd.to_numeric(adj["adj_factor"], errors="coerce")
    merged = work.merge(adj[["trade_date", "adj_factor"]], on="trade_date", how="left")
    merged = merged.sort_values("trade_date").reset_index(drop=True)
    merged["adj_factor"] = merged["adj_factor"].ffill()
    latest_factor = merged["adj_factor"].dropna().iloc[-1] if merged["adj_factor"].notna().any() else None
    if latest_factor is None or latest_factor == 0:
        raise ValueError("adj_factor data missing latest valid factor")
    scale = merged["adj_factor"] / float(latest_factor)
    for col in ["open", "high", "low", "close"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
        merged[f"raw_{col}"] = merged[col]
        merged[f"qfq_{col}"] = (merged[col] * scale).round(4)
    return merged


def _build_calendar_frame(trade_calendar: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    cal = trade_calendar.copy()
    cal["trade_date"] = cal["trade_date"].astype(str).str.strip()
    cal = cal[(cal["trade_date"] >= start_date) & (cal["trade_date"] <= end_date)].copy()
    cal = cal[["trade_date"]].drop_duplicates().sort_values("trade_date").reset_index(drop=True)
    return cal


def _prepare_limit_frame(limit_df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
    if limit_df.empty:
        return pd.DataFrame(columns=["trade_date", "up_limit", "down_limit"])
    use = limit_df[limit_df["ts_code"].astype(str).str.strip() == ts_code].copy()
    if use.empty:
        return pd.DataFrame(columns=["trade_date", "up_limit", "down_limit"])
    for col in ["up_limit", "down_limit"]:
        use[col] = pd.to_numeric(use[col], errors="coerce")
    return use[["trade_date", "up_limit", "down_limit"]]


def _prepare_suspend_set(suspend_df: pd.DataFrame, ts_code: str) -> set[str]:
    if suspend_df.empty:
        return set()
    use = suspend_df[suspend_df["ts_code"].astype(str).str.strip() == ts_code].copy()
    if use.empty:
        return set()
    return set(use["trade_date"].astype(str).str.strip().tolist())


def _prepare_market_context(market_df: pd.DataFrame) -> pd.DataFrame:
    work = market_df.copy()
    work["trade_date"] = work["trade_date"].astype(str).str.strip()
    return work


def build_market_context_from_indexes(index_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    merged: pd.DataFrame | None = None
    for alias, _, _ in DEFAULT_INDEXES:
        raw_df = index_frames[alias].copy()
        features = compute_indicators(raw_df, horizons=DEFAULT_HORIZONS)
        keep_cols = [col for col in features.columns if col != "ts_code"]
        features = features[keep_cols].copy()
        rename_map = {col: f"{alias}_{col}" for col in features.columns if col != "trade_date"}
        features = features.rename(columns=rename_map)
        merged = features if merged is None else merged.merge(features, on="trade_date", how="outer")
    if merged is None:
        raise ValueError("index_frames is empty")
    return merged.sort_values("trade_date").reset_index(drop=True)


def build_processed_frame(
    raw_df: pd.DataFrame,
    adj_df: pd.DataFrame,
    snapshot_row: pd.Series,
    trade_calendar: pd.DataFrame,
    limit_df: pd.DataFrame,
    suspend_df: pd.DataFrame,
    market_context: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    ts_code = str(snapshot_row["ts_code"]).strip()
    symbol = str(snapshot_row["symbol"]).strip()
    name = str(snapshot_row["name"]).strip()
    listed_from = normalize_date_text(snapshot_row["list_date"])

    raw = _merge_adj_factor(raw_df, adj_df)
    raw["trade_date"] = raw["trade_date"].astype(str).str.strip()
    raw["vol"] = pd.to_numeric(raw.get("vol"), errors="coerce")
    raw["amount"] = pd.to_numeric(raw.get("amount"), errors="coerce")
    raw["pre_close"] = pd.to_numeric(raw.get("pre_close"), errors="coerce")
    raw["change"] = pd.to_numeric(raw.get("change"), errors="coerce")
    raw["pct_chg"] = pd.to_numeric(raw.get("pct_chg"), errors="coerce")

    calendar = _build_calendar_frame(trade_calendar, max(start_date, listed_from), end_date)
    work = calendar.merge(raw, on="trade_date", how="left")
    work["ts_code"] = ts_code
    work["symbol"] = symbol
    work["name"] = name

    limits = _prepare_limit_frame(limit_df, ts_code)
    work = work.merge(limits, on="trade_date", how="left")

    suspend_set = _prepare_suspend_set(suspend_df, ts_code)
    work["is_suspended_t"] = work["trade_date"].isin(suspend_set) | work["raw_close"].isna()
    work["is_suspended_t"] = work["is_suspended_t"].fillna(False)
    work["is_suspended_t1"] = work["is_suspended_t"].shift(-1).fillna(True)

    raw_open = pd.to_numeric(work["raw_open"], errors="coerce")
    raw_high = pd.to_numeric(work["raw_high"], errors="coerce")
    raw_low = pd.to_numeric(work["raw_low"], errors="coerce")
    raw_close = pd.to_numeric(work["raw_close"], errors="coerce")
    up_limit = pd.to_numeric(work["up_limit"], errors="coerce")
    next_raw_open = raw_open.shift(-1)
    next_down_limit = pd.to_numeric(work["down_limit"], errors="coerce").shift(-1)
    next_raw_close = raw_close.shift(-1)

    work["can_buy_t"] = (
        (~work["is_suspended_t"])
        & raw_close.notna()
        & (
            work["up_limit"].isna()
            | (raw_close < up_limit * 0.9995)
        )
    )
    work["can_sell_t"] = (
        (~work["is_suspended_t"])
        & pd.to_numeric(work["raw_open"], errors="coerce").notna()
        & (
            work["down_limit"].isna()
            | (pd.to_numeric(work["raw_open"], errors="coerce") > pd.to_numeric(work["down_limit"], errors="coerce") * 1.0005)
        )
    )
    work["can_sell_t1"] = (
        (~work["is_suspended_t1"])
        & next_raw_open.notna()
        & (next_down_limit.isna() | (next_raw_open > next_down_limit * 1.0005))
    )

    features_base = work[["trade_date", "qfq_open", "qfq_high", "qfq_low", "qfq_close", "vol", "amount"]].rename(
        columns={
            "qfq_open": "open",
            "qfq_high": "high",
            "qfq_low": "low",
            "qfq_close": "close",
        }
    )
    features = compute_indicators(features_base, horizons=DEFAULT_HORIZONS)
    work = work.merge(features, on="trade_date", how="left", suffixes=("", "_calc"))

    work["open"] = work["qfq_open"]
    work["high"] = work["qfq_high"]
    work["low"] = work["qfq_low"]
    work["close"] = work["qfq_close"]
    work["next_open"] = pd.to_numeric(work["open"], errors="coerce").shift(-1)
    work["next_close"] = pd.to_numeric(work["close"], errors="coerce").shift(-1)
    work["r_on"] = (work["next_open"] / pd.to_numeric(work["close"], errors="coerce") - 1.0).round(4)
    work["next_raw_open"] = next_raw_open
    work["next_raw_close"] = next_raw_close
    work["r_on_raw"] = next_raw_open / raw_close - 1.0

    bar_range = raw_high - raw_low
    real_body_high = pd.concat([raw_open, raw_close], axis=1).max(axis=1)
    real_body_low = pd.concat([raw_open, raw_close], axis=1).min(axis=1)
    base_open = raw_open.where(raw_open != 0)
    work["close_to_up_limit"] = raw_close / up_limit
    work["high_to_up_limit"] = raw_high / up_limit
    work["close_pos_in_bar"] = (raw_close - raw_low) / bar_range
    work.loc[bar_range <= 0, "close_pos_in_bar"] = pd.NA
    work["body_pct"] = (raw_close - raw_open) / base_open
    work["upper_shadow_pct"] = (raw_high - real_body_high) / base_open
    work["lower_shadow_pct"] = (real_body_low - raw_low) / base_open
    work["vol_ratio_3"] = pd.to_numeric(work["vol"], errors="coerce") / pd.to_numeric(work["vol"], errors="coerce").rolling(3).mean()
    work["amount_ratio_3"] = pd.to_numeric(work["amount"], errors="coerce") / pd.to_numeric(work["amount"], errors="coerce").rolling(3).mean()
    work["body_pct_3avg"] = pd.to_numeric(work["body_pct"], errors="coerce").rolling(3).mean()
    work["close_to_up_limit_3max"] = pd.to_numeric(work["close_to_up_limit"], errors="coerce").rolling(3).max()

    work["industry"] = snapshot_row.get("industry")
    work["market"] = snapshot_row.get("market")
    work["board"] = infer_board(symbol)
    listed_date = pd.to_datetime(pd.Series([listed_from]), format="%Y%m%d", errors="coerce").iloc[0]
    trade_dates = pd.to_datetime(work["trade_date"], format="%Y%m%d", errors="coerce")
    work["listed_days"] = (trade_dates - listed_date).dt.days
    work["total_mv_snapshot"] = pd.to_numeric(pd.Series([snapshot_row.get("total_mv")]), errors="coerce").iloc[0]
    work["turnover_rate_snapshot"] = pd.to_numeric(pd.Series([snapshot_row.get("turnover_rate_f")]), errors="coerce").iloc[0]

    market = _prepare_market_context(market_context)
    work = work.merge(market, on="trade_date", how="left")
    work["vol_ratio_5"] = pd.to_numeric(work["vol"], errors="coerce") / pd.to_numeric(work["vol5"], errors="coerce")
    work["ret_accel_3"] = pd.to_numeric(work["ret1"], errors="coerce") - pd.to_numeric(work["ret3"], errors="coerce") / 3.0
    work = work.sort_values("trade_date").drop_duplicates(subset=["trade_date"], keep="last").reset_index(drop=True)
    return work


def validate_processed_frame(df: pd.DataFrame) -> None:
    missing = REQUIRED_PROCESSED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"processed frame missing required columns: {sorted(missing)}")
    if not df["trade_date"].astype(str).is_monotonic_increasing:
        raise ValueError("processed frame trade_date must be ascending")
    if df["trade_date"].astype(str).duplicated().any():
        raise ValueError("processed frame trade_date contains duplicates")


def build_processed_dataset(
    bundle_dir: Path,
    output_dir: Path,
    snapshot_csv: Path | None = None,
    horizons: Iterable[int] | None = None,
) -> list[ProcessingResult]:
    _ = horizons
    snapshot_path = snapshot_csv or bundle_dir / "universe_snapshot.csv"
    trade_calendar_path = bundle_dir / "trade_calendar.csv"
    stk_limit_path = bundle_dir / "stk_limit.csv"
    suspend_path = bundle_dir / "suspend_d.csv"
    market_context_path = bundle_dir / "market_context.csv"
    raw_dir = bundle_dir / "raw_daily"
    adj_dir = bundle_dir / "adj_factor"

    snapshot = _read_csv(snapshot_path)
    trade_calendar = _read_csv(trade_calendar_path)
    stk_limit = _read_csv(stk_limit_path) if stk_limit_path.exists() else pd.DataFrame()
    suspend_df = _read_csv(suspend_path) if suspend_path.exists() else pd.DataFrame()
    market_context = _read_csv(market_context_path)

    ensure_dir(output_dir)
    manifest_rows: list[dict] = []
    results: list[ProcessingResult] = []

    start_date = trade_calendar["trade_date"].astype(str).min()
    end_date = trade_calendar["trade_date"].astype(str).max()

    for row in snapshot.to_dict(orient="records"):
        ts_code = str(row["ts_code"]).strip()
        symbol = str(row["symbol"]).strip()
        raw_path = raw_dir / f"{symbol}.csv"
        adj_path = adj_dir / f"{symbol}.csv"
        if not raw_path.exists() or not adj_path.exists():
            message = f"missing input file raw={raw_path.exists()} adj={adj_path.exists()}"
            result = ProcessingResult(symbol=symbol, status="missing_input", rows=0, output_path="", message=message)
            results.append(result)
            manifest_rows.append(result.__dict__)
            continue

        raw_df = _read_csv(raw_path)
        adj_df = _read_csv(adj_path)
        frame = build_processed_frame(
            raw_df=raw_df,
            adj_df=adj_df,
            snapshot_row=pd.Series(row),
            trade_calendar=trade_calendar,
            limit_df=stk_limit,
            suspend_df=suspend_df,
            market_context=market_context,
            start_date=start_date,
            end_date=end_date,
        )
        validate_processed_frame(frame)
        output_path = output_dir / f"{symbol}.csv"
        frame.to_csv(output_path, index=False, encoding="utf-8-sig")
        result = ProcessingResult(symbol=symbol, status="ok", rows=len(frame), output_path=str(output_path))
        results.append(result)
        manifest_rows.append(result.__dict__)

    pd.DataFrame(manifest_rows).to_csv(output_dir / "processing_manifest.csv", index=False, encoding="utf-8-sig")
    return results
