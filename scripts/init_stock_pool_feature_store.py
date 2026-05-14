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
    parser = argparse.ArgumentParser(description="初始化股票池共享日线与指标库")
    parser.add_argument("--source", choices=["all", "active_templates", "template", "symbols"], default="all")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--template-name", default="")
    parser.add_argument("--stock-text", default="")
    parser.add_argument("--start-date", default="20220101")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--db-path", default="")
    parser.add_argument("--log-dir", default="logs/stock_pool_template_update")
    parser.add_argument("--batch-size", type=int, default=0, help="每批处理股票数，0 表示不按批次切分")
    parser.add_argument("--batch-index", type=int, default=0, help="批次序号，从 0 开始；batch-size>0 时生效")
    parser.add_argument("--offset", type=int, default=0, help="从待处理列表的第 N 只开始；填写后优先于 batch-index 计算起点")
    parser.add_argument("--resume-after-symbol", default="", help="断点续跑：从指定股票代码之后继续")
    parser.add_argument("--retry-attempts", type=int, default=1, help="单只股票失败重试次数，至少 1")
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0, help="失败重试基础等待秒数，第 N 次按 N 倍等待")
    parser.add_argument("--include-up-to-date", action="store_true", help="包含已更新到截止日的股票；默认只补缺失")
    parser.add_argument("--max-symbols", type=int, default=0, help="测试或分批补数时限制股票数量，0 表示不限")
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--force-full-rebuild", action="store_true")
    args = parser.parse_args()

    config = StockPoolFeatureUpdateConfig(
        source=args.source,
        job_type="initial_load",
        username=args.username,
        template_name=args.template_name,
        stock_text=args.stock_text,
        start_date=args.start_date,
        end_date=args.end_date,
        db_path=Path(args.db_path) if args.db_path else None,
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
    summary = run_stock_pool_feature_update(config)
    print(json.dumps({k: v for k, v in summary.items() if k != "items"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
