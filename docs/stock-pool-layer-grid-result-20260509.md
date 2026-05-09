# L0-L4 股票池分层实验记录（2026-05-09）

## 1. 实验目的

本次实验用于验证：当前主题股票池是否因为偏大市值而影响策略表现，以及板块轮动代表策略在不同市值层中的稳定性是否不同。

实验不修改模拟账户股票池，也不替换现有 Top100 目录；脚本只在 `research_runs/` 下输出成分、汇总、交易流水和报告。正式运行使用 `--fast-account`，不会再复制每层完整增强 CSV，避免占用腾讯云磁盘。

## 2. 数据与分层口径

- 股票来源：`sector_research/data/processed/stock_theme_exposure.csv` 与 `data_bundle/processed_qfq` 的可回测交集。
- 可回测主题股票数：304 只。
- 分层依据：每只股票处理后 CSV 中最新非空 `total_mv_snapshot`。
- 分层方法：`quantile` 等频五层，L0 最大市值，L4 最小市值。
- 可比区间：板块/轮动字段覆盖后，从 `20230403` 到 `20260430`；2021-2022 只作为基准动量历史参考。
- 代表策略：`基准动量`、`板块候选_score0.4_rank0.7`、`主线簇匹配加权_w5`、`候选_避开新能源主线`。

| 分层 | 股票数 | 市值排名 | 总市值中位数 | 主题覆盖摘要 |
| --- | ---: | ---: | ---: | --- |
| L0 | 61 | 1-61 | 23,519,230 | AI 25、光伏新能源 25、半导体芯片 19、锂矿锂电 17、机器人 14、存储芯片 8 |
| L1 | 61 | 62-122 | 11,908,590 | 光伏新能源 32、AI 30、锂矿锂电 23、机器人 19、半导体芯片 18、存储芯片 6 |
| L2 | 61 | 123-183 | 7,842,467 | 光伏新能源 27、半导体芯片 26、AI 24、锂矿锂电 21、机器人 16、存储芯片 6 |
| L3 | 61 | 184-244 | 6,119,405 | 半导体芯片 25、AI 22、光伏新能源 22、锂矿锂电 19、机器人 12、存储芯片 7 |
| L4 | 60 | 245-304 | 5,181,454 | AI 26、半导体芯片 22、光伏新能源 21、锂矿锂电 21、医药 11、存储芯片 7 |

说明：主题覆盖按 `theme_names` 全部命中统计，不按 `primary_theme` 排他统计，因此一只股票可以同时计入 AI、半导体芯片、存储芯片等多个主题。

## 3. 复现命令

```bash
python scripts/run_stock_pool_layer_grid.py \
  --start-date 20210101 \
  --end-date 20260508 \
  --out-dir research_runs/20260509_stock_pool_layer_grid_account \
  --fast-account \
  --rolling-months 0 \
  --overwrite
```

如果中途断开：

```bash
python scripts/run_stock_pool_layer_grid.py \
  --start-date 20210101 \
  --end-date 20260508 \
  --out-dir research_runs/20260509_stock_pool_layer_grid_account \
  --fast-account \
  --rolling-months 0 \
  --resume
```

## 4. 全区间结果

| 分层 | 全区间最佳策略 | 收益 | 回撤 | 买入次数 | 备注 |
| --- | --- | ---: | ---: | ---: | --- |
| L0 | 主线簇匹配加权_w5 | 41.08% | 17.62% | 158 | 收益最低且回撤偏高 |
| L1 | 基准动量 | 71.99% | 14.07% | 226 | 大于 L0，但回撤偏高 |
| L2 | 基准动量 | 51.17% | 16.74% | 209 | 优于 L0 的部分板块策略，但不如 L1/L3 |
| L3 | 基准动量 | 98.41% | 11.70% | 232 | 本次最优，收益最高且回撤可接受 |
| L4 | 基准动量 | 76.89% | 21.48% | 228 | 收益高但回撤明显放大 |

## 5. 年度稳定性

| 分层 | 最佳年度稳定策略 | 正收益年份 | 年均收益 | 年收益中位数 | 最差年份 | 最大回撤 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| L0 | 主线簇匹配加权_w5 | 2/4 | 9.32% | 5.85% | -12.98% | 17.62% |
| L1 | 基准动量 | 3/4 | 14.53% | 10.34% | -7.44% | 14.07% |
| L2 | 基准动量 | 3/4 | 11.43% | 10.32% | -12.43% | 16.74% |
| L3 | 基准动量 | 3/4 | 19.77% | 11.84% | -3.50% | 10.36% |
| L4 | 基准动量 | 3/4 | 14.15% | 14.52% | -6.68% | 13.76% |

2023 年多数层为负，2024、2025、2026YTD 明显改善。L3 的 2023 回撤和亏损最小，2025、2026YTD 弹性最好，是本轮最值得继续研究的层。

## 6. 初步结论

1. 股票池问题确实存在：当前 Top100 偏大市值，L0 表现显著弱于 L1-L4，尤其弱于 L3。
2. 当前不建议简单去掉 TopN，但建议把候选池从 Top100 扩展到分层池，并重点测试 L2-L4 或 L1-L3。
3. 板块轮动加权没有稳定跑赢基准动量。它在 L0 全区间略好，但年度稳定性不强；在 L1-L4 中多数不如基准动量。
4. `候选_避开新能源主线` 通常降低收益但能降低部分层的回撤，可作为风险过滤备选，不应作为收益增强主策略。
5. 存储芯片在本次可回测交集中各层都有 6-8 只命中，不再是之前 `primary_theme` 口径看到的 8 只总量问题。

## 7. 输出位置

- `research_runs/20260509_stock_pool_layer_grid_account/stock_pool_layer_constituents.csv`
- `research_runs/20260509_stock_pool_layer_grid_account/stock_pool_layer_summary.csv`
- `research_runs/20260509_stock_pool_layer_grid_account/stock_pool_layer_grid_summary.csv`
- `research_runs/20260509_stock_pool_layer_grid_account/stock_pool_layer_grid_by_layer_case.csv`
- `research_runs/20260509_stock_pool_layer_grid_account/stock_pool_layer_coverage.csv`
- `research_runs/20260509_stock_pool_layer_grid_account/stock_pool_layer_grid_trade_records.csv`
- `research_runs/20260509_stock_pool_layer_grid_account/stock_pool_layer_grid_report.md`

## 8. 下一步建议

优先做“候选池组合实验”：构建 L1-L3、L2-L4、L3-only 三个候选池，仍使用基准动量 TopN 逻辑，与当前 Top100 模拟账户口径对比。若 L3-only 交易次数足够且回撤仍可控，可以再考虑新增一个模拟账户专门观察 L3 分层池。