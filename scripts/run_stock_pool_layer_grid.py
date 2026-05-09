from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.backtest import LoadedSymbol, load_processed_folder
from scripts.run_sector_rotation_grid import load_rotation_daily, merge_rotation_features
from scripts.run_sector_rotation_match_grid import SECTOR_CANDIDATE_NAME
from scripts.run_sector_parameter_grid import BASE_BUY_CONDITION, BASE_SCORE_EXPRESSION
from scripts.run_sector_rotation_match_stability import (
    AVOID_NEW_ENERGY_CASE_NAME,
    ROTATION_COVERAGE_COLUMNS,
    SECTOR_COVERAGE_COLUMNS,
    WEIGHTED_CLUSTER_CASE_NAME,
    _available_dates,
    _case_context_frame,
    _cases_for_period,
    _coverage_by_year,
    _first_date_with_complete_coverage,
    _pct,
    _run_account_case,
    _run_case,
    _summarize_case,
    _write_frames,
    build_periods,
    build_stability_cases,
)
from overnight_bt.sector_features import validate_sector_feature_set
from overnight_bt.rotation_features import THEME_CLUSTER_MAP
from sector_research.integration import DAILY_FEATURE_COLUMNS, STATIC_FEATURE_COLUMNS
from sector_research.integration import merge_sector_features_to_processed_dir


BASE_BUY_COLUMNS = ["m120", "m60", "m20", "m10", "m5", "hs300_m20"]
BASE_SCORE_COLUMNS = ["m20", "m60", "m120", "m5", "m10"]
SECTOR_FILTER_COLUMNS = ["sector_exposure_score", "sector_strongest_theme_score", "sector_strongest_theme_rank_pct"]
ROTATION_FILTER_COLUMNS = ["rotation_top_cluster"]
ROTATION_SCORE_COLUMNS = ["stock_matches_rotation_top_cluster"]


def _default_out_dir() -> Path:
    return ROOT / "research_runs" / f"{datetime.now():%Y%m%d_%H%M%S}_stock_pool_layer_grid"


def _resolve(path_text: str | Path) -> Path:
    path = Path(str(path_text)).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def _normalize_symbol(value: object) -> str:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return ""
    if len(digits) <= 6:
        return digits.zfill(6)
    return digits[-6:]


def _normalize_date(value: object) -> str:
    return str(value or "").strip().replace("-", "")


def _safe_rmtree(path: Path) -> None:
    resolved = path.resolve()
    if resolved == ROOT or ROOT not in resolved.parents:
        raise ValueError(f"拒绝清理项目目录之外的路径: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def _read_latest_stock_meta(file_path: Path) -> dict[str, Any]:
    columns = {"trade_date", "symbol", "name", "industry", "market", "total_mv_snapshot", "turnover_rate_snapshot"}
    frame = pd.read_csv(file_path, dtype={"trade_date": str, "symbol": str}, usecols=lambda col: col in columns, encoding="utf-8-sig")
    if frame.empty:
        raise ValueError(f"处理后股票文件为空: {file_path}")
    frame["trade_date"] = frame["trade_date"].astype(str).str.strip()
    frame = frame.sort_values("trade_date")
    latest = frame.iloc[-1].to_dict()
    if "total_mv_snapshot" in frame.columns:
        with_mv = frame[pd.to_numeric(frame["total_mv_snapshot"], errors="coerce").notna()]
    else:
        with_mv = pd.DataFrame()
    if with_mv.empty:
        latest["total_mv_snapshot"] = math.nan
        latest["total_mv_trade_date"] = ""
    else:
        mv_row = with_mv.iloc[-1]
        latest["total_mv_snapshot"] = float(pd.to_numeric(mv_row["total_mv_snapshot"], errors="coerce"))
        latest["total_mv_trade_date"] = str(mv_row["trade_date"])
    latest["latest_trade_date"] = str(latest.get("trade_date", ""))
    latest["symbol"] = _normalize_symbol(latest.get("symbol") or file_path.stem)
    latest["source_file"] = str(file_path)
    return latest


def _load_exposure(exposure_path: str | Path) -> pd.DataFrame:
    file_path = _resolve(exposure_path)
    if not file_path.exists():
        raise FileNotFoundError(f"个股主题暴露文件不存在: {file_path}")
    exposure = pd.read_csv(file_path, dtype=str, encoding="utf-8-sig").fillna("")
    if "stock_code" not in exposure.columns:
        raise ValueError(f"个股主题暴露文件缺少 stock_code 字段: {file_path}")
    exposure["symbol"] = exposure["stock_code"].map(_normalize_symbol)
    exposure = exposure[exposure["symbol"] != ""].copy()
    exposure = exposure.drop_duplicates("symbol", keep="first")
    for column in ["theme_count", "subtheme_count", "board_count", "exposure_score"]:
        if column in exposure.columns:
            exposure[column] = pd.to_numeric(exposure[column], errors="coerce")
    return exposure


def _layer_name(layer: str) -> str:
    names = {
        "L0": "最大市值主题股层",
        "L1": "偏大市值主题股层",
        "L2": "中等市值主题股层",
        "L3": "偏小市值主题股层",
        "L4": "最小市值主题股层",
    }
    return names.get(str(layer), f"主题股分层{layer}")


def build_layer_constituents(
    *,
    processed_dir: str | Path,
    exposure_path: str | Path,
    layer_count: int = 5,
    layer_method: str = "quantile",
    rank_bands: str = "100,200,300,500",
    min_total_mv: float = 0.0,
) -> pd.DataFrame:
    """Build L0-L4 constituents from the backtestable theme-exposed stock intersection."""

    source_dir = _resolve(processed_dir)
    if not source_dir.exists():
        raise FileNotFoundError(f"处理后股票目录不存在: {source_dir}")
    if layer_count < 1:
        raise ValueError("layer_count 必须大于 0")

    exposure = _load_exposure(exposure_path)
    exposure_by_symbol = exposure.set_index("symbol")
    rows: list[dict[str, Any]] = []
    for file_path in sorted(source_dir.glob("*.csv")):
        if file_path.name.endswith("manifest.csv"):
            continue
        symbol = _normalize_symbol(file_path.stem)
        if not symbol or symbol not in exposure_by_symbol.index:
            continue
        meta = _read_latest_stock_meta(file_path)
        total_mv = pd.to_numeric(pd.Series([meta.get("total_mv_snapshot")]), errors="coerce").iloc[0]
        if pd.isna(total_mv) or float(total_mv) < min_total_mv:
            continue
        exposure_row = exposure_by_symbol.loc[symbol].to_dict()
        rows.append(
            {
                "symbol": symbol,
                "name": meta.get("name") or exposure_row.get("stock_name", ""),
                "industry": meta.get("industry", ""),
                "market": meta.get("market", ""),
                "latest_trade_date": meta.get("latest_trade_date", ""),
                "total_mv_trade_date": meta.get("total_mv_trade_date", ""),
                "total_mv_snapshot": float(total_mv),
                "turnover_rate_snapshot": meta.get("turnover_rate_snapshot", ""),
                "theme_names": exposure_row.get("theme_names", ""),
                "subtheme_names": exposure_row.get("subtheme_names", ""),
                "board_names": exposure_row.get("board_names", ""),
                "primary_theme": exposure_row.get("primary_theme", ""),
                "primary_subtheme": exposure_row.get("primary_subtheme", ""),
                "theme_count": exposure_row.get("theme_count", ""),
                "subtheme_count": exposure_row.get("subtheme_count", ""),
                "board_count": exposure_row.get("board_count", ""),
                "exposure_score": exposure_row.get("exposure_score", ""),
                "source_file": meta.get("source_file", ""),
            }
        )

    if not rows:
        raise ValueError("处理后股票目录与个股主题暴露表没有可用交集")

    frame = pd.DataFrame(rows).sort_values(["total_mv_snapshot", "symbol"], ascending=[False, True]).reset_index(drop=True)
    frame["market_cap_rank"] = range(1, len(frame) + 1)
    if layer_method == "quantile":
        n = len(frame)
        frame["layer_index"] = [min(int(idx * layer_count / n), layer_count - 1) for idx in range(n)]
    elif layer_method == "rank_bands":
        bands = [int(item.strip()) for item in str(rank_bands).split(",") if item.strip()]
        if not bands or sorted(bands) != bands:
            raise ValueError("rank_bands 必须为升序整数列表")
        frame["layer_index"] = frame["market_cap_rank"].map(lambda rank: sum(int(rank) > band for band in bands))
    else:
        raise ValueError(f"不支持的分层方法: {layer_method}")
    frame["layer"] = frame["layer_index"].map(lambda value: f"L{int(value)}")
    frame["layer_name"] = frame["layer"].map(_layer_name)
    ordered = [
        "layer",
        "layer_name",
        "market_cap_rank",
        "symbol",
        "name",
        "industry",
        "market",
        "latest_trade_date",
        "total_mv_trade_date",
        "total_mv_snapshot",
        "turnover_rate_snapshot",
        "theme_names",
        "subtheme_names",
        "board_names",
        "primary_theme",
        "primary_subtheme",
        "theme_count",
        "subtheme_count",
        "board_count",
        "exposure_score",
        "source_file",
    ]
    return frame[ordered]


def _split_theme_names(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").split("、") if item.strip()]


def summarize_layer_constituents(constituents: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for layer, group in constituents.groupby("layer", sort=True):
        theme_counts: dict[str, int] = {}
        for value in group["theme_names"]:
            for theme in _split_theme_names(value):
                theme_counts[theme] = theme_counts.get(theme, 0) + 1
        rows.append(
            {
                "layer": layer,
                "layer_name": _layer_name(layer),
                "stock_count": int(len(group)),
                "rank_min": int(group["market_cap_rank"].min()),
                "rank_max": int(group["market_cap_rank"].max()),
                "total_mv_max": float(group["total_mv_snapshot"].max()),
                "total_mv_median": float(group["total_mv_snapshot"].median()),
                "total_mv_min": float(group["total_mv_snapshot"].min()),
                "avg_exposure_score": float(pd.to_numeric(group["exposure_score"], errors="coerce").mean()),
                "theme_hit_counts": json.dumps(theme_counts, ensure_ascii=False, sort_keys=True),
                "primary_theme_counts": json.dumps(group["primary_theme"].fillna("").astype(str).value_counts().to_dict(), ensure_ascii=False, sort_keys=True),
            }
        )
    return pd.DataFrame(rows)


def _copy_layer_base_files(*, source_dir: Path, layer_dir: Path, symbols: list[str]) -> None:
    layer_dir.mkdir(parents=True, exist_ok=True)
    for old_file in layer_dir.glob("*.csv"):
        old_file.unlink()
    for symbol in symbols:
        source_file = source_dir / f"{symbol}.csv"
        if not source_file.exists():
            raise FileNotFoundError(f"分层股票缺少处理后 CSV: {source_file}")
        shutil.copy2(source_file, layer_dir / source_file.name)


def materialize_layer_dirs(
    *,
    constituents: pd.DataFrame,
    base_processed_dir: str | Path,
    sector_processed_dir: str | Path,
    out_dir: str | Path,
) -> list[dict[str, Any]]:
    source_dir = _resolve(base_processed_dir)
    target_root = _resolve(out_dir) / "processed_layers"
    target_root.mkdir(parents=True, exist_ok=True)
    layer_dirs: list[dict[str, Any]] = []
    for layer, group in constituents.groupby("layer", sort=True):
        layer_root = target_root / layer
        base_dir = layer_root / "base"
        sector_dir = layer_root / "sector"
        symbols = group.sort_values("market_cap_rank")["symbol"].astype(str).tolist()
        _copy_layer_base_files(source_dir=source_dir, layer_dir=base_dir, symbols=symbols)
        merge_sector_features_to_processed_dir(
            processed_dir=base_dir,
            sector_processed_dir=_resolve(sector_processed_dir),
            output_dir=sector_dir,
            overwrite=True,
        )
        layer_dirs.append({"layer": layer, "base_dir": str(base_dir), "sector_dir": str(sector_dir), "stock_count": len(symbols)})
    return layer_dirs


def _load_theme_strength(sector_processed_dir: str | Path) -> pd.DataFrame:
    path = _resolve(sector_processed_dir) / "theme_strength_daily.csv"
    if not path.exists():
        raise FileNotFoundError(f"缺少主题强度日线文件: {path}")
    frame = pd.read_csv(path, dtype={"trade_date": str}, encoding="utf-8-sig")
    frame["trade_date"] = frame["trade_date"].astype(str).str.strip()
    for col in ["theme_score", "m5", "m20", "m60", "amount_ratio_20", "board_up_ratio", "positive_m20_ratio", "theme_rank", "theme_rank_pct"]:
        if col not in frame.columns:
            frame[col] = pd.NA
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


def _build_symbol_exposure_map(exposure_path: str | Path) -> dict[str, dict[str, Any]]:
    exposure = _load_exposure(exposure_path).fillna("")
    return {str(row["symbol"]).zfill(6): row for row in exposure.to_dict("records")}


def _empty_sector_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in STATIC_FEATURE_COLUMNS + DAILY_FEATURE_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    return out


def _merge_sector_frame_fast(base_frame: pd.DataFrame, exposure_row: dict[str, Any], theme_strength: pd.DataFrame) -> pd.DataFrame:
    result = base_frame.copy()
    result["sector_theme_names"] = exposure_row.get("theme_names", "")
    result["sector_subtheme_names"] = exposure_row.get("subtheme_names", "")
    result["sector_board_names"] = exposure_row.get("board_names", "")
    result["sector_theme_count"] = pd.to_numeric(exposure_row.get("theme_count", pd.NA), errors="coerce")
    result["sector_subtheme_count"] = pd.to_numeric(exposure_row.get("subtheme_count", pd.NA), errors="coerce")
    result["sector_board_count"] = pd.to_numeric(exposure_row.get("board_count", pd.NA), errors="coerce")
    result["sector_exposure_score"] = pd.to_numeric(exposure_row.get("exposure_score", pd.NA), errors="coerce")
    theme_names = _split_theme_names(exposure_row.get("theme_names", ""))
    daily = theme_strength[theme_strength["theme_name"].isin(theme_names)].copy()
    if daily.empty:
        return _empty_sector_columns(result)
    daily = daily.sort_values(["trade_date", "theme_score"], ascending=[True, False]).groupby("trade_date", as_index=False).first()
    daily = daily.rename(
        columns={
            "theme_name": "sector_strongest_theme",
            "theme_rank": "sector_strongest_theme_rank",
            "theme_rank_pct": "sector_strongest_theme_rank_pct",
            "theme_score": "sector_strongest_theme_score",
            "m5": "sector_strongest_theme_m5",
            "m20": "sector_strongest_theme_m20",
            "m60": "sector_strongest_theme_m60",
            "amount_ratio_20": "sector_strongest_theme_amount_ratio_20",
            "board_up_ratio": "sector_strongest_theme_board_up_ratio",
            "positive_m20_ratio": "sector_strongest_theme_positive_m20_ratio",
            "strongest_board": "sector_strongest_board",
            "strongest_subtheme": "sector_strongest_subtheme",
        }
    )
    keep_cols = ["trade_date"] + [col for col in DAILY_FEATURE_COLUMNS if col in daily.columns]
    result = result.merge(daily[keep_cols], on="trade_date", how="left")
    return _empty_sector_columns(result)


def build_fast_layer_frame(
    *,
    constituents: pd.DataFrame,
    layer: str,
    base_processed_dir: str | Path,
    exposure_map: dict[str, dict[str, Any]],
    theme_strength: pd.DataFrame,
    rotation_daily: pd.DataFrame,
) -> pd.DataFrame:
    source_dir = _resolve(base_processed_dir)
    frames: list[pd.DataFrame] = []
    symbols = constituents[constituents["layer"] == layer]["symbol"].astype(str).tolist()
    for symbol in symbols:
        file_path = source_dir / f"{symbol}.csv"
        if not file_path.exists():
            continue
        base = pd.read_csv(file_path, dtype={"trade_date": str, "symbol": str}, encoding="utf-8-sig")
        base["trade_date"] = base["trade_date"].astype(str).str.strip()
        base["symbol"] = base.get("symbol", symbol)
        base["symbol"] = base["symbol"].astype(str).str.zfill(6)
        exposure_row = exposure_map.get(symbol)
        if exposure_row is None:
            enriched = _empty_sector_columns(base)
        else:
            enriched = _merge_sector_frame_fast(base, exposure_row, theme_strength)
        frames.append(enriched)
    if not frames:
        return pd.DataFrame()
    frame = pd.concat(frames, ignore_index=True, sort=False)
    frame = frame.merge(rotation_daily, on="trade_date", how="left")
    frame["stock_theme_cluster"] = frame.get("sector_strongest_theme", pd.Series([""] * len(frame))).map(THEME_CLUSTER_MAP).fillna("")
    stock_theme = frame.get("sector_strongest_theme", pd.Series([""] * len(frame))).fillna("")
    frame["stock_matches_rotation_top_theme"] = (stock_theme == frame.get("rotation_top_theme", "").fillna("")).astype(float)
    frame["stock_matches_rotation_top_cluster"] = (frame["stock_theme_cluster"].fillna("") == frame.get("rotation_top_cluster", "").fillna("")).astype(float)
    return frame


def _parse_int_list(raw_text: str) -> list[int]:
    values = [int(item.strip()) for item in str(raw_text).split(",") if item.strip()]
    if not values:
        raise ValueError("窗口列表不能为空")
    return values


def _last_date_with_complete_coverage(loaded: list[LoadedSymbol], columns: tuple[str, ...], min_coverage: float) -> str:
    rows: list[pd.DataFrame] = []
    for item in loaded:
        existing = [column for column in ("trade_date", *columns) if column in item.df.columns]
        if "trade_date" in existing:
            rows.append(item.df[existing].copy())
    if not rows:
        return ""
    frame = pd.concat(rows, ignore_index=True, sort=False)
    grouped = list(frame.groupby(frame["trade_date"].astype(str), sort=True))
    for trade_date, group in reversed(grouped):
        checks = []
        for column in columns:
            if column not in group.columns:
                checks.append(0.0)
            else:
                series = group[column]
                if pd.api.types.is_numeric_dtype(series):
                    checks.append(float(pd.to_numeric(series, errors="coerce").notna().mean()))
                else:
                    checks.append(float(series.fillna("").astype(str).str.strip().ne("").mean()))
        if checks and min(checks) >= min_coverage:
            return str(trade_date)
    return ""


def _coverage_frame(layer: str, loaded: list[LoadedSymbol]) -> pd.DataFrame:
    frame = _coverage_by_year(loaded)
    if frame.empty:
        return frame
    frame.insert(0, "layer", layer)
    frame.insert(1, "layer_name", _layer_name(layer))
    return frame


def _layer_trade_frame(layer: str, case: Any, period: Any, trades: pd.DataFrame) -> pd.DataFrame:
    frame = _case_context_frame(case, period, trades)
    if frame.empty:
        return frame
    frame.insert(0, "layer", layer)
    frame.insert(1, "layer_name", _layer_name(layer))
    return frame


def _summarize_layer_case(
    *,
    layer: str,
    layer_stock_count: int,
    case: Any,
    period: Any,
    signal_result: dict[str, Any],
    account_result: dict[str, Any],
) -> dict[str, Any]:
    row = _summarize_case(case=case, period=period, signal_result=signal_result, account_result=account_result)
    row = {"layer": layer, "layer_name": _layer_name(layer), "layer_stock_count": layer_stock_count, **row}
    return row


def _account_risk_note(row: dict[str, Any]) -> str:
    notes: list[str] = []
    buy_count = int(row.get("account_buy_count") or 0)
    drawdown = float(row.get("account_max_drawdown") or 0.0)
    total_return = float(row.get("account_total_return") or 0.0)
    if buy_count < 15:
        notes.append("交易次数偏少")
    if drawdown > 0.12:
        notes.append("账户回撤偏高")
    if total_return <= 0:
        notes.append("账户收益为负")
    return "；".join(notes) if notes else "通过账户基础风险筛选"


def _account_grid_score(row: dict[str, Any]) -> float:
    account_return = float(row.get("account_total_return") or 0.0)
    account_win_rate = float(row.get("account_win_rate") or 0.0)
    account_drawdown = float(row.get("account_max_drawdown") or 0.0)
    buy_count = float(row.get("account_buy_count") or 0.0)
    activity_bonus = min(buy_count / 80.0, 1.0) * 0.06
    return round(account_return * 1.2 + account_win_rate * 0.2 + activity_bonus - account_drawdown * 0.8, 6)


def _summarize_layer_account_case(
    *,
    layer: str,
    layer_stock_count: int,
    case: Any,
    period: Any,
    account_result: dict[str, Any],
) -> dict[str, Any]:
    account_summary = account_result["summary"]
    row: dict[str, Any] = {
        "layer": layer,
        "layer_name": _layer_name(layer),
        "layer_stock_count": layer_stock_count,
        "period_label": period.label,
        "period_kind": period.kind,
        "period_start": period.start_date,
        "period_end": period.end_date,
        "period_note": period.note,
        "case": case.name,
        "family": case.family,
        "data_profile": case.data_profile,
        "processed_dir": case.processed_dir,
        "buy_condition": case.buy_condition,
        "score_expression": case.score_expression,
        "signal_count": "",
        "signal_completed_count": "",
        "signal_avg_trade_return": "",
        "signal_median_trade_return": "",
        "signal_win_rate": "",
        "signal_profit_factor": "",
        "signal_curve_return": "",
        "signal_max_drawdown": "",
        "signal_candidate_day_ratio": "",
        "signal_topn_fill_rate": "",
        "account_total_return": account_summary.get("total_return"),
        "account_annualized_return": account_summary.get("annualized_return"),
        "account_max_drawdown": account_summary.get("max_drawdown"),
        "account_buy_count": account_summary.get("buy_count"),
        "account_sell_count": account_summary.get("sell_count"),
        "account_win_rate": account_summary.get("win_rate"),
        "account_avg_trade_return": account_summary.get("avg_trade_return"),
        "account_median_trade_return": account_summary.get("median_trade_return"),
        "account_profit_factor": account_summary.get("profit_factor"),
        "account_ending_equity": account_summary.get("ending_equity"),
        "account_open_position_count": account_summary.get("open_position_count"),
    }
    row.update({f"param_{key}": value for key, value in case.params.items()})
    row["grid_score"] = _account_grid_score(row)
    row["risk_note"] = _account_risk_note(row)
    return row


def _fast_max_exit_offset(args: argparse.Namespace) -> int:
    return int(args.entry_offset + args.max_hold_days) if int(args.max_hold_days) > 0 else int(args.exit_offset)


def _load_fast_frame(loaded: list[LoadedSymbol], *, use_rotation: bool) -> pd.DataFrame:
    keep = {
        "trade_date",
        "symbol",
        "name",
        "raw_open",
        "raw_close",
        "adj_factor",
        "can_buy_open_t",
        "can_sell_t",
        *BASE_BUY_COLUMNS,
        *BASE_SCORE_COLUMNS,
        *SECTOR_FILTER_COLUMNS,
    }
    if use_rotation:
        keep.update(ROTATION_FILTER_COLUMNS)
        keep.update(ROTATION_SCORE_COLUMNS)
    frames: list[pd.DataFrame] = []
    for item in loaded:
        cols = [col for col in item.df.columns if col in keep]
        frame = item.df[cols].copy()
        if "symbol" not in frame.columns:
            frame["symbol"] = item.symbol
        if "name" not in frame.columns:
            frame["name"] = item.name
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True, sort=False)
    out["trade_date"] = out["trade_date"].astype(str).str.strip()
    out["symbol"] = out["symbol"].astype(str).str.zfill(6)
    out["name"] = out["name"].astype(str)
    numeric_cols = [
        "raw_open",
        "raw_close",
        "adj_factor",
        *BASE_BUY_COLUMNS,
        *BASE_SCORE_COLUMNS,
        *SECTOR_FILTER_COLUMNS,
        *ROTATION_SCORE_COLUMNS,
    ]
    for col in numeric_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    for col in ["can_buy_open_t", "can_sell_t"]:
        if col in out.columns:
            out[col] = out[col].astype(str).str.lower().isin(["true", "1", "yes"])
        else:
            out[col] = False
    return out.sort_values(["trade_date", "symbol"]).reset_index(drop=True)


def _fast_candidate_frame(frame: pd.DataFrame, case: Any) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    required = [col for col in [*BASE_BUY_COLUMNS, *BASE_SCORE_COLUMNS] if col in frame.columns]
    work = frame.dropna(subset=required).copy()
    if work.empty:
        return work
    mask = (
        (work["m120"] > 0.02)
        & (work["m60"] > 0.01)
        & (work["m20"] > 0.08)
        & (work["m10"] < 0.16)
        & (work["m5"] < 0.1)
        & (work["hs300_m20"] > 0.02)
    )
    if case.family != "baseline":
        for col in SECTOR_FILTER_COLUMNS:
            if col not in work.columns:
                work[col] = math.nan
        mask = mask & (work["sector_exposure_score"] > 0) & (work["sector_strongest_theme_score"] >= 0.4) & (work["sector_strongest_theme_rank_pct"] <= 0.7)
    if case.name == AVOID_NEW_ENERGY_CASE_NAME:
        mask = mask & (work.get("rotation_top_cluster", "").fillna("").astype(str) != "新能源")
    work = work[mask].copy()
    if work.empty:
        return work
    score = (
        work["m20"] * 140
        + (work["m20"] - work["m60"] / 3) * 90
        + (work["m20"] - work["m120"] / 6) * 40
        - (work["m5"] - 0.03).abs() * 55
        - (work["m10"] - 0.08).abs() * 30
    )
    if case.name == WEIGHTED_CLUSTER_CASE_NAME:
        score = score + pd.to_numeric(work.get("stock_matches_rotation_top_cluster", 0.0), errors="coerce").fillna(0.0) * 5.0
    work["score"] = score
    return work.sort_values(["trade_date", "score", "symbol"], ascending=[True, False, True]).reset_index(drop=True)


def _row_lookup(frame: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in frame.to_dict("records"):
        rows[(str(row["symbol"]).zfill(6), str(row["trade_date"]))] = row
    return rows


def _symbol_dates(frame: pd.DataFrame) -> dict[str, list[str]]:
    return {symbol: group["trade_date"].astype(str).tolist() for symbol, group in frame.groupby("symbol", sort=False)}


def _future_date(dates: list[str], trade_date: str, offset: int) -> str:
    try:
        idx = dates.index(trade_date)
    except ValueError:
        return ""
    future_idx = idx + int(offset)
    if future_idx < 0 or future_idx >= len(dates):
        return ""
    return str(dates[future_idx])


def _shares_for_budget(*, cash: float, price: float, args: argparse.Namespace) -> tuple[int, float, float]:
    exec_price = float(price) * (1.0 + float(args.slippage_bps) / 10000.0) if args.realistic_execution else float(price)
    per_lot_cost = exec_price * int(args.lot_size)
    est_fee = per_lot_cost * float(args.buy_fee_rate)
    if args.realistic_execution and per_lot_cost > 0:
        est_fee = max(est_fee, float(args.min_commission))
    total_one_lot = per_lot_cost + est_fee
    budget = min(float(args.per_trade_budget), cash)
    lots = int(budget // total_one_lot) if total_one_lot > 0 else 0
    shares = lots * int(args.lot_size)
    gross = exec_price * shares
    fees = gross * float(args.buy_fee_rate)
    if args.realistic_execution and gross > 0:
        fees = max(fees, float(args.min_commission))
    return shares, exec_price, fees


def _fast_portfolio_backtest(
    *,
    frame: pd.DataFrame,
    case: Any,
    period: Any,
    args: argparse.Namespace,
    layer: str,
) -> dict[str, Any]:
    data = frame[(frame["trade_date"] >= period.start_date) & (frame["trade_date"] <= period.end_date)].copy()
    if data.empty:
        raise ValueError(f"{layer} {period.label} 没有可用数据")
    candidates = _fast_candidate_frame(data, case)
    all_dates = sorted(data["trade_date"].astype(str).unique().tolist())
    cutoff_date = all_dates[-1]
    row_by_key = _row_lookup(data)
    dates_by_symbol = _symbol_dates(data)
    candidate_groups = {date: group for date, group in candidates.groupby("trade_date", sort=False)}

    cash = float(args.initial_cash)
    holdings: dict[str, dict[str, Any]] = {}
    pending_orders: dict[str, list[dict[str, Any]]] = {}
    trades: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    equity_curve: list[float] = [float(args.initial_cash)]
    realized_returns: list[float] = []

    for trade_date in all_dates:
        for symbol, pos in list(holdings.items()):
            if trade_date < str(pos["planned_exit_date"]):
                continue
            row = row_by_key.get((symbol, trade_date))
            open_px = None if row is None else row.get("raw_open")
            can_sell = bool(row.get("can_sell_t", False)) if row is not None else False
            if pd.isna(open_px) or (args.realistic_execution and not can_sell):
                continue
            exec_price = float(open_px) * (1.0 - float(args.slippage_bps) / 10000.0) if args.realistic_execution else float(open_px)
            gross = exec_price * float(pos["shares"])
            commission = gross * float(args.sell_fee_rate)
            if args.realistic_execution and gross > 0:
                commission = max(commission, float(args.min_commission))
            fees = commission + gross * float(args.stamp_tax_sell)
            net = gross - fees
            cash += net
            trade_return = net / float(pos["buy_net_amount"]) - 1.0 if pos["buy_net_amount"] else 0.0
            realized_returns.append(trade_return)
            trades.append(
                {
                    "trade_date": trade_date,
                    "signal_date": pos["signal_date"],
                    "planned_entry_date": pos["planned_entry_date"],
                    "planned_exit_date": pos["planned_exit_date"],
                    "symbol": symbol,
                    "name": pos["name"],
                    "action": "SELL",
                    "price": round(exec_price, 4),
                    "shares": int(pos["shares"]),
                    "gross_amount": round(gross, 2),
                    "fees": round(fees, 2),
                    "net_amount": round(net, 2),
                    "cash_after": round(cash, 2),
                    "holding_days": max(0, all_dates.index(trade_date) - all_dates.index(pos["buy_date"])),
                    "trade_return": round(trade_return, 6),
                    "price_pnl": round(exec_price - float(pos["buy_price"]), 4),
                    "exit_reason": "fast_fixed_or_max_exit",
                }
            )
            del holdings[symbol]

        for order in pending_orders.pop(trade_date, []):
            row = row_by_key.get((order["symbol"], trade_date))
            open_px = None if row is None else row.get("raw_open")
            can_buy = bool(row.get("can_buy_open_t", False)) if row is not None else False
            if pd.isna(open_px) or (args.realistic_execution and not can_buy):
                continue
            shares, exec_price, fees = _shares_for_budget(cash=cash, price=float(open_px), args=args)
            if shares <= 0:
                continue
            gross = exec_price * shares
            net = gross + fees
            if net > cash:
                continue
            cash -= net
            holdings[order["symbol"]] = {
                **order,
                "buy_date": trade_date,
                "buy_price": exec_price,
                "buy_net_amount": net,
                "shares": shares,
            }
            trades.append(
                {
                    "trade_date": trade_date,
                    "signal_date": order["signal_date"],
                    "planned_entry_date": order["planned_entry_date"],
                    "planned_exit_date": order["planned_exit_date"],
                    "symbol": order["symbol"],
                    "name": order["name"],
                    "action": "BUY",
                    "price": round(exec_price, 4),
                    "shares": int(shares),
                    "gross_amount": round(gross, 2),
                    "fees": round(fees, 2),
                    "net_amount": round(net, 2),
                    "cash_after": round(cash, 2),
                    "rank": order["rank"],
                    "score": round(float(order["score"]), 6),
                    "reason": "fast selected on signal day and executed at next open",
                }
            )

        if trade_date in candidate_groups:
            pending_symbols = {symbol for symbol in holdings}
            for orders in pending_orders.values():
                pending_symbols.update(order["symbol"] for order in orders)
            group = candidate_groups[trade_date]
            selected_rows = []
            for row in group.to_dict("records"):
                symbol = str(row["symbol"]).zfill(6)
                if symbol in pending_symbols:
                    continue
                dates = dates_by_symbol.get(symbol, [])
                entry_date = _future_date(dates, trade_date, int(args.entry_offset))
                exit_date = _future_date(dates, trade_date, _fast_max_exit_offset(args))
                if not entry_date or not exit_date or entry_date >= cutoff_date:
                    continue
                selected_rows.append((symbol, row, entry_date, exit_date))
                if len(selected_rows) >= int(args.top_n):
                    break
            for rank, (symbol, row, entry_date, exit_date) in enumerate(selected_rows, start=1):
                pending_orders.setdefault(entry_date, []).append(
                    {
                        "symbol": symbol,
                        "name": str(row.get("name", "")),
                        "signal_date": trade_date,
                        "planned_entry_date": entry_date,
                        "planned_exit_date": exit_date,
                        "score": float(row.get("score", 0.0)),
                        "rank": rank,
                    }
                )

        market_value = 0.0
        for symbol, pos in holdings.items():
            row = row_by_key.get((symbol, trade_date))
            close_px = None if row is None else row.get("raw_close")
            market_value += (float(close_px) if not pd.isna(close_px) else float(pos["buy_price"])) * float(pos["shares"])
        equity = cash + market_value
        equity_curve.append(equity)
        peak = max(equity_curve)
        daily_rows.append(
            {
                "trade_date": trade_date,
                "cash": round(cash, 2),
                "market_value": round(market_value, 2),
                "equity": round(equity, 2),
                "position_count": len(holdings),
                "drawdown": round(equity / peak - 1.0, 6) if peak > 0 else 0.0,
            }
        )

    ending_equity = daily_rows[-1]["equity"] if daily_rows else float(args.initial_cash)
    max_drawdown = 0.0
    peak = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = min(max_drawdown, value / peak - 1.0)
    wins = sum(1 for value in realized_returns if value > 0)
    summary = {
        "total_return": round(ending_equity / float(args.initial_cash) - 1.0, 6),
        "annualized_return": 0.0,
        "max_drawdown": round(abs(max_drawdown), 6),
        "buy_count": sum(1 for row in trades if row["action"] == "BUY"),
        "sell_count": sum(1 for row in trades if row["action"] == "SELL"),
        "win_rate": round(wins / len(realized_returns), 6) if realized_returns else 0.0,
        "avg_trade_return": round(sum(realized_returns) / len(realized_returns), 6) if realized_returns else 0.0,
        "median_trade_return": round(float(pd.Series(realized_returns).median()), 6) if realized_returns else 0.0,
        "profit_factor": 0.0,
        "ending_equity": round(ending_equity, 2),
        "open_position_count": len(holdings),
    }
    return {"summary": summary, "trade_rows": trades, "daily_rows": daily_rows}


def _aggregate_by_layer_case(summary_df: pd.DataFrame) -> pd.DataFrame:
    annual = summary_df[summary_df["period_kind"] == "year"].copy() if not summary_df.empty else pd.DataFrame()
    if annual.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for (layer, case), group in annual.groupby(["layer", "case"], sort=True):
        returns = pd.to_numeric(group["account_total_return"], errors="coerce").fillna(0.0)
        drawdowns = pd.to_numeric(group["account_max_drawdown"], errors="coerce").fillna(0.0)
        buys = pd.to_numeric(group["account_buy_count"], errors="coerce").fillna(0.0)
        rows.append(
            {
                "layer": layer,
                "layer_name": _layer_name(layer),
                "case": case,
                "year_count": int(len(group)),
                "positive_year_count": int((returns > 0).sum()),
                "positive_year_ratio": round(float((returns > 0).mean()), 6) if len(group) else 0.0,
                "avg_annual_return": round(float(returns.mean()), 6) if len(group) else 0.0,
                "median_annual_return": round(float(returns.median()), 6) if len(group) else 0.0,
                "min_annual_return": round(float(returns.min()), 6) if len(group) else 0.0,
                "max_annual_return": round(float(returns.max()), 6) if len(group) else 0.0,
                "avg_drawdown": round(float(drawdowns.mean()), 6) if len(group) else 0.0,
                "max_drawdown": round(float(drawdowns.max()), 6) if len(group) else 0.0,
                "avg_buy_count": round(float(buys.mean()), 2) if len(group) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _num(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(number):
        return "-"
    return f"{number:.{digits}f}"


def _render_report(
    *,
    args: argparse.Namespace,
    out_dir: Path,
    constituents: pd.DataFrame,
    layer_summary: pd.DataFrame,
    summary_df: pd.DataFrame,
    aggregate_df: pd.DataFrame,
    coverage_df: pd.DataFrame,
) -> str:
    lines = [
        "# L0-L4 股票池分层实验报告",
        "",
        f"- 运行时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        f"- 用户请求区间：{args.start_date} 至 {args.end_date or '各层最新可用交易日'}",
        f"- 基础处理后目录：`{args.base_processed_dir}`",
        f"- 个股主题暴露：`{args.exposure_path}`",
        f"- 当前纳入股票数：{len(constituents)}。只纳入同时存在主题暴露和处理后前复权行情 CSV 的股票。",
        f"- 分层方法：`{args.layer_method}`；`quantile` 表示按最新 `total_mv_snapshot` 等频分层，L0 最大、L4 最小。",
        "",
        "## 1. 分层股票池",
        "",
        "| 分层 | 说明 | 股票数 | 排名范围 | 总市值最大 | 总市值中位 | 总市值最小 | 主题覆盖摘要 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, row in layer_summary.iterrows():
        theme_counts = json.loads(str(row.get("theme_hit_counts") or "{}"))
        top_themes = "、".join(f"{key}:{value}" for key, value in sorted(theme_counts.items(), key=lambda item: item[1], reverse=True)[:5])
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("layer", "")),
                    str(row.get("layer_name", "")),
                    str(int(row.get("stock_count") or 0)),
                    f"{int(row.get('rank_min') or 0)}-{int(row.get('rank_max') or 0)}",
                    _num(row.get("total_mv_max"), 0),
                    _num(row.get("total_mv_median"), 0),
                    _num(row.get("total_mv_min"), 0),
                    top_themes,
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 2. 年度稳定性",
            "",
            "| 分层 | 策略 | 年份数 | 正收益年份 | 正收益占比 | 年均收益 | 年收益中位数 | 最差年份 | 最大回撤 | 年均买入 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    display_aggregate = aggregate_df.sort_values(["layer", "avg_annual_return"], ascending=[True, False]) if not aggregate_df.empty else aggregate_df
    for _, row in display_aggregate.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("layer", "")),
                    str(row.get("case", "")),
                    str(int(row.get("year_count") or 0)),
                    str(int(row.get("positive_year_count") or 0)),
                    _pct(row.get("positive_year_ratio")),
                    _pct(row.get("avg_annual_return")),
                    _pct(row.get("median_annual_return")),
                    _pct(row.get("min_annual_return")),
                    _pct(row.get("max_drawdown")),
                    _num(row.get("avg_buy_count"), 1),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 3. 可比全区间",
            "",
            "| 分层 | 策略 | 收益 | 年化 | 回撤 | 买入 | 胜率 | 信号中位 | 风险提示 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    full = summary_df[summary_df["period_label"] == "可比全区间"].sort_values(["layer", "account_total_return"], ascending=[True, False]) if not summary_df.empty else pd.DataFrame()
    for _, row in full.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("layer", "")),
                    str(row.get("case", "")),
                    _pct(row.get("account_total_return")),
                    _pct(row.get("account_annualized_return")),
                    _pct(row.get("account_max_drawdown")),
                    str(int(row.get("account_buy_count") or 0)),
                    _pct(row.get("account_win_rate")),
                    _pct(row.get("signal_median_trade_return")),
                    str(row.get("risk_note") or ""),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 4. 数据覆盖",
            "",
            "| 分层 | 年份 | 行数 | 板块强度覆盖 | 轮动主线覆盖 | 轮动状态覆盖 |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in coverage_df.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("layer", "")),
                    str(row.get("year", "")),
                    str(int(row.get("rows") or 0)),
                    _pct(row.get("sector_strongest_theme_score_coverage")),
                    _pct(row.get("rotation_top_cluster_coverage")),
                    _pct(row.get("rotation_state_coverage")),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 5. 输出文件",
            "",
            f"- 分层成分：`{(out_dir / 'stock_pool_layer_constituents.csv').as_posix()}`",
            f"- 分层摘要：`{(out_dir / 'stock_pool_layer_summary.csv').as_posix()}`",
            f"- 策略汇总：`{(out_dir / 'stock_pool_layer_grid_summary.csv').as_posix()}`",
            f"- 年度稳定性：`{(out_dir / 'stock_pool_layer_grid_by_layer_case.csv').as_posix()}`",
            f"- 数据覆盖：`{(out_dir / 'stock_pool_layer_coverage.csv').as_posix()}`",
            f"- 买卖流水：`{(out_dir / 'stock_pool_layer_grid_trade_records.csv').as_posix()}`",
            f"- 参数配置：`{(out_dir / 'stock_pool_layer_grid_config.json').as_posix()}`",
        ]
    )
    return "\n".join(lines) + "\n"


def run_stock_pool_layer_grid(args: argparse.Namespace) -> Path:
    out_dir = _resolve(args.out_dir) if args.out_dir else _default_out_dir()
    if out_dir.exists() and args.overwrite and not args.resume:
        _safe_rmtree(out_dir)
    if out_dir.exists() and not args.resume and any(out_dir.iterdir()):
        raise FileExistsError(f"输出目录已存在且非空，如需重建请加 --overwrite 或更换 --out-dir: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    constituents = build_layer_constituents(
        processed_dir=args.base_processed_dir,
        exposure_path=args.exposure_path,
        layer_count=args.layer_count,
        layer_method=args.layer_method,
        rank_bands=args.rank_bands,
        min_total_mv=args.min_total_mv,
    )
    layer_summary = summarize_layer_constituents(constituents)
    constituents.to_csv(out_dir / "stock_pool_layer_constituents.csv", index=False, encoding="utf-8-sig")
    layer_summary.to_csv(out_dir / "stock_pool_layer_summary.csv", index=False, encoding="utf-8-sig")

    if args.fast_account:
        layer_dirs = [
            {"layer": str(row["layer"]), "base_dir": "", "sector_dir": "", "stock_count": int(row["stock_count"])}
            for _, row in layer_summary.sort_values("layer").iterrows()
        ]
    else:
        layer_dirs = materialize_layer_dirs(
            constituents=constituents,
            base_processed_dir=args.base_processed_dir,
            sector_processed_dir=args.sector_processed_dir,
            out_dir=out_dir,
        )

    summary_path = out_dir / "stock_pool_layer_grid_summary.csv"
    aggregate_path = out_dir / "stock_pool_layer_grid_by_layer_case.csv"
    coverage_path = out_dir / "stock_pool_layer_coverage.csv"
    trades_path = out_dir / "stock_pool_layer_grid_trade_records.csv"
    config_path = out_dir / "stock_pool_layer_grid_config.json"
    report_path = out_dir / "stock_pool_layer_grid_report.md"

    config_path.write_text(
        json.dumps(
            {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "args": vars(args),
                "layer_dirs": layer_dirs,
                "representative_strategies": ["基准动量", SECTOR_CANDIDATE_NAME, WEIGHTED_CLUSTER_CASE_NAME, AVOID_NEW_ENERGY_CASE_NAME],
                "coverage_note": "当前只纳入 stock_theme_exposure.csv 与 base_processed_dir 的可回测交集。",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    completed_keys: set[tuple[str, str, str]] = set()
    summary_rows: list[dict[str, Any]] = []
    trade_frames: list[pd.DataFrame] = []
    if args.resume and summary_path.exists() and summary_path.stat().st_size > 0:
        existing_summary = pd.read_csv(summary_path, encoding="utf-8-sig")
        if not existing_summary.empty and {"layer", "period_label", "case"}.issubset(existing_summary.columns):
            summary_rows = existing_summary.to_dict("records")
            completed_keys = set(zip(existing_summary["layer"].astype(str), existing_summary["period_label"].astype(str), existing_summary["case"].astype(str)))
            print(f"检测到已完成 {len(completed_keys)} 个分层-区间-策略组合，将从缺口继续", flush=True)
    if args.resume and not args.skip_trade_records and trades_path.exists() and trades_path.stat().st_size > 0:
        existing_trades = pd.read_csv(trades_path, encoding="utf-8-sig")
        if not existing_trades.empty:
            trade_frames.append(existing_trades)

    rotation_daily = load_rotation_daily(_resolve(args.rotation_daily_path))
    coverage_frames: list[pd.DataFrame] = []
    total_runs = 0
    exposure_map = _build_symbol_exposure_map(args.exposure_path) if args.fast_account else {}
    theme_strength = _load_theme_strength(args.sector_processed_dir) if args.fast_account else pd.DataFrame()
    for item in layer_dirs:
        if args.fast_account:
            count_frame = build_fast_layer_frame(
                constituents=constituents,
                layer=str(item["layer"]),
                base_processed_dir=args.base_processed_dir,
                exposure_map=exposure_map,
                theme_strength=theme_strength,
                rotation_daily=rotation_daily,
            )
            baseline_dates = sorted(count_frame["trade_date"].astype(str).unique().tolist())
            sector_dates = baseline_dates
            count_loaded = [LoadedSymbol(symbol="__layer__", name=str(item["layer"]), df=count_frame, idx_by_date={})]
            first_sector_date = _first_date_with_complete_coverage(count_loaded, SECTOR_COVERAGE_COLUMNS, args.min_coverage)
            first_rotation_date = _first_date_with_complete_coverage(count_loaded, ROTATION_COVERAGE_COLUMNS, args.min_coverage)
            last_sector_date = _last_date_with_complete_coverage(count_loaded, SECTOR_COVERAGE_COLUMNS, args.min_coverage)
            last_rotation_date = _last_date_with_complete_coverage(count_loaded, ROTATION_COVERAGE_COLUMNS, args.min_coverage)
            coverage_frames.append(_coverage_frame(str(item["layer"]), count_loaded))
        else:
            base_count_loaded, _ = load_processed_folder(item["base_dir"])
            count_loaded, count_diagnostics = load_processed_folder(item["sector_dir"])
            count_diagnostics.update(validate_sector_feature_set(loaded_items=count_loaded, processed_dir=count_diagnostics["processed_dir"]))
            rotation_count_loaded = merge_rotation_features(count_loaded, rotation_daily)
            baseline_dates = _available_dates(base_count_loaded)
            sector_dates = _available_dates(rotation_count_loaded)
            first_sector_date = _first_date_with_complete_coverage(rotation_count_loaded, SECTOR_COVERAGE_COLUMNS, args.min_coverage)
            first_rotation_date = _first_date_with_complete_coverage(rotation_count_loaded, ROTATION_COVERAGE_COLUMNS, args.min_coverage)
            last_sector_date = _last_date_with_complete_coverage(rotation_count_loaded, SECTOR_COVERAGE_COLUMNS, args.min_coverage)
            last_rotation_date = _last_date_with_complete_coverage(rotation_count_loaded, ROTATION_COVERAGE_COLUMNS, args.min_coverage)
            coverage_frames.append(_coverage_frame(str(item["layer"]), rotation_count_loaded))
        effective_end = _normalize_date(args.end_date) or (max(sector_dates) if sector_dates else "")
        sector_start = max(date for date in [_normalize_date(args.start_date), first_sector_date, first_rotation_date] if date)
        sector_end_candidates = [effective_end, max(sector_dates) if sector_dates else effective_end]
        sector_end_candidates.extend(date for date in [last_sector_date, last_rotation_date] if date)
        sector_end = min(sector_end_candidates)
        periods = build_periods(
            start_date=args.start_date,
            end_date=effective_end,
            sector_start_date=sector_start,
            sector_end_date=sector_end,
            baseline_available_dates=baseline_dates,
            sector_available_dates=sector_dates,
            rolling_months=_parse_int_list(args.rolling_months),
        )
        cases = build_stability_cases(base_processed_dir=item["base_dir"], sector_processed_dir=item["sector_dir"])
        total_runs += sum(len(_cases_for_period(cases, period)) for period in periods)
        item["periods"] = periods
        item["cases"] = cases
        if args.fast_account:
            del count_frame, count_loaded
        else:
            del base_count_loaded, count_loaded, count_diagnostics, rotation_count_loaded

    _write_frames(coverage_path, coverage_frames)

    current = 0
    new_run_count = 0
    should_stop = False
    for item in layer_dirs:
        layer = str(item["layer"])
        stock_count = int(item["stock_count"])
        if args.fast_account:
            rotation_fast_frame = build_fast_layer_frame(
                constituents=constituents,
                layer=layer,
                base_processed_dir=args.base_processed_dir,
                exposure_map=exposure_map,
                theme_strength=theme_strength,
                rotation_daily=rotation_daily,
            )
            base_fast_frame = rotation_fast_frame.copy()
            base_loaded = []
            rotation_loaded = []
            base_diagnostics = {}
            rotation_diagnostics = {}
        else:
            base_loaded, base_diagnostics = load_processed_folder(item["base_dir"])
            base_diagnostics["data_profile"] = "base"
            sector_loaded, sector_diagnostics = load_processed_folder(item["sector_dir"])
            sector_diagnostics.update(validate_sector_feature_set(loaded_items=sector_loaded, processed_dir=sector_diagnostics["processed_dir"]))
            rotation_loaded = merge_rotation_features(sector_loaded, rotation_daily)
            rotation_diagnostics = dict(sector_diagnostics)
            rotation_diagnostics["rotation_daily_path"] = str(_resolve(args.rotation_daily_path))
            rotation_diagnostics["rotation_match_feature_enabled"] = True
            base_fast_frame = _load_fast_frame(base_loaded, use_rotation=False)
            rotation_fast_frame = _load_fast_frame(rotation_loaded, use_rotation=True)
        periods = item.get("periods", [])
        cases = item.get("cases", build_stability_cases(base_processed_dir=item["base_dir"], sector_processed_dir=item["sector_dir"]))
        for period in periods:
            for case in _cases_for_period(cases, period):
                current += 1
                key = (layer, period.label, case.name)
                if key in completed_keys:
                    print(f"[{current}/{total_runs}] 跳过已完成 {layer} {period.label} {case.name}", flush=True)
                    continue
                if args.max_runs > 0 and new_run_count >= args.max_runs:
                    should_stop = True
                    break
                print(f"[{current}/{total_runs}] 运行 {layer} {period.label} {case.name}", flush=True)
                if case.family == "baseline":
                    loaded, diagnostics = base_loaded, base_diagnostics
                else:
                    loaded, diagnostics = rotation_loaded, rotation_diagnostics
                if args.fast_account:
                    fast_frame = base_fast_frame if case.family == "baseline" else rotation_fast_frame
                    account_result = _fast_portfolio_backtest(frame=fast_frame, case=case, period=period, args=args, layer=layer)
                    summary_rows.append(
                        _summarize_layer_account_case(
                            layer=layer,
                            layer_stock_count=stock_count,
                            case=case,
                            period=period,
                            account_result=account_result,
                        )
                    )
                elif args.account_only:
                    account_result = _run_account_case(case=case, period=period, args=args, loaded=loaded, diagnostics=diagnostics)
                    summary_rows.append(
                        _summarize_layer_account_case(
                            layer=layer,
                            layer_stock_count=stock_count,
                            case=case,
                            period=period,
                            account_result=account_result,
                        )
                    )
                else:
                    signal_result, account_result = _run_case(case=case, period=period, args=args, loaded=loaded, diagnostics=diagnostics)
                    summary_rows.append(
                        _summarize_layer_case(
                            layer=layer,
                            layer_stock_count=stock_count,
                            case=case,
                            period=period,
                            signal_result=signal_result,
                            account_result=account_result,
                        )
                    )
                completed_keys.add(key)
                new_run_count += 1
                if not args.skip_trade_records:
                    trade_frame = _layer_trade_frame(layer, case, period, pd.DataFrame(account_result.get("trade_rows", [])))
                    if not trade_frame.empty:
                        trade_frames.append(trade_frame)
                        _write_frames(trades_path, trade_frames)
                summary_df = pd.DataFrame(summary_rows)
                summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
                _aggregate_by_layer_case(summary_df).to_csv(aggregate_path, index=False, encoding="utf-8-sig")
            if should_stop:
                break
        if should_stop:
            break
        if args.fast_account:
            del base_loaded, base_diagnostics, rotation_loaded, rotation_diagnostics, base_fast_frame, rotation_fast_frame
        else:
            del base_loaded, base_diagnostics, sector_loaded, sector_diagnostics, rotation_loaded, rotation_diagnostics, base_fast_frame, rotation_fast_frame

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    aggregate_df = _aggregate_by_layer_case(summary_df)
    aggregate_df.to_csv(aggregate_path, index=False, encoding="utf-8-sig")
    if not args.skip_trade_records:
        _write_frames(trades_path, trade_frames)
    coverage_df = pd.read_csv(coverage_path, encoding="utf-8-sig") if coverage_path.exists() and coverage_path.stat().st_size > 0 else pd.DataFrame()
    report_path.write_text(
        _render_report(
            args=args,
            out_dir=out_dir,
            constituents=constituents,
            layer_summary=layer_summary,
            summary_df=summary_df,
            aggregate_df=aggregate_df,
            coverage_df=coverage_df,
        ),
        encoding="utf-8",
    )
    print(f"L0-L4 股票池分层实验完成：{out_dir.as_posix()}")
    return out_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按市值分层验证主题股票池 L0-L4 与板块轮动代表策略的配合效果")
    parser.add_argument("--base-processed-dir", default="data_bundle/processed_qfq", help="基础处理后股票 CSV 目录，默认使用当前最宽的处理后行情覆盖")
    parser.add_argument("--exposure-path", default="sector_research/data/processed/stock_theme_exposure.csv")
    parser.add_argument("--sector-processed-dir", default="sector_research/data/processed")
    parser.add_argument("--rotation-daily-path", default="research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv")
    parser.add_argument("--start-date", default="20210101")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--layer-method", choices=["quantile", "rank_bands"], default="quantile")
    parser.add_argument("--layer-count", type=int, default=5)
    parser.add_argument("--rank-bands", default="100,200,300,500")
    parser.add_argument("--min-total-mv", type=float, default=0.0)
    parser.add_argument("--rolling-months", default="6,12")
    parser.add_argument("--min-coverage", type=float, default=0.95)
    parser.add_argument("--sell-condition", default="m20<0.08,hs300_m20<0.02")
    parser.add_argument("--top-n", type=int, default=2)
    parser.add_argument("--initial-cash", type=float, default=100000.0)
    parser.add_argument("--per-trade-budget", type=float, default=10000.0)
    parser.add_argument("--lot-size", type=int, default=100)
    parser.add_argument("--buy-fee-rate", type=float, default=0.00003)
    parser.add_argument("--sell-fee-rate", type=float, default=0.00003)
    parser.add_argument("--stamp-tax-sell", type=float, default=0.0)
    parser.add_argument("--entry-offset", type=int, default=1)
    parser.add_argument("--exit-offset", type=int, default=5)
    parser.add_argument("--min-hold-days", type=int, default=3)
    parser.add_argument("--max-hold-days", type=int, default=15)
    parser.add_argument("--settlement-mode", choices=["cutoff", "complete"], default="cutoff")
    parser.add_argument("--slippage-bps", type=float, default=3.0)
    parser.add_argument("--min-commission", type=float, default=0.0)
    parser.add_argument("--realistic-execution", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--fast-account", action="store_true", help="使用固定代表策略快速账户路径；用于 L0-L4 分层批量实验")
    parser.add_argument("--account-only", action="store_true", help="只跑组合账户回测，不跑信号质量统计；适合先做 L0-L4 股票池层级筛选")
    parser.add_argument("--skip-trade-records", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-runs", type=int, default=0, help="单次最多新增运行多少个组合，0 表示不限制")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    run_stock_pool_layer_grid(parse_args(argv))


if __name__ == "__main__":
    main()
