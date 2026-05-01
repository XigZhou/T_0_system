from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


THEME_CLUSTER_MAP = {
    "AI": "科技成长",
    "半导体芯片": "科技成长",
    "存储芯片": "科技成长",
    "机器人": "科技成长",
    "光伏新能源": "新能源",
    "锂矿锂电": "新能源",
    "医药": "医药防御",
}

THEME_STRENGTH_COLUMNS = (
    "trade_date",
    "theme_name",
    "theme_score",
    "theme_rank_pct",
    "m5",
    "m20",
    "m60",
    "strongest_board",
)

SECTOR_STOCK_COLUMNS = (
    "trade_date",
    "symbol",
    "sector_strongest_theme",
    "sector_strongest_theme_score",
    "sector_strongest_theme_rank_pct",
    "sector_exposure_score",
)


def _default_out_dir() -> Path:
    return Path("research_runs") / f"{datetime.now():%Y%m%d_%H%M%S}_sector_rotation_diagnosis"


def _read_csv(path: Path, **kwargs: Any) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, encoding="utf-8-sig", **kwargs)


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "-"


def _num(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return default if pd.isna(number) else number


def _normalize_symbol(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "." in text:
        text = text.split(".", 1)[0]
    if text.isdigit():
        return text.zfill(6)
    return text


def _parse_case_list(raw_text: str) -> list[str]:
    return [token.strip() for token in str(raw_text or "").split(",") if token.strip()]


def load_theme_strength(path: str | Path, *, start_date: str = "", end_date: str = "") -> pd.DataFrame:
    frame = _read_csv(Path(path), dtype={"trade_date": str, "theme_name": str})
    missing = {"trade_date", "theme_name", "theme_score", "theme_rank_pct"} - set(frame.columns)
    if missing:
        raise ValueError(f"主题强度文件缺少必要字段: {sorted(missing)}")

    frame["trade_date"] = frame["trade_date"].astype(str).str.strip()
    frame["theme_name"] = frame["theme_name"].astype(str).str.strip()
    if start_date:
        frame = frame[frame["trade_date"] >= str(start_date).strip()].copy()
    if end_date:
        frame = frame[frame["trade_date"] <= str(end_date).strip()].copy()
    if frame.empty:
        raise ValueError("主题强度文件在所选日期区间内没有数据")

    for column in ["theme_score", "theme_rank_pct", "m5", "m20", "m60", "volume_price_score", "reversal_score"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["theme_cluster"] = frame["theme_name"].map(THEME_CLUSTER_MAP).fillna("其他")
    return frame.sort_values(["trade_date", "theme_rank_pct", "theme_score"], ascending=[True, True, False]).reset_index(drop=True)


def _run_days(values: pd.Series) -> pd.Series:
    result: list[int] = []
    previous = None
    count = 0
    for value in values.tolist():
        if value == previous:
            count += 1
        else:
            count = 1
            previous = value
        result.append(count)
    return pd.Series(result, index=values.index)


def build_rotation_daily(
    theme_strength: pd.DataFrame,
    *,
    strong_rank_pct: float = 0.33,
    fresh_days: int = 5,
    weak_score: float = 0.35,
    min_top_gap: float = 0.02,
) -> pd.DataFrame:
    theme_strength = theme_strength.copy()
    if "theme_cluster" not in theme_strength.columns:
        theme_strength["theme_cluster"] = theme_strength["theme_name"].map(THEME_CLUSTER_MAP).fillna("其他")
    for column in ["theme_score", "theme_rank_pct", "m5", "m20", "m60"]:
        if column in theme_strength.columns:
            theme_strength[column] = pd.to_numeric(theme_strength[column], errors="coerce")

    score_pivot = theme_strength.pivot_table(index="trade_date", columns="theme_name", values="theme_score", aggfunc="last")
    rank_pivot = theme_strength.pivot_table(index="trade_date", columns="theme_name", values="theme_rank_pct", aggfunc="last")
    m20_pivot = theme_strength.pivot_table(index="trade_date", columns="theme_name", values="m20", aggfunc="last")
    score_chg5 = score_pivot - score_pivot.shift(5)
    score_chg20 = score_pivot - score_pivot.shift(20)
    rank_chg5 = rank_pivot - rank_pivot.shift(5)

    rows: list[dict[str, Any]] = []
    for trade_date, group in theme_strength.groupby("trade_date", sort=True):
        valid = group.dropna(subset=["theme_score", "theme_rank_pct"]).copy()
        if valid.empty:
            continue
        valid = valid.sort_values(["theme_rank_pct", "theme_score"], ascending=[True, False]).reset_index(drop=True)
        top = valid.iloc[0]
        second = valid.iloc[1] if len(valid) > 1 else None
        cluster_rows = (
            valid.groupby("theme_cluster", as_index=False)
            .agg(
                cluster_score=("theme_score", "mean"),
                cluster_best_rank_pct=("theme_rank_pct", "min"),
                cluster_top_theme=("theme_name", "first"),
            )
            .sort_values(["cluster_score", "cluster_best_rank_pct"], ascending=[False, True])
            .reset_index(drop=True)
        )
        top_theme = str(top["theme_name"])
        top_cluster = str(top["theme_cluster"])
        second_score = float(second["theme_score"]) if second is not None else 0.0
        top_score = float(top["theme_score"])
        rows.append(
            {
                "trade_date": trade_date,
                "top_theme": top_theme,
                "top_cluster": top_cluster,
                "top_score": top_score,
                "top_rank_pct": float(top["theme_rank_pct"]),
                "top_m5": top.get("m5"),
                "top_m20": top.get("m20"),
                "top_m60": top.get("m60"),
                "top_strongest_board": top.get("strongest_board", ""),
                "second_theme": "" if second is None else str(second["theme_name"]),
                "second_score": second_score,
                "second_rank_pct": None if second is None else float(second["theme_rank_pct"]),
                "top_gap": top_score - second_score,
                "strong_theme_count": int((valid["theme_rank_pct"] <= strong_rank_pct).sum()),
                "theme_score_dispersion": float(valid["theme_score"].std(ddof=0)),
                "top_cluster_by_score": "" if cluster_rows.empty else str(cluster_rows.iloc[0]["theme_cluster"]),
                "top_cluster_score": None if cluster_rows.empty else float(cluster_rows.iloc[0]["cluster_score"]),
                "top_theme_score_chg_5": score_chg5.at[trade_date, top_theme] if top_theme in score_chg5.columns and trade_date in score_chg5.index else None,
                "top_theme_score_chg_20": score_chg20.at[trade_date, top_theme] if top_theme in score_chg20.columns and trade_date in score_chg20.index else None,
                "top_theme_rank_pct_chg_5": rank_chg5.at[trade_date, top_theme] if top_theme in rank_chg5.columns and trade_date in rank_chg5.index else None,
                "top_theme_m20": m20_pivot.at[trade_date, top_theme] if top_theme in m20_pivot.columns and trade_date in m20_pivot.index else None,
            }
        )

    daily = pd.DataFrame(rows)
    if daily.empty:
        raise ValueError("无法生成轮动状态，主题强度数据为空")
    daily["top_theme_run_days"] = _run_days(daily["top_theme"])
    daily["top_cluster_run_days"] = _run_days(daily["top_cluster"])
    daily["rotation_state"] = daily.apply(
        lambda row: _classify_rotation_state(
            row,
            strong_rank_pct=strong_rank_pct,
            fresh_days=fresh_days,
            weak_score=weak_score,
            min_top_gap=min_top_gap,
        ),
        axis=1,
    )
    return daily


def _classify_rotation_state(
    row: pd.Series,
    *,
    strong_rank_pct: float,
    fresh_days: int,
    weak_score: float,
    min_top_gap: float,
) -> str:
    top_score = _as_float(row.get("top_score"), 0.0)
    top_gap = _as_float(row.get("top_gap"), 0.0)
    rank_pct = _as_float(row.get("top_rank_pct"), 1.0)
    run_days = int(row.get("top_theme_run_days") or 0)
    score_chg_5 = _as_float(row.get("top_theme_score_chg_5"), 0.0)
    m20 = _as_float(row.get("top_theme_m20"), 0.0)
    if top_score < weak_score and top_gap < min_top_gap:
        return "无明确主线"
    if run_days <= fresh_days and rank_pct <= 0.5 and score_chg_5 > 0:
        return "新主线启动"
    if rank_pct <= strong_rank_pct and run_days > fresh_days and m20 >= 0:
        return "主线延续"
    if score_chg_5 < -0.05 or (m20 < 0 and score_chg_5 < 0):
        return "主线退潮"
    return "轮动观察"


def build_theme_run_table(rotation_daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    current_theme = None
    current_cluster = None
    start_idx = 0
    for idx, row in rotation_daily.reset_index(drop=True).iterrows():
        theme = row["top_theme"]
        cluster = row["top_cluster"]
        if current_theme is None:
            current_theme = theme
            current_cluster = cluster
            start_idx = idx
            continue
        if theme != current_theme:
            rows.append(_theme_run_row(rotation_daily.reset_index(drop=True), start_idx, idx - 1, current_theme, current_cluster))
            current_theme = theme
            current_cluster = cluster
            start_idx = idx
    rows.append(_theme_run_row(rotation_daily.reset_index(drop=True), start_idx, len(rotation_daily) - 1, current_theme, current_cluster))
    return pd.DataFrame(rows).sort_values(["run_days", "start_date"], ascending=[False, True]).reset_index(drop=True)


def _theme_run_row(frame: pd.DataFrame, start_idx: int, end_idx: int, theme: str, cluster: str) -> dict[str, Any]:
    start = frame.iloc[start_idx]
    end = frame.iloc[end_idx]
    return {
        "top_theme": theme,
        "top_cluster": cluster,
        "start_date": start["trade_date"],
        "end_date": end["trade_date"],
        "run_days": int(end_idx - start_idx + 1),
        "start_score": start["top_score"],
        "end_score": end["top_score"],
        "score_change": float(end["top_score"]) - float(start["top_score"]),
        "end_rotation_state": end["rotation_state"],
    }


def build_transition_table(rotation_daily: pd.DataFrame) -> pd.DataFrame:
    top_theme = rotation_daily["top_theme"].reset_index(drop=True)
    transitions = pd.DataFrame({"from_theme": top_theme.shift(1), "to_theme": top_theme})
    transitions = transitions.dropna()
    transitions = transitions[transitions["from_theme"] != transitions["to_theme"]]
    if transitions.empty:
        return pd.DataFrame(columns=["from_theme", "to_theme", "transition_count"])
    return (
        transitions.groupby(["from_theme", "to_theme"], as_index=False)
        .size()
        .rename(columns={"size": "transition_count"})
        .sort_values("transition_count", ascending=False)
        .reset_index(drop=True)
    )


def build_cluster_daily(theme_strength: pd.DataFrame) -> pd.DataFrame:
    cluster_daily = (
        theme_strength.groupby(["trade_date", "theme_cluster"], as_index=False)
        .agg(
            cluster_score=("theme_score", "mean"),
            cluster_best_rank_pct=("theme_rank_pct", "min"),
            cluster_top_theme=("theme_name", lambda s: str(s.iloc[0])),
            theme_count=("theme_name", "count"),
        )
        .sort_values(["trade_date", "cluster_score", "cluster_best_rank_pct"], ascending=[True, False, True])
        .reset_index(drop=True)
    )
    cluster_daily["cluster_rank"] = cluster_daily.groupby("trade_date")["cluster_score"].rank(method="first", ascending=False).astype("Int64")
    return cluster_daily


def _load_sector_stock_features(sector_processed_dir: str | Path, symbols: set[str]) -> pd.DataFrame:
    folder = Path(sector_processed_dir)
    if not folder.exists():
        raise FileNotFoundError(folder)
    frames: list[pd.DataFrame] = []
    for symbol in sorted(symbols):
        file_path = folder / f"{_normalize_symbol(symbol)}.csv"
        if not file_path.exists():
            continue
        available = pd.read_csv(file_path, nrows=0, encoding="utf-8-sig").columns
        usecols = [column for column in SECTOR_STOCK_COLUMNS if column in available]
        if "trade_date" not in usecols:
            continue
        frame = pd.read_csv(file_path, usecols=usecols, dtype={"trade_date": str, "symbol": str}, encoding="utf-8-sig")
        if "symbol" not in frame.columns:
            frame["symbol"] = _normalize_symbol(symbol)
        frame["symbol"] = frame["symbol"].map(_normalize_symbol)
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=SECTOR_STOCK_COLUMNS)
    result = pd.concat(frames, ignore_index=True, sort=False)
    for column in ["sector_strongest_theme_score", "sector_strongest_theme_rank_pct", "sector_exposure_score"]:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def label_trade_records(
    trade_records_path: str | Path,
    rotation_daily: pd.DataFrame,
    *,
    sector_processed_dir: str | Path,
    cases: list[str],
) -> pd.DataFrame:
    trades = _read_csv(
        Path(trade_records_path),
        dtype={"trade_date": str, "signal_date": str, "symbol": str, "case": str, "action": str},
    )
    if trades.empty:
        return trades
    if cases:
        trades = trades[trades["case"].isin(cases)].copy()
    if trades.empty:
        return trades
    trades["symbol"] = trades["symbol"].map(_normalize_symbol)
    for column in ["trade_return", "price_pnl", "gross_amount", "fees", "net_amount"]:
        if column in trades.columns:
            trades[column] = pd.to_numeric(trades[column], errors="coerce")

    rotation_cols = [
        "trade_date",
        "top_theme",
        "top_cluster",
        "top_score",
        "top_rank_pct",
        "top_gap",
        "top_theme_run_days",
        "top_cluster_run_days",
        "rotation_state",
    ]
    rotation = rotation_daily[rotation_cols].rename(columns={column: f"signal_{column}" for column in rotation_cols if column != "trade_date"})
    rotation = rotation.rename(columns={"trade_date": "signal_date"})
    labeled = trades.merge(rotation, on="signal_date", how="left")

    stock_features = _load_sector_stock_features(sector_processed_dir, set(labeled["symbol"].dropna().astype(str)))
    if not stock_features.empty:
        stock_features = stock_features.rename(columns={"trade_date": "signal_date"})
        labeled = labeled.merge(stock_features, on=["symbol", "signal_date"], how="left")
    else:
        for column in SECTOR_STOCK_COLUMNS:
            if column not in {"trade_date", "symbol"}:
                labeled[column] = pd.NA

    labeled["stock_theme_cluster"] = labeled["sector_strongest_theme"].map(THEME_CLUSTER_MAP).fillna("")
    labeled["stock_matches_top_theme"] = labeled["sector_strongest_theme"].fillna("") == labeled["signal_top_theme"].fillna("")
    labeled["stock_matches_top_cluster"] = labeled["stock_theme_cluster"].fillna("") == labeled["signal_top_cluster"].fillna("")
    return labeled


def build_trade_summary(labeled_trades: pd.DataFrame) -> pd.DataFrame:
    if labeled_trades.empty:
        return pd.DataFrame()
    sell_rows = labeled_trades[labeled_trades["action"].astype(str).str.upper() == "SELL"].copy()
    buy_rows = labeled_trades[labeled_trades["action"].astype(str).str.upper() == "BUY"].copy()
    rows: list[dict[str, Any]] = []
    group_specs = [
        ("rotation_state", "signal_rotation_state"),
        ("top_theme", "signal_top_theme"),
        ("top_cluster", "signal_top_cluster"),
        ("stock_theme", "sector_strongest_theme"),
        ("stock_cluster", "stock_theme_cluster"),
    ]
    for group_name, column in group_specs:
        if column not in labeled_trades.columns:
            continue
        for case, case_buys in buy_rows.groupby("case", dropna=False):
            case_sells = sell_rows[sell_rows["case"] == case]
            buy_counts = case_buys.groupby(column, dropna=False).size()
            sell_groups = case_sells.groupby(column, dropna=False)
            keys = set(buy_counts.index.tolist()) | set(sell_groups.groups.keys())
            for key in keys:
                subset = sell_groups.get_group(key) if key in sell_groups.groups else pd.DataFrame(columns=sell_rows.columns)
                returns = pd.to_numeric(subset.get("trade_return"), errors="coerce") if not subset.empty else pd.Series(dtype=float)
                rows.append(
                    {
                        "group_type": group_name,
                        "case": case,
                        "group_value": "" if pd.isna(key) else str(key),
                        "buy_count": int(buy_counts.get(key, 0)),
                        "sell_count": int(len(subset)),
                        "avg_trade_return": float(returns.mean()) if not returns.empty else None,
                        "median_trade_return": float(returns.median()) if not returns.empty else None,
                        "win_rate": float((returns > 0).mean()) if not returns.empty else None,
                        "total_price_pnl": float(pd.to_numeric(subset.get("price_pnl"), errors="coerce").sum()) if not subset.empty else 0.0,
                    }
                )
    return pd.DataFrame(rows)


def _render_report(
    *,
    rotation_daily: pd.DataFrame,
    theme_runs: pd.DataFrame,
    transitions: pd.DataFrame,
    trade_summary: pd.DataFrame,
    args: argparse.Namespace,
    out_dir: Path,
) -> str:
    latest = rotation_daily.iloc[-1]
    top_counts = rotation_daily["top_theme"].value_counts()
    state_counts = rotation_daily["rotation_state"].value_counts()
    avg_run_days = len(rotation_daily) / max(len(theme_runs), 1)

    lines = [
        "# 板块轮动诊断报告",
        "",
        f"- 诊断区间：{rotation_daily['trade_date'].min()} 至 {rotation_daily['trade_date'].max()}",
        f"- 主题强度文件：`{args.theme_strength_path}`",
        f"- 交易流水文件：`{args.trade_records_path}`",
        f"- 板块增强股票目录：`{args.sector_processed_dir}`",
        "",
        "## 最新轮动状态",
        "",
        f"- 最新交易日：`{latest['trade_date']}`",
        f"- Top1 主题：`{latest['top_theme']}`；主题簇：`{latest['top_cluster']}`；状态：`{latest['rotation_state']}`",
        f"- Top1 分数：`{_num(latest['top_score'], 4)}`；排名百分位：`{_pct(latest['top_rank_pct'])}`；与第二名差距：`{_num(latest['top_gap'], 4)}`",
        f"- Top1 已连续：`{int(latest['top_theme_run_days'])}` 个交易日；主题簇已连续：`{int(latest['top_cluster_run_days'])}` 个交易日",
        "",
        "## 轮动概览",
        "",
        f"- Top1 切换次数：`{max(len(theme_runs) - 1, 0)}`",
        f"- 平均 Top1 持续交易日：`{avg_run_days:.2f}`",
        f"- 平均主题分离度：`{rotation_daily['theme_score_dispersion'].mean():.4f}`",
        "",
        "| Top1 主题 | 交易日数 | 占比 |",
        "| --- | ---: | ---: |",
    ]
    for theme, count in top_counts.items():
        lines.append(f"| {theme} | {int(count)} | {count / len(rotation_daily) * 100:.2f}% |")

    lines.extend(["", "## 轮动状态分布", "", "| 状态 | 交易日数 | 占比 |", "| --- | ---: | ---: |"])
    for state, count in state_counts.items():
        lines.append(f"| {state} | {int(count)} | {count / len(rotation_daily) * 100:.2f}% |")

    lines.extend(["", "## 最长主线阶段", "", "| 主题 | 主题簇 | 开始 | 结束 | 持续天数 | 分数变化 | 结束状态 |", "| --- | --- | --- | --- | ---: | ---: | --- |"])
    for _, row in theme_runs.head(args.report_top_k).iterrows():
        lines.append(
            f"| {row['top_theme']} | {row['top_cluster']} | {row['start_date']} | {row['end_date']} | "
            f"{int(row['run_days'])} | {_num(row['score_change'], 4)} | {row['end_rotation_state']} |"
        )

    if not transitions.empty:
        lines.extend(["", "## 高频切换路径", "", "| 从 | 到 | 次数 |", "| --- | --- | ---: |"])
        for _, row in transitions.head(args.report_top_k).iterrows():
            lines.append(f"| {row['from_theme']} | {row['to_theme']} | {int(row['transition_count'])} |")

    if not trade_summary.empty:
        state_summary = trade_summary[trade_summary["group_type"] == "rotation_state"].copy()
        if not state_summary.empty:
            state_summary = state_summary.sort_values(["case", "buy_count"], ascending=[True, False])
            lines.extend(
                [
                    "",
                    "## 交易按轮动状态分组",
                    "",
                    "| 策略 | 轮动状态 | 买入次数 | 卖出次数 | 中位收益 | 胜率 | 价格盈亏 |",
                    "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for _, row in state_summary.iterrows():
                lines.append(
                    f"| {row['case']} | {row['group_value']} | {int(row['buy_count'])} | {int(row['sell_count'])} | "
                    f"{_pct(row['median_trade_return'])} | {_pct(row['win_rate'])} | {_num(row['total_price_pnl'], 2)} |"
                )

    lines.extend(
        [
            "",
            "## 输出文件",
            "",
            f"- 每日轮动状态：`{(out_dir / 'sector_rotation_daily.csv').as_posix()}`",
            f"- 主题连续阶段：`{(out_dir / 'sector_rotation_theme_runs.csv').as_posix()}`",
            f"- 主题切换统计：`{(out_dir / 'sector_rotation_transitions.csv').as_posix()}`",
            f"- 交易轮动打标：`{(out_dir / 'sector_rotation_labeled_trades.csv').as_posix()}`",
            f"- 交易分组统计：`{(out_dir / 'sector_rotation_trade_summary.csv').as_posix()}`",
        ]
    )
    return "\n".join(lines) + "\n"


def run_rotation_diagnosis(args: argparse.Namespace) -> Path:
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    theme_strength = load_theme_strength(args.theme_strength_path, start_date=args.start_date, end_date=args.end_date)
    rotation_daily = build_rotation_daily(
        theme_strength,
        strong_rank_pct=args.strong_rank_pct,
        fresh_days=args.fresh_days,
        weak_score=args.weak_score,
        min_top_gap=args.min_top_gap,
    )
    theme_runs = build_theme_run_table(rotation_daily)
    transitions = build_transition_table(rotation_daily)
    cluster_daily = build_cluster_daily(theme_strength)

    cases = _parse_case_list(args.cases)
    labeled_trades = pd.DataFrame()
    trade_summary = pd.DataFrame()
    if args.trade_records_path:
        labeled_trades = label_trade_records(
            args.trade_records_path,
            rotation_daily,
            sector_processed_dir=args.sector_processed_dir,
            cases=cases,
        )
        trade_summary = build_trade_summary(labeled_trades)

    rotation_daily.to_csv(out_dir / "sector_rotation_daily.csv", index=False, encoding="utf-8-sig")
    theme_runs.to_csv(out_dir / "sector_rotation_theme_runs.csv", index=False, encoding="utf-8-sig")
    transitions.to_csv(out_dir / "sector_rotation_transitions.csv", index=False, encoding="utf-8-sig")
    cluster_daily.to_csv(out_dir / "sector_rotation_cluster_daily.csv", index=False, encoding="utf-8-sig")
    labeled_trades.to_csv(out_dir / "sector_rotation_labeled_trades.csv", index=False, encoding="utf-8-sig")
    trade_summary.to_csv(out_dir / "sector_rotation_trade_summary.csv", index=False, encoding="utf-8-sig")

    config = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "args": vars(args),
        "theme_cluster_map": THEME_CLUSTER_MAP,
        "rotation_state_rules": {
            "strong_rank_pct": args.strong_rank_pct,
            "fresh_days": args.fresh_days,
            "weak_score": args.weak_score,
            "min_top_gap": args.min_top_gap,
        },
    }
    (out_dir / "sector_rotation_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "sector_rotation_report.md").write_text(
        _render_report(
            rotation_daily=rotation_daily,
            theme_runs=theme_runs,
            transitions=transitions,
            trade_summary=trade_summary,
            args=args,
            out_dir=out_dir,
        ),
        encoding="utf-8",
    )
    print(f"板块轮动诊断完成：{out_dir.as_posix()}")
    return out_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="诊断主题板块轮动状态，并给回测交易流水打上轮动标签")
    parser.add_argument("--theme-strength-path", default="sector_research/data/processed/theme_strength_daily.csv")
    parser.add_argument("--trade-records-path", default="research_runs/20260501_142052_sector_parameter_grid/sector_parameter_grid_trade_records.csv")
    parser.add_argument("--sector-processed-dir", default="data_bundle/processed_qfq_theme_focus_top100_sector")
    parser.add_argument("--start-date", default="20230101")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--cases", default="基准动量,硬过滤_score0.4_rank0.7", help="逗号分隔的策略名称，留空表示不过滤")
    parser.add_argument("--strong-rank-pct", type=float, default=0.33)
    parser.add_argument("--fresh-days", type=int, default=5)
    parser.add_argument("--weak-score", type=float, default=0.35)
    parser.add_argument("--min-top-gap", type=float, default=0.02)
    parser.add_argument("--report-top-k", type=int, default=10)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    run_rotation_diagnosis(parse_args(argv))


if __name__ == "__main__":
    main()
