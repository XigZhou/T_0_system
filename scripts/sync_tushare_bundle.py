from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.tushare_data import SyncConfig, sync_tushare_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description="Download raw tushare bundle for the overnight backtest system")
    parser.add_argument("--env", default="D:/量化/Momentum/code/tushare/.env")
    parser.add_argument("--bundle-dir", default="D:/量化/Momentum/T_0_system/data_bundle")
    parser.add_argument("--snapshot-csv", default="D:/量化/Momentum/T_0_system/data_bundle/universe_snapshot.csv")
    parser.add_argument("--start-date", default="20160101")
    parser.add_argument("--end-date", default="20260417")
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    args = parser.parse_args()

    result = sync_tushare_bundle(
        SyncConfig(
            env_path=Path(args.env),
            bundle_dir=Path(args.bundle_dir),
            snapshot_csv=Path(args.snapshot_csv),
            start_date=str(args.start_date).strip(),
            end_date=str(args.end_date).strip(),
            sleep_seconds=float(args.sleep_seconds),
        )
    )
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
