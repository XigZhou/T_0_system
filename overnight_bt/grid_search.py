from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any

import pandas as pd

from .research import ResearchCase


@dataclass(frozen=True)
class GridDimension:
    key: str
    values: tuple[Any, ...]


@dataclass(frozen=True)
class GridCase:
    name: str
    family: str
    params: dict[str, Any]
    case: ResearchCase


@dataclass(frozen=True)
class GridPreset:
    name: str
    family: str
    score_expression: str
    top_n: int
    dimensions: tuple[GridDimension, ...]
    fixed_params: dict[str, Any]


def _format_decimal(value: float) -> str:
    text = f"{float(value):.4f}".rstrip("0").rstrip(".")
    return text.replace("-", "m").replace(".", "p")


def _build_buy_condition(params: dict[str, Any], fixed_params: dict[str, Any]) -> str:
    clauses: list[str] = []
    board = params.get("board")
    if board:
        clauses.append(f"board={board}")
    clauses.append(f"listed_days>{int(params['listed_days_min'])}")
    clauses.append(f"m20>{float(params['m20_min'])}")
    clauses.append("m5>0")
    clauses.append(f"pct_chg>{float(fixed_params['pct_chg_min'])}")
    clauses.append(f"pct_chg<{float(params['pct_chg_max'])}")
    clauses.append(f"close_pos_in_bar>{float(params['close_pos_in_bar_min'])}")
    clauses.append(f"upper_shadow_pct<{float(fixed_params['upper_shadow_pct_max'])}")
    clauses.append(f"body_pct>{float(fixed_params['body_pct_min'])}")
    clauses.append(f"vr<{float(fixed_params['vr_max'])}")
    clauses.append(f"hs300_pct_chg>{float(fixed_params['hs300_pct_chg_min'])}")
    return ",".join(clauses)


def build_buy_condition_grid_v1() -> tuple[list[GridCase], GridPreset]:
    preset = GridPreset(
        name="buy_condition_grid_v1",
        family="trend_close",
        score_expression="m20 * 120 + m5 * 80 + close_pos_in_bar * 5 + body_pct * 60 - upper_shadow_pct * 80 - abs(vr - 1.0) * 2",
        top_n=5,
        dimensions=(
            GridDimension("board", (None, "主板")),
            GridDimension("listed_days_min", (250, 500)),
            GridDimension("m20_min", (0.02, 0.04)),
            GridDimension("pct_chg_max", (4.0, 6.0)),
            GridDimension("close_pos_in_bar_min", (0.45, 0.60)),
        ),
        fixed_params={
            "pct_chg_min": -1.5,
            "upper_shadow_pct_max": 0.03,
            "body_pct_min": -0.01,
            "vr_max": 1.8,
            "hs300_pct_chg_min": -1.5,
        },
    )

    keys = [dim.key for dim in preset.dimensions]
    cases: list[GridCase] = []
    for values in product(*[dim.values for dim in preset.dimensions]):
        params = dict(zip(keys, values))
        board_tag = "main" if params["board"] else "all"
        name = (
            f"grid_{board_tag}"
            f"_ld{int(params['listed_days_min'])}"
            f"_m20{_format_decimal(params['m20_min'])}"
            f"_pch{_format_decimal(params['pct_chg_max'])}"
            f"_cp{_format_decimal(params['close_pos_in_bar_min'])}"
        )
        buy_condition = _build_buy_condition(params, preset.fixed_params)
        case = ResearchCase(
            name=name,
            buy_condition=buy_condition,
            score_expression=preset.score_expression,
            top_n=preset.top_n,
        )
        cases.append(
            GridCase(
                name=name,
                family=preset.family,
                params=params,
                case=case,
            )
        )
    return cases, preset


def build_buy_condition_focus_grid_v1() -> tuple[list[GridCase], GridPreset]:
    preset = GridPreset(
        name="buy_condition_focus_grid_v1",
        family="mainboard_trend_focus",
        score_expression="m20 * 140 + close_pos_in_bar * 6 + body_pct * 80 - upper_shadow_pct * 100 - abs(vr - 1.0) * 2",
        top_n=3,
        dimensions=(
            GridDimension("m20_min", (0.04, 0.06)),
            GridDimension("pct_chg_max", (4.0, 6.0)),
        ),
        fixed_params={
            "board": "主板",
            "listed_days_min": 500,
            "close_pos_in_bar_min": 0.60,
            "pct_chg_min": -1.0,
            "upper_shadow_pct_max": 0.02,
            "body_pct_min": 0.0,
            "vr_max": 1.4,
            "hs300_pct_chg_min": -1.0,
        },
    )

    keys = [dim.key for dim in preset.dimensions]
    cases: list[GridCase] = []
    for values in product(*[dim.values for dim in preset.dimensions]):
        params = dict(zip(keys, values))
        merged_params = dict(preset.fixed_params)
        merged_params.update(params)
        name = (
            "focus_main"
            f"_ld{int(merged_params['listed_days_min'])}"
            f"_m20{_format_decimal(merged_params['m20_min'])}"
            f"_pch{_format_decimal(merged_params['pct_chg_max'])}"
            f"_cp{_format_decimal(merged_params['close_pos_in_bar_min'])}"
        )
        buy_condition = _build_buy_condition(merged_params, merged_params)
        case = ResearchCase(
            name=name,
            buy_condition=buy_condition,
            score_expression=preset.score_expression,
            top_n=preset.top_n,
        )
        cases.append(
            GridCase(
                name=name,
                family=preset.family,
                params=merged_params,
                case=case,
            )
        )
    return cases, preset


def build_buy_condition_focus_grid_v2() -> tuple[list[GridCase], GridPreset]:
    preset = GridPreset(
        name="buy_condition_focus_grid_v2",
        family="mainboard_trend_fine",
        score_expression="m20 * 150 + close_pos_in_bar * 6 + body_pct * 90 - upper_shadow_pct * 120 - abs(vr - 1.0) * 3",
        top_n=3,
        dimensions=(
            GridDimension("m20_min", (0.035, 0.045)),
            GridDimension("pct_chg_max", (3.5, 4.5)),
            GridDimension("close_pos_in_bar_min", (0.55, 0.65)),
            GridDimension("vr_max", (1.2, 1.6)),
        ),
        fixed_params={
            "board": "主板",
            "listed_days_min": 500,
            "pct_chg_min": -1.0,
            "upper_shadow_pct_max": 0.02,
            "body_pct_min": 0.0,
            "hs300_pct_chg_min": -1.0,
        },
    )

    keys = [dim.key for dim in preset.dimensions]
    cases: list[GridCase] = []
    for values in product(*[dim.values for dim in preset.dimensions]):
        params = dict(zip(keys, values))
        merged_params = dict(preset.fixed_params)
        merged_params.update(params)
        name = (
            "fine_main"
            f"_ld{int(merged_params['listed_days_min'])}"
            f"_m20{_format_decimal(merged_params['m20_min'])}"
            f"_pch{_format_decimal(merged_params['pct_chg_max'])}"
            f"_cp{_format_decimal(merged_params['close_pos_in_bar_min'])}"
            f"_vr{_format_decimal(merged_params['vr_max'])}"
        )
        buy_condition = _build_buy_condition(merged_params, merged_params)
        case = ResearchCase(
            name=name,
            buy_condition=buy_condition,
            score_expression=preset.score_expression,
            top_n=preset.top_n,
        )
        cases.append(
            GridCase(
                name=name,
                family=preset.family,
                params=merged_params,
                case=case,
            )
        )
    return cases, preset


def build_buy_condition_topm_grid_v1() -> tuple[list[GridCase], GridPreset]:
    preset = GridPreset(
        name="buy_condition_topm_grid_v1",
        family="mainboard_trend_topm",
        score_expression="m20 * 150 + close_pos_in_bar * 6 + body_pct * 90 - upper_shadow_pct * 120 - abs(vr - 1.0) * 3",
        top_n=3,
        dimensions=(
            GridDimension("top_n", (1, 2, 3, 5)),
        ),
        fixed_params={
            "board": "主板",
            "listed_days_min": 500,
            "m20_min": 0.035,
            "pct_chg_min": -1.0,
            "pct_chg_max": 3.5,
            "close_pos_in_bar_min": 0.65,
            "upper_shadow_pct_max": 0.02,
            "body_pct_min": 0.0,
            "vr_max": 1.6,
            "hs300_pct_chg_min": -1.0,
        },
    )

    cases: list[GridCase] = []
    for top_n in preset.dimensions[0].values:
        merged_params = dict(preset.fixed_params)
        merged_params["top_n"] = int(top_n)
        name = (
            "topm_main"
            f"_m{int(top_n)}"
            f"_m20{_format_decimal(merged_params['m20_min'])}"
            f"_pch{_format_decimal(merged_params['pct_chg_max'])}"
            f"_cp{_format_decimal(merged_params['close_pos_in_bar_min'])}"
            f"_vr{_format_decimal(merged_params['vr_max'])}"
        )
        buy_condition = _build_buy_condition(merged_params, merged_params)
        case = ResearchCase(
            name=name,
            buy_condition=buy_condition,
            score_expression=preset.score_expression,
            top_n=int(top_n),
        )
        cases.append(
            GridCase(
                name=name,
                family=preset.family,
                params=merged_params,
                case=case,
            )
        )
    return cases, preset


def _build_rank_focus_grid(
    preset_name: str,
    family: str,
    top_n: int,
) -> tuple[list[GridCase], GridPreset]:
    preset = GridPreset(
        name=preset_name,
        family=family,
        score_expression="m20 * 155 + close_pos_in_bar * 6 + body_pct * 90 - upper_shadow_pct * 120 - abs(vr - 1.0) * 3",
        top_n=int(top_n),
        dimensions=(
            GridDimension("m20_min", (0.03, 0.035)),
            GridDimension("pct_chg_max", (3.0, 3.5)),
            GridDimension("close_pos_in_bar_min", (0.60, 0.65)),
            GridDimension("vr_max", (1.4, 1.6)),
        ),
        fixed_params={
            "board": "主板",
            "listed_days_min": 500,
            "pct_chg_min": -1.0,
            "upper_shadow_pct_max": 0.02,
            "body_pct_min": 0.0,
            "hs300_pct_chg_min": -1.0,
        },
    )

    keys = [dim.key for dim in preset.dimensions]
    cases: list[GridCase] = []
    for values in product(*[dim.values for dim in preset.dimensions]):
        params = dict(zip(keys, values))
        merged_params = dict(preset.fixed_params)
        merged_params.update(params)
        merged_params["top_n"] = int(top_n)
        name = (
            f"rank{int(top_n)}fine_main"
            f"_m20{_format_decimal(merged_params['m20_min'])}"
            f"_pch{_format_decimal(merged_params['pct_chg_max'])}"
            f"_cp{_format_decimal(merged_params['close_pos_in_bar_min'])}"
            f"_vr{_format_decimal(merged_params['vr_max'])}"
        )
        buy_condition = _build_buy_condition(merged_params, merged_params)
        case = ResearchCase(
            name=name,
            buy_condition=buy_condition,
            score_expression=preset.score_expression,
            top_n=int(top_n),
        )
        cases.append(
            GridCase(
                name=name,
                family=preset.family,
                params=merged_params,
                case=case,
            )
        )
    return cases, preset


def build_buy_condition_top1_focus_grid_v1() -> tuple[list[GridCase], GridPreset]:
    return _build_rank_focus_grid(
        preset_name="buy_condition_top1_focus_grid_v1",
        family="mainboard_trend_top1_fine",
        top_n=1,
    )


def build_buy_condition_top2_focus_grid_v1() -> tuple[list[GridCase], GridPreset]:
    return _build_rank_focus_grid(
        preset_name="buy_condition_top2_focus_grid_v1",
        family="mainboard_trend_top2_fine",
        top_n=2,
    )


def build_grid_cases(preset: str = "buy_condition_grid_v1") -> tuple[list[GridCase], GridPreset]:
    if preset == "buy_condition_grid_v1":
        return build_buy_condition_grid_v1()
    if preset == "buy_condition_focus_grid_v1":
        return build_buy_condition_focus_grid_v1()
    if preset == "buy_condition_focus_grid_v2":
        return build_buy_condition_focus_grid_v2()
    if preset == "buy_condition_topm_grid_v1":
        return build_buy_condition_topm_grid_v1()
    if preset == "buy_condition_top1_focus_grid_v1":
        return build_buy_condition_top1_focus_grid_v1()
    if preset == "buy_condition_top2_focus_grid_v1":
        return build_buy_condition_top2_focus_grid_v1()
    raise ValueError(f"unsupported grid preset: {preset}")


def add_stability_columns(frame: pd.DataFrame, suffix: str = "") -> pd.DataFrame:
    work = frame.copy()

    def _col(name: str) -> str:
        return f"{name}{suffix}"

    for col in [
        _col("annualized_return"),
        _col("positive_month_ratio"),
        _col("win_rate"),
        _col("max_drawdown"),
        _col("sell_count"),
        _col("active_day_ratio"),
        _col("median_trade_return"),
    ]:
        if col not in work.columns:
            work[col] = 0.0
        work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0.0)

    annualized = work[_col("annualized_return")].clip(lower=-0.5, upper=1.0)
    positive_month_ratio = work[_col("positive_month_ratio")].clip(lower=0.0, upper=1.0)
    win_rate = work[_col("win_rate")].clip(lower=0.0, upper=1.0)
    max_drawdown = work[_col("max_drawdown")].clip(lower=0.0, upper=1.0)
    sell_count = work[_col("sell_count")].clip(lower=0.0)
    active_day_ratio = work[_col("active_day_ratio")].clip(lower=0.0, upper=1.0)
    median_trade_return = work[_col("median_trade_return")].clip(lower=-0.05, upper=0.05)

    work[f"stability_score{suffix}"] = (
        positive_month_ratio * 40.0
        + win_rate * 15.0
        + active_day_ratio * 10.0
        + annualized * 30.0
        + median_trade_return * 100.0
        + sell_count.clip(upper=200.0) / 200.0 * 10.0
        - max_drawdown * 25.0
    ).round(6)

    work[f"stable_pass{suffix}"] = (
        (work[_col("annualized_return")] > 0)
        & (work[_col("positive_month_ratio")] >= 0.55)
        & (work[_col("max_drawdown")] <= 0.25)
        & (work[_col("sell_count")] >= 80)
        & (work[_col("active_day_ratio")] >= 0.08)
    )
    return work
