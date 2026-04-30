from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_SECTOR_PROCESSED_DIR = "sector_research/data/processed"
DEFAULT_SECTOR_REPORT_DIR = "sector_research/reports"

THEME_COLUMNS = [
    "trade_date",
    "theme_rank",
    "theme_name",
    "theme_score",
    "volume_price_score",
    "reversal_score",
    "m5",
    "m20",
    "m60",
    "m120",
    "amount_ratio_20",
    "board_up_ratio",
    "positive_m20_ratio",
    "strongest_board",
    "strongest_subtheme",
    "strongest_board_score",
    "board_count",
    "subtheme_count",
    "theme_rank_pct",
]

BOARD_COLUMNS = [
    "trade_date",
    "board_rank_overall",
    "board_rank_in_theme",
    "theme_name",
    "subtheme_name",
    "board_type",
    "board_name",
    "theme_board_score",
    "volume_price_score",
    "reversal_score",
    "pct_chg",
    "m5",
    "m20",
    "m60",
    "m120",
    "amount_ratio_20",
    "main_net_inflow_today",
    "main_net_inflow_ratio_today",
    "drawdown_from_120_high",
    "position_in_250_range",
]

EXPOSURE_COLUMNS = [
    "stock_code",
    "stock_name",
    "primary_theme",
    "primary_subtheme",
    "exposure_score",
    "theme_count",
    "subtheme_count",
    "board_count",
    "theme_names",
    "subtheme_names",
    "board_names",
    "matched_keywords",
    "latest_fetched_at",
]

MAPPING_COLUMNS = [
    "theme_name",
    "subtheme_name",
    "matched_keyword",
    "board_type",
    "board_code",
    "board_name",
    "source",
    "fetched_at",
]

HISTORY_COLUMNS = ["trade_date", "theme_name", "theme_score", "m20", "amount_ratio_20", "theme_rank"]

NUMERIC_COLUMNS = {
    "theme_rank",
    "theme_score",
    "volume_price_score",
    "reversal_score",
    "m5",
    "m20",
    "m60",
    "m120",
    "amount_ratio_20",
    "board_up_ratio",
    "positive_m20_ratio",
    "strongest_board_score",
    "board_count",
    "subtheme_count",
    "theme_rank_pct",
    "board_rank_overall",
    "board_rank_in_theme",
    "theme_board_score",
    "pct_chg",
    "main_net_inflow_today",
    "main_net_inflow_ratio_today",
    "drawdown_from_120_high",
    "position_in_250_range",
    "exposure_score",
    "theme_count",
    "subtheme_count",
}


def build_sector_dashboard_payload(
    *,
    base_dir: str | Path,
    processed_dir: str | Path = DEFAULT_SECTOR_PROCESSED_DIR,
    report_dir: str | Path = DEFAULT_SECTOR_REPORT_DIR,
) -> dict[str, Any]:
    """Read sector research outputs and shape them for the read-only dashboard."""

    base = Path(base_dir).resolve()
    processed = _resolve_under_base(base, processed_dir)
    report = _resolve_under_base(base, report_dir)
    messages: list[str] = []

    theme_strength = _read_csv(processed / "theme_strength_daily.csv", base, messages)
    board_strength = _read_csv(processed / "sector_board_daily.csv", base, messages)
    stock_exposure = _read_csv(processed / "stock_theme_exposure.csv", base, messages)
    mapping = _read_csv(processed / "theme_board_mapping.csv", base, messages)
    errors = _read_csv(report / "sector_research_errors.csv", base, messages, required=False)
    summary_json = _read_json(report / "sector_research_summary.json", base, messages)

    latest_date = _latest_trade_date(theme_strength, board_strength, summary_json)
    latest_themes = _latest_rows(theme_strength, latest_date, "theme_score", THEME_COLUMNS, 40)
    latest_boards = _latest_rows(board_strength, latest_date, "theme_board_score", BOARD_COLUMNS, 80)
    exposure_rows = _sorted_rows(stock_exposure, "exposure_score", EXPOSURE_COLUMNS, 120)
    mapping_rows = _sorted_rows(mapping, "theme_name", MAPPING_COLUMNS, 500, numeric_sort=False)
    error_rows = _records(errors.tail(200), limit=200) if not errors.empty else []
    theme_history = _theme_history(theme_strength, latest_themes)

    summary = _build_summary(
        summary_json=summary_json,
        latest_date=latest_date,
        mapping=mapping,
        board_strength=board_strength,
        theme_strength=theme_strength,
        stock_exposure=stock_exposure,
        errors=errors,
        processed=processed,
        report=report,
        base=base,
    )

    has_data = any(not frame.empty for frame in [theme_strength, board_strength, stock_exposure, mapping])
    status = "ready" if has_data else "empty"
    if not has_data:
        messages.append("尚未读取到板块研究结果；请先运行 scripts/run_sector_research.py 生成数据。")

    return {
        "status": status,
        "messages": messages,
        "paths": _file_paths(base, processed, report),
        "summary": summary,
        "latest_themes": latest_themes,
        "latest_boards": latest_boards,
        "stock_exposure": exposure_rows,
        "mapping_rows": mapping_rows,
        "error_rows": error_rows,
        "theme_history": theme_history,
    }


def _resolve_under_base(base: Path, value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"路径必须位于项目目录内: {value}") from exc
    return resolved


def _read_csv(path: Path, base: Path, messages: list[str], *, required: bool = True) -> pd.DataFrame:
    if not path.exists():
        if required:
            messages.append(f"缺少数据文件: {_display_path(base, path)}")
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except Exception as exc:  # noqa: BLE001
        messages.append(f"读取失败: {_display_path(base, path)}，原因: {exc}")
        return pd.DataFrame()


def _read_json(path: Path, base: Path, messages: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        messages.append(f"读取失败: {_display_path(base, path)}，原因: {exc}")
        return {}


def _latest_trade_date(theme_strength: pd.DataFrame, board_strength: pd.DataFrame, summary_json: dict[str, Any]) -> str:
    dates: list[str] = []
    for frame in [theme_strength, board_strength]:
        if not frame.empty and "trade_date" in frame.columns:
            values = frame["trade_date"].astype(str).str.strip()
            values = values[values != ""]
            if not values.empty:
                dates.append(str(values.max()))
    if dates:
        return max(dates)
    return str(summary_json.get("latest_trade_date") or "")


def _latest_rows(frame: pd.DataFrame, latest_date: str, sort_col: str, columns: list[str], limit: int) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    target = frame.copy()
    if latest_date and "trade_date" in target.columns:
        target = target[target["trade_date"].astype(str) == latest_date]
    return _sorted_rows(target, sort_col, columns, limit)


def _sorted_rows(
    frame: pd.DataFrame,
    sort_col: str,
    columns: list[str],
    limit: int,
    *,
    numeric_sort: bool = True,
) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    target = frame.copy()
    if sort_col in target.columns:
        if numeric_sort:
            target["_sort_value"] = pd.to_numeric(target[sort_col], errors="coerce")
            target = target.sort_values("_sort_value", ascending=False, na_position="last")
        else:
            target = target.sort_values(sort_col, ascending=True, na_position="last")
    return _records(target, columns=columns, limit=limit)


def _theme_history(theme_strength: pd.DataFrame, latest_themes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if theme_strength.empty or not latest_themes or "theme_name" not in theme_strength.columns:
        return []
    top_names = [str(row.get("theme_name") or "") for row in latest_themes[:8]]
    target = theme_strength[theme_strength["theme_name"].astype(str).isin(top_names)].copy()
    if "trade_date" in target.columns:
        target = target.sort_values(["theme_name", "trade_date"])
    target = target.groupby("theme_name", as_index=False, group_keys=False).tail(80)
    return _records(target, columns=HISTORY_COLUMNS, limit=640)


def _records(frame: pd.DataFrame, *, columns: list[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    target = frame.copy()
    keep_cols = [col for col in (columns or list(target.columns)) if col in target.columns]
    target = target[keep_cols]
    for col in keep_cols:
        if col in NUMERIC_COLUMNS:
            target[col] = pd.to_numeric(target[col], errors="coerce")
    if limit is not None:
        target = target.head(limit)
    return [{key: _clean_value(value) for key, value in row.items()} for row in target.to_dict(orient="records")]


def _clean_value(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _build_summary(
    *,
    summary_json: dict[str, Any],
    latest_date: str,
    mapping: pd.DataFrame,
    board_strength: pd.DataFrame,
    theme_strength: pd.DataFrame,
    stock_exposure: pd.DataFrame,
    errors: pd.DataFrame,
    processed: Path,
    report: Path,
    base: Path,
) -> dict[str, Any]:
    theme_count = int(mapping["theme_name"].nunique()) if not mapping.empty and "theme_name" in mapping.columns else 0
    board_count = int(mapping[["board_type", "board_name"]].drop_duplicates().shape[0]) if not mapping.empty and {"board_type", "board_name"}.issubset(mapping.columns) else 0
    summary = {
        "latest_trade_date": latest_date,
        "theme_count": theme_count,
        "board_count": board_count,
        "mapping_count": int(len(mapping)),
        "board_daily_rows": int(len(board_strength)),
        "theme_daily_rows": int(len(theme_strength)),
        "stock_exposure_rows": int(len(stock_exposure)),
        "error_count": int(len(errors)),
        "processed_dir": _display_path(base, processed),
        "report_dir": _display_path(base, report),
    }
    for key, value in summary_json.items():
        summary.setdefault(key, _clean_value(value))
    return summary


def _file_paths(base: Path, processed: Path, report: Path) -> dict[str, Any]:
    files = {
        "theme_strength_daily": processed / "theme_strength_daily.csv",
        "sector_board_daily": processed / "sector_board_daily.csv",
        "stock_theme_exposure": processed / "stock_theme_exposure.csv",
        "theme_board_mapping": processed / "theme_board_mapping.csv",
        "sector_research_errors": report / "sector_research_errors.csv",
        "sector_research_summary": report / "sector_research_summary.json",
        "theme_strength_report": report / "theme_strength_report.md",
        "theme_strength_latest": report / "theme_strength_latest.xlsx",
    }
    return {
        "processed_dir": _display_path(base, processed),
        "report_dir": _display_path(base, report),
        "files": {key: {"path": _display_path(base, path), "exists": path.exists()} for key, path in files.items()},
    }


def _display_path(base: Path, path: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return str(path)
