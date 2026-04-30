from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


STATIC_FEATURE_COLUMNS = [
    "sector_theme_names",
    "sector_subtheme_names",
    "sector_board_names",
    "sector_theme_count",
    "sector_subtheme_count",
    "sector_board_count",
    "sector_exposure_score",
]

DAILY_FEATURE_COLUMNS = [
    "sector_strongest_theme",
    "sector_strongest_theme_rank",
    "sector_strongest_theme_rank_pct",
    "sector_strongest_theme_score",
    "sector_strongest_theme_m5",
    "sector_strongest_theme_m20",
    "sector_strongest_theme_m60",
    "sector_strongest_theme_amount_ratio_20",
    "sector_strongest_theme_board_up_ratio",
    "sector_strongest_theme_positive_m20_ratio",
    "sector_strongest_board",
    "sector_strongest_subtheme",
]


@dataclass(frozen=True)
class SectorFeatureMergeResult:
    processed_dir: str
    sector_processed_dir: str
    output_dir: str
    stock_files: int
    matched_files: int
    unmatched_files: int
    rows_written: int
    manifest_path: str


def merge_sector_features_to_processed_dir(
    *,
    processed_dir: str | Path,
    sector_processed_dir: str | Path = "sector_research/data/processed",
    output_dir: str | Path,
) -> SectorFeatureMergeResult:
    """Write a separate processed stock directory enriched with sector research fields."""

    processed_dir = Path(processed_dir)
    sector_processed_dir = Path(sector_processed_dir)
    output_dir = Path(output_dir)
    if not processed_dir.exists():
        raise FileNotFoundError(f"处理后股票目录不存在: {processed_dir}")
    if output_dir.resolve() == processed_dir.resolve():
        raise ValueError("板块研究特征必须写入独立输出目录，不能覆盖原 processed_dir")
    output_dir.mkdir(parents=True, exist_ok=True)

    exposure_path = sector_processed_dir / "stock_theme_exposure.csv"
    theme_strength_path = sector_processed_dir / "theme_strength_daily.csv"
    if not exposure_path.exists():
        raise FileNotFoundError(f"缺少个股主题暴露文件: {exposure_path}")
    if not theme_strength_path.exists():
        raise FileNotFoundError(f"缺少主题强度日线文件: {theme_strength_path}")

    exposure = pd.read_csv(exposure_path, dtype=str, encoding="utf-8-sig").fillna("")
    theme_strength = pd.read_csv(theme_strength_path, dtype=str, encoding="utf-8-sig").fillna("")
    theme_strength["trade_date"] = theme_strength["trade_date"].astype(str)
    for col in ["theme_score", "m5", "m20", "m60", "amount_ratio_20", "board_up_ratio", "positive_m20_ratio", "theme_rank", "theme_rank_pct"]:
        if col not in theme_strength.columns:
            theme_strength[col] = pd.NA
        theme_strength[col] = pd.to_numeric(theme_strength[col], errors="coerce")

    exposure_by_code = {
        _normalize_stock_code(row.get("stock_code", "")): row
        for row in exposure.to_dict(orient="records")
        if _normalize_stock_code(row.get("stock_code", ""))
    }

    manifest_rows: list[dict[str, Any]] = []
    rows_written = 0
    matched_files = 0
    stock_files = 0
    for source_file in sorted(processed_dir.glob("*.csv")):
        stock_code = _normalize_stock_code(source_file.stem)
        if not stock_code:
            continue
        stock_files += 1
        frame = pd.read_csv(source_file, dtype={"trade_date": str}, encoding="utf-8-sig")
        if "trade_date" not in frame.columns:
            raise ValueError(f"股票文件缺少 trade_date 字段: {source_file}")
        frame["trade_date"] = frame["trade_date"].astype(str)

        exposure_row = exposure_by_code.get(stock_code)
        matched = exposure_row is not None
        if matched:
            matched_files += 1
            enriched = _merge_one_stock(frame, exposure_row, theme_strength)
        else:
            enriched = _with_empty_sector_features(frame)

        target_file = output_dir / source_file.name
        enriched.to_csv(target_file, index=False, encoding="utf-8-sig")
        rows_written += len(enriched)
        manifest_rows.append(
            {
                "stock_code": stock_code,
                "source_file": str(source_file),
                "target_file": str(target_file),
                "matched_sector_theme": bool(matched),
                "theme_names": "" if exposure_row is None else exposure_row.get("theme_names", ""),
                "rows": len(enriched),
            }
        )

    manifest = pd.DataFrame(manifest_rows)
    manifest_path = output_dir / "sector_feature_manifest.csv"
    manifest.to_csv(manifest_path, index=False, encoding="utf-8-sig")
    return SectorFeatureMergeResult(
        processed_dir=str(processed_dir),
        sector_processed_dir=str(sector_processed_dir),
        output_dir=str(output_dir),
        stock_files=stock_files,
        matched_files=matched_files,
        unmatched_files=stock_files - matched_files,
        rows_written=rows_written,
        manifest_path=str(manifest_path),
    )


def _merge_one_stock(frame: pd.DataFrame, exposure_row: dict[str, Any], theme_strength: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["sector_theme_names"] = exposure_row.get("theme_names", "")
    result["sector_subtheme_names"] = exposure_row.get("subtheme_names", "")
    result["sector_board_names"] = exposure_row.get("board_names", "")
    result["sector_theme_count"] = _to_int_or_na(exposure_row.get("theme_count", ""))
    result["sector_subtheme_count"] = _to_int_or_na(exposure_row.get("subtheme_count", ""))
    result["sector_board_count"] = _to_int_or_na(exposure_row.get("board_count", ""))
    result["sector_exposure_score"] = _to_float_or_na(exposure_row.get("exposure_score", ""))

    theme_names = _split_names(exposure_row.get("theme_names", ""))
    daily = theme_strength[theme_strength["theme_name"].isin(theme_names)].copy()
    if daily.empty:
        return _ensure_daily_columns(result)

    daily = (
        daily.sort_values(["trade_date", "theme_score"], ascending=[True, False])
        .groupby("trade_date", as_index=False)
        .first()
    )
    daily = daily.rename(
        columns={
            "theme_name": "sector_strongest_theme",
            "theme_rank": "sector_strongest_theme_rank",
            "theme_rank_pct": "sector_strongest_theme_rank_pct",
            "theme_score": "sector_strongest_theme_score",
            "m5": "sector_strongest_theme_m5",
            "m20": "sector_strongest_theme_m20",
            "m60": "sector_strongest_theme_m60",
            "amount_ratio_20": "sector_strongest_theme_amount_ratio_20",
            "board_up_ratio": "sector_strongest_theme_board_up_ratio",
            "positive_m20_ratio": "sector_strongest_theme_positive_m20_ratio",
            "strongest_board": "sector_strongest_board",
            "strongest_subtheme": "sector_strongest_subtheme",
        }
    )
    keep_cols = ["trade_date"] + [col for col in DAILY_FEATURE_COLUMNS if col in daily.columns]
    result = result.merge(daily[keep_cols], on="trade_date", how="left")
    return _ensure_daily_columns(result)


def _with_empty_sector_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for col in STATIC_FEATURE_COLUMNS + DAILY_FEATURE_COLUMNS:
        result[col] = pd.NA
    return result


def _ensure_daily_columns(frame: pd.DataFrame) -> pd.DataFrame:
    for col in DAILY_FEATURE_COLUMNS:
        if col not in frame.columns:
            frame[col] = pd.NA
    return frame


def _split_names(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").split("、") if item.strip()]


def _normalize_stock_code(value: object) -> str:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return ""
    if len(digits) <= 6:
        return digits.zfill(6)
    return digits[-6:]


def _to_float_or_na(value: object) -> float | pd._libs.missing.NAType:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return pd.NA
    return float(number)


def _to_int_or_na(value: object) -> int | pd._libs.missing.NAType:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return pd.NA
    return int(number)
