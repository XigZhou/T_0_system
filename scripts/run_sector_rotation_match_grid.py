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
from scripts.run_sector_effect_grid import _risk_note
from scripts.run_sector_parameter_grid import BASE_BUY_CONDITION, BASE_SCORE_EXPRESSION, SELL_CONDITION
from scripts.run_sector_rotation_grid import load_rotation_daily, merge_rotation_features


SECTOR_CANDIDATE_FILTER = "sector_exposure_score>0,sector_strongest_theme_score>=0.4,sector_strongest_theme_rank_pct<=0.7"
SECTOR_CANDIDATE_NAME = "板块候选_score0.4_rank0.7"
PICK_FEATURE_COLUMNS = [
    "rotation_state",
    "rotation_top_theme",
    "rotation_top_cluster",
    "rotation_is_new_start",
    "stock_theme_cluster",
    "stock_matches_rotation_top_theme",
    "stock_matches_rotation_top_cluster",
]


@dataclass(frozen=True)
class RotationMatchCase:
    name: str
    family: str
    processed_dir: str
    data_profile: str
    buy_condition: str
    score_expression: str
    params: dict[str, Any]


def _default_out_dir() -> Path:
    return Path("research_runs") / f"{datetime.now():%Y%m%d_%H%M%S}_sector_rotation_match_grid"


def _parse_float_list(raw_text: str) -> list[float]:
    values = [float(token.strip()) for token in str(raw_text).split(",") if token.strip()]
    if not values:
        raise ValueError("参数列表不能为空")
    return values


def _sector_candidate_condition(*extra_parts: str) -> str:
    parts = [BASE_BUY_CONDITION, SECTOR_CANDIDATE_FILTER]
    parts.extend(part for part in extra_parts if str(part or "").strip())
    return ",".join(parts)


def _rotation_match_score(*, cluster_weight: float, theme_weight: float, new_start_penalty: float) -> str:
    penalty_part = ""
    if new_start_penalty:
        penalty_part = f" - rotation_is_new_start * (1 - stock_matches_rotation_top_cluster) * {new_start_penalty:g}"
    return (
        f"{BASE_SCORE_EXPRESSION} "
        f"+ stock_matches_rotation_top_cluster * {cluster_weight:g} "
        f"+ stock_matches_rotation_top_theme * {theme_weight:g}"
        f"{penalty_part}"
    )


def build_rotation_match_cases(
    *,
    base_processed_dir: str,
    sector_processed_dir: str,
    cluster_weights: list[float],
    theme_weights: list[float],
    penalty_weights: list[float],
    include_baseline: bool = True,
) -> list[RotationMatchCase]:
    cases: list[RotationMatchCase] = []
    if include_baseline:
        cases.append(
            RotationMatchCase(
                name="基准动量",
                family="baseline",
                processed_dir=base_processed_dir,
                data_profile="auto",
                buy_condition=BASE_BUY_CONDITION,
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_match_usage": "none", "cluster_weight": 0.0, "theme_weight": 0.0, "new_start_penalty": 0.0},
            )
        )

    cases.extend(
        [
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
                name="候选_避开新能源主线",
                family="rotation_cluster_guard",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition("rotation_top_cluster!=新能源"),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_match_usage": "avoid_new_energy", "cluster_weight": 0.0, "theme_weight": 0.0, "new_start_penalty": 0.0},
            ),
            RotationMatchCase(
                name="候选_股票匹配主线簇",
                family="rotation_match_filter",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition("stock_matches_rotation_top_cluster>0"),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_match_usage": "cluster_filter", "cluster_weight": 0.0, "theme_weight": 0.0, "new_start_penalty": 0.0},
            ),
            RotationMatchCase(
                name="候选_股票匹配Top主题",
                family="rotation_match_filter",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition("stock_matches_rotation_top_theme>0"),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_match_usage": "theme_filter", "cluster_weight": 0.0, "theme_weight": 0.0, "new_start_penalty": 0.0},
            ),
        ]
    )

    for weight in cluster_weights:
        cases.append(
            RotationMatchCase(
                name=f"主线簇匹配加权_w{weight:g}",
                family="rotation_match_score",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition(),
                score_expression=_rotation_match_score(cluster_weight=weight, theme_weight=0.0, new_start_penalty=0.0),
                params={"rotation_match_usage": "cluster_score", "cluster_weight": weight, "theme_weight": 0.0, "new_start_penalty": 0.0},
            )
        )

    for weight in theme_weights:
        cases.append(
            RotationMatchCase(
                name=f"Top主题匹配加权_w{weight:g}",
                family="rotation_match_score",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition(),
                score_expression=_rotation_match_score(cluster_weight=0.0, theme_weight=weight, new_start_penalty=0.0),
                params={"rotation_match_usage": "theme_score", "cluster_weight": 0.0, "theme_weight": weight, "new_start_penalty": 0.0},
            )
        )

    for cluster_weight in cluster_weights:
        for theme_weight in theme_weights:
            cases.append(
                RotationMatchCase(
                    name=f"主线匹配组合加权_c{cluster_weight:g}_t{theme_weight:g}",
                    family="rotation_match_score",
                    processed_dir=sector_processed_dir,
                    data_profile="sector",
                    buy_condition=_sector_candidate_condition(),
                    score_expression=_rotation_match_score(cluster_weight=cluster_weight, theme_weight=theme_weight, new_start_penalty=0.0),
                    params={"rotation_match_usage": "cluster_theme_score", "cluster_weight": cluster_weight, "theme_weight": theme_weight, "new_start_penalty": 0.0},
                )
            )

    for penalty in penalty_weights:
        cases.append(
            RotationMatchCase(
                name=f"主线匹配加权_新启动惩罚_p{penalty:g}",
                family="rotation_match_score",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition(),
                score_expression=_rotation_match_score(
                    cluster_weight=max(cluster_weights) if cluster_weights else 0.0,
                    theme_weight=max(theme_weights) if theme_weights else 0.0,
                    new_start_penalty=penalty,
                ),
                params={
                    "rotation_match_usage": "cluster_theme_score_with_new_start_penalty",
                    "cluster_weight": max(cluster_weights) if cluster_weights else 0.0,
                    "theme_weight": max(theme_weights) if theme_weights else 0.0,
                    "new_start_penalty": penalty,
                },
            )
        )
    return cases


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
    overlap = row.get("pick_overlap_rate_vs_sector_candidate")
    overlap_penalty = 0.0
    if overlap not in (None, ""):
        overlap_penalty = max(0.0, 1.0 - float(overlap)) * 0.02
    activity_bonus = min(buy_count / 120.0, 1.0) * 0.08
    return account_return * 1.1 + signal_median * 2.0 + account_win_rate * 0.2 + fill_rate * 0.05 + activity_bonus - account_drawdown * 0.8 - overlap_penalty


def _case_context_frame(case: RotationMatchCase, frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    out.insert(0, "case", case.name)
    out.insert(1, "family", case.family)
    out.insert(2, "buy_condition", case.buy_condition)
    out.insert(3, "score_expression", case.score_expression)
    for key, value in case.params.items():
        out[f"param_{key}"] = value
    return out


def _build_pick_feature_lookup(loaded: list[LoadedSymbol]) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for item in loaded:
        columns = [column for column in PICK_FEATURE_COLUMNS if column in item.df.columns]
        if not columns:
            continue
        for _, row in item.df[["trade_date", *columns]].iterrows():
            lookup[(item.symbol, str(row["trade_date"]))] = {column: row.get(column) for column in columns}
    return lookup


def _enrich_pick_features(frame: pd.DataFrame, feature_lookup: dict[tuple[str, str], dict[str, Any]]) -> pd.DataFrame:
    if frame.empty or not feature_lookup or "symbol" not in frame.columns or "signal_date" not in frame.columns:
        return frame
    out = frame.copy()
    enriched_rows: list[dict[str, Any]] = []
    for _, row in out.iterrows():
        enriched_rows.append(feature_lookup.get((str(row["symbol"]), str(row["signal_date"])), {}))
    enriched = pd.DataFrame(enriched_rows)
    if enriched.empty:
        return out
    for column in enriched.columns:
        out[column] = enriched[column]
    return out


def _write_frames(path: Path, frames: list[pd.DataFrame]) -> None:
    usable = [frame for frame in frames if not frame.empty]
    if not usable:
        pd.DataFrame().to_csv(path, index=False, encoding="utf-8-sig")
        return
    combined = pd.concat(usable, ignore_index=True, sort=False)
    combined.to_csv(path, index=False, encoding="utf-8-sig")


def _pick_signature(frame: pd.DataFrame) -> set[tuple[str, str]]:
    if frame.empty or "signal_date" not in frame.columns or "symbol" not in frame.columns:
        return set()
    return set(zip(frame["signal_date"].astype(str), frame["symbol"].astype(str)))


def _append_pick_overlap(summary_rows: list[dict[str, Any]], pick_frames: list[pd.DataFrame]) -> list[dict[str, Any]]:
    if not pick_frames:
        return summary_rows
    picks = pd.concat([frame for frame in pick_frames if not frame.empty], ignore_index=True, sort=False)
    signatures = {
        str(case): _pick_signature(group)
        for case, group in picks.groupby("case")
    }
    candidate_signature = signatures.get(SECTOR_CANDIDATE_NAME, set())
    out: list[dict[str, Any]] = []
    for row in summary_rows:
        row = dict(row)
        signature = signatures.get(str(row.get("case")), set())
        if candidate_signature:
            row["pick_overlap_rate_vs_sector_candidate"] = round(len(signature & candidate_signature) / len(candidate_signature), 6)
            row["pick_changed_count_vs_sector_candidate"] = len(signature.symmetric_difference(candidate_signature))
        else:
            row["pick_overlap_rate_vs_sector_candidate"] = ""
            row["pick_changed_count_vs_sector_candidate"] = ""
        row["grid_score"] = round(_score_case(row), 6)
        out.append(row)
    return out


def _summarize_case(
    *,
    case: RotationMatchCase,
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
    row["pick_overlap_rate_vs_sector_candidate"] = ""
    row["pick_changed_count_vs_sector_candidate"] = ""
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
    lines = [
        "# 股票匹配主线轮动 TopN 网格报告",
        "",
        f"- 回测区间：{args.start_date} 至 {args.end_date}",
        f"- 轮动日频文件：`{args.rotation_daily_path}`",
        f"- 基准目录：`{args.base_processed_dir}`",
        f"- 板块增强目录：`{args.sector_processed_dir}`",
        "- 本报告只研究股票是否匹配当日主线对 TopN 的影响，不修改模拟账户。",
        "",
        "## Top 结果",
        "",
        "| 排名 | 策略 | 家族 | 用法 | 账户收益 | 年化 | 回撤 | 买入次数 | 胜率 | 信号中位 | TopN重合率 | grid_score | 风险提示 |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for idx, row in ranked.head(args.report_top_k).iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx + 1),
                    str(row["case"]),
                    str(row["family"]),
                    str(row.get("param_rotation_match_usage", "")),
                    _pct(row.get("account_total_return")),
                    _pct(row.get("account_annualized_return")),
                    _pct(row.get("account_max_drawdown")),
                    str(int(row.get("account_buy_count") or 0)),
                    _pct(row.get("account_win_rate")),
                    _pct(row.get("signal_median_trade_return")),
                    _pct(row.get("pick_overlap_rate_vs_sector_candidate")),
                    _num(row.get("grid_score"), 4),
                    str(row.get("risk_note") or ""),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 输出文件",
            "",
            f"- 汇总表：`{(out_dir / 'sector_rotation_match_grid_summary.csv').as_posix()}`",
            f"- 买卖记录：`{(out_dir / 'sector_rotation_match_grid_trade_records.csv').as_posix()}`",
            f"- 入选记录：`{(out_dir / 'sector_rotation_match_grid_pick_records.csv').as_posix()}`",
            f"- 参数配置：`{(out_dir / 'sector_rotation_match_grid_config.json').as_posix()}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _run_case(
    *,
    case: RotationMatchCase,
    args: argparse.Namespace,
    loaded_by_profile: dict[str, tuple[list[LoadedSymbol], dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    profile_key = "baseline" if case.family == "baseline" else "sector"
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


def run_rotation_match_grid(args: argparse.Namespace) -> Path:
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = build_rotation_match_cases(
        base_processed_dir=args.base_processed_dir,
        sector_processed_dir=args.sector_processed_dir,
        cluster_weights=_parse_float_list(args.cluster_weights),
        theme_weights=_parse_float_list(args.theme_weights),
        penalty_weights=_parse_float_list(args.penalty_weights),
        include_baseline=not args.no_baseline,
    )

    base_loaded, base_diagnostics = load_processed_folder(args.base_processed_dir)
    base_diagnostics["data_profile"] = "base"
    sector_loaded, sector_diagnostics = load_processed_folder(args.sector_processed_dir)
    sector_diagnostics.update(validate_sector_feature_set(loaded_items=sector_loaded, processed_dir=sector_diagnostics["processed_dir"]))
    rotation_daily = load_rotation_daily(args.rotation_daily_path)
    rotation_loaded = merge_rotation_features(sector_loaded, rotation_daily)
    rotation_diagnostics = dict(sector_diagnostics)
    rotation_diagnostics["rotation_daily_path"] = str(Path(args.rotation_daily_path))
    rotation_diagnostics["rotation_match_feature_enabled"] = True
    loaded_by_profile = {
        "baseline": (base_loaded, base_diagnostics),
        "sector": (rotation_loaded, rotation_diagnostics),
    }
    pick_feature_lookup = _build_pick_feature_lookup(rotation_loaded)

    summary_path = out_dir / "sector_rotation_match_grid_summary.csv"
    trades_path = out_dir / "sector_rotation_match_grid_trade_records.csv"
    picks_path = out_dir / "sector_rotation_match_grid_pick_records.csv"
    config_path = out_dir / "sector_rotation_match_grid_config.json"
    report_path = out_dir / "sector_rotation_match_grid_report.md"
    summary_rows: list[dict[str, Any]] = []
    trade_frames: list[pd.DataFrame] = []
    pick_frames: list[pd.DataFrame] = []

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

    for idx, case in enumerate(cases, start=1):
        if args.max_runs > 0 and len(summary_rows) >= args.max_runs:
            print(f"已达到本批上限 {args.max_runs}，保留中间结果并退出", flush=True)
            break
        print(f"[{idx}/{len(cases)}] {case.name}", flush=True)
        signal_result, account_result = _run_case(case=case, args=args, loaded_by_profile=loaded_by_profile)
        summary_rows.append(_summarize_case(case=case, signal_result=signal_result, account_result=account_result))
        if not args.skip_trade_records:
            trade_frame = _case_context_frame(case, pd.DataFrame(account_result.get("trade_rows", [])))
            if not trade_frame.empty:
                trade_frames.append(trade_frame)
                _write_frames(trades_path, trade_frames)
        pick_frame = _enrich_pick_features(pd.DataFrame(account_result.get("pick_rows", [])), pick_feature_lookup)
        pick_frame = _case_context_frame(case, pick_frame)
        if not pick_frame.empty:
            pick_frames.append(pick_frame)
            _write_frames(picks_path, pick_frames)
        interim_rows = _append_pick_overlap(summary_rows, pick_frames)
        pd.DataFrame(interim_rows).to_csv(summary_path, index=False, encoding="utf-8-sig")

    summary_rows = _append_pick_overlap(summary_rows, pick_frames)
    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(["grid_score", "account_total_return", "account_max_drawdown"], ascending=[False, False, True])
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    if not args.skip_trade_records:
        _write_frames(trades_path, trade_frames)
    _write_frames(picks_path, pick_frames)
    report_path.write_text(_render_report(summary_df, args, out_dir), encoding="utf-8")
    print(f"股票匹配主线轮动 TopN 网格完成：{out_dir.as_posix()}")
    return out_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="探索股票是否匹配当日主线对板块候选 TopN 排序的影响")
    parser.add_argument("--base-processed-dir", default="data_bundle/processed_qfq_theme_focus_top100")
    parser.add_argument("--sector-processed-dir", default="data_bundle/processed_qfq_theme_focus_top100_sector")
    parser.add_argument("--rotation-daily-path", default="research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv")
    parser.add_argument("--start-date", default="20230101")
    parser.add_argument("--end-date", default="20260429")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--cluster-weights", default="5,10")
    parser.add_argument("--theme-weights", default="8,12")
    parser.add_argument("--penalty-weights", default="5,8")
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
    parser.add_argument("--max-runs", type=int, default=0, help="单次最多运行多少个组合，0 表示不限制")
    parser.add_argument("--report-top-k", type=int, default=12)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    run_rotation_match_grid(parse_args(argv))


if __name__ == "__main__":
    main()
