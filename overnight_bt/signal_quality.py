from __future__ import annotations

import math
from typing import Any

import pandas as pd

from .backtest import (
    LoadedSymbol,
    _average,
    _build_eval_row,
    _compute_position_runtime_metrics,
    _count_holding_days,
    _effective_max_exit_offset,
    _effective_shares,
    _fmt_count,
    _fmt_num,
    _fmt_pct,
    _future_row,
    _max_drawdown_from_equity,
    _median,
    _period_key,
    _profit_factor,
    _score_required_offset,
    _within_range,
    load_processed_folder,
)
from .expressions import (
    compile_score_expression,
    evaluate_conditions,
    evaluate_score_expression,
    max_required_offset,
    parse_condition_expr,
)
from .models import Position, SignalQualityRequest
from .utils import to_float


_QUALITY_START_EQUITY = 100_000.0
_SIGNAL_FEATURE_COLUMNS = (
    "board",
    "market",
    "industry",
    "listed_days",
    "m5",
    "m10",
    "m20",
    "m60",
    "m120",
    "pct_chg",
    "close_pos_in_bar",
    "upper_shadow_pct",
    "lower_shadow_pct",
    "body_pct",
    "vr",
    "vol_ratio_5",
    "ret_accel_3",
    "hs300_m5",
    "hs300_m10",
    "hs300_m20",
    "hs300_m60",
    "hs300_m120",
    "hs300_pct_chg",
    "industry_m20",
    "industry_m60",
    "industry_rank_m20",
    "industry_rank_m60",
    "industry_up_ratio",
    "industry_strong_ratio",
    "industry_amount",
    "industry_amount20",
    "industry_amount_ratio",
    "industry_stock_count",
    "industry_valid_m20_count",
    "stock_vs_industry_m20",
    "stock_vs_industry_m60",
)


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _execution_price(row: pd.Series, side: str, req: SignalQualityRequest) -> float | None:
    open_px = to_float(row.get("raw_open"))
    if open_px is None or open_px <= 0:
        return None
    if not req.realistic_execution:
        return float(open_px)
    slip = float(req.slippage_bps) / 10000.0
    if side == "buy":
        return float(open_px) * (1.0 + slip)
    return float(open_px) * (1.0 - slip)


def _net_return(
    *,
    buy_price: float,
    sell_price: float,
    sell_shares: float,
    req: SignalQualityRequest,
) -> float:
    buy_gross = float(buy_price)
    buy_net = buy_gross * (1.0 + float(req.buy_fee_rate))
    sell_gross = float(sell_price) * float(sell_shares)
    sell_net = sell_gross * (1.0 - float(req.sell_fee_rate) - float(req.stamp_tax_sell))
    return sell_net / buy_net - 1.0 if buy_net > 0 else 0.0


def _next_sellable_idx(
    *,
    item: LoadedSymbol,
    start_idx: int,
    latest_idx: int,
    req: SignalQualityRequest,
) -> int | None:
    for idx in range(max(start_idx, 0), min(latest_idx, len(item.df) - 1) + 1):
        row = item.df.iloc[idx]
        if not req.realistic_execution or _is_truthy(row.get("can_sell_t", True)):
            return idx
    return None


def _signal_feature_values(row: pd.Series) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for column in _SIGNAL_FEATURE_COLUMNS:
        raw_value = row.get(column)
        numeric_value = to_float(raw_value)
        values[column] = numeric_value if numeric_value is not None else raw_value
    return values


def _build_quality_period_rows(daily_rows: list[dict], signal_rows: list[dict], period: str) -> list[dict]:
    daily_groups: dict[str, list[dict]] = {}
    for row in daily_rows:
        daily_groups.setdefault(_period_key(str(row["trade_date"]), period), []).append(row)

    signal_groups: dict[str, list[dict]] = {}
    for row in signal_rows:
        if row.get("status") != "已完成":
            continue
        signal_groups.setdefault(_period_key(str(row["signal_date"]), period), []).append(row)

    rows: list[dict] = []
    for key in sorted(daily_groups):
        period_daily = daily_groups[key]
        equities = [float(row["equity"]) for row in period_daily if row.get("equity") is not None]
        if not equities:
            continue
        completed = signal_groups.get(key, [])
        returns = [float(row["trade_return"]) for row in completed if row.get("trade_return") is not None]
        rows.append(
            {
                "period": key,
                "period_return": round(equities[-1] / equities[0] - 1.0, 6) if equities[0] > 0 else 0.0,
                "max_drawdown": round(_max_drawdown_from_equity(equities), 6),
                "ending_equity": round(equities[-1], 2),
                "picked_days": sum(1 for row in period_daily if int(row.get("picked_count", 0)) > 0),
                "signal_count": len(completed),
                "win_rate": round(sum(1 for item in returns if item > 0) / len(returns), 6) if returns else 0.0,
                "avg_trade_return": round(_average(returns), 6) if returns else 0.0,
                "median_trade_return": round(_median(returns), 6) if returns else 0.0,
            }
        )
    return rows


def _build_quality_exit_rows(signal_rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in signal_rows:
        if row.get("status") != "已完成":
            continue
        groups.setdefault(str(row.get("exit_type") or "未知"), []).append(row)

    rows: list[dict] = []
    for label, group in sorted(groups.items()):
        returns = [float(row["trade_return"]) for row in group if row.get("trade_return") is not None]
        holding_days = [float(row["holding_days"]) for row in group if row.get("holding_days") is not None]
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


def _build_quality_rank_rows(signal_rows: list[dict], top_n: int) -> list[dict]:
    rows: list[dict] = []
    for rank in range(1, int(top_n) + 1):
        group = [row for row in signal_rows if row.get("status") == "已完成" and int(row.get("rank", 0)) == rank]
        returns = [float(row["trade_return"]) for row in group if row.get("trade_return") is not None]
        holding_days = [float(row["holding_days"]) for row in group if row.get("holding_days") is not None]
        rows.append(
            {
                "rank": rank,
                "signal_count": len(group),
                "win_rate": round(sum(1 for item in returns if item > 0) / len(returns), 6) if returns else 0.0,
                "avg_trade_return": round(_average(returns), 6) if returns else 0.0,
                "median_trade_return": round(_median(returns), 6) if returns else 0.0,
                "p10_trade_return": round(pd.Series(returns).quantile(0.10), 6) if returns else 0.0,
                "p90_trade_return": round(pd.Series(returns).quantile(0.90), 6) if returns else 0.0,
                "avg_holding_days": round(_average(holding_days), 2) if holding_days else 0.0,
            }
        )
    return rows


def _scan_topk_values(top_n: int) -> list[int]:
    base_values = [1, 2, 3, 5, 10, 20, 50, 100]
    top_n = max(1, int(top_n))
    values = {value for value in base_values if value <= top_n}
    values.add(top_n)
    return sorted(values)


def _quality_note(*, avg_return: float, median_return: float, win_rate: float, profit_factor: float) -> str:
    if profit_factor <= 0:
        return "样本不足，暂时不能判断。"
    if median_return > 0 and profit_factor > 1.3:
        return "中位数为正且收益因子较好，信号更均衡。"
    if avg_return > 0 and median_return < 0 and profit_factor > 1:
        return "均值为正但中位数为负，偏低胜率高赔率。"
    if avg_return > 0 and win_rate >= 0.5:
        return "胜率和均值都为正，稳定性相对更好。"
    return "收益质量偏弱，需要谨慎或继续优化条件。"


def _build_quality_topk_rows(signal_rows: list[dict], signal_dates: list[str], top_n: int) -> list[dict]:
    completed_by_signal_date: dict[str, list[dict]] = {}
    all_by_signal_date: dict[str, list[dict]] = {}
    for row in signal_rows:
        signal_date = str(row.get("signal_date") or "")
        if not signal_date:
            continue
        all_by_signal_date.setdefault(signal_date, []).append(row)
        if row.get("status") == "已完成":
            completed_by_signal_date.setdefault(signal_date, []).append(row)

    rows: list[dict] = []
    for top_k in _scan_topk_values(top_n):
        all_group = [row for row in signal_rows if int(row.get("rank", 0)) <= top_k]
        completed_group = [row for row in all_group if row.get("status") == "已完成"]
        returns = [float(row["trade_return"]) for row in completed_group if row.get("trade_return") is not None]
        holding_days = [float(row["holding_days"]) for row in completed_group if row.get("holding_days") is not None]

        equity = _QUALITY_START_EQUITY
        equity_curve = [equity]
        daily_rows: list[dict[str, Any]] = []
        completed_days = 0
        picked_days = 0
        for signal_date in signal_dates:
            picked_today = [row for row in all_by_signal_date.get(signal_date, []) if int(row.get("rank", 0)) <= top_k]
            completed_today = [
                row for row in completed_by_signal_date.get(signal_date, []) if int(row.get("rank", 0)) <= top_k
            ]
            if picked_today:
                picked_days += 1
            day_returns = [
                float(row["trade_return"]) for row in completed_today if row.get("trade_return") is not None
            ]
            if day_returns:
                completed_days += 1
            daily_return = _average(day_returns) if day_returns else 0.0
            equity *= 1.0 + daily_return
            equity_curve.append(equity)
            daily_rows.append({"trade_date": signal_date, "equity": equity})

        year_returns: list[float] = []
        yearly_groups: dict[str, list[float]] = {}
        for row in daily_rows:
            yearly_groups.setdefault(_period_key(str(row["trade_date"]), "year"), []).append(float(row["equity"]))
        for equities in yearly_groups.values():
            if equities and equities[0] > 0:
                year_returns.append(equities[-1] / equities[0] - 1.0)
        profitable_years = sum(1 for value in year_returns if value > 0)

        avg_return = _average(returns) if returns else 0.0
        median_return = _median(returns) if returns else 0.0
        win_rate = sum(1 for item in returns if item > 0) / len(returns) if returns else 0.0
        profit_factor = _profit_factor(returns) if returns else 0.0
        max_drawdown = _max_drawdown_from_equity(equity_curve)
        stability_rate = profitable_years / len(year_returns) if year_returns else 0.0
        sample_ratio = min(len(completed_group) / 100.0, 1.0)
        complexity_penalty = math.log1p(float(top_k)) * 0.12
        recommendation_score = (
            avg_return * 100.0
            + median_return * 120.0
            + max(0.0, min(profit_factor, 5.0) - 1.0) * 0.8
            + (win_rate - 0.5) * 0.8
            + stability_rate * 0.8
            - abs(max_drawdown) * 0.6
            - complexity_penalty
        ) * sample_ratio

        rows.append(
            {
                "top_k": top_k,
                "signal_count": len(all_group),
                "completed_signal_count": len(completed_group),
                "picked_days": picked_days,
                "completed_days": completed_days,
                "topk_fill_rate": round(len(all_group) / (len(signal_dates) * top_k), 6)
                if signal_dates and top_k > 0
                else 0.0,
                "win_rate": round(win_rate, 6),
                "avg_trade_return": round(avg_return, 6),
                "median_trade_return": round(median_return, 6),
                "profit_factor": round(profit_factor, 6),
                "signal_curve_return": round(equity / _QUALITY_START_EQUITY - 1.0, 6),
                "max_drawdown": round(max_drawdown, 6),
                "best_trade_return": round(max(returns), 6) if returns else 0.0,
                "worst_trade_return": round(min(returns), 6) if returns else 0.0,
                "avg_holding_days": round(_average(holding_days), 2) if holding_days else 0.0,
                "profitable_years": profitable_years,
                "year_count": len(year_returns),
                "best_year_return": round(max(year_returns), 6) if year_returns else 0.0,
                "worst_year_return": round(min(year_returns), 6) if year_returns else 0.0,
                "recommendation_score": round(recommendation_score, 4),
                "quality_note": _quality_note(
                    avg_return=avg_return,
                    median_return=median_return,
                    win_rate=win_rate,
                    profit_factor=profit_factor,
                ),
            }
        )

    scored_rows = [row for row in rows if int(row.get("completed_signal_count", 0)) > 0]
    if scored_rows:
        recommended = max(
            scored_rows,
            key=lambda row: (
                float(row.get("recommendation_score", 0.0)),
                float(row.get("profit_factor", 0.0)),
                float(row.get("avg_trade_return", 0.0)),
                -int(row.get("top_k", 0)),
            ),
        )
        recommended_top_k = int(recommended["top_k"])
        for row in rows:
            row["recommended"] = "建议" if int(row["top_k"]) == recommended_top_k else ""
    return rows


def _build_quality_contribution_rows(signal_rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in signal_rows:
        if row.get("status") != "已完成":
            continue
        key = (str(row.get("symbol") or ""), str(row.get("name") or ""))
        groups.setdefault(key, []).append(row)

    rows: list[dict] = []
    for (symbol, name), group in groups.items():
        returns = [float(row["trade_return"]) for row in group if row.get("trade_return") is not None]
        rows.append(
            {
                "symbol": symbol,
                "name": name,
                "signal_count": len(group),
                "win_rate": round(sum(1 for item in returns if item > 0) / len(returns), 6) if returns else 0.0,
                "avg_trade_return": round(_average(returns), 6) if returns else 0.0,
                "median_trade_return": round(_median(returns), 6) if returns else 0.0,
                "total_signal_return": round(sum(returns), 6) if returns else 0.0,
            }
        )
    return sorted(rows, key=lambda row: (row["total_signal_return"], row["signal_count"]), reverse=True)


def _build_quality_condition_rows(
    *,
    summary: dict,
    diagnostics: dict,
    rank_rows: list[dict],
    topk_rows: list[dict],
    year_rows: list[dict],
) -> list[dict]:
    top_rank = rank_rows[0] if rank_rows else {}
    recommended_topk = next((row for row in topk_rows if row.get("recommended")), {})
    avg_rank_return = _average([float(row.get("avg_trade_return", 0.0)) for row in rank_rows]) if rank_rows else 0.0
    profitable_years = sum(1 for row in year_rows if float(row.get("period_return", 0.0)) > 0)
    best_year = max((float(row.get("period_return", 0.0)) for row in year_rows), default=0.0)
    worst_year = min((float(row.get("period_return", 0.0)) for row in year_rows), default=0.0)

    return [
        {
            "category": "信号覆盖",
            "metric": "有候选日占比",
            "value": _fmt_pct(summary.get("candidate_day_ratio", 0.0)),
            "reading": "越高说明条件经常能找到股票；过低时样本少，结果更容易偶然。",
        },
        {
            "category": "信号覆盖",
            "metric": "选股数量填满率",
            "value": _fmt_pct(summary.get("topn_fill_rate", 0.0)),
            "reading": "低于100%说明很多日期凑不满 TopN，评分表达式发挥空间有限。",
        },
        {
            "category": "信号质量",
            "metric": "完成信号数",
            "value": f"{_fmt_count(int(summary.get('completed_signal_count', 0)))}/{_fmt_count(int(summary.get('signal_count', 0)))}",
            "reading": "分母是入选信号，分子是已完成买卖或可计算收益的信号。",
        },
        {
            "category": "信号质量",
            "metric": "平均/中位单笔收益",
            "value": f"{_fmt_pct(summary.get('avg_trade_return', 0.0))} / {_fmt_pct(summary.get('median_trade_return', 0.0))}",
            "reading": "中位数更接近普通信号；均值明显更高时可能依赖少数大涨样本。",
        },
        {
            "category": "信号质量",
            "metric": "胜率 / 收益因子",
            "value": f"{_fmt_pct(summary.get('win_rate', 0.0))} / {_fmt_num(summary.get('profit_factor', 0.0), 2)}",
            "reading": "收益因子大于1说明盈利信号的合计收益超过亏损信号。",
        },
        {
            "category": "排名质量",
            "metric": "第1名收益 / 排名均值",
            "value": f"{_fmt_pct(float(top_rank.get('avg_trade_return', 0.0)))} / {_fmt_pct(avg_rank_return)}",
            "reading": "第1名显著高于排名均值，说明评分表达式确实有排序能力。",
        },
        {
            "category": "TopK扫描",
            "metric": "当前建议TopK",
            "value": f"Top{recommended_topk.get('top_k', '-')}",
            "reading": "按平均收益、中位收益、收益因子、胜率、年度稳定性、回撤和大TopK复杂度做辅助排序；最终仍要结合样本量和实盘资金约束。",
        },
        {
            "category": "执行摩擦",
            "metric": "买入阻塞信号",
            "value": _fmt_count(int(summary.get("blocked_entry_count", 0))),
            "reading": "严格成交下，次日开盘涨跌停或停牌导致无法买入的信号数量。",
        },
        {
            "category": "持仓去重",
            "metric": "持仓期跳过信号",
            "value": _fmt_count(int(summary.get("blocked_reentry_count", 0))),
            "reading": "同一股票已有虚拟持仓或待买订单时，不再重复入选，避免连续加仓放大风险。",
        },
        {
            "category": "持仓退出",
            "metric": "平均持有天数",
            "value": _fmt_num(float(summary.get("avg_holding_days", 0.0)), 2),
            "reading": "用于判断卖出条件和最长持有天数是否符合预期节奏。",
        },
        {
            "category": "时间稳定性",
            "metric": "盈利年份",
            "value": f"{profitable_years}/{len(year_rows)}",
            "reading": "比总收益更能体现条件是否跨年份有效。",
        },
        {
            "category": "时间稳定性",
            "metric": "最好/最差年份",
            "value": f"{_fmt_pct(best_year)} / {_fmt_pct(worst_year)}",
            "reading": "观察收益是否集中在单一年份，以及最差年份是否可接受。",
        },
        {
            "category": "口径说明",
            "metric": "资金约束",
            "value": "不使用现金",
            "reading": "信号质量回测不模拟账户现金和仓位金额，但会按单股虚拟持仓去重，避免同一股票持仓期重复买入。",
        },
        {
            "category": "数据诊断",
            "metric": "载入文件数",
            "value": _fmt_count(int(diagnostics.get("file_count", 0))),
            "reading": "参与本次信号扫描的股票 CSV 文件数量。",
        },
    ]


def run_signal_quality_loaded(
    loaded: list[LoadedSymbol],
    diagnostics: dict[str, Any],
    req: SignalQualityRequest,
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
    cutoff_mode = req.settlement_mode == "cutoff"
    cutoff_date = signal_dates[-1]

    rows_by_date: dict[str, list[tuple[LoadedSymbol, int]]] = {}
    for item in loaded:
        for date, idx in item.idx_by_date.items():
            rows_by_date.setdefault(date, []).append((item, idx))

    signal_rows: list[dict] = []
    daily_rows: list[dict] = []
    candidate_day_count = 0
    picked_day_count = 0
    total_candidate_count = 0
    blocked_entry_count = 0
    blocked_reentry_count = 0
    open_signal_count = 0
    completed_signal_count = 0
    equity = _QUALITY_START_EQUITY
    equity_curve = [equity]
    active_release_by_symbol: dict[str, str] = {}

    for signal_date in signal_dates:
        active_release_by_symbol = {
            symbol: release_date
            for symbol, release_date in active_release_by_symbol.items()
            if signal_date < release_date
        }
        date_rows = rows_by_date.get(signal_date, [])
        candidates: list[dict[str, Any]] = []
        reentry_blocked_today = 0
        for item, idx in date_rows:
            payload = _build_eval_row(item.df, idx, max_offset)
            ok, reason = evaluate_conditions(payload, buy_rules)
            if not ok:
                continue
            score = evaluate_score_expression(payload, score_tree)
            if math.isnan(score):
                continue
            if item.symbol in active_release_by_symbol:
                blocked_reentry_count += 1
                reentry_blocked_today += 1
                continue
            signal_row = item.df.iloc[idx]
            candidates.append(
                {
                    "item": item,
                    "idx": idx,
                    "score": float(score),
                    "reason": reason,
                    "signal_close": to_float(signal_row.get("close")),
                    "signal_raw_close": to_float(signal_row.get("raw_close")),
                    "signal_row": signal_row,
                }
            )

        candidates.sort(key=lambda row: (-row["score"], row["item"].symbol))
        selected = candidates[: int(req.top_n)]
        candidate_count = len(candidates)
        picked_count = len(selected)
        if candidate_count:
            candidate_day_count += 1
        if picked_count:
            picked_day_count += 1
        total_candidate_count += candidate_count

        completed_returns_today: list[float] = []
        for rank, candidate in enumerate(selected, start=1):
            item: LoadedSymbol = candidate["item"]
            idx = int(candidate["idx"])
            signal_row = candidate["signal_row"]
            entry = _future_row(item, idx, int(req.entry_offset))
            max_exit_idx = idx + _effective_max_exit_offset(req)
            signal_base = {
                "signal_date": signal_date,
                "symbol": item.symbol,
                "name": item.name,
                "rank": rank,
                "score": round(float(candidate["score"]), 6),
                "signal_close": round(candidate["signal_close"], 4) if candidate["signal_close"] is not None else None,
                "signal_raw_close": round(candidate["signal_raw_close"], 4) if candidate["signal_raw_close"] is not None else None,
                "sell_condition_enabled": bool(sell_rules),
                **_signal_feature_values(signal_row),
            }

            if entry is None:
                open_signal_count += 1
                signal_rows.append(
                    {
                        **signal_base,
                        "status": "未完成",
                        "planned_entry_date": "下一交易日",
                        "planned_exit_date": "未知",
                        "execution_note": "没有足够未来数据计算买入价",
                    }
                )
                continue

            entry_date, entry_row = entry
            if cutoff_mode and entry_date > cutoff_date:
                open_signal_count += 1
                signal_rows.append(
                    {
                        **signal_base,
                        "status": "未完成",
                        "planned_entry_date": entry_date,
                        "planned_exit_date": "截止日后",
                        "execution_note": "截止日后才会买入，不纳入已完成信号统计",
                    }
                )
                continue

            entry_idx = item.idx_by_date.get(entry_date)
            if entry_idx is None:
                open_signal_count += 1
                signal_rows.append(
                    {
                        **signal_base,
                        "status": "未完成",
                        "planned_entry_date": entry_date,
                        "planned_exit_date": "未知",
                        "execution_note": "买入日记录缺失",
                    }
                )
                continue

            if req.realistic_execution and not _is_truthy(entry_row.get("can_buy_open_t", False)):
                blocked_entry_count += 1
                signal_rows.append(
                    {
                        **signal_base,
                        "status": "买入阻塞",
                        "planned_entry_date": entry_date,
                        "planned_exit_date": "未成交",
                        "entry_can_buy_open": False,
                        "execution_note": "严格成交模式下买入日开盘不可买",
                    }
                )
                continue

            buy_price = _execution_price(entry_row, "buy", req)
            if buy_price is None:
                open_signal_count += 1
                signal_rows.append(
                    {
                        **signal_base,
                        "status": "未完成",
                        "planned_entry_date": entry_date,
                        "planned_exit_date": "未知",
                        "entry_can_buy_open": True,
                        "execution_note": "买入日缺少未复权开盘价",
                    }
                )
                continue

            latest_exit_idx = min(max_exit_idx, len(item.df) - 1)
            planned_exit_date = str(item.df.iloc[latest_exit_idx]["trade_date"]).strip()
            planned_exit_after_cutoff = bool(cutoff_mode and planned_exit_date > cutoff_date)
            if planned_exit_after_cutoff:
                latest_exit_idx = item.idx_by_date.get(cutoff_date, latest_exit_idx)

            pos = Position(
                symbol=item.symbol,
                name=item.name,
                shares=1,
                signal_date=signal_date,
                planned_entry_date=entry_date,
                buy_date=entry_date,
                planned_exit_date=planned_exit_date,
                max_exit_date=planned_exit_date,
                buy_price=float(buy_price),
                buy_net_amount=float(buy_price) * (1.0 + float(req.buy_fee_rate)),
                buy_adj_factor=to_float(entry_row.get("adj_factor")),
                score=float(candidate["score"]),
            )

            exit_idx: int | None = None
            exit_type = "固定或最大持有退出"
            exit_signal_date = ""
            if sell_rules:
                for current_idx in range(entry_idx, max(entry_idx, latest_exit_idx)):
                    current_row = item.df.iloc[current_idx]
                    current_date = str(current_row["trade_date"]).strip()
                    if cutoff_mode and current_date > cutoff_date:
                        break
                    holding_days = _count_holding_days(date_index, entry_date, current_date)
                    if holding_days < int(req.min_hold_days):
                        continue
                    payload = _build_eval_row(item.df, current_idx, max_offset)
                    payload.update(
                        _compute_position_runtime_metrics(
                            item=item,
                            pos=pos,
                            current_idx=current_idx,
                            current_row=current_row,
                            date_index=date_index,
                        )
                    )
                    ok, _ = evaluate_conditions(payload, sell_rules)
                    if not ok:
                        continue
                    candidate_exit_idx = current_idx + 1
                    if candidate_exit_idx > latest_exit_idx:
                        break
                    sellable_idx = _next_sellable_idx(
                        item=item,
                        start_idx=candidate_exit_idx,
                        latest_idx=latest_exit_idx,
                        req=req,
                    )
                    if sellable_idx is not None:
                        exit_idx = sellable_idx
                        exit_type = "卖出条件触发"
                        exit_signal_date = current_date
                    break

            if exit_idx is None:
                if planned_exit_after_cutoff:
                    open_signal_count += 1
                    valuation_row = item.df.iloc[latest_exit_idx]
                    active_release_by_symbol[item.symbol] = "99991231"
                    valuation_close = to_float(valuation_row.get("raw_close"))
                    unrealized_return = valuation_close / buy_price - 1.0 if valuation_close and buy_price > 0 else None
                    signal_rows.append(
                        {
                            **signal_base,
                            "status": "截止日估值",
                            "planned_entry_date": entry_date,
                            "planned_exit_date": "截止日后",
                            "entry_raw_open": round(float(to_float(entry_row.get("raw_open")) or 0.0), 4),
                            "entry_price": round(buy_price, 4),
                            "valuation_date": str(valuation_row["trade_date"]).strip(),
                            "unrealized_return": round(unrealized_return, 6) if unrealized_return is not None else None,
                            "execution_note": "最长持有退出在截止日之后，不读取未来开盘价，只做估值展示",
                        }
                    )
                    continue
                if max_exit_idx >= len(item.df) and not cutoff_mode:
                    open_signal_count += 1
                    active_release_by_symbol[item.symbol] = "99991231"
                    signal_rows.append(
                        {
                            **signal_base,
                            "status": "未完成",
                            "planned_entry_date": entry_date,
                            "planned_exit_date": "数据结束后",
                            "entry_raw_open": round(float(to_float(entry_row.get("raw_open")) or 0.0), 4),
                            "execution_note": "没有足够未来数据完成最长持有退出",
                        }
                    )
                    continue
                exit_idx = _next_sellable_idx(item=item, start_idx=latest_exit_idx, latest_idx=latest_exit_idx, req=req)

            if exit_idx is None:
                open_signal_count += 1
                valuation_row = item.df.iloc[latest_exit_idx]
                active_release_by_symbol[item.symbol] = "99991231"
                valuation_close = to_float(valuation_row.get("raw_close"))
                unrealized_return = valuation_close / buy_price - 1.0 if valuation_close and buy_price > 0 else None
                signal_rows.append(
                    {
                        **signal_base,
                        "status": "截止日估值",
                        "planned_entry_date": entry_date,
                        "planned_exit_date": planned_exit_date,
                        "entry_raw_open": round(float(to_float(entry_row.get("raw_open")) or 0.0), 4),
                        "entry_price": round(buy_price, 4),
                        "valuation_date": str(valuation_row["trade_date"]).strip(),
                        "unrealized_return": round(unrealized_return, 6) if unrealized_return is not None else None,
                        "execution_note": "截止日前未完成卖出，只做估值展示，不纳入已完成信号统计",
                    }
                )
                continue

            exit_row = item.df.iloc[exit_idx]
            exit_date = str(exit_row["trade_date"]).strip()
            if cutoff_mode and exit_date > cutoff_date:
                open_signal_count += 1
                continue
            sell_price = _execution_price(exit_row, "sell", req)
            if sell_price is None:
                open_signal_count += 1
                continue
            sell_shares = _effective_shares(pos, exit_row)
            trade_return = _net_return(buy_price=buy_price, sell_price=sell_price, sell_shares=sell_shares, req=req)
            holding_days = _count_holding_days(date_index, entry_date, exit_date)
            buy_fee = buy_price * float(req.buy_fee_rate)
            sell_fee = sell_price * sell_shares * (float(req.sell_fee_rate) + float(req.stamp_tax_sell))
            active_release_by_symbol[item.symbol] = exit_date
            completed_signal_count += 1
            completed_returns_today.append(trade_return)
            signal_rows.append(
                {
                    **signal_base,
                    "status": "已完成",
                    "planned_entry_date": entry_date,
                    "planned_exit_date": planned_exit_date,
                    "trade_date": exit_date,
                    "entry_raw_open": round(float(to_float(entry_row.get("raw_open")) or 0.0), 4),
                    "exit_raw_open": round(float(to_float(exit_row.get("raw_open")) or 0.0), 4),
                    "entry_price": round(buy_price, 4),
                    "exit_price": round(sell_price, 4),
                    "shares": round(float(sell_shares), 6),
                    "buy_fee": round(buy_fee, 6),
                    "sell_fee": round(sell_fee, 6),
                    "buy_net_amount": round(buy_price + buy_fee, 6),
                    "sell_net_amount": round(sell_price * sell_shares - sell_fee, 6),
                    "trade_return": round(trade_return, 6),
                    "holding_days": holding_days,
                    "exit_type": exit_type,
                    "exit_signal_date": exit_signal_date,
                    "execution_note": "信号质量样本，不使用账户现金；同一股票持仓期内不重复买入",
                }
            )

        daily_return = _average(completed_returns_today) if completed_returns_today else 0.0
        equity *= 1.0 + daily_return
        equity_curve.append(equity)
        peak = max(equity_curve)
        drawdown = equity / peak - 1.0 if peak > 0 else 0.0
        daily_rows.append(
            {
                "trade_date": signal_date,
                "equity": round(equity, 2),
                "drawdown": round(drawdown, 6),
                "candidate_count": candidate_count,
                "picked_count": picked_count,
                "completed_signal_count": len(completed_returns_today),
                "blocked_reentry_count": reentry_blocked_today,
                "avg_trade_return": round(daily_return, 6),
            }
        )

    completed_rows = [row for row in signal_rows if row.get("status") == "已完成"]
    returns = [float(row["trade_return"]) for row in completed_rows if row.get("trade_return") is not None]
    holding_days = [float(row["holding_days"]) for row in completed_rows if row.get("holding_days") is not None]
    year_rows = _build_quality_period_rows(daily_rows, signal_rows, "year")
    month_rows = _build_quality_period_rows(daily_rows, signal_rows, "month")
    rank_rows = _build_quality_rank_rows(signal_rows, req.top_n)
    topk_rows = _build_quality_topk_rows(signal_rows, signal_dates, req.top_n)
    exit_rows = _build_quality_exit_rows(signal_rows)
    contribution_rows = _build_quality_contribution_rows(signal_rows)
    signal_count = len(signal_rows)
    max_possible_picks = len(signal_dates) * int(req.top_n)
    recommended_topk = next((row for row in topk_rows if row.get("recommended")), {})
    summary = {
        "result_mode": "signal_quality",
        "start_date": signal_dates[0],
        "end_date": signal_dates[-1],
        "settlement_mode": "截止日估值" if cutoff_mode else "完整结算",
        "trade_days": len(signal_dates),
        "top_n": int(req.top_n),
        "entry_offset": int(req.entry_offset),
        "exit_offset": int(req.exit_offset),
        "min_hold_days": int(req.min_hold_days),
        "max_hold_days": int(req.max_hold_days),
        "sell_condition": req.sell_condition,
        "signal_count": signal_count,
        "completed_signal_count": completed_signal_count,
        "open_signal_count": open_signal_count,
        "blocked_entry_count": blocked_entry_count,
        "blocked_reentry_count": blocked_reentry_count,
        "candidate_days": candidate_day_count,
        "picked_days": picked_day_count,
        "candidate_day_ratio": round(candidate_day_count / len(signal_dates), 6) if signal_dates else 0.0,
        "topn_fill_rate": round(signal_count / max_possible_picks, 6) if max_possible_picks else 0.0,
        "avg_signals_per_day": round(signal_count / len(signal_dates), 4) if signal_dates else 0.0,
        "avg_trade_return": round(_average(returns), 6) if returns else 0.0,
        "median_trade_return": round(_median(returns), 6) if returns else 0.0,
        "best_trade_return": round(max(returns), 6) if returns else 0.0,
        "worst_trade_return": round(min(returns), 6) if returns else 0.0,
        "win_rate": round(sum(1 for item in returns if item > 0) / len(returns), 6) if returns else 0.0,
        "profit_factor": round(_profit_factor(returns), 6) if returns else 0.0,
        "avg_holding_days": round(_average(holding_days), 2) if holding_days else 0.0,
        "signal_curve_return": round(equity / _QUALITY_START_EQUITY - 1.0, 6),
        "max_drawdown": round(_max_drawdown_from_equity(equity_curve), 6),
        "recommended_top_k": recommended_topk.get("top_k"),
        "recommended_topk_score": recommended_topk.get("recommendation_score", 0.0),
        "recommended_topk_avg_trade_return": recommended_topk.get("avg_trade_return", 0.0),
        "recommended_topk_median_trade_return": recommended_topk.get("median_trade_return", 0.0),
        "recommended_topk_profit_factor": recommended_topk.get("profit_factor", 0.0),
    }
    diagnostics.update(
        {
            "signal_days": len(signal_dates),
            "candidate_days": candidate_day_count,
            "picked_days": picked_day_count,
            "completed_signal_count": completed_signal_count,
            "blocked_reentry_count": blocked_reentry_count,
        }
    )
    condition_rows = _build_quality_condition_rows(
        summary=summary,
        diagnostics=diagnostics,
        rank_rows=rank_rows,
        topk_rows=topk_rows,
        year_rows=year_rows,
    )
    return {
        "summary": summary,
        "daily_rows": daily_rows,
        "pick_rows": signal_rows,
        "trade_rows": completed_rows,
        "contribution_rows": contribution_rows,
        "condition_rows": condition_rows,
        "topk_rows": topk_rows,
        "rank_rows": rank_rows,
        "year_rows": year_rows,
        "month_rows": month_rows,
        "exit_reason_rows": exit_rows,
        "diagnostics": diagnostics,
    }


def run_signal_quality(req: SignalQualityRequest) -> dict[str, Any]:
    loaded, diagnostics = load_processed_folder(req.processed_dir)
    return run_signal_quality_loaded(loaded, diagnostics, req)
