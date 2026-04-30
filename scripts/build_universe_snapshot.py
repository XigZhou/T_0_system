from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.tushare_data import SnapshotBuildConfig, build_universe_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Build fixed universe snapshot for the overnight backtest system")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--out", default="data_bundle/universe_snapshot.csv")
    parser.add_argument("--as-of", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--min-mv-yi", type=float, default=500.0)
    args = parser.parse_args()

    path = build_universe_snapshot(
        SnapshotBuildConfig(
            env_path=Path(args.env),
            out_csv=Path(args.out),
            as_of=str(args.as_of).strip(),
            min_mv_yi=float(args.min_mv_yi),
        )
    )
    print(path)


if __name__ == "__main__":
    main()
