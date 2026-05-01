# 板块轮动诊断数据说明

本文档说明 `scripts/run_sector_rotation_diagnosis.py` 生成的板块轮动诊断数据。该脚本用于判断锂矿锂电、光伏新能源、半导体芯片、存储芯片、AI、机器人、医药等主题之间是否存在轮动，并把回测交易流水标记到对应轮动状态下。

## 1. 数据来源

| 输入 | 默认路径 | 来源 |
| --- | --- | --- |
| 主题强度日频数据 | `sector_research/data/processed/theme_strength_daily.csv` | `scripts/run_sector_research.py` 生成 |
| 板块增强股票目录 | `data_bundle/processed_qfq_theme_focus_top100_sector` | `scripts/build_sector_research_features.py` 生成 |
| 参数网格交易流水 | `research_runs/20260501_142052_sector_parameter_grid/sector_parameter_grid_trade_records.csv` | `scripts/run_sector_parameter_grid.py` 生成 |

脚本只读取已有 CSV，不抓取 AKShare 或 Tushare 数据，不修改回测主数据。

## 2. 主题簇定义

| 主题簇 | 包含主题 | 用途 |
| --- | --- | --- |
| 科技成长 | `AI`、`半导体芯片`、`存储芯片`、`机器人` | 观察科技链内部轮动 |
| 新能源 | `光伏新能源`、`锂矿锂电` | 观察新能源链内部轮动 |
| 医药防御 | `医药` | 作为相对独立或防御主题观察 |

## 3. 输出文件

默认输出目录：

```text
research_runs/YYYYMMDD_HHMMSS_sector_rotation_diagnosis/
```

| 文件 | 数据粒度 | 主键字段 | 说明 |
| --- | --- | --- | --- |
| `sector_rotation_daily.csv` | 每个交易日一行 | `trade_date` | 每日 Top1 主题、主题簇、轮动状态和强弱变化 |
| `sector_rotation_theme_runs.csv` | 每段连续 Top1 主题一行 | `top_theme` + `start_date` + `end_date` | 主线持续阶段统计 |
| `sector_rotation_transitions.csv` | 每个 Top1 切换路径一行 | `from_theme` + `to_theme` | 主题之间的接力次数 |
| `sector_rotation_cluster_daily.csv` | 每日每个主题簇一行 | `trade_date` + `theme_cluster` | 主题簇强度与簇排名 |
| `sector_rotation_labeled_trades.csv` | 每笔交易流水一行 | `case` + `trade_date` + `symbol` + `action` | 给交易流水打上轮动状态和股票所属主题 |
| `sector_rotation_trade_summary.csv` | 每个分组一行 | `group_type` + `case` + `group_value` | 按轮动状态、Top1 主题、主题簇、股票主题统计收益 |
| `sector_rotation_config.json` | 每次运行一份 | `created_at` | 运行参数、主题簇映射和轮动状态规则 |
| `sector_rotation_report.md` | 每次运行一份 | 无 | 中文诊断报告 |

## 4. `sector_rotation_daily.csv` 字段

| 字段 | 定义 |
| --- | --- |
| `trade_date` | 交易日 |
| `top_theme` | 当日主题强度排名第一的主题 |
| `top_cluster` | `top_theme` 所属主题簇 |
| `top_score` | Top1 主题综合分 |
| `top_rank_pct` | Top1 主题排名百分位，越小越强 |
| `top_m5`、`top_m20`、`top_m60` | Top1 主题 5/20/60 日动量 |
| `top_strongest_board` | Top1 主题下当日最强板块 |
| `second_theme` | 当日排名第二的主题 |
| `second_score` | 排名第二主题综合分 |
| `second_rank_pct` | 排名第二主题排名百分位 |
| `top_gap` | `top_score - second_score`，衡量主线领先幅度 |
| `strong_theme_count` | 当日 `theme_rank_pct <= strong_rank_pct` 的主题数量 |
| `theme_score_dispersion` | 当日所有主题分数标准差，衡量主题分化程度 |
| `top_cluster_by_score` | 按主题簇均值排序的最强主题簇 |
| `top_cluster_score` | 最强主题簇平均分 |
| `top_theme_score_chg_5` | Top1 主题较 5 个交易日前的分数变化 |
| `top_theme_score_chg_20` | Top1 主题较 20 个交易日前的分数变化 |
| `top_theme_rank_pct_chg_5` | Top1 主题较 5 个交易日前的排名百分位变化，负值代表排名改善 |
| `top_theme_m20` | Top1 主题 20 日动量 |
| `top_theme_run_days` | 当前 Top1 主题连续保持第一的交易日数 |
| `top_cluster_run_days` | 当前 Top1 主题簇连续保持第一的交易日数 |
| `rotation_state` | 轮动状态：`新主线启动`、`主线延续`、`主线退潮`、`无明确主线`、`轮动观察` |

## 5. 轮动状态规则

默认参数：

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `strong_rank_pct` | `0.33` | 排名前三分之一视为强主题 |
| `fresh_days` | `5` | Top1 连续天数不超过该值时，可判定为新启动 |
| `weak_score` | `0.35` | Top1 分数低于该值且领先幅度不足时，视为无明确主线 |
| `min_top_gap` | `0.02` | Top1 与第二名差距低于该值时，认为主线领先不明显 |

分类逻辑：

| 状态 | 规则 |
| --- | --- |
| `无明确主线` | `top_score < weak_score` 且 `top_gap < min_top_gap` |
| `新主线启动` | `top_theme_run_days <= fresh_days`，`top_rank_pct <= 0.5`，且 `top_theme_score_chg_5 > 0` |
| `主线延续` | `top_rank_pct <= strong_rank_pct`，`top_theme_run_days > fresh_days`，且 `top_theme_m20 >= 0` |
| `主线退潮` | `top_theme_score_chg_5 < -0.05`，或 `top_theme_m20 < 0` 且 `top_theme_score_chg_5 < 0` |
| `轮动观察` | 不满足上述规则的中间状态 |

这些规则只用于研究分组，不直接触发买入或卖出。

## 6. `sector_rotation_labeled_trades.csv` 字段

除原始交易流水字段外，新增：

| 字段 | 定义 |
| --- | --- |
| `signal_top_theme` | 交易信号日的 Top1 主题 |
| `signal_top_cluster` | 交易信号日的 Top1 主题簇 |
| `signal_top_score` | 交易信号日 Top1 主题分数 |
| `signal_top_rank_pct` | 交易信号日 Top1 主题排名百分位 |
| `signal_top_gap` | 交易信号日 Top1 与第二名分数差 |
| `signal_top_theme_run_days` | 信号日 Top1 主题连续天数 |
| `signal_top_cluster_run_days` | 信号日 Top1 主题簇连续天数 |
| `signal_rotation_state` | 信号日轮动状态 |
| `sector_strongest_theme` | 该股票在信号日命中的最强主题 |
| `sector_strongest_theme_score` | 该股票信号日最强主题分 |
| `sector_strongest_theme_rank_pct` | 该股票信号日最强主题排名百分位 |
| `sector_exposure_score` | 个股主题暴露分 |
| `stock_theme_cluster` | 股票最强主题所属主题簇 |
| `stock_matches_top_theme` | 股票最强主题是否等于当日 Top1 主题 |
| `stock_matches_top_cluster` | 股票最强主题簇是否等于当日 Top1 主题簇 |

## 7. 缺失值与异常处理

- 主题强度文件缺少 `trade_date`、`theme_name`、`theme_score` 或 `theme_rank_pct` 时，脚本直接报错。
- 交易流水可以为空；为空时仍生成轮动状态、主题阶段和切换统计。
- 若某只股票在板块增强目录中找不到对应 CSV，交易打标中的股票主题字段为空。
- `signal_date` 无法匹配到轮动状态时，对应 `signal_*` 字段为空，不影响其他交易。
- 所有输出只写入 `research_runs/`，不会覆盖回测主输入目录。
