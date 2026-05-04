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
from .rotation_features import ROTATION_NUMERIC_COLUMNS
from .sector_features import SECTOR_NUMERIC_COLUMNS, resolve_data_profile, sector_display_values, validate_sector_feature_set
from .utils import to_float


@dataclass
class LoadedSymbol:
    symbol: str
    name: str
    df: pd.DataFrame
    idx_by_date: dict[str, int]


_SCORE_OFFSET_RE = re.compile(r"\[(\d+)\]")
_CUTOFF_EXIT_DATE = "99991231"
_CUTOFF_EXIT_LABEL = "截止日后估值"
PROCESSED_METADATA_CSV_NAMES = {
    "processing_manifest.csv",
    "sector_feature_manifest.csv",
    "rotation_feature_manifest.csv",
}


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
        if p.is_file()
        and p.suffix.lower() == ".csv"
        and p.name not in PROCESSED_METADATA_CSV_NAMES
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
                or col in SECTOR_NUMERIC_COLUMNS
                or col in ROTATION_NUMERIC_COLUMNS
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


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _profit_factor(returns: list[float]) -> float:
    gains = sum(item for item in returns if item > 0)
    losses = abs(sum(item for item in returns if item < 0))
    if gains <= 0 or losses <= 0:
        return 0.0
    return gains / losses


def _max_drawdown_from_equity(values: list[float]) -> float:
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        if value > peak:
            peak = value
        if peak > 0:
            max_drawdown = min(max_drawdown, value / peak - 1.0)
    return abs(max_drawdown)


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _fmt_num(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def _fmt_count(value: int) -> str:
    return f"{value}"


def _period_key(trade_date: str, period: str) -> str:
    date_text = str(trade_date)
    if period == "year":
        return date_text[:4]
    return f"{date_text[:4]}-{date_text[4:6]}"


def _build_period_rows(daily_rows: list[dict], trades: list[dict], period: str) -> list[dict]:
    grouped_daily: dict[str, list[dict]] = {}
    for row in daily_rows:
        grouped_daily.setdefault(_period_key(str(row["trade_date"]), period), []).append(row)

    grouped_trades: dict[str, list[dict]] = {}
    for trade in trades:
        trade_date = trade.get("trade_date")
        if not trade_date:
            continue
        grouped_trades.setdefault(_period_key(str(trade_date), period), []).append(trade)

    rows: list[dict] = []
    for key in sorted(grouped_daily):
        period_daily = grouped_daily[key]
        equities = [float(row["equity"]) for row in period_daily if row.get("equity") is not None]
        if not equities:
            continue
        start_equity = equities[0]
        end_equity = equities[-1]
        trades_in_period = grouped_trades.get(key, [])
        sell_returns = [
            float(row["trade_return"])
            for row in trades_in_period
            if row.get("action") == "SELL" and row.get("trade_return") is not None
        ]
        rows.append(
            {
                "period": key,
                "period_return": round(end_equity / start_equity - 1.0, 6) if start_equity > 0 else 0.0,
                "max_drawdown": round(_max_drawdown_from_equity(equities), 6),
                "ending_equity": round(end_equity, 2),
                "picked_days": sum(1 for row in period_daily if int(row.get("picked_count", 0)) > 0),
                "buy_count": sum(1 for row in trades_in_period if row.get("action") == "BUY"),
                "sell_count": len(sell_returns),
                "win_rate": round(sum(1 for item in sell_returns if item > 0) / len(sell_returns), 6)
                if sell_returns
                else 0.0,
                "avg_trade_return": round(_average(sell_returns), 6) if sell_returns else 0.0,
            }
        )
    return rows


def _build_exit_reason_rows(trades: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for trade in trades:
        if trade.get("action") != "SELL":
            continue
        reason = str(trade.get("exit_reason") or "unknown")
        label = "卖出条件触发" if reason.startswith("sell_condition") else "固定或最大持有退出"
        groups.setdefault(label, []).append(trade)

    rows: list[dict] = []
    for label, group in sorted(groups.items()):
        returns = [
            float(row["trade_return"])
            for row in group
            if row.get("trade_return") is not None
        ]
        holding_days = [
            float(row["holding_days"])
            for row in group
            if row.get("holding_days") is not None
        ]
        rows.append(
            {
                "exit_type": label,
                "trade_count": len(group),
                "win_rate": round(sum(1 for item in returns if item > 0) / len(returns), 6) if returns else 0.0,
                "avg_trade_return": round(_average(returns), 6) if returns else 0.0,
                "median_trade_return": round(_median(returns), 6) if returns else 0.0,
                "avg_holding_days": round(_average(holding_days), 2) if holding_days else 0.0,
            }
        )
    return rows


def _build_condition_rows(
    *,
    req: BacktestRequest,
    diagnostics: dict,
    daily_rows: list[dict],
    trades: list[dict],
    sell_trade_returns: list[float],
    year_rows: list[dict],
) -> list[dict]:
    signal_days = int(diagnostics.get("signal_days", 0))
    candidate_days = int(diagnostics.get("candidate_days", 0))
    total_candidates = sum(int(row.get("candidate_count", 0)) for row in daily_rows)
    total_picks = sum(int(row.get("picked_count", 0)) for row in daily_rows)
    max_possible_picks = signal_days * int(req.top_n)
    topn_fill_rate = total_picks / max_possible_picks if max_possible_picks > 0 else 0.0
    avg_candidates = total_candidates / signal_days if signal_days > 0 else 0.0

    blocked_buy_count = sum(1 for row in trades if row.get("action") == "BUY_BLOCKED")
    blocked_sell_count = sum(1 for row in trades if row.get("action") == "SELL_BLOCKED")
    skipped_cash_count = sum(1 for row in trades if row.get("action") == "BUY_SKIPPED_CASH")
    total_fees = sum(float(row.get("fees") or 0.0) for row in trades if row.get("action") in {"BUY", "SELL"})
    holding_days = [
        float(row["holding_days"])
        for row in trades
        if row.get("action") == "SELL" and row.get("holding_days") is not None
    ]

    profitable_years = sum(1 for row in year_rows if float(row.get("period_return", 0.0)) > 0)
    year_count = len(year_rows)
    best_year = max((float(row.get("period_return", 0.0)) for row in year_rows), default=0.0)
    worst_year = min((float(row.get("period_return", 0.0)) for row in year_rows), default=0.0)

    return [
        {
            "category": "信号覆盖",
            "metric": "有候选日占比",
            "value": _fmt_pct(candidate_days / signal_days if signal_days else 0.0),
            "reading": "越高说明条件不至于过窄；太低时样本少，结果容易偶然。",
        },
        {
            "category": "信号覆盖",
            "metric": "选股数量填满率",
            "value": _fmt_pct(topn_fill_rate),
            "reading": "低于100%说明很多信号日没有足够股票可买，选股数量可能偏大或条件偏严。",
        },
        {
            "category": "信号覆盖",
            "metric": "平均候选数/信号日",
            "value": _fmt_num(avg_candidates, 2),
            "reading": "用于判断每天可选择空间；太低时评分表达式很难发挥作用。",
        },
        {
            "category": "交易质量",
            "metric": "胜率",
            "value": _fmt_pct(sum(1 for item in sell_trade_returns if item > 0) / len(sell_trade_returns)) if sell_trade_returns else "0.00%",
            "reading": "胜率要和平均收益一起看；高胜率但单次亏损很大也不稳。",
        },
        {
            "category": "交易质量",
            "metric": "平均/中位单笔收益",
            "value": f"{_fmt_pct(_average(sell_trade_returns))} / {_fmt_pct(_median(sell_trade_returns))}",
            "reading": "中位数更能反映普通交易，均值明显更高时可能依赖少数大赚交易。",
        },
        {
            "category": "交易质量",
            "metric": "收益因子",
            "value": _fmt_num(_profit_factor(sell_trade_returns), 2),
            "reading": "大于1说明盈利交易合计幅度超过亏损交易，越高越好。",
        },
        {
            "category": "执行摩擦",
            "metric": "买入阻塞/资金跳过",
            "value": f"{_fmt_count(blocked_buy_count)} / {_fmt_count(skipped_cash_count)}",
            "reading": "阻塞多说明信号落到涨跌停或停牌环境，资金跳过多说明预算或股价不匹配。",
        },
        {
            "category": "执行摩擦",
            "metric": "卖出阻塞",
            "value": _fmt_count(blocked_sell_count),
            "reading": "卖出阻塞越多，真实成交风险越高，资金曲线可能低估流动性压力。",
        },
        {
            "category": "执行摩擦",
            "metric": "手续费滑点成本",
            "value": f"{_fmt_num(total_fees, 2)} / {_fmt_pct(total_fees / req.initial_cash if req.initial_cash else 0.0)}",
            "reading": "前者是累计成本，后者是相对初始资金占比；短线策略要特别盯这个数。",
        },
        {
            "category": "持仓退出",
            "metric": "平均持有天数",
            "value": _fmt_num(_average(holding_days), 2),
            "reading": "用于确认条件是否符合预期持仓节奏，过短会放大交易成本影响。",
        },
        {
            "category": "时间稳定性",
            "metric": "盈利年份",
            "value": f"{profitable_years}/{year_count}",
            "reading": "比单一总收益更重要；只有一两个年份赚钱时要小心过拟合。",
        },
        {
            "category": "时间稳定性",
            "metric": "最好/最差年份",
            "value": f"{_fmt_pct(best_year)} / {_fmt_pct(worst_year)}",
            "reading": "观察收益是否集中在某一年，以及最差年份能否接受。",
        },
    ]


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


def _display_exit_date(value: str) -> str:
    return _CUTOFF_EXIT_LABEL if value == _CUTOFF_EXIT_DATE else value


def _next_trade_row(item: LoadedSymbol, idx: int) -> tuple[str, pd.Series] | None:
    return _future_row(item, idx, 1)


def _compute_position_runtime_metrics(
    item: LoadedSymbol,
    pos: Position,
    current_idx: int,
    current_row: pd.Series,
    date_index: dict[str, int],
) -> dict[str, float]:
    buy_idx = item.idx_by_date.get(pos.buy_date)
    if buy_idx is None:
        return {
            "days_held": 0.0,
            "holding_return": 0.0,
            "best_return_since_entry": 0.0,
            "drawdown_from_peak": 0.0,
        }

    current_value = _mark_to_market_close(pos, current_row, pos.buy_price)
    initial_value = max(float(pos.buy_price) * float(pos.shares), 1e-12)
    holding_return = current_value / initial_value - 1.0

    peak_value = current_value
    for hist_idx in range(buy_idx, current_idx + 1):
        hist_row = item.df.iloc[hist_idx]
        hist_value = _mark_to_market_close(pos, hist_row, pos.buy_price)
        if hist_value > peak_value:
            peak_value = hist_value
    best_return_since_entry = peak_value / initial_value - 1.0

    if peak_value <= 0:
        drawdown_from_peak = 0.0
    else:
        drawdown_from_peak = max(0.0, 1.0 - current_value / peak_value)

    days_held = float(_count_holding_days(date_index, pos.buy_date, str(current_row["trade_date"]).strip()))
    return {
        "days_held": days_held,
        "holding_return": float(holding_return),
        "best_return_since_entry": float(best_return_since_entry),
        "drawdown_from_peak": float(drawdown_from_peak),
    }


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
    cutoff_mode = req.settlement_mode == "cutoff"
    cutoff_date = signal_dates[-1]

    date_index = {date: idx for idx, date in enumerate(all_dates)}
    rows_by_date: dict[str, list[tuple[LoadedSymbol, int]]] = {}
    for item in loaded:
        for date, idx in item.idx_by_date.items():
            rows_by_date.setdefault(date, []).append((item, idx))
    symbol_names = {item.symbol: item.name for item in loaded}
    loaded_by_symbol = {item.symbol: item for item in loaded}

    cash = float(req.initial_cash)
    holdings: dict[str, Position] = {}
    pending_orders: dict[str, list[PendingOrder]] = {}
    trades: list[dict] = []
    picks: list[dict] = []
    daily_rows: list[dict] = []
    open_position_rows: list[dict] = []
    pending_sell_rows: list[dict] = []
    realized_by_symbol: dict[str, list[float]] = {}
    realized_pnl_by_symbol: dict[str, float] = {}
    last_close_by_symbol: dict[str, float] = {}
    equity_curve: list[float] = []
    blocked_buy_count = 0
    blocked_sell_count = 0
    skipped_buy_cash_count = 0
    skipped_cutoff_buy_count = 0
    sell_condition_exit_count = 0
    max_hold_exit_count = 0

    simulation_start = signal_dates[0]

    for trade_date in all_dates:
        if trade_date < simulation_start:
            continue
        if cutoff_mode and trade_date > cutoff_date:
            break
        if not cutoff_mode and req.end_date and trade_date > req.end_date and not holdings and not pending_orders:
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
                        "planned_exit_date": _display_exit_date(pos.planned_exit_date),
                        "max_exit_date": _display_exit_date(pos.max_exit_date),
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
                        "planned_exit_date": _display_exit_date(pos.planned_exit_date),
                        "max_exit_date": _display_exit_date(pos.max_exit_date),
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
                    "planned_exit_date": _display_exit_date(pos.planned_exit_date),
                    "max_exit_date": _display_exit_date(pos.max_exit_date),
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
        if cutoff_mode and trade_date >= cutoff_date and due_orders:
            for order in due_orders:
                skipped_cutoff_buy_count += 1
                trades.append(
                    {
                        "trade_date": trade_date,
                        "signal_date": order.signal_date,
                        "planned_entry_date": order.planned_entry_date,
                        "planned_exit_date": _display_exit_date(order.planned_exit_date),
                        "max_exit_date": _display_exit_date(order.max_exit_date),
                        "symbol": order.symbol,
                        "name": order.name,
                        "action": "BUY_SKIPPED_CUTOFF",
                        "price": None,
                        "shares": 0,
                        "gross_amount": None,
                        "fees": None,
                        "net_amount": None,
                        "cash_after": round(cash, 2),
                        "rank": order.rank,
                        "score": round(order.score, 6),
                        "reason": "cutoff date only marks existing positions; no new buy is executed",
                    }
                )
            due_orders = []
        for order in due_orders:
            row = rows_map.get(order.symbol)
            if row is None:
                blocked_buy_count += 1
                trades.append(
                    {
                        "trade_date": trade_date,
                        "signal_date": order.signal_date,
                        "planned_entry_date": order.planned_entry_date,
                        "planned_exit_date": _display_exit_date(order.planned_exit_date),
                        "max_exit_date": _display_exit_date(order.max_exit_date),
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
                        "planned_exit_date": _display_exit_date(order.planned_exit_date),
                        "max_exit_date": _display_exit_date(order.max_exit_date),
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
                        "planned_exit_date": _display_exit_date(order.planned_exit_date),
                        "max_exit_date": _display_exit_date(order.max_exit_date),
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
                        "planned_exit_date": _display_exit_date(order.planned_exit_date),
                        "max_exit_date": _display_exit_date(order.max_exit_date),
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
                        "planned_exit_date": _display_exit_date(order.planned_exit_date),
                        "max_exit_date": _display_exit_date(order.max_exit_date),
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
                    "planned_exit_date": _display_exit_date(order.planned_exit_date),
                    "max_exit_date": _display_exit_date(order.max_exit_date),
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
            is_cutoff_signal = cutoff_mode and trade_date == cutoff_date
            pending_symbols = {order.symbol for orders in pending_orders.values() for order in orders}
            candidates: list[dict[str, Any]] = []
            for item, idx in date_rows:
                if item.symbol in holdings or item.symbol in pending_symbols:
                    continue

                if is_cutoff_signal:
                    entry_date = "下一交易日"
                    entry_row = None
                else:
                    future_entry = _future_row(item, idx, req.entry_offset)
                    if future_entry is None:
                        continue
                    entry_date, entry_row = future_entry
                    if cutoff_mode and entry_date >= cutoff_date:
                        continue

                exit_date = _CUTOFF_EXIT_DATE
                exit_row = None
                if not is_cutoff_signal:
                    future_exit = _future_row(item, idx, _effective_max_exit_offset(req))
                    if future_exit is not None:
                        candidate_exit_date, candidate_exit_row = future_exit
                        if not cutoff_mode or candidate_exit_date <= cutoff_date:
                            exit_date = candidate_exit_date
                            exit_row = candidate_exit_row
                    elif not cutoff_mode:
                        continue

                payload = _build_eval_row(item.df, idx, max_offset)
                ok, reason = evaluate_conditions(payload, buy_rules)
                if not ok:
                    continue
                score = evaluate_score_expression(payload, score_tree)
                if math.isnan(score):
                    continue

                signal_row = item.df.iloc[idx]
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
                        "entry_raw_open": to_float(entry_row.get("raw_open")) if entry_row is not None else None,
                        "entry_can_buy_open": bool(entry_row.get("can_buy_open_t", False)) if entry_row is not None else False,
                        "exit_raw_open": to_float(exit_row.get("raw_open")) if exit_row is not None else None,
                        "exit_can_sell_open": bool(exit_row.get("can_sell_t", False)) if exit_row is not None else False,
                        "execution_note": "截止日预测，不在本次回测内成交" if is_cutoff_signal else "信号日入选，按计划买入日成交",
                        **sector_display_values(signal_row),
                    }
                )

            candidates.sort(key=lambda x: (-x["score"], x["symbol"]))
            selected = candidates[: req.top_n]
            signal_candidates = len(candidates)
            signal_picks = len(selected)

            for rank, candidate in enumerate(selected, start=1):
                if not is_cutoff_signal:
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
                        "planned_exit_date": _display_exit_date(candidate["planned_exit_date"]),
                        "max_exit_date": _display_exit_date(candidate["max_exit_date"]),
                        "entry_raw_open": round(candidate["entry_raw_open"], 4) if candidate["entry_raw_open"] is not None else None,
                        "entry_can_buy_open": candidate["entry_can_buy_open"],
                        "exit_raw_open": round(candidate["exit_raw_open"], 4) if candidate["exit_raw_open"] is not None else None,
                        "exit_can_sell_open": candidate["exit_can_sell_open"],
                        "sell_condition_enabled": bool(sell_rules),
                        "execution_note": candidate["execution_note"],
                        **sector_display_values(candidate),
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
                current_row = item.df.iloc[idx]
                payload = _build_eval_row(item.df, idx, max_offset)
                runtime_metrics = _compute_position_runtime_metrics(
                    item=item,
                    pos=pos,
                    current_idx=idx,
                    current_row=current_row,
                    date_index=date_index,
                )
                payload.update(runtime_metrics)
                ok, _ = evaluate_conditions(payload, sell_rules)
                if not ok:
                    continue

                next_trade = _next_trade_row(item, idx)
                next_trade_date = next_trade[0] if next_trade is not None else ""
                if cutoff_mode and (not next_trade_date or next_trade_date > cutoff_date):
                    pending_sell_rows.append(
                        {
                            "signal_date": trade_date,
                            "planned_sell_date": next_trade_date or "下一交易日",
                            "symbol": symbol,
                            "name": pos.name,
                            "shares": pos.shares,
                            "buy_date": pos.buy_date,
                            "buy_price": round(pos.buy_price, 4),
                            "current_raw_close": round(to_float(current_row.get("raw_close")) or pos.buy_price, 4),
                            "holding_days": holding_days,
                            "holding_return": round(runtime_metrics["holding_return"], 6),
                            "best_return_since_entry": round(runtime_metrics["best_return_since_entry"], 6),
                            "drawdown_from_peak": round(runtime_metrics["drawdown_from_peak"], 6),
                            "sell_condition": req.sell_condition,
                            "reason": "截止日触发卖出条件，未使用结束日之后价格成交",
                        }
                    )
                    continue
                if next_trade is None:
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
    median_trade_return = _median(sell_trade_returns)
    profit_factor = _profit_factor(sell_trade_returns)
    holding_days = [
        float(row["holding_days"])
        for row in trades
        if row.get("action") == "SELL" and row.get("holding_days") is not None
    ]
    total_fees = sum(float(row.get("fees") or 0.0) for row in trades if row.get("action") in {"BUY", "SELL"})
    valuation_date = daily_rows[-1]["trade_date"] if daily_rows else cutoff_date
    ending_market_value = daily_rows[-1]["market_value"] if daily_rows else 0.0

    for symbol, pos in sorted(holdings.items()):
        item = loaded_by_symbol.get(symbol)
        row = None
        current_idx = None
        if item is not None:
            current_idx = item.idx_by_date.get(str(valuation_date))
            if current_idx is not None:
                row = item.df.iloc[current_idx]
        market_value = _mark_to_market_close(pos, row, pos.buy_price) if row is not None else pos.buy_price * pos.shares
        current_close = to_float(row.get("raw_close")) if row is not None else pos.buy_price
        runtime_metrics = (
            _compute_position_runtime_metrics(item, pos, current_idx, row, date_index)
            if item is not None and current_idx is not None and row is not None
            else {
                "days_held": 0.0,
                "holding_return": 0.0,
                "best_return_since_entry": 0.0,
                "drawdown_from_peak": 0.0,
            }
        )
        unrealized_pnl = market_value - float(pos.buy_net_amount)
        open_position_rows.append(
            {
                "valuation_date": valuation_date,
                "symbol": symbol,
                "name": pos.name,
                "shares": pos.shares,
                "buy_date": pos.buy_date,
                "buy_price": round(pos.buy_price, 4),
                "current_raw_close": round(current_close or pos.buy_price, 4),
                "market_value": round(market_value, 2),
                "buy_net_amount": round(pos.buy_net_amount, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_return": round(unrealized_pnl / pos.buy_net_amount, 6) if pos.buy_net_amount else 0.0,
                "holding_days": int(runtime_metrics["days_held"]),
                "best_return_since_entry": round(runtime_metrics["best_return_since_entry"], 6),
                "drawdown_from_peak": round(runtime_metrics["drawdown_from_peak"], 6),
                "planned_exit_date": _display_exit_date(pos.planned_exit_date),
                "exit_signal_date": pos.exit_signal_date,
            }
        )

    contribution_rows = []
    for symbol, pnl in sorted(realized_pnl_by_symbol.items(), key=lambda item: item[1], reverse=True):
        returns_for_symbol = realized_by_symbol.get(symbol, [])
        contribution_rows.append(
            {
                "symbol": symbol,
                "name": symbol_names.get(symbol, ""),
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

    diagnostics.update(
        {
            "signal_days": len(signal_dates),
            "candidate_days": sum(1 for row in daily_rows if row["candidate_count"] > 0),
            "picked_days": sum(1 for row in daily_rows if row["picked_count"] > 0),
        }
    )
    year_rows = _build_period_rows(daily_rows, trades, "year")
    month_rows = _build_period_rows(daily_rows, trades, "month")
    exit_reason_rows = _build_exit_reason_rows(trades)
    condition_rows = _build_condition_rows(
        req=req,
        diagnostics=diagnostics,
        daily_rows=daily_rows,
        trades=trades,
        sell_trade_returns=sell_trade_returns,
        year_rows=year_rows,
    )

    summary = {
        "start_date": signal_dates[0],
        "end_date": signal_dates[-1],
        "simulation_end_date": daily_rows[-1]["trade_date"] if daily_rows else signal_dates[-1],
        "settlement_mode": "截止日估值" if cutoff_mode else "完整结算",
        "data_profile": diagnostics.get("data_profile", "base"),
        "valuation_date": valuation_date,
        "trade_days": len(daily_rows),
        "entry_offset": req.entry_offset,
        "exit_offset": req.exit_offset,
        "min_hold_days": req.min_hold_days,
        "max_hold_days": req.max_hold_days,
        "sell_condition": req.sell_condition,
        "initial_cash": round(req.initial_cash, 2),
        "per_trade_budget": round(req.per_trade_budget, 2),
        "ending_cash": round(cash, 2),
        "ending_market_value": round(float(ending_market_value), 2),
        "ending_equity": round(ending_equity, 2),
        "total_return": round(ending_equity / req.initial_cash - 1.0, 6),
        "annualized_return": round(_annualized_return(req.initial_cash, ending_equity, len(daily_rows)), 6),
        "max_drawdown": round(abs(max_drawdown), 6),
        "buy_count": sum(1 for row in trades if row["action"] == "BUY"),
        "sell_count": sum(1 for row in trades if row["action"] == "SELL"),
        "blocked_buy_count": blocked_buy_count,
        "blocked_sell_count": blocked_sell_count,
        "skipped_buy_cash_count": skipped_buy_cash_count,
        "skipped_cutoff_buy_count": skipped_cutoff_buy_count,
        "sell_condition_exit_count": sell_condition_exit_count,
        "max_hold_exit_count": max_hold_exit_count,
        "open_position_count": len(open_position_rows),
        "pending_sell_signal_count": len(pending_sell_rows),
        "win_rate": round(win_rate, 6),
        "avg_trade_return": round(sum(sell_trade_returns) / len(sell_trade_returns), 6) if sell_trade_returns else 0.0,
        "median_trade_return": round(median_trade_return, 6) if sell_trade_returns else 0.0,
        "best_trade_return": round(max(sell_trade_returns), 6) if sell_trade_returns else 0.0,
        "worst_trade_return": round(min(sell_trade_returns), 6) if sell_trade_returns else 0.0,
        "profit_factor": round(profit_factor, 6),
        "avg_holding_days": round(_average(holding_days), 2) if holding_days else 0.0,
        "total_fees": round(total_fees, 2),
    }
    return {
        "summary": summary,
        "daily_rows": daily_rows,
        "pick_rows": picks,
        "trade_rows": trades,
        "contribution_rows": contribution_rows,
        "condition_rows": condition_rows,
        "year_rows": year_rows,
        "month_rows": month_rows,
        "exit_reason_rows": exit_reason_rows,
        "open_position_rows": open_position_rows,
        "pending_sell_rows": pending_sell_rows,
        "diagnostics": diagnostics,
    }


def run_portfolio_backtest(req: BacktestRequest) -> dict[str, Any]:
    loaded, diagnostics = load_processed_folder(req.processed_dir)
    data_profile = resolve_data_profile(
        requested_profile=req.data_profile,
        processed_dir=diagnostics["processed_dir"],
        buy_condition=req.buy_condition,
        sell_condition=req.sell_condition,
        score_expression=req.score_expression,
    )
    diagnostics["data_profile"] = data_profile
    if data_profile == "sector":
        diagnostics.update(validate_sector_feature_set(loaded_items=loaded, processed_dir=diagnostics["processed_dir"]))
    return run_portfolio_backtest_loaded(loaded, diagnostics, req)


_EXPORT_COLUMN_LABELS = {
    "action": "操作",
    "annualized_return": "年化收益率",
    "avg_holding_days": "平均持有天数",
    "avg_trade_return": "平均单笔收益",
    "best_return_since_entry": "持仓以来最大收益",
    "best_trade_return": "最好单笔收益",
    "blocked_buy_count": "买入阻塞次数",
    "blocked_sell_count": "卖出阻塞次数",
    "buy_count": "买入次数",
    "buy_date": "买入日期",
    "buy_fee_rate": "买入费率",
    "buy_net_amount": "买入净金额",
    "buy_price": "买入价",
    "candidate_count": "候选数",
    "candidate_days": "出现候选日数",
    "cash": "现金",
    "cash_after": "交易后现金",
    "category": "分类",
    "current_raw_close": "当前未复权收盘价",
    "drawdown": "回撤",
    "drawdown_from_peak": "从高点回撤",
    "ending_cash": "期末现金",
    "ending_equity": "期末权益",
    "ending_market_value": "期末持仓市值",
    "end_date": "结束日期",
    "entry_can_buy_open": "买入日可开盘买入",
    "entry_offset": "买入偏移",
    "entry_raw_open": "买入日未复权开盘价",
    "equity": "权益",
    "execution_note": "执行说明",
    "estimated_budget": "目标资金",
    "estimated_shares": "估算股数",
    "exit_can_sell_open": "卖出日可开盘卖出",
    "exit_offset": "固定卖出偏移",
    "exit_raw_open": "卖出日未复权开盘价",
    "exit_reason": "退出原因",
    "exit_signal_date": "退出信号日",
    "exit_type": "退出类型",
    "fees": "费用",
    "gross_amount": "成交金额",
    "holding_days": "持有天数",
    "holding_return": "当前浮盈",
    "initial_cash": "初始资金",
    "lot_size": "每手股数",
    "market_value": "持仓市值",
    "max_drawdown": "最大回撤",
    "max_exit_date": "最晚卖出日",
    "max_hold_days": "最大持有天数",
    "max_hold_exit_count": "固定或最大持有退出次数",
    "median_trade_return": "中位单笔收益",
    "metric": "指标",
    "min_hold_days": "最短持有天数",
    "name": "股票名称",
    "net_amount": "净金额",
    "open_position_count": "期末持仓数",
    "pending_order_count": "待执行订单数",
    "pending_sell_signal_count": "截止日卖出提醒数",
    "period": "周期",
    "period_return": "周期收益",
    "per_trade_budget": "每笔目标资金",
    "picked_count": "入选数",
    "picked_days": "触发选股日数",
    "planned_buy_date": "计划买入日",
    "planned_entry_date": "计划买入日",
    "planned_exit_date": "计划卖出日",
    "planned_sell_date": "计划卖出日",
    "position_count": "持仓数",
    "price": "成交价",
    "price_pnl": "价差盈亏",
    "profit_factor": "收益因子",
    "rank": "排名",
    "reading": "怎么看",
    "realistic_execution": "严格成交",
    "realized_pnl": "已实现盈亏",
    "reason": "说明",
    "score": "评分",
    "sell_condition": "卖出条件",
    "sell_condition_enabled": "启用卖出条件",
    "sell_condition_exit_count": "卖出条件触发次数",
    "sell_count": "卖出次数",
    "sell_fee_rate": "卖出费率",
    "settlement_mode": "结束日处理方式",
    "sector_exposure_score": "板块主题暴露分",
    "sector_strongest_board": "最强板块",
    "sector_strongest_theme": "最强主题",
    "sector_strongest_theme_m20": "最强主题二十日动量",
    "sector_strongest_theme_rank_pct": "最强主题排名百分位",
    "sector_strongest_theme_score": "最强主题综合分",
    "sector_theme_names": "命中主题",
    "shares": "股数",
    "signal_close": "信号日前复权收盘价",
    "signal_date": "信号日期",
    "signal_days": "信号日数",
    "signal_raw_close": "信号日未复权收盘价",
    "simulation_end_date": "模拟结束日期",
    "skipped_buy_cash_count": "资金不足跳过次数",
    "skipped_cutoff_buy_count": "截止日不买入次数",
    "slippage_bps": "滑点(bps)",
    "stamp_tax_sell": "卖出印花税",
    "start_date": "开始日期",
    "symbol": "股票代码",
    "total_fees": "总费用",
    "total_return": "总收益率",
    "trade_count": "交易次数",
    "trade_date": "交易日期",
    "trade_days": "交易日数",
    "trade_return": "交易收益",
    "unrealized_pnl": "浮动盈亏",
    "unrealized_return": "浮动收益",
    "valuation_date": "估值日期",
    "value": "数值",
    "win_rate": "胜率",
    "worst_trade_return": "最差单笔收益",
}


def _localize_export_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns={key: value for key, value in _EXPORT_COLUMN_LABELS.items() if key in frame.columns})


def export_backtest_zip(result: dict[str, Any]) -> bytes:
    buffers = {
        "汇总.csv": pd.DataFrame([result["summary"]]),
        "每日资金曲线.csv": pd.DataFrame(result["daily_rows"]),
        "每日选股明细.csv": pd.DataFrame(result["pick_rows"]),
        "交易流水.csv": pd.DataFrame(result["trade_rows"]),
        "个股贡献汇总.csv": pd.DataFrame(result["contribution_rows"]),
        "条件诊断.csv": pd.DataFrame(result.get("condition_rows", [])),
        "年度稳定性.csv": pd.DataFrame(result.get("year_rows", [])),
        "月度表现.csv": pd.DataFrame(result.get("month_rows", [])),
        "退出原因统计.csv": pd.DataFrame(result.get("exit_reason_rows", [])),
        "期末持仓.csv": pd.DataFrame(result.get("open_position_rows", [])),
        "截止日卖出提醒.csv": pd.DataFrame(result.get("pending_sell_rows", [])),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, frame in buffers.items():
            zf.writestr(name, _localize_export_frame(frame).to_csv(index=False, encoding="utf-8-sig"))
    return output.getvalue()
