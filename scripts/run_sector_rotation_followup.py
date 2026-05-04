from __future__ import annotations

import argparse
import json
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
from scripts.run_sector_rotation_grid import SECTOR_CANDIDATE_FILTER, load_rotation_daily, merge_rotation_features


@dataclass(frozen=True)
class FollowupCase:
    name: str
    family: str
    processed_dir: str
    data_profile: str
    buy_condition: str
    score_expression: str
    params: dict[str, Any]


@dataclass(frozen=True)
class PeriodSpec:
    label: str
    start_date: str
    end_date: str
    kind: str


def _default_out_dir() -> Path:
    return Path("research_runs") / f"{datetime.now():%Y%m%d_%H%M%S}_sector_rotation_followup"


def _parse_float_list(raw_text: str) -> list[float]:
    values = [float(token.strip()) for token in str(raw_text).split(",") if token.strip()]
    if not values:
        raise ValueError("参数列表不能为空")
    return values


def _fmt_weight(value: float) -> str:
    return f"{value:g}"


def _sector_candidate_condition(*extra_parts: str) -> str:
    parts = [BASE_BUY_CONDITION, SECTOR_CANDIDATE_FILTER]
    parts.extend(part for part in extra_parts if str(part or "").strip())
    return ",".join(parts)


def _rotation_weighted_score(*, tech_bonus: float, new_energy_penalty: float, new_start_penalty: float) -> str:
    return (
        f"{BASE_SCORE_EXPRESSION} "
        f"+ rotation_top_cluster_tech * {_fmt_weight(tech_bonus)} "
        f"- rotation_top_cluster_new_energy * {_fmt_weight(new_energy_penalty)} "
        f"- rotation_is_new_start * {_fmt_weight(new_start_penalty)}"
    )


def build_comparison_cases(*, base_processed_dir: str, sector_processed_dir: str) -> list[FollowupCase]:
    return [
        FollowupCase(
            name="基准动量",
            family="baseline",
            processed_dir=base_processed_dir,
            data_profile="auto",
            buy_condition=BASE_BUY_CONDITION,
            score_expression=BASE_SCORE_EXPRESSION,
            params={"rotation_usage": "none"},
        ),
        FollowupCase(
            name="板块候选_score0.4_rank0.7",
            family="sector_candidate",
            processed_dir=sector_processed_dir,
            data_profile="sector",
            buy_condition=_sector_candidate_condition(),
            score_expression=BASE_SCORE_EXPRESSION,
            params={"rotation_usage": "none"},
        ),
        FollowupCase(
            name="候选_避开新能源主线",
            family="rotation_hard_filter",
            processed_dir=sector_processed_dir,
            data_profile="sector",
            buy_condition=_sector_candidate_condition("rotation_top_cluster!=新能源"),
            score_expression=BASE_SCORE_EXPRESSION,
            params={"rotation_usage": "hard_filter", "rotation_filter": "非新能源主线"},
        ),
    ]


def build_weighted_score_cases(
    *,
    sector_processed_dir: str,
    tech_bonuses: list[float],
    new_energy_penalties: list[float],
    new_start_penalties: list[float],
) -> list[FollowupCase]:
    cases: list[FollowupCase] = []
    for tech_bonus in tech_bonuses:
        for new_energy_penalty in new_energy_penalties:
            for new_start_penalty in new_start_penalties:
                name = (
                    f"轮动加权_tech{_fmt_weight(tech_bonus)}"
                    f"_ne{_fmt_weight(new_energy_penalty)}"
                    f"_new{_fmt_weight(new_start_penalty)}"
                )
                cases.append(
                    FollowupCase(
                        name=name,
                        family="rotation_score_weight",
                        processed_dir=sector_processed_dir,
                        data_profile="sector",
                        buy_condition=_sector_candidate_condition(),
                        score_expression=_rotation_weighted_score(
                            tech_bonus=tech_bonus,
                            new_energy_penalty=new_energy_penalty,
                            new_start_penalty=new_start_penalty,
                        ),
                        params={
                            "rotation_usage": "score_weight",
                            "tech_bonus": tech_bonus,
                            "new_energy_penalty": new_energy_penalty,
                            "new_start_penalty": new_start_penalty,
                        },
                    )
                )
    return cases


def build_periods(start_date: str, end_date: str) -> list[PeriodSpec]:
    start = str(start_date).strip()
    end = str(end_date).strip()
    if not start or not end:
        raise ValueError("start_date 和 end_date 都不能为空")
    periods = [PeriodSpec("全区间", start, end, "full")]
    start_year = int(start[:4])
    end_year = int(end[:4])
    for year in range(start_year, end_year + 1):
        period_start = max(start, f"{year}0101")
        period_end = min(end, f"{year}1231")
        if period_start <= period_end:
            label = f"{year}" if year < end_year else f"{year}YTD"
            periods.append(PeriodSpec(label, period_start, period_end, "year"))
    end_dt = datetime.strptime(end, "%Y%m%d")
    recent_start = (end_dt.replace(year=end_dt.year - 1) + timedelta(days=1)).strftime("%Y%m%d")
    periods.append(PeriodSpec("最近一年", max(start, recent_start), end, "recent_year"))
    return periods


def _common_signal_kwargs(args: argparse.Namespace, period: PeriodSpec | None = None) -> dict[str, Any]:
    return {
        "start_date": period.start_date if period else args.start_date,
        "end_date": period.end_date if period else args.end_date,
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


def _common_account_kwargs(args: argparse.Namespace, period: PeriodSpec | None = None) -> dict[str, Any]:
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
    if buy_count < 60:
        notes.append("交易次数偏少")
    if drawdown > 0.12:
        notes.append("账户回撤偏高")
    if total_return <= 0:
        notes.append("账户收益为负")
    if median_return <= 0:
        notes.append("信号中位收益不佳")
    return "；".join(notes) if notes else "通过基础风险筛选"


def _summarize_case(
    *,
    case: FollowupCase,
    signal_result: dict[str, Any],
    account_result: dict[str, Any],
    period: PeriodSpec | None = None,
) -> dict[str, Any]:
    signal_summary = signal_result["summary"]
    account_summary = account_result["summary"]
    row = {
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
    if period is not None:
        row.update(
            {
                "period_label": period.label,
                "period_start": period.start_date,
                "period_end": period.end_date,
                "period_kind": period.kind,
            }
        )
    row.update({f"param_{key}": value for key, value in case.params.items()})
    row["grid_score"] = round(_score_case(row), 6)
    row["risk_note"] = _risk_note(row)
    return row


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "-"


def _num(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _dataset_for_case(
    case: FollowupCase,
    *,
    base_loaded: list[LoadedSymbol],
    base_diagnostics: dict[str, Any],
    rotation_loaded: list[LoadedSymbol],
    rotation_diagnostics: dict[str, Any],
) -> tuple[list[LoadedSymbol], dict[str, Any]]:
    if case.family == "baseline":
        return base_loaded, base_diagnostics
    return rotation_loaded, rotation_diagnostics


def _run_case(
    *,
    case: FollowupCase,
    args: argparse.Namespace,
    loaded: list[LoadedSymbol],
    diagnostics: dict[str, Any],
    period: PeriodSpec | None = None,
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


def _annual_concentration(period_df: pd.DataFrame) -> list[str]:
    rows: list[str] = []
    yearly = period_df[period_df["period_kind"] == "year"].copy()
    if yearly.empty:
        return rows
    for case, group in yearly.groupby("case", sort=False):
        returns = pd.to_numeric(group["account_total_return"], errors="coerce").fillna(0.0)
        positive_sum = returns[returns > 0].sum()
        best_idx = returns.idxmax()
        best_label = str(yearly.loc[best_idx, "period_label"])
        best_return = float(yearly.loc[best_idx, "account_total_return"] or 0.0)
        if positive_sum > 0:
            concentration = best_return / positive_sum
            rows.append(f"- `{case}` 最好年份是 `{best_label}`，收益 {_pct(best_return)}，占正收益年份合计的 {_pct(concentration)}。")
        else:
            rows.append(f"- `{case}` 没有正收益年份，最好年份 `{best_label}` 收益 {_pct(best_return)}。")
    return rows


def _render_report(period_df: pd.DataFrame, weighted_df: pd.DataFrame, args: argparse.Namespace, out_dir: Path) -> str:
    lines = [
        "# 板块轮动后续验证报告",
        "",
        f"- 回测区间：{args.start_date} 至 {args.end_date}",
        f"- 轮动日频文件：`{args.rotation_daily_path}`",
        f"- 基准目录：`{args.base_processed_dir}`",
        f"- 板块增强目录：`{args.sector_processed_dir}`",
        "- 本报告落实 2026-05-01 结果记录里的两项建议：分年度/最近一年对比，以及轮动评分加权实验。",
        "",
        "## 1. 分年度和最近一年对比",
        "",
        "| 周期 | 策略 | 账户收益 | 年化 | 回撤 | 买入次数 | 胜率 | 信号中位 | 风险提示 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    period_order = {label: idx for idx, label in enumerate(period_df["period_label"].drop_duplicates().tolist())}
    display_period = period_df.sort_values(["period_label", "case"], key=lambda col: col.map(period_order) if col.name == "period_label" else col)
    for _, row in display_period.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("period_label", "")),
                    str(row["case"]),
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
    lines.extend(["", "年度集中度观察：", ""])
    lines.extend(_annual_concentration(period_df))

    ranked_weighted = weighted_df.sort_values(["grid_score", "account_total_return", "account_max_drawdown"], ascending=[False, False, True]).reset_index(drop=True)
    lines.extend(
        [
            "",
            "## 2. 轮动加权评分实验",
            "",
            "| 排名 | 策略 | 科技加分 | 新能源扣分 | 新启动扣分 | 账户收益 | 年化 | 回撤 | 买入次数 | 胜率 | 信号中位 | grid_score | 风险提示 |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for idx, row in ranked_weighted.head(args.report_top_k).iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx + 1),
                    str(row["case"]),
                    _num(row.get("param_tech_bonus"), 1),
                    _num(row.get("param_new_energy_penalty"), 1),
                    _num(row.get("param_new_start_penalty"), 1),
                    _pct(row.get("account_total_return")),
                    _pct(row.get("account_annualized_return")),
                    _pct(row.get("account_max_drawdown")),
                    str(int(row.get("account_buy_count") or 0)),
                    _pct(row.get("account_win_rate")),
                    _pct(row.get("signal_median_trade_return")),
                    _num(row.get("grid_score"), 4),
                    str(row.get("risk_note") or ""),
                ]
            )
            + " |"
        )

    base_weight = weighted_df[
        (pd.to_numeric(weighted_df.get("param_tech_bonus"), errors="coerce").fillna(-1) == 0)
        & (pd.to_numeric(weighted_df.get("param_new_energy_penalty"), errors="coerce").fillna(-1) == 0)
        & (pd.to_numeric(weighted_df.get("param_new_start_penalty"), errors="coerce").fillna(-1) == 0)
    ]
    if not base_weight.empty and not ranked_weighted.empty:
        base = base_weight.iloc[0]
        best = ranked_weighted.iloc[0]
        lines.extend(
            [
                "",
                "加权结论：",
                "",
                f"- 不加权的板块候选收益为 {_pct(base.get('account_total_return'))}，回撤 {_pct(base.get('account_max_drawdown'))}。",
                f"- 本轮加权最优为 `{best['case']}`，收益 {_pct(best.get('account_total_return'))}，回撤 {_pct(best.get('account_max_drawdown'))}。",
            ]
        )
        if float(best.get("account_total_return") or 0.0) > float(base.get("account_total_return") or 0.0):
            lines.append("- 加权评分有改善收益的迹象，后续可以进一步做更细权重和滚动窗口验证。")
        else:
            lines.append("- 当前权重没有超过不加权板块候选，轮动更适合作为风险提示或小权重观察项。")

    lines.extend(
        [
            "",
            "## 输出文件",
            "",
            f"- 分年度/最近一年对比：`{(out_dir / 'sector_rotation_period_comparison.csv').as_posix()}`",
            f"- 加权评分汇总：`{(out_dir / 'sector_rotation_weighted_score_summary.csv').as_posix()}`",
            f"- 加权评分交易流水：`{(out_dir / 'sector_rotation_weighted_score_trade_records.csv').as_posix()}`",
            f"- 参数配置：`{(out_dir / 'sector_rotation_followup_config.json').as_posix()}`",
        ]
    )
    return "\n".join(lines) + "\n"


def run_followup(args: argparse.Namespace) -> Path:
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    rotation_daily = load_rotation_daily(args.rotation_daily_path)
    base_loaded, base_diagnostics = load_processed_folder(args.base_processed_dir)
    base_diagnostics["data_profile"] = "base"
    sector_loaded, sector_diagnostics = load_processed_folder(args.sector_processed_dir)
    sector_diagnostics.update(validate_sector_feature_set(loaded_items=sector_loaded, processed_dir=sector_diagnostics["processed_dir"]))
    rotation_loaded = merge_rotation_features(sector_loaded, rotation_daily)
    rotation_diagnostics = dict(sector_diagnostics)
    rotation_diagnostics["rotation_daily_path"] = str(Path(args.rotation_daily_path))
    rotation_diagnostics["rotation_feature_enabled"] = True

    comparison_cases = build_comparison_cases(base_processed_dir=args.base_processed_dir, sector_processed_dir=args.sector_processed_dir)
    weighted_cases = build_weighted_score_cases(
        sector_processed_dir=args.sector_processed_dir,
        tech_bonuses=_parse_float_list(args.tech_bonuses),
        new_energy_penalties=_parse_float_list(args.new_energy_penalties),
        new_start_penalties=_parse_float_list(args.new_start_penalties),
    )
    periods = build_periods(args.start_date, args.end_date)

    period_path = out_dir / "sector_rotation_period_comparison.csv"
    weighted_path = out_dir / "sector_rotation_weighted_score_summary.csv"
    weighted_trades_path = out_dir / "sector_rotation_weighted_score_trade_records.csv"
    config_path = out_dir / "sector_rotation_followup_config.json"
    report_path = out_dir / "sector_rotation_followup_report.md"
    period_rows: list[dict[str, Any]] = []
    weighted_rows: list[dict[str, Any]] = []
    completed_period_keys: set[tuple[str, str]] = set()
    completed_weighted_cases: set[str] = set()
    completed_trade_cases: set[str] = set()

    if args.resume:
        if period_path.exists() and period_path.stat().st_size > 0:
            period_df_existing = pd.read_csv(period_path, encoding="utf-8-sig")
            period_rows = period_df_existing.to_dict("records")
            completed_period_keys = {
                (str(row.get("period_label") or ""), str(row.get("case") or "")) for row in period_rows
            }
        if weighted_path.exists() and weighted_path.stat().st_size > 0:
            weighted_df_existing = pd.read_csv(weighted_path, encoding="utf-8-sig")
            weighted_rows = weighted_df_existing.to_dict("records")
            completed_weighted_cases = {str(row.get("case") or "") for row in weighted_rows}
        if weighted_trades_path.exists() and weighted_trades_path.stat().st_size > 0:
            try:
                trade_case_frame = pd.read_csv(weighted_trades_path, usecols=["case"], encoding="utf-8-sig")
                completed_trade_cases = set(trade_case_frame["case"].dropna().astype(str).tolist())
            except pd.errors.EmptyDataError:
                completed_trade_cases = set()
            except ValueError:
                completed_trade_cases = set()

    config_path.write_text(
        json.dumps(
            {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "args": vars(args),
                "periods": [asdict(period) for period in periods],
                "comparison_cases": [asdict(case) for case in comparison_cases],
                "weighted_cases": [asdict(case) for case in weighted_cases],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    total_period_runs = len(periods) * len(comparison_cases)
    run_idx = 0
    for period in periods:
        for case in comparison_cases:
            run_idx += 1
            period_key = (period.label, case.name)
            if period_key in completed_period_keys:
                print(f"[period {run_idx}/{total_period_runs}] 跳过已完成 {period.label} - {case.name}", flush=True)
                continue
            print(f"[period {run_idx}/{total_period_runs}] {period.label} - {case.name}", flush=True)
            loaded, diagnostics = _dataset_for_case(
                case,
                base_loaded=base_loaded,
                base_diagnostics=base_diagnostics,
                rotation_loaded=rotation_loaded,
                rotation_diagnostics=rotation_diagnostics,
            )
            signal_result, account_result = _run_case(case=case, args=args, loaded=loaded, diagnostics=diagnostics, period=period)
            period_rows.append(_summarize_case(case=case, signal_result=signal_result, account_result=account_result, period=period))
            pd.DataFrame(period_rows).to_csv(period_path, index=False, encoding="utf-8-sig")

    weighted_run_count = 0
    for idx, case in enumerate(weighted_cases, start=1):
        if case.name in completed_weighted_cases and (args.skip_trade_records or case.name in completed_trade_cases):
            print(f"[weighted {idx}/{len(weighted_cases)}] 跳过已完成 {case.name}", flush=True)
            continue
        if args.max_weighted_runs > 0 and weighted_run_count >= args.max_weighted_runs:
            print(f"[weighted] 已达到本批上限 {args.max_weighted_runs}，保留中间结果并退出", flush=True)
            break
        print(f"[weighted {idx}/{len(weighted_cases)}] {case.name}", flush=True)
        signal_result, account_result = _run_case(case=case, args=args, loaded=rotation_loaded, diagnostics=rotation_diagnostics)
        weighted_run_count += 1
        weighted_rows = [row for row in weighted_rows if str(row.get("case") or "") != case.name]
        weighted_rows.append(_summarize_case(case=case, signal_result=signal_result, account_result=account_result))
        pd.DataFrame(weighted_rows).to_csv(weighted_path, index=False, encoding="utf-8-sig")
        if not args.skip_trade_records:
            trades = pd.DataFrame(account_result.get("trade_rows", []))
            if not trades.empty:
                trades.insert(0, "case", case.name)
                trades.insert(1, "family", case.family)
                trades.insert(2, "buy_condition", case.buy_condition)
                trades.insert(3, "score_expression", case.score_expression)
                for key, value in case.params.items():
                    trades[f"param_{key}"] = value
                write_header = not weighted_trades_path.exists() or weighted_trades_path.stat().st_size == 0
                trades.to_csv(weighted_trades_path, mode="a", header=write_header, index=False, encoding="utf-8-sig")

    period_df = pd.DataFrame(period_rows)
    weighted_df = pd.DataFrame(weighted_rows).sort_values(["grid_score", "account_total_return", "account_max_drawdown"], ascending=[False, False, True])
    period_df.to_csv(period_path, index=False, encoding="utf-8-sig")
    weighted_df.to_csv(weighted_path, index=False, encoding="utf-8-sig")
    if not weighted_trades_path.exists():
        pd.DataFrame().to_csv(weighted_trades_path, index=False, encoding="utf-8-sig")
    report_path.write_text(_render_report(period_df, weighted_df, args, out_dir), encoding="utf-8")
    print(f"板块轮动后续验证完成：{out_dir.as_posix()}")
    return out_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="落实板块轮动结果记录的后续建议：年度对比和轮动评分加权")
    parser.add_argument("--base-processed-dir", default="data_bundle/processed_qfq_theme_focus_top100")
    parser.add_argument("--sector-processed-dir", default="data_bundle/processed_qfq_theme_focus_top100_sector")
    parser.add_argument("--rotation-daily-path", default="research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv")
    parser.add_argument("--start-date", default="20230101")
    parser.add_argument("--end-date", default="20260429")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--tech-bonuses", default="0,2,4")
    parser.add_argument("--new-energy-penalties", default="0,2,4")
    parser.add_argument("--new-start-penalties", default="0,2,4")
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
    parser.add_argument("--resume", action="store_true", help="输出目录已有中间结果时跳过已完成组合并继续生成缺失内容")
    parser.add_argument("--max-weighted-runs", type=int, default=0, help="单次最多新增运行多少个加权组合，0 表示不限制；用于长实验分批续跑")
    parser.add_argument("--report-top-k", type=int, default=12)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    run_followup(parse_args(argv))


if __name__ == "__main__":
    main()
