from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.processing import build_processed_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Build processed per-stock qfq CSVs for the overnight backtest system")
    parser.add_argument("--bundle-dir", default="/home/ubuntu/T_0_system/data_bundle")
    parser.add_argument("--output-dir", default="/home/ubuntu/T_0_system/data_bundle/processed_qfq")
    parser.add_argument("--snapshot-csv", default="")
    args = parser.parse_args()

    results = build_processed_dataset(
        bundle_dir=Path(args.bundle_dir),
        output_dir=Path(args.output_dir),
        snapshot_csv=Path(args.snapshot_csv) if args.snapshot_csv.strip() else None,
    )
    ok_count = sum(1 for item in results if item.status == "ok")
    print(f"processed: {ok_count}/{len(results)}")


if __name__ == "__main__":
    main()
