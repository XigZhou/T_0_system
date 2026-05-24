from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.sqlite_runtime_reset import RuntimeResetPaths, soft_reset_runtime, summary_json


def main() -> None:
    parser = argparse.ArgumentParser(description="\u8f6f\u91cd\u7f6e SQLite \u8fd0\u884c\u6570\u636e\uff0c\u5e76\u79cd\u5165\u5355\u80a1\u7968\u521d\u59cb\u5316\u6837\u672c")
    parser.add_argument("--execute", action="store_true", help="\u771f\u6b63\u6267\u884c\u6e05\u7406\uff1b\u9ed8\u8ba4\u4ec5\u505a dry-run")
    parser.add_argument("--market-db", default="data_store/market_data.sqlite")
    parser.add_argument("--stock-pool-db", default="data_store/stock_pool_templates.sqlite")
    parser.add_argument("--paper-db", default="data_store/paper_trading.sqlite")
    parser.add_argument("--scheduler-db", default="data_store/scheduler.sqlite")
    parser.add_argument("--backup-root", default="data_store/backups")
    parser.add_argument("--skip-backup", action="store_true", help="??????? SQLite ????????????????????????")
    args = parser.parse_args()

    summary = soft_reset_runtime(
        paths=RuntimeResetPaths(
            market_db_path=Path(args.market_db),
            stock_pool_db_path=Path(args.stock_pool_db),
            paper_db_path=Path(args.paper_db),
            scheduler_db_path=Path(args.scheduler_db),
            backup_root=Path(args.backup_root),
        ),
        execute=args.execute,
        backup=not args.skip_backup,
    )
    print(summary_json(summary))


if __name__ == "__main__":
    main()
