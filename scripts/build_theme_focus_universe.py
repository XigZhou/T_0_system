from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.universe_filters import write_theme_focus_outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a theme-focused universe and filtered processed_qfq directory.")
    parser.add_argument("--snapshot-csv", default="data_bundle/universe_snapshot.csv")
    parser.add_argument("--processed-dir", default="data_bundle/processed_qfq")
    parser.add_argument("--out-snapshot", default="data_bundle/universe_snapshot_theme_focus.csv")
    parser.add_argument("--out-processed-dir", default="data_bundle/processed_qfq_theme_focus")
    parser.add_argument("--top-k", type=int, default=0, help="Optional top-k by total_mv after theme filtering. 0 means no cap.")
    args = parser.parse_args()

    snapshot_df = pd.read_csv(args.snapshot_csv, encoding="utf-8-sig", dtype=str)
    result = write_theme_focus_outputs(
        snapshot_df=snapshot_df,
        processed_source_dir=Path(args.processed_dir),
        out_snapshot_path=Path(args.out_snapshot),
        out_processed_dir=Path(args.out_processed_dir),
        top_k=args.top_k if args.top_k > 0 else None,
    )
    print(
        json.dumps(
            {
                "snapshot_path": result.snapshot_path,
                "processed_dir": result.processed_dir,
                "selected_count": result.selected_count,
                "selected_symbols_preview": result.selected_symbols[:20],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
