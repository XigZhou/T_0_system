from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.backtest import _average, _max_drawdown_from_equity, _median, _period_key, _profit_factor
from overnight_bt.expressions import evaluate_conditions, parse_condition_expr
from overnight_bt.models import SignalQualityRequest
from overnight_bt.signal_quality import run_signal_quality


DEFAULT_PROCESSED_DIR = "data_bundle/processed_qfq_theme_focus_top100"
DEFAULT_START_DATE = "20230101"
DEFAULT_END_DATE = "20251231"
DEFAULT_BUY_CONDITION = "m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1"
DEFAULT_SELL_CONDITION = "m20<0.08,hs300_m20<0.02"
DEFAULT_SCORE_EXPRESSION = (
    "m20 * 140 + (m20 - m60 / 3) * 90 + (m20 - m120 / 6) * 40 "
    "- abs(m5 - 0.03) * 55 - abs(m10 - 0.08) * 30"
)


@dataclass(frozen=True)
class FilterCase:
    name: str
    label: str
    extra_condition: str


@dataclass(frozen=True)
class SellCase:
    name: str
    label: str
    condition: str


def _timestamp_dir(prefix: str = "signal_median_scan") -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("research_runs") / f"{stamp}_{prefix}"


def _parse_ints(text: str) -> list[int]:
    return [int(item.strip()) for item in text.split(",") if item.strip()]


def _format_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "-"


def _build_filter_cases() -> list[FilterCase]:
    return [
        FilterCase("base", "不加过滤", ""),
        FilterCase("m5_gt_0", "五日动量为正", "m5>0"),
        FilterCase("m5_gt_m1pct", "五日动量不弱于-1%", "m5>-0.01"),
        FilterCase("m5_gt_2pct", "五日动量大于2%", "m5>0.02"),
        FilterCase("m5_gt_3pct", "五日动量大于3%", "m5>0.03"),
        FilterCase("m10_gt_0", "十日动量为正", "m10>0"),
        FilterCase("m10_gt_2pct", "十日动量大于2%", "m10>0.02"),
        FilterCase("m10_gt_4pct", "十日动量大于4%", "m10>0.04"),
        FilterCase("m10_gt_6pct", "十日动量大于6%", "m10>0.06"),
        FilterCase("m20_gt_10pct", "二十日动量大于10%", "m20>0.10"),
        FilterCase("m20_gt_12pct", "二十日动量大于12%", "m20>0.12"),
        FilterCase("m20_gt_15pct", "二十日动量大于15%", "m20>0.15"),
        FilterCase("m20_gt_m60", "二十日动量强于六十日", "m20>m60"),
        FilterCase("m20_gt_m120", "二十日动量强于一百二十日", "m20>m120"),
        FilterCase("m5_lt_8pct", "五日动量低于8%", "m5<0.08"),
        FilterCase("m10_lt_14pct", "十日动量低于14%", "m10<0.14"),
        FilterCase("hs300_m20_gt_0", "沪深300二十日动量为正", "hs300_m20>0"),
        FilterCase("hs300_m20_gt_1pct", "沪深300二十日动量大于1%", "hs300_m20>0.01"),
        FilterCase("hs300_m20_gt_2pct", "沪深300二十日动量大于2%", "hs300_m20>0.02"),
        FilterCase("hs300_m10_gt_0", "沪深300十日动量为正", "hs300_m10>0"),
        FilterCase("hs300_m5_gt_0", "沪深300五日动量为正", "hs300_m5>0"),
        FilterCase("hs300_m5_gt_m1pct", "沪深300五日动量不弱于-1%", "hs300_m5>-0.01"),
        FilterCase("pct_chg_band", "当日涨跌幅在-1%到3%", "pct_chg>-1,pct_chg<3"),
        FilterCase("pct_chg_tight", "当日涨跌幅在-0.5%到2.5%", "pct_chg>-0.5,pct_chg<2.5"),
        FilterCase("close_pos_gt_60", "收盘位于日K上部60%", "close_pos_in_bar>0.60"),
        FilterCase("close_pos_gt_65", "收盘位于日K上部65%", "close_pos_in_bar>0.65"),
        FilterCase("upper_shadow_lt_3", "上影线低于3%", "upper_shadow_pct<0.03"),
        FilterCase("upper_shadow_lt_2", "上影线低于2%", "upper_shadow_pct<0.02"),
        FilterCase("body_gt_0", "日K实体为正", "body_pct>0"),
        FilterCase("vr_lt_18", "量比低于1.8", "vr<1.8"),
        FilterCase("vr_lt_16", "量比低于1.6", "vr<1.6"),
        FilterCase("main_ld500", "主板且上市超过500天", "board=主板,listed_days>500"),
        FilterCase("m5_m10_positive", "五日和十日动量都为正", "m5>0,m10>0"),
        FilterCase("m5_m10_positive_market", "短动量为正且大盘二十日为正", "m5>0,m10>0,hs300_m20>0"),
        FilterCase("anti_overheat", "短期不过热", "m5<0.08,m10<0.14"),
        FilterCase("anti_overheat_m5pos", "短期不过热且五日为正", "m5>0,m5<0.08,m10<0.14"),
        FilterCase("bar_quality", "K线质量过滤", "pct_chg>-1,pct_chg<3,close_pos_in_bar>0.60,upper_shadow_pct<0.03"),
        FilterCase("bar_quality_vr", "K线质量加量比过滤", "pct_chg>-1,pct_chg<3,close_pos_in_bar>0.60,upper_shadow_pct<0.03,vr<1.8"),
        FilterCase("main_quality", "主板成熟股加K线质量", "board=主板,listed_days>500,pct_chg>-1,pct_chg<3,close_pos_in_bar>0.60,upper_shadow_pct<0.03"),
        FilterCase("balanced_1", "短动量正+不过热+大盘正", "m5>0,m10>0,m5<0.08,m10<0.14,hs300_m20>0"),
        FilterCase("balanced_2", "短动量正+K线质量", "m5>0,m10>0,pct_chg>-1,pct_chg<3,close_pos_in_bar>0.60,upper_shadow_pct<0.03"),
        FilterCase("balanced_3", "主板成熟+短动量正+K线质量", "board=主板,listed_days>500,m5>0,m10>0,pct_chg>-1,pct_chg<3,close_pos_in_bar>0.60,upper_shadow_pct<0.03"),
        FilterCase("balanced_4", "短动量强+不过热+大盘强", "m5>0.02,m10>0.02,m5<0.08,m10<0.14,hs300_m20>0.01"),
        FilterCase("balanced_5", "短动量强+二十日更强+大盘强", "m5>0.02,m10>0.04,m20>0.10,hs300_m20>0.01"),
        FilterCase("balanced_6", "动量形态向上+不过热", "m20>m60,m20>m120,m5>0,m10>0,m5<0.08,m10<0.14"),
        FilterCase("balanced_7", "动量形态向上+大盘强", "m20>m60,m20>m120,m5>0,m10>0,hs300_m20>0.01"),
        FilterCase("strict_bar", "严格K线质量", "pct_chg>-0.5,pct_chg<2.5,close_pos_in_bar>0.65,upper_shadow_pct<0.02,body_pct>0"),
        FilterCase("strict_bar_momentum", "严格K线质量+短动量正", "m5>0,m10>0,pct_chg>-0.5,pct_chg<2.5,close_pos_in_bar>0.65,upper_shadow_pct<0.02,body_pct>0"),
        FilterCase("strict_all", "主板成熟+短动量正+严格K线质量+大盘强", "board=主板,listed_days>500,m5>0,m10>0,pct_chg>-0.5,pct_chg<2.5,close_pos_in_bar>0.65,upper_shadow_pct<0.02,body_pct>0,hs300_m20>0.01"),
        FilterCase("industry_m20_gt_0", "行业二十日动量为正", "industry_m20>0"),
        FilterCase("industry_m20_gt_3pct", "行业二十日动量大于3%", "industry_m20>0.03"),
        FilterCase("industry_top30_m20", "行业二十日强度前30%", "industry_rank_m20<0.3"),
        FilterCase("industry_top20_m20", "行业二十日强度前20%", "industry_rank_m20<0.2"),
        FilterCase("industry_up_gt_50", "行业上涨占比超过50%", "industry_up_ratio>0.5"),
        FilterCase("industry_strong_gt_50", "行业强势股占比超过50%", "industry_strong_ratio>0.5"),
        FilterCase("stock_stronger_than_industry", "个股强于所属行业", "stock_vs_industry_m20>0"),
        FilterCase("industry_top30_positive", "强行业且行业动量为正", "industry_rank_m20<0.3,industry_m20>0"),
        FilterCase("industry_top30_breadth", "强行业且内部扩散好", "industry_rank_m20<0.3,industry_up_ratio>0.5,industry_strong_ratio>0.5"),
        FilterCase("industry_top30_stock_alpha", "强行业里的相对强个股", "industry_rank_m20<0.3,industry_m20>0,stock_vs_industry_m20>0"),
        FilterCase("market_industry_stock", "强市场+强行业+强个股", "hs300_m20>0.02,industry_rank_m20<0.3,industry_m20>0,stock_vs_industry_m20>0"),
        FilterCase("market_industry_breadth", "强市场+强行业+扩散好", "hs300_m20>0.02,industry_rank_m20<0.3,industry_up_ratio>0.5,industry_strong_ratio>0.5"),
        FilterCase("industry_guarded_top30", "强行业且样本数充足", "industry_stock_count>=3,industry_valid_m20_count>=3,industry_rank_m20<0.3,industry_m20>0"),
        FilterCase("market_industry_guarded_stock", "强市场+强行业+强个股+样本数充足", "industry_stock_count>=3,industry_valid_m20_count>=3,hs300_m20>0.02,industry_rank_m20<0.3,industry_m20>0,stock_vs_industry_m20>0"),
    ]


def _build_sell_cases(base_sell_condition: str) -> list[SellCase]:
    return [
        SellCase("current", "当前卖出条件", base_sell_condition),
        SellCase("m10_lt_2pct_and_m20", "十日转弱且二十日跌破8%", "m10<0.02,m20<0.08"),
        SellCase("m5_lt_0_and_m20", "五日转弱且二十日跌破8%", "m5<0,m20<0.08"),
    ]


def _condition_matches(row: dict[str, Any], rules: list[Any]) -> bool:
    if not rules:
        return True
    ok, _ = evaluate_conditions(row, rules)
    return ok


def _selected_rows(rows: list[dict[str, Any]], rules: list[Any], top_k: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not _condition_matches(row, rules):
            continue
        grouped.setdefault(str(row.get("signal_date") or ""), []).append(row)

    selected: list[dict[str, Any]] = []
    for signal_date in sorted(grouped):
        group = sorted(
            grouped[signal_date],
            key=lambda item: (-float(item.get("score") or 0.0), str(item.get("symbol") or "")),
        )
        for rank_after_filter, item in enumerate(group[:top_k], start=1):
            selected.append({**item, "rank_after_filter": rank_after_filter})
    return selected


def _evaluate_selection(
    *,
    selected: list[dict[str, Any]],
    signal_dates: list[str],
    top_k: int,
    filter_case: FilterCase,
    sell_case: SellCase,
) -> dict[str, Any]:
    completed = [row for row in selected if row.get("status") == "已完成" and row.get("trade_return") is not None]
    returns = [float(row["trade_return"]) for row in completed]
    holding_days = [float(row["holding_days"]) for row in completed if row.get("holding_days") is not None]

    selected_by_date: dict[str, list[dict[str, Any]]] = {}
    for row in selected:
        selected_by_date.setdefault(str(row.get("signal_date") or ""), []).append(row)

    equity = 100_000.0
    equity_curve = [equity]
    daily_equities: list[dict[str, Any]] = []
    completed_days = 0
    picked_days = 0
    for signal_date in signal_dates:
        today = selected_by_date.get(signal_date, [])
        if today:
            picked_days += 1
        today_returns = [
            float(row["trade_return"])
            for row in today
            if row.get("status") == "已完成" and row.get("trade_return") is not None
        ]
        if today_returns:
            completed_days += 1
        equity *= 1.0 + (_average(today_returns) if today_returns else 0.0)
        equity_curve.append(equity)
        daily_equities.append({"trade_date": signal_date, "equity": equity})

    year_returns: list[float] = []
    year_groups: dict[str, list[float]] = {}
    for row in daily_equities:
        year_groups.setdefault(_period_key(str(row["trade_date"]), "year"), []).append(float(row["equity"]))
    for equities in year_groups.values():
        if equities and equities[0] > 0:
            year_returns.append(equities[-1] / equities[0] - 1.0)

    avg_return = _average(returns) if returns else 0.0
    median_return = _median(returns) if returns else 0.0
    win_rate = sum(1 for item in returns if item > 0) / len(returns) if returns else 0.0
    profit_factor = _profit_factor(returns) if returns else 0.0
    max_drawdown = _max_drawdown_from_equity(equity_curve)
    stability_rate = sum(1 for item in year_returns if item > 0) / len(year_returns) if year_returns else 0.0
    median_score = (
        median_return * 250.0
        + avg_return * 60.0
        + max(0.0, min(profit_factor, 5.0) - 1.0) * 0.7
        + (win_rate - 0.5) * 0.7
        + stability_rate * 0.6
        - abs(max_drawdown) * 0.4
    )

    return {
        "filter_case": filter_case.name,
        "filter_label": filter_case.label,
        "extra_buy_condition": filter_case.extra_condition,
        "sell_case": sell_case.name,
        "sell_label": sell_case.label,
        "sell_condition": sell_case.condition,
        "top_k": top_k,
        "signal_count": len(selected),
        "completed_signal_count": len(completed),
        "picked_days": picked_days,
        "completed_days": completed_days,
        "topk_fill_rate": round(len(selected) / (len(signal_dates) * top_k), 6) if signal_dates and top_k > 0 else 0.0,
        "avg_trade_return": round(avg_return, 6),
        "median_trade_return": round(median_return, 6),
        "win_rate": round(win_rate, 6),
        "profit_factor": round(profit_factor, 6),
        "signal_curve_return": round(equity / 100_000.0 - 1.0, 6),
        "max_drawdown": round(max_drawdown, 6),
        "best_trade_return": round(max(returns), 6) if returns else 0.0,
        "worst_trade_return": round(min(returns), 6) if returns else 0.0,
        "avg_holding_days": round(_average(holding_days), 2) if holding_days else 0.0,
        "profitable_years": sum(1 for item in year_returns if item > 0),
        "year_count": len(year_returns),
        "best_year_return": round(max(year_returns), 6) if year_returns else 0.0,
        "worst_year_return": round(min(year_returns), 6) if year_returns else 0.0,
        "median_priority_score": round(median_score, 4),
    }


def _scan_pool(
    *,
    pool_rows: list[dict[str, Any]],
    signal_dates: list[str],
    filter_cases: list[FilterCase],
    sell_case: SellCase,
    top_k_values: list[int],
) -> tuple[list[dict[str, Any]], dict[tuple[str, int], list[dict[str, Any]]]]:
    result_rows: list[dict[str, Any]] = []
    selected_lookup: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for filter_case in filter_cases:
        rules = parse_condition_expr(filter_case.extra_condition) if filter_case.extra_condition else []
        for top_k in top_k_values:
            selected = _selected_rows(pool_rows, rules, top_k)
            selected_lookup[(filter_case.name, top_k)] = selected
            result_rows.append(
                _evaluate_selection(
                    selected=selected,
                    signal_dates=signal_dates,
                    top_k=top_k,
                    filter_case=filter_case,
                    sell_case=sell_case,
                )
            )
    return result_rows, selected_lookup


def _best_row(rows: list[dict[str, Any]], min_completed: int) -> dict[str, Any]:
    candidates = [row for row in rows if int(row.get("completed_signal_count", 0)) >= min_completed]
    if not candidates:
        candidates = rows
    return max(
        candidates,
        key=lambda row: (
            float(row.get("median_trade_return", 0.0)),
            float(row.get("profit_factor", 0.0)),
            float(row.get("avg_trade_return", 0.0)),
            float(row.get("win_rate", 0.0)),
            int(row.get("completed_signal_count", 0)),
        ),
    )


def _write_best_records(out_dir: Path, best: dict[str, Any], selected_rows: list[dict[str, Any]]) -> None:
    records = [row for row in selected_rows if row.get("status") == "已完成"]
    df = pd.DataFrame(records)
    if df.empty:
        df.to_csv(out_dir / "最佳组合信号明细.csv", index=False, encoding="utf-8-sig")
        return

    df["filter_label"] = best["filter_label"]
    df["sell_label"] = best["sell_label"]
    df["top_k"] = best["top_k"]
    columns = [
        "filter_label",
        "sell_label",
        "top_k",
        "signal_date",
        "planned_entry_date",
        "trade_date",
        "symbol",
        "name",
        "rank_after_filter",
        "rank",
        "score",
        "entry_price",
        "exit_price",
        "shares",
        "buy_fee",
        "sell_fee",
        "buy_net_amount",
        "sell_net_amount",
        "trade_return",
        "holding_days",
        "exit_type",
        "m5",
        "m10",
        "m20",
        "m60",
        "m120",
        "hs300_m20",
        "pct_chg",
        "close_pos_in_bar",
        "upper_shadow_pct",
        "vr",
        "board",
        "listed_days",
    ]
    existing = [column for column in columns if column in df.columns]
    df[existing].rename(
        columns={
            "filter_label": "买入过滤",
            "sell_label": "卖出条件",
            "top_k": "累计TopK",
            "signal_date": "信号日期",
            "planned_entry_date": "买入日期",
            "trade_date": "卖出日期",
            "symbol": "股票代码",
            "name": "股票名称",
            "rank_after_filter": "过滤后排名",
            "rank": "原始排名",
            "score": "评分",
            "entry_price": "买入执行价",
            "exit_price": "卖出执行价",
            "shares": "虚拟股数",
            "buy_fee": "买入费用",
            "sell_fee": "卖出费用",
            "buy_net_amount": "买入净金额",
            "sell_net_amount": "卖出净金额",
            "trade_return": "单笔收益率",
            "holding_days": "持有天数",
            "exit_type": "退出类型",
            "m5": "五日动量",
            "m10": "十日动量",
            "m20": "二十日动量",
            "m60": "六十日动量",
            "m120": "一百二十日动量",
            "hs300_m20": "沪深300二十日动量",
            "pct_chg": "当日涨跌幅",
            "close_pos_in_bar": "收盘所在日K位置",
            "upper_shadow_pct": "上影线占比",
            "vr": "量比",
            "board": "板块",
            "listed_days": "上市天数",
        }
    ).to_csv(out_dir / "最佳组合信号明细.csv", index=False, encoding="utf-8-sig")


def _render_summary(
    *,
    out_dir: Path,
    args: argparse.Namespace,
    best: dict[str, Any],
    top_rows: list[dict[str, Any]],
    sell_case_rows: list[dict[str, Any]],
) -> str:
    lines = [
        "# 信号中位收益优化扫描总结",
        "",
        "## 扫描口径",
        "",
        f"- 数据目录：`{args.processed_dir}`",
        f"- 日期范围：`{args.start_date}` 到 `{args.end_date}`",
        f"- 基础买入条件：`{args.buy_condition}`",
        f"- 基础卖出条件：`{args.sell_condition}`",
        f"- 评分表达式：`{args.score_expression}`",
        f"- 候选池 TopN：`{args.pool_top_n}`",
        f"- 扫描 TopK：`{','.join(str(item) for item in _parse_ints(args.top_k_values))}`",
        f"- 推荐最低完成信号数：`{args.min_completed}`",
        "",
        "说明：本脚本以中位单笔收益为第一排序目标，再看收益因子、平均收益、胜率和样本量。结果用于判断普通信号是否更接近不亏，不直接代表账户资金曲线。",
        "",
        "## 当前最佳结果",
        "",
        f"下面结果已应用最低完成信号数约束：`{args.min_completed}`。",
        "",
        f"- 建议口径：`Top{best['top_k']}`",
        f"- 额外买入过滤：`{best['extra_buy_condition'] or '不加过滤'}`",
        f"- 卖出条件：`{best['sell_condition']}`",
        f"- 完成信号数：`{best['completed_signal_count']}`",
        f"- 中位单笔收益：`{_format_pct(best['median_trade_return'])}`",
        f"- 平均单笔收益：`{_format_pct(best['avg_trade_return'])}`",
        f"- 胜率：`{_format_pct(best['win_rate'])}`",
        f"- 收益因子：`{best['profit_factor']:.2f}`",
        f"- 最大回撤：`{_format_pct(best['max_drawdown'])}`",
        f"- 盈利年份：`{best['profitable_years']}/{best['year_count']}`",
        "",
        "## 前20名结果",
        "",
        "下表按原始中位收益排序，可能包含样本很少的组合；正式采用前请重点看完成信号数。",
        "",
        "| 排名 | TopK | 买入过滤 | 卖出条件 | 完成信号 | 中位收益 | 平均收益 | 胜率 | 收益因子 | 最大回撤 |",
        "| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for idx, row in enumerate(top_rows, start=1):
        lines.append(
            "| "
            f"{idx} | Top{row['top_k']} | {row['filter_label']} | {row['sell_label']} | "
            f"{row['completed_signal_count']} | {_format_pct(row['median_trade_return'])} | "
            f"{_format_pct(row['avg_trade_return'])} | {_format_pct(row['win_rate'])} | "
            f"{row['profit_factor']:.2f} | {_format_pct(row['max_drawdown'])} |"
        )

    lines.extend(
        [
            "",
            "## 卖出条件对比",
            "",
            "| 卖出条件 | 最佳TopK | 最佳买入过滤 | 完成信号 | 中位收益 | 平均收益 | 胜率 | 收益因子 |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in sell_case_rows:
        lines.append(
            "| "
            f"{row['sell_label']} | Top{row['top_k']} | {row['filter_label']} | "
            f"{row['completed_signal_count']} | {_format_pct(row['median_trade_return'])} | "
            f"{_format_pct(row['avg_trade_return'])} | {_format_pct(row['win_rate'])} | "
            f"{row['profit_factor']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## 输出文件",
            "",
            "- `中位收益优化结果.csv`：全部过滤条件、卖出条件和 TopK 的扫描结果",
            "- `最佳组合信号明细.csv`：最佳组合下已完成信号的逐笔明细，包含买入日期、卖出日期、股票代码、股票名称、执行价、费用、收益率和关键指标",
            "- `扫描配置.json`：本次扫描参数",
            "",
            "## 使用提醒",
            "",
            "- 如果最佳结果的中位收益仍小于 0，说明当前动量候选池里的普通信号仍偏弱，下一步应继续收紧买入过滤或调整评分表达式。",
            "- 如果中位收益刚好转正但完成信号数明显下降，需要再用实盘账户回测确认资金利用率和可执行性。",
            f"- 本次输出目录：`{out_dir.as_posix()}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="围绕信号质量回测扫描让中位单笔收益更接近转正的条件")
    parser.add_argument("--processed-dir", default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--buy-condition", default=DEFAULT_BUY_CONDITION)
    parser.add_argument("--sell-condition", default=DEFAULT_SELL_CONDITION)
    parser.add_argument("--score-expression", default=DEFAULT_SCORE_EXPRESSION)
    parser.add_argument("--pool-top-n", type=int, default=20, help="每个卖出条件先取多少名候选进入复用池")
    parser.add_argument("--top-k-values", default="1,2,3,5,10,20")
    parser.add_argument("--min-completed", type=int, default=200)
    parser.add_argument("--sell-scope", choices=("all", "current"), default="all", help="是否只扫描当前卖出条件")
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else _timestamp_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    filter_cases = _build_filter_cases()
    sell_cases = _build_sell_cases(args.sell_condition)
    if args.sell_scope == "current":
        sell_cases = sell_cases[:1]
    top_k_values = _parse_ints(args.top_k_values)

    all_results: list[dict[str, Any]] = []
    selected_by_case: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for sell_idx, sell_case in enumerate(sell_cases, start=1):
        print(f"[{sell_idx}/{len(sell_cases)}] 构建候选池：{sell_case.label} -> {sell_case.condition}")
        req = SignalQualityRequest(
            processed_dir=args.processed_dir,
            start_date=args.start_date,
            end_date=args.end_date,
            buy_condition=args.buy_condition,
            sell_condition=sell_case.condition,
            score_expression=args.score_expression,
            top_n=args.pool_top_n,
            entry_offset=1,
            exit_offset=5,
            min_hold_days=3,
            max_hold_days=15,
            settlement_mode="cutoff",
            realistic_execution=True,
            buy_fee_rate=0.00003,
            sell_fee_rate=0.00003,
            stamp_tax_sell=0.0,
            slippage_bps=3,
        )
        result = run_signal_quality(req)
        signal_dates = [str(row["trade_date"]) for row in result["daily_rows"]]
        rows, selected_lookup = _scan_pool(
            pool_rows=result["pick_rows"],
            signal_dates=signal_dates,
            filter_cases=filter_cases,
            sell_case=sell_case,
            top_k_values=top_k_values,
        )
        all_results.extend(rows)
        for (filter_name, top_k), selected_rows in selected_lookup.items():
            selected_by_case[(sell_case.name, filter_name, top_k)] = selected_rows

    result_df = pd.DataFrame(all_results).sort_values(
        by=["median_trade_return", "profit_factor", "avg_trade_return", "win_rate", "completed_signal_count"],
        ascending=[False, False, False, False, False],
    )
    result_df.to_csv(out_dir / "中位收益优化结果.csv", index=False, encoding="utf-8-sig")

    best = _best_row(all_results, min_completed=args.min_completed)
    best_selected = selected_by_case[(best["sell_case"], best["filter_case"], int(best["top_k"]))]
    _write_best_records(out_dir, best, best_selected)

    sell_case_best_rows = [
        _best_row([row for row in all_results if row["sell_case"] == sell_case.name], min_completed=args.min_completed)
        for sell_case in sell_cases
    ]
    config = {
        "processed_dir": args.processed_dir,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "buy_condition": args.buy_condition,
        "sell_condition": args.sell_condition,
        "score_expression": args.score_expression,
        "pool_top_n": args.pool_top_n,
        "top_k_values": top_k_values,
        "min_completed": args.min_completed,
        "sell_scope": args.sell_scope,
        "filter_cases": [case.__dict__ for case in filter_cases],
        "sell_cases": [case.__dict__ for case in sell_cases],
        "best": best,
    }
    (out_dir / "扫描配置.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = _render_summary(
        out_dir=out_dir,
        args=args,
        best=best,
        top_rows=result_df.head(20).to_dict("records"),
        sell_case_rows=sell_case_best_rows,
    )
    (out_dir / "中位收益优化总结.md").write_text(summary, encoding="utf-8")
    print(f"最佳结果：Top{best['top_k']}，中位收益 {_format_pct(best['median_trade_return'])}，输出 {out_dir}")


if __name__ == "__main__":
    main()
