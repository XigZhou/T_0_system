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

from overnight_bt.theme_universe import (  # noqa: E402
    ThemeUniverseBuildConfig,
    build_theme_tradeable_universe,
    normalize_symbol,
    parse_top_sizes,
    write_theme_tradeable_outputs,
)
from overnight_bt.tushare_data import _create_pro_client  # noqa: E402
from overnight_bt.utils import latest_open_trade_date  # noqa: E402


def _resolve(path_text: str | Path) -> Path:
    path = Path(str(path_text)).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig")


def _fetch_stock_basic(pro) -> pd.DataFrame:
    frame = pro.stock_basic(
        exchange="",
        list_status="L",
        fields="ts_code,symbol,name,area,industry,market,list_date,list_status",
    )
    if frame is None or frame.empty:
        raise RuntimeError("Tushare stock_basic 返回空数据")
    return frame


def _fetch_daily_basic(pro, trade_date: str) -> pd.DataFrame:
    fields = "ts_code,trade_date,close,total_mv,turnover_rate_f,volume_ratio,pe_ttm,pb"
    frame = pro.daily_basic(trade_date=trade_date, fields=fields)
    if frame is None or frame.empty:
        raise RuntimeError(f"Tushare daily_basic 在 {trade_date} 返回空数据")
    return frame


def _load_or_fetch_metadata(args: argparse.Namespace, out_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    if args.basic_csv.strip() and args.daily_basic_csv.strip():
        basic = _read_csv(_resolve(args.basic_csv))
        daily = _read_csv(_resolve(args.daily_basic_csv))
        trade_date = str(daily.get("trade_date", pd.Series([args.as_of])).dropna().astype(str).max() or args.as_of)
        return basic, daily, trade_date

    pro = _create_pro_client(Path(args.env))
    trade_date = latest_open_trade_date(pro, str(args.as_of).strip())
    basic = _fetch_stock_basic(pro)
    daily = _fetch_daily_basic(pro, trade_date)
    source_dir = out_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    basic.to_csv(source_dir / f"stock_basic_{trade_date}.csv", index=False, encoding="utf-8-sig")
    daily.to_csv(source_dir / f"daily_basic_{trade_date}.csv", index=False, encoding="utf-8-sig")
    return basic, daily, trade_date


def _load_current_top100(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["symbol", "name"])
    frame = _read_csv(path)
    if "symbol" not in frame.columns and "ts_code" in frame.columns:
        frame["symbol"] = frame["ts_code"].map(normalize_symbol)
    if "symbol" not in frame.columns:
        return pd.DataFrame(columns=["symbol", "name"])
    frame["symbol"] = frame["symbol"].map(normalize_symbol)
    return frame[frame["symbol"] != ""].drop_duplicates("symbol", keep="first").reset_index(drop=True)


def _parse_excluded_markets(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in str(value or "").split(",") if item.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a unified tradeable theme universe snapshot and L0-L4 market-cap layers without pulling daily bars.")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--exposure-path", default="sector_research/data/processed/stock_theme_exposure.csv")
    parser.add_argument("--current-top100-snapshot", default="data_bundle/universe_snapshot_theme_focus_top100.csv")
    parser.add_argument("--out-dir", default="sector_research/data/processed/theme_tradeable_universe")
    parser.add_argument("--as-of", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--top-sizes", default="500,1000")
    parser.add_argument("--layer-count", type=int, default=5)
    parser.add_argument("--min-total-mv-yi", type=float, default=30.0)
    parser.add_argument("--min-listed-days", type=int, default=250)
    parser.add_argument("--exclude-markets", default="北交所")
    parser.add_argument("--include-st", action="store_true")
    parser.add_argument("--basic-csv", default="", help="Optional offline stock_basic CSV")
    parser.add_argument("--daily-basic-csv", default="", help="Optional offline daily_basic CSV")
    args = parser.parse_args()

    out_dir = _resolve(args.out_dir)
    exposure_path = _resolve(args.exposure_path)
    current_top100_path = _resolve(args.current_top100_snapshot)
    if not exposure_path.exists():
        raise FileNotFoundError(f"个股主题暴露文件不存在: {exposure_path}")

    exposure = _read_csv(exposure_path)
    current_top100 = _load_current_top100(current_top100_path)
    basic, daily, trade_date = _load_or_fetch_metadata(args, out_dir)
    config = ThemeUniverseBuildConfig(
        min_total_mv_yi=float(args.min_total_mv_yi),
        min_listed_days=int(args.min_listed_days),
        excluded_markets=_parse_excluded_markets(args.exclude_markets),
        exclude_st=not bool(args.include_st),
    )
    universe = build_theme_tradeable_universe(
        exposure=exposure,
        stock_basic=basic,
        daily_basic=daily,
        as_of_trade_date=trade_date,
        current_top100_symbols=current_top100["symbol"].tolist() if "symbol" in current_top100.columns else [],
        config=config,
    )
    top_sizes = parse_top_sizes(args.top_sizes)
    outputs = write_theme_tradeable_outputs(
        universe=universe,
        current_top100=current_top100,
        out_dir=out_dir,
        top_sizes=top_sizes,
        layer_count=int(args.layer_count),
    )
    print(json.dumps({
        "as_of_trade_date": trade_date,
        "exposure_rows": int(len(exposure)),
        "universe_rows": int(len(universe)),
        "tradeable_rows": int(universe["is_tradeable_base"].astype(bool).sum()),
        "current_top100_rows": int(len(current_top100)),
        "top_sizes": top_sizes,
        "outputs": outputs,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
