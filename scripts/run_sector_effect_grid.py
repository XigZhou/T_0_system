from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
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


REQUIRED_EFFECT_COLUMNS = {
    "sector_exposure_score",
    "sector_strongest_theme_score",
    "sector_strongest_theme_rank_pct",
    "sector_strongest_theme_m20",
    "sector_strongest_theme_amount_ratio_20",
    "sector_strongest_theme_board_up_ratio",
    "sector_strongest_theme_positive_m20_ratio",
}


@dataclass(frozen=True)
class SectorEffectCase:
    name: str
    family: str
    processed_dir: str
    data_profile: str
    buy_condition: str
    score_expression: str
    params: dict[str, Any]


def _default_out_dir() -> Path:
    return Path("research_runs") / f"{datetime.now():%Y%m%d_%H%M%S}_sector_effect_grid"


def _parse_float_list(raw_text: str) -> list[float]:
    values = [float(token.strip()) for token in str(raw_text).split(",") if token.strip()]
    if not values:
        raise ValueError("参数列表不能为空")
    return values


def _parse_optional_float_list(raw_text: str) -> list[float | None]:
    values: list[float | None] = []
    for token in str(raw_text).split(","):
        item = token.strip().lower()
        if not item:
            continue
        if item in {"any", "none", "all", "na", "null", "-"}:
            values.append(None)
        else:
            values.append(float(item))
    if not values:
        raise ValueError("参数列表不能为空")
    return values


def _fmt_value(value: float | None) -> str:
    return "any" if value is None else f"{value:g}"


def _field_filter(field: str, op: str, value: float | None) -> str:
    if value is None:
        return ""
    return f"{field}{op}{value:g}"


def _sector_effect_condition(
    *,
    score_threshold: float,
    rank_pct: float,
    exposure_min: float,
    theme_m20_min: float | None,
    amount_ratio_min: float | None,
) -> str:
    exposure_part = "sector_exposure_score>0" if exposure_min <= 0 else f"sector_exposure_score>={exposure_min:g}"
    parts = [
        BASE_BUY_CONDITION,
        exposure_part,
        f"sector_strongest_theme_score>={score_threshold:g}",
        f"sector_strongest_theme_rank_pct<={rank_pct:g}",
        _field_filter("sector_strongest_theme_m20", ">=", theme_m20_min),
        _field_filter("sector_strongest_theme_amount_ratio_20", ">=", amount_ratio_min),
    ]
    return ",".join(part for part in parts if part)


def _case_name(
    *,
    score_threshold: float,
    rank_pct: float,
    exposure_min: float,
    theme_m20_min: float | None,
    amount_ratio_min: float | None,
) -> str:
    if (
        score_threshold == 0.4
        and rank_pct == 0.7
        and exposure_min <= 0
        and theme_m20_min is None
        and amount_ratio_min is None
    ):
        return "板块候选_score0.4_rank0.7"
    return (
        f"板块效应_score{score_threshold:g}"
        f"_rank{rank_pct:g}"
        f"_exp{exposure_min:g}"
        f"_m20{_fmt_value(theme_m20_min)}"
        f"_amt{_fmt_value(amount_ratio_min)}"
    )


def _sector_effect_weighted_score(weight: float) -> str:
    score_weight = weight
    exposure_weight = max(weight / 2.0, 1.0)
    rank_penalty = max(weight / 2.0, 1.0)
    m20_weight = max(weight * 3.0, 1.0)
    amount_weight = max(weight / 3.0, 1.0)
    up_ratio_weight = max(weight / 3.0, 1.0)
    return (
        f"{BASE_SCORE_EXPRESSION} "
        f"+ sector_strongest_theme_score * {score_weight:g} "
        f"+ sector_exposure_score * {exposure_weight:g} "
        f"- sector_strongest_theme_rank_pct * {rank_penalty:g} "
        f"+ sector_strongest_theme_m20 * {m20_weight:g} "
        f"+ (sector_strongest_theme_amount_ratio_20 - 1) * {amount_weight:g} "
        f"+ sector_strongest_theme_board_up_ratio * {up_ratio_weight:g}"
    )


def build_sector_effect_cases(
    *,
    base_processed_dir: str,
    sector_processed_dir: str,
    score_thresholds: list[float],
    rank_pcts: list[float],
    exposure_mins: list[float],
    theme_m20_mins: list[float | None],
    amount_ratio_mins: list[float | None],
    score_weights: list[float],
    include_baseline: bool = True,
) -> list[SectorEffectCase]:
    cases: list[SectorEffectCase] = []
    if include_baseline:
        cases.append(
            SectorEffectCase(
                name="基准动量",
                family="baseline",
                processed_dir=base_processed_dir,
                data_profile="auto",
                buy_condition=BASE_BUY_CONDITION,
                score_expression=BASE_SCORE_EXPRESSION,
                params={"effect_usage": "none"},
            )
        )

    seen: set[str] = set()
    for score_threshold in score_thresholds:
        for rank_pct in rank_pcts:
            for exposure_min in exposure_mins:
                for theme_m20_min in theme_m20_mins:
                    for amount_ratio_min in amount_ratio_mins:
                        name = _case_name(
                            score_threshold=score_threshold,
                            rank_pct=rank_pct,
                            exposure_min=exposure_min,
                            theme_m20_min=theme_m20_min,
                            amount_ratio_min=amount_ratio_min,
                        )
                        if name in seen:
                            continue
                        seen.add(name)
                        cases.append(
                            SectorEffectCase(
                                name=name,
                                family="hard_filter",
                                processed_dir=sector_processed_dir,
                                data_profile="sector",
                                buy_condition=_sector_effect_condition(
                                    score_threshold=score_threshold,
                                    rank_pct=rank_pct,
                                    exposure_min=exposure_min,
                                    theme_m20_min=theme_m20_min,
                                    amount_ratio_min=amount_ratio_min,
                                ),
                                score_expression=BASE_SCORE_EXPRESSION,
                                params={
                                    "effect_usage": "hard_filter",
                                    "score_threshold": score_threshold,
                                    "rank_pct": rank_pct,
                                    "exposure_min": exposure_min,
                                    "theme_m20_min": theme_m20_min,
                                    "amount_ratio_min": amount_ratio_min,
                                    "score_weight": 0.0,
                                },
                            )
                        )

    for weight in score_weights:
        cases.append(
            SectorEffectCase(
                name=f"板块效应评分_w{weight:g}",
                family="score_weight",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=BASE_BUY_CONDITION,
                score_expression=_sector_effect_weighted_score(weight),
                params={
                    "effect_usage": "score_weight",
                    "score_threshold": "",
                    "rank_pct": "",
                    "exposure_min": "",
                    "theme_m20_min": "",
                    "amount_ratio_min": "",
                    "score_weight": weight,
                },
            )
        )
    return cases


def validate_effect_feature_set(*, loaded_items: list[LoadedSymbol], processed_dir: str | Path) -> dict[str, Any]:
    diagnostics = validate_sector_feature_set(loaded_items=loaded_items, processed_dir=processed_dir)
    missing_by_file: list[str] = []
    for item in loaded_items:
        missing = sorted(REQUIRED_EFFECT_COLUMNS - set(item.df.columns))
        if missing:
            missing_by_file.append(f"{item.symbol}: {','.join(missing)}")
        if len(missing_by_file) >= 5:
            break
    if missing_by_file:
        raise ValueError("板块效应选股网格缺少必要字段：" + "；".join(missing_by_file))
    diagnostics["sector_effect_required_columns"] = sorted(REQUIRED_EFFECT_COLUMNS)
    return diagnostics


def _common_signal_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "start_date": args.start_date,
        "end_date": args.end_date,
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


def _common_account_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        **_common_signal_kwargs(args),
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
    fill_rate = float(row.get("signal_topn_fill_rate") or 0.0)
    activity_bonus = min(buy_count / 120.0, 1.0) * 0.08
    return account_return * 1.1 + signal_median * 2.0 + account_win_rate * 0.2 + fill_rate * 0.05 + activity_bonus - account_drawdown * 0.8


def _risk_note(row: dict[str, Any]) -> str:
    notes: list[str] = []
    buy_count = int(row.get("account_buy_count") or 0)
    drawdown = float(row.get("account_max_drawdown") or 0.0)
    total_return = float(row.get("account_total_return") or 0.0)
    median_return = float(row.get("signal_median_trade_return") or 0.0)
    fill_rate = float(row.get("signal_topn_fill_rate") or 0.0)
    if buy_count < 80:
        notes.append("交易次数偏少")
    if drawdown > 0.12:
        notes.append("账户回撤偏高")
    if total_return <= 0:
        notes.append("账户收益为负")
    if median_return <= 0:
        notes.append("信号中位收益不佳")
    if fill_rate < 0.5:
        notes.append("TopN填满率偏低")
    return "；".join(notes) if notes else "通过基础风险筛选"


def _summarize_case(
    *,
    case: SectorEffectCase,
    signal_result: dict[str, Any],
    account_result: dict[str, Any],
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


def _render_report(summary_df: pd.DataFrame, args: argparse.Namespace, out_dir: Path) -> str:
    ranked = summary_df.sort_values(["grid_score", "account_total_return", "account_max_drawdown"], ascending=[False, False, True]).reset_index(drop=True)
    best = ranked.head(args.report_top_k)
    lines = [
        "# 板块效应选股条件探索报告",
        "",
        f"- 回测区间：{args.start_date} 至 {args.end_date}",
        f"- 基准目录：`{args.base_processed_dir}`",
        f"- 板块增强目录：`{args.sector_processed_dir}`",
        f"- TopN：`{args.top_n}`；买入偏移：`T+{args.entry_offset}`；固定卖出偏移：`T+{args.exit_offset}`；最短/最长持有：`{args.min_hold_days}/{args.max_hold_days}`",
        "",
        "## 网格范围",
        "",
        f"- 主题强度阈值：`{args.score_thresholds}`",
        f"- 主题排名百分位阈值：`{args.rank_pcts}`",
        f"- 个股暴露分阈值：`{args.exposure_mins}`",
        f"- 主题 20 日动量阈值：`{args.theme_m20_mins}`",
        f"- 主题成交额放大阈值：`{args.amount_ratio_mins}`",
        f"- 板块效应评分权重：`{args.score_weights}`",
        "",
        "## Top 结果",
        "",
        "| 排名 | 策略 | 家族 | 强度阈值 | 排名阈值 | 暴露阈值 | m20阈值 | 成交额阈值 | 权重 | 账户收益 | 年化 | 回撤 | 买入次数 | 账户胜率 | 信号中位 | grid_score | 风险提示 |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for idx, row in best.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx + 1),
                    str(row["case"]),
                    str(row["family"]),
                    str(row.get("param_score_threshold", "")),
                    str(row.get("param_rank_pct", "")),
                    str(row.get("param_exposure_min", "")),
                    str(row.get("param_theme_m20_min", "")),
                    str(row.get("param_amount_ratio_min", "")),
                    str(row.get("param_score_weight", "")),
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

    baseline = summary_df[summary_df["family"] == "baseline"]
    if not baseline.empty and not ranked.empty:
        base = baseline.iloc[0]
        top = ranked.iloc[0]
        lines.extend(
            [
                "",
                "## 基准对照",
                "",
                f"- 基准账户收益：{_pct(base.get('account_total_return'))}，回撤：{_pct(base.get('account_max_drawdown'))}，买入次数：{int(base.get('account_buy_count') or 0)}，信号中位：{_pct(base.get('signal_median_trade_return'))}。",
                f"- 本轮 Top 策略 `{top['case']}` 账户收益：{_pct(top.get('account_total_return'))}，回撤：{_pct(top.get('account_max_drawdown'))}，买入次数：{int(top.get('account_buy_count') or 0)}，信号中位：{_pct(top.get('signal_median_trade_return'))}。",
                "",
                "如果某组条件收益提高但信号中位收益变差，说明它更依赖少数大盈利；如果收益略降但中位收益、胜率和回撤改善，可以作为保守观察账户候选。",
            ]
        )

    lines.extend(
        [
            "",
            "## 输出文件",
            "",
            f"- 汇总表：`{(out_dir / 'sector_effect_grid_summary.csv').as_posix()}`",
            f"- 买卖记录：`{(out_dir / 'sector_effect_grid_trade_records.csv').as_posix()}`",
            f"- 参数配置：`{(out_dir / 'sector_effect_grid_config.json').as_posix()}`",
        ]
    )
    return "\n".join(lines) + "\n"


TRADE_META_COLUMNS = [
    "case",
    "family",
    "buy_condition",
    "score_expression",
    "param_effect_usage",
    "param_score_threshold",
    "param_rank_pct",
    "param_exposure_min",
    "param_theme_m20_min",
    "param_amount_ratio_min",
    "param_score_weight",
]


def _case_trade_frame(case: SectorEffectCase, trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    trades = trades.copy()
    trades.insert(0, "case", case.name)
    trades.insert(1, "family", case.family)
    trades.insert(2, "buy_condition", case.buy_condition)
    trades.insert(3, "score_expression", case.score_expression)
    for key, value in case.params.items():
        trades[f"param_{key}"] = value
    return trades


def _write_trade_frames(trades_path: Path, trade_frames: list[pd.DataFrame]) -> None:
    frames = [frame for frame in trade_frames if not frame.empty]
    if not frames:
        pd.DataFrame().to_csv(trades_path, index=False, encoding="utf-8-sig")
        return
    combined = pd.concat(frames, ignore_index=True, sort=False)
    ordered_columns = [col for col in TRADE_META_COLUMNS if col in combined.columns]
    ordered_columns.extend(col for col in combined.columns if col not in ordered_columns)
    combined.to_csv(trades_path, columns=ordered_columns, index=False, encoding="utf-8-sig")


def _run_case(
    *,
    case: SectorEffectCase,
    args: argparse.Namespace,
    loaded_by_profile: dict[str, tuple[list[LoadedSymbol], dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    profile_key = "sector" if case.data_profile == "sector" else "auto"
    loaded, diagnostics = loaded_by_profile[profile_key]
    signal_req = SignalQualityRequest(
        processed_dir=case.processed_dir,
        data_profile=case.data_profile,
        buy_condition=case.buy_condition,
        score_expression=case.score_expression,
        **_common_signal_kwargs(args),
    )
    signal_result = run_signal_quality_loaded(loaded, diagnostics, signal_req)
    account_req = BacktestRequest(
        processed_dir=case.processed_dir,
        data_profile=case.data_profile,
        buy_condition=case.buy_condition,
        score_expression=case.score_expression,
        **_common_account_kwargs(args),
    )
    account_result = run_portfolio_backtest_loaded(loaded, diagnostics, account_req)
    return signal_result, account_result


def run_effect_grid(args: argparse.Namespace) -> Path:
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = build_sector_effect_cases(
        base_processed_dir=args.base_processed_dir,
        sector_processed_dir=args.sector_processed_dir,
        score_thresholds=_parse_float_list(args.score_thresholds),
        rank_pcts=_parse_float_list(args.rank_pcts),
        exposure_mins=_parse_float_list(args.exposure_mins),
        theme_m20_mins=_parse_optional_float_list(args.theme_m20_mins),
        amount_ratio_mins=_parse_optional_float_list(args.amount_ratio_mins),
        score_weights=_parse_float_list(args.score_weights),
        include_baseline=not args.no_baseline,
    )

    base_loaded, base_diagnostics = load_processed_folder(args.base_processed_dir)
    base_diagnostics["data_profile"] = "base"
    sector_loaded, sector_diagnostics = load_processed_folder(args.sector_processed_dir)
    sector_diagnostics.update(validate_effect_feature_set(loaded_items=sector_loaded, processed_dir=sector_diagnostics["processed_dir"]))
    loaded_by_profile = {
        "auto": (base_loaded, base_diagnostics),
        "sector": (sector_loaded, sector_diagnostics),
    }

    summary_path = out_dir / "sector_effect_grid_summary.csv"
    trades_path = out_dir / "sector_effect_grid_trade_records.csv"
    config_path = out_dir / "sector_effect_grid_config.json"
    report_path = out_dir / "sector_effect_grid_report.md"
    completed_cases: set[str] = set()
    summary_rows: list[dict[str, Any]] = []
    trade_frames: list[pd.DataFrame] = []
    if args.resume and summary_path.exists() and summary_path.stat().st_size > 0:
        existing = pd.read_csv(summary_path, encoding="utf-8-sig")
        summary_rows = existing.to_dict("records")
        completed_cases = set(existing["case"].dropna().astype(str).tolist()) if "case" in existing.columns else set()
        if not args.skip_trade_records and trades_path.exists() and trades_path.stat().st_size > 0:
            try:
                existing_trades = pd.read_csv(trades_path, encoding="utf-8-sig")
            except pd.errors.ParserError as exc:
                raise ValueError(f"已有买卖记录文件列不一致，无法安全续跑，请更换 out-dir 或删除旧文件: {trades_path}") from exc
            if not existing_trades.empty:
                trade_frames.append(existing_trades)

    config_path.write_text(
        json.dumps(
            {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "args": vars(args),
                "case_count": len(cases),
                "cases": [asdict(case) for case in cases],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    new_run_count = 0
    for idx, case in enumerate(cases, start=1):
        if case.name in completed_cases:
            print(f"[{idx}/{len(cases)}] 跳过已完成 {case.name}", flush=True)
            continue
        if args.max_runs > 0 and new_run_count >= args.max_runs:
            print(f"已达到本批上限 {args.max_runs}，保留中间结果并退出", flush=True)
            break
        print(f"[{idx}/{len(cases)}] {case.name}", flush=True)
        signal_result, account_result = _run_case(case=case, args=args, loaded_by_profile=loaded_by_profile)
        if not args.skip_trade_records:
            trade_frame = _case_trade_frame(case, pd.DataFrame(account_result.get("trade_rows", [])))
            if not trade_frame.empty:
                trade_frames.append(trade_frame)
                _write_trade_frames(trades_path, trade_frames)
        summary_rows.append(_summarize_case(case=case, signal_result=signal_result, account_result=account_result))
        new_run_count += 1
        pd.DataFrame(summary_rows).to_csv(summary_path, index=False, encoding="utf-8-sig")

    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(["grid_score", "account_total_return", "account_max_drawdown"], ascending=[False, False, True])
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    if not args.skip_trade_records:
        _write_trade_frames(trades_path, trade_frames)
    report_path.write_text(_render_report(summary_df, args, out_dir), encoding="utf-8")
    print(f"板块效应选股条件探索完成：{out_dir.as_posix()}")
    return out_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="探索优先选择有板块效应股票的买入过滤与评分加权条件")
    parser.add_argument("--base-processed-dir", default="data_bundle/processed_qfq_theme_focus_top100")
    parser.add_argument("--sector-processed-dir", default="data_bundle/processed_qfq_theme_focus_top100_sector")
    parser.add_argument("--start-date", default="20230101")
    parser.add_argument("--end-date", default="20260429")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--score-thresholds", default="0.4,0.5")
    parser.add_argument("--rank-pcts", default="0.5,0.7")
    parser.add_argument("--exposure-mins", default="0,0.3")
    parser.add_argument("--theme-m20-mins", default="any,0")
    parser.add_argument("--amount-ratio-mins", default="any,1.0")
    parser.add_argument("--score-weights", default="5,10,15")
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
    parser.add_argument("--no-baseline", action="store_true")
    parser.add_argument("--skip-trade-records", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-runs", type=int, default=0, help="单次最多新增运行多少个组合，0 表示不限制")
    parser.add_argument("--report-top-k", type=int, default=12)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    run_effect_grid(parse_args(argv))


if __name__ == "__main__":
    main()
