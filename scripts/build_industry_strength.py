from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.industry_strength import add_industry_strength_to_processed_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="基于处理后股票日线聚合行业强度指标，并写回处理后 CSV")
    parser.add_argument("--processed-dir", default="data_bundle/processed_qfq_theme_focus_top100", help="处理后股票 CSV 目录")
    parser.add_argument("--output-dir", default="", help="可选；填写后写到新目录，不填写则覆盖 processed-dir")
    parser.add_argument("--report-dir", default="", help="可选；生成报告目录，默认写入 research_runs")
    parser.add_argument("--amount-window", type=int, default=20, help="行业成交额均值窗口")
    parser.add_argument("--amount-min-periods", type=int, default=5, help="行业成交额均值最少样本")
    args = parser.parse_args()

    result = add_industry_strength_to_processed_dir(
        Path(args.processed_dir),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        report_dir=Path(args.report_dir) if args.report_dir else None,
        amount_window=args.amount_window,
        amount_min_periods=args.amount_min_periods,
    )
    print(
        "行业强度指标生成完成："
        f"文件 {result.file_count} 个，行 {result.row_count} 条，"
        f"行业 {result.industry_count} 个，报告 {result.report_dir}"
    )


if __name__ == "__main__":
    main()
