from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
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


@dataclass(frozen=True)
class SellGridCase:
    name: str
    sell_condition: str
    min_hold_days: int
    max_hold_days: int
    exit_offset: int
    note: str


def _default_out_dir() -> Path:
    return Path("research_runs") / f"{date.today():%Y%m%d}_sell_condition_grid_v1"


def build_sell_grid_cases_v1() -> list[SellGridCase]:
    return [
        SellGridCase("fixed_exit_t5", "", 0, 0, 5, "固定 T+5 卖出基线"),
        SellGridCase("close_lt_ma5_h1_mh7", "close<ma5", 1, 7, 5, "跌破 ma5，最短持有 1 天"),
        SellGridCase("close_lt_ma5_h2_mh7", "close<ma5", 2, 7, 5, "跌破 ma5，最短持有 2 天"),
        SellGridCase("m5_lt_0_h2_mh7", "m5<0", 2, 7, 5, "短周期动量转负"),
        SellGridCase("close_lt_ma5_and_m5_lt_0_h2_mh7", "close<ma5,m5<0", 2, 7, 5, "趋势和动量同时转弱"),
        SellGridCase("ret1_lt_0_and_close_lt_ma5_h2_mh7", "ret1<0,close<ma5", 2, 7, 5, "单日转弱并跌破 ma5"),
        SellGridCase("close_lt_ma10_h2_mh7", "close<ma10", 2, 7, 5, "跌破更长均线 ma10"),
        SellGridCase("body_lt_0_and_close_pos_lt_0p5_h2_mh7", "body_pct<0,close_pos_in_bar<0.5", 2, 7, 5, "弱收盘实体"),
        SellGridCase("m5_rollover_and_close_lt_ma5_h2_mh7", "m5<m5[1],close<ma5", 2, 7, 5, "动量拐头且跌破 ma5"),
    ]


def build_sell_grid_cases_v2_advanced() -> list[SellGridCase]:
    return [
        SellGridCase("fixed_exit_t5", "", 0, 0, 5, "固定 T+5 卖出基线"),
        SellGridCase("stoploss_5pct_h1_mh15", "holding_return<-0.05", 1, 15, 5, "5% 止损"),
        SellGridCase("stoploss_3pct_h1_mh15", "holding_return<-0.03", 1, 15, 5, "3% 止损"),
        SellGridCase("trail_8_4_h2_mh15", "best_return_since_entry>0.08,drawdown_from_peak>0.04", 2, 15, 5, "浮盈超 8% 后回撤 4%"),
        SellGridCase("trail_10_5_h2_mh15", "best_return_since_entry>0.10,drawdown_from_peak>0.05", 2, 15, 5, "浮盈超 10% 后回撤 5%"),
        SellGridCase("trail_6_3_h2_mh15", "best_return_since_entry>0.06,drawdown_from_peak>0.03", 2, 15, 5, "浮盈超 6% 后回撤 3%"),
        SellGridCase("stoploss_5pct_h1_mh10", "holding_return<-0.05", 1, 10, 5, "5% 止损 + 更短最大持有"),
        SellGridCase("trail_8_4_h2_mh10", "best_return_since_entry>0.08,drawdown_from_peak>0.04", 2, 10, 5, "浮盈回撤 + 更短最大持有"),
    ]


def build_sell_grid_cases(preset: str) -> list[SellGridCase]:
    if preset == "sell_grid_basic_v1":
        return build_sell_grid_cases_v1()
    if preset == "sell_grid_advanced_v1":
        return build_sell_grid_cases_v2_advanced()
    raise ValueError(f"unsupported sell grid preset: {preset}")


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
        "top_n": args.top_n,
        "realistic_execution": args.realistic_execution,
        "slippage_bps": args.slippage_bps,
        "min_commission": args.min_commission,
    }


def _run_period(
    cases: list[SellGridCase],
    loaded: list,
    diagnostics: dict,
    common_kwargs: dict,
    start_date: str,
    end_date: str,
    period: str,
    out_csv: Path,
    args: argparse.Namespace,
) -> pd.DataFrame:
    rows: list[dict] = []
    total = len(cases)
    for idx, case in enumerate(cases, start=1):
        print(f"[{period}] case {idx}/{total}: {case.name}")
        req = BacktestRequest(
            start_date=start_date,
            end_date=end_date,
            buy_condition=args.buy_condition,
            sell_condition=case.sell_condition,
            score_expression=args.score_expression,
            exit_offset=case.exit_offset,
            min_hold_days=case.min_hold_days,
            max_hold_days=case.max_hold_days,
            **common_kwargs,
        )
        result = run_portfolio_backtest_loaded(loaded, diagnostics, req)
        row = summarize_case_result(case.name, period, args.buy_condition, args.score_expression, args.top_n, result)
        row["sell_condition"] = case.sell_condition
        row["min_hold_days"] = case.min_hold_days
        row["max_hold_days"] = case.max_hold_days
        row["note"] = case.note
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
    leaderboard = add_stability_columns(leaderboard, suffix="_validation")
    leaderboard = leaderboard.sort_values(
        ["stable_pass_validation", "stability_score_validation", "annualized_return_validation", "max_drawdown_validation"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    return leaderboard


def _export_trade_records(
    leaderboard: pd.DataFrame,
    case_lookup: dict[str, SellGridCase],
    loaded: list,
    diagnostics: dict,
    common_kwargs: dict,
    start_date: str,
    end_date: str,
    out_csv: Path,
    args: argparse.Namespace,
    top_k: int,
) -> None:
    frames: list[pd.DataFrame] = []
    for _, row in leaderboard.head(top_k).iterrows():
        case = case_lookup[str(row["case"])]
        req = BacktestRequest(
            start_date=start_date,
            end_date=end_date,
            buy_condition=args.buy_condition,
            sell_condition=case.sell_condition,
            score_expression=args.score_expression,
            exit_offset=case.exit_offset,
            min_hold_days=case.min_hold_days,
            max_hold_days=case.max_hold_days,
            **common_kwargs,
        )
        result = run_portfolio_backtest_loaded(loaded, diagnostics, req)
        trade_rows = pd.DataFrame(result.get("trade_rows", []))
        if trade_rows.empty:
            continue
        trade_rows.insert(0, "period", "validation")
        trade_rows.insert(1, "case", case.name)
        trade_rows.insert(2, "sell_condition", case.sell_condition)
        trade_rows.insert(3, "min_hold_days", case.min_hold_days)
        trade_rows.insert(4, "max_hold_days", case.max_hold_days)
        frames.append(trade_rows)
    if frames:
        pd.concat(frames, ignore_index=True).to_csv(out_csv, index=False, encoding="utf-8-sig")
        return
    pd.DataFrame(
        columns=[
            "period",
            "case",
            "sell_condition",
            "min_hold_days",
            "max_hold_days",
            "trade_date",
            "signal_date",
            "planned_entry_date",
            "planned_exit_date",
            "max_exit_date",
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
            "exit_reason",
            "exit_signal_date",
        ]
    ).to_csv(out_csv, index=False, encoding="utf-8-sig")


def _render_summary(
    cases: list[SellGridCase],
    train_df: pd.DataFrame,
    selected_df: pd.DataFrame,
    leaderboard: pd.DataFrame,
    args: argparse.Namespace,
) -> str:
    lines = [
        "# 卖出指标网格测试总结书",
        "",
        "## 本次测试目标",
        "",
        "- 固定当前买入条件与持仓名额，测试不同卖出条件对收益、交易笔数、胜率和稳定性的影响。",
        "- 卖出信号统一在收盘后判断，实际成交放到下一交易日开盘。",
        "",
        "## 固定买入配置",
        "",
        f"- 买入条件：`{args.buy_condition}`",
        f"- 评分表达式：`{args.score_expression}`",
        f"- TopN：`{args.top_n}`",
        f"- 买入偏移：`T+{args.entry_offset}` 开盘",
        "",
        "## 本轮卖出候选",
        "",
    ]
    for case in cases:
        lines.append(
            f"- `{case.name}`：卖出条件 `{case.sell_condition or '固定 T+5 卖出'}`，"
            f"`min_hold_days={case.min_hold_days}`，`max_hold_days={case.max_hold_days}`，说明：{case.note}"
        )

    lines.extend(
        [
            "",
            "## 训练期入围情况",
            "",
            f"- 训练期总组合数：{len(train_df)}",
            f"- 进入验证期组合数：{len(selected_df)}",
            "",
            "## 稳定通过判定规则",
            "",
            "- 验证期 `annualized_return > 0`",
            "- 验证期 `positive_month_ratio >= 0.55`",
            "- 验证期 `max_drawdown <= 0.25`",
            "- 验证期 `sell_count >= 80`",
            "- 验证期 `active_day_ratio >= 0.08`",
            "",
            "说明：",
            "- 只有同时满足以上 5 条，`稳定通过` 才会显示为 `True`。",
            "- `stability_score_validation` 是排序分数，会综合收益、回撤、正收益月份占比、胜率、活跃度和交易次数；但是否 `稳定通过` 仍以上面的硬门槛为准。",
            "",
            "## 验证期推荐组合",
            "",
        ]
    )

    if leaderboard.empty:
        lines.append("- 当前没有验证期结果。")
        return "\n".join(lines)

    for rank, (_, row) in enumerate(leaderboard.head(10).iterrows(), start=1):
        lines.append(
            f"{rank}. `{row['case']}` / 稳定通过=`{bool(row['stable_pass_validation'])}`"
        )
        lines.append(
            f"   卖出条件：`{row['sell_condition_train'] if isinstance(row.get('sell_condition_train'), str) and row.get('sell_condition_train') else '固定 T+5 卖出'}`"
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
            f"- 当前首选卖出方案是 `{best['case']}`。",
            f"- 卖出条件：`{best['sell_condition_train'] if isinstance(best.get('sell_condition_train'), str) and best.get('sell_condition_train') else '固定 T+5 卖出'}`",
            f"- 该方案验证期稳定分为 `{float(best['stability_score_validation']):.4f}`。",
            "",
            "## 输出文件",
            "",
            "- `sell_grid_cases.json`：本轮卖出候选定义",
            "- `train_results.csv`：训练期结果",
            "- `selected_train_cases.csv`：训练期入围方案",
            "- `validation_results.csv`：验证期结果",
            "- `leaderboard.csv`：训练/验证合并后的排行榜",
            "- `sell_grid_summary.md`：本次测试总结书",
            "- `selected_case_trade_records.csv`：推荐卖出方案的逐笔交易记录",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run sell-condition grid tests on a fixed buy condition.")
    parser.add_argument("--processed-dir", default="data_bundle/processed_qfq")
    parser.add_argument("--sell-grid-preset", default="sell_grid_basic_v1")
    parser.add_argument("--buy-condition", default=DEFAULT_BUY_CONDITION)
    parser.add_argument("--score-expression", default=DEFAULT_SCORE_EXPRESSION)
    parser.add_argument("--train-start", default="20190101")
    parser.add_argument("--train-end", default="20221231")
    parser.add_argument("--valid-start", default="20230101")
    parser.add_argument("--valid-end", default="20251231")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--top-n", type=int, default=1)
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

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = build_sell_grid_cases(args.sell_grid_preset)
    case_lookup = {case.name: case for case in cases}
    (out_dir / "sell_grid_cases.json").write_text(
        json.dumps(
            [
                {
                    "name": case.name,
                    "sell_condition": case.sell_condition,
                    "min_hold_days": case.min_hold_days,
                    "max_hold_days": case.max_hold_days,
                    "exit_offset": case.exit_offset,
                    "note": case.note,
                }
                for case in cases
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
        cases=cases,
        loaded=train_loaded,
        diagnostics=train_diagnostics,
        common_kwargs=common_kwargs,
        start_date=args.train_start,
        end_date=args.train_end,
        period="train",
        out_csv=out_dir / "train_results.csv",
        args=args,
    )
    selected_df = _select_train_cases(train_df, top_k=args.top_k)
    selected_df.to_csv(out_dir / "selected_train_cases.csv", index=False, encoding="utf-8-sig")

    selected_cases = [case_lookup[str(row["case"])] for _, row in selected_df.iterrows()]
    valid_df = _run_period(
        cases=selected_cases,
        loaded=valid_loaded,
        diagnostics=valid_diagnostics,
        common_kwargs=common_kwargs,
        start_date=args.valid_start,
        end_date=args.valid_end,
        period="validation",
        out_csv=out_dir / "validation_results.csv",
        args=args,
    )
    leaderboard = _merge_leaderboard(selected_df, valid_df)
    leaderboard.to_csv(out_dir / "leaderboard.csv", index=False, encoding="utf-8-sig")

    _export_trade_records(
        leaderboard=leaderboard,
        case_lookup=case_lookup,
        loaded=valid_loaded,
        diagnostics=valid_diagnostics,
        common_kwargs=common_kwargs,
        start_date=args.valid_start,
        end_date=args.valid_end,
        out_csv=out_dir / "selected_case_trade_records.csv",
        args=args,
        top_k=args.export_top_trades_k,
    )

    summary = {
        "sell_case_count": len(cases),
        "train_case_count": len(train_df),
        "selected_train_case_count": len(selected_df),
        "validation_case_count": len(valid_df),
        "best_case": leaderboard.iloc[0]["case"] if not leaderboard.empty else "",
        "best_stability_score_validation": float(leaderboard.iloc[0]["stability_score_validation"]) if not leaderboard.empty else None,
    }
    (out_dir / "sell_grid_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "sell_grid_summary.md").write_text(
        _render_summary(
            cases=cases,
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
