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
class UniverseCase:
    name: str
    processed_dir: str
    note: str


def _default_out_dir() -> Path:
    return Path("research_runs") / f"{date.today():%Y%m%d}_universe_hold_compare_v1"


def build_universe_cases() -> list[UniverseCase]:
    return [
        UniverseCase("full_universe", "data_bundle/processed_qfq", "原始全量大市值股票池"),
        UniverseCase("theme_focus", "data_bundle/processed_qfq_theme_focus", "主题聚焦全量池"),
        UniverseCase("theme_focus_top100", "data_bundle/processed_qfq_theme_focus_top100", "主题聚焦前100市值池"),
    ]


def _common_request_kwargs(args: argparse.Namespace) -> dict:
    return {
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


def _run_case(
    universe_case: UniverseCase,
    exit_offset: int,
    period: str,
    start_date: str,
    end_date: str,
    args: argparse.Namespace,
    common_kwargs: dict,
) -> tuple[dict, dict]:
    loaded, diagnostics = load_processed_folder(universe_case.processed_dir, start_date, end_date)
    req = BacktestRequest(
        processed_dir=universe_case.processed_dir,
        start_date=start_date,
        end_date=end_date,
        buy_condition=args.buy_condition,
        score_expression=args.score_expression,
        exit_offset=exit_offset,
        **common_kwargs,
    )
    result = run_portfolio_backtest_loaded(loaded, diagnostics, req)
    row = summarize_case_result(
        f"{universe_case.name}_n{exit_offset}",
        period,
        args.buy_condition,
        args.score_expression,
        args.top_n,
        result,
    )
    row["universe_name"] = universe_case.name
    row["processed_dir"] = universe_case.processed_dir
    row["universe_note"] = universe_case.note
    row["exit_offset"] = exit_offset
    return row, result


def _run_period(
    universe_cases: list[UniverseCase],
    exit_offsets: list[int],
    period: str,
    start_date: str,
    end_date: str,
    args: argparse.Namespace,
    common_kwargs: dict,
    out_csv: Path,
) -> pd.DataFrame:
    rows: list[dict] = []
    total = len(universe_cases) * len(exit_offsets)
    seq = 0
    for universe_case in universe_cases:
        for exit_offset in exit_offsets:
            seq += 1
            print(f"[{period}] case {seq}/{total}: {universe_case.name} | T+{exit_offset} open")
            row, _ = _run_case(
                universe_case=universe_case,
                exit_offset=exit_offset,
                period=period,
                start_date=start_date,
                end_date=end_date,
                args=args,
                common_kwargs=common_kwargs,
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
    leaderboard["universe_name"] = leaderboard["universe_name_train"].fillna(leaderboard.get("universe_name_validation"))
    leaderboard["exit_offset"] = leaderboard["exit_offset_validation"].fillna(leaderboard["exit_offset_train"])
    leaderboard = add_stability_columns(leaderboard, suffix="_validation")
    leaderboard = leaderboard.sort_values(
        ["stable_pass_validation", "stability_score_validation", "annualized_return_validation", "max_drawdown_validation"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    return leaderboard


def _export_trade_records(
    leaderboard: pd.DataFrame,
    universe_case_lookup: dict[str, UniverseCase],
    args: argparse.Namespace,
    common_kwargs: dict,
    out_csv: Path,
    top_k: int,
) -> None:
    frames: list[pd.DataFrame] = []
    for _, row in leaderboard.head(top_k).iterrows():
        universe_case = universe_case_lookup[str(row["universe_name"])]
        _, result = _run_case(
            universe_case=universe_case,
            exit_offset=int(row["exit_offset"]),
            period="validation_export",
            start_date=args.valid_start,
            end_date=args.valid_end,
            args=args,
            common_kwargs=common_kwargs,
        )
        trade_rows = pd.DataFrame(result.get("trade_rows", []))
        if trade_rows.empty:
            continue
        trade_rows.insert(0, "period", "validation")
        trade_rows.insert(1, "universe_name", universe_case.name)
        trade_rows.insert(2, "exit_offset", int(row["exit_offset"]))
        frames.append(trade_rows)
    if frames:
        pd.concat(frames, ignore_index=True).to_csv(out_csv, index=False, encoding="utf-8-sig")
        return
    pd.DataFrame(
        columns=[
            "period",
            "universe_name",
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
    universe_cases: list[UniverseCase],
    exit_offsets: list[int],
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    leaderboard: pd.DataFrame,
    args: argparse.Namespace,
) -> str:
    lines = [
        "# 股票池与固定持有期对比总结书",
        "",
        "## 本次测试目标",
        "",
        "- 固定当前最优 Top1 买入条件",
        "- 比较不同股票池和不同固定持有天数的表现差异",
        "",
        "## 固定买入配置",
        "",
        f"- 买入条件：`{args.buy_condition}`",
        f"- 评分表达式：`{args.score_expression}`",
        f"- TopN：`{args.top_n}`",
        f"- 买入偏移：`T+{args.entry_offset}` 开盘",
        "",
        "## 本轮股票池",
        "",
    ]
    for universe_case in universe_cases:
        lines.append(f"- `{universe_case.name}`：{universe_case.note}，目录 `{universe_case.processed_dir}`")

    lines.extend(
        [
            "",
            "## 本轮固定持有天数",
            "",
            "- " + " / ".join(f"`T+{offset}`" for offset in exit_offsets),
            "",
            "## 训练期与验证期组合数量",
            "",
            f"- 训练期结果数：{len(train_df)}",
            f"- 验证期结果数：{len(valid_df)}",
            "",
            "## 验证期排行榜",
            "",
        ]
    )

    for rank, (_, row) in enumerate(leaderboard.head(12).iterrows(), start=1):
        lines.append(
            f"{rank}. 股票池 `{row['universe_name']}` / `T+{int(row['exit_offset'])}` / 稳定通过=`{bool(row['stable_pass_validation'])}`"
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
            f"- 当前最优组合是股票池 `{best['universe_name']}` 搭配 `T+{int(best['exit_offset'])}` 固定卖出。",
            f"- 该组合验证期稳定分为 `{float(best['stability_score_validation']):.4f}`。",
            "",
            "## 输出文件",
            "",
            "- `train_results.csv`：训练期对比结果",
            "- `validation_results.csv`：验证期对比结果",
            "- `leaderboard.csv`：验证期排序结果",
            "- `universe_hold_summary.md`：本次对比总结书",
            "- `selected_case_trade_records.csv`：前几名组合的逐笔交易记录",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare fixed holding periods across multiple universes on a fixed Top1 strategy.")
    parser.add_argument("--buy-condition", default=DEFAULT_BUY_CONDITION)
    parser.add_argument("--score-expression", default=DEFAULT_SCORE_EXPRESSION)
    parser.add_argument("--train-start", default="20190101")
    parser.add_argument("--train-end", default="20221231")
    parser.add_argument("--valid-start", default="20230101")
    parser.add_argument("--valid-end", default="20251231")
    parser.add_argument("--exit-offsets", default="4,5,6,7")
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

    exit_offsets = sorted({int(token.strip()) for token in args.exit_offsets.split(",") if token.strip()})
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    universe_cases = build_universe_cases()
    universe_case_lookup = {case.name: case for case in universe_cases}
    common_kwargs = _common_request_kwargs(args)

    train_df = _run_period(
        universe_cases=universe_cases,
        exit_offsets=exit_offsets,
        period="train",
        start_date=args.train_start,
        end_date=args.train_end,
        args=args,
        common_kwargs=common_kwargs,
        out_csv=out_dir / "train_results.csv",
    )
    valid_df = _run_period(
        universe_cases=universe_cases,
        exit_offsets=exit_offsets,
        period="validation",
        start_date=args.valid_start,
        end_date=args.valid_end,
        args=args,
        common_kwargs=common_kwargs,
        out_csv=out_dir / "validation_results.csv",
    )
    leaderboard = _merge_leaderboard(train_df, valid_df)
    leaderboard.to_csv(out_dir / "leaderboard.csv", index=False, encoding="utf-8-sig")

    _export_trade_records(
        leaderboard=leaderboard,
        universe_case_lookup=universe_case_lookup,
        args=args,
        common_kwargs=common_kwargs,
        out_csv=out_dir / "selected_case_trade_records.csv",
        top_k=args.export_top_trades_k,
    )

    summary = {
        "universe_case_count": len(universe_cases),
        "exit_offsets": exit_offsets,
        "best_universe": leaderboard.iloc[0]["universe_name"] if not leaderboard.empty else "",
        "best_exit_offset": int(leaderboard.iloc[0]["exit_offset"]) if not leaderboard.empty else None,
        "best_stability_score_validation": float(leaderboard.iloc[0]["stability_score_validation"]) if not leaderboard.empty else None,
    }
    (out_dir / "universe_hold_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "universe_hold_summary.md").write_text(
        _render_summary(
            universe_cases=universe_cases,
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
