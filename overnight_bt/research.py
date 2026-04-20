from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ResearchCase:
    name: str
    buy_condition: str
    score_expression: str
    top_n: int


def _baseline_case() -> ResearchCase:
    return ResearchCase(
        name="baseline",
        buy_condition="pct_chg>2.0,m5>0.05,amp<0.04,vr<1.5,hs300_pct_chg>-0.5",
        score_expression="pct_chg + m5 * 100 - amp * 100 - abs(vr - 1.0) * 2",
        top_n=5,
    )


def _overnight_v2_cases() -> list[ResearchCase]:
    score = "close_pos_in_bar * 10 + body_pct * 100 - upper_shadow_pct * 100 - abs(close_to_up_limit - 0.975) * 50"
    return [
        ResearchCase(
            "overnight_limit_buffer",
            "listed_days>250,close_to_up_limit<0.985,close_pos_in_bar>0.60,upper_shadow_pct<0.02,body_pct>0.005,vol_ratio_5<1.8,hs300_pct_chg>-1.0",
            score,
            5,
        ),
        ResearchCase(
            "overnight_strong_close",
            "listed_days>250,m20>0,close_pos_in_bar>0.70,body_pct>0.01,upper_shadow_pct<0.015,close_to_up_limit<0.99,vol_ratio_5<1.6",
            score,
            5,
        ),
        ResearchCase(
            "overnight_trend_pullback",
            "listed_days>250,m20>0.03,m5>0,pct_chg>0.5,pct_chg<4.0,close_pos_in_bar>0.45,close_to_up_limit<0.985,vol_ratio_5<1.8",
            score,
            5,
        ),
        ResearchCase(
            "overnight_mainboard_body",
            "board=主板,listed_days>250,body_pct>0,upper_shadow_pct<0.01,lower_shadow_pct<0.03,close_pos_in_bar>0.55,close_to_up_limit<0.985",
            score,
            5,
        ),
        ResearchCase(
            "overnight_turnover_guard",
            "listed_days>250,turnover_rate_snapshot<3,close_pos_in_bar>0.55,body_pct>0.003,upper_shadow_pct<0.02,close_to_up_limit<0.985,vol_ratio_5<1.5",
            score,
            5,
        ),
    ]


def _overnight_v3_cases() -> list[ResearchCase]:
    score = (
        "body_pct * 100 + close_pos_in_bar * 5 "
        "- upper_shadow_pct * 100 "
        "- abs(close_to_up_limit - 0.985) * 200 "
        "- abs(high_to_up_limit - 0.99) * 100 "
        "- abs(vol_ratio_5 - 0.9) * 5"
    )
    return [
        ResearchCase(
            "v3_buffer_mid",
            "listed_days>250,0.96<=close_to_up_limit<=0.995,body_pct>0.02,upper_shadow_pct<0.02,lower_shadow_pct<0.03,vol_ratio_5<=1.0",
            score,
            2,
        ),
        ResearchCase(
            "v3_buffer_strong",
            "listed_days>250,0.96<=close_to_up_limit<=0.995,body_pct>0.03,upper_shadow_pct<0.02,lower_shadow_pct<0.03,vol_ratio_5<=1.0",
            score,
            2,
        ),
        ResearchCase(
            "v3_near_limit",
            "listed_days>250,0.97<=close_to_up_limit<=0.995,body_pct>0.015,upper_shadow_pct<0.02,lower_shadow_pct<0.03,vol_ratio_5<=1.2",
            score,
            2,
        ),
        ResearchCase(
            "v3_high_touch",
            "listed_days>250,high_to_up_limit>=0.98,close_to_up_limit<=0.995,body_pct>0.015,upper_shadow_pct<0.02,lower_shadow_pct<0.03,vol_ratio_5<=1.2",
            score,
            2,
        ),
        ResearchCase(
            "v3_broad_buffer",
            "listed_days>250,0.95<=close_to_up_limit<=0.995,body_pct>0.02,upper_shadow_pct<0.02,lower_shadow_pct<0.03,vol_ratio_5<=1.0",
            score,
            2,
        ),
    ]


def _overnight_v4_cases() -> list[ResearchCase]:
    score = (
        "body_pct_3avg * 100 + body_pct * 50 + close_pos_in_bar * 5 "
        "- abs(ret_accel_3) * 50 "
        "- abs(vol_ratio_3 - 1.0) * 10 "
        "- abs(amount_ratio_3 - 1.0) * 5 "
        "- abs(close_to_up_limit_3max - 0.99) * 100"
    )
    return [
        ResearchCase(
            "v4_core_tight",
            "listed_days>250,0.96<=close_to_up_limit<=0.995,body_pct>0.03,upper_shadow_pct<0.02,lower_shadow_pct<0.03,vol_ratio_5<=1.0,vol_ratio_3<=1.1,amount_ratio_3<=1.1,ret_accel_3>-0.015",
            score,
            2,
        ),
        ResearchCase(
            "v4_core_mid",
            "listed_days>250,0.96<=close_to_up_limit<=0.995,body_pct>0.025,upper_shadow_pct<0.02,lower_shadow_pct<0.03,vol_ratio_5<=1.0,vol_ratio_3<=1.1,amount_ratio_3<=1.15,ret_accel_3>-0.02",
            score,
            2,
        ),
        ResearchCase(
            "v4_body_avg",
            "listed_days>250,0.96<=close_to_up_limit<=0.995,body_pct>0.02,body_pct_3avg>0.012,upper_shadow_pct<0.02,lower_shadow_pct<0.03,vol_ratio_5<=1.0,vol_ratio_3<=1.1",
            score,
            2,
        ),
        ResearchCase(
            "v4_near_limit_memory",
            "listed_days>250,0.96<=close_to_up_limit<=0.995,close_to_up_limit_3max>=0.98,body_pct>0.025,upper_shadow_pct<0.02,lower_shadow_pct<0.03,vol_ratio_5<=1.0,ret_accel_3>-0.02",
            score,
            2,
        ),
        ResearchCase(
            "v4_soft_accel",
            "listed_days>250,0.96<=close_to_up_limit<=0.995,body_pct>0.03,upper_shadow_pct<0.02,lower_shadow_pct<0.03,vol_ratio_5<=1.0,vol_ratio_3<=1.2,amount_ratio_3<=1.2,ret_accel_3>-0.03",
            score,
            2,
        ),
    ]


def build_neighborhood_cases(preset: str = "baseline_v1") -> list[ResearchCase]:
    if preset == "overnight_v2":
        return _overnight_v2_cases()
    if preset == "overnight_v3":
        return _overnight_v3_cases()
    if preset == "overnight_v4":
        return _overnight_v4_cases()
    if preset != "baseline_v1":
        raise ValueError(f"unsupported research preset: {preset}")
    baseline = _baseline_case()
    score = baseline.score_expression
    cases = [
        baseline,
        ResearchCase("pct_chg_1p5", "pct_chg>1.5,m5>0.05,amp<0.04,vr<1.5,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("pct_chg_2p5", "pct_chg>2.5,m5>0.05,amp<0.04,vr<1.5,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("m5_0p02", "pct_chg>2.0,m5>0.02,amp<0.04,vr<1.5,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("m5_0p08", "pct_chg>2.0,m5>0.08,amp<0.04,vr<1.5,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("amp_0p03", "pct_chg>2.0,m5>0.05,amp<0.03,vr<1.5,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("amp_0p05", "pct_chg>2.0,m5>0.05,amp<0.05,vr<1.5,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("vr_1p2", "pct_chg>2.0,m5>0.05,amp<0.04,vr<1.2,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("vr_1p8", "pct_chg>2.0,m5>0.05,amp<0.04,vr<1.8,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("hs300_-1p0", "pct_chg>2.0,m5>0.05,amp<0.04,vr<1.5,hs300_pct_chg>-1.0", score, 5),
        ResearchCase("hs300_0p0", "pct_chg>2.0,m5>0.05,amp<0.04,vr<1.5,hs300_pct_chg>0.0", score, 5),
        ResearchCase("board_main", "board=主板,pct_chg>2.0,m5>0.05,amp<0.04,vr<1.5,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("board_ex_star", "board!=科创板,pct_chg>2.0,m5>0.05,amp<0.04,vr<1.5,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("listed_120", "listed_days>120,pct_chg>2.0,m5>0.05,amp<0.04,vr<1.5,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("listed_250", "listed_days>250,pct_chg>2.0,m5>0.05,amp<0.04,vr<1.5,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("listed_500", "listed_days>500,pct_chg>2.0,m5>0.05,amp<0.04,vr<1.5,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("turnover_2", "turnover_rate_snapshot<2,pct_chg>2.0,m5>0.05,amp<0.04,vr<1.5,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("turnover_3", "turnover_rate_snapshot<3,pct_chg>2.0,m5>0.05,amp<0.04,vr<1.5,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("mv_800", "total_mv_snapshot>8000000,pct_chg>2.0,m5>0.05,amp<0.04,vr<1.5,hs300_pct_chg>-0.5", score, 5),
        ResearchCase("topn_3", baseline.buy_condition, score, 3),
        ResearchCase("topn_8", baseline.buy_condition, score, 8),
        ResearchCase(
            "board_main_listed_250",
            "board=主板,listed_days>250,pct_chg>2.0,m5>0.05,amp<0.04,vr<1.5,hs300_pct_chg>-0.5",
            score,
            5,
        ),
    ]
    return cases


def summarize_case_result(
    case_name: str,
    period: str,
    buy_condition: str,
    score_expression: str,
    top_n: int,
    result: dict[str, Any],
) -> dict[str, Any]:
    summary = dict(result["summary"])
    diagnostics = dict(result.get("diagnostics", {}))
    daily = pd.DataFrame(result.get("daily_rows", []))
    positive_month_ratio = 0.0
    positive_months = 0
    months = 0
    avg_picked_count = 0.0
    if not daily.empty:
        daily["trade_date"] = daily["trade_date"].astype(str)
        daily["equity"] = pd.to_numeric(daily["equity"], errors="coerce")
        daily["candidate_count"] = pd.to_numeric(daily.get("candidate_count"), errors="coerce").fillna(0)
        daily["picked_count"] = pd.to_numeric(daily.get("picked_count"), errors="coerce").fillna(0)
        daily["month"] = daily["trade_date"].str[:6]
        monthly = daily.groupby("month").agg(start_equity=("equity", "first"), end_equity=("equity", "last")).reset_index()
        monthly["month_return"] = monthly["end_equity"] / monthly["start_equity"] - 1.0
        months = int(len(monthly))
        positive_months = int((monthly["month_return"] > 0).sum())
        positive_month_ratio = float((monthly["month_return"] > 0).mean()) if months else 0.0
        avg_picked_count = float(daily["picked_count"].mean())
    trade_days = int(summary.get("trade_days", 0) or 0)
    candidate_days = int(diagnostics.get("candidate_days", 0) or 0)
    active_day_ratio = (candidate_days / trade_days) if trade_days > 0 else 0.0
    return {
        "period": period,
        "case": case_name,
        "buy_condition": buy_condition,
        "score_expression": score_expression,
        "top_n": top_n,
        "annualized_return": float(summary.get("annualized_return", 0.0) or 0.0),
        "total_return": float(summary.get("total_return", 0.0) or 0.0),
        "max_drawdown": float(summary.get("max_drawdown", 0.0) or 0.0),
        "win_rate": float(summary.get("win_rate", 0.0) or 0.0),
        "sell_count": int(summary.get("sell_count", 0) or 0),
        "buy_count": int(summary.get("buy_count", 0) or 0),
        "trade_days": trade_days,
        "candidate_days": candidate_days,
        "active_day_ratio": active_day_ratio,
        "avg_picked_count": avg_picked_count,
        "months": months,
        "positive_months": positive_months,
        "positive_month_ratio": positive_month_ratio,
    }


def select_train_top_cases(train_df: pd.DataFrame, top_k: int = 5) -> pd.DataFrame:
    eligible = train_df[
        (pd.to_numeric(train_df["sell_count"], errors="coerce") >= 200)
        & (pd.to_numeric(train_df["positive_month_ratio"], errors="coerce") >= 0.5)
        & (pd.to_numeric(train_df["active_day_ratio"], errors="coerce") >= 0.25)
    ].copy()
    if eligible.empty:
        eligible = train_df.copy()
    eligible = eligible.sort_values(
        ["annualized_return", "max_drawdown", "positive_month_ratio", "sell_count"],
        ascending=[False, True, False, False],
    )
    return eligible.head(top_k).reset_index(drop=True)
