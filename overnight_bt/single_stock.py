from __future__ import annotations

import math
import os
import re
from pathlib import Path

import pandas as pd

from .expressions import evaluate_conditions, max_required_offset, parse_condition_expr
from .models import SingleStockBacktestRequest
from .market_data_store import DISABLE_LEGACY_FALLBACK, read_feature_rows
from .sqlite_only_guard import assert_sqlite_only_allowed, is_sqlite_only_enabled
from . import stock_pool_templates
from .stock_pool_templates import DEFAULT_USERNAME, _connect_readonly, read_template_symbols


REQUIRED_BY_TIMING = {
    "same_day_close": {"close"},
    "next_day_open": {"open", "close"},
}

_WINDOWS_DRIVE_RE = re.compile(r"^(?P<drive>[A-Za-z]):[\\/](?P<rest>.*)$")
_WSL_MOUNT_RE = re.compile(r"^/mnt/(?P<drive>[A-Za-z])/(?P<rest>.+)$")
_MSYS_MOUNT_RE = re.compile(r"^/(?P<drive>[A-Za-z])/(?P<rest>.+)$")


def _normalize_columns(df: pd.DataFrame) -> dict[str, str]:
    return {str(col).strip().lower(): str(col) for col in df.columns}


def _pick_excel_engine(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return "openpyxl"
    if suffix == ".xls":
        return "xlrd"
    raise ValueError(f"unsupported excel suffix: {suffix}")


def _clean_path_text(path_text: str) -> str:
    text = str(path_text or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    return text


def _path_candidates(path_text: str) -> list[Path]:
    text = _clean_path_text(path_text)
    if not text:
        return [Path("")]

    candidates: list[Path] = []
    normalized = text.replace("\\", "/")

    if os.name == "nt":
        for pattern in (_WSL_MOUNT_RE, _MSYS_MOUNT_RE):
            match = pattern.match(normalized)
            if match:
                candidates.append(Path(f"{match.group('drive').upper()}:/{match.group('rest')}"))
                break
    else:
        match = _WINDOWS_DRIVE_RE.match(normalized)
        if match:
            candidates.append(Path(f"/mnt/{match.group('drive').lower()}/{match.group('rest')}"))

    candidates.append(Path(text))

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def _resolve_excel_path(excel_path: str) -> Path:
    candidates = _path_candidates(excel_path)
    resolved_candidates: list[Path] = []
    for candidate in candidates:
        path = candidate.expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()
        resolved_candidates.append(path)
        if path.exists() and path.is_file():
            return path

    attempted = ", ".join(str(path) for path in resolved_candidates)
    raise FileNotFoundError(f"excel not found: {_clean_path_text(excel_path)}; tried: {attempted}")


def _symbol_key(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text


def _load_single_stock_processed(processed_dir: str, symbol_query: str) -> tuple[pd.DataFrame, str, str, str]:
    assert_sqlite_only_allowed("single-stock processed CSV folder", str(processed_dir))
    query = str(symbol_query or "").strip()
    if not query:
        raise ValueError("股票代码或名称不能为空")

    loaded, _ = load_processed_folder(processed_dir)
    query_key = _symbol_key(query)
    exact_matches = [
        item
        for item in loaded
        if _symbol_key(item.symbol) == query_key or str(item.name).strip() == query
    ]
    fuzzy_matches = [
        item
        for item in loaded
        if query and query in str(item.name).strip()
    ]
    matches = exact_matches or fuzzy_matches
    if not matches:
        raise ValueError(f"处理后数据目录中找不到股票：{query}")
    if len(matches) > 1:
        names = ", ".join(f"{item.symbol} {item.name}" for item in matches[:8])
        raise ValueError(f"股票匹配到多个结果，请输入更精确的代码或名称：{names}")

    item = matches[0]
    work = item.df.copy()
    work["trade_date_text"] = work["trade_date"].astype(str).str.strip()
    work["trade_date"] = pd.to_datetime(work["trade_date_text"], format="%Y%m%d", errors="coerce")
    work = work.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    if work.empty:
        raise ValueError(f"{item.symbol} {item.name} 没有可用交易日期")
    return work, item.symbol, item.name, "前复权价格"


_SQLITE_TEXT_COLUMNS = {
    "symbol",
    "ts_code",
    "name",
    "trade_date",
    "trade_date_text",
    "industry",
    "market",
    "board",
    "created_at",
    "updated_at",
    "resolved_name",
}
_SQLITE_BOOLEAN_COLUMNS = {
    "is_suspended_t",
    "is_suspended_t1",
    "can_buy_t",
    "can_buy_open_t",
    "can_buy_open_t1",
    "can_sell_t",
    "can_sell_t1",
}
_TRUE_VALUES = {"1", "true", "yes", "y"}
_FALSE_VALUES = {"0", "false", "no", "n"}


def _bool_value(value, default: bool = True) -> bool:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return default
        if text in _TRUE_VALUES:
            return True
        if text in _FALSE_VALUES:
            return False
    return bool(value)


def _first_numeric_series(work: pd.DataFrame, columns: list[str]) -> pd.Series:
    for column in columns:
        if column in work.columns:
            return pd.to_numeric(work[column], errors="coerce")
    return pd.Series([pd.NA] * len(work), index=work.index, dtype="Float64")


def _ensure_price_column(work: pd.DataFrame, column: str, fallbacks: list[str]) -> None:
    fallback = _first_numeric_series(work, fallbacks)
    if column not in work.columns:
        work[column] = fallback
    else:
        work[column] = pd.to_numeric(work[column], errors="coerce").fillna(fallback)


def _prepare_single_stock_frame(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    if "trade_date" not in df.columns:
        raise ValueError(f"{source_name} missing trade_date")
    work = df.copy()
    if "resolved_name" in work.columns:
        resolved = work["resolved_name"].fillna("").astype(str).str.strip()
        current = work["name"].fillna("").astype(str).str.strip() if "name" in work.columns else pd.Series([""] * len(work), index=work.index)
        work["name"] = current.where(current != "", resolved)
        work = work.drop(columns=["resolved_name"])
    work["trade_date_text"] = work["trade_date"].astype(str).str.strip()
    work["trade_date"] = pd.to_datetime(work["trade_date_text"], format="%Y%m%d", errors="coerce")
    work = work.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    if work.empty:
        raise ValueError(f"{source_name} has no valid trade_date rows")

    for column in list(work.columns):
        if column in _SQLITE_BOOLEAN_COLUMNS:
            work[column] = work[column].map(lambda value: _bool_value(value, default=False))
        elif column not in _SQLITE_TEXT_COLUMNS:
            work[column] = pd.to_numeric(work[column], errors="coerce")

    _ensure_price_column(work, "close", ["qfq_close", "raw_close"])
    _ensure_price_column(work, "open", ["qfq_open", "raw_open", "close"])
    _ensure_price_column(work, "high", ["qfq_high", "raw_high", "close"])
    _ensure_price_column(work, "low", ["qfq_low", "raw_low", "close"])
    if "vol" not in work.columns:
        work["vol"] = 0.0
    else:
        work["vol"] = pd.to_numeric(work["vol"], errors="coerce").fillna(0.0)
    return work


def _stock_pool_scope(username: str, template_name: str) -> tuple[str, str]:
    clean_username = str(username or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME
    clean_template = str(template_name or "").strip()
    return clean_username, clean_template


def _sqlite_candidate_rows(conn, query: str, username: str, template_name: str) -> list[dict]:
    scope_join = ""
    scope_params: list[str] = []
    name_expr = "COALESCE(NULLIF(MAX(f.name), ''), NULLIF(MAX(b.name), ''), '') AS name"
    name_fields = ["f.name", "b.name"]
    if template_name:
        scope_join = "JOIN stock_pool_template_stocks s ON s.symbol=f.symbol AND s.username=? AND s.template_name=?"
        scope_params = [username, template_name]
        name_expr = "COALESCE(NULLIF(MAX(f.name), ''), NULLIF(MAX(s.stock_name), ''), NULLIF(MAX(b.name), ''), '') AS name"
        name_fields = ["f.name", "s.stock_name", "b.name"]

    def run(where_sql: str, params: list[str]) -> list[dict]:
        rows = conn.execute(
            f"""
            SELECT f.symbol, {name_expr}
            FROM stock_daily_features f
            {scope_join}
            LEFT JOIN stock_basic b ON b.symbol=f.symbol
            WHERE {where_sql}
            GROUP BY f.symbol
            ORDER BY f.symbol
            """,
            [*scope_params, *params],
        ).fetchall()
        return [dict(row) for row in rows]

    query_key = _symbol_key(query)
    if query_key.isdigit():
        exact_symbol = run("f.symbol=?", [query_key.zfill(6)])
        if exact_symbol:
            return exact_symbol

    exact_where = " OR ".join(f"{field}=?" for field in name_fields)
    exact_name = run(exact_where, [query] * len(name_fields))
    if exact_name:
        return exact_name

    like = f"%{query}%"
    fuzzy_where = " OR ".join(f"{field} LIKE ?" for field in name_fields)
    return run(fuzzy_where, [like] * len(name_fields))



def _template_candidate_rows(stocks: list[dict], query: str) -> list[dict]:
    query_text = str(query or "").strip()
    query_key = _symbol_key(query_text)

    def as_row(stock: dict) -> dict:
        return {"symbol": str(stock.get("symbol") or "").strip().zfill(6), "name": str(stock.get("stock_name") or "").strip()}

    if query_key.isdigit():
        exact_symbol = [as_row(stock) for stock in stocks if _symbol_key(str(stock.get("symbol") or "")) == query_key.zfill(6)]
        if exact_symbol:
            return exact_symbol

    exact_name = [as_row(stock) for stock in stocks if str(stock.get("stock_name") or "").strip() == query_text]
    if exact_name:
        return exact_name

    return [as_row(stock) for stock in stocks if query_text and query_text in str(stock.get("stock_name") or "").strip()]

def _load_single_stock_sqlite(
    symbol_query: str,
    db_path: str | Path | None,
    username: str = DEFAULT_USERNAME,
    template_name: str = "",
) -> tuple[pd.DataFrame, str, str, str]:
    query = str(symbol_query or "").strip()
    if not query:
        raise ValueError("stock code or name is required")
    clean_username, clean_template = _stock_pool_scope(username, template_name)
    resolved_db_path = db_path or stock_pool_templates.DEFAULT_DB_PATH

    if clean_template:
        stocks = read_template_symbols(clean_username, clean_template, db_path=resolved_db_path)
        matches = _template_candidate_rows(stocks, query)
    else:
        with _connect_readonly(resolved_db_path) as conn:
            matches = _sqlite_candidate_rows(conn, query, clean_username, clean_template)

    if not matches:
        scope = f"template {clean_username}/{clean_template}" if clean_template else "stock pool SQLite"
        raise ValueError(f"{scope} does not contain stock: {query}")
    if len(matches) > 1:
        names = ", ".join(f"{row['symbol']} {row.get('name') or ''}".strip() for row in matches[:8])
        raise ValueError(f"multiple stocks matched; use a more specific code or name: {names}")

    symbol = str(matches[0]["symbol"]).strip().zfill(6)
    legacy_db_path = DISABLE_LEGACY_FALLBACK if is_sqlite_only_enabled() else resolved_db_path
    rows = read_feature_rows([symbol], legacy_db_path=legacy_db_path)
    if not rows:
        raise ValueError(f"stock pool SQLite has no daily rows for {symbol}")
    frame = pd.DataFrame(rows)
    template_name_value = str(matches[0].get("name") or "").strip()
    if template_name_value:
        if "name" not in frame.columns:
            frame["name"] = template_name_value
        else:
            frame["name"] = frame["name"].fillna("").replace("", template_name_value)
    work = _prepare_single_stock_frame(frame, f"{symbol}.sqlite")
    stock_name = str(work.iloc[0].get("name") or template_name_value).strip()
    return work, symbol, stock_name, "前复权价格"


def load_single_stock_excel(excel_path: str, execution_timing: str) -> tuple[pd.DataFrame, str, str, str]:
    assert_sqlite_only_allowed("single-stock Excel file", str(excel_path))
    path = _resolve_excel_path(excel_path)

    engine = _pick_excel_engine(path)
    try:
        df = pd.read_excel(path, engine=engine)
    except ImportError as exc:
        if engine == "xlrd":
            raise ValueError("reading .xls requires xlrd; install xlrd or convert file to .xlsx") from exc
        raise ValueError(f"failed to read excel: {path.name}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"failed to read excel: {path.name}: {exc}") from exc

    cols = _normalize_columns(df)
    if "trade_date" not in cols:
        raise ValueError("missing required column: trade_date")

    missing = [column for column in REQUIRED_BY_TIMING[execution_timing] if column not in cols]
    if missing:
        raise ValueError(f"missing required columns for {execution_timing}: {missing}")

    renamed = {original: normalized for normalized, original in cols.items()}
    work = df.rename(columns=renamed).copy()

    work["trade_date"] = pd.to_datetime(work["trade_date"].astype(str).str.strip(), errors="coerce")
    work = work.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    if work.empty:
        raise ValueError("excel has no valid trade_date rows")

    numeric_candidates = [
        "open",
        "high",
        "low",
        "close",
        "pct_chg",
        "vol",
        "vol5",
        "vol10",
        "amount",
        "m120",
        "m60",
        "m30",
        "m20",
        "m10",
        "m5",
        "ma5",
        "ma10",
        "ma20",
        "amp",
        "amp5",
        "vr",
        "bias_ma5",
        "bias_ma10",
        "ret1",
        "ret2",
        "ret3",
        "body_pct",
        "close_pos_in_bar",
        "upper_shadow_pct",
        "lower_shadow_pct",
    ]
    for column in work.columns:
        if column in numeric_candidates or column.startswith(("avg5m", "avg10m", "high_", "low_")):
            work[column] = pd.to_numeric(work[column], errors="coerce")

    close_series = pd.to_numeric(work.get("close"), errors="coerce")
    for column in ["open", "high", "low"]:
        if column not in work.columns:
            work[column] = close_series
        else:
            work[column] = pd.to_numeric(work[column], errors="coerce").fillna(close_series)
    if "vol" not in work.columns:
        work["vol"] = 0.0
    else:
        work["vol"] = pd.to_numeric(work["vol"], errors="coerce").fillna(0.0)

    stem_parts = path.stem.split("_", 1)
    stock_code = stem_parts[0] if stem_parts else path.stem
    stock_name = stem_parts[1] if len(stem_parts) > 1 else ""
    work["trade_date_text"] = work["trade_date"].dt.strftime("%Y%m%d")
    return work, stock_code, stock_name, "除权价格"


def load_single_stock_data(req: SingleStockBacktestRequest) -> tuple[pd.DataFrame, str, str, str]:
    data_source = str(getattr(req, "data_source", "stock_pool") or "stock_pool")
    if data_source != "stock_pool":
        raise RuntimeError("legacy single-stock CSV/Excel input has been removed; use stock pool SQLite data instead")
    if str(req.symbol or "").strip():
        return _load_single_stock_sqlite(
            req.symbol,
            getattr(req, "stock_pool_db_path", "") or None,
            username=getattr(req, "stock_pool_username", DEFAULT_USERNAME),
            template_name=getattr(req, "stock_pool_template_name", ""),
        )
    raise ValueError("stock code is required; default source is stock pool SQLite")


def _apply_date_range(df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    work = df
    if start_date:
        start_dt = pd.to_datetime(str(start_date).strip(), format="%Y%m%d", errors="coerce")
        if pd.isna(start_dt):
            raise ValueError(f"invalid start_date: {start_date}, expected YYYYMMDD")
        work = work[work["trade_date"] >= start_dt]
    if end_date:
        end_dt = pd.to_datetime(str(end_date).strip(), format="%Y%m%d", errors="coerce")
        if pd.isna(end_dt):
            raise ValueError(f"invalid end_date: {end_date}, expected YYYYMMDD")
        work = work[work["trade_date"] <= end_dt]
    work = work.reset_index(drop=True)
    if work.empty:
        raise ValueError("no data in selected date range")
    return work


def _execution_point(df: pd.DataFrame, signal_idx: int, timing: str) -> tuple[int | None, float | None, str]:
    if timing == "same_day_close":
        row = df.iloc[signal_idx]
        price = row.get("raw_close", row.get("close"))
        if pd.isna(price):
            return None, None, "close is NaN"
        return signal_idx, float(price), "same_day_close"

    exec_idx = signal_idx + 1
    if exec_idx >= len(df):
        return None, None, "next day does not exist"
    row = df.iloc[exec_idx]
    price = row.get("raw_open", row.get("open"))
    if pd.isna(price):
        return None, None, "next day open is NaN"
    return exec_idx, float(price), "next_day_open"


def _row_price(row: dict, raw_key: str, fallback_key: str) -> float | None:
    raw = row.get(raw_key, row.get(fallback_key))
    if pd.isna(raw):
        return None
    return float(raw)


def _row_float(row: dict, key: str) -> float | None:
    value = row.get(key)
    if pd.isna(value):
        return None
    return float(value)


def _build_eval_row(df: pd.DataFrame, idx: int, max_offset: int) -> dict:
    eval_row = df.iloc[idx].to_dict()
    for lag in range(1, max_offset + 1):
        lag_idx = idx - lag
        if lag_idx < 0:
            continue
        lag_row = df.iloc[lag_idx].to_dict()
        for key, value in lag_row.items():
            eval_row[f"{key}[{lag}]"] = value
    return eval_row


def _metric_definitions() -> list[dict]:
    return [
        {"key": "ending_equity", "label": "期末总资产", "formula": "ending_cash + ending_market_value", "meaning": "回测结束时现金与持仓市值之和。"},
        {"key": "total_return", "label": "总收益率", "formula": "ending_equity / initial_cash - 1", "meaning": "整个回测期间总资产相对初始资金的涨跌幅。"},
        {"key": "win_rate", "label": "胜率", "formula": "盈利卖出次数 / 卖出次数", "meaning": "只统计平仓卖出单，衡量单笔交易胜率。"},
        {"key": "max_drawdown", "label": "最大回撤", "formula": "max((peak_equity - equity_t) / peak_equity)", "meaning": "资金曲线从历史峰值回落的最大比例。"},
        {"key": "annualized_return", "label": "年化收益率", "formula": "(ending_equity / initial_cash)^(252 / N) - 1", "meaning": "用 252 个交易日换算后的年化收益率。"},
        {"key": "sharpe_ratio", "label": "夏普比率", "formula": "mean(daily_return) / std(daily_return) * sqrt(252)", "meaning": "风险调整后收益，风险自由利率固定为 0。"},
        {"key": "profit_factor", "label": "盈亏比", "formula": "sum(盈利已实现盈亏) / abs(sum(亏损已实现盈亏))", "meaning": "总盈利与总亏损的比值。"},
        {"key": "realized_pnl", "label": "已实现盈亏", "formula": "所有卖出单净额 - 对应持仓成本", "meaning": "已经落袋的盈利或亏损。"},
        {"key": "unrealized_pnl", "label": "未实现盈亏", "formula": "(last_close - avg_cost_per_share) * ending_position", "meaning": "回测结束时持仓尚未卖出的浮动盈亏。"},
    ]


def _strict_execution_block_reason(row: dict, action: str, timing: str, strict_execution: bool) -> str:
    if not strict_execution:
        return ""
    if action == "BUY":
        flag = "can_buy_t" if timing == "same_day_close" else "can_buy_open_t"
        if not _bool_value(row.get(flag), default=True):
            return "strict execution blocked buy at open"
    if action == "SELL" and not _bool_value(row.get("can_sell_t"), default=True):
        return "strict execution blocked sell at open"
    return ""


def _blocked_trade_row(order: dict, row: dict, trade_date_text: str, reason: str, cash: float, position: int) -> dict:
    action = str(order.get("action") or "")
    close_price = _row_price(row, "raw_close", "close") or 0.0
    market_value = close_price * position
    return {
        "signal_date": order.get("signal_date", trade_date_text),
        "trade_date": trade_date_text,
        "action": f"{action}_BLOCKED",
        "price": None,
        "shares": int(position if action == "SELL" else 0),
        "gross_amount": None,
        "fees": None,
        "net_amount": None,
        "cash_after": round(cash, 2),
        "position_after": int(position),
        "position_market_value_after": round(market_value, 2),
        "equity_after": round(cash + market_value, 2),
        "pnl_realized": None,
        "reason": reason,
    }


def run_single_stock_backtest(req: SingleStockBacktestRequest) -> dict:
    df, stock_code, stock_name, chart_price_basis = load_single_stock_data(req)
    df = _apply_date_range(df, req.start_date, req.end_date)

    buy_rules = parse_condition_expr(req.buy_condition)
    sell_rules = parse_condition_expr(req.sell_condition) if str(req.sell_condition or "").strip() else []
    max_offset = max(max_required_offset(buy_rules), max_required_offset(sell_rules))

    cash = float(req.initial_cash)
    position = 0
    avg_cost_per_share = 0.0
    last_buy_exec_idx: int | None = None
    max_hold_exit_idx: int | None = None
    pending_order: dict | None = None

    trades: list[dict] = []
    daily_rows: list[dict] = []
    realized_pnl_total = 0.0
    gross_profit_total = 0.0
    gross_loss_total = 0.0
    win_count = 0
    loss_count = 0
    buy_streak = 0
    sell_streak = 0
    blocked_buy_count = 0
    blocked_sell_count = 0
    equity_curve: list[float] = []

    def process_order(order: dict, current_row: dict, current_date: str) -> tuple[str, str]:
        nonlocal cash, position, avg_cost_per_share, last_buy_exec_idx, max_hold_exit_idx
        nonlocal realized_pnl_total, gross_profit_total, gross_loss_total, win_count, loss_count
        nonlocal blocked_buy_count, blocked_sell_count

        action = str(order["action"])
        block_reason = _strict_execution_block_reason(current_row, action, req.execution_timing, bool(req.strict_execution))
        if block_reason:
            if action == "BUY":
                blocked_buy_count += 1
            else:
                blocked_sell_count += 1
            trades.append(_blocked_trade_row(order, current_row, current_date, block_reason, cash, position))
            return f"{action}_BLOCKED", block_reason

        price_timing = str(order.get("price_timing") or req.execution_timing)
        if price_timing in {"next_day_open", "current_open"}:
            exec_price = _row_price(current_row, "raw_open", "open")
        elif price_timing == "same_day_close":
            exec_price = _row_price(current_row, "raw_close", "close")
        else:
            raw_order_price = order.get("price")
            exec_price = None if raw_order_price is None or pd.isna(raw_order_price) else float(raw_order_price)
        if exec_price is None:
            missing_reason = f"{price_timing} price is NaN"
            if action == "BUY":
                blocked_buy_count += 1
            else:
                blocked_sell_count += 1
            trades.append(_blocked_trade_row(order, current_row, current_date, missing_reason, cash, position))
            return f"{action}_BLOCKED", missing_reason

        current_close = _row_price(current_row, "raw_close", "close") or exec_price
        if action == "BUY":
            shares = int(order["shares"])
            gross_amount = exec_price * shares
            fees = float(order["fees"])
            net_amount = gross_amount + fees
            cash -= net_amount
            position = shares
            avg_cost_per_share = net_amount / shares if shares else 0.0
            last_buy_exec_idx = idx
            max_hold_exit_idx = idx + int(req.max_hold_days) if int(req.max_hold_days or 0) > 0 else None
            position_market_value_after = current_close * position
            equity_after = cash + position_market_value_after
            trades.append(
                {
                    "signal_date": order["signal_date"],
                    "trade_date": current_date,
                    "action": "BUY",
                    "price": round(exec_price, 4),
                    "shares": int(shares),
                    "gross_amount": round(gross_amount, 2),
                    "fees": round(fees, 2),
                    "net_amount": round(net_amount, 2),
                    "cash_after": round(cash, 2),
                    "position_after": int(position),
                    "position_market_value_after": round(position_market_value_after, 2),
                    "equity_after": round(equity_after, 2),
                    "pnl_realized": 0.0,
                    "reason": order["reason"],
                }
            )
            return "BUY", order["reason"]

        shares = int(position)
        gross_amount = exec_price * shares
        fees = gross_amount * (req.sell_fee_rate + req.stamp_tax_sell)
        net_amount = gross_amount - fees
        realized = net_amount - (avg_cost_per_share * shares)
        cash += net_amount
        position = 0
        avg_cost_per_share = 0.0
        max_hold_exit_idx = None
        if realized > 0:
            win_count += 1
            gross_profit_total += realized
        elif realized < 0:
            loss_count += 1
            gross_loss_total += abs(realized)
        realized_pnl_total += realized
        equity_after = cash
        trades.append(
            {
                "signal_date": order["signal_date"],
                "trade_date": current_date,
                "action": "SELL",
                "price": round(exec_price, 4),
                "shares": int(shares),
                "gross_amount": round(gross_amount, 2),
                "fees": round(fees, 2),
                "net_amount": round(net_amount, 2),
                "cash_after": round(cash, 2),
                "position_after": 0,
                "position_market_value_after": 0.0,
                "equity_after": round(equity_after, 2),
                "pnl_realized": round(realized, 2),
                "reason": order["reason"],
            }
        )
        return "SELL", order["reason"]

    for idx in range(len(df)):
        row = df.iloc[idx].to_dict()
        trade_date_text = str(row.get("trade_date_text", ""))
        executed_action = ""
        executed_reason = ""

        if pending_order and pending_order["exec_idx"] <= idx:
            current_order = pending_order
            executed_action, executed_reason = process_order(current_order, row, trade_date_text)
            pending_order = None
            if executed_action == "SELL_BLOCKED" and idx + 1 < len(df):
                pending_order = {
                    **current_order,
                    "exec_idx": idx + 1,
                    "reason": f"{current_order.get('reason', '')}; retry after blocked sell".strip("; "),
                }

        if pending_order is None and position > 0 and max_hold_exit_idx is not None and idx >= max_hold_exit_idx:
            exec_price = _row_price(row, "raw_open", "open")
            max_order = {
                "action": "SELL",
                "signal_date": trade_date_text,
                "exec_idx": idx,
                "price": float(exec_price) if exec_price is not None else 0.0,
                "price_timing": "current_open",
                "reason": f"max hold reached ({req.max_hold_days}) via current_open",
            }
            if exec_price is None:
                blocked_sell_count += 1
                executed_action = "SELL_BLOCKED"
                executed_reason = "max hold sell but current open is NaN"
                trades.append(_blocked_trade_row(max_order, row, trade_date_text, executed_reason, cash, position))
            else:
                executed_action, executed_reason = process_order(max_order, row, trade_date_text)

        eval_row = _build_eval_row(df, idx, max_offset)
        buy_ok, buy_reason = evaluate_conditions(eval_row, buy_rules)
        if sell_rules:
            sell_ok, sell_reason = evaluate_conditions(eval_row, sell_rules)
        else:
            sell_ok, sell_reason = False, "sell condition disabled"

        buy_streak = buy_streak + 1 if buy_ok else 0
        sell_streak = sell_streak + 1 if sell_ok else 0

        scheduled_action = ""
        scheduled_trade_date = ""
        signal_reason = "no signal"

        if pending_order is None:
            sell_signal_hit = bool(sell_rules) and position > 0 and sell_streak >= req.sell_confirm_days
            if sell_signal_hit:
                exec_idx, exec_price, px_src = _execution_point(df, idx, req.execution_timing)
                if exec_idx is not None and exec_price is not None:
                    pending_order = {
                        "action": "SELL",
                        "signal_date": trade_date_text,
                        "exec_idx": exec_idx,
                        "price": float(exec_price),
                        "price_timing": px_src,
                        "reason": f"sell streak reached ({sell_streak}) via {px_src}",
                    }
                    scheduled_action = "SELL"
                    scheduled_trade_date = str(df.iloc[exec_idx].get("trade_date_text", trade_date_text))
                    signal_reason = sell_reason
                    if pending_order["exec_idx"] == idx:
                        current_order = pending_order
                        executed_action, executed_reason = process_order(current_order, row, trade_date_text)
                        pending_order = None
                        if executed_action == "SELL_BLOCKED" and idx + 1 < len(df):
                            pending_order = {
                                **current_order,
                                "exec_idx": idx + 1,
                                "reason": f"{current_order.get('reason', '')}; retry after blocked sell".strip("; "),
                            }
                else:
                    signal_reason = f"sell signal but cannot execute: {px_src}"
            elif position == 0 and buy_streak >= req.buy_confirm_days:
                cooldown_ok = last_buy_exec_idx is None or (idx - last_buy_exec_idx) > req.buy_cooldown_days
                if cooldown_ok:
                    exec_idx, exec_price, px_src = _execution_point(df, idx, req.execution_timing)
                    if exec_idx is not None and exec_price is not None:
                        gross_per_lot = exec_price * req.lot_size
                        fee_per_lot = gross_per_lot * req.buy_fee_rate
                        lot_cost = gross_per_lot + fee_per_lot
                        budget = min(float(req.per_trade_budget), cash)
                        lots = int(budget // lot_cost) if lot_cost > 0 else 0
                        shares = lots * req.lot_size
                        if shares > 0:
                            fees = exec_price * shares * req.buy_fee_rate
                            pending_order = {
                                "action": "BUY",
                                "signal_date": trade_date_text,
                                "exec_idx": exec_idx,
                                "price": float(exec_price),
                                "price_timing": px_src,
                                "shares": int(shares),
                                "fees": float(fees),
                                "reason": f"buy streak reached ({buy_streak}) via {px_src}",
                            }
                            scheduled_action = "BUY"
                            scheduled_trade_date = str(df.iloc[exec_idx].get("trade_date_text", trade_date_text))
                            signal_reason = buy_reason
                            if pending_order["exec_idx"] == idx:
                                executed_action, executed_reason = process_order(pending_order, row, trade_date_text)
                                pending_order = None
                        else:
                            signal_reason = "insufficient cash for configured trade budget"
                    else:
                        signal_reason = f"buy signal but cannot execute: {px_src}"
                else:
                    signal_reason = f"buy cooldown active ({req.buy_cooldown_days} days)"

        close_price = _row_price(row, "raw_close", "close") or 0.0
        position_market_value = position * close_price
        equity = cash + position_market_value
        equity_curve.append(equity)

        daily_rows.append(
            {
                "trade_date": trade_date_text,
                "open": _row_price(row, "qfq_open", "open"),
                "high": _row_price(row, "qfq_high", "high"),
                "low": _row_price(row, "qfq_low", "low"),
                "close": _row_price(row, "qfq_close", "close"),
                "vol": None if pd.isna(row.get("vol")) else float(row.get("vol")),
                "ma5": _row_float(row, "ma5"),
                "ma10": _row_float(row, "ma10"),
                "ma20": _row_float(row, "ma20"),
                "m5": _row_float(row, "m5"),
                "m10": _row_float(row, "m10"),
                "m20": _row_float(row, "m20"),
                "buy_signal": bool(buy_ok),
                "sell_signal": bool(sell_ok),
                "buy_streak": int(buy_streak),
                "sell_streak": int(sell_streak),
                "scheduled_action": scheduled_action,
                "scheduled_trade_date": scheduled_trade_date,
                "executed_action": executed_action,
                "reason": executed_reason or signal_reason,
                "cash": round(cash, 2),
                "position": int(position),
                "position_market_value": round(position_market_value, 2),
                "equity": round(equity, 2),
            }
        )

    last_row = df.iloc[-1].to_dict()
    last_close = _row_price(last_row, "raw_close", "close") or 0.0
    ending_market_value = position * last_close
    unrealized_pnl = (last_close - avg_cost_per_share) * position if position > 0 else 0.0
    ending_equity = cash + ending_market_value

    returns: list[float] = []
    for idx in range(1, len(equity_curve)):
        prev_equity = equity_curve[idx - 1]
        current_equity = equity_curve[idx]
        if prev_equity > 0:
            returns.append(current_equity / prev_equity - 1.0)

    peak_equity = 0.0
    max_drawdown = 0.0
    for equity in equity_curve:
        if equity > peak_equity:
            peak_equity = equity
        if peak_equity > 0:
            drawdown = (peak_equity - equity) / peak_equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown

    annualized_return = 0.0
    n_days = len(equity_curve)
    if n_days > 1 and req.initial_cash > 0 and ending_equity > 0:
        annualized_return = (ending_equity / req.initial_cash) ** (252.0 / n_days) - 1.0

    sharpe_ratio = 0.0
    if len(returns) >= 2:
        return_series = pd.Series(returns, dtype=float)
        std = float(return_series.std(ddof=0))
        if std > 0:
            sharpe_ratio = float(return_series.mean()) / std * math.sqrt(252.0)

    profit_factor = 0.0
    if gross_profit_total > 0 and gross_loss_total > 0:
        profit_factor = gross_profit_total / gross_loss_total

    executed_trades = [trade for trade in trades if trade["action"] in {"BUY", "SELL"}]
    sell_trades = [trade for trade in trades if trade["action"] == "SELL"]
    summary = {
        "initial_cash": round(req.initial_cash, 2),
        "ending_cash": round(cash, 2),
        "ending_position": int(position),
        "last_close": round(last_close, 4),
        "ending_market_value": round(ending_market_value, 2),
        "ending_equity": round(ending_equity, 2),
        "realized_pnl": round(realized_pnl_total, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "total_return": round(ending_equity / req.initial_cash - 1.0, 4),
        "trade_count": len(executed_trades),
        "buy_count": len([trade for trade in trades if trade["action"] == "BUY"]),
        "sell_count": len(sell_trades),
        "blocked_buy_count": blocked_buy_count,
        "blocked_sell_count": blocked_sell_count,
        "win_rate": round(win_count / len(sell_trades), 4) if sell_trades else 0.0,
        "loss_count": loss_count,
        "sharpe_ratio": round(sharpe_ratio, 4),
        "max_drawdown": round(max_drawdown, 4),
        "annualized_return": round(annualized_return, 4),
        "profit_factor": round(profit_factor, 4),
    }

    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "chart_price_basis": chart_price_basis,
        "summary": summary,
        "metric_definitions": _metric_definitions(),
        "trade_rows": trades,
        "signal_rows": daily_rows,
    }
