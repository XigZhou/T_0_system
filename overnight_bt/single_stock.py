from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from .expressions import evaluate_conditions, max_required_offset, parse_condition_expr
from .models import SingleStockBacktestRequest


REQUIRED_BY_TIMING = {
    "same_day_close": {"close"},
    "next_day_open": {"open", "close"},
}


def _normalize_columns(df: pd.DataFrame) -> dict[str, str]:
    return {str(col).strip().lower(): str(col) for col in df.columns}


def _pick_excel_engine(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return "openpyxl"
    if suffix == ".xls":
        return "xlrd"
    raise ValueError(f"unsupported excel suffix: {suffix}")


def load_single_stock_excel(excel_path: str, execution_timing: str) -> tuple[pd.DataFrame, str, str]:
    path = Path(excel_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"excel not found: {path}")

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
    return work, stock_code, stock_name


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
        price = df.iloc[signal_idx].get("close")
        if pd.isna(price):
            return None, None, "close is NaN"
        return signal_idx, float(price), "same_day_close"

    exec_idx = signal_idx + 1
    if exec_idx >= len(df):
        return None, None, "next day does not exist"
    price = df.iloc[exec_idx].get("open")
    if pd.isna(price):
        return None, None, "next day open is NaN"
    return exec_idx, float(price), "next_day_open"


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


def run_single_stock_backtest(req: SingleStockBacktestRequest) -> dict:
    df, stock_code, stock_name = load_single_stock_excel(req.excel_path, req.execution_timing)
    df = _apply_date_range(df, req.start_date, req.end_date)

    buy_rules = parse_condition_expr(req.buy_condition)
    sell_rules = parse_condition_expr(req.sell_condition)
    max_offset = max(max_required_offset(buy_rules), max_required_offset(sell_rules))

    cash = float(req.initial_cash)
    position = 0
    avg_cost_per_share = 0.0
    last_buy_exec_idx: int | None = None
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
    equity_curve: list[float] = []

    for idx in range(len(df)):
        row = df.iloc[idx].to_dict()
        trade_date_text = str(row.get("trade_date_text", ""))
        executed_action = ""
        executed_reason = ""

        if pending_order and pending_order["exec_idx"] == idx:
            exec_price = pending_order["price"]
            current_close = float(row.get("close")) if not pd.isna(row.get("close")) else exec_price
            if pending_order["action"] == "BUY":
                shares = pending_order["shares"]
                gross_amount = exec_price * shares
                fees = pending_order["fees"]
                net_amount = gross_amount + fees
                cash -= net_amount
                position = shares
                avg_cost_per_share = net_amount / shares if shares else 0.0
                position_market_value_after = current_close * position
                equity_after = cash + position_market_value_after
                trades.append(
                    {
                        "signal_date": pending_order["signal_date"],
                        "trade_date": trade_date_text,
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
                        "reason": pending_order["reason"],
                    }
                )
                last_buy_exec_idx = idx
                executed_action = "BUY"
                executed_reason = pending_order["reason"]
            else:
                shares = position
                gross_amount = exec_price * shares
                fees = gross_amount * (req.sell_fee_rate + req.stamp_tax_sell)
                net_amount = gross_amount - fees
                realized = net_amount - (avg_cost_per_share * shares)
                cash += net_amount
                position = 0
                avg_cost_per_share = 0.0
                if realized > 0:
                    win_count += 1
                    gross_profit_total += realized
                elif realized < 0:
                    loss_count += 1
                    gross_loss_total += abs(realized)
                realized_pnl_total += realized
                position_market_value_after = 0.0
                equity_after = cash
                trades.append(
                    {
                        "signal_date": pending_order["signal_date"],
                        "trade_date": trade_date_text,
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
                        "reason": pending_order["reason"],
                    }
                )
                executed_action = "SELL"
                executed_reason = pending_order["reason"]
            pending_order = None

        eval_row = _build_eval_row(df, idx, max_offset)
        buy_ok, buy_reason = evaluate_conditions(eval_row, buy_rules)
        sell_ok, sell_reason = evaluate_conditions(eval_row, sell_rules)

        buy_streak = buy_streak + 1 if buy_ok else 0
        sell_streak = sell_streak + 1 if sell_ok else 0

        scheduled_action = ""
        scheduled_trade_date = ""
        signal_reason = "no signal"

        if pending_order is None:
            if position > 0 and sell_streak >= req.sell_confirm_days:
                exec_idx, exec_price, px_src = _execution_point(df, idx, req.execution_timing)
                if exec_idx is not None and exec_price is not None:
                    pending_order = {
                        "action": "SELL",
                        "signal_date": trade_date_text,
                        "exec_idx": exec_idx,
                        "price": float(exec_price),
                        "reason": f"sell streak reached ({sell_streak}) via {px_src}",
                    }
                    scheduled_action = "SELL"
                    scheduled_trade_date = str(df.iloc[exec_idx].get("trade_date_text", trade_date_text))
                    signal_reason = sell_reason
                    if req.execution_timing == "same_day_close":
                        continue
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
                                "shares": int(shares),
                                "fees": float(fees),
                                "reason": f"buy streak reached ({buy_streak}) via {px_src}",
                            }
                            scheduled_action = "BUY"
                            scheduled_trade_date = str(df.iloc[exec_idx].get("trade_date_text", trade_date_text))
                            signal_reason = buy_reason
                            if req.execution_timing == "same_day_close":
                                continue
                        else:
                            signal_reason = "insufficient cash for configured trade budget"
                    else:
                        signal_reason = f"buy signal but cannot execute: {px_src}"
                else:
                    signal_reason = f"buy cooldown active ({req.buy_cooldown_days} days)"

        close_price = float(row.get("close")) if not pd.isna(row.get("close")) else 0.0
        position_market_value = position * close_price
        equity = cash + position_market_value
        equity_curve.append(equity)

        daily_rows.append(
            {
                "trade_date": trade_date_text,
                "open": None if pd.isna(row.get("open")) else float(row.get("open")),
                "high": None if pd.isna(row.get("high")) else float(row.get("high")),
                "low": None if pd.isna(row.get("low")) else float(row.get("low")),
                "close": None if pd.isna(row.get("close")) else float(row.get("close")),
                "vol": None if pd.isna(row.get("vol")) else float(row.get("vol")),
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

    last_close = float(df.iloc[-1].get("close")) if not pd.isna(df.iloc[-1].get("close")) else 0.0
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
        "trade_count": len(trades),
        "buy_count": len([trade for trade in trades if trade["action"] == "BUY"]),
        "sell_count": len(sell_trades),
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
        "summary": summary,
        "metric_definitions": _metric_definitions(),
        "trade_rows": trades,
        "signal_rows": daily_rows,
    }
