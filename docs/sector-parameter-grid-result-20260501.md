# 板块参数网格探索结果记录（2026-05-01）

本文记录 2026-05-01 在腾讯云 `/home/ubuntu/T_0_system` 上完成的板块参数网格探索结果，用于后续决定是否把板块增强参数接入模拟账户或扩大回测。

## 1. 运行命令

```bash
cd /home/ubuntu/T_0_system
source /home/ubuntu/TencentCloud/myenv/bin/activate

python scripts/run_sector_parameter_grid.py \
  --start-date 20230101 \
  --end-date 20260429 \
  --score-thresholds 0.4,0.5,0.6 \
  --rank-pcts 0.3,0.5,0.7 \
  --score-weights 10,20,30 \
  --out-dir research_runs/20260501_142052_sector_parameter_grid
```

## 2. 数据来源

| 数据 | 路径 | 说明 |
| --- | --- | --- |
| 基准处理后股票 | `data_bundle/processed_qfq_theme_focus_top100` | 主题前 100 股票处理后日线，不包含 `sector_*` 字段 |
| 板块增强股票 | `data_bundle/processed_qfq_theme_focus_top100_sector` | 在基准目录副本上合并板块研究字段 |
| 板块增强校验清单 | `data_bundle/processed_qfq_theme_focus_top100_sector/sector_feature_manifest.csv` | 用于确认增强目录不是误用基准目录 |

脚本只读取既有 CSV，不重新抓取 AKShare 或 Tushare 数据。

## 3. 输出文件

| 文件 | 路径 |
| --- | --- |
| 汇总表 | `research_runs/20260501_142052_sector_parameter_grid/sector_parameter_grid_summary.csv` |
| 交易流水 | `research_runs/20260501_142052_sector_parameter_grid/sector_parameter_grid_trade_records.csv` |
| 参数配置 | `research_runs/20260501_142052_sector_parameter_grid/sector_parameter_grid_config.json` |
| 自动报告 | `research_runs/20260501_142052_sector_parameter_grid/sector_parameter_grid_report.md` |
| 运行日志 | `research_runs/20260501_142052_sector_parameter_grid.log` |

`research_runs/` 是实验产物目录，当前不纳入 Git；交付时以服务器路径保留完整交易流水。

## 4. 参数网格

本次共跑 13 组：

| 家族 | 组合数量 | 参数 |
| --- | ---: | --- |
| `baseline` | 1 | 基准动量，不使用板块字段 |
| `hard_filter` | 9 | `sector_strongest_theme_score` 为 `0.4/0.5/0.6`，`sector_strongest_theme_rank_pct` 为 `0.3/0.5/0.7` |
| `score_only` | 3 | 板块评分权重为 `10/20/30` |

默认基础买入条件：

```text
m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02
```

默认卖出条件：

```text
m20<0.08,hs300_m20<0.02
```

## 5. 结果摘要

| 排名 | 策略 | 家族 | 账户收益 | 年化收益 | 最大回撤 | 买入次数 | 胜率 | 信号中位收益 | 结论 |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `硬过滤_score0.4_rank0.7` | `hard_filter` | 87.29% | 21.76% | 11.30% | 212 | 52.17% | -0.04% | 收益高于基准，但信号中位收益略负，需要进一步分年度和近一年复核 |
| 2 | `基准动量` | `baseline` | 75.86% | 19.38% | 11.90% | 238 | 51.50% | 0.28% | 基准仍然稳健，信号中位收益为正 |
| 3 | `硬过滤_score0.4_rank0.3` | `hard_filter` | 74.07% | 19.00% | 11.12% | 211 | 51.44% | -0.55% | 收益接近基准，回撤略低，但信号中位收益偏弱 |
| 4 | `只评分_weight10` | `score_only` | 68.92% | 17.88% | 12.41% | 215 | 50.48% | 0.12% | 低于基准且回撤略高，不宜优先接入 |
| 5 | `只评分_weight20` | `score_only` | 68.07% | 17.70% | 12.06% | 215 | 49.05% | -0.07% | 低于基准 |
| 6 | `硬过滤_score0.4_rank0.5` | `hard_filter` | 68.59% | 17.81% | 12.14% | 209 | 48.78% | -0.23% | 低于基准 |
| 7 | `只评分_weight30` | `score_only` | 68.00% | 17.68% | 12.61% | 216 | 48.34% | -0.07% | 低于基准 |
| 8 | `硬过滤_score0.5_rank0.7` | `hard_filter` | 66.26% | 17.30% | 11.18% | 159 | 50.64% | -0.44% | 交易次数明显减少，未超过基准 |

## 6. 初步判断

1. 本次唯一明显超过基准的是 `硬过滤_score0.4_rank0.7`：收益提高约 11.43 个百分点，回撤略低，交易次数从 238 降到 212。
2. 该组合的 `signal_median_trade_return=-0.04%`，说明账户收益可能来自少数较大的盈利交易，不能直接替换当前基准。
3. `score_only` 三组全部低于基准，暂时不建议把板块强度直接加进排序表达式作为主策略。
4. 更严格的 `score>=0.5/0.6` 会明显降低交易次数，多数组合收益下降，说明当前主题强度过滤不宜设得太硬。

## 7. 下一步建议

先把 `硬过滤_score0.4_rank0.7` 作为候选策略继续验证，不直接进入正式模拟账户主账号。下一步应做：

1. 对 `基准动量` 和 `硬过滤_score0.4_rank0.7` 做分年度、最近一年、牛熊阶段对比。
2. 从 `sector_parameter_grid_trade_records.csv` 抽取这两组的买卖流水，检查收益是否集中在少数股票或少数日期。
3. 如果近一年表现也优于基准，再新增一个独立模拟账户模板，只跑候选板块过滤策略，与当前基准模拟账户并行观察。
