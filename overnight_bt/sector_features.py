from __future__ import annotations

import re
import math
from pathlib import Path
from typing import Any


SECTOR_NUMERIC_COLUMNS = frozenset(
    {
        "sector_theme_count",
        "sector_subtheme_count",
        "sector_board_count",
        "sector_exposure_score",
        "sector_strongest_theme_rank",
        "sector_strongest_theme_rank_pct",
        "sector_strongest_theme_score",
        "sector_strongest_theme_m5",
        "sector_strongest_theme_m20",
        "sector_strongest_theme_m60",
        "sector_strongest_theme_amount_ratio_20",
        "sector_strongest_theme_board_up_ratio",
        "sector_strongest_theme_positive_m20_ratio",
    }
)

SECTOR_CATEGORICAL_COLUMNS = frozenset(
    {
        "sector_theme_names",
        "sector_subtheme_names",
        "sector_board_names",
        "sector_strongest_theme",
        "sector_strongest_board",
        "sector_strongest_subtheme",
    }
)

REQUIRED_SECTOR_FEATURE_COLUMNS = frozenset(
    {
        "sector_exposure_score",
        "sector_strongest_theme_score",
        "sector_strongest_theme_rank_pct",
        "sector_strongest_theme_m20",
    }
)
SECTOR_DISPLAY_COLUMNS = (
    "sector_theme_names",
    "sector_exposure_score",
    "sector_strongest_theme",
    "sector_strongest_theme_score",
    "sector_strongest_theme_rank_pct",
    "sector_strongest_theme_m20",
    "sector_strongest_board",
)

_SECTOR_TOKEN_RE = re.compile(r"\bsector_[A-Za-z0-9_]*(?:\[\d+\])?\b")


def references_sector_features(*texts: str | None) -> bool:
    return any(_SECTOR_TOKEN_RE.search(str(text or "")) for text in texts)


def resolve_data_profile(
    *,
    requested_profile: str = "auto",
    processed_dir: str | Path,
    buy_condition: str = "",
    sell_condition: str = "",
    score_expression: str = "",
) -> str:
    profile = str(requested_profile or "auto").strip().lower()
    if profile not in {"auto", "base", "sector"}:
        raise ValueError(f"未知数据口径: {requested_profile}")
    if profile == "sector":
        return "sector"
    if profile == "base":
        return "base"
    folder = Path(processed_dir)
    if references_sector_features(buy_condition, sell_condition, score_expression):
        return "sector"
    if folder.name.endswith("_sector") or (folder / "sector_feature_manifest.csv").exists():
        return "sector"
    return "base"


def validate_sector_feature_set(
    *,
    loaded_items: list[Any],
    processed_dir: str | Path,
) -> dict[str, Any]:
    folder = Path(processed_dir)
    manifest_path = folder / "sector_feature_manifest.csv"
    if not manifest_path.exists():
        raise ValueError(
            "当前选择的是板块增强口径，但处理后数据目录缺少 "
            "sector_feature_manifest.csv；请先运行 scripts/build_sector_research_features.py "
            "生成 data_bundle/processed_qfq_theme_focus_top100_sector。"
        )

    missing_by_file: list[str] = []
    for item in loaded_items:
        columns = set(getattr(item, "df").columns)
        missing = sorted(REQUIRED_SECTOR_FEATURE_COLUMNS - columns)
        if missing:
            symbol = str(getattr(item, "symbol", "") or "unknown")
            missing_by_file.append(f"{symbol}: {','.join(missing)}")
        if len(missing_by_file) >= 5:
            break

    if missing_by_file:
        raise ValueError(
            "当前选择的是板块增强口径，但部分股票 CSV 缺少必要板块字段："
            + "；".join(missing_by_file)
        )

    return {
        "data_profile": "sector",
        "sector_manifest_path": str(manifest_path),
        "sector_required_columns": sorted(REQUIRED_SECTOR_FEATURE_COLUMNS),
        "sector_checked_file_count": len(loaded_items),
    }


def sector_display_values(row: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for column in SECTOR_DISPLAY_COLUMNS:
        if column not in row:
            continue
        value = row.get(column)
        if column in SECTOR_NUMERIC_COLUMNS:
            try:
                number = float(value)
            except (TypeError, ValueError):
                values[column] = None
                continue
            values[column] = round(number, 6) if math.isfinite(number) else None
        else:
            if value is None or value != value:
                values[column] = None
                continue
            text = str(value or "").strip()
            values[column] = text if text else None
    return values
