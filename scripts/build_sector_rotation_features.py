from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.backtest import load_processed_folder
from overnight_bt.sector_features import validate_sector_feature_set
from scripts.run_sector_rotation_grid import load_rotation_daily, merge_rotation_features


def _resolve(path_text: str | Path) -> Path:
    path = Path(str(path_text)).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def _prepare_output_dir(input_dir: Path, output_dir: Path, *, overwrite: bool) -> None:
    if input_dir == output_dir:
        raise ValueError("output_dir 不能和 sector_processed_dir 相同，避免覆盖板块增强主数据")
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"输出目录已存在，如需重建请加 --overwrite: {output_dir}")
        if ROOT not in output_dir.parents:
            raise ValueError(f"拒绝清理项目目录之外的路径: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def build_sector_rotation_features(
    *,
    sector_processed_dir: str | Path,
    rotation_daily_path: str | Path,
    output_dir: str | Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    source_dir = _resolve(sector_processed_dir)
    rotation_path = _resolve(rotation_daily_path)
    target_dir = _resolve(output_dir)
    _prepare_output_dir(source_dir, target_dir, overwrite=overwrite)

    loaded, diagnostics = load_processed_folder(str(source_dir))
    diagnostics.update(validate_sector_feature_set(loaded_items=loaded, processed_dir=diagnostics["processed_dir"]))
    rotation_daily = load_rotation_daily(rotation_path)
    merged = merge_rotation_features(loaded, rotation_daily)

    rotation_columns = sorted(column for column in merged[0].df.columns if column.startswith("rotation_") or column.startswith("stock_matches_rotation_") or column == "stock_theme_cluster") if merged else []
    manifest_rows: list[dict[str, Any]] = []
    for item in merged:
        out_file = target_dir / f"{item.symbol}.csv"
        item.df.to_csv(out_file, index=False, encoding="utf-8-sig")
        available = item.df[[column for column in ["trade_date", "rotation_state", "rotation_top_theme", "rotation_top_cluster"] if column in item.df.columns]].dropna(how="all")
        manifest_rows.append(
            {
                "symbol": item.symbol,
                "name": item.name,
                "row_count": len(item.df),
                "first_trade_date": str(item.df["trade_date"].iloc[0]) if not item.df.empty else "",
                "last_trade_date": str(item.df["trade_date"].iloc[-1]) if not item.df.empty else "",
                "rotation_matched_rows": int(available["rotation_state"].notna().sum()) if "rotation_state" in available.columns else 0,
            }
        )

    for sidecar in ["sector_feature_manifest.csv", "processing_manifest.csv"]:
        src = source_dir / sidecar
        if src.exists():
            shutil.copy2(src, target_dir / sidecar)

    rotation_manifest = pd.DataFrame(manifest_rows)
    rotation_manifest.to_csv(target_dir / "rotation_feature_manifest.csv", index=False, encoding="utf-8-sig")
    metadata = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "sector_processed_dir": str(source_dir),
        "rotation_daily_path": str(rotation_path),
        "output_dir": str(target_dir),
        "stock_files": len(merged),
        "rotation_columns": rotation_columns,
    }
    (target_dir / "rotation_feature_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把板块轮动诊断字段合并到板块增强股票 CSV 副本目录")
    parser.add_argument("--sector-processed-dir", default="data_bundle/processed_qfq_theme_focus_top100_sector")
    parser.add_argument("--rotation-daily-path", default="research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv")
    parser.add_argument("--output-dir", default="data_bundle/processed_qfq_theme_focus_top100_sector_rotation")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    result = build_sector_rotation_features(**vars(parse_args(argv)))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
