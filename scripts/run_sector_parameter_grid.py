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

from overnight_bt.backtest import load_processed_folder, run_portfolio_backtest_loaded
from overnight_bt.models import BacktestRequest, SignalQualityRequest
from overnight_bt.sector_features import validate_sector_feature_set
from overnight_bt.signal_quality import run_signal_quality_loaded


BASE_BUY_CONDITION = "m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02"
SELL_CONDITION = "m20<0.08,hs300_m20<0.02"
BASE_SCORE_EXPRESSION = (
    "m20 * 140 + (m20 - m60 / 3) * 90 + (m20 - m120 / 6) * 40 "
    "- abs(m5 - 0.03) * 55 - abs(m10 - 0.08) * 30"
)


@dataclass(frozen=True)
class SectorGridCase:
    name: str
    family: str
    processed_dir: str
    data_profile: str
    buy_condition: str
    score_expression: str
    params: dict[str, Any]


def _parse_float_list(raw_text: str) -> list[float]:
    values = [float(token.strip()) for token in str(raw_text).split(",") if token.strip()]
    if not values:
        raise ValueError("参数列表不能为空")
    return values


def _default_out_dir() -> Path:
    return Path("research_runs") / f"{datetime.now():%Y%m%d_%H%M%S}_sector_parameter_grid"


def _sector_filter_condition(score_threshold: float, rank_pct: float, *, include_exposure: bool = True) -> str:
    parts = [BASE_BUY_CONDITION]
    if include_exposure:
        parts.append("sector_exposure_score>0")
    parts.extend(
        [
            f"sector_strongest_theme_score>={score_threshold:g}",
            f"sector_strongest_theme_rank_pct<={rank_pct:g}",
        ]
    )
    return ",".join(parts)


def _sector_weighted_score(weight: float) -> str:
    exposure_weight = max(weight / 3.0, 1.0)
    rank_penalty = max(weight / 2.0, 1.0)
    return (
        f"{BASE_SCORE_EXPRESSION} + sector_strongest_theme_score * {weight:g} "
        f"+ sector_exposure_score * {exposure_weight:g} "
        f"- sector_strongest_theme_rank_pct * {rank_penalty:g}"
    )


def build_sector_grid_cases(
    *,
    base_processed_dir: str,
    sector_processed_dir: str,
    score_thresholds: list[float],
    rank_pcts: list[float],
    weights: list[float],
    include_baseline: bool = True,
) -> list[SectorGridCase]:
    cases: list[SectorGridCase] = []
    if include_baseline:
        cases.append(
            SectorGridCase(
                name="基准动量",
                family="baseline",
                processed_dir=base_processed_dir,
                data_profile="auto",
                buy_condition=BASE_BUY_CONDITION,
                score_expression=BASE_SCORE_EXPRESSION,
                params={},
            )
        )

    for score_threshold in score_thresholds:
        for rank_pct in rank_pcts:
            cases.append(
                SectorGridCase(
                    name=f"硬过滤_score{score_threshold:g}_rank{rank_pct:g}",
                    family="hard_filter",
                    processed_dir=sector_processed_dir,
                    data_profile="sector",
                    buy_condition=_sector_filter_condition(score_threshold, rank_pct),
                    score_expression=BASE_SCORE_EXPRESSION,
                    params={
                        "score_threshold": score_threshold,
                        "rank_pct": rank_pct,
                        "score_weight": 0.0,
                        "hard_filter": True,
                    },
                )
            )

    for weight in weights:
        cases.append(
            SectorGridCase(
                name=f"只评分_weight{weight:g}",
                family="score_only",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=BASE_BUY_CONDITION,
                score_expression=_sector_weighted_score(weight),
                params={
                    "score_threshold": "",
                    "rank_pct": "",
                    "score_weight": weight,
                    "hard_filter": False,
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


def _case_key(row: dict[str, Any]) -> tuple[int, float, float, int]:
    return (
        int(row.get("account_total_return", 0.0) > 0),
        float(row.get("account_total_return", 0.0)),
        -float(row.get("account_max_drawdown", 1.0)),
        int(row.get("account_buy_count", 0)),
    )


def _score_case(row: dict[str, Any]) -> float:
    account_return = float(row.get("account_total_return") or 0.0)
    signal_median = float(row.get("signal_median_trade_return") or 0.0)
    signal_win_rate = float(row.get("signal_win_rate") or 0.0)
    account_drawdown = float(row.get("account_max_drawdown") or 0.0)
    buy_count = float(row.get("account_buy_count") or 0.0)
    fill_rate = float(row.get("signal_topn_fill_rate") or 0.0)
    activity_bonus = min(buy_count / 120.0, 1.0) * 0.08
    return account_return * 1.2 + signal_median * 1.5 + signal_win_rate * 0.2 + fill_rate * 0.08 + activity_bonus - account_drawdown * 0.8


def _summarize_case(
    *,
    case: SectorGridCase,
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


def _risk_note(row: dict[str, Any]) -> str:
    buy_count = int(row.get("account_buy_count") or 0)
    drawdown = float(row.get("account_max_drawdown") or 0.0)
    total_return = float(row.get("account_total_return") or 0.0)
    median_return = float(row.get("signal_median_trade_return") or 0.0)
    notes: list[str] = []
    if buy_count < 80:
        notes.append("交易次数偏少")
    if drawdown > 0.12:
        notes.append("账户回撤偏高")
    if total_return <= 0:
        notes.append("账户收益为负")
    if median_return <= 0:
        notes.append("信号中位收益不佳")
    return "；".join(notes) if notes else "通过基础风险筛选"


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


def _render_report(
    *,
    summary_df: pd.DataFrame,
    args: argparse.Namespace,
    out_dir: Path,
) -> str:
    ranked = summary_df.sort_values(
        ["grid_score", "account_total_return", "account_max_drawdown"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    best = ranked.head(args.report_top_k)
    lines = [
        "# 板块参数网格探索报告",
        "",
        f"- 回测区间：{args.start_date} 至 {args.end_date}",
        f"- 基准目录：`{args.base_processed_dir}`",
        f"- 板块增强目录：`{args.sector_processed_dir}`",
        f"- TopN：`{args.top_n}`；买入偏移：`T+{args.entry_offset}`；固定卖出偏移：`T+{args.exit_offset}`；最短/最长持有：`{args.min_hold_days}/{args.max_hold_days}`",
        f"- 交易成本：买入费率 `{args.buy_fee_rate}`，卖出费率 `{args.sell_fee_rate}`，滑点 `{args.slippage_bps}` bps，无最低佣金时填 `0`。",
        "",
        "## 网格范围",
        "",
        f"- 主题强度阈值：`{args.score_thresholds}`",
        f"- 主题排名百分位阈值：`{args.rank_pcts}`",
        f"- 只评分加权权重：`{args.score_weights}`",
        "- 家族说明：`hard_filter` 表示把板块强度写进买入过滤；`score_only` 表示不做板块硬过滤，只把板块强度加入评分。",
        "",
        "## 推荐排序口径",
        "",
        "- `grid_score` 综合账户收益、信号中位收益、胜率、活跃度、TopN填满率并惩罚账户回撤。",
        "- 排名不是最终实盘建议，先用来缩小候选范围；正式进入模拟账户前还要看交易明细和最近一年表现。",
        "",
        "## Top 结果",
        "",
        "| 排名 | 策略 | 家族 | 强度阈值 | 排名阈值 | 权重 | 账户收益 | 年化 | 回撤 | 买入次数 | 账户胜率 | 信号中位 | grid_score | 风险提示 |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
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
    if not baseline.empty:
        base = baseline.iloc[0]
        lines.extend(
            [
                "",
                "## 基准对照",
                "",
                f"- 基准账户收益：{_pct(base.get('account_total_return'))}",
                f"- 基准账户回撤：{_pct(base.get('account_max_drawdown'))}",
                f"- 基准买入次数：{int(base.get('account_buy_count') or 0)}",
                "",
                "如果某个板块组合的收益没有接近基准，同时交易次数明显减少，只能说明它降低了活跃度，不能说明增强有效。",
            ]
        )

    lines.extend(
        [
            "",
            "## 输出文件",
            "",
            f"- 汇总表：`{(out_dir / 'sector_parameter_grid_summary.csv').as_posix()}`",
            f"- 买卖记录：`{(out_dir / 'sector_parameter_grid_trade_records.csv').as_posix()}`",
            f"- 参数配置：`{(out_dir / 'sector_parameter_grid_config.json').as_posix()}`",
        ]
    )
    return "\n".join(lines) + "\n"


def run_grid(args: argparse.Namespace) -> Path:
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    score_thresholds = _parse_float_list(args.score_thresholds)
    rank_pcts = _parse_float_list(args.rank_pcts)
    weights = _parse_float_list(args.score_weights)
    cases = build_sector_grid_cases(
        base_processed_dir=args.base_processed_dir,
        sector_processed_dir=args.sector_processed_dir,
        score_thresholds=score_thresholds,
        rank_pcts=rank_pcts,
        weights=weights,
        include_baseline=not args.no_baseline,
    )

    base_loaded, base_diagnostics = load_processed_folder(args.base_processed_dir)
    base_diagnostics["data_profile"] = "base"
    sector_loaded, sector_diagnostics = load_processed_folder(args.sector_processed_dir)
    sector_diagnostics.update(
        validate_sector_feature_set(
            loaded_items=sector_loaded,
            processed_dir=sector_diagnostics["processed_dir"],
        )
    )
    loaded_by_profile = {
        "auto": (base_loaded, base_diagnostics),
        "sector": (sector_loaded, sector_diagnostics),
    }

    summary_rows: list[dict[str, Any]] = []
    trade_frames: list[pd.DataFrame] = []
    summary_path = out_dir / "sector_parameter_grid_summary.csv"
    trades_path = out_dir / "sector_parameter_grid_trade_records.csv"
    config_path = out_dir / "sector_parameter_grid_config.json"
    report_path = out_dir / "sector_parameter_grid_report.md"

    config_payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "args": vars(args),
        "case_count": len(cases),
        "cases": [asdict(case) for case in cases],
    }
    config_path.write_text(json.dumps(config_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    for idx, case in enumerate(cases, start=1):
        print(f"[{idx}/{len(cases)}] {case.name}", flush=True)
        loaded, diagnostics = loaded_by_profile["sector" if case.data_profile == "sector" else "auto"]
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
        summary_rows.append(_summarize_case(case=case, signal_result=signal_result, account_result=account_result))
        pd.DataFrame(summary_rows).to_csv(summary_path, index=False, encoding="utf-8-sig")

        if not args.skip_trade_records:
            trades = pd.DataFrame(account_result.get("trade_rows", []))
            if not trades.empty:
                trades.insert(0, "case", case.name)
                trades.insert(1, "family", case.family)
                trades.insert(2, "buy_condition", case.buy_condition)
                trades.insert(3, "score_expression", case.score_expression)
                trade_frames.append(trades)

    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.sort_values(["grid_score", "account_total_return", "account_max_drawdown"], ascending=[False, False, True])
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    if trade_frames:
        pd.concat(trade_frames, ignore_index=True, sort=False).to_csv(trades_path, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame().to_csv(trades_path, index=False, encoding="utf-8-sig")
    report_path.write_text(_render_report(summary_df=summary_df, args=args, out_dir=out_dir), encoding="utf-8")
    print(f"板块参数网格探索完成：{out_dir.as_posix()}")
    return out_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="探索板块增强参数对回测和信号质量的影响")
    parser.add_argument("--base-processed-dir", default="data_bundle/processed_qfq_theme_focus_top100", help="基准处理后股票 CSV 目录")
    parser.add_argument("--sector-processed-dir", default="data_bundle/processed_qfq_theme_focus_top100_sector", help="板块增强处理后股票 CSV 目录")
    parser.add_argument("--start-date", default="20230101", help="回测开始日期 YYYYMMDD")
    parser.add_argument("--end-date", default="", help="回测结束日期 YYYYMMDD，留空使用数据最新日期")
    parser.add_argument("--out-dir", default="", help="输出目录，留空写入 research_runs/时间戳_sector_parameter_grid")
    parser.add_argument("--score-thresholds", default="0.4,0.5,0.6", help="最强主题分阈值列表")
    parser.add_argument("--rank-pcts", default="0.3,0.5,0.7", help="最强主题排名百分位阈值列表，越小越强")
    parser.add_argument("--score-weights", default="10,20,30", help="只评分加权模式中的板块强度权重列表")
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
    parser.add_argument("--no-baseline", action="store_true", help="不跑基准动量对照")
    parser.add_argument("--skip-trade-records", action="store_true", help="不导出账户回测交易流水")
    parser.add_argument("--report-top-k", type=int, default=10)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    run_grid(parse_args(argv))


if __name__ == "__main__":
    main()
