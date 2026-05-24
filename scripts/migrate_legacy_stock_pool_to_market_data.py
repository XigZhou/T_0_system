from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overnight_bt.market_data_store import migrate_legacy_stock_pool_to_market_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="迁移旧股票池特征表到 market_data.sqlite 主数据表")
    parser.add_argument("--legacy-db", default="data_store/stock_pool_templates.sqlite", help="旧股票池 SQLite 路径")
    parser.add_argument("--market-db", default="data_store/market_data.sqlite", help="目标主数据 SQLite 路径")
    parser.add_argument("--source", default="legacy_template_migration", help="写入主股票池的来源标记")
    parser.add_argument("--batch-size", type=int, default=5000, help="stock_daily_features 分批复制行数")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = migrate_legacy_stock_pool_to_market_data(
        legacy_db_path=Path(args.legacy_db),
        market_db_path=Path(args.market_db),
        source=args.source,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
