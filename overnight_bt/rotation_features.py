from __future__ import annotations


ROTATION_NUMERIC_COLUMNS = frozenset(
    {
        "rotation_top_score",
        "rotation_top_rank_pct",
        "rotation_top_gap",
        "rotation_top_m5",
        "rotation_top_m20",
        "rotation_top_m60",
        "rotation_top_theme_m20",
        "rotation_top_theme_score_chg_5",
        "rotation_top_theme_score_chg_20",
        "rotation_top_theme_rank_pct_chg_5",
        "rotation_top_theme_run_days",
        "rotation_top_cluster_run_days",
        "rotation_strong_theme_count",
        "rotation_theme_score_dispersion",
        "rotation_is_new_start",
        "rotation_is_main_decline",
        "rotation_is_watch",
        "rotation_is_main_extend",
        "rotation_is_no_clear",
        "rotation_is_favorable_state",
        "rotation_is_not_new_start",
        "rotation_top_cluster_tech",
        "rotation_top_cluster_new_energy",
        "rotation_top_cluster_medical",
        "stock_matches_rotation_top_theme",
        "stock_matches_rotation_top_cluster",
    }
)

ROTATION_CATEGORICAL_COLUMNS = frozenset(
    {
        "rotation_state",
        "rotation_top_theme",
        "rotation_top_cluster",
        "rotation_second_theme",
        "rotation_top_cluster_by_score",
        "stock_theme_cluster",
    }
)

THEME_CLUSTER_MAP = {
    "AI": "科技成长",
    "半导体芯片": "科技成长",
    "存储芯片": "科技成长",
    "机器人": "科技成长",
    "光伏新能源": "新能源",
    "锂矿锂电": "新能源",
    "医药": "医药防御",
}
