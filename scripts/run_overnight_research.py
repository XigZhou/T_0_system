from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.backtest import load_processed_folder, run_portfolio_backtest_loaded
from overnight_bt.models import BacktestRequest
from overnight_bt.research import ResearchCase, build_neighborhood_cases, select_train_top_cases, summarize_case_result


def _default_out_dir() -> Path:
    return Path("research_runs") / f"{date.today():%Y%m%d}_swing_research"


def _parse_exit_offsets(raw_text: str) -> list[int]:
    values = sorted({int(token.strip()) for token in str(raw_text).split(",") if token.strip()})
    if not values:
        raise ValueError("exit offsets cannot be empty")
    if any(value < 2 or value > 5 for value in values):
        raise ValueError("exit offsets must be between 2 and 5")
    return values


def _common_request_kwargs(args: argparse.Namespace) -> dict:
    return {
        "processed_dir": args.processed_dir,
        "initial_cash": args.initial_cash,
        "per_trade_budget": args.per_trade_budget,
        "lot_size": args.lot_size,
        "buy_fee_rate": args.buy_fee_rate,
        "sell_fee_rate": args.sell_fee_rate,
        "stamp_tax_sell": args.stamp_tax_sell,
        "entry_offset": args.entry_offset,
        "realistic_execution": args.realistic_execution,
        "slippage_bps": args.slippage_bps,
        "min_commission": args.min_commission,
    }


def _expand_case_specs(cases: list[ResearchCase], exit_offsets: list[int]) -> list[tuple[ResearchCase, int]]:
    return [(case, exit_offset) for case in cases for exit_offset in exit_offsets]


def _run_period(
    case_specs: list[tuple[ResearchCase, int]],
    loaded: list,
    diagnostics: dict,
    common_kwargs: dict,
    start_date: str,
    end_date: str,
    period: str,
    out_csv: Path,
) -> pd.DataFrame:
    rows: list[dict] = []
    total = len(case_specs)
    for idx, (case, exit_offset) in enumerate(case_specs, start=1):
        print(f"[{period}] case {idx}/{total}: {case.name} | T+{exit_offset} open")
        req = BacktestRequest(
            start_date=start_date,
            end_date=end_date,
            buy_condition=case.buy_condition,
            score_expression=case.score_expression,
            top_n=case.top_n,
            exit_offset=exit_offset,
            **common_kwargs,
        )
        result = run_portfolio_backtest_loaded(loaded, diagnostics, req)
        row = summarize_case_result(case.name, period, case.buy_condition, case.score_expression, case.top_n, result)
        rows.append(row)
        pd.DataFrame(rows).to_csv(out_csv, index=False, encoding="utf-8-sig")
        print(
            json.dumps(
                {
                    "case": case.name,
                    "period": period,
                    "exit_offset": exit_offset,
                    "annualized_return": row["annualized_return"],
                    "max_drawdown": row["max_drawdown"],
                    "sell_count": row["sell_count"],
                    "positive_month_ratio": row["positive_month_ratio"],
                },
                ensure_ascii=False,
            )
        )
    return pd.DataFrame(rows)


def _build_case_lookup(cases: list[ResearchCase]) -> dict[str, ResearchCase]:
    return {case.name: case for case in cases}


def _rows_to_case_specs(rows: pd.DataFrame, case_lookup: dict[str, ResearchCase]) -> list[tuple[ResearchCase, int]]:
    specs: list[tuple[ResearchCase, int]] = []
    for _, row in rows.iterrows():
        case = case_lookup[str(row["case"])]
        specs.append((case, int(row["exit_offset"])))
    return specs


def _export_selected_trade_records(
    leaderboard: pd.DataFrame,
    case_lookup: dict[str, ResearchCase],
    loaded: list,
    diagnostics: dict,
    common_kwargs: dict,
    start_date: str,
    end_date: str,
    out_csv: Path,
    top_k: int,
) -> None:
    frames: list[pd.DataFrame] = []
    for _, row in leaderboard.head(top_k).iterrows():
        case = case_lookup[str(row["case"])]
        exit_offset = int(row["exit_offset"])
        req = BacktestRequest(
            start_date=start_date,
            end_date=end_date,
            buy_condition=case.buy_condition,
            score_expression=case.score_expression,
            top_n=case.top_n,
            exit_offset=exit_offset,
            **common_kwargs,
        )
        result = run_portfolio_backtest_loaded(loaded, diagnostics, req)
        trade_rows = pd.DataFrame(result.get("trade_rows", []))
        if trade_rows.empty:
            continue
        trade_rows.insert(0, "period", "validation")
        trade_rows.insert(1, "case", case.name)
        trade_rows.insert(2, "exit_offset", exit_offset)
        frames.append(trade_rows)
    if frames:
        pd.concat(frames, ignore_index=True).to_csv(out_csv, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame(
            columns=[
                "period",
                "case",
                "exit_offset",
                "trade_date",
                "signal_date",
                "planned_entry_date",
                "planned_exit_date",
                "symbol",
                "name",
                "action",
                "price",
                "shares",
                "gross_amount",
                "fees",
                "net_amount",
                "cash_after",
                "trade_return",
                "price_pnl",
            ]
        ).to_csv(out_csv, index=False, encoding="utf-8-sig")


def _render_research_summary_md(
    preset: str,
    entry_offset: int,
    exit_offsets: list[int],
    train_df: pd.DataFrame,
    selected_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    leaderboard: pd.DataFrame,
    args: argparse.Namespace,
) -> str:
    lines = [
        "# T 日信号摆动研究汇总",
        "",
        "## 本次研究配置",
        "",
        f"- 预设方案：`{preset}`",
        f"- 买入口径：`T+{entry_offset}` 日开盘",
        f"- 卖出口径：`T+N` 日开盘，N 属于 `{', '.join(str(item) for item in exit_offsets)}`",
        f"- 初始资金：`{args.initial_cash:.2f}`",
        f"- 每笔目标资金：`{args.per_trade_budget:.2f}`",
        f"- 每手股数：`{args.lot_size}`",
        f"- 买入手续费率：`{args.buy_fee_rate}`",
        f"- 卖出手续费率：`{args.sell_fee_rate}`",
        f"- 滑点(bps)：`{args.slippage_bps}`",
        "",
        "## 训练期概览",
        "",
        f"- 样本组合数：{len(train_df)}",
        f"- 入选验证组合数：{len(selected_df)}",
        "",
        "## 训练期入选组合",
        "",
    ]
    if selected_df.empty:
        lines.append("- 没有入选组合。")
    else:
        for _, row in selected_df.iterrows():
            lines.append(
                f"- `{row['case']}` / `T+{int(row['exit_offset'])}`："
                f"年化 {float(row['annualized_return']):.4f}，最大回撤 {float(row['max_drawdown']):.4f}，"
                f"正收益月份占比 {float(row['positive_month_ratio']):.4f}"
            )

    lines.extend(
        [
            "",
            "## 验证期排行榜",
            "",
        ]
    )
    if leaderboard.empty:
        lines.append("- 验证期没有可用结果。")
    else:
        for _, row in leaderboard.head(10).iterrows():
            lines.append(
                f"- `{row['case']}` / `T+{int(row['exit_offset'])}`："
                f"验证年化 {float(row['annualized_return_validation']):.4f}，"
                f"验证最大回撤 {float(row['max_drawdown_validation']):.4f}，"
                f"验证胜率 {float(row['win_rate_validation']):.4f}"
            )
    lines.extend(
        [
            "",
            "## 输出文件",
            "",
            "- `train_results.csv`：训练期所有组合结果",
            "- `selected_train_cases.csv`：训练期入选组合",
            "- `validation_results.csv`：验证期结果",
            "- `leaderboard.csv`：训练/验证合并后的排行榜",
            "- `selected_case_trade_records.csv`：验证期前几名组合的逐笔交易明细",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run T-day signal research with T+1 open entry and T+N open exits.")
    parser.add_argument("--processed-dir", default="data_bundle/processed_qfq")
    parser.add_argument("--preset", default="swing_v1")
    parser.add_argument("--train-start", default="20190101")
    parser.add_argument("--train-end", default="20221231")
    parser.add_argument("--valid-start", default="20230101")
    parser.add_argument("--valid-end", default="20251231")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--entry-offset", type=int, default=1)
    parser.add_argument("--exit-offsets", default="2,3,4,5")
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--per-trade-budget", type=float, default=10_000.0)
    parser.add_argument("--lot-size", type=int, default=100)
    parser.add_argument("--buy-fee-rate", type=float, default=0.00003)
    parser.add_argument("--sell-fee-rate", type=float, default=0.00003)
    parser.add_argument("--stamp-tax-sell", type=float, default=0.0)
    parser.add_argument("--slippage-bps", type=float, default=3.0)
    parser.add_argument("--min-commission", type=float, default=0.0)
    parser.add_argument("--realistic-execution", dest="realistic_execution", action="store_true")
    parser.add_argument("--no-realistic-execution", dest="realistic_execution", action="store_false")
    parser.add_argument("--export-top-trades-k", type=int, default=3)
    parser.add_argument("--out-dir", default=str(_default_out_dir()))
    parser.set_defaults(realistic_execution=True)
    args = parser.parse_args()

    exit_offsets = _parse_exit_offsets(args.exit_offsets)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = build_neighborhood_cases(preset=args.preset)
    case_lookup = _build_case_lookup(cases)
    case_specs = _expand_case_specs(cases, exit_offsets)
    (out_dir / "case_definitions.json").write_text(
        json.dumps(
            [
                {
                    "name": case.name,
                    "buy_condition": case.buy_condition,
                    "score_expression": case.score_expression,
                    "top_n": case.top_n,
                }
                for case in cases
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("loading full processed dataset once for train/validation reuse")
    loaded, diagnostics = load_processed_folder(args.processed_dir)
    common_kwargs = _common_request_kwargs(args)

    train_df = _run_period(
        case_specs=case_specs,
        loaded=loaded,
        diagnostics=diagnostics,
        common_kwargs=common_kwargs,
        start_date=args.train_start,
        end_date=args.train_end,
        period="train",
        out_csv=out_dir / "train_results.csv",
    )
    selected = select_train_top_cases(train_df, top_k=args.top_k)
    selected.to_csv(out_dir / "selected_train_cases.csv", index=False, encoding="utf-8-sig")

    selected_specs = _rows_to_case_specs(selected, case_lookup)
    valid_df = _run_period(
        case_specs=selected_specs,
        loaded=loaded,
        diagnostics=diagnostics,
        common_kwargs=common_kwargs,
        start_date=args.valid_start,
        end_date=args.valid_end,
        period="validation",
        out_csv=out_dir / "validation_results.csv",
    )

    leaderboard = selected.merge(
        valid_df,
        on="case_key",
        how="left",
        suffixes=("_train", "_validation"),
    )
    leaderboard["case"] = leaderboard["case_train"].fillna(leaderboard.get("case_validation"))
    leaderboard["exit_offset"] = leaderboard["exit_offset_validation"].fillna(leaderboard["exit_offset_train"])
    leaderboard = leaderboard.sort_values(
        ["annualized_return_validation", "max_drawdown_validation", "positive_month_ratio_validation"],
        ascending=[False, True, False],
    ).reset_index(drop=True)
    leaderboard.to_csv(out_dir / "leaderboard.csv", index=False, encoding="utf-8-sig")

    _export_selected_trade_records(
        leaderboard=leaderboard,
        case_lookup=case_lookup,
        loaded=loaded,
        diagnostics=diagnostics,
        common_kwargs=common_kwargs,
        start_date=args.valid_start,
        end_date=args.valid_end,
        out_csv=out_dir / "selected_case_trade_records.csv",
        top_k=args.export_top_trades_k,
    )

    summary = {
        "preset": args.preset,
        "entry_offset": args.entry_offset,
        "exit_offsets": exit_offsets,
        "case_count_train": len(train_df),
        "case_count_validation": len(valid_df),
        "top_k": args.top_k,
        "best_validation_case": leaderboard.iloc[0]["case"] if not leaderboard.empty else "",
        "best_validation_exit_offset": int(leaderboard.iloc[0]["exit_offset"]) if not leaderboard.empty else None,
    }
    (out_dir / "research_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "research_summary.md").write_text(
        _render_research_summary_md(
            preset=args.preset,
            entry_offset=args.entry_offset,
            exit_offsets=exit_offsets,
            train_df=train_df,
            selected_df=selected,
            valid_df=valid_df,
            leaderboard=leaderboard,
            args=args,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
