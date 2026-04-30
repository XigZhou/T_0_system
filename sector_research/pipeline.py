from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .config import ThemeConfig, load_theme_config
from .providers import AkshareSectorDataProvider, SectorDataProvider


BOARD_TYPES = ["industry", "concept"]
FUND_FLOW_INDICATORS = ["今日", "5日", "10日"]


@dataclass(frozen=True)
class SectorResearchResult:
    config_path: str
    start_date: str
    end_date: str
    raw_dir: str
    processed_dir: str
    report_dir: str
    board_count: int
    board_daily_rows: int
    theme_daily_rows: int
    constituent_rows: int
    latest_trade_date: str


def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = denominator.where(denominator != 0)
    return numerator / denom


def _scale(series: pd.Series, low: float, high: float) -> pd.Series:
    return ((series - low) / (high - low)).clip(lower=0, upper=1)


def _rank_pct(ranks: pd.Series, counts: pd.Series) -> pd.Series:
    denom = (counts - 1).where(counts > 1, 1)
    return ((ranks - 1) / denom).round(6)


def _join_unique(series: pd.Series) -> str:
    values = [str(item).strip() for item in series if str(item).strip()]
    return "、".join(sorted(set(values)))


def _momentum(close: pd.Series, window: int) -> pd.Series:
    if window <= 1:
        return close.pct_change()
    return close / close.shift(window - 1) - 1.0


def discover_theme_boards(board_list: pd.DataFrame, config: ThemeConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for board in board_list.to_dict(orient="records"):
        board_name = str(board.get("board_name") or "").strip()
        if not board_name:
            continue
        for theme in config.themes:
            for subtheme in theme.subthemes:
                for keyword in subtheme.keywords:
                    if keyword and keyword in board_name:
                        row = {
                            "theme_name": theme.name,
                            "subtheme_name": subtheme.name,
                            "matched_keyword": keyword,
                            "board_type": board.get("board_type", ""),
                            "board_code": board.get("board_code", ""),
                            "board_name": board_name,
                            "source": board.get("source", ""),
                            "fetched_at": board.get("fetched_at", ""),
                        }
                        rows.append(row)
                        break
                else:
                    continue
                break
    if not rows:
        return pd.DataFrame(columns=["theme_name", "subtheme_name", "matched_keyword", "board_type", "board_code", "board_name", "source", "fetched_at"])
    return pd.DataFrame(rows).drop_duplicates(["theme_name", "subtheme_name", "board_type", "board_name"]).reset_index(drop=True)


def build_board_strength_daily(board_daily: pd.DataFrame) -> pd.DataFrame:
    if board_daily.empty:
        return board_daily.copy()
    frame = board_daily.copy()
    frame["trade_date"] = frame["trade_date"].astype(str)
    for col in ["open", "close", "high", "low", "pct_chg", "vol", "amount", "turnover_rate"]:
        if col not in frame.columns:
            frame[col] = pd.NA
        frame[col] = _to_num(frame[col])
    frame = frame.sort_values(["theme_name", "subtheme_name", "board_type", "board_name", "trade_date"]).reset_index(drop=True)

    group_cols = ["theme_name", "subtheme_name", "board_type", "board_name"]
    grouped = frame.groupby(group_cols, sort=False)
    for window in [5, 20, 60, 120, 250]:
        frame[f"m{window}"] = grouped["close"].transform(lambda series, w=window: _momentum(series, w))
    frame["amount20"] = grouped["amount"].transform(lambda series: series.rolling(20, min_periods=5).mean())
    frame["amount_ratio_20"] = _safe_ratio(frame["amount"], frame["amount20"])
    frame["high_120"] = grouped["high"].transform(lambda series: series.rolling(120, min_periods=20).max())
    frame["high_250"] = grouped["high"].transform(lambda series: series.rolling(250, min_periods=40).max())
    frame["low_250"] = grouped["low"].transform(lambda series: series.rolling(250, min_periods=40).min())
    frame["drawdown_from_120_high"] = frame["close"] / frame["high_120"] - 1.0
    frame["position_in_250_range"] = _safe_ratio(frame["close"] - frame["low_250"], frame["high_250"] - frame["low_250"]).clip(0, 1)

    daily_return = frame["pct_chg"] / 100.0
    trend_core = (
        0.30 * _scale(frame["m20"], -0.05, 0.20)
        + 0.25 * _scale(frame["m60"], -0.10, 0.30)
        + 0.20 * _scale(frame["m5"], -0.02, 0.08)
        + 0.25 * _scale(frame["amount_ratio_20"], 0.8, 2.0)
    )
    frame["volume_price_score"] = (
        0.50 * trend_core
        + 0.30 * _scale(frame["amount_ratio_20"], 0.8, 2.0)
        + 0.20 * _scale(daily_return, -0.01, 0.03)
    ).clip(0, 1)
    weakness_score = (1.0 - frame["position_in_250_range"]).clip(0, 1)
    frame["reversal_score"] = (
        0.45 * weakness_score
        + 0.20 * _scale(frame["m5"], -0.03, 0.08)
        + 0.20 * _scale(frame["amount_ratio_20"], 0.8, 2.0)
        + 0.15 * _scale(frame["m20"] - frame["m60"], -0.05, 0.10)
    ).clip(0, 1)
    frame["theme_board_score"] = frame[["volume_price_score", "reversal_score"]].max(axis=1)

    board_rank_in_theme = frame.groupby(["trade_date", "theme_name"])["theme_board_score"].rank(method="min", ascending=False)
    board_count_in_theme = frame.groupby(["trade_date", "theme_name"])["theme_board_score"].transform("count")
    board_rank_overall = frame.groupby("trade_date")["theme_board_score"].rank(method="min", ascending=False)
    board_count_overall = frame.groupby("trade_date")["theme_board_score"].transform("count")
    frame["board_rank_in_theme"] = board_rank_in_theme.astype("Int64")
    frame["board_rank_in_theme_pct"] = _rank_pct(board_rank_in_theme, board_count_in_theme)
    frame["board_rank_overall"] = board_rank_overall.astype("Int64")
    frame["board_rank_overall_pct"] = _rank_pct(board_rank_overall, board_count_overall)

    numeric_cols = [
        "m5",
        "m20",
        "m60",
        "m120",
        "m250",
        "amount20",
        "amount_ratio_20",
        "drawdown_from_120_high",
        "position_in_250_range",
        "volume_price_score",
        "reversal_score",
        "theme_board_score",
        "board_rank_in_theme_pct",
        "board_rank_overall_pct",
    ]
    for col in numeric_cols:
        frame[col] = _to_num(frame[col]).round(6)
    return frame


def build_theme_strength_daily(board_strength: pd.DataFrame) -> pd.DataFrame:
    if board_strength.empty:
        return pd.DataFrame()
    frame = board_strength.copy()
    frame["up_flag"] = _to_num(frame["pct_chg"]) > 0
    frame["positive_m20_flag"] = _to_num(frame["m20"]) > 0
    grouped = frame.groupby(["trade_date", "theme_name"], as_index=False)
    result = grouped.agg(
        board_count=("board_name", "nunique"),
        subtheme_count=("subtheme_name", "nunique"),
        m5=("m5", "mean"),
        m20=("m20", "mean"),
        m60=("m60", "mean"),
        m120=("m120", "mean"),
        amount_ratio_20=("amount_ratio_20", "mean"),
        board_up_ratio=("up_flag", "mean"),
        positive_m20_ratio=("positive_m20_flag", "mean"),
        volume_price_score=("volume_price_score", "mean"),
        reversal_score=("reversal_score", "mean"),
        theme_score=("theme_board_score", "mean"),
    )

    strongest = (
        frame.sort_values(["trade_date", "theme_name", "theme_board_score"], ascending=[True, True, False])
        .groupby(["trade_date", "theme_name"], as_index=False)
        .first()[["trade_date", "theme_name", "board_name", "subtheme_name", "theme_board_score"]]
        .rename(
            columns={
                "board_name": "strongest_board",
                "subtheme_name": "strongest_subtheme",
                "theme_board_score": "strongest_board_score",
            }
        )
    )
    result = result.merge(strongest, on=["trade_date", "theme_name"], how="left")
    numeric_cols = [
        "m5",
        "m20",
        "m60",
        "m120",
        "amount_ratio_20",
        "board_up_ratio",
        "positive_m20_ratio",
        "volume_price_score",
        "reversal_score",
        "theme_score",
        "strongest_board_score",
    ]
    for col in numeric_cols:
        result[col] = _to_num(result[col]).round(6)
    theme_rank = result.groupby("trade_date")["theme_score"].rank(method="min", ascending=False)
    theme_count = result.groupby("trade_date")["theme_score"].transform("count")
    result["theme_rank"] = theme_rank.astype("Int64")
    result["theme_rank_pct"] = _rank_pct(theme_rank, theme_count)
    return result.sort_values(["trade_date", "theme_score"], ascending=[True, False]).reset_index(drop=True)


def build_stock_theme_exposure(constituents: pd.DataFrame) -> pd.DataFrame:
    if constituents.empty:
        return pd.DataFrame(
            columns=[
                "stock_code",
                "stock_name",
                "theme_count",
                "subtheme_count",
                "board_count",
                "theme_names",
                "subtheme_names",
                "board_types",
                "board_names",
                "matched_keywords",
                "sources",
                "latest_fetched_at",
                "primary_theme",
                "primary_subtheme",
                "exposure_score",
            ]
        )
    frame = constituents.copy()
    for col in ["theme_name", "subtheme_name", "board_type", "board_name", "matched_keyword", "source", "fetched_at"]:
        if col not in frame.columns:
            frame[col] = ""
    grouped = frame.groupby(["stock_code", "stock_name"], as_index=False)
    result = grouped.agg(
        theme_count=("theme_name", "nunique"),
        subtheme_count=("subtheme_name", "nunique"),
        board_count=("board_name", "nunique"),
        theme_names=("theme_name", _join_unique),
        subtheme_names=("subtheme_name", _join_unique),
        board_types=("board_type", _join_unique),
        board_names=("board_name", _join_unique),
        matched_keywords=("matched_keyword", _join_unique),
        sources=("source", _join_unique),
        latest_fetched_at=("fetched_at", "max"),
    )
    result["primary_theme"] = result["theme_names"].str.split("、").str[0].fillna("")
    result["primary_subtheme"] = result["subtheme_names"].str.split("、").str[0].fillna("")
    max_board_count = max(float(result["board_count"].max()), 1.0)
    result["exposure_score"] = (result["board_count"] / max_board_count).round(6)
    return result.sort_values(["exposure_score", "board_count", "stock_code"], ascending=[False, False, True]).reset_index(drop=True)


def run_sector_research(
    *,
    config_path: str | Path = "sector_research/configs/themes.yaml",
    start_date: str = "20230101",
    end_date: str = "",
    raw_dir: str | Path = "sector_research/data/raw",
    processed_dir: str | Path = "sector_research/data/processed",
    report_dir: str | Path = "sector_research/reports",
    provider: SectorDataProvider | None = None,
    fetch_constituents: bool = True,
) -> SectorResearchResult:
    config_path = Path(config_path)
    config = load_theme_config(config_path)
    end_date = str(end_date or datetime.now().strftime("%Y%m%d"))
    raw_dir = Path(raw_dir)
    processed_dir = Path(processed_dir)
    report_dir = Path(report_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    provider = provider or AkshareSectorDataProvider()

    board_lists = []
    errors: list[dict[str, Any]] = []
    for board_type in BOARD_TYPES:
        try:
            board_lists.append(provider.list_boards(board_type))
        except Exception as exc:  # noqa: BLE001
            errors.append({"stage": "list_boards", "board_type": board_type, "error": str(exc)})
    if not board_lists:
        raise RuntimeError(f"无法获取任何板块列表: {errors}")
    board_list = pd.concat(board_lists, ignore_index=True)
    mapping = discover_theme_boards(board_list, config)
    if mapping.empty:
        raise RuntimeError("没有从 AKShare 板块列表匹配到任何配置主题，请检查关键词")

    histories: list[pd.DataFrame] = []
    constituents: list[pd.DataFrame] = []
    for item in mapping.to_dict(orient="records"):
        board_name = str(item["board_name"])
        board_type = str(item["board_type"])
        try:
            hist = provider.fetch_board_history(board_name, board_type, start_date, end_date)
            for key in ["theme_name", "subtheme_name", "matched_keyword", "board_code"]:
                hist[key] = item.get(key, "")
            histories.append(hist)
        except Exception as exc:  # noqa: BLE001
            errors.append({"stage": "fetch_board_history", "board_type": board_type, "board_name": board_name, "error": str(exc)})
        if fetch_constituents:
            try:
                cons = provider.fetch_board_constituents(board_name, board_type)
                for key in ["theme_name", "subtheme_name", "matched_keyword", "board_code"]:
                    cons[key] = item.get(key, "")
                constituents.append(cons)
            except Exception as exc:  # noqa: BLE001
                errors.append({"stage": "fetch_board_constituents", "board_type": board_type, "board_name": board_name, "error": str(exc)})

    if not histories:
        raise RuntimeError(f"匹配到板块但没有成功获取历史行情: {errors[:10]}")
    board_daily = pd.concat(histories, ignore_index=True)
    board_daily = board_daily.merge(
        mapping[["theme_name", "subtheme_name", "board_type", "board_name", "board_code", "matched_keyword"]],
        on=["theme_name", "subtheme_name", "board_type", "board_name", "board_code", "matched_keyword"],
        how="left",
    )

    fund_flows = []
    for board_type in BOARD_TYPES:
        for indicator in FUND_FLOW_INDICATORS:
            try:
                fund_flows.append(provider.fetch_fund_flow_rank(board_type, indicator))
            except Exception as exc:  # noqa: BLE001
                errors.append({"stage": "fetch_fund_flow_rank", "board_type": board_type, "indicator": indicator, "error": str(exc)})
    fund_flow = pd.concat(fund_flows, ignore_index=True) if fund_flows else pd.DataFrame()

    board_strength = build_board_strength_daily(board_daily)
    latest_date = str(board_strength["trade_date"].max())
    latest_fund = _latest_fund_flow_wide(fund_flow, latest_date)
    if not latest_fund.empty:
        board_strength = board_strength.merge(latest_fund, on=["board_type", "board_name", "trade_date"], how="left")

    theme_strength = build_theme_strength_daily(board_strength)
    constituents_frame = pd.concat(constituents, ignore_index=True) if constituents else pd.DataFrame()
    stock_exposure = build_stock_theme_exposure(constituents_frame)

    board_list.to_csv(raw_dir / "board_list.csv", index=False, encoding="utf-8-sig")
    mapping.to_csv(processed_dir / "theme_board_mapping.csv", index=False, encoding="utf-8-sig")
    board_daily.to_csv(raw_dir / "board_daily_raw.csv", index=False, encoding="utf-8-sig")
    fund_flow.to_csv(raw_dir / "board_fund_flow_rank.csv", index=False, encoding="utf-8-sig")
    board_strength.to_csv(processed_dir / "sector_board_daily.csv", index=False, encoding="utf-8-sig")
    theme_strength.to_csv(processed_dir / "theme_strength_daily.csv", index=False, encoding="utf-8-sig")
    constituents_frame.to_csv(processed_dir / "theme_constituents_snapshot.csv", index=False, encoding="utf-8-sig")
    stock_exposure.to_csv(processed_dir / "stock_theme_exposure.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(errors).to_csv(report_dir / "sector_research_errors.csv", index=False, encoding="utf-8-sig")

    _write_report(
        report_dir=report_dir,
        config_path=config_path,
        start_date=start_date,
        end_date=end_date,
        mapping=mapping,
        board_strength=board_strength,
        theme_strength=theme_strength,
        stock_exposure=stock_exposure,
        errors=errors,
    )
    _write_excel_summary(report_dir, theme_strength, board_strength, mapping, constituents_frame, stock_exposure)

    return SectorResearchResult(
        config_path=str(config_path),
        start_date=start_date,
        end_date=end_date,
        raw_dir=str(raw_dir),
        processed_dir=str(processed_dir),
        report_dir=str(report_dir),
        board_count=int(mapping[["board_type", "board_name"]].drop_duplicates().shape[0]),
        board_daily_rows=len(board_strength),
        theme_daily_rows=len(theme_strength),
        constituent_rows=len(constituents_frame),
        latest_trade_date=latest_date,
    )


def _latest_fund_flow_wide(fund_flow: pd.DataFrame, latest_date: str) -> pd.DataFrame:
    if fund_flow.empty:
        return pd.DataFrame()
    frame = fund_flow.copy()
    rows = []
    for (board_type, board_name), group in frame.groupby(["board_type", "board_name"], sort=False):
        row: dict[str, Any] = {"board_type": board_type, "board_name": board_name, "trade_date": latest_date}
        for item in group.to_dict(orient="records"):
            suffix = str(item.get("fund_flow_indicator") or "")
            if suffix == "今日":
                suffix = "today"
            elif suffix == "5日":
                suffix = "5d"
            elif suffix == "10日":
                suffix = "10d"
            else:
                suffix = suffix or "unknown"
            row[f"main_net_inflow_{suffix}"] = item.get("main_net_inflow")
            row[f"main_net_inflow_ratio_{suffix}"] = item.get("main_net_inflow_ratio")
        rows.append(row)
    return pd.DataFrame(rows)


def _write_report(
    *,
    report_dir: Path,
    config_path: Path,
    start_date: str,
    end_date: str,
    mapping: pd.DataFrame,
    board_strength: pd.DataFrame,
    theme_strength: pd.DataFrame,
    stock_exposure: pd.DataFrame,
    errors: list[dict[str, Any]],
) -> None:
    latest_date = str(theme_strength["trade_date"].max()) if not theme_strength.empty else ""
    latest_themes = theme_strength[theme_strength["trade_date"].astype(str) == latest_date].sort_values("theme_score", ascending=False)
    latest_boards = board_strength[board_strength["trade_date"].astype(str) == latest_date].sort_values("theme_board_score", ascending=False)

    lines = [
        "# 板块主题强度研究报告",
        "",
        f"- 配置文件：`{config_path}`",
        f"- 历史区间：`{start_date}` 到 `{end_date}`",
        f"- 最新交易日：`{latest_date}`",
        f"- 匹配板块数：`{mapping[['board_type', 'board_name']].drop_duplicates().shape[0]}`",
        f"- 输出时间：`{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"- 抓取/处理异常数：`{len(errors)}`",
        "",
        "## 最新主题排名",
        "",
        "| 排名 | 主题 | 综合分 | 量价齐升分 | 极弱反转分 | 5日动量 | 20日动量 | 最强板块 |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for rank, row in enumerate(latest_themes.head(20).to_dict(orient="records"), start=1):
        lines.append(
            "| "
            f"{rank} | {row.get('theme_name', '')} | {_fmt(row.get('theme_score'))} | {_fmt(row.get('volume_price_score'))} | "
            f"{_fmt(row.get('reversal_score'))} | {_fmt(row.get('m5'))} | {_fmt(row.get('m20'))} | "
            f"{row.get('strongest_board', '')} |"
        )

    lines.extend(["", "## 最新强势板块", "", "| 排名 | 主题 | 子赛道 | 板块 | 类型 | 综合分 | 20日动量 | 成交额放大 |", "| ---: | --- | --- | --- | --- | ---: | ---: | ---: |"])
    for rank, row in enumerate(latest_boards.head(30).to_dict(orient="records"), start=1):
        lines.append(
            "| "
            f"{rank} | {row.get('theme_name', '')} | {row.get('subtheme_name', '')} | {row.get('board_name', '')} | "
            f"{row.get('board_type', '')} | {_fmt(row.get('theme_board_score'))} | {_fmt(row.get('m20'))} | "
            f"{_fmt(row.get('amount_ratio_20'))} |"
        )

    lines.extend(["", "## 个股主题暴露 Top20", "", "| 排名 | 股票代码 | 股票名称 | 主题数 | 板块数 | 主题 |", "| ---: | --- | --- | ---: | ---: | --- |"])
    for rank, row in enumerate(stock_exposure.head(20).to_dict(orient="records"), start=1):
        lines.append(
            "| "
            f"{rank} | {row.get('stock_code', '')} | {row.get('stock_name', '')} | {row.get('theme_count', '')} | "
            f"{row.get('board_count', '')} | {row.get('theme_names', '')} |"
        )

    lines.extend(
        [
            "",
            "## 数据源与输出文件",
            "",
            "- 数据源：默认使用 AKShare 东方财富行业板块、概念板块、板块历史行情、成分股与资金流接口。",
            "- 原始标准化数据：`board_list.csv`、`board_daily_raw.csv`、`board_fund_flow_rank.csv`。",
            "- 处理后数据：`theme_board_mapping.csv`、`sector_board_daily.csv`、`theme_strength_daily.csv`、`theme_constituents_snapshot.csv`、`stock_theme_exposure.csv`。",
            "- 本报告只读取外部板块数据并写入 `sector_research/` 目录，不覆盖当前回测主目录。",
            "",
            "## 解读说明",
            "",
            "- `量价齐升分` 更适合寻找趋势继续增强的赛道。",
            "- `极弱反转分` 更适合寻找长期低位、开始放量修复的赛道。",
            "- 第一阶段只做板块研究，不会修改当前 T_0 回测系统的股票 CSV。",
            "- 资金流数据若抓取失败，不影响历史行情和主题强度计算。",
            "",
        ]
    )
    (report_dir / "theme_strength_report.md").write_text("\n".join(lines), encoding="utf-8")
    (report_dir / "sector_research_summary.json").write_text(
        json.dumps(
            {
                "config_path": str(config_path),
                "start_date": start_date,
                "end_date": end_date,
                "latest_trade_date": latest_date,
                "mapping_count": len(mapping),
                "board_daily_rows": len(board_strength),
                "theme_daily_rows": len(theme_strength),
                "stock_exposure_rows": len(stock_exposure),
                "error_count": len(errors),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_excel_summary(
    report_dir: Path,
    theme_strength: pd.DataFrame,
    board_strength: pd.DataFrame,
    mapping: pd.DataFrame,
    constituents: pd.DataFrame,
    stock_exposure: pd.DataFrame,
) -> None:
    latest_date = str(theme_strength["trade_date"].max()) if not theme_strength.empty else ""
    latest_themes = theme_strength[theme_strength["trade_date"].astype(str) == latest_date].sort_values("theme_score", ascending=False)
    latest_boards = board_strength[board_strength["trade_date"].astype(str) == latest_date].sort_values("theme_board_score", ascending=False)
    with pd.ExcelWriter(report_dir / "theme_strength_latest.xlsx", engine="openpyxl") as writer:
        latest_themes.to_excel(writer, sheet_name="最新主题强度", index=False)
        latest_boards.to_excel(writer, sheet_name="最新板块强度", index=False)
        mapping.to_excel(writer, sheet_name="主题板块映射", index=False)
        stock_exposure.head(500).to_excel(writer, sheet_name="个股主题暴露", index=False)
        constituents.head(1000).to_excel(writer, sheet_name="成分股快照", index=False)


def _fmt(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
        return f"{float(value):.4f}"
    except Exception:
        return ""
