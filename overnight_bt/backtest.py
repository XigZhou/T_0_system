from __future__ import annotations

import io
import math
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .config import REQUIRED_PROCESSED_COLUMNS
from .expressions import (
    compile_score_expression,
    evaluate_conditions,
    evaluate_score_expression,
    max_required_offset,
    parse_condition_expr,
)
from .models import BacktestRequest, PendingOrder, Position
from .utils import to_float


@dataclass
class LoadedSymbol:
    symbol: str
    name: str
    df: pd.DataFrame
    idx_by_date: dict[str, int]


_SCORE_OFFSET_RE = re.compile(r"\[(\d+)\]")


def _normalize_folder(path_text: str) -> Path:
    path = Path(str(path_text).strip()).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _validate_processed_df(df: pd.DataFrame, file_path: Path) -> None:
    missing = REQUIRED_PROCESSED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"{file_path.name} missing required columns: {sorted(missing)}")
    if df["trade_date"].astype(str).duplicated().any():
        raise ValueError(f"{file_path.name} contains duplicated trade_date")
    if not df["trade_date"].astype(str).is_monotonic_increasing:
        raise ValueError(f"{file_path.name} trade_date must be ascending")


def _score_required_offset(score_expression: str) -> int:
    matches = [int(token) for token in _SCORE_OFFSET_RE.findall(str(score_expression or ""))]
    return max(matches, default=0)


def load_processed_folder(folder_path: str, start_date: str = "", end_date: str = "") -> tuple[list[LoadedSymbol], dict]:
    folder = _normalize_folder(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"processed_dir not found: {folder}")
    files = sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() == ".csv" and p.name != "processing_manifest.csv"
    )
    if not files:
        raise FileNotFoundError(f"no csv found under processed_dir: {folder}")

    loaded: list[LoadedSymbol] = []
    for file_path in files:
        df = pd.read_csv(file_path, dtype=str, encoding="utf-8-sig")
        _validate_processed_df(df, file_path)
        df["trade_date"] = df["trade_date"].astype(str).str.strip()
        if start_date:
            df = df[df["trade_date"] >= str(start_date).strip()].copy()
        if end_date:
            df = df[df["trade_date"] <= str(end_date).strip()].copy()
        if df.empty:
            continue

        numeric_cols = {
            "open",
            "high",
            "low",
            "close",
            "raw_open",
            "raw_high",
            "raw_low",
            "raw_close",
            "qfq_open",
            "qfq_high",
            "qfq_low",
            "qfq_close",
            "adj_factor",
            "next_open",
            "next_close",
            "r_on",
            "next_raw_open",
            "next_raw_close",
            "r_on_raw",
            "up_limit",
            "down_limit",
            "vol",
            "vol5",
            "vol10",
            "amount",
            "amount5",
            "amount10",
            "pct_chg",
            "ret1",
            "ret2",
            "ret3",
            "ma5",
            "ma10",
            "ma20",
            "bias_ma5",
            "bias_ma10",
            "amp",
            "amp5",
            "close_to_up_limit",
            "high_to_up_limit",
            "close_pos_in_bar",
            "body_pct",
            "upper_shadow_pct",
            "lower_shadow_pct",
            "vol_ratio_5",
            "ret_accel_3",
            "vol_ratio_3",
            "amount_ratio_3",
            "body_pct_3avg",
            "close_to_up_limit_3max",
            "vr",
            "listed_days",
            "total_mv_snapshot",
            "turnover_rate_snapshot",
        }
        for col in df.columns:
            if (
                col in numeric_cols
                or col.startswith(("avg5m", "avg10m", "high_", "low_", "sh_", "hs300_", "cyb_"))
                or (col.startswith("m") and col[1:].isdigit())
            ):
                df[col] = pd.to_numeric(df[col], errors="coerce")

        for col in [
            "can_buy_t",
            "can_buy_open_t",
            "can_buy_open_t1",
            "can_sell_t",
            "can_sell_t1",
            "is_suspended_t",
            "is_suspended_t1",
        ]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.lower().isin(["true", "1", "yes"])

        symbol = str(df.iloc[0]["symbol"]).strip()
        name = str(df.iloc[0]["name"]).strip()
        loaded.append(
            LoadedSymbol(
                symbol=symbol,
                name=name,
                df=df.reset_index(drop=True),
                idx_by_date={d: i for i, d in enumerate(df["trade_date"].tolist())},
            )
        )

    if not loaded:
        raise ValueError("no data available in selected date range")
    diagnostics = {
        "processed_dir": str(folder),
        "file_count": len(loaded),
    }
    return loaded, diagnostics


def _build_eval_row(df: pd.DataFrame, idx: int, max_offset: int) -> dict[str, Any]:
    row = df.iloc[idx].to_dict()
    for lag in range(1, max_offset + 1):
        if idx - lag < 0:
            continue
        lag_row = df.iloc[idx - lag].to_dict()
        for key, value in lag_row.items():
            row[f"{key}[{lag}]"] = value
    return row


def _position_share_ratio(position: Position, row: pd.Series) -> float:
    current_adj = to_float(row.get("adj_factor"))
    if current_adj is None or position.buy_adj_factor is None or position.buy_adj_factor == 0:
        return 1.0
    return float(current_adj) / float(position.buy_adj_factor)


def _effective_shares(position: Position, row: pd.Series) -> float:
    return float(position.shares) * _position_share_ratio(position, row)


def _mark_to_market_close(position: Position, row: pd.Series, fallback_price: float | None) -> float:
    close_px = to_float(row.get("raw_close"))
    if close_px is None:
        close_px = fallback_price if fallback_price is not None else position.buy_price
    return float(close_px) * _effective_shares(position, row)


def _annualized_return(start_equity: float, end_equity: float, n_days: int) -> float:
    if n_days <= 1 or start_equity <= 0 or end_equity <= 0:
        return 0.0
    return (end_equity / start_equity) ** (252.0 / n_days) - 1.0


def _future_row(item: LoadedSymbol, idx: int, offset: int) -> tuple[str, pd.Series] | None:
    future_idx = idx + int(offset)
    if future_idx < 0 or future_idx >= len(item.df):
        return None
    row = item.df.iloc[future_idx]
    return str(row["trade_date"]).strip(), row


def _within_range(trade_date: str, start_date: str, end_date: str) -> bool:
    if start_date and trade_date < start_date:
        return False
    if end_date and trade_date > end_date:
        return False
    return True


def _count_holding_days(date_index: dict[str, int], start_date: str, end_date: str) -> int:
    if start_date not in date_index or end_date not in date_index:
        return 0
    return max(0, date_index[end_date] - date_index[start_date])


def _effective_max_exit_offset(req: BacktestRequest) -> int:
    if req.max_hold_days > 0:
        return req.entry_offset + req.max_hold_days
    return req.exit_offset


def _next_trade_row(item: LoadedSymbol, idx: int) -> tuple[str, pd.Series] | None:
    return _future_row(item, idx, 1)


def run_portfolio_backtest_loaded(
    loaded: list[LoadedSymbol],
    diagnostics: dict[str, Any],
    req: BacktestRequest,
) -> dict[str, Any]:
    if req.exit_offset <= req.entry_offset:
        raise ValueError("exit_offset must be greater than entry_offset")

    diagnostics = dict(diagnostics)
    buy_rules = parse_condition_expr(req.buy_condition)
    sell_rules = parse_condition_expr(req.sell_condition) if str(req.sell_condition or "").strip() else []
    score_tree, _ = compile_score_expression(req.score_expression)
    max_offset = max(
        max_required_offset(buy_rules),
        max_required_offset(sell_rules),
        _score_required_offset(req.score_expression),
    )

    all_dates = sorted({date for item in loaded for date in item.df["trade_date"].astype(str).tolist()})
    signal_dates = [d for d in all_dates if _within_range(d, req.start_date, req.end_date)]
    if not signal_dates:
        raise ValueError("no signal dates available in selected date range")

    date_index = {date: idx for idx, date in enumerate(all_dates)}
    rows_by_date: dict[str, list[tuple[LoadedSymbol, int]]] = {}
    for item in loaded:
        for date, idx in item.idx_by_date.items():
            rows_by_date.setdefault(date, []).append((item, idx))

    cash = float(req.initial_cash)
    holdings: dict[str, Position] = {}
    pending_orders: dict[str, list[PendingOrder]] = {}
    trades: list[dict] = []
    picks: list[dict] = []
    daily_rows: list[dict] = []
    realized_by_symbol: dict[str, list[float]] = {}
    realized_pnl_by_symbol: dict[str, float] = {}
    last_close_by_symbol: dict[str, float] = {}
    equity_curve: list[float] = []
    blocked_buy_count = 0
    blocked_sell_count = 0
    skipped_buy_cash_count = 0
    sell_condition_exit_count = 0
    max_hold_exit_count = 0

    simulation_start = signal_dates[0]

    for trade_date in all_dates:
        if trade_date < simulation_start:
            continue
        if req.end_date and trade_date > req.end_date and not holdings and not pending_orders:
            break

        date_rows = rows_by_date.get(trade_date, [])
        item_idx_map = {item.symbol: (item, idx) for item, idx in date_rows}
        rows_map = {symbol: item.df.iloc[idx] for symbol, (item, idx) in item_idx_map.items()}

        sold_today = 0
        bought_today = 0
        signal_candidates = 0
        signal_picks = 0

        for symbol in list(holdings.keys()):
            pos = holdings[symbol]
            if trade_date < pos.planned_exit_date:
                continue
            row = rows_map.get(symbol)
            if row is None:
                continue

            open_px = to_float(row.get("raw_open"))
            can_sell = bool(row.get("can_sell_t", False))
            if open_px is None:
                can_sell = False

            exit_reason = pos.exit_reason or "fixed_or_max_exit"

            if req.realistic_execution and not can_sell:
                blocked_sell_count += 1
                trades.append(
                    {
                        "trade_date": trade_date,
                        "signal_date": pos.signal_date,
                        "planned_entry_date": pos.planned_entry_date,
                        "planned_exit_date": pos.planned_exit_date,
                        "max_exit_date": pos.max_exit_date,
                        "symbol": symbol,
                        "name": pos.name,
                        "action": "SELL_BLOCKED",
                        "price": None,
                        "shares": pos.shares,
                        "gross_amount": None,
                        "fees": None,
                        "net_amount": None,
                        "cash_after": round(cash, 2),
                        "exit_reason": exit_reason,
                        "reason": "strict execution blocked sell at open",
                    }
                )
                continue

            if open_px is None:
                blocked_sell_count += 1
                trades.append(
                    {
                        "trade_date": trade_date,
                        "signal_date": pos.signal_date,
                        "planned_entry_date": pos.planned_entry_date,
                        "planned_exit_date": pos.planned_exit_date,
                        "max_exit_date": pos.max_exit_date,
                        "symbol": symbol,
                        "name": pos.name,
                        "action": "SELL_BLOCKED",
                        "price": None,
                        "shares": pos.shares,
                        "gross_amount": None,
                        "fees": None,
                        "net_amount": None,
                        "cash_after": round(cash, 2),
                        "exit_reason": exit_reason,
                        "reason": "raw_open missing on scheduled exit date",
                    }
                )
                continue

            exec_price = float(open_px)
            if req.realistic_execution:
                exec_price *= 1.0 - (req.slippage_bps / 10000.0)
            sell_shares = _effective_shares(pos, row)
            gross = exec_price * sell_shares
            commission = gross * req.sell_fee_rate
            if req.realistic_execution and gross > 0:
                commission = max(commission, float(req.min_commission))
            stamp_tax = gross * req.stamp_tax_sell
            fees = commission + stamp_tax
            net = gross - fees
            cash += net

            trade_return = net / pos.buy_net_amount - 1.0 if pos.buy_net_amount else 0.0
            realized_by_symbol.setdefault(symbol, []).append(trade_return)
            realized_pnl_by_symbol[symbol] = realized_pnl_by_symbol.get(symbol, 0.0) + (net - pos.buy_net_amount)
            trades.append(
                {
                    "trade_date": trade_date,
                    "signal_date": pos.signal_date,
                    "planned_entry_date": pos.planned_entry_date,
                    "planned_exit_date": pos.planned_exit_date,
                    "max_exit_date": pos.max_exit_date,
                    "symbol": symbol,
                    "name": pos.name,
                    "action": "SELL",
                    "price": round(exec_price, 4),
                    "shares": round(sell_shares, 4),
                    "gross_amount": round(gross, 2),
                    "fees": round(fees, 2),
                    "net_amount": round(net, 2),
                    "cash_after": round(cash, 2),
                    "holding_days": _count_holding_days(date_index, pos.buy_date, trade_date),
                    "trade_return": round(trade_return, 6),
                    "price_pnl": round(exec_price - pos.buy_price, 4),
                    "exit_reason": exit_reason,
                    "exit_signal_date": pos.exit_signal_date,
                    "reason": "sell at scheduled or next available open",
                }
            )
            if exit_reason.startswith("sell_condition"):
                sell_condition_exit_count += 1
            else:
                max_hold_exit_count += 1
            sold_today += 1
            del holdings[symbol]

        due_orders = pending_orders.pop(trade_date, [])
        for order in due_orders:
            row = rows_map.get(order.symbol)
            if row is None:
                blocked_buy_count += 1
                trades.append(
                    {
                        "trade_date": trade_date,
                        "signal_date": order.signal_date,
                        "planned_entry_date": order.planned_entry_date,
                        "planned_exit_date": order.planned_exit_date,
                        "max_exit_date": order.max_exit_date,
                        "symbol": order.symbol,
                        "name": order.name,
                        "action": "BUY_BLOCKED",
                        "price": None,
                        "shares": 0,
                        "gross_amount": None,
                        "fees": None,
                        "net_amount": None,
                        "cash_after": round(cash, 2),
                        "rank": order.rank,
                        "score": round(order.score, 6),
                        "reason": "entry date row missing",
                    }
                )
                continue

            open_px = to_float(row.get("raw_open"))
            can_buy_open = bool(row.get("can_buy_open_t", False))
            if open_px is None:
                can_buy_open = False

            if req.realistic_execution and not can_buy_open:
                blocked_buy_count += 1
                trades.append(
                    {
                        "trade_date": trade_date,
                        "signal_date": order.signal_date,
                        "planned_entry_date": order.planned_entry_date,
                        "planned_exit_date": order.planned_exit_date,
                        "max_exit_date": order.max_exit_date,
                        "symbol": order.symbol,
                        "name": order.name,
                        "action": "BUY_BLOCKED",
                        "price": None,
                        "shares": 0,
                        "gross_amount": None,
                        "fees": None,
                        "net_amount": None,
                        "cash_after": round(cash, 2),
                        "rank": order.rank,
                        "score": round(order.score, 6),
                        "reason": "strict execution blocked buy at open",
                    }
                )
                continue

            if open_px is None:
                blocked_buy_count += 1
                trades.append(
                    {
                        "trade_date": trade_date,
                        "signal_date": order.signal_date,
                        "planned_entry_date": order.planned_entry_date,
                        "planned_exit_date": order.planned_exit_date,
                        "max_exit_date": order.max_exit_date,
                        "symbol": order.symbol,
                        "name": order.name,
                        "action": "BUY_BLOCKED",
                        "price": None,
                        "shares": 0,
                        "gross_amount": None,
                        "fees": None,
                        "net_amount": None,
                        "cash_after": round(cash, 2),
                        "rank": order.rank,
                        "score": round(order.score, 6),
                        "reason": "raw_open missing on planned entry date",
                    }
                )
                continue

            exec_price = float(open_px)
            if req.realistic_execution:
                exec_price *= 1.0 + (req.slippage_bps / 10000.0)
            per_lot_cost = exec_price * req.lot_size
            est_fee_one = per_lot_cost * req.buy_fee_rate
            if req.realistic_execution and per_lot_cost > 0:
                est_fee_one = max(est_fee_one, float(req.min_commission))
            total_one_lot = per_lot_cost + est_fee_one
            budget = min(float(req.per_trade_budget), cash)
            lots = int(budget // total_one_lot) if total_one_lot > 0 else 0
            shares = lots * req.lot_size
            if shares <= 0:
                skipped_buy_cash_count += 1
                trades.append(
                    {
                        "trade_date": trade_date,
                        "signal_date": order.signal_date,
                        "planned_entry_date": order.planned_entry_date,
                        "planned_exit_date": order.planned_exit_date,
                        "max_exit_date": order.max_exit_date,
                        "symbol": order.symbol,
                        "name": order.name,
                        "action": "BUY_SKIPPED_CASH",
                        "price": round(exec_price, 4),
                        "shares": 0,
                        "gross_amount": None,
                        "fees": None,
                        "net_amount": None,
                        "cash_after": round(cash, 2),
                        "rank": order.rank,
                        "score": round(order.score, 6),
                        "reason": "insufficient cash for one lot under per_trade_budget",
                    }
                )
                continue

            gross = exec_price * shares
            fees = gross * req.buy_fee_rate
            if req.realistic_execution and gross > 0:
                fees = max(fees, float(req.min_commission))
            net = gross + fees
            if net > cash:
                skipped_buy_cash_count += 1
                trades.append(
                    {
                        "trade_date": trade_date,
                        "signal_date": order.signal_date,
                        "planned_entry_date": order.planned_entry_date,
                        "planned_exit_date": order.planned_exit_date,
                        "max_exit_date": order.max_exit_date,
                        "symbol": order.symbol,
                        "name": order.name,
                        "action": "BUY_SKIPPED_CASH",
                        "price": round(exec_price, 4),
                        "shares": 0,
                        "gross_amount": None,
                        "fees": None,
                        "net_amount": None,
                        "cash_after": round(cash, 2),
                        "rank": order.rank,
                        "score": round(order.score, 6),
                        "reason": "net cash requirement exceeds available cash",
                    }
                )
                continue

            cash -= net
            holdings[order.symbol] = Position(
                symbol=order.symbol,
                name=order.name,
                shares=int(shares),
                signal_date=order.signal_date,
                planned_entry_date=order.planned_entry_date,
                buy_date=trade_date,
                planned_exit_date=order.planned_exit_date,
                max_exit_date=order.max_exit_date,
                buy_price=float(exec_price),
                buy_net_amount=float(net),
                buy_adj_factor=to_float(row.get("adj_factor")),
                score=float(order.score),
                exit_reason=None,
                exit_signal_date=None,
            )
            trades.append(
                {
                    "trade_date": trade_date,
                    "signal_date": order.signal_date,
                    "planned_entry_date": order.planned_entry_date,
                    "planned_exit_date": order.planned_exit_date,
                    "max_exit_date": order.max_exit_date,
                    "symbol": order.symbol,
                    "name": order.name,
                    "action": "BUY",
                    "price": round(exec_price, 4),
                    "shares": int(shares),
                    "gross_amount": round(gross, 2),
                    "fees": round(fees, 2),
                    "net_amount": round(net, 2),
                    "cash_after": round(cash, 2),
                    "rank": order.rank,
                    "score": round(order.score, 6),
                    "reason": "selected on signal day and executed at next open",
                }
            )
            bought_today += 1

        if trade_date in signal_dates:
            pending_symbols = {order.symbol for orders in pending_orders.values() for order in orders}
            candidates: list[dict[str, Any]] = []
            for item, idx in date_rows:
                if item.symbol in holdings or item.symbol in pending_symbols:
                    continue

                future_entry = _future_row(item, idx, req.entry_offset)
                future_exit = _future_row(item, idx, _effective_max_exit_offset(req))
                if future_entry is None or future_exit is None:
                    continue

                payload = _build_eval_row(item.df, idx, max_offset)
                ok, reason = evaluate_conditions(payload, buy_rules)
                if not ok:
                    continue
                score = evaluate_score_expression(payload, score_tree)
                if math.isnan(score):
                    continue

                signal_row = item.df.iloc[idx]
                entry_date, entry_row = future_entry
                exit_date, exit_row = future_exit
                candidates.append(
                    {
                        "signal_date": trade_date,
                        "symbol": item.symbol,
                        "name": item.name,
                        "score": float(score),
                        "reason": reason,
                        "signal_close": to_float(signal_row.get("close")),
                        "signal_raw_close": to_float(signal_row.get("raw_close")),
                        "planned_entry_date": entry_date,
                        "planned_exit_date": exit_date,
                        "max_exit_date": exit_date,
                        "entry_raw_open": to_float(entry_row.get("raw_open")),
                        "entry_can_buy_open": bool(entry_row.get("can_buy_open_t", False)),
                        "exit_raw_open": to_float(exit_row.get("raw_open")),
                        "exit_can_sell_open": bool(exit_row.get("can_sell_t", False)),
                    }
                )

            candidates.sort(key=lambda x: (-x["score"], x["symbol"]))
            selected = candidates[: req.top_n]
            signal_candidates = len(candidates)
            signal_picks = len(selected)

            for rank, candidate in enumerate(selected, start=1):
                order = PendingOrder(
                    symbol=candidate["symbol"],
                    name=candidate["name"],
                    signal_date=candidate["signal_date"],
                    planned_entry_date=candidate["planned_entry_date"],
                    planned_exit_date=candidate["planned_exit_date"],
                    max_exit_date=candidate["max_exit_date"],
                    score=float(candidate["score"]),
                    rank=rank,
                )
                pending_orders.setdefault(order.planned_entry_date, []).append(order)
                picks.append(
                    {
                        "signal_date": candidate["signal_date"],
                        "symbol": candidate["symbol"],
                        "name": candidate["name"],
                        "rank": rank,
                        "score": round(candidate["score"], 6),
                        "signal_close": round(candidate["signal_close"], 4) if candidate["signal_close"] is not None else None,
                        "signal_raw_close": round(candidate["signal_raw_close"], 4) if candidate["signal_raw_close"] is not None else None,
                        "planned_entry_date": candidate["planned_entry_date"],
                        "planned_exit_date": candidate["planned_exit_date"],
                        "max_exit_date": candidate["max_exit_date"],
                        "entry_raw_open": round(candidate["entry_raw_open"], 4) if candidate["entry_raw_open"] is not None else None,
                        "entry_can_buy_open": candidate["entry_can_buy_open"],
                        "exit_raw_open": round(candidate["exit_raw_open"], 4) if candidate["exit_raw_open"] is not None else None,
                        "exit_can_sell_open": candidate["exit_can_sell_open"],
                        "sell_condition_enabled": bool(sell_rules),
                    }
                )

        if sell_rules:
            for symbol, pos in holdings.items():
                if trade_date < pos.buy_date or trade_date >= pos.planned_exit_date:
                    continue
                item_idx = item_idx_map.get(symbol)
                if item_idx is None:
                    continue
                item, idx = item_idx
                holding_days = _count_holding_days(date_index, pos.buy_date, trade_date)
                if holding_days < req.min_hold_days:
                    continue
                next_trade = _next_trade_row(item, idx)
                if next_trade is None:
                    continue
                next_trade_date, _ = next_trade
                payload = _build_eval_row(item.df, idx, max_offset)
                ok, _ = evaluate_conditions(payload, sell_rules)
                if not ok:
                    continue
                if next_trade_date > pos.planned_exit_date:
                    continue
                pos.planned_exit_date = next_trade_date
                pos.exit_reason = f"sell_condition:{req.sell_condition}"
                pos.exit_signal_date = trade_date

        market_value = 0.0
        for symbol, pos in holdings.items():
            row = rows_map.get(symbol)
            if row is None:
                market_value += pos.buy_price * pos.shares
                continue
            last_close = to_float(row.get("raw_close"))
            if last_close is not None:
                last_close_by_symbol[symbol] = last_close
            market_value += _mark_to_market_close(pos, row, last_close_by_symbol.get(symbol))

        equity = cash + market_value
        equity_curve.append(equity)
        running_max = max(equity_curve)
        drawdown = equity / running_max - 1.0 if running_max > 0 else 0.0
        daily_rows.append(
            {
                "trade_date": trade_date,
                "cash": round(cash, 2),
                "market_value": round(market_value, 2),
                "equity": round(equity, 2),
                "position_count": len(holdings),
                "pending_order_count": sum(len(orders) for orders in pending_orders.values()),
                "candidate_count": signal_candidates,
                "picked_count": signal_picks,
                "buy_count": bought_today,
                "sell_count": sold_today,
                "drawdown": round(drawdown, 6),
            }
        )

    ending_equity = daily_rows[-1]["equity"] if daily_rows else req.initial_cash
    returns: list[float] = []
    for idx in range(1, len(equity_curve)):
        prev = equity_curve[idx - 1]
        curr = equity_curve[idx]
        if prev > 0:
            returns.append(curr / prev - 1.0)

    max_drawdown = 0.0
    peak = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        if peak > 0:
            max_drawdown = min(max_drawdown, value / peak - 1.0)

    sell_trade_returns = [
        float(row["trade_return"])
        for row in trades
        if row["action"] == "SELL" and row.get("trade_return") is not None
    ]
    win_rate = (
        sum(1 for item in sell_trade_returns if item > 0) / len(sell_trade_returns)
        if sell_trade_returns
        else 0.0
    )

    contribution_rows = []
    for symbol, pnl in sorted(realized_pnl_by_symbol.items(), key=lambda item: item[1], reverse=True):
        returns_for_symbol = realized_by_symbol.get(symbol, [])
        contribution_rows.append(
            {
                "symbol": symbol,
                "realized_pnl": round(pnl, 2),
                "trade_count": len(returns_for_symbol),
                "win_rate": round(sum(1 for item in returns_for_symbol if item > 0) / len(returns_for_symbol), 4)
                if returns_for_symbol
                else 0.0,
                "avg_trade_return": round(sum(returns_for_symbol) / len(returns_for_symbol), 6)
                if returns_for_symbol
                else 0.0,
            }
        )

    summary = {
        "start_date": signal_dates[0],
        "end_date": signal_dates[-1],
        "simulation_end_date": daily_rows[-1]["trade_date"] if daily_rows else signal_dates[-1],
        "trade_days": len(daily_rows),
        "entry_offset": req.entry_offset,
        "exit_offset": req.exit_offset,
        "min_hold_days": req.min_hold_days,
        "max_hold_days": req.max_hold_days,
        "sell_condition": req.sell_condition,
        "initial_cash": round(req.initial_cash, 2),
        "per_trade_budget": round(req.per_trade_budget, 2),
        "ending_cash": round(cash, 2),
        "ending_equity": round(ending_equity, 2),
        "total_return": round(ending_equity / req.initial_cash - 1.0, 6),
        "annualized_return": round(_annualized_return(req.initial_cash, ending_equity, len(daily_rows)), 6),
        "max_drawdown": round(abs(max_drawdown), 6),
        "buy_count": sum(1 for row in trades if row["action"] == "BUY"),
        "sell_count": sum(1 for row in trades if row["action"] == "SELL"),
        "blocked_buy_count": blocked_buy_count,
        "blocked_sell_count": blocked_sell_count,
        "skipped_buy_cash_count": skipped_buy_cash_count,
        "sell_condition_exit_count": sell_condition_exit_count,
        "max_hold_exit_count": max_hold_exit_count,
        "win_rate": round(win_rate, 6),
        "avg_trade_return": round(sum(sell_trade_returns) / len(sell_trade_returns), 6) if sell_trade_returns else 0.0,
        "best_trade_return": round(max(sell_trade_returns), 6) if sell_trade_returns else 0.0,
        "worst_trade_return": round(min(sell_trade_returns), 6) if sell_trade_returns else 0.0,
    }
    diagnostics.update(
        {
            "signal_days": len(signal_dates),
            "candidate_days": sum(1 for row in daily_rows if row["candidate_count"] > 0),
            "picked_days": sum(1 for row in daily_rows if row["picked_count"] > 0),
        }
    )
    return {
        "summary": summary,
        "daily_rows": daily_rows,
        "pick_rows": picks,
        "trade_rows": trades,
        "contribution_rows": contribution_rows,
        "diagnostics": diagnostics,
    }


def run_portfolio_backtest(req: BacktestRequest) -> dict[str, Any]:
    loaded, diagnostics = load_processed_folder(req.processed_dir)
    return run_portfolio_backtest_loaded(loaded, diagnostics, req)


def export_backtest_zip(result: dict[str, Any]) -> bytes:
    buffers = {
        "summary.csv": pd.DataFrame([result["summary"]]),
        "daily_equity.csv": pd.DataFrame(result["daily_rows"]),
        "daily_picks.csv": pd.DataFrame(result["pick_rows"]),
        "trades.csv": pd.DataFrame(result["trade_rows"]),
        "contributions.csv": pd.DataFrame(result["contribution_rows"]),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, frame in buffers.items():
            zf.writestr(name, frame.to_csv(index=False, encoding="utf-8-sig"))
    return output.getvalue()
