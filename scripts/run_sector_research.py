from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sector_research.pipeline import run_sector_research


def main() -> None:
    parser = argparse.ArgumentParser(description="独立板块研究系统：抓取 AKShare 板块数据并生成主题强度与报告")
    parser.add_argument("--config", default="sector_research/configs/themes.yaml", help="主题配置 YAML")
    parser.add_argument("--start-date", default="20230101", help="历史起始日期 YYYYMMDD")
    parser.add_argument("--end-date", default="", help="历史结束日期 YYYYMMDD；留空使用今天")
    parser.add_argument("--raw-dir", default="sector_research/data/raw", help="原始标准化数据输出目录")
    parser.add_argument("--processed-dir", default="sector_research/data/processed", help="处理后指标输出目录")
    parser.add_argument("--report-dir", default="sector_research/reports", help="报告输出目录")
    parser.add_argument("--skip-constituents", action="store_true", help="跳过板块成分股抓取，加快调试")
    args = parser.parse_args()

    result = run_sector_research(
        config_path=args.config,
        start_date=args.start_date,
        end_date=args.end_date,
        raw_dir=args.raw_dir,
        processed_dir=args.processed_dir,
        report_dir=args.report_dir,
        fetch_constituents=not args.skip_constituents,
    )
    print(
        "板块研究完成："
        f"板块 {result.board_count} 个，板块日线 {result.board_daily_rows} 行，"
        f"主题日线 {result.theme_daily_rows} 行，成分股 {result.constituent_rows} 行，"
        f"最新日期 {result.latest_trade_date}，报告目录 {result.report_dir}"
    )


if __name__ == "__main__":
    main()
