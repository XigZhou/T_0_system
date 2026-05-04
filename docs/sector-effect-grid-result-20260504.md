# 板块效应选股条件探索结果记录（2026-05-04）

本文记录“优先选择有板块效应股票”的第一轮网格实验。实验目标是判断：在当前 T+1 回测和模拟买卖口径下，板块字段更适合做买入硬过滤，还是只作为评分加权。

## 1. 运行命令

腾讯云运行目录：

```bash
cd /home/ubuntu/T_0_system
source /home/ubuntu/TencentCloud/myenv/bin/activate

python scripts/run_sector_effect_grid.py \
  --start-date 20230101 \
  --end-date 20260429 \
  --out-dir research_runs/20260504_181000_sector_effect_grid_fixed \
  --score-thresholds 0.4,0.5 \
  --rank-pcts 0.7 \
  --exposure-mins 0 \
  --theme-m20-mins any,0 \
  --amount-ratio-mins any,1.0 \
  --score-weights 5,10,15 \
  --resume
```

本次实际先跑过一轮默认 36 组大网格，发现运行时间过长，随后保留基准结果并改为 12 组聚焦网格续跑。旧的半截输出保留在 `research_runs/20260504_173000_sector_effect_grid/` 和 `research_runs/20260504_181000_sector_effect_grid_fixed/` 的日志中，正式结论以 `research_runs/20260504_181000_sector_effect_grid_fixed/` 为准。

## 2. 数据来源

| 数据 | 路径 | 来源 | 说明 |
| --- | --- | --- | --- |
| 基准处理后股票 | `data_bundle/processed_qfq_theme_focus_top100` | `scripts/build_theme_focus_universe.py` | 主题前 100 股票处理后日线 |
| 板块增强股票 | `data_bundle/processed_qfq_theme_focus_top100_sector` | `scripts/build_sector_research_features.py` | 在基准处理后日线上追加 `sector_*` 字段 |
| 上游板块研究 | `sector_research/data/processed` | `scripts/run_sector_research.py` | AKShare 东方财富行业/概念板块、历史行情、成分股、资金流加工结果 |

本脚本只读取已有 CSV，不抓取 AKShare 或 Tushare，也不覆盖处理后股票目录。

## 3. 输出文件

| 文件 | 路径 | 说明 |
| --- | --- | --- |
| 汇总表 | `research_runs/20260504_181000_sector_effect_grid_fixed/sector_effect_grid_summary.csv` | 12 组策略收益、回撤、信号质量和排序 |
| 买卖记录 | `research_runs/20260504_181000_sector_effect_grid_fixed/sector_effect_grid_trade_records.csv` | 6740 行、33 列，逐笔买入、卖出、跳过和阻塞流水 |
| 参数配置 | `research_runs/20260504_181000_sector_effect_grid_fixed/sector_effect_grid_config.json` | CLI 参数和展开后的策略清单 |
| 自动报告 | `research_runs/20260504_181000_sector_effect_grid_fixed/sector_effect_grid_report.md` | 脚本自动生成的 Top 结果报告 |

交易流水已用 pandas 读取校验通过，不再出现旧版追加写 CSV 时的列数不一致问题。

## 4. 汇总结果

| 排名 | 策略 | 家族 | 账户收益 | 年化收益 | 最大回撤 | 买入次数 | 胜率 | 信号中位收益 | TopN 填满率 | grid_score | 风险提示 |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 板块候选_score0.4_rank0.7 | hard_filter | 87.29% | 21.76% | 11.30% | 212 | 52.17% | -0.04% | 24.66% | 1.0657 | 信号中位收益不佳；TopN填满率偏低 |
| 2 | 板块效应_score0.4_rank0.7_exp0_m20any_amt1 | hard_filter | 83.26% | 20.94% | 10.89% | 210 | 51.22% | -0.01% | 23.23% | 1.0226 | 信号中位收益不佳；TopN填满率偏低 |
| 3 | 基准动量 | baseline | 75.86% | 19.38% | 11.90% | 238 | 51.50% | 0.28% | 29.76% | 0.9427 | TopN填满率偏低 |
| 4 | 板块效应评分_w10 | score_weight | 71.85% | 18.52% | 12.52% | 215 | 50.00% | -0.02% | 27.71% | 0.8837 | 账户回撤偏高；信号中位收益不佳；TopN填满率偏低 |
| 5 | 板块效应评分_w5 | score_weight | 70.07% | 18.13% | 12.33% | 215 | 50.00% | 0.12% | 27.71% | 0.8684 | 账户回撤偏高；TopN填满率偏低 |
| 6 | 板块效应评分_w15 | score_weight | 71.34% | 18.41% | 12.92% | 216 | 48.82% | -0.30% | 27.71% | 0.8669 | 账户回撤偏高；信号中位收益不佳；TopN填满率偏低 |
| 7 | 板块效应_score0.5_rank0.7_exp0_m20any_amt1 | hard_filter | 70.49% | 18.23% | 10.93% | 160 | 49.04% | -0.61% | 17.75% | 0.8627 | 信号中位收益不佳；TopN填满率偏低 |
| 8 | 板块效应_score0.5_rank0.7_exp0_m20any_amtany | hard_filter | 66.26% | 17.30% | 11.18% | 159 | 50.64% | -0.44% | 18.12% | 0.8210 | 信号中位收益不佳；TopN填满率偏低 |
| 9 | 板块效应_score0.4_rank0.7_exp0_m200_amt1 | hard_filter | 58.91% | 15.65% | 12.90% | 185 | 49.44% | -0.03% | 21.73% | 0.7340 | 账户回撤偏高；信号中位收益不佳；TopN填满率偏低 |
| 10 | 板块效应_score0.4_rank0.7_exp0_m200_amtany | hard_filter | 58.31% | 15.51% | 12.65% | 191 | 47.85% | -0.07% | 22.98% | 0.7261 | 账户回撤偏高；信号中位收益不佳；TopN填满率偏低 |
| 11 | 板块效应_score0.5_rank0.7_exp0_m200_amtany | hard_filter | 56.13% | 15.01% | 11.90% | 143 | 47.86% | -0.67% | 16.81% | 0.6929 | 信号中位收益不佳；TopN填满率偏低 |
| 12 | 板块效应_score0.5_rank0.7_exp0_m200_amt1 | hard_filter | 55.83% | 14.94% | 11.92% | 144 | 46.10% | -0.61% | 16.63% | 0.6870 | 信号中位收益不佳；TopN填满率偏低 |

## 5. 逐笔流水校验

交易流水按 `case + action` 汇总：

| 策略 | BUY | SELL | BUY_SKIPPED_CASH | SELL_BLOCKED |
| --- | ---: | ---: | ---: | ---: |
| 基准动量 | 238 | 233 | 259 | 1 |
| 板块候选_score0.4_rank0.7 | 212 | 207 | 192 | 0 |
| 板块效应_score0.4_rank0.7_exp0_m20any_amt1 | 210 | 205 | 172 | 0 |
| 板块效应_score0.4_rank0.7_exp0_m200_amtany | 191 | 186 | 182 | 0 |
| 板块效应_score0.4_rank0.7_exp0_m200_amt1 | 185 | 180 | 169 | 0 |
| 板块效应_score0.5_rank0.7_exp0_m20any_amtany | 159 | 156 | 133 | 0 |
| 板块效应_score0.5_rank0.7_exp0_m20any_amt1 | 160 | 157 | 126 | 0 |
| 板块效应_score0.5_rank0.7_exp0_m200_amtany | 143 | 140 | 128 | 0 |
| 板块效应_score0.5_rank0.7_exp0_m200_amt1 | 144 | 141 | 123 | 0 |
| 板块效应评分_w5 | 215 | 210 | 243 | 1 |
| 板块效应评分_w10 | 215 | 210 | 243 | 1 |
| 板块效应评分_w15 | 216 | 211 | 242 | 1 |

每笔交易包含 `trade_date`、`signal_date`、`symbol`、`name`、`action`、`price`、`shares`、`gross_amount`、`fees`、`net_amount`、`trade_return`、`price_pnl`、`exit_reason` 等字段，可用于复核成交金额、手续费和卖出盈亏。

## 6. 结论

1. `板块候选_score0.4_rank0.7` 仍是当前最值得继续观察的板块效应方案：收益 87.29%，高于基准动量的 75.86%；最大回撤 11.30%，略低于基准的 11.90%。
2. 在 `score0.4_rank0.7` 基础上增加 `sector_strongest_theme_amount_ratio_20>=1` 后，收益降到 83.26%，回撤降到 10.89%。它可以作为略保守版本，但不是收益最优。
3. 增加 `sector_strongest_theme_m20>=0` 后效果明显变差，收益约 55.83% 到 58.91%，说明这个过滤把部分有效候选也过滤掉了。
4. 把板块效应只做评分加权没有超过基准动量，`w5/w10/w15` 收益在 70.07% 到 71.85%，回撤高于 12%，暂不适合作为当前主策略。
5. 第一名虽然收益和回撤优于基准，但信号中位收益为 -0.04%，仍说明收益可能依赖少数大盈利交易。它可以继续放在模拟账户观察，但不应直接替代全部基准策略。

## 7. 下一步建议

下一步不建议继续扩大简单评分加权权重，也不建议继续加严 `theme_m20>=0`。更合理的方向是从选股条件本身入手，做一轮“板块效应 + 个股质量”的组合过滤：

```text
基础动量
+ sector_exposure_score>0
+ sector_strongest_theme_score>=0.4
+ sector_strongest_theme_rank_pct<=0.7
+ 个股相对行业/板块强度过滤
+ 成交可用性和回撤控制过滤
```

优先测试的方向：

1. 保留 `板块候选_score0.4_rank0.7` 作为主候选。
2. 增加个股层面的“相对板块更强”过滤，例如 `stock_vs_industry_m20>0` 或与 `sector_strongest_theme_m20` 的相对差。
3. 做滚动窗口验证，特别拆开 2023、2024、2025、2026YTD，确认是否仍然只依赖 2025。
4. 继续用模拟账户观察，不直接用本轮结果覆盖原基准账户。
