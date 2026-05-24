from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.stock_pool_feature_store import StockPoolFeatureUpdateConfig, run_stock_daily_raw_collection


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect stock daily raw inputs into SQLite raw tables")
    parser.add_argument("--source", choices=["active_templates", "template", "symbols", "all", "main_universe"], default="all")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--template-name", default="")
    parser.add_argument("--stock-text", default="")
    parser.add_argument("--start-date", default="20220101")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--db-path", default="")
    parser.add_argument("--market-db-path", default="", help="market-data SQLite path")
    parser.add_argument("--log-dir", default="logs/stock_pool_template_update")
    parser.add_argument("--batch-size", type=int, default=0)
    parser.add_argument("--batch-index", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--resume-after-symbol", default="")
    parser.add_argument("--retry-attempts", type=int, default=1)
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0)
    parser.add_argument("--include-up-to-date", action="store_true")
    parser.add_argument("--max-symbols", type=int, default=0)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--force-full-rebuild", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.source == "template" and not args.template_name.strip():
        raise SystemExit("--source template requires --template-name")
    config = StockPoolFeatureUpdateConfig(
        source=args.source,
        job_type="raw_daily_collect",
        username=args.username,
        template_name=args.template_name,
        stock_text=args.stock_text,
        start_date=args.start_date,
        end_date=args.end_date,
        db_path=Path(args.db_path) if args.db_path else None,
        market_db_path=Path(args.market_db_path) if args.market_db_path else None,
        log_dir=Path(args.log_dir),
        max_symbols=args.max_symbols,
        sleep_seconds=args.sleep_seconds,
        batch_size=args.batch_size,
        batch_index=args.batch_index,
        offset=args.offset,
        resume_after_symbol=args.resume_after_symbol,
        retry_attempts=args.retry_attempts,
        retry_sleep_seconds=args.retry_sleep_seconds,
        only_missing=not args.include_up_to_date,
        force_full_rebuild=args.force_full_rebuild,
    )
    summary = run_stock_daily_raw_collection(config)
    printable = {key: value for key, value in summary.items() if key != "items"}
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    if str(summary.get("status", "")).strip().lower() != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
