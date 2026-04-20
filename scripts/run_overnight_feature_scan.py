from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.feature_scan import (
    apply_research_net_return,
    build_feature_bucket_report,
    build_scan_overview,
    load_feature_scan_frame,
    write_feature_scan_outputs,
)


def _default_out_dir(exit_offset: int) -> Path:
    return Path("research_runs") / f"{date.today():%Y%m%d}_feature_scan_n{exit_offset}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run stratified feature scan for T-day signals and T+N open exits.")
    parser.add_argument("--processed-dir", default="data_bundle/processed_qfq")
    parser.add_argument("--start-date", default="20190101")
    parser.add_argument("--end-date", default="20251231")
    parser.add_argument("--entry-offset", type=int, default=1)
    parser.add_argument("--exit-offset", type=int, default=2)
    parser.add_argument("--buy-fee-rate", type=float, default=0.00003)
    parser.add_argument("--sell-fee-rate", type=float, default=0.00003)
    parser.add_argument("--stamp-tax-sell", type=float, default=0.0)
    parser.add_argument("--slippage-bps", type=float, default=3.0)
    parser.add_argument("--min-commission", type=float, default=0.0)
    parser.add_argument("--per-trade-notional", type=float, default=10_000.0)
    parser.add_argument("--min-count", type=int, default=200)
    parser.add_argument("--strict-executable", dest="strict_executable", action="store_true")
    parser.add_argument("--no-strict-executable", dest="strict_executable", action="store_false")
    parser.add_argument("--out-dir", default="")
    parser.set_defaults(strict_executable=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir) if str(args.out_dir).strip() else _default_out_dir(args.exit_offset)
    base = load_feature_scan_frame(
        processed_dir=args.processed_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        entry_offset=args.entry_offset,
        exit_offset=args.exit_offset,
        strict_executable=args.strict_executable,
    )
    enriched = apply_research_net_return(
        base,
        buy_fee_rate=args.buy_fee_rate,
        sell_fee_rate=args.sell_fee_rate,
        stamp_tax_sell=args.stamp_tax_sell,
        slippage_bps=args.slippage_bps,
        min_commission=args.min_commission,
        per_trade_notional=args.per_trade_notional,
    )
    report = build_feature_bucket_report(enriched, min_count=args.min_count)
    overview = build_scan_overview(enriched)
    write_feature_scan_outputs(
        out_dir,
        overview,
        report,
        entry_offset=args.entry_offset,
        exit_offset=args.exit_offset,
    )
    print(f"feature scan rows: {overview['sample_count']}")
    print(f"feature scan output: {out_dir}")


if __name__ == "__main__":
    main()
