from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class FeatureBucketSpec:
    feature: str
    bins: tuple[float, ...]
    labels: tuple[str, ...]


DEFAULT_FEATURE_BUCKET_SPECS = (
    FeatureBucketSpec("close_to_up_limit", (0.0, 0.97, 0.985, 0.995, 2.0), ("<=0.97", "0.97-0.985", "0.985-0.995", ">0.995")),
    FeatureBucketSpec("high_to_up_limit", (0.0, 0.98, 0.99, 0.995, 2.0), ("<=0.98", "0.98-0.99", "0.99-0.995", ">0.995")),
    FeatureBucketSpec("close_pos_in_bar", (0.0, 0.3, 0.5, 0.7, 1.000001), ("0-0.3", "0.3-0.5", "0.5-0.7", "0.7-1.0")),
    FeatureBucketSpec("body_pct", (-1.0, -0.01, 0.0, 0.01, 0.03, 1.0), ("<=-1%", "-1%-0%", "0%-1%", "1%-3%", ">3%")),
    FeatureBucketSpec("upper_shadow_pct", (0.0, 0.01, 0.02, 0.04, 1.0), ("0-1%", "1%-2%", "2%-4%", ">4%")),
    FeatureBucketSpec("lower_shadow_pct", (0.0, 0.01, 0.02, 0.04, 1.0), ("0-1%", "1%-2%", "2%-4%", ">4%")),
    FeatureBucketSpec("vol_ratio_5", (0.0, 0.8, 1.0, 1.3, 1.8, 10.0), ("<=0.8", "0.8-1.0", "1.0-1.3", "1.3-1.8", ">1.8")),
)

SCAN_REQUIRED_COLUMNS = {
    "trade_date",
    "symbol",
    "name",
    "board",
    "market",
    "raw_open",
    "raw_close",
    "can_buy_open_t",
    "can_sell_t",
    "close_to_up_limit",
    "high_to_up_limit",
    "close_pos_in_bar",
    "body_pct",
    "upper_shadow_pct",
    "lower_shadow_pct",
    "vol_ratio_5",
}


def _bucket_series(series: pd.Series, spec: FeatureBucketSpec) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return pd.cut(
        numeric,
        bins=list(spec.bins),
        labels=list(spec.labels),
        include_lowest=True,
        right=True,
    )


def _attach_holding_period_labels(frame: pd.DataFrame, entry_offset: int, exit_offset: int) -> pd.DataFrame:
    work = frame.copy()
    work["trade_date"] = work["trade_date"].astype(str).str.strip()
    work["entry_trade_date"] = work["trade_date"].shift(-entry_offset)
    work["exit_trade_date"] = work["trade_date"].shift(-exit_offset)
    work["entry_raw_open"] = pd.to_numeric(work.get("raw_open"), errors="coerce").shift(-entry_offset)
    work["exit_raw_open"] = pd.to_numeric(work.get("raw_open"), errors="coerce").shift(-exit_offset)
    work["entry_can_buy_open"] = work["can_buy_open_t"].shift(-entry_offset)
    work["exit_can_sell_open"] = work["can_sell_t"].shift(-exit_offset)
    return work


def apply_research_net_return(
    frame: pd.DataFrame,
    buy_fee_rate: float,
    sell_fee_rate: float,
    stamp_tax_sell: float,
    slippage_bps: float,
    min_commission: float = 0.0,
    per_trade_notional: float = 10_000.0,
) -> pd.DataFrame:
    work = frame.copy()
    work["entry_raw_open"] = pd.to_numeric(work.get("entry_raw_open"), errors="coerce")
    work["exit_raw_open"] = pd.to_numeric(work.get("exit_raw_open"), errors="coerce")
    work["holding_return_raw"] = work["exit_raw_open"] / work["entry_raw_open"] - 1.0

    buy_slip = 1.0 + float(slippage_bps) / 10000.0
    sell_slip = 1.0 - float(slippage_bps) / 10000.0
    gross_ratio = (work["exit_raw_open"] * sell_slip) / (work["entry_raw_open"] * buy_slip)

    if per_trade_notional > 0:
        buy_fee_effective = max(float(per_trade_notional) * float(buy_fee_rate), float(min_commission)) / float(per_trade_notional)
        est_sell_notional = float(per_trade_notional) * gross_ratio.clip(lower=0)
        sell_fee_effective = est_sell_notional.mul(float(sell_fee_rate)).clip(lower=float(min_commission))
        sell_fee_effective = sell_fee_effective / est_sell_notional.where(est_sell_notional > 0)
        sell_fee_effective = sell_fee_effective.fillna(0.0)
    else:
        buy_fee_effective = float(buy_fee_rate)
        sell_fee_effective = float(sell_fee_rate)

    work["holding_return_net"] = gross_ratio * (1.0 - sell_fee_effective - float(stamp_tax_sell)) / (1.0 + buy_fee_effective) - 1.0
    return work


def build_feature_bucket_report(
    frame: pd.DataFrame,
    specs: list[FeatureBucketSpec] | tuple[FeatureBucketSpec, ...] = DEFAULT_FEATURE_BUCKET_SPECS,
    min_count: int = 20,
) -> pd.DataFrame:
    rows: list[dict] = []
    for spec in specs:
        bucketed = frame.copy()
        bucketed["bucket"] = _bucket_series(bucketed[spec.feature], spec)
        bucketed = bucketed.dropna(subset=["bucket", "holding_return_raw", "holding_return_net"])
        if bucketed.empty:
            continue
        grouped = (
            bucketed.groupby("bucket", observed=False)
            .agg(
                sample_count=("bucket", "size"),
                avg_holding_return_raw=("holding_return_raw", "mean"),
                median_holding_return_raw=("holding_return_raw", "median"),
                win_rate_raw=("holding_return_raw", lambda s: (pd.to_numeric(s, errors="coerce") > 0).mean()),
                avg_holding_return_net=("holding_return_net", "mean"),
                median_holding_return_net=("holding_return_net", "median"),
                win_rate_net=("holding_return_net", lambda s: (pd.to_numeric(s, errors="coerce") > 0).mean()),
            )
            .reset_index()
        )
        grouped = grouped[grouped["sample_count"] >= int(min_count)].copy()
        if grouped.empty:
            continue
        grouped["feature"] = spec.feature
        grouped["bucket_order"] = grouped["bucket"].apply(lambda label: list(spec.labels).index(str(label)))
        rows.extend(grouped.to_dict(orient="records"))
    if not rows:
        return pd.DataFrame(
            columns=[
                "feature",
                "bucket",
                "sample_count",
                "avg_holding_return_raw",
                "median_holding_return_raw",
                "win_rate_raw",
                "avg_holding_return_net",
                "median_holding_return_net",
                "win_rate_net",
                "bucket_order",
            ]
        )
    report = pd.DataFrame(rows)
    return report.sort_values(["feature", "bucket_order"]).reset_index(drop=True)


def load_feature_scan_frame(
    processed_dir: str | Path,
    start_date: str = "",
    end_date: str = "",
    entry_offset: int = 1,
    exit_offset: int = 2,
    strict_executable: bool = True,
) -> pd.DataFrame:
    if exit_offset <= entry_offset:
        raise ValueError("exit_offset must be greater than entry_offset")

    folder = Path(processed_dir).expanduser()
    if not folder.is_absolute():
        folder = Path.cwd() / folder
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"processed_dir not found: {folder}")

    frames: list[pd.DataFrame] = []
    for file_path in sorted(folder.glob("*.csv")):
        if file_path.name == "processing_manifest.csv":
            continue
        frame = pd.read_csv(file_path, encoding="utf-8-sig")
        missing = SCAN_REQUIRED_COLUMNS - set(frame.columns)
        if missing:
            raise ValueError(f"{file_path.name} missing scan columns: {sorted(missing)}")

        frame = frame[list(SCAN_REQUIRED_COLUMNS)].copy()
        frame["trade_date"] = frame["trade_date"].astype(str).str.strip()
        frame = _attach_holding_period_labels(frame, entry_offset=entry_offset, exit_offset=exit_offset)
        if start_date:
            frame = frame[frame["trade_date"] >= str(start_date).strip()].copy()
        if end_date:
            frame = frame[frame["trade_date"] <= str(end_date).strip()].copy()
        if frame.empty:
            continue

        for col in SCAN_REQUIRED_COLUMNS - {"trade_date", "symbol", "name", "board", "market", "can_buy_open_t", "can_sell_t"}:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
        for col in ["can_buy_open_t", "can_sell_t", "entry_can_buy_open", "exit_can_sell_open"]:
            frame[col] = frame[col].astype(str).str.lower().isin(["true", "1", "yes"])
        frames.append(frame)

    if not frames:
        raise ValueError("no rows available for feature scan")
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["entry_raw_open", "exit_raw_open"]).copy()
    if strict_executable:
        combined = combined[combined["entry_can_buy_open"] & combined["exit_can_sell_open"]].copy()
    if combined.empty:
        raise ValueError("no executable rows available for feature scan")
    return combined.reset_index(drop=True)


def build_scan_overview(frame: pd.DataFrame) -> dict[str, float | int]:
    raw = pd.to_numeric(frame.get("holding_return_raw"), errors="coerce")
    net = pd.to_numeric(frame.get("holding_return_net"), errors="coerce")
    return {
        "sample_count": int(len(frame)),
        "avg_holding_return_raw": float(raw.mean()) if len(raw) else 0.0,
        "avg_holding_return_net": float(net.mean()) if len(net) else 0.0,
        "win_rate_raw": float((raw > 0).mean()) if len(raw) else 0.0,
        "win_rate_net": float((net > 0).mean()) if len(net) else 0.0,
    }


def render_feature_scan_summary(
    overview: dict[str, float | int],
    report: pd.DataFrame,
    entry_offset: int,
    exit_offset: int,
    top_n: int = 3,
) -> str:
    lines = [
        "# T 日信号分层扫描小结",
        "",
        "## 标签口径",
        "",
        f"- 买入口径：`T+{entry_offset}` 日原始开盘价",
        f"- 卖出口径：`T+{exit_offset}` 日原始开盘价",
        "",
        "## 样本概览",
        "",
        f"- 样本数：{overview.get('sample_count', 0)}",
        f"- 平均毛收益：{overview.get('avg_holding_return_raw', 0.0):.6f}",
        f"- 平均净收益：{overview.get('avg_holding_return_net', 0.0):.6f}",
        f"- 毛收益胜率：{overview.get('win_rate_raw', 0.0):.4f}",
        f"- 净收益胜率：{overview.get('win_rate_net', 0.0):.4f}",
        "",
        "## 各特征最优分层",
        "",
    ]
    if report.empty:
        lines.append("- 当前没有达到最小样本门槛的分层结果。")
        return "\n".join(lines)

    for feature in sorted(report["feature"].dropna().unique().tolist()):
        top = report[report["feature"] == feature].sort_values(["avg_holding_return_net", "sample_count"], ascending=[False, False]).head(top_n)
        lines.append(f"### `{feature}`")
        lines.append("")
        for _, row in top.iterrows():
            lines.append(
                f"- `{row['bucket']}`：样本 {int(row['sample_count'])}，平均毛收益 {float(row['avg_holding_return_raw']):.6f}，"
                f"平均净收益 {float(row['avg_holding_return_net']):.6f}，净收益胜率 {float(row['win_rate_net']):.4f}"
            )
        lines.append("")
    return "\n".join(lines)


def write_feature_scan_outputs(
    out_dir: Path,
    overview: dict[str, float | int],
    report: pd.DataFrame,
    entry_offset: int,
    exit_offset: int,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(overview)
    payload["entry_offset"] = entry_offset
    payload["exit_offset"] = exit_offset
    (out_dir / "scan_overview.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report.to_csv(out_dir / "feature_bucket_report.csv", index=False, encoding="utf-8-sig")
    (out_dir / "feature_scan_summary.md").write_text(
        render_feature_scan_summary(overview, report, entry_offset=entry_offset, exit_offset=exit_offset),
        encoding="utf-8",
    )
