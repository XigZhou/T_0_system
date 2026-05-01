# 板块轮动状态条件网格数据说明

本文档说明 `scripts/run_sector_rotation_grid.py` 生成的研究数据。该脚本用于验证“板块候选策略 + 轮动状态条件”是否优于基准动量和上一轮最佳板块候选。

## 1. 数据来源

| 输入 | 默认路径 | 来源 |
| --- | --- | --- |
| 基准处理后股票目录 | `data_bundle/processed_qfq_theme_focus_top100` | 主题前 100 股票处理后日线 |
| 板块增强股票目录 | `data_bundle/processed_qfq_theme_focus_top100_sector` | `scripts/build_sector_research_features.py` 生成 |
| 每日轮动状态 | `research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv` | `scripts/run_sector_rotation_diagnosis.py` 生成 |

脚本只读取既有 CSV，不重新抓取 AKShare 或 Tushare 数据。轮动字段在内存中合并到板块增强股票数据，不覆盖原处理后目录。

## 2. 默认探索策略

默认先保留上一轮最佳板块候选条件：

```text
m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02,
sector_exposure_score>0,sector_strongest_theme_score>=0.4,sector_strongest_theme_rank_pct<=0.7
```

然后叠加以下轮动条件：

| 策略 | 条件 |
| --- | --- |
| `基准动量` | 不使用 `sector_*` 或 `rotation_*` 字段 |
| `板块候选_score0.4_rank0.7` | 只使用上一轮最佳板块候选 |
| `候选_新主线启动` | `rotation_state=新主线启动` |
| `候选_主线退潮` | `rotation_state=主线退潮` |
| `候选_轮动观察` | `rotation_state=轮动观察` |
| `候选_主线延续` | `rotation_state=主线延续` |
| `候选_退潮或观察` | `rotation_is_favorable_state>0`，即主线退潮或轮动观察 |
| `候选_避开新主线启动` | `rotation_is_not_new_start>0` |
| `候选_科技成长主线` | `rotation_top_cluster=科技成长` |
| `候选_科技成长且非新启动` | 科技成长主线且不是新主线启动 |
| `候选_科技成长且股票匹配` | 科技成长主线且股票所属主题簇也为科技成长 |
| `候选_避开新能源主线` | `rotation_top_cluster!=新能源` |
| `候选_医药防御主线` | `rotation_top_cluster=医药防御` |

## 3. 轮动字段定义

| 字段 | 类型 | 定义 |
| --- | --- | --- |
| `rotation_state` | 文本 | 信号日轮动状态 |
| `rotation_top_theme` | 文本 | 信号日 Top1 主题 |
| `rotation_top_cluster` | 文本 | 信号日 Top1 主题簇 |
| `rotation_top_score` | 数值 | 信号日 Top1 主题分 |
| `rotation_top_rank_pct` | 数值 | 信号日 Top1 主题排名百分位 |
| `rotation_top_gap` | 数值 | Top1 与第二名主题分差 |
| `rotation_top_theme_run_days` | 数值 | Top1 主题连续保持第一的交易日数 |
| `rotation_top_cluster_run_days` | 数值 | Top1 主题簇连续保持第一的交易日数 |
| `rotation_is_new_start` | 数值 | 是否为新主线启动，是为 `1`，否则为 `0` |
| `rotation_is_main_decline` | 数值 | 是否为主线退潮 |
| `rotation_is_watch` | 数值 | 是否为轮动观察 |
| `rotation_is_main_extend` | 数值 | 是否为主线延续 |
| `rotation_is_favorable_state` | 数值 | 是否为主线退潮或轮动观察 |
| `rotation_is_not_new_start` | 数值 | 是否不是新主线启动 |
| `stock_theme_cluster` | 文本 | 股票信号日最强主题所属主题簇 |
| `stock_matches_rotation_top_theme` | 数值 | 股票最强主题是否等于当日 Top1 主题 |
| `stock_matches_rotation_top_cluster` | 数值 | 股票主题簇是否等于当日 Top1 主题簇 |

这些字段只用于研究条件，不直接写入原始股票 CSV。

## 4. 输出文件

默认输出目录：

```text
research_runs/YYYYMMDD_HHMMSS_sector_rotation_grid/
```

| 文件 | 数据粒度 | 主键字段 | 说明 |
| --- | --- | --- | --- |
| `sector_rotation_grid_summary.csv` | 每组策略一行 | `case` | 信号质量、账户收益、回撤、交易次数、综合排序分 |
| `sector_rotation_grid_trade_records.csv` | 每组策略每笔交易一行 | `case` + `trade_date` + `symbol` + `action` | 账户买卖流水 |
| `sector_rotation_grid_config.json` | 每次运行一份 | `created_at` | CLI 参数和展开后的策略条件 |
| `sector_rotation_grid_report.md` | 每次运行一份 | 无 | 中文总结报告 |

## 5. 缺失值与异常处理

- 轮动日频文件缺少 `trade_date`、`top_theme`、`top_cluster` 或 `rotation_state` 时直接报错。
- 板块增强目录缺少 `sector_feature_manifest.csv` 或必要 `sector_*` 字段时直接报错。
- 股票在某个信号日没有轮动状态时，叠加 `rotation_*` 条件的策略不会选中该日股票。
- 交易次数过少的组合只作为观察，不建议直接接入模拟账户。

## 6. 复权与成交口径

- 买入条件和评分表达式使用处理后股票 CSV 中的前复权指标。
- 买入和卖出成交仍使用原始除权价格。
- 手续费、滑点、整手买入、停牌和涨跌停约束沿用账户回测引擎。
