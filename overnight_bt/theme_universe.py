from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

THEME_SPLIT = "、"
DEFAULT_EXCLUDED_MARKETS = ("北交所",)


@dataclass(frozen=True)
class ThemeUniverseBuildConfig:
    min_total_mv_yi: float = 30.0
    min_listed_days: int = 250
    excluded_markets: tuple[str, ...] = DEFAULT_EXCLUDED_MARKETS
    exclude_st: bool = True


def normalize_symbol(value: object) -> str:
    text = str(value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return ""
    if len(digits) <= 6:
        return digits.zfill(6)
    return digits[-6:].zfill(6)


def normalize_ts_code(value: object) -> str:
    text = str(value or "").strip().upper()
    if "." in text and len(text.split(".", 1)[0]) == 6:
        return text
    symbol = normalize_symbol(text)
    if not symbol:
        return ""
    return f"{symbol}.SH" if symbol.startswith(("6", "9")) else f"{symbol}.SZ"


def split_theme_names(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").split(THEME_SPLIT) if item.strip()]


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _date(value: object) -> pd.Timestamp | pd.NaT:
    text = str(value or "").strip().replace("-", "")
    if not text:
        return pd.NaT
    return pd.to_datetime(text, format="%Y%m%d", errors="coerce")


def _listed_days(list_date: pd.Series, as_of_trade_date: str) -> pd.Series:
    as_of = _date(as_of_trade_date)
    if pd.isna(as_of):
        return pd.Series([pd.NA] * len(list_date), index=list_date.index, dtype="Float64")
    dates = pd.to_datetime(list_date.astype(str).str.replace("-", "", regex=False), format="%Y%m%d", errors="coerce")
    return (as_of - dates).dt.days.astype("Float64")


def _st_flag(name_series: pd.Series) -> pd.Series:
    return name_series.fillna("").astype(str).str.upper().str.contains("ST", regex=False)


def prepare_exposure_frame(exposure: pd.DataFrame) -> pd.DataFrame:
    work = exposure.copy().fillna("")
    if "stock_code" not in work.columns:
        raise ValueError("stock_theme_exposure 缺少 stock_code 字段")
    work["symbol"] = work["stock_code"].map(normalize_symbol)
    work = work[work["symbol"] != ""].drop_duplicates("symbol", keep="first").copy()
    for column in ["theme_count", "subtheme_count", "board_count", "exposure_score"]:
        if column in work.columns:
            work[column] = _num(work[column])
    return work


def prepare_basic_frame(stock_basic: pd.DataFrame) -> pd.DataFrame:
    work = stock_basic.copy().fillna("")
    if "symbol" not in work.columns:
        if "ts_code" not in work.columns:
            raise ValueError("stock_basic 缺少 symbol/ts_code 字段")
        work["symbol"] = work["ts_code"].map(normalize_symbol)
    work["symbol"] = work["symbol"].map(normalize_symbol)
    work["ts_code"] = work["ts_code"].map(normalize_ts_code) if "ts_code" in work.columns else work["symbol"].map(normalize_ts_code)
    if "name" in work.columns:
        work = work.rename(columns={"name": "tushare_name"})
    for column in ["area", "industry", "market", "list_date", "list_status", "tushare_name"]:
        if column not in work.columns:
            work[column] = ""
    work["list_status"] = work["list_status"].replace("", "L")
    return work.drop_duplicates("symbol", keep="first")


def prepare_daily_basic_frame(daily_basic: pd.DataFrame) -> pd.DataFrame:
    work = daily_basic.copy().fillna("")
    if "ts_code" not in work.columns:
        raise ValueError("daily_basic 缺少 ts_code 字段")
    work["ts_code"] = work["ts_code"].map(normalize_ts_code)
    work["symbol"] = work["ts_code"].map(normalize_symbol)
    for column in ["close", "total_mv", "turnover_rate_f", "volume_ratio", "pe_ttm", "pb"]:
        if column not in work.columns:
            work[column] = pd.NA
        work[column] = _num(work[column])
    if "trade_date" not in work.columns:
        work["trade_date"] = ""
    return work.drop_duplicates("symbol", keep="first")


def _filter_reasons(frame: pd.DataFrame, config: ThemeUniverseBuildConfig) -> pd.Series:
    reasons: list[str] = []
    excluded = set(config.excluded_markets)
    for _, row in frame.iterrows():
        current: list[str] = []
        if str(row.get("list_status", "")).strip() != "L":
            current.append("非上市状态")
        if config.exclude_st and bool(row.get("is_st", False)):
            current.append("ST或名称含ST")
        if str(row.get("market", "")).strip() in excluded:
            current.append(f"排除市场:{row.get('market')}")
        listed_days = pd.to_numeric(pd.Series([row.get("listed_days")]), errors="coerce").iloc[0]
        if pd.isna(listed_days) or float(listed_days) < config.min_listed_days:
            current.append(f"上市天数<{config.min_listed_days}")
        total_mv_yi = pd.to_numeric(pd.Series([row.get("total_mv_yi")]), errors="coerce").iloc[0]
        if pd.isna(total_mv_yi):
            current.append("缺少最新总市值")
        elif float(total_mv_yi) < config.min_total_mv_yi:
            current.append(f"总市值<{config.min_total_mv_yi:g}亿")
        reasons.append(";".join(current))
    return pd.Series(reasons, index=frame.index)


def build_theme_tradeable_universe(
    *,
    exposure: pd.DataFrame,
    stock_basic: pd.DataFrame,
    daily_basic: pd.DataFrame,
    as_of_trade_date: str,
    current_top100_symbols: Iterable[str] = (),
    config: ThemeUniverseBuildConfig | None = None,
) -> pd.DataFrame:
    cfg = config or ThemeUniverseBuildConfig()
    exposure_frame = prepare_exposure_frame(exposure)
    basic_frame = prepare_basic_frame(stock_basic)
    daily_frame = prepare_daily_basic_frame(daily_basic)
    work = exposure_frame.merge(
        basic_frame[["symbol", "ts_code", "tushare_name", "area", "industry", "market", "list_date", "list_status"]],
        on="symbol",
        how="left",
    )
    work = work.merge(
        daily_frame[["symbol", "trade_date", "close", "total_mv", "turnover_rate_f", "volume_ratio", "pe_ttm", "pb"]],
        on="symbol",
        how="left",
    )
    work["as_of_trade_date"] = str(as_of_trade_date)
    work["name"] = work.get("tushare_name", "").fillna("").astype(str)
    if "stock_name" in work.columns:
        work["name"] = work["name"].where(work["name"].str.len() > 0, work["stock_name"].fillna(""))
    work["list_status"] = work["list_status"].fillna("MISSING").replace("", "MISSING")
    work["listed_days"] = _listed_days(work["list_date"].fillna(""), str(as_of_trade_date))
    work["is_st"] = _st_flag(work["name"])
    work["total_mv"] = _num(work["total_mv"])
    work["total_mv_yi"] = work["total_mv"] / 10000.0
    work["turnover_rate_f"] = _num(work["turnover_rate_f"])
    work["current_top100_symbol"] = work["symbol"].isin({normalize_symbol(item) for item in current_top100_symbols})
    work["filter_reasons"] = _filter_reasons(work, cfg)
    work["is_tradeable_base"] = work["filter_reasons"].astype(str).str.len() == 0
    work = work.sort_values(["is_tradeable_base", "total_mv", "turnover_rate_f", "symbol"], ascending=[False, False, False, True]).reset_index(drop=True)
    ranks = work[work["is_tradeable_base"]].index.tolist()
    rank_map = {idx: rank + 1 for rank, idx in enumerate(ranks)}
    work["tradeable_rank"] = work.index.map(rank_map).astype("Int64")
    columns = [
        "tradeable_rank", "is_tradeable_base", "filter_reasons", "as_of_trade_date", "symbol", "ts_code", "name", "stock_name",
        "area", "industry", "market", "list_status", "list_date", "listed_days", "is_st", "close", "total_mv", "total_mv_yi",
        "turnover_rate_f", "volume_ratio", "pe_ttm", "pb", "theme_names", "subtheme_names", "board_names", "primary_theme",
        "primary_subtheme", "theme_count", "subtheme_count", "board_count", "exposure_score", "current_top100_symbol",
        "matched_keywords", "sources", "latest_fetched_at",
    ]
    for col in columns:
        if col not in work.columns:
            work[col] = ""
    return work[columns]


def layer_display_name(layer: object) -> str:
    names = {"L0": "最大市值层", "L1": "偏大市值层", "L2": "中等市值层", "L3": "偏小市值层", "L4": "最小市值层"}
    return names.get(str(layer), f"{layer}层")


def assign_market_cap_layers(universe: pd.DataFrame, *, top_n: int, layer_count: int = 5) -> pd.DataFrame:
    if top_n <= 0 or layer_count <= 0:
        raise ValueError("top_n 和 layer_count 必须大于 0")
    layered = universe[universe["is_tradeable_base"].astype(bool)].copy()
    layered = layered.sort_values(["total_mv", "turnover_rate_f", "symbol"], ascending=[False, False, True]).head(top_n).reset_index(drop=True)
    if layered.empty:
        return layered
    n = len(layered)
    layered["pool_name"] = f"Top{top_n}"
    layered["pool_rank"] = range(1, n + 1)
    layered["layer_index"] = [min(int(idx * layer_count / n), layer_count - 1) for idx in range(n)]
    layered["layer"] = layered["layer_index"].map(lambda value: f"L{int(value)}")
    layered["layer_name"] = layered["layer"].map(layer_display_name)
    return layered


def summarize_theme_hits(frame: pd.DataFrame) -> dict[str, int]:
    counts: dict[str, int] = {}
    if "theme_names" not in frame.columns:
        return counts
    for value in frame["theme_names"]:
        for theme in split_theme_names(value):
            counts[theme] = counts.get(theme, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def summarize_layered_pool(layered: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for layer, group in layered.groupby("layer", sort=True):
        mv = _num(group["total_mv_yi"])
        rows.append({
            "pool_name": str(group["pool_name"].iloc[0]),
            "layer": layer,
            "layer_name": layer_display_name(layer),
            "stock_count": int(len(group)),
            "pool_rank_min": int(group["pool_rank"].min()),
            "pool_rank_max": int(group["pool_rank"].max()),
            "total_mv_yi_max": round(float(mv.max()), 4) if mv.notna().any() else pd.NA,
            "total_mv_yi_median": round(float(mv.median()), 4) if mv.notna().any() else pd.NA,
            "total_mv_yi_min": round(float(mv.min()), 4) if mv.notna().any() else pd.NA,
            "current_top100_count": int(group["current_top100_symbol"].astype(bool).sum()) if "current_top100_symbol" in group.columns else 0,
            "theme_hit_counts": json.dumps(summarize_theme_hits(group), ensure_ascii=False, sort_keys=True),
            "primary_theme_counts": json.dumps(group.get("primary_theme", pd.Series(dtype=str)).fillna("").astype(str).value_counts().to_dict(), ensure_ascii=False, sort_keys=True),
        })
    return pd.DataFrame(rows)


def build_current_top100_compare(*, current_top100: pd.DataFrame, universe: pd.DataFrame, layered_by_top_n: dict[int, pd.DataFrame]) -> pd.DataFrame:
    current = current_top100.copy().fillna("")
    if "symbol" not in current.columns:
        if "ts_code" not in current.columns:
            raise ValueError("当前 Top100 快照缺少 symbol/ts_code 字段")
        current["symbol"] = current["ts_code"].map(normalize_symbol)
    current["symbol"] = current["symbol"].map(normalize_symbol)
    current = current[current["symbol"] != ""].drop_duplicates("symbol", keep="first").reset_index(drop=True)
    current["current_top100_rank"] = range(1, len(current) + 1)
    name_col = "name" if "name" in current.columns else "stock_name" if "stock_name" in current.columns else ""
    cols = ["symbol", "current_top100_rank"] + ([name_col] if name_col else [])
    merged = current[cols].rename(columns={name_col: "current_top100_name"} if name_col else {})
    universe_cols = ["symbol", "is_tradeable_base", "filter_reasons", "tradeable_rank", "name", "industry", "market", "total_mv_yi", "turnover_rate_f", "theme_names", "primary_theme", "primary_subtheme"]
    merged = merged.merge(universe[universe_cols], on="symbol", how="left")
    merged["in_tradeable_universe"] = merged["is_tradeable_base"].fillna(False).astype(bool)
    for top_n, layered in sorted(layered_by_top_n.items()):
        use = layered[["symbol", "pool_rank", "layer", "layer_name"]].rename(columns={"pool_rank": f"top{top_n}_rank", "layer": f"top{top_n}_layer", "layer_name": f"top{top_n}_layer_name"})
        merged = merged.merge(use, on="symbol", how="left")
    return merged.sort_values("current_top100_rank").reset_index(drop=True)


def build_universe_summary(universe: pd.DataFrame, layered_by_top_n: dict[int, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for scope, frame in [("all_exposure", universe), ("tradeable_base", universe[universe["is_tradeable_base"].astype(bool)])]:
        rows.append({"scope": scope, "stock_count": int(len(frame)), "tradeable_count": int(frame["is_tradeable_base"].astype(bool).sum()) if not frame.empty else 0, "current_top100_count": int(frame["current_top100_symbol"].astype(bool).sum()) if not frame.empty else 0, "theme_hit_counts": json.dumps(summarize_theme_hits(frame), ensure_ascii=False, sort_keys=True)})
    for top_n, frame in sorted(layered_by_top_n.items()):
        rows.append({"scope": f"top{top_n}", "stock_count": int(len(frame)), "tradeable_count": int(len(frame)), "current_top100_count": int(frame["current_top100_symbol"].astype(bool).sum()) if not frame.empty else 0, "theme_hit_counts": json.dumps(summarize_theme_hits(frame), ensure_ascii=False, sort_keys=True)})
    return pd.DataFrame(rows)


def parse_top_sizes(value: str) -> list[int]:
    sizes = sorted({int(item.strip()) for item in str(value or "").split(",") if item.strip()})
    if not sizes or any(size <= 0 for size in sizes):
        raise ValueError("top-sizes 必须为正整数列表")
    return sizes


def write_theme_tradeable_outputs(*, universe: pd.DataFrame, current_top100: pd.DataFrame, out_dir: Path, top_sizes: list[int], layer_count: int = 5) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    universe_path = out_dir / "theme_tradeable_universe_snapshot.csv"
    universe.to_csv(universe_path, index=False, encoding="utf-8-sig")
    outputs["universe_snapshot"] = str(universe_path)
    layered_by_top_n: dict[int, pd.DataFrame] = {}
    summaries = []
    for top_n in top_sizes:
        layered = assign_market_cap_layers(universe, top_n=top_n, layer_count=layer_count)
        layered_by_top_n[top_n] = layered
        layer_path = out_dir / f"theme_tradeable_top{top_n}_layers.csv"
        layered.to_csv(layer_path, index=False, encoding="utf-8-sig")
        outputs[f"top{top_n}_layers"] = str(layer_path)
        summary = summarize_layered_pool(layered)
        summary_path = out_dir / f"theme_tradeable_top{top_n}_layer_summary.csv"
        summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
        outputs[f"top{top_n}_layer_summary"] = str(summary_path)
        if not summary.empty:
            summaries.append(summary)
    compare = build_current_top100_compare(current_top100=current_top100, universe=universe, layered_by_top_n=layered_by_top_n)
    compare_path = out_dir / "current_top100_layer_compare.csv"
    compare.to_csv(compare_path, index=False, encoding="utf-8-sig")
    outputs["current_top100_layer_compare"] = str(compare_path)
    universe_summary = build_universe_summary(universe, layered_by_top_n)
    universe_summary_path = out_dir / "theme_tradeable_universe_summary.csv"
    universe_summary.to_csv(universe_summary_path, index=False, encoding="utf-8-sig")
    outputs["universe_summary"] = str(universe_summary_path)
    all_summary = pd.concat(summaries, ignore_index=True) if summaries else pd.DataFrame()
    all_summary_path = out_dir / "theme_tradeable_layer_summary_all.csv"
    all_summary.to_csv(all_summary_path, index=False, encoding="utf-8-sig")
    outputs["layer_summary_all"] = str(all_summary_path)
    manifest_path = out_dir / "theme_tradeable_universe_manifest.json"
    manifest_path.write_text(json.dumps({"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "top_sizes": top_sizes, "layer_count": layer_count, "outputs": outputs}, ensure_ascii=False, indent=2), encoding="utf-8")
    outputs["manifest"] = str(manifest_path)
    return outputs
