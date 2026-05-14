from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.stock_pool_feature_store import StockPoolFeatureUpdateConfig, run_stock_pool_feature_update


def main() -> None:
    parser = argparse.ArgumentParser(description="更新股票池模板涉及股票的共享日线与指标库")
    parser.add_argument("--source", choices=["active_templates", "template", "symbols", "all"], default="active_templates")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--template-name", default="")
    parser.add_argument("--stock-text", default="")
    parser.add_argument("--start-date", default="20220101")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--db-path", default="")
    parser.add_argument("--log-dir", default="logs/stock_pool_template_update")
    parser.add_argument("--max-symbols", type=int, default=0)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--force-full-rebuild", action="store_true")
    args = parser.parse_args()

    if args.source == "template" and not args.template_name.strip():
        raise SystemExit("--source template 时必须提供 --template-name")

    config = StockPoolFeatureUpdateConfig(
        source=args.source,
        job_type="daily_update" if args.source == "active_templates" else "manual_refresh",
        username=args.username,
        template_name=args.template_name,
        stock_text=args.stock_text,
        start_date=args.start_date,
        end_date=args.end_date,
        db_path=Path(args.db_path) if args.db_path else None,
        log_dir=Path(args.log_dir),
        max_symbols=args.max_symbols,
        sleep_seconds=args.sleep_seconds,
        force_full_rebuild=args.force_full_rebuild,
    )
    summary = run_stock_pool_feature_update(config)
    print(json.dumps({k: v for k, v in summary.items() if k != "items"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
