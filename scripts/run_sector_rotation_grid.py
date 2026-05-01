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
from overnight_bt.rotation_features import ROTATION_NUMERIC_COLUMNS, THEME_CLUSTER_MAP
from overnight_bt.sector_features import validate_sector_feature_set
from overnight_bt.signal_quality import run_signal_quality_loaded
from scripts.run_sector_parameter_grid import BASE_BUY_CONDITION, BASE_SCORE_EXPRESSION, SELL_CONDITION


SECTOR_CANDIDATE_FILTER = "sector_exposure_score>0,sector_strongest_theme_score>=0.4,sector_strongest_theme_rank_pct<=0.7"


@dataclass(frozen=True)
class RotationGridCase:
    name: str
    family: str
    processed_dir: str
    data_profile: str
    buy_condition: str
    score_expression: str
    params: dict[str, Any]


def _default_out_dir() -> Path:
    return Path("research_runs") / f"{datetime.now():%Y%m%d_%H%M%S}_sector_rotation_grid"


def _sector_candidate_condition(*extra_parts: str) -> str:
    parts = [BASE_BUY_CONDITION, SECTOR_CANDIDATE_FILTER]
    parts.extend(part for part in extra_parts if str(part or "").strip())
    return ",".join(parts)


def build_rotation_grid_cases(
    *,
    base_processed_dir: str,
    sector_processed_dir: str,
    include_baseline: bool = True,
) -> list[RotationGridCase]:
    cases: list[RotationGridCase] = []
    if include_baseline:
        cases.append(
            RotationGridCase(
                name="基准动量",
                family="baseline",
                processed_dir=base_processed_dir,
                data_profile="auto",
                buy_condition=BASE_BUY_CONDITION,
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_filter": "none"},
            )
        )
    cases.extend(
        [
            RotationGridCase(
                name="板块候选_score0.4_rank0.7",
                family="sector_candidate",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition(),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_filter": "none"},
            ),
            RotationGridCase(
                name="候选_新主线启动",
                family="rotation_state",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition("rotation_state=新主线启动"),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_filter": "新主线启动"},
            ),
            RotationGridCase(
                name="候选_主线退潮",
                family="rotation_state",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition("rotation_state=主线退潮"),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_filter": "主线退潮"},
            ),
            RotationGridCase(
                name="候选_轮动观察",
                family="rotation_state",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition("rotation_state=轮动观察"),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_filter": "轮动观察"},
            ),
            RotationGridCase(
                name="候选_主线延续",
                family="rotation_state",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition("rotation_state=主线延续"),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_filter": "主线延续"},
            ),
            RotationGridCase(
                name="候选_退潮或观察",
                family="rotation_state_combo",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition("rotation_is_favorable_state>0"),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_filter": "主线退潮或轮动观察"},
            ),
            RotationGridCase(
                name="候选_避开新主线启动",
                family="rotation_state_combo",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition("rotation_is_not_new_start>0"),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_filter": "非新主线启动"},
            ),
            RotationGridCase(
                name="候选_科技成长主线",
                family="rotation_cluster",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition("rotation_top_cluster=科技成长"),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_filter": "科技成长"},
            ),
            RotationGridCase(
                name="候选_科技成长且非新启动",
                family="rotation_cluster_combo",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition("rotation_top_cluster=科技成长", "rotation_is_not_new_start>0"),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_filter": "科技成长且非新主线启动"},
            ),
            RotationGridCase(
                name="候选_科技成长且股票匹配",
                family="rotation_cluster_combo",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition("rotation_top_cluster=科技成长", "stock_matches_rotation_top_cluster>0"),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_filter": "科技成长且股票匹配主线簇"},
            ),
            RotationGridCase(
                name="候选_避开新能源主线",
                family="rotation_cluster_combo",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition("rotation_top_cluster!=新能源"),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_filter": "非新能源主线"},
            ),
            RotationGridCase(
                name="候选_医药防御主线",
                family="rotation_cluster",
                processed_dir=sector_processed_dir,
                data_profile="sector",
                buy_condition=_sector_candidate_condition("rotation_top_cluster=医药防御"),
                score_expression=BASE_SCORE_EXPRESSION,
                params={"rotation_filter": "医药防御"},
            ),
        ]
    )
    return cases


def _as_flag(series: pd.Series, target: str) -> pd.Series:
    return (series.fillna("").astype(str) == target).astype(float)


def load_rotation_daily(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"轮动诊断日频文件不存在: {file_path}")
    frame = pd.read_csv(file_path, dtype={"trade_date": str}, encoding="utf-8-sig")
    missing = {"trade_date", "top_theme", "top_cluster", "rotation_state"} - set(frame.columns)
    if missing:
        raise ValueError(f"轮动诊断日频文件缺少必要字段: {sorted(missing)}")
    frame["trade_date"] = frame["trade_date"].astype(str).str.strip()
    out = pd.DataFrame({"trade_date": frame["trade_date"]})
    rename_map = {
        "top_theme": "rotation_top_theme",
        "top_cluster": "rotation_top_cluster",
        "rotation_state": "rotation_state",
        "second_theme": "rotation_second_theme",
        "top_cluster_by_score": "rotation_top_cluster_by_score",
        "top_score": "rotation_top_score",
        "top_rank_pct": "rotation_top_rank_pct",
        "top_gap": "rotation_top_gap",
        "top_m5": "rotation_top_m5",
        "top_m20": "rotation_top_m20",
        "top_m60": "rotation_top_m60",
        "top_theme_m20": "rotation_top_theme_m20",
        "top_theme_score_chg_5": "rotation_top_theme_score_chg_5",
        "top_theme_score_chg_20": "rotation_top_theme_score_chg_20",
        "top_theme_rank_pct_chg_5": "rotation_top_theme_rank_pct_chg_5",
        "top_theme_run_days": "rotation_top_theme_run_days",
        "top_cluster_run_days": "rotation_top_cluster_run_days",
        "strong_theme_count": "rotation_strong_theme_count",
        "theme_score_dispersion": "rotation_theme_score_dispersion",
    }
    for source, target in rename_map.items():
        if source in frame.columns:
            out[target] = frame[source]

    out["rotation_is_new_start"] = _as_flag(out["rotation_state"], "新主线启动")
    out["rotation_is_main_decline"] = _as_flag(out["rotation_state"], "主线退潮")
    out["rotation_is_watch"] = _as_flag(out["rotation_state"], "轮动观察")
    out["rotation_is_main_extend"] = _as_flag(out["rotation_state"], "主线延续")
    out["rotation_is_no_clear"] = _as_flag(out["rotation_state"], "无明确主线")
    out["rotation_is_favorable_state"] = ((out["rotation_is_main_decline"] > 0) | (out["rotation_is_watch"] > 0)).astype(float)
    out["rotation_is_not_new_start"] = (out["rotation_is_new_start"] < 1).astype(float)
    out["rotation_top_cluster_tech"] = _as_flag(out["rotation_top_cluster"], "科技成长")
    out["rotation_top_cluster_new_energy"] = _as_flag(out["rotation_top_cluster"], "新能源")
    out["rotation_top_cluster_medical"] = _as_flag(out["rotation_top_cluster"], "医药防御")

    for column in ROTATION_NUMERIC_COLUMNS:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def merge_rotation_features(loaded: list[LoadedSymbol], rotation_daily: pd.DataFrame) -> list[LoadedSymbol]:
    out: list[LoadedSymbol] = []
    for item in loaded:
        df = item.df.merge(rotation_daily, on="trade_date", how="left").copy()
        if "sector_strongest_theme" in df.columns:
            df["stock_theme_cluster"] = df["sector_strongest_theme"].map(THEME_CLUSTER_MAP).fillna("")
            stock_theme = df["sector_strongest_theme"].fillna("")
        else:
            df["stock_theme_cluster"] = ""
            stock_theme = pd.Series([""] * len(df), index=df.index)
        df["stock_matches_rotation_top_theme"] = (stock_theme == df["rotation_top_theme"].fillna("")).astype(float)
        df["stock_matches_rotation_top_cluster"] = (df["stock_theme_cluster"].fillna("") == df["rotation_top_cluster"].fillna("")).astype(float)
        out.append(
            LoadedSymbol(
                symbol=item.symbol,
                name=item.name,
                df=df.reset_index(drop=True),
                idx_by_date={d: i for i, d in enumerate(df["trade_date"].tolist())},
            )
        )
    return out


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
    signal_win_rate = float(row.get("signal_win_rate") or 0.0)
    account_drawdown = float(row.get("account_max_drawdown") or 0.0)
    buy_count = float(row.get("account_buy_count") or 0.0)
    fill_rate = float(row.get("signal_topn_fill_rate") or 0.0)
    activity_bonus = min(buy_count / 120.0, 1.0) * 0.08
    return account_return * 1.2 + signal_median * 1.5 + signal_win_rate * 0.2 + fill_rate * 0.08 + activity_bonus - account_drawdown * 0.8


def _risk_note(row: dict[str, Any]) -> str:
    buy_count = int(row.get("account_buy_count") or 0)
    drawdown = float(row.get("account_max_drawdown") or 0.0)
    total_return = float(row.get("account_total_return") or 0.0)
    median_return = float(row.get("signal_median_trade_return") or 0.0)
    notes: list[str] = []
    if buy_count < 60:
        notes.append("交易次数偏少")
    if drawdown > 0.12:
        notes.append("账户回撤偏高")
    if total_return <= 0:
        notes.append("账户收益为负")
    if median_return <= 0:
        notes.append("信号中位收益不佳")
    return "；".join(notes) if notes else "通过基础风险筛选"


def _summarize_case(case: RotationGridCase, signal_result: dict[str, Any], account_result: dict[str, Any]) -> dict[str, Any]:
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
    lines = [
        "# 板块轮动状态条件网格探索报告",
        "",
        f"- 回测区间：{args.start_date} 至 {args.end_date}",
        f"- 轮动日频文件：`{args.rotation_daily_path}`",
        f"- 基准目录：`{args.base_processed_dir}`",
        f"- 板块增强目录：`{args.sector_processed_dir}`",
        "- 本报告用于验证轮动状态是否能改善上一轮最佳板块候选，不直接修改模拟账户。",
        "",
        "## Top 结果",
        "",
        "| 排名 | 策略 | 家族 | 轮动过滤 | 账户收益 | 年化 | 回撤 | 买入次数 | 账户胜率 | 信号中位 | grid_score | 风险提示 |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for idx, row in ranked.head(args.report_top_k).iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx + 1),
                    str(row["case"]),
                    str(row["family"]),
                    str(row.get("param_rotation_filter", "")),
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
    candidate = summary_df[summary_df["case"] == "板块候选_score0.4_rank0.7"]
    lines.extend(["", "## 对照", ""])
    if not baseline.empty:
        row = baseline.iloc[0]
        lines.append(f"- 基准动量：账户收益 {_pct(row.get('account_total_return'))}，回撤 {_pct(row.get('account_max_drawdown'))}，买入 {int(row.get('account_buy_count') or 0)} 次。")
    if not candidate.empty:
        row = candidate.iloc[0]
        lines.append(f"- 上轮板块候选：账户收益 {_pct(row.get('account_total_return'))}，回撤 {_pct(row.get('account_max_drawdown'))}，买入 {int(row.get('account_buy_count') or 0)} 次。")
    lines.extend(
        [
            "",
            "## 输出文件",
            "",
            f"- 汇总表：`{(out_dir / 'sector_rotation_grid_summary.csv').as_posix()}`",
            f"- 买卖记录：`{(out_dir / 'sector_rotation_grid_trade_records.csv').as_posix()}`",
            f"- 参数配置：`{(out_dir / 'sector_rotation_grid_config.json').as_posix()}`",
        ]
    )
    return "\n".join(lines) + "\n"


def run_rotation_grid(args: argparse.Namespace) -> Path:
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    rotation_daily = load_rotation_daily(args.rotation_daily_path)
    cases = build_rotation_grid_cases(
        base_processed_dir=args.base_processed_dir,
        sector_processed_dir=args.sector_processed_dir,
        include_baseline=not args.no_baseline,
    )

    base_loaded, base_diagnostics = load_processed_folder(args.base_processed_dir)
    base_diagnostics["data_profile"] = "base"
    sector_loaded, sector_diagnostics = load_processed_folder(args.sector_processed_dir)
    sector_diagnostics.update(validate_sector_feature_set(loaded_items=sector_loaded, processed_dir=sector_diagnostics["processed_dir"]))
    rotation_loaded = merge_rotation_features(sector_loaded, rotation_daily)
    rotation_diagnostics = dict(sector_diagnostics)
    rotation_diagnostics["rotation_daily_path"] = str(Path(args.rotation_daily_path))
    rotation_diagnostics["rotation_feature_enabled"] = True

    loaded_by_family = {
        "baseline": (base_loaded, base_diagnostics),
        "sector": (rotation_loaded, rotation_diagnostics),
    }

    summary_rows: list[dict[str, Any]] = []
    trade_frames: list[pd.DataFrame] = []
    summary_path = out_dir / "sector_rotation_grid_summary.csv"
    trades_path = out_dir / "sector_rotation_grid_trade_records.csv"
    config_path = out_dir / "sector_rotation_grid_config.json"
    report_path = out_dir / "sector_rotation_grid_report.md"
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
        print(f"[{idx}/{len(cases)}] {case.name}", flush=True)
        loaded, diagnostics = loaded_by_family["baseline" if case.family == "baseline" else "sector"]
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
        summary_rows.append(_summarize_case(case, signal_result, account_result))
        pd.DataFrame(summary_rows).to_csv(summary_path, index=False, encoding="utf-8-sig")
        if not args.skip_trade_records:
            trades = pd.DataFrame(account_result.get("trade_rows", []))
            if not trades.empty:
                trades.insert(0, "case", case.name)
                trades.insert(1, "family", case.family)
                trades.insert(2, "buy_condition", case.buy_condition)
                trades.insert(3, "score_expression", case.score_expression)
                trade_frames.append(trades)

    summary_df = pd.DataFrame(summary_rows).sort_values(["grid_score", "account_total_return", "account_max_drawdown"], ascending=[False, False, True])
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    if trade_frames:
        pd.concat(trade_frames, ignore_index=True, sort=False).to_csv(trades_path, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame().to_csv(trades_path, index=False, encoding="utf-8-sig")
    report_path.write_text(_render_report(summary_df, args, out_dir), encoding="utf-8")
    print(f"板块轮动状态条件网格探索完成：{out_dir.as_posix()}")
    return out_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="探索轮动状态条件对板块候选策略的影响")
    parser.add_argument("--base-processed-dir", default="data_bundle/processed_qfq_theme_focus_top100")
    parser.add_argument("--sector-processed-dir", default="data_bundle/processed_qfq_theme_focus_top100_sector")
    parser.add_argument("--rotation-daily-path", default="research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv")
    parser.add_argument("--start-date", default="20230101")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--out-dir", default="")
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
    parser.add_argument("--report-top-k", type=int, default=12)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    run_rotation_grid(parse_args(argv))


if __name__ == "__main__":
    main()
