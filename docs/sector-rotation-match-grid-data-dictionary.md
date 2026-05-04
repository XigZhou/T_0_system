# 股票匹配主线轮动 TopN 网格数据说明

本文档说明 `scripts/run_sector_rotation_match_grid.py` 生成的研究数据。该脚本用于验证“股票是否匹配当日主线”这种股票差异化轮动字段，是否能真正改变 TopN 入选股票，并改善板块候选策略。

## 1. 数据概览

| 数据名称 | 输出文件路径 | 数据粒度 | 主键字段 | 更新时间 | 用途 |
| --- | --- | --- | --- | --- | --- |
| 轮动匹配网格汇总 | `research_runs/*_sector_rotation_match_grid/sector_rotation_match_grid_summary.csv` | 每组策略一行 | `case` | 每次运行生成 | 比较收益、回撤、买入次数、信号质量和 TopN 重合率 |
| 轮动匹配交易流水 | `research_runs/*_sector_rotation_match_grid/sector_rotation_match_grid_trade_records.csv` | 每组策略每笔账户流水一行 | `case` + `trade_date` + `symbol` + `action` | 每完成一个组合更新 | 复核买入、卖出、费用和盈亏 |
| 轮动匹配入选记录 | `research_runs/*_sector_rotation_match_grid/sector_rotation_match_grid_pick_records.csv` | 每组策略每个信号日入选股票一行 | `case` + `signal_date` + `symbol` | 每完成一个组合更新 | 直接检查 TopN 是否被轮动匹配字段改变 |
| 运行配置 | `research_runs/*_sector_rotation_match_grid/sector_rotation_match_grid_config.json` | 每次运行一份 | `created_at` | 每次运行开始生成 | 记录 CLI 参数和展开后的策略组合 |
| 自动报告 | `research_runs/*_sector_rotation_match_grid/sector_rotation_match_grid_report.md` | 每次运行一份 | 无 | 每次运行结束生成 | 中文 Top 结果和输出路径 |

`research_runs/` 默认不入库，因此正式结论需要同步写入 `docs/sector-rotation-match-grid-result-YYYYMMDD.md`。

## 2. 数据来源

| 输入 | 默认路径 | 来源脚本 | 说明 |
| --- | --- | --- | --- |
| 基准处理后股票目录 | `data_bundle/processed_qfq_theme_focus_top100` | `scripts/build_theme_focus_universe.py` | 主题前 100 股票处理后日线 |
| 板块增强股票目录 | `data_bundle/processed_qfq_theme_focus_top100_sector` | `scripts/build_sector_research_features.py` | 在基准日线上追加 `sector_*` 字段 |
| 轮动日频文件 | `research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv` | `scripts/run_sector_rotation_diagnosis.py` | 每日 Top1 主题、主题簇和轮动状态 |

脚本只读取已有 CSV，不抓取 AKShare 或 Tushare，不写回输入目录。轮动字段在内存中合并到板块增强股票数据。

## 3. 策略家族

| family | 定义 |
| --- | --- |
| `baseline` | 基准动量，不使用板块或轮动字段 |
| `sector_candidate` | 当前主候选：基础动量 + `sector_exposure_score>0` + `sector_strongest_theme_score>=0.4` + `sector_strongest_theme_rank_pct<=0.7` |
| `rotation_cluster_guard` | 在主候选基础上避开某类市场主线，例如新能源 |
| `rotation_match_filter` | 在主候选基础上硬要求股票匹配当日 Top1 主题或主题簇 |
| `rotation_match_score` | 不硬过滤，把股票是否匹配主线加入 TopN 评分 |

## 4. 关键字段

| 字段名 | 中文含义 | 类型/单位 | 示例 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `rotation_top_theme` | 当日 Top1 主题 | 文本 | `AI` | 缺失时匹配字段为 0 | 来自轮动诊断 |
| `rotation_top_cluster` | 当日 Top1 主题簇 | 文本 | `科技成长` | 缺失时匹配字段为 0 | 主题簇包括科技成长、新能源、医药防御 |
| `rotation_state` | 当日轮动状态 | 文本 | `新主线启动` | 缺失时条件不满足 | 来自轮动诊断分类 |
| `rotation_is_new_start` | 是否新主线启动 | 0/1 | `1` | 缺失按 0 或条件不满足 | 用于新主线不匹配惩罚 |
| `stock_theme_cluster` | 股票最强主题所属主题簇 | 文本 | `科技成长` | 缺失为空 | 由 `sector_strongest_theme` 映射得到 |
| `stock_matches_rotation_top_theme` | 股票最强主题是否等于当日 Top1 主题 | 0/1 | `1` | 缺失为 0 | 股票差异化字段，会改变同日 TopN |
| `stock_matches_rotation_top_cluster` | 股票主题簇是否等于当日 Top1 主题簇 | 0/1 | `1` | 缺失为 0 | 股票差异化字段，会改变同日 TopN |
| `pick_overlap_rate_vs_sector_candidate` | 与主候选 TopN 入选记录重合率 | 小数 | `0.83` | 主候选无记录时为空 | 越低说明轮动匹配越改变 TopN |
| `pick_changed_count_vs_sector_candidate` | 与主候选 TopN 入选记录的对称差数量 | 整数 | `42` | 主候选无记录时为空 | 用于检查排序变化幅度 |

## 5. 评分表达式

主候选基础条件：

```text
m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02,
sector_exposure_score>0,
sector_strongest_theme_score>=0.4,
sector_strongest_theme_rank_pct<=0.7
```

主线簇匹配加权：

```text
基础评分 + stock_matches_rotation_top_cluster * 权重
```

Top 主题匹配加权：

```text
基础评分 + stock_matches_rotation_top_theme * 权重
```

组合加权：

```text
基础评分
+ stock_matches_rotation_top_cluster * cluster_weight
+ stock_matches_rotation_top_theme * theme_weight
```

新主线启动不匹配惩罚：

```text
基础评分
+ stock_matches_rotation_top_cluster * cluster_weight
+ stock_matches_rotation_top_theme * theme_weight
- rotation_is_new_start * (1 - stock_matches_rotation_top_cluster) * penalty
```

## 6. 使用示例

```bash
python scripts/run_sector_rotation_match_grid.py \
  --start-date 20230101 \
  --end-date 20260429 \
  --out-dir research_runs/20260504_191500_sector_rotation_match_grid \
  --cluster-weights 5,10 \
  --theme-weights 8,12 \
  --penalty-weights 5,8
```

复核 TopN 是否改变：

```bash
python - <<'PY'
import pandas as pd
summary = pd.read_csv("research_runs/20260504_191500_sector_rotation_match_grid/sector_rotation_match_grid_summary.csv")
print(summary[["case", "pick_overlap_rate_vs_sector_candidate", "account_total_return"]])
PY
```

## 7. 异常处理

- 板块增强目录缺少 `sector_feature_manifest.csv` 或必要 `sector_*` 字段时直接报错。
- 轮动日频文件缺少 `trade_date`、`top_theme`、`top_cluster`、`rotation_state` 时直接报错。
- 入选记录会补充轮动匹配字段，用于复核 TopN 改变情况；这一步只在脚本输出中发生，不修改回测引擎。
- 信号指标和评分使用前复权字段，实际买卖使用原始除权价格，成交约束沿用账户回测引擎。
