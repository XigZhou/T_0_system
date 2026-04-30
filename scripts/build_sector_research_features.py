from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sector_research.integration import merge_sector_features_to_processed_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="把独立板块研究结果合入处理后股票 CSV 的副本目录")
    parser.add_argument("--processed-dir", required=True, help="现有处理后股票 CSV 目录，例如 data_bundle/processed_qfq_theme_focus_top100")
    parser.add_argument("--sector-processed-dir", default="sector_research/data/processed", help="板块研究处理后数据目录")
    parser.add_argument("--output-dir", required=True, help="增强后的输出目录；必须不同于 --processed-dir")
    args = parser.parse_args()

    result = merge_sector_features_to_processed_dir(
        processed_dir=args.processed_dir,
        sector_processed_dir=args.sector_processed_dir,
        output_dir=args.output_dir,
    )
    print(
        "板块研究特征合并完成："
        f"股票文件 {result.stock_files} 个，命中主题 {result.matched_files} 个，"
        f"未命中 {result.unmatched_files} 个，写入 {result.rows_written} 行，"
        f"输出目录 {result.output_dir}，清单 {result.manifest_path}"
    )


if __name__ == "__main__":
    main()
