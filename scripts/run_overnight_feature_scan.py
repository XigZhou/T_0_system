from __future__ import annotations

import argparse
import sys
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


def _default_out_dir() -> Path:
    return Path("research_runs") / "20260419_feature_scan_v1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run stratified overnight feature scan on processed per-stock CSVs.")
    parser.add_argument("--processed-dir", default="data_bundle/processed_qfq")
    parser.add_argument("--start-date", default="20190101")
    parser.add_argument("--end-date", default="20251231")
    parser.add_argument("--buy-fee-rate", type=float, default=0.0003)
    parser.add_argument("--sell-fee-rate", type=float, default=0.0003)
    parser.add_argument("--stamp-tax-sell", type=float, default=0.001)
    parser.add_argument("--slippage-bps", type=float, default=3.0)
    parser.add_argument("--min-commission", type=float, default=5.0)
    parser.add_argument("--per-trade-notional", type=float, default=10_000.0)
    parser.add_argument("--min-count", type=int, default=200)
    parser.add_argument("--strict-executable", action="store_true", default=True)
    parser.add_argument("--out-dir", default=str(_default_out_dir()))
    args = parser.parse_args()

    base = load_feature_scan_frame(
        processed_dir=args.processed_dir,
        start_date=args.start_date,
        end_date=args.end_date,
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
    out_dir = Path(args.out_dir)
    write_feature_scan_outputs(out_dir, overview, report)
    print(f"feature scan rows: {overview['sample_count']}")
    print(f"feature scan output: {out_dir}")


if __name__ == "__main__":
    main()
