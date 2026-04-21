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
from overnight_bt.grid_search import add_stability_columns
from overnight_bt.models import BacktestRequest
from overnight_bt.research import summarize_case_result


DEFAULT_BUY_CONDITION = (
    "board=主板,listed_days>500,m20>0.03,m5>0,pct_chg>-1.0,pct_chg<3.0,"
    "close_pos_in_bar>0.65,upper_shadow_pct<0.02,body_pct>0.0,vr<1.6,hs300_pct_chg>-1.0"
)
DEFAULT_SCORE_EXPRESSION = "m20 * 155 + close_pos_in_bar * 6 + body_pct * 90 - upper_shadow_pct * 120 - abs(vr - 1.0) * 3"


def _default_out_dir() -> Path:
    return Path("research_runs") / f"{date.today():%Y%m%d}_topn_hold_compare_v1"


def _parse_int_list(raw_text: str) -> list[int]:
    values = sorted({int(token.strip()) for token in str(raw_text).split(",") if token.strip()})
    if not values:
        raise ValueError("parameter list cannot be empty")
    return values


def _common_request_kwargs(args: argparse.Namespace, top_n: int) -> dict:
    return {
        "processed_dir": args.processed_dir,
        "initial_cash": args.initial_cash,
        "per_trade_budget": args.per_trade_budget,
        "lot_size": args.lot_size,
        "buy_fee_rate": args.buy_fee_rate,
        "sell_fee_rate": args.sell_fee_rate,
        "stamp_tax_sell": args.stamp_tax_sell,
        "entry_offset": args.entry_offset,
        "top_n": top_n,
        "realistic_execution": args.realistic_execution,
        "slippage_bps": args.slippage_bps,
        "min_commission": args.min_commission,
    }


def _run_case(
    loaded: list,
    diagnostics: dict,
    top_n: int,
    exit_offset: int,
    period: str,
    start_date: str,
    end_date: str,
    args: argparse.Namespace,
) -> tuple[dict, dict]:
    req = BacktestRequest(
        start_date=start_date,
        end_date=end_date,
        buy_condition=args.buy_condition,
        score_expression=args.score_expression,
        exit_offset=exit_offset,
        **_common_request_kwargs(args, top_n),
    )
    result = run_portfolio_backtest_loaded(loaded, diagnostics, req)
    row = summarize_case_result(
        f"top{top_n}_n{exit_offset}",
        period,
        args.buy_condition,
        args.score_expression,
        top_n,
        result,
    )
    row["top_n"] = top_n
    row["exit_offset"] = exit_offset
    row["processed_dir"] = args.processed_dir
    return row, result


def _run_period(
    loaded: list,
    diagnostics: dict,
    top_ns: list[int],
    exit_offsets: list[int],
    period: str,
    start_date: str,
    end_date: str,
    args: argparse.Namespace,
    out_csv: Path,
) -> pd.DataFrame:
    rows: list[dict] = []
    total = len(top_ns) * len(exit_offsets)
    seq = 0
    for top_n in top_ns:
        for exit_offset in exit_offsets:
            seq += 1
            print(f"[{period}] case {seq}/{total}: Top{top_n} | T+{exit_offset} open")
            row, _ = _run_case(
                loaded=loaded,
                diagnostics=diagnostics,
                top_n=top_n,
                exit_offset=exit_offset,
                period=period,
                start_date=start_date,
                end_date=end_date,
                args=args,
            )
            rows.append(row)
            pd.DataFrame(rows).to_csv(out_csv, index=False, encoding="utf-8-sig")
    return pd.DataFrame(rows)


def _merge_leaderboard(train_df: pd.DataFrame, valid_df: pd.DataFrame) -> pd.DataFrame:
    leaderboard = train_df.merge(
        valid_df,
        on="case_key",
        how="left",
        suffixes=("_train", "_validation"),
    )
    leaderboard["top_n"] = leaderboard["top_n_validation"].fillna(leaderboard["top_n_train"])
    leaderboard["exit_offset"] = leaderboard["exit_offset_validation"].fillna(leaderboard["exit_offset_train"])
    leaderboard = add_stability_columns(leaderboard, suffix="_validation")
    leaderboard = leaderboard.sort_values(
        ["stable_pass_validation", "stability_score_validation", "annualized_return_validation", "max_drawdown_validation"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    return leaderboard


def _export_trade_records(
    leaderboard: pd.DataFrame,
    loaded: list,
    diagnostics: dict,
    args: argparse.Namespace,
    out_csv: Path,
    top_k: int,
) -> None:
    frames: list[pd.DataFrame] = []
    for _, row in leaderboard.head(top_k).iterrows():
        _, result = _run_case(
            loaded=loaded,
            diagnostics=diagnostics,
            top_n=int(row["top_n"]),
            exit_offset=int(row["exit_offset"]),
            period="validation_export",
            start_date=args.valid_start,
            end_date=args.valid_end,
            args=args,
        )
        trade_rows = pd.DataFrame(result.get("trade_rows", []))
        if trade_rows.empty:
            continue
        trade_rows.insert(0, "period", "validation")
        trade_rows.insert(1, "top_n", int(row["top_n"]))
        trade_rows.insert(2, "exit_offset", int(row["exit_offset"]))
        frames.append(trade_rows)
    if frames:
        pd.concat(frames, ignore_index=True).to_csv(out_csv, index=False, encoding="utf-8-sig")
        return
    pd.DataFrame(
        columns=[
            "period",
            "top_n",
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


def _render_summary(
    top_ns: list[int],
    exit_offsets: list[int],
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    leaderboard: pd.DataFrame,
    args: argparse.Namespace,
) -> str:
    lines = [
        "# 主题前100池 TopN 与固定持有期对比总结书",
        "",
        "## 本次测试目标",
        "",
        "- 固定主题前100市值股票池",
        "- 固定当前主线买入条件",
        "- 比较 `Top1 / Top3 / Top5` 与 `T+4 / T+5 / T+6 / T+7` 的差异",
        "",
        "## 固定配置",
        "",
        f"- 股票池目录：`{args.processed_dir}`",
        f"- 买入条件：`{args.buy_condition}`",
        f"- 评分表达式：`{args.score_expression}`",
        f"- 买入偏移：`T+{args.entry_offset}` 开盘",
        "",
        "## 比较维度",
        "",
        "- TopN：" + " / ".join(f"`Top{n}`" for n in top_ns),
        "- 固定卖出：" + " / ".join(f"`T+{offset}`" for offset in exit_offsets),
        "",
        "## 训练期与验证期组合数量",
        "",
        f"- 训练期结果数：{len(train_df)}",
        f"- 验证期结果数：{len(valid_df)}",
        "",
        "## 验证期排行榜",
        "",
    ]

    for rank, (_, row) in enumerate(leaderboard.head(12).iterrows(), start=1):
        lines.append(
            f"{rank}. `Top{int(row['top_n'])}` / `T+{int(row['exit_offset'])}` / 稳定通过=`{bool(row['stable_pass_validation'])}`"
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
            f"- 当前最优组合是 `Top{int(best['top_n'])}` 搭配 `T+{int(best['exit_offset'])}` 固定卖出。",
            f"- 该组合验证期稳定分为 `{float(best['stability_score_validation']):.4f}`。",
            "",
            "## 输出文件",
            "",
            "- `train_results.csv`：训练期对比结果",
            "- `validation_results.csv`：验证期对比结果",
            "- `leaderboard.csv`：验证期排行榜",
            "- `topn_hold_summary.md`：本次对比总结书",
            "- `selected_case_trade_records.csv`：前几名组合的逐笔交易记录",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare TopN and fixed holding days on theme_focus_top100.")
    parser.add_argument("--processed-dir", default="data_bundle/processed_qfq_theme_focus_top100")
    parser.add_argument("--buy-condition", default=DEFAULT_BUY_CONDITION)
    parser.add_argument("--score-expression", default=DEFAULT_SCORE_EXPRESSION)
    parser.add_argument("--train-start", default="20190101")
    parser.add_argument("--train-end", default="20221231")
    parser.add_argument("--valid-start", default="20230101")
    parser.add_argument("--valid-end", default="20251231")
    parser.add_argument("--top-n-values", default="1,3,5")
    parser.add_argument("--exit-offsets", default="4,5,6,7")
    parser.add_argument("--entry-offset", type=int, default=1)
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

    top_ns = _parse_int_list(args.top_n_values)
    exit_offsets = _parse_int_list(args.exit_offsets)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    train_loaded, train_diagnostics = load_processed_folder(args.processed_dir, args.train_start, args.train_end)
    valid_loaded, valid_diagnostics = load_processed_folder(args.processed_dir, args.valid_start, args.valid_end)

    train_df = _run_period(
        loaded=train_loaded,
        diagnostics=train_diagnostics,
        top_ns=top_ns,
        exit_offsets=exit_offsets,
        period="train",
        start_date=args.train_start,
        end_date=args.train_end,
        args=args,
        out_csv=out_dir / "train_results.csv",
    )
    valid_df = _run_period(
        loaded=valid_loaded,
        diagnostics=valid_diagnostics,
        top_ns=top_ns,
        exit_offsets=exit_offsets,
        period="validation",
        start_date=args.valid_start,
        end_date=args.valid_end,
        args=args,
        out_csv=out_dir / "validation_results.csv",
    )
    leaderboard = _merge_leaderboard(train_df, valid_df)
    leaderboard.to_csv(out_dir / "leaderboard.csv", index=False, encoding="utf-8-sig")
    _export_trade_records(
        leaderboard=leaderboard,
        loaded=valid_loaded,
        diagnostics=valid_diagnostics,
        args=args,
        out_csv=out_dir / "selected_case_trade_records.csv",
        top_k=args.export_top_trades_k,
    )

    summary = {
        "processed_dir": args.processed_dir,
        "top_ns": top_ns,
        "exit_offsets": exit_offsets,
        "best_top_n": int(leaderboard.iloc[0]["top_n"]) if not leaderboard.empty else None,
        "best_exit_offset": int(leaderboard.iloc[0]["exit_offset"]) if not leaderboard.empty else None,
        "best_stability_score_validation": float(leaderboard.iloc[0]["stability_score_validation"]) if not leaderboard.empty else None,
    }
    (out_dir / "topn_hold_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "topn_hold_summary.md").write_text(
        _render_summary(
            top_ns=top_ns,
            exit_offsets=exit_offsets,
            train_df=train_df,
            valid_df=valid_df,
            leaderboard=leaderboard,
            args=args,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
