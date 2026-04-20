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
from overnight_bt.grid_search import add_stability_columns, build_grid_cases
from overnight_bt.models import BacktestRequest
from overnight_bt.research import summarize_case_result


def _default_out_dir() -> Path:
    return Path("research_runs") / f"{date.today():%Y%m%d}_buy_condition_grid_v1"


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


def _expand_specs(grid_cases: list, exit_offsets: list[int]) -> list[tuple[object, int]]:
    return [(grid_case, exit_offset) for grid_case in grid_cases for exit_offset in exit_offsets]


def _run_period(
    case_specs: list[tuple[object, int]],
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
    for idx, (grid_case, exit_offset) in enumerate(case_specs, start=1):
        print(f"[{period}] case {idx}/{total}: {grid_case.name} | T+{exit_offset} open")
        case = grid_case.case
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
        row["grid_family"] = grid_case.family
        row.update({f"param_{key}": value for key, value in grid_case.params.items()})
        rows.append(row)
        pd.DataFrame(rows).to_csv(out_csv, index=False, encoding="utf-8-sig")
    return pd.DataFrame(rows)


def _select_train_cases(train_df: pd.DataFrame, top_k: int) -> pd.DataFrame:
    ranked = add_stability_columns(train_df)
    eligible = ranked[ranked["stable_pass"]].copy()
    if eligible.empty:
        eligible = ranked.copy()
    eligible = eligible.sort_values(
        ["stability_score", "annualized_return", "max_drawdown", "positive_month_ratio", "sell_count"],
        ascending=[False, False, True, False, False],
    )
    return eligible.head(top_k).reset_index(drop=True)


def _merge_leaderboard(selected_df: pd.DataFrame, valid_df: pd.DataFrame) -> pd.DataFrame:
    leaderboard = selected_df.merge(
        valid_df,
        on="case_key",
        how="left",
        suffixes=("_train", "_validation"),
    )
    leaderboard["case"] = leaderboard["case_train"].fillna(leaderboard.get("case_validation"))
    leaderboard["exit_offset"] = leaderboard["exit_offset_validation"].fillna(leaderboard["exit_offset_train"])
    leaderboard = add_stability_columns(leaderboard, suffix="_validation")
    leaderboard = leaderboard.sort_values(
        ["stable_pass_validation", "stability_score_validation", "annualized_return_validation", "max_drawdown_validation"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    return leaderboard


def _export_trade_records(
    leaderboard: pd.DataFrame,
    grid_case_lookup: dict[str, object],
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
        grid_case = grid_case_lookup[str(row["case"])]
        case = grid_case.case
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
        trade_rows.insert(3, "buy_condition", case.buy_condition)
        frames.append(trade_rows)
    if frames:
        pd.concat(frames, ignore_index=True).to_csv(out_csv, index=False, encoding="utf-8-sig")
        return
    pd.DataFrame(
        columns=[
            "period",
            "case",
            "exit_offset",
            "buy_condition",
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


def _render_summary(
    preset,
    grid_cases: list,
    exit_offsets: list[int],
    train_df: pd.DataFrame,
    selected_df: pd.DataFrame,
    leaderboard: pd.DataFrame,
    args: argparse.Namespace,
) -> str:
    lines = [
        "# 买入条件网格测试总结书",
        "",
        "## 本次测试目标",
        "",
        "- 在 `T` 日信号、`T+1` 开盘买入、`T+N` 开盘卖出的模型下，寻找回报率稳定性更高的买入条件。",
        "- 优先关注验证期稳定性，而不是只看训练期年化收益。",
        "",
        "## 回测参数",
        "",
        f"- 网格预设：`{preset.name}`",
        f"- 测试买入条件数：`{len(grid_cases)}`",
        f"- 卖出偏移集合：`{', '.join(str(item) for item in exit_offsets)}`",
        f"- 初始资金：`{args.initial_cash:.2f}`",
        f"- 每笔目标资金：`{args.per_trade_budget:.2f}`",
        f"- 手续费率：买入 `{args.buy_fee_rate}`，卖出 `{args.sell_fee_rate}`",
        f"- 滑点(bps)：`{args.slippage_bps}`",
        "",
        "## 网格维度",
        "",
    ]
    for dimension in preset.dimensions:
        lines.append(f"- `{dimension.key}`: " + " / ".join(str(item) for item in dimension.values))
    if preset.fixed_params:
        lines.extend(
            [
                "",
                "固定约束：",
            ]
        )
        for key, value in preset.fixed_params.items():
            lines.append(f"- `{key} = {value}`")
    lines.extend(
        [
            "",
            "## 稳定性筛选口径",
            "",
            "- 验证期 `annualized_return > 0`",
            "- 验证期 `positive_month_ratio >= 0.55`",
            "- 验证期 `max_drawdown <= 0.25`",
            "- 验证期 `sell_count >= 80`",
            "- 验证期 `active_day_ratio >= 0.08`",
            "",
            "稳定性评分说明：",
            "- 评分综合正收益月份占比、胜率、活跃度、年化收益、中位单笔收益、交易次数与回撤。",
            "- 排名时先看 `stable_pass_validation`，再看 `stability_score_validation`。",
            "",
            "## 训练期入围情况",
            "",
            f"- 训练期总组合数：{len(train_df)}",
            f"- 进入验证期组合数：{len(selected_df)}",
            "",
            "## 验证期推荐组合",
            "",
        ]
    )

    if leaderboard.empty:
        lines.append("- 当前没有验证期结果。")
        return "\n".join(lines)

    shown = leaderboard.head(10)
    for rank, (_, row) in enumerate(shown.iterrows(), start=1):
        lines.append(
            f"{rank}. `{row['case']}` / `T+{int(row['exit_offset'])}` / 稳定通过=`{bool(row['stable_pass_validation'])}`"
        )
        lines.append(
            f"   买入条件：`{row['buy_condition_train']}`"
        )
        lines.append(
            f"   验证期：稳定分 `{float(row['stability_score_validation']):.4f}`，年化 `{float(row['annualized_return_validation']):.4f}`，"
            f"最大回撤 `{float(row['max_drawdown_validation']):.4f}`，正收益月份占比 `{float(row['positive_month_ratio_validation']):.4f}`，"
            f"胜率 `{float(row['win_rate_validation']):.4f}`，卖出笔数 `{int(row['sell_count_validation'])}`"
        )

    best = leaderboard.iloc[0]
    lines.extend(
        [
            "",
            "## 本轮结论",
            "",
            f"- 当前首选组合是 `{best['case']}`，卖出偏移为 `T+{int(best['exit_offset'])}`。",
            f"- 推荐买入条件：`{best['buy_condition_train']}`",
            f"- 该组合验证期稳定分为 `{float(best['stability_score_validation']):.4f}`。",
            "",
            "## 输出文件",
            "",
            "- `grid_cases.json`：本轮网格定义",
            "- `train_results.csv`：训练期全部结果",
            "- `selected_train_cases.csv`：训练期入围组合",
            "- `validation_results.csv`：验证期结果",
            "- `leaderboard.csv`：训练/验证合并后的稳定性排行榜",
            "- `grid_summary.md`：本次测试总结书",
            "- `selected_case_trade_records.csv`：推荐组合的逐笔买卖记录",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run buy-condition grid tests and output a summary book plus trade records.")
    parser.add_argument("--processed-dir", default="data_bundle/processed_qfq")
    parser.add_argument("--grid-preset", default="buy_condition_grid_v1")
    parser.add_argument("--train-start", default="20190101")
    parser.add_argument("--train-end", default="20221231")
    parser.add_argument("--valid-start", default="20230101")
    parser.add_argument("--valid-end", default="20251231")
    parser.add_argument("--top-k", type=int, default=12)
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

    grid_cases, preset = build_grid_cases(args.grid_preset)
    grid_case_lookup = {grid_case.name: grid_case for grid_case in grid_cases}
    case_specs = _expand_specs(grid_cases, exit_offsets)
    (out_dir / "grid_cases.json").write_text(
        json.dumps(
            [
                {
                    "name": grid_case.name,
                    "family": grid_case.family,
                    "params": grid_case.params,
                    "buy_condition": grid_case.case.buy_condition,
                    "score_expression": grid_case.case.score_expression,
                    "top_n": grid_case.case.top_n,
                }
                for grid_case in grid_cases
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("loading train dataset")
    train_loaded, train_diagnostics = load_processed_folder(args.processed_dir, args.train_start, args.train_end)
    print("loading validation dataset")
    valid_loaded, valid_diagnostics = load_processed_folder(args.processed_dir, args.valid_start, args.valid_end)
    common_kwargs = _common_request_kwargs(args)

    train_df = _run_period(
        case_specs=case_specs,
        loaded=train_loaded,
        diagnostics=train_diagnostics,
        common_kwargs=common_kwargs,
        start_date=args.train_start,
        end_date=args.train_end,
        period="train",
        out_csv=out_dir / "train_results.csv",
    )
    selected_df = _select_train_cases(train_df, top_k=args.top_k)
    selected_df.to_csv(out_dir / "selected_train_cases.csv", index=False, encoding="utf-8-sig")

    selected_specs = [(grid_case_lookup[str(row["case"])], int(row["exit_offset"])) for _, row in selected_df.iterrows()]
    valid_df = _run_period(
        case_specs=selected_specs,
        loaded=valid_loaded,
        diagnostics=valid_diagnostics,
        common_kwargs=common_kwargs,
        start_date=args.valid_start,
        end_date=args.valid_end,
        period="validation",
        out_csv=out_dir / "validation_results.csv",
    )
    leaderboard = _merge_leaderboard(selected_df, valid_df)
    leaderboard.to_csv(out_dir / "leaderboard.csv", index=False, encoding="utf-8-sig")

    _export_trade_records(
        leaderboard=leaderboard,
        grid_case_lookup=grid_case_lookup,
        loaded=valid_loaded,
        diagnostics=valid_diagnostics,
        common_kwargs=common_kwargs,
        start_date=args.valid_start,
        end_date=args.valid_end,
        out_csv=out_dir / "selected_case_trade_records.csv",
        top_k=args.export_top_trades_k,
    )

    summary = {
        "grid_preset": args.grid_preset,
        "grid_case_count": len(grid_cases),
        "train_case_count": len(train_df),
        "selected_train_case_count": len(selected_df),
        "validation_case_count": len(valid_df),
        "best_case": leaderboard.iloc[0]["case"] if not leaderboard.empty else "",
        "best_exit_offset": int(leaderboard.iloc[0]["exit_offset"]) if not leaderboard.empty else None,
        "best_stability_score_validation": float(leaderboard.iloc[0]["stability_score_validation"]) if not leaderboard.empty else None,
    }
    (out_dir / "grid_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "grid_summary.md").write_text(
        _render_summary(
            preset=preset,
            grid_cases=grid_cases,
            exit_offsets=exit_offsets,
            train_df=train_df,
            selected_df=selected_df,
            leaderboard=leaderboard,
            args=args,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
