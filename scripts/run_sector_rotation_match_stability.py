from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.backtest import LoadedSymbol, load_processed_folder, run_portfolio_backtest_loaded
from overnight_bt.models import BacktestRequest, SignalQualityRequest
from overnight_bt.sector_features import validate_sector_feature_set
from overnight_bt.signal_quality import run_signal_quality_loaded
from scripts.run_sector_parameter_grid import BASE_BUY_CONDITION, BASE_SCORE_EXPRESSION, SELL_CONDITION
from scripts.run_sector_rotation_grid import load_rotation_daily, merge_rotation_features
from scripts.run_sector_rotation_match_grid import (
    SECTOR_CANDIDATE_FILTER,
    SECTOR_CANDIDATE_NAME,
    RotationMatchCase,
    _rotation_match_score,
    _sector_candidate_condition,
)


WEIGHTED_CLUSTER_CASE_NAME = "主线簇匹配加权_w5"
AVOID_NEW_ENERGY_CASE_NAME = "候选_避开新能源主线"
SECTOR_COVERAGE_COLUMNS = (
    "sector_exposure_score",
    "sector_strongest_theme_score",
    "sector_strongest_theme_rank_pct",
)
ROTATION_COVERAGE_COLUMNS = (
    "rotation_top_theme",
    "rotation_top_cluster",
    "rotation_state",
)


@dataclass(frozen=True)
class PeriodSpec:
    label: str
    start_date: str
    end_date: str
    kind: str
    note: str = ""


def _default_out_dir() -> Path:
    return Path("research_runs") / f"{datetime.now():%Y%m%d_%H%M%S}_sector_rotation_match_stability"


def build_stability_cases(*, base_processed_dir: str, sector_processed_dir: str) -> list[RotationMatchCase]:
    return [
        RotationMatchCase(
            name="基准动量",
            family="baseline",
            processed_dir=base_processed_dir,
            data_profile="auto",
            buy_condition=BASE_BUY_CONDITION,
            score_expression=BASE_SCORE_EXPRESSION,
            params={"rotation_match_usage": "none", "cluster_weight": 0.0, "theme_weight": 0.0, "new_start_penalty": 0.0},
        ),
        RotationMatchCase(
            name=SECTOR_CANDIDATE_NAME,
            family="sector_candidate",
            processed_dir=sector_processed_dir,
            data_profile="sector",
            buy_condition=_sector_candidate_condition(),
            score_expression=BASE_SCORE_EXPRESSION,
            params={"rotation_match_usage": "none", "cluster_weight": 0.0, "theme_weight": 0.0, "new_start_penalty": 0.0},
        ),
        RotationMatchCase(
            name=WEIGHTED_CLUSTER_CASE_NAME,
            family="rotation_match_score",
            processed_dir=sector_processed_dir,
            data_profile="sector",
            buy_condition=_sector_candidate_condition(),
            score_expression=_rotation_match_score(cluster_weight=5.0, theme_weight=0.0, new_start_penalty=0.0),
            params={"rotation_match_usage": "cluster_score", "cluster_weight": 5.0, "theme_weight": 0.0, "new_start_penalty": 0.0},
        ),
        RotationMatchCase(
            name=AVOID_NEW_ENERGY_CASE_NAME,
            family="rotation_cluster_guard",
            processed_dir=sector_processed_dir,
            data_profile="sector",
            buy_condition=_sector_candidate_condition("rotation_top_cluster!=新能源"),
            score_expression=BASE_SCORE_EXPRESSION,
            params={"rotation_match_usage": "avoid_new_energy", "cluster_weight": 0.0, "theme_weight": 0.0, "new_start_penalty": 0.0},
        ),
    ]


def _parse_int_list(raw_text: str) -> list[int]:
    values = [int(token.strip()) for token in str(raw_text).split(",") if token.strip()]
    if not values:
        raise ValueError("窗口列表不能为空")
    return values


def _normalize_date(value: str) -> str:
    return str(value or "").strip().replace("-", "")


def _yyyymmdd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


def _shift_months(dt: datetime, months: int) -> datetime:
    month_index = dt.year * 12 + (dt.month - 1) + months
    year = month_index // 12
    month = month_index % 12 + 1
    last_day = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return dt.replace(year=year, month=month, day=min(dt.day, last_day))


def _available_dates(loaded: list[LoadedSymbol]) -> list[str]:
    dates: set[str] = set()
    for item in loaded:
        if "trade_date" in item.df.columns:
            dates.update(item.df["trade_date"].astype(str).tolist())
    return sorted(dates)


def _first_date_with_complete_coverage(loaded: list[LoadedSymbol], columns: tuple[str, ...], min_coverage: float) -> str:
    rows: list[pd.DataFrame] = []
    for item in loaded:
        existing = [column for column in columns if column in item.df.columns]
        if not existing:
            continue
        rows.append(item.df[["trade_date", *existing]].copy())
    if not rows:
        return ""
    frame = pd.concat(rows, ignore_index=True, sort=False)
    grouped = frame.groupby(frame["trade_date"].astype(str), sort=True)
    for trade_date, group in grouped:
        checks = []
        for column in columns:
            if column not in group.columns:
                checks.append(0.0)
                continue
            series = group[column]
            if pd.api.types.is_numeric_dtype(series):
                coverage = pd.to_numeric(series, errors="coerce").notna().mean()
            else:
                coverage = series.fillna("").astype(str).str.strip().ne("").mean()
            checks.append(float(coverage))
        if checks and min(checks) >= min_coverage:
            return str(trade_date)
    return ""


def _period_has_data(start: str, end: str, available_dates: list[str]) -> bool:
    return any(start <= trade_date <= end for trade_date in available_dates)


def build_periods(
    *,
    start_date: str,
    end_date: str,
    sector_start_date: str,
    sector_end_date: str,
    baseline_available_dates: list[str],
    sector_available_dates: list[str],
    rolling_months: list[int],
) -> list[PeriodSpec]:
    start = _normalize_date(start_date)
    end = _normalize_date(end_date)
    sector_start = max(start, _normalize_date(sector_start_date))
    sector_end = min(end, _normalize_date(sector_end_date))
    if not start or not end:
        raise ValueError("start_date 和 end_date 不能为空")
    if sector_start > sector_end:
        raise ValueError(f"板块/轮动有效覆盖区间为空：{sector_start} > {sector_end}")

    periods: list[PeriodSpec] = []
    if _period_has_data(sector_start, sector_end, sector_available_dates):
        periods.append(PeriodSpec("可比全区间", sector_start, sector_end, "full", "板块/轮动字段覆盖后才纳入公平比较"))

    for year in range(int(sector_start[:4]), int(sector_end[:4]) + 1):
        period_start = max(sector_start, f"{year}0101")
        period_end = min(sector_end, f"{year}1231")
        if period_start <= period_end and _period_has_data(period_start, period_end, sector_available_dates):
            label = f"{year}YTD" if year == int(sector_end[:4]) and period_end < f"{year}1231" else str(year)
            periods.append(PeriodSpec(label, period_start, period_end, "year"))

    end_dt = datetime.strptime(sector_end, "%Y%m%d")
    recent_start = max(sector_start, _yyyymmdd(end_dt.replace(year=end_dt.year - 1) + timedelta(days=1)))
    if recent_start <= sector_end and _period_has_data(recent_start, sector_end, sector_available_dates):
        periods.append(PeriodSpec("最近一年", recent_start, sector_end, "recent_year"))

    for months in rolling_months:
        current_end = end_dt
        while True:
            current_start = _shift_months(current_end, -months) + timedelta(days=1)
            start_text = max(sector_start, _yyyymmdd(current_start))
            end_text = min(sector_end, _yyyymmdd(current_end))
            if start_text > end_text:
                break
            if _period_has_data(start_text, end_text, sector_available_dates):
                label = f"滚动{months}月_{start_text}-{end_text}"
                periods.append(PeriodSpec(label, start_text, end_text, f"rolling_{months}m"))
            if start_text == sector_start:
                break
            current_end = current_start - timedelta(days=1)

    baseline_reference_end = min(end, "20221231")
    if start <= baseline_reference_end and _period_has_data(start, baseline_reference_end, baseline_available_dates):
        periods.append(PeriodSpec("基准历史参考_2016-2022", start, baseline_reference_end, "baseline_reference", "该区间缺少板块强度字段，只运行基准动量"))

    unique: dict[tuple[str, str, str, str], PeriodSpec] = {}
    for period in periods:
        unique[(period.label, period.start_date, period.end_date, period.kind)] = period
    return list(unique.values())


def _common_signal_kwargs(args: argparse.Namespace, period: PeriodSpec) -> dict[str, Any]:
    return {
        "start_date": period.start_date,
        "end_date": period.end_date,
        "sell_condition": args.sell_condition,
        "top_n": args.top_n,
        "buy_fee_rate": args.buy_fee_rate,
        "sell_fee_rate": args.sell_fee_rate,
        "stamp_tax_sell": args.stamp_tax_sell,
        "entry_offset": args.entry_offset,
        "exit_offset": args.exit_offset,
        "min_hold_days": args.min_hold_days,
        "max_hold_days": args.max_hold_days,
        "settlement_mode": args.settlement_mode,
        "realistic_execution": args.realistic_execution,
        "slippage_bps": args.slippage_bps,
    }


def _common_account_kwargs(args: argparse.Namespace, period: PeriodSpec) -> dict[str, Any]:
    return {
        **_common_signal_kwargs(args, period),
        "initial_cash": args.initial_cash,
        "per_trade_budget": args.per_trade_budget,
        "lot_size": args.lot_size,
        "min_commission": args.min_commission,
    }


def _score_case(row: dict[str, Any]) -> float:
    account_return = float(row.get("account_total_return") or 0.0)
    signal_median = float(row.get("signal_median_trade_return") or 0.0)
    account_win_rate = float(row.get("account_win_rate") or 0.0)
    account_drawdown = float(row.get("account_max_drawdown") or 0.0)
    buy_count = float(row.get("account_buy_count") or 0.0)
    activity_bonus = min(buy_count / 120.0, 1.0) * 0.08
    return account_return * 1.2 + signal_median * 1.5 + account_win_rate * 0.2 + activity_bonus - account_drawdown * 0.8


def _risk_note(row: dict[str, Any]) -> str:
    notes: list[str] = []
    buy_count = int(row.get("account_buy_count") or 0)
    drawdown = float(row.get("account_max_drawdown") or 0.0)
    total_return = float(row.get("account_total_return") or 0.0)
    median_return = float(row.get("signal_median_trade_return") or 0.0)
    if buy_count < 20:
        notes.append("交易次数偏少")
    if drawdown > 0.12:
        notes.append("账户回撤偏高")
    if total_return <= 0:
        notes.append("账户收益为负")
    if median_return <= 0:
        notes.append("信号中位收益不佳")
    return "；".join(notes) if notes else "通过基础风险筛选"


def _case_context_frame(case: RotationMatchCase, period: PeriodSpec, frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    out.insert(0, "period_label", period.label)
    out.insert(1, "period_kind", period.kind)
    out.insert(2, "case", case.name)
    out.insert(3, "family", case.family)
    out.insert(4, "buy_condition", case.buy_condition)
    out.insert(5, "score_expression", case.score_expression)
    for key, value in case.params.items():
        out[f"param_{key}"] = value
    return out


def _summarize_case(
    *,
    case: RotationMatchCase,
    period: PeriodSpec,
    signal_result: dict[str, Any],
    account_result: dict[str, Any],
) -> dict[str, Any]:
    signal_summary = signal_result["summary"]
    account_summary = account_result["summary"]
    row = {
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
        "signal_count": signal_summary.get("signal_count"),
        "signal_completed_count": signal_summary.get("completed_signal_count"),
        "signal_avg_trade_return": signal_summary.get("avg_trade_return"),
        "signal_median_trade_return": signal_summary.get("median_trade_return"),
        "signal_win_rate": signal_summary.get("win_rate"),
        "signal_profit_factor": signal_summary.get("profit_factor"),
        "signal_curve_return": signal_summary.get("signal_curve_return"),
        "signal_max_drawdown": signal_summary.get("max_drawdown"),
        "signal_candidate_day_ratio": signal_summary.get("candidate_day_ratio"),
        "signal_topn_fill_rate": signal_summary.get("topn_fill_rate"),
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
    row["grid_score"] = round(_score_case(row), 6)
    row["risk_note"] = _risk_note(row)
    return row


def _run_case(
    *,
    case: RotationMatchCase,
    period: PeriodSpec,
    args: argparse.Namespace,
    loaded: list[LoadedSymbol],
    diagnostics: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    signal_req = SignalQualityRequest(
        processed_dir=case.processed_dir,
        data_profile=case.data_profile,
        buy_condition=case.buy_condition,
        score_expression=case.score_expression,
        **_common_signal_kwargs(args, period),
    )
    signal_result = run_signal_quality_loaded(loaded, diagnostics, signal_req)
    account_req = BacktestRequest(
        processed_dir=case.processed_dir,
        data_profile=case.data_profile,
        buy_condition=case.buy_condition,
        score_expression=case.score_expression,
        **_common_account_kwargs(args, period),
    )
    account_result = run_portfolio_backtest_loaded(loaded, diagnostics, account_req)
    return signal_result, account_result


def _run_account_case(
    *,
    case: RotationMatchCase,
    period: PeriodSpec,
    args: argparse.Namespace,
    loaded: list[LoadedSymbol],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    account_req = BacktestRequest(
        processed_dir=case.processed_dir,
        data_profile=case.data_profile,
        buy_condition=case.buy_condition,
        score_expression=case.score_expression,
        **_common_account_kwargs(args, period),
    )
    return run_portfolio_backtest_loaded(loaded, diagnostics, account_req)


def _coverage_by_year(loaded: list[LoadedSymbol]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    columns = ["trade_date", *SECTOR_COVERAGE_COLUMNS, *ROTATION_COVERAGE_COLUMNS]
    for item in loaded:
        existing = [column for column in columns if column in item.df.columns]
        if "trade_date" not in existing:
            continue
        rows.append(item.df[existing].copy())
    if not rows:
        return pd.DataFrame()
    frame = pd.concat(rows, ignore_index=True, sort=False)
    frame["year"] = frame["trade_date"].astype(str).str[:4]
    result_rows: list[dict[str, Any]] = []
    for year, group in frame.groupby("year", sort=True):
        row: dict[str, Any] = {"year": year, "rows": len(group)}
        for column in SECTOR_COVERAGE_COLUMNS:
            row[f"{column}_coverage"] = _column_coverage(group, column)
        for column in ROTATION_COVERAGE_COLUMNS:
            row[f"{column}_coverage"] = _column_coverage(group, column)
        result_rows.append(row)
    return pd.DataFrame(result_rows)


def _column_coverage(frame: pd.DataFrame, column: str) -> float:
    if column not in frame.columns or frame.empty:
        return 0.0
    series = frame[column]
    if pd.api.types.is_numeric_dtype(series):
        return float(pd.to_numeric(series, errors="coerce").notna().mean())
    return float(series.fillna("").astype(str).str.strip().ne("").mean())


def _write_frames(path: Path, frames: list[pd.DataFrame]) -> None:
    usable = [frame for frame in frames if not frame.empty]
    if not usable:
        pd.DataFrame().to_csv(path, index=False, encoding="utf-8-sig")
        return
    pd.concat(usable, ignore_index=True, sort=False).to_csv(path, index=False, encoding="utf-8-sig")


def _period_sort_key(label: str, order: dict[str, int]) -> int:
    return order.get(label, len(order) + 1)


def _stability_rows(summary_df: pd.DataFrame) -> pd.DataFrame:
    comparable = summary_df[summary_df["period_kind"].isin(["year", "recent_year", "rolling_6m", "rolling_12m", "full"])].copy()
    if comparable.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    pivot_base = comparable[["period_label", "case", "account_total_return", "account_max_drawdown", "account_buy_count"]].copy()
    candidate_by_period = pivot_base[pivot_base["case"] == SECTOR_CANDIDATE_NAME].set_index("period_label")
    baseline_by_period = pivot_base[pivot_base["case"] == "基准动量"].set_index("period_label")
    for case, group in pivot_base.groupby("case", sort=False):
        returns = pd.to_numeric(group["account_total_return"], errors="coerce").fillna(0.0)
        drawdowns = pd.to_numeric(group["account_max_drawdown"], errors="coerce").fillna(0.0)
        buys = pd.to_numeric(group["account_buy_count"], errors="coerce").fillna(0.0)
        row: dict[str, Any] = {
            "case": case,
            "period_count": int(len(group)),
            "positive_period_count": int((returns > 0).sum()),
            "positive_period_ratio": round(float((returns > 0).mean()), 6) if len(group) else 0.0,
            "avg_period_return": round(float(returns.mean()), 6) if len(group) else 0.0,
            "min_period_return": round(float(returns.min()), 6) if len(group) else 0.0,
            "max_period_return": round(float(returns.max()), 6) if len(group) else 0.0,
            "avg_drawdown": round(float(drawdowns.mean()), 6) if len(group) else 0.0,
            "max_drawdown": round(float(drawdowns.max()), 6) if len(group) else 0.0,
            "avg_buy_count": round(float(buys.mean()), 2) if len(group) else 0.0,
        }
        beat_candidate = []
        beat_baseline = []
        for _, item in group.iterrows():
            period_label = str(item["period_label"])
            ret = float(item.get("account_total_return") or 0.0)
            if period_label in candidate_by_period.index and case != SECTOR_CANDIDATE_NAME:
                beat_candidate.append(ret - float(candidate_by_period.loc[period_label, "account_total_return"]))
            if period_label in baseline_by_period.index and case != "基准动量":
                beat_baseline.append(ret - float(baseline_by_period.loc[period_label, "account_total_return"]))
        row["beat_sector_candidate_count"] = int(sum(value >= 0 for value in beat_candidate)) if beat_candidate else ""
        row["beat_sector_candidate_ratio"] = round(sum(value >= 0 for value in beat_candidate) / len(beat_candidate), 6) if beat_candidate else ""
        row["avg_excess_vs_sector_candidate"] = round(sum(beat_candidate) / len(beat_candidate), 6) if beat_candidate else ""
        row["beat_baseline_count"] = int(sum(value >= 0 for value in beat_baseline)) if beat_baseline else ""
        row["beat_baseline_ratio"] = round(sum(value >= 0 for value in beat_baseline) / len(beat_baseline), 6) if beat_baseline else ""
        row["avg_excess_vs_baseline"] = round(sum(beat_baseline) / len(beat_baseline), 6) if beat_baseline else ""
        rows.append(row)
    return pd.DataFrame(rows)


def _pct(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(number):
        return "-"
    return f"{number * 100:.2f}%"


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
    summary_df: pd.DataFrame,
    stability_df: pd.DataFrame,
    coverage_df: pd.DataFrame,
    args: argparse.Namespace,
    out_dir: Path,
    sector_start_date: str,
    sector_end_date: str,
) -> str:
    period_order = {label: idx for idx, label in enumerate(summary_df["period_label"].drop_duplicates().tolist())}
    display_df = summary_df.copy()
    display_df["_period_order"] = display_df["period_label"].map(lambda value: _period_sort_key(str(value), period_order))
    display_df = display_df.sort_values(["_period_order", "case"]).drop(columns=["_period_order"])

    lines = [
        "# 板块轮动匹配稳定性验证报告",
        "",
        f"- 用户请求区间：{args.start_date} 至 {args.end_date}",
        f"- 板块/轮动可比区间：{sector_start_date} 至 {sector_end_date}",
        f"- 轮动日频文件：`{args.rotation_daily_path}`",
        f"- 基准目录：`{args.base_processed_dir}`",
        f"- 板块增强目录：`{args.sector_processed_dir}`",
        "- 目的：验证 `主线簇匹配加权_w5` 是否在分年度、最近一年和滚动窗口中稳定，不只依赖某一个年份。",
        "",
        "## 1. 数据覆盖",
        "",
        "板块/轮动策略只在 `sector_strongest_theme_score`、`rotation_top_cluster` 等字段覆盖后才公平比较。2016-2022 的股票行情可用于基准历史参考，但不用于板块轮动策略结论。",
        "",
        "| 年份 | 行数 | 板块强度覆盖 | 轮动主线覆盖 | 轮动状态覆盖 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for _, row in coverage_df.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
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
            "## 2. 分区间结果",
            "",
            "| 周期 | 类型 | 策略 | 收益 | 年化 | 回撤 | 买入 | 胜率 | 信号中位 | 风险提示 |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for _, row in display_df.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("period_label", "")),
                    str(row.get("period_kind", "")),
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
            "## 3. 稳定性汇总",
            "",
            "| 策略 | 区间数 | 正收益区间 | 正收益占比 | 平均区间收益 | 最差区间收益 | 最大回撤 | 跑赢板块候选次数 | 跑赢板块候选占比 | 相对板块候选平均超额 | 跑赢基准次数 | 跑赢基准占比 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in stability_df.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("case", "")),
                    str(int(row.get("period_count") or 0)),
                    str(int(row.get("positive_period_count") or 0)),
                    _pct(row.get("positive_period_ratio")),
                    _pct(row.get("avg_period_return")),
                    _pct(row.get("min_period_return")),
                    _pct(row.get("max_drawdown")),
                    str(row.get("beat_sector_candidate_count", "")),
                    _pct(row.get("beat_sector_candidate_ratio")),
                    _pct(row.get("avg_excess_vs_sector_candidate")),
                    str(row.get("beat_baseline_count", "")),
                    _pct(row.get("beat_baseline_ratio")),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 4. 输出文件",
            "",
            f"- 区间汇总：`{(out_dir / 'sector_rotation_match_stability_summary.csv').as_posix()}`",
            f"- 稳定性汇总：`{(out_dir / 'sector_rotation_match_stability_by_case.csv').as_posix()}`",
            f"- 年度覆盖：`{(out_dir / 'sector_rotation_match_stability_coverage.csv').as_posix()}`",
            f"- 买卖流水：`{(out_dir / 'sector_rotation_match_stability_trade_records.csv').as_posix()}`",
            f"- 参数配置：`{(out_dir / 'sector_rotation_match_stability_config.json').as_posix()}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _cases_for_period(cases: list[RotationMatchCase], period: PeriodSpec) -> list[RotationMatchCase]:
    if period.kind == "baseline_reference":
        return [case for case in cases if case.family == "baseline"]
    return cases


def run_sector_rotation_match_stability(args: argparse.Namespace) -> Path:
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    base_loaded, base_diagnostics = load_processed_folder(args.base_processed_dir)
    base_diagnostics["data_profile"] = "base"
    sector_loaded, sector_diagnostics = load_processed_folder(args.sector_processed_dir)
    sector_diagnostics.update(validate_sector_feature_set(loaded_items=sector_loaded, processed_dir=sector_diagnostics["processed_dir"]))
    rotation_daily = load_rotation_daily(args.rotation_daily_path)
    rotation_loaded = merge_rotation_features(sector_loaded, rotation_daily)
    rotation_diagnostics = dict(sector_diagnostics)
    rotation_diagnostics["rotation_daily_path"] = str(Path(args.rotation_daily_path))
    rotation_diagnostics["rotation_match_feature_enabled"] = True

    baseline_dates = _available_dates(base_loaded)
    sector_dates = _available_dates(rotation_loaded)
    first_sector_date = _first_date_with_complete_coverage(rotation_loaded, SECTOR_COVERAGE_COLUMNS, args.min_coverage)
    first_rotation_date = _first_date_with_complete_coverage(rotation_loaded, ROTATION_COVERAGE_COLUMNS, args.min_coverage)
    sector_start_date = max(_normalize_date(args.start_date), first_sector_date, first_rotation_date)
    sector_end_date = min(_normalize_date(args.end_date), max(sector_dates) if sector_dates else _normalize_date(args.end_date))
    periods = build_periods(
        start_date=args.start_date,
        end_date=args.end_date,
        sector_start_date=sector_start_date,
        sector_end_date=sector_end_date,
        baseline_available_dates=baseline_dates,
        sector_available_dates=sector_dates,
        rolling_months=_parse_int_list(args.rolling_months),
    )
    cases = build_stability_cases(base_processed_dir=args.base_processed_dir, sector_processed_dir=args.sector_processed_dir)

    summary_path = out_dir / "sector_rotation_match_stability_summary.csv"
    stability_path = out_dir / "sector_rotation_match_stability_by_case.csv"
    coverage_path = out_dir / "sector_rotation_match_stability_coverage.csv"
    trades_path = out_dir / "sector_rotation_match_stability_trade_records.csv"
    config_path = out_dir / "sector_rotation_match_stability_config.json"
    report_path = out_dir / "sector_rotation_match_stability_report.md"

    config_path.write_text(
        json.dumps(
            {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "args": vars(args),
                "sector_start_date": sector_start_date,
                "sector_end_date": sector_end_date,
                "periods": [asdict(period) for period in periods],
                "cases": [asdict(case) for case in cases],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    coverage_df = _coverage_by_year(rotation_loaded)
    coverage_df.to_csv(coverage_path, index=False, encoding="utf-8-sig")

    summary_rows: list[dict[str, Any]] = []
    trade_frames: list[pd.DataFrame] = []
    completed_keys: set[tuple[str, str]] = set()
    completed_trade_keys: set[tuple[str, str]] = set()
    if args.resume and summary_path.exists():
        existing_summary = pd.read_csv(summary_path, encoding="utf-8-sig")
        if not existing_summary.empty and {"period_label", "case"}.issubset(existing_summary.columns):
            summary_rows = existing_summary.to_dict("records")
            completed_keys = set(zip(existing_summary["period_label"].astype(str), existing_summary["case"].astype(str)))
            print(f"检测到已完成 {len(completed_keys)} 个区间策略组合，将从缺口继续", flush=True)
    if args.resume and not args.skip_trade_records and trades_path.exists():
        existing_trades = pd.read_csv(trades_path, encoding="utf-8-sig")
        if not existing_trades.empty:
            trade_frames.append(existing_trades)
            if {"period_label", "case"}.issubset(existing_trades.columns):
                completed_trade_keys = set(zip(existing_trades["period_label"].astype(str), existing_trades["case"].astype(str)))

    total_runs = sum(len(_cases_for_period(cases, period)) for period in periods)
    current = 0
    new_run_count = 0
    for period in periods:
        for case in _cases_for_period(cases, period):
            key = (period.label, case.name)
            summary_done = key in completed_keys
            trade_done = args.skip_trade_records or key in completed_trade_keys
            should_fill_trade = args.fill_missing_trade_records and summary_done and not trade_done
            if summary_done and not should_fill_trade:
                current += 1
                print(f"[{current}/{total_runs}] 跳过已完成 {period.label} {case.name}", flush=True)
                continue
            if args.max_runs > 0 and new_run_count >= args.max_runs:
                print(f"已达到本批上限 {args.max_runs}，保留中间结果并退出", flush=True)
                break
            current += 1
            action_text = "补交易流水" if should_fill_trade else "运行"
            print(f"[{current}/{total_runs}] {action_text} {period.label} {case.name}", flush=True)
            if case.family == "baseline":
                loaded, diagnostics = base_loaded, base_diagnostics
            else:
                loaded, diagnostics = rotation_loaded, rotation_diagnostics
            if should_fill_trade:
                account_result = _run_account_case(case=case, period=period, args=args, loaded=loaded, diagnostics=diagnostics)
            else:
                signal_result, account_result = _run_case(case=case, period=period, args=args, loaded=loaded, diagnostics=diagnostics)
                summary_rows.append(_summarize_case(case=case, period=period, signal_result=signal_result, account_result=account_result))
                completed_keys.add(key)
            new_run_count += 1
            if not args.skip_trade_records:
                trade_frame = _case_context_frame(case, period, pd.DataFrame(account_result.get("trade_rows", [])))
                if not trade_frame.empty:
                    trade_frames.append(trade_frame)
                    completed_trade_keys.add(key)
                    _write_frames(trades_path, trade_frames)
            summary_df = pd.DataFrame(summary_rows)
            summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
            _stability_rows(summary_df).to_csv(stability_path, index=False, encoding="utf-8-sig")
        if args.max_runs > 0 and len(summary_rows) >= args.max_runs:
            break

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    stability_df = _stability_rows(summary_df)
    stability_df.to_csv(stability_path, index=False, encoding="utf-8-sig")
    if not args.skip_trade_records:
        _write_frames(trades_path, trade_frames)
    report_path.write_text(
        _render_report(
            summary_df=summary_df,
            stability_df=stability_df,
            coverage_df=coverage_df,
            args=args,
            out_dir=out_dir,
            sector_start_date=sector_start_date,
            sector_end_date=sector_end_date,
        ),
        encoding="utf-8",
    )
    print(f"板块轮动匹配稳定性验证完成：{out_dir.as_posix()}")
    return out_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证板块轮动匹配策略在分年度、最近一年和滚动窗口中的稳定性")
    parser.add_argument("--base-processed-dir", default="data_bundle/processed_qfq_theme_focus_top100")
    parser.add_argument("--sector-processed-dir", default="data_bundle/processed_qfq_theme_focus_top100_sector")
    parser.add_argument("--rotation-daily-path", default="research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv")
    parser.add_argument("--start-date", default="20160101")
    parser.add_argument("--end-date", default="20260429")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--rolling-months", default="6,12")
    parser.add_argument("--min-coverage", type=float, default=0.95, help="板块/轮动字段达到该覆盖率后才进入可比区间")
    parser.add_argument("--sell-condition", default=SELL_CONDITION)
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
    parser.add_argument("--skip-trade-records", action="store_true")
    parser.add_argument("--resume", action="store_true", help="同一 out-dir 已有中间结果时跳过已完成区间策略组合")
    parser.add_argument("--fill-missing-trade-records", action="store_true", help="配合 --resume 使用，只补齐已有汇总中缺失的交易流水")
    parser.add_argument("--max-runs", type=int, default=0, help="单次最多运行多少个区间策略组合，0 表示不限制")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    run_sector_rotation_match_stability(parse_args(argv))


if __name__ == "__main__":
    main()
