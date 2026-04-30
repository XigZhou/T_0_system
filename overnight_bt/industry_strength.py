from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


INDUSTRY_STRENGTH_COLUMNS = [
    "industry_m20",
    "industry_m60",
    "industry_rank_m20",
    "industry_rank_m60",
    "industry_up_ratio",
    "industry_strong_ratio",
    "industry_amount",
    "industry_amount20",
    "industry_amount_ratio",
    "industry_stock_count",
    "industry_valid_m20_count",
    "stock_vs_industry_m20",
    "stock_vs_industry_m60",
]


@dataclass(frozen=True)
class IndustryStrengthResult:
    processed_dir: str
    output_dir: str
    report_dir: str
    file_count: int
    row_count: int
    industry_count: int
    start_date: str
    end_date: str
    in_place: bool


def _read_processed_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig")


def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = denominator.where(denominator != 0)
    return numerator / denom


def _rank_percentile_by_date(metrics: pd.DataFrame, value_col: str) -> pd.Series:
    result = pd.Series(pd.NA, index=metrics.index, dtype="Float64")
    for _, group in metrics.groupby("trade_date", sort=False):
        valid = group[value_col].notna()
        valid_count = int(valid.sum())
        if valid_count <= 0:
            continue
        ranks = group.loc[valid, value_col].rank(method="min", ascending=False)
        denom = max(valid_count - 1, 1)
        result.loc[group.loc[valid].index] = (ranks - 1) / denom
    return result


def _collect_base_rows(processed_dir: Path) -> tuple[pd.DataFrame, list[tuple[Path, pd.DataFrame]]]:
    frames: list[pd.DataFrame] = []
    loaded: list[tuple[Path, pd.DataFrame]] = []
    csv_paths = sorted(path for path in processed_dir.glob("*.csv") if "manifest" not in path.stem.lower())
    if not csv_paths:
        raise FileNotFoundError(f"no processed csv files found in {processed_dir}")

    required = {"trade_date", "symbol", "name", "industry", "m20", "m60", "pct_chg", "amount"}
    for path in csv_paths:
        frame = _read_processed_csv(path)
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{path} missing required columns: {sorted(missing)}")
        loaded.append((path, frame))
        use = frame[["trade_date", "symbol", "name", "industry", "m20", "m60", "pct_chg", "amount"]].copy()
        use["source_file"] = path.name
        frames.append(use)

    base = pd.concat(frames, ignore_index=True)
    base["trade_date"] = base["trade_date"].astype(str).str.strip()
    base["industry"] = base["industry"].fillna("").astype(str).str.strip()
    base = base[base["industry"] != ""].copy()
    if base.empty:
        raise ValueError("processed files do not contain usable industry values")
    for col in ["m20", "m60", "pct_chg", "amount"]:
        base[col] = _to_num(base[col])
    return base, loaded


def build_industry_strength_frame(
    base: pd.DataFrame,
    *,
    amount_window: int = 20,
    amount_min_periods: int = 5,
) -> pd.DataFrame:
    work = base.copy()
    work["up_flag"] = _to_num(work["pct_chg"]) > 0
    work["strong_flag"] = _to_num(work["m20"]) > 0

    grouped = work.groupby(["trade_date", "industry"], as_index=False)
    metrics = grouped.agg(
        industry_m20=("m20", "mean"),
        industry_m60=("m60", "mean"),
        industry_up_ratio=("up_flag", "mean"),
        industry_strong_ratio=("strong_flag", "mean"),
        industry_amount=("amount", "sum"),
        industry_stock_count=("symbol", "nunique"),
        industry_valid_m20_count=("m20", "count"),
    )
    metrics = metrics.sort_values(["industry", "trade_date"]).reset_index(drop=True)
    metrics["industry_amount20"] = metrics.groupby("industry")["industry_amount"].transform(
        lambda series: series.rolling(int(amount_window), min_periods=int(amount_min_periods)).mean()
    )
    metrics["industry_amount_ratio"] = _safe_ratio(metrics["industry_amount"], metrics["industry_amount20"])
    metrics = metrics.sort_values(["trade_date", "industry"]).reset_index(drop=True)
    metrics["industry_rank_m20"] = _rank_percentile_by_date(metrics, "industry_m20")
    metrics["industry_rank_m60"] = _rank_percentile_by_date(metrics, "industry_m60")

    keep_cols = ["trade_date", "industry", *INDUSTRY_STRENGTH_COLUMNS[:-2]]
    return metrics[keep_cols].copy()


def _merge_metrics(frame: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    work = frame.drop(columns=[col for col in INDUSTRY_STRENGTH_COLUMNS if col in frame.columns], errors="ignore").copy()
    work["trade_date"] = work["trade_date"].astype(str).str.strip()
    work["industry"] = work["industry"].fillna("").astype(str).str.strip()
    merged = work.merge(metrics, on=["trade_date", "industry"], how="left")
    merged["m20_num_for_industry"] = _to_num(merged.get("m20"))
    merged["m60_num_for_industry"] = _to_num(merged.get("m60"))
    merged["stock_vs_industry_m20"] = merged["m20_num_for_industry"] - _to_num(merged["industry_m20"])
    merged["stock_vs_industry_m60"] = merged["m60_num_for_industry"] - _to_num(merged["industry_m60"])
    merged = merged.drop(columns=["m20_num_for_industry", "m60_num_for_industry"])
    for col in INDUSTRY_STRENGTH_COLUMNS:
        if col in merged.columns:
            merged[col] = _to_num(merged[col]).round(6)
    return merged


def _write_summary(
    *,
    report_dir: Path,
    result: IndustryStrengthResult,
    metrics: pd.DataFrame,
    manifest_rows: list[dict[str, Any]],
    amount_window: int,
    amount_min_periods: int,
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "industry_strength_manifest.csv").write_text(
        pd.DataFrame(manifest_rows).to_csv(index=False),
        encoding="utf-8-sig",
    )
    config = {
        "processed_dir": result.processed_dir,
        "output_dir": result.output_dir,
        "in_place": result.in_place,
        "file_count": result.file_count,
        "row_count": result.row_count,
        "industry_count": result.industry_count,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "amount_window": amount_window,
        "amount_min_periods": amount_min_periods,
        "columns": INDUSTRY_STRENGTH_COLUMNS,
    }
    (report_dir / "industry_strength_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    top_industries = (
        metrics.sort_values(["trade_date", "industry_rank_m20"])
        .groupby("trade_date")
        .head(3)[["trade_date", "industry", "industry_m20", "industry_rank_m20", "industry_stock_count"]]
        .tail(15)
    )
    if top_industries.empty:
        top_table = "暂无样例。"
    else:
        table_rows = ["| 交易日 | 行业 | 行业二十日动量 | 行业排名百分位 | 股票数 |", "| --- | --- | ---: | ---: | ---: |"]
        for row in top_industries.to_dict(orient="records"):
            table_rows.append(
                "| "
                f"{row['trade_date']} | {row['industry']} | {float(row['industry_m20']):.4f} | "
                f"{float(row['industry_rank_m20']):.4f} | {int(row['industry_stock_count'])} |"
            )
        top_table = "\n".join(table_rows)
    summary_lines = [
        "# 行业强度指标生成总结",
        "",
        f"- 处理后数据目录：`{result.processed_dir}`",
        f"- 输出目录：`{result.output_dir}`",
        f"- 是否覆盖原目录：`{'是' if result.in_place else '否'}`",
        f"- 股票文件数：`{result.file_count}`",
        f"- 写入行数：`{result.row_count}`",
        f"- 行业数量：`{result.industry_count}`",
        f"- 日期范围：`{result.start_date}` 到 `{result.end_date}`",
        f"- 行业成交额滚动窗口：`{amount_window}`，最少样本：`{amount_min_periods}`",
        "",
        "## 新增字段",
        "",
        *[f"- `{col}`" for col in INDUSTRY_STRENGTH_COLUMNS],
        "",
        "## 最近日期强势行业样例",
        "",
        top_table,
        "",
        "## 使用方式",
        "",
        "前端买入条件可直接使用这些字段，例如：",
        "",
        "```text",
        "industry_rank_m20<0.3,industry_m20>0,industry_up_ratio>0.5,stock_vs_industry_m20>0",
        "```",
        "",
    ]
    (report_dir / "industry_strength_summary.md").write_text("\n".join(summary_lines), encoding="utf-8")


def add_industry_strength_to_processed_dir(
    processed_dir: Path,
    *,
    output_dir: Path | None = None,
    report_dir: Path | None = None,
    amount_window: int = 20,
    amount_min_periods: int = 5,
) -> IndustryStrengthResult:
    processed_dir = Path(processed_dir)
    if not processed_dir.exists():
        raise FileNotFoundError(f"processed_dir not found: {processed_dir}")
    in_place = output_dir is None
    output_dir = processed_dir if output_dir is None else Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if report_dir is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_dir = Path("research_runs") / f"{stamp}_industry_strength"
    else:
        report_dir = Path(report_dir)

    base, loaded = _collect_base_rows(processed_dir)
    metrics = build_industry_strength_frame(base, amount_window=amount_window, amount_min_periods=amount_min_periods)
    manifest_rows: list[dict[str, Any]] = []
    row_count = 0
    for path, frame in loaded:
        merged = _merge_metrics(frame, metrics)
        out_path = output_dir / path.name
        merged.to_csv(out_path, index=False, encoding="utf-8-sig")
        row_count += len(merged)
        manifest_rows.append(
            {
                "symbol_file": path.name,
                "rows": len(merged),
                "output_path": str(out_path),
                "has_industry_metrics": bool(merged["industry_m20"].notna().any()),
            }
        )

    result = IndustryStrengthResult(
        processed_dir=str(processed_dir),
        output_dir=str(output_dir),
        report_dir=str(report_dir),
        file_count=len(loaded),
        row_count=row_count,
        industry_count=int(base["industry"].nunique()),
        start_date=str(base["trade_date"].min()),
        end_date=str(base["trade_date"].max()),
        in_place=in_place,
    )
    _write_summary(
        report_dir=report_dir,
        result=result,
        metrics=metrics,
        manifest_rows=manifest_rows,
        amount_window=amount_window,
        amount_min_periods=amount_min_periods,
    )
    return result
