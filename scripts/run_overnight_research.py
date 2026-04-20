from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.backtest import load_processed_folder, run_portfolio_backtest_loaded
from overnight_bt.models import BacktestRequest
from overnight_bt.research import build_neighborhood_cases, select_train_top_cases, summarize_case_result


def _default_out_dir() -> Path:
    return Path("research_runs") / "20260419_train_valid_v1"


def _common_request_kwargs(args: argparse.Namespace) -> dict:
    return {
        "processed_dir": args.processed_dir,
        "initial_cash": args.initial_cash,
        "lot_size": args.lot_size,
        "buy_fee_rate": args.buy_fee_rate,
        "sell_fee_rate": args.sell_fee_rate,
        "stamp_tax_sell": args.stamp_tax_sell,
        "realistic_execution": args.realistic_execution,
        "slippage_bps": args.slippage_bps,
        "min_commission": args.min_commission,
    }


def _run_period(
    cases: list,
    loaded: list,
    diagnostics: dict,
    common_kwargs: dict,
    start_date: str,
    end_date: str,
    period: str,
    out_csv: Path,
) -> pd.DataFrame:
    rows: list[dict] = []
    total = len(cases)
    for idx, case in enumerate(cases, start=1):
        print(f"[{period}] case {idx}/{total}: {case.name}")
        req = BacktestRequest(
            start_date=start_date,
            end_date=end_date,
            buy_condition=case.buy_condition,
            score_expression=case.score_expression,
            top_n=case.top_n,
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
                    "annualized_return": row["annualized_return"],
                    "max_drawdown": row["max_drawdown"],
                    "sell_count": row["sell_count"],
                    "active_day_ratio": row["active_day_ratio"],
                },
                ensure_ascii=False,
            )
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run neighborhood research for overnight T+1 strategy.")
    parser.add_argument("--processed-dir", default="data_bundle/processed_qfq")
    parser.add_argument("--preset", default="baseline_v1")
    parser.add_argument("--train-start", default="20190101")
    parser.add_argument("--train-end", default="20221231")
    parser.add_argument("--valid-start", default="20230101")
    parser.add_argument("--valid-end", default="20251231")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--lot-size", type=int, default=100)
    parser.add_argument("--buy-fee-rate", type=float, default=0.0003)
    parser.add_argument("--sell-fee-rate", type=float, default=0.0003)
    parser.add_argument("--stamp-tax-sell", type=float, default=0.001)
    parser.add_argument("--slippage-bps", type=float, default=3.0)
    parser.add_argument("--min-commission", type=float, default=5.0)
    parser.add_argument("--realistic-execution", action="store_true", default=True)
    parser.add_argument("--out-dir", default=str(_default_out_dir()))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = build_neighborhood_cases(preset=args.preset)
    (out_dir / "case_definitions.json").write_text(
        json.dumps([case.__dict__ for case in cases], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"loading train dataset: {args.train_start} - {args.train_end}")
    train_loaded, train_diagnostics = load_processed_folder(args.processed_dir, args.train_start, args.train_end)
    print(f"loading validation dataset: {args.valid_start} - {args.valid_end}")
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
    )
    selected = select_train_top_cases(train_df, top_k=args.top_k)
    selected.to_csv(out_dir / "selected_train_cases.csv", index=False, encoding="utf-8-sig")

    selected_cases = [case for case in cases if case.name in set(selected["case"].tolist())]
    valid_df = _run_period(
        cases=selected_cases,
        loaded=valid_loaded,
        diagnostics=valid_diagnostics,
        common_kwargs=common_kwargs,
        start_date=args.valid_start,
        end_date=args.valid_end,
        period="validation",
        out_csv=out_dir / "validation_results.csv",
    )

    leaderboard = selected.merge(
        valid_df,
        on="case",
        how="left",
        suffixes=("_train", "_validation"),
    )
    leaderboard = leaderboard.sort_values(
        ["annualized_return_validation", "max_drawdown_validation"],
        ascending=[False, True],
    ).reset_index(drop=True)
    leaderboard.to_csv(out_dir / "leaderboard.csv", index=False, encoding="utf-8-sig")

    summary = {
        "case_count_train": len(train_df),
        "case_count_validation": len(valid_df),
        "top_k": args.top_k,
        "best_validation_case": leaderboard.iloc[0]["case"] if not leaderboard.empty else "",
    }
    (out_dir / "research_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
