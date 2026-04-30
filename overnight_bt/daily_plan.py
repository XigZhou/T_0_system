from __future__ import annotations

import math
from typing import Any

from .backtest import (
    LoadedSymbol,
    _build_eval_row,
    _compute_position_runtime_metrics,
    _count_holding_days,
    _future_row,
    _score_required_offset,
    load_processed_folder,
)
from .expressions import (
    compile_score_expression,
    evaluate_conditions,
    evaluate_score_expression,
    max_required_offset,
    parse_condition_expr,
)
from .models import DailyPlanRequest, Position
from .utils import to_float


def _symbol_key(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text


def _build_symbol_map(loaded: list[LoadedSymbol]) -> dict[str, LoadedSymbol]:
    out: dict[str, LoadedSymbol] = {}
    for item in loaded:
        out[item.symbol] = item
        out[_symbol_key(item.symbol)] = item
    return out


def _resolve_signal_date(all_dates: list[str], requested: str) -> tuple[str, str]:
    if not all_dates:
        raise ValueError("no trade dates available")
    requested = str(requested or "").strip()
    if not requested:
        return all_dates[-1], "使用数据中的最新交易日"
    candidates = [date for date in all_dates if date <= requested]
    if not candidates:
        raise ValueError("no trade date on or before requested signal_date")
    signal_date = candidates[-1]
    note = "使用输入交易日" if signal_date == requested else f"输入日期非交易日，使用前一交易日 {signal_date}"
    return signal_date, note


def _next_trade_date(item: LoadedSymbol, idx: int) -> str:
    next_row = _future_row(item, idx, 1)
    return next_row[0] if next_row is not None else "下一交易日"


def _estimate_shares(raw_close: float | None, per_trade_budget: float, lot_size: int) -> int:
    if raw_close is None or raw_close <= 0:
        return 0
    lots = int(float(per_trade_budget) // (float(raw_close) * int(lot_size)))
    return max(0, lots * int(lot_size))


def build_daily_plan(req: DailyPlanRequest) -> dict[str, Any]:
    loaded, diagnostics = load_processed_folder(req.processed_dir)
    all_dates = sorted({date for item in loaded for date in item.df["trade_date"].astype(str).tolist()})
    signal_date, date_note = _resolve_signal_date(all_dates, req.signal_date)
    symbol_map = _build_symbol_map(loaded)
    holding_symbols = {_symbol_key(item.symbol) for item in req.holdings}

    rows_by_date: list[tuple[LoadedSymbol, int]] = []
    for item in loaded:
        idx = item.idx_by_date.get(signal_date)
        if idx is not None:
            rows_by_date.append((item, idx))

    buy_rules = parse_condition_expr(req.buy_condition)
    sell_rules = parse_condition_expr(req.sell_condition) if str(req.sell_condition or "").strip() else []
    score_tree, _ = compile_score_expression(req.score_expression)
    max_offset = max(
        max_required_offset(buy_rules),
        max_required_offset(sell_rules),
        _score_required_offset(req.score_expression),
    )

    buy_rows: list[dict] = []
    for item, idx in rows_by_date:
        if _symbol_key(item.symbol) in holding_symbols:
            continue
        payload = _build_eval_row(item.df, idx, max_offset)
        ok, reason = evaluate_conditions(payload, buy_rules)
        if not ok:
            continue
        score = evaluate_score_expression(payload, score_tree)
        if math.isnan(score):
            continue
        row = item.df.iloc[idx]
        raw_close = to_float(row.get("raw_close"))
        buy_rows.append(
            {
                "signal_date": signal_date,
                "planned_buy_date": _next_trade_date(item, idx),
                "symbol": item.symbol,
                "name": item.name,
                "rank": 0,
                "score": round(float(score), 6),
                "signal_raw_close": round(raw_close, 4) if raw_close is not None else None,
                "estimated_shares": _estimate_shares(raw_close, req.per_trade_budget, req.lot_size),
                "estimated_budget": round(float(req.per_trade_budget), 2),
                "reason": reason,
                "open_check": "明日开盘若涨停、跌停、停牌或流动性不足，则不买入",
            }
        )
    buy_rows.sort(key=lambda item: (-float(item["score"]), str(item["symbol"])))
    buy_rows = buy_rows[: req.top_n]
    for rank, row in enumerate(buy_rows, start=1):
        row["rank"] = rank

    date_index = {date: idx for idx, date in enumerate(all_dates)}
    holding_rows: list[dict] = []
    sell_rows: list[dict] = []
    for holding in req.holdings:
        symbol_key = _symbol_key(holding.symbol)
        item = symbol_map.get(symbol_key) or symbol_map.get(str(holding.symbol).strip())
        if item is None:
            holding_rows.append(
                {
                    "signal_date": signal_date,
                    "symbol": holding.symbol,
                    "name": holding.name,
                    "status": "未找到股票数据",
                }
            )
            continue
        current_idx = item.idx_by_date.get(signal_date)
        buy_idx = item.idx_by_date.get(str(holding.buy_date).strip())
        if current_idx is None or buy_idx is None:
            holding_rows.append(
                {
                    "signal_date": signal_date,
                    "symbol": item.symbol,
                    "name": holding.name or item.name,
                    "status": "缺少买入日或信号日行情",
                }
            )
            continue

        current_row = item.df.iloc[current_idx]
        buy_row = item.df.iloc[buy_idx]
        position = Position(
            symbol=item.symbol,
            name=holding.name or item.name,
            shares=int(holding.shares),
            signal_date=str(holding.buy_date).strip(),
            planned_entry_date=str(holding.buy_date).strip(),
            buy_date=str(holding.buy_date).strip(),
            planned_exit_date="99991231",
            max_exit_date="99991231",
            buy_price=float(holding.buy_price),
            buy_net_amount=float(holding.buy_price) * int(holding.shares),
            buy_adj_factor=to_float(buy_row.get("adj_factor")),
        )
        metrics = _compute_position_runtime_metrics(item, position, current_idx, current_row, date_index)
        holding_days = _count_holding_days(date_index, position.buy_date, signal_date)
        payload = _build_eval_row(item.df, current_idx, max_offset)
        payload.update(metrics)

        condition_hit = False
        condition_note = "未设置卖出条件"
        if sell_rules and holding_days >= req.min_hold_days:
            condition_hit, condition_note = evaluate_conditions(payload, sell_rules)
        elif sell_rules:
            condition_note = f"持有 {holding_days} 天，未达到最短持有 {req.min_hold_days} 天"

        max_hold_hit = req.max_hold_days > 0 and holding_days >= req.max_hold_days
        should_sell = condition_hit or max_hold_hit
        sell_reason = "卖出条件触发" if condition_hit else ("达到最大持有天数" if max_hold_hit else "继续观察")
        raw_close = to_float(current_row.get("raw_close"))
        base_row = {
            "signal_date": signal_date,
            "planned_sell_date": _next_trade_date(item, current_idx),
            "symbol": item.symbol,
            "name": holding.name or item.name,
            "shares": int(holding.shares),
            "buy_date": position.buy_date,
            "buy_price": round(float(holding.buy_price), 4),
            "current_raw_close": round(raw_close, 4) if raw_close is not None else None,
            "holding_days": holding_days,
            "holding_return": round(metrics["holding_return"], 6),
            "best_return_since_entry": round(metrics["best_return_since_entry"], 6),
            "drawdown_from_peak": round(metrics["drawdown_from_peak"], 6),
            "sell_reason": sell_reason,
            "condition_note": condition_note,
            "open_check": "明日开盘若跌停、停牌或无法成交，则顺延或人工处理",
        }
        holding_rows.append(base_row)
        if should_sell:
            sell_rows.append(base_row)

    return {
        "summary": {
            "signal_date": signal_date,
            "date_note": date_note,
            "planned_buy_date": buy_rows[0]["planned_buy_date"] if buy_rows else "下一交易日",
            "buy_candidate_count": len(buy_rows),
            "sell_signal_count": len(sell_rows),
            "holding_count": len(req.holdings),
            "top_n": req.top_n,
        },
        "buy_rows": buy_rows,
        "sell_rows": sell_rows,
        "holding_rows": holding_rows,
        "diagnostics": {
            **diagnostics,
            "signal_date": signal_date,
            "date_note": date_note,
            "available_stock_count": len(rows_by_date),
        },
    }
