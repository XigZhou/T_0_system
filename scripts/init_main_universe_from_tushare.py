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

from overnight_bt.main_universe import DEFAULT_DB_PATH, MainUniverseSaveRequest, save_main_universe
from overnight_bt.market_data_store import upsert_stock_basic_rows
from overnight_bt.utils import latest_open_trade_date, load_env, normalize_date_text

SOURCE_TAG = "tushare_non_st_total_mv_gt_300y"
DEFAULT_MARKET_CAP_MIN_YI = 300.0


def _normal_symbol(value: object) -> str:
    text = str(value or "").strip()
    if "." in text:
        text = text.split(".", 1)[0]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6) if digits else ""


def _is_non_st_name(name: object) -> bool:
    text = str(name or "").strip().upper()
    if not text:
        return False
    return "ST" not in text and "退" not in text


def _stock_basic_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if frame is None or frame.empty:
        return rows
    for raw in frame.to_dict(orient="records"):
        symbol = _normal_symbol(raw.get("symbol") or raw.get("ts_code"))
        if not symbol or len(symbol) != 6:
            continue
        rows.append(
            {
                "symbol": symbol,
                "ts_code": str(raw.get("ts_code") or "").strip(),
                "name": str(raw.get("name") or "").strip(),
                "industry": str(raw.get("industry") or "").strip(),
                "market": str(raw.get("market") or "").strip(),
                "list_date": normalize_date_text(raw.get("list_date") or "") if str(raw.get("list_date") or "").strip() else "",
                "is_active": 1,
            }
        )
    rows.sort(key=lambda item: item["symbol"])
    return rows


def _market_cap_map(frame: pd.DataFrame) -> dict[str, float]:
    mapping: dict[str, float] = {}
    if frame is None or frame.empty:
        return mapping
    for raw in frame.to_dict(orient="records"):
        ts_code = str(raw.get("ts_code") or "").strip()
        if not ts_code:
            continue
        total_mv = raw.get("total_mv")
        if total_mv is None or pd.isna(total_mv):
            continue
        mapping[ts_code] = float(total_mv)
    return mapping


def initialize_main_universe_by_market_cap(
    *,
    pro: Any,
    db_path: str | Path | None = None,
    as_of: str = "",
    market_cap_min_yi: float = DEFAULT_MARKET_CAP_MIN_YI,
) -> dict[str, Any]:
    clean_as_of = normalize_date_text(as_of or datetime.now().strftime("%Y%m%d"))
    trade_date = latest_open_trade_date(pro, clean_as_of)
    stock_basic = pro.stock_basic(
        exchange="",
        list_status="L",
        fields="ts_code,symbol,name,area,industry,market,list_date",
    )
    if stock_basic is None or stock_basic.empty:
        raise RuntimeError("Tushare stock_basic returned empty data")
    daily_basic = pro.daily_basic(trade_date=trade_date, fields="ts_code,total_mv")
    if daily_basic is None or daily_basic.empty:
        raise RuntimeError(f"Tushare daily_basic returned empty data: {trade_date}")

    basic_rows = _stock_basic_rows(stock_basic)
    total_mv_by_ts_code = _market_cap_map(daily_basic)
    threshold_wan_yuan = float(market_cap_min_yi) * 10000.0
    selected: list[dict[str, Any]] = []
    for row in basic_rows:
        total_mv = total_mv_by_ts_code.get(str(row.get("ts_code") or ""))
        if total_mv is None or total_mv <= threshold_wan_yuan:
            continue
        if not _is_non_st_name(row.get("name")):
            continue
        selected.append(row)

    target_db = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    upsert_stock_basic_rows(basic_rows, db_path=target_db)
    save_result = save_main_universe(
        MainUniverseSaveRequest(
            mode="replace",
            source=SOURCE_TAG,
            rows=[{"symbol": row["symbol"], "ts_code": row["ts_code"], "name": row["name"]} for row in selected],
        ),
        db_path=target_db,
    )
    return {
        "trade_date": trade_date,
        "candidate_count": len(basic_rows),
        "selected_count": len(selected),
        "saved_count": int(save_result.get("saved_count") or 0),
        "market_cap_min_yi": float(market_cap_min_yi),
        "source": SOURCE_TAG,
        "db_path": str(target_db),
        "unresolved": save_result.get("unresolved", []),
        "duplicate_inputs": save_result.get("duplicate_inputs", []),
        "ambiguous": save_result.get("ambiguous", []),
    }


def _build_pro(env_path: Path):
    import tushare as ts

    token = load_env(env_path).get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise ValueError(f"TUSHARE_TOKEN is empty: {env_path}")
    return ts.pro_api(token)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize main_stock_universe from Tushare non-ST A-shares above market-cap threshold")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--env-path", default=str(ROOT / ".env"))
    parser.add_argument("--as-of", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--market-cap-min-yi", type=float, default=DEFAULT_MARKET_CAP_MIN_YI)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = initialize_main_universe_by_market_cap(
        pro=_build_pro(Path(args.env_path)),
        db_path=Path(args.db_path),
        as_of=args.as_of,
        market_cap_min_yi=args.market_cap_min_yi,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
