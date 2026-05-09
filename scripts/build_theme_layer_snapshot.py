from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.theme_universe import normalize_symbol, normalize_ts_code  # noqa: E402


SNAPSHOT_COLUMNS = [
    "ts_code",
    "symbol",
    "name",
    "area",
    "industry",
    "market",
    "list_date",
    "close",
    "total_mv",
    "turnover_rate_f",
    "pe_ttm",
    "pb",
]


def _resolve(path_text: str | Path) -> Path:
    path = Path(str(path_text)).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def _parse_layers(value: str) -> set[str]:
    layers = {item.strip().upper() for item in str(value or "").split(",") if item.strip()}
    if not layers:
        raise ValueError("--layers 至少需要包含一个层级，例如 L0,L1,L2,L3,L4")
    return layers


def build_theme_layer_snapshot(
    *,
    layers_csv: str | Path,
    out_csv: str | Path,
    layers: set[str] | None = None,
    pool_name: str = "",
) -> dict[str, object]:
    source = _resolve(layers_csv)
    target = _resolve(out_csv)
    if not source.exists():
        raise FileNotFoundError(f"主题分层明细文件不存在: {source}")

    frame = pd.read_csv(source, dtype=str, encoding="utf-8-sig").fillna("")
    missing = [column for column in SNAPSHOT_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"主题分层明细缺少生成取数快照所需字段: {missing}")

    work = frame.copy()
    if layers is not None:
        if "layer" not in work.columns:
            raise ValueError("使用 --layers 时，输入文件必须包含 layer 字段")
        work = work[work["layer"].astype(str).str.upper().isin(layers)].copy()

    if pool_name and "pool_name" in work.columns:
        work = work[work["pool_name"].astype(str).str.strip() == str(pool_name).strip()].copy()

    if work.empty:
        raise ValueError("按 layers/pool_name 过滤后没有可输出股票")

    work["symbol"] = work["symbol"].map(normalize_symbol)
    work["ts_code"] = work["ts_code"].where(work["ts_code"].astype(str).str.strip() != "", work["symbol"].map(normalize_ts_code))
    work["ts_code"] = work["ts_code"].map(normalize_ts_code)
    work = work[(work["symbol"] != "") & (work["ts_code"] != "")].copy()
    if work.empty:
        raise ValueError("输入文件中没有有效 symbol/ts_code")

    for column in ["close", "total_mv", "turnover_rate_f", "pe_ttm", "pb"]:
        work[column] = pd.to_numeric(work[column], errors="coerce")

    work = work.drop_duplicates("symbol", keep="first").copy()
    sort_columns = [column for column in ["pool_rank", "tradeable_rank", "total_mv", "symbol"] if column in work.columns]
    if "pool_rank" in work.columns:
        work["pool_rank"] = pd.to_numeric(work["pool_rank"], errors="coerce")
    if "tradeable_rank" in work.columns:
        work["tradeable_rank"] = pd.to_numeric(work["tradeable_rank"], errors="coerce")
    if sort_columns:
        ascending = [True if column in {"pool_rank", "tradeable_rank", "symbol"} else False for column in sort_columns]
        work = work.sort_values(sort_columns, ascending=ascending)

    target.parent.mkdir(parents=True, exist_ok=True)
    output = work[SNAPSHOT_COLUMNS].copy()
    output.to_csv(target, index=False, encoding="utf-8-sig")

    manifest = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(source),
        "output": str(target),
        "rows": int(len(output)),
        "layers": sorted(layers) if layers is not None else "all",
        "pool_name": pool_name,
        "columns": SNAPSHOT_COLUMNS,
    }
    manifest_path = target.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert theme tradeable TopN L0-L4 layer CSV to a Tushare sync snapshot.")
    parser.add_argument("--layers-csv", default="sector_research/data/processed/theme_tradeable_universe/theme_tradeable_top500_layers.csv")
    parser.add_argument("--out", default="data_bundle/theme_tradeable_top500_4y/universe_snapshot_top500.csv")
    parser.add_argument("--layers", default="L0,L1,L2,L3,L4", help="Comma separated layer list, for example L0,L1,L2,L3,L4 or L2.")
    parser.add_argument("--pool-name", default="", help="Optional pool_name filter, for example Top500.")
    args = parser.parse_args()

    manifest = build_theme_layer_snapshot(
        layers_csv=args.layers_csv,
        out_csv=args.out,
        layers=_parse_layers(args.layers),
        pool_name=str(args.pool_name).strip(),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
