# Top500 L0-L4 股票池分层实验记录（2026-05-09）

## 1. 实验目的

本次实验用于回答：把主题股票池从原来 304 只可回测交集扩展到统一主题可交易 Top500 后，L0-L4 市值分层结果是否更稳定，是否能找到比当前大市值 Top100 更适合模拟买入系统的候选池。

实验只使用独立数据目录 `data_bundle/theme_tradeable_top500_4y/` 和独立输出目录 `research_runs/20260509_top500_stock_pool_layer_grid_account/`，不修改当前模拟账户使用的 `data_bundle/processed_qfq_theme_focus_top100*` 目录。

## 2. 数据来源与定义

- 主题来源：`sector_research/data/processed/stock_theme_exposure.csv`，主题覆盖按 `theme_names` 全部命中统计，不按 `primary_theme` 排他统计。
- 可交易母池：`scripts/build_theme_tradeable_universe.py`，过滤 ST、北交所、上市不足 250 天、总市值低于 30 亿的股票。
- Top500 分层来源：`sector_research/data/processed/theme_tradeable_universe/theme_tradeable_top500_layers.csv`。
- 取数快照：`data_bundle/theme_tradeable_top500_4y/universe_snapshot_top500.csv`，由 `scripts/build_theme_layer_snapshot.py` 从 Top500 分层明细生成。
- 历史行情：Tushare `daily`、`adj_factor`、`stk_limit`、`suspend_d`、`trade_cal`，区间为 `20210701` 到 `20260508`。
- 处理后数据：`data_bundle/theme_tradeable_top500_4y/processed_qfq`，500 只股票全部处理成功。
- 回测信号：前复权价格计算指标，买入卖出使用原始除权价格，仍按 T 日信号、T+1 日开盘买入。

## 3. 复现命令

```bash
python scripts/build_theme_tradeable_universe.py \
  --as-of 20260508 \
  --top-sizes 500,1000 \
  --min-total-mv-yi 30 \
  --min-listed-days 250

python scripts/build_theme_layer_snapshot.py \
  --layers-csv sector_research/data/processed/theme_tradeable_universe/theme_tradeable_top500_layers.csv \
  --out data_bundle/theme_tradeable_top500_4y/universe_snapshot_top500.csv \
  --layers L0,L1,L2,L3,L4 \
  --pool-name Top500

python scripts/sync_tushare_bundle.py \
  --env .env \
  --bundle-dir data_bundle/theme_tradeable_top500_4y \
  --snapshot-csv data_bundle/theme_tradeable_top500_4y/universe_snapshot_top500.csv \
  --start-date 20210701 \
  --end-date 20260508 \
  --sleep-seconds 0.2

python scripts/build_processed_data.py \
  --bundle-dir data_bundle/theme_tradeable_top500_4y \
  --output-dir data_bundle/theme_tradeable_top500_4y/processed_qfq \
  --snapshot-csv data_bundle/theme_tradeable_top500_4y/universe_snapshot_top500.csv

python scripts/run_stock_pool_layer_grid.py \
  --base-processed-dir data_bundle/theme_tradeable_top500_4y/processed_qfq \
  --start-date 20220101 \
  --end-date 20260507 \
  --rotation-daily-path research_runs/latest_sector_rotation_diagnosis/sector_rotation_daily.csv \
  --out-dir research_runs/20260509_top500_stock_pool_layer_grid_account \
  --fast-account \
  --rolling-months 0 \
  --overwrite
```

## 4. 分层结构

| 分层 | 股票数 | 市值排名 | 总市值中位数 | 主题覆盖摘要 |
| --- | ---: | ---: | ---: | --- |
| L0 | 100 | 1-100 | 20,018,670 | AI 48、光伏新能源 40、半导体芯片 39、锂矿锂电 30、机器人 27、存储芯片 16 |
| L1 | 100 | 101-200 | 8,916,063 | 光伏新能源 48、AI 45、锂矿锂电 37、半导体芯片 36、机器人 23、存储芯片 8 |
| L2 | 100 | 201-300 | 6,282,908 | AI 41、光伏新能源 35、半导体芯片 35、机器人 27、锂矿锂电 27、存储芯片 9 |
| L3 | 100 | 301-400 | 4,457,453 | 光伏新能源 43、半导体芯片 40、AI 37、锂矿锂电 35、医药 21、存储芯片 9 |
| L4 | 100 | 401-500 | 3,583,734 | 光伏新能源 48、半导体芯片 36、锂矿锂电 32、AI 31、机器人 22、存储芯片 6 |

说明：`total_mv` 单位沿用 Tushare `daily_basic`，为万元。Top500 每层固定 100 只，比 304 只交集实验每层约 60 只更稳定。

## 5. 全区间结果

| 分层 | 最佳策略 | 收益 | 最大回撤 | 买入次数 | 胜率 |
| --- | --- | ---: | ---: | ---: | ---: |
| L0 | 基准动量 | 66.06% | 17.85% | 192 | 59.90% |
| L1 | 基准动量 | 67.98% | 25.22% | 219 | 49.77% |
| L2 | 基准动量 | 105.01% | 13.70% | 249 | 57.43% |
| L3 | 基准动量 | 60.58% | 21.37% | 241 | 50.21% |
| L4 | 基准动量 | 47.69% | 16.27% | 235 | 54.04% |

全区间收益最高的是 L2 的 `基准动量`，收益 105.01%，最大回撤 13.70%。L2 的板块候选和主线簇匹配加权也分别达到 100.77% 和 96.77%，但仍未超过基准动量。

## 6. 年度稳定性

| 分层 | 策略 | 正收益年份 | 年均收益 | 年收益中位数 | 最差年份 | 最大回撤 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| L2 | 基准动量 | 4/4 | 24.97% | 13.69% | 4.23% | 12.71% |
| L2 | 主线簇匹配加权_w5 | 4/4 | 21.35% | 12.56% | 2.91% | 12.46% |
| L2 | 板块候选_score0.4_rank0.7 | 4/4 | 21.30% | 12.15% | 3.17% | 12.44% |

L2 基准动量逐年结果：

| 年份 | 收益 | 最大回撤 | 买入次数 |
| --- | ---: | ---: | ---: |
| 2023 | 4.23% | 9.96% | 29 |
| 2024 | 6.20% | 11.11% | 72 |
| 2025 | 68.26% | 12.71% | 114 |
| 2026YTD | 21.19% | 4.44% | 13 |

## 7. 与 304 只交集实验对比

| 口径 | 最佳层 | 最佳策略 | 收益 | 最大回撤 | 结论 |
| --- | --- | --- | ---: | ---: | --- |
| 304 只可回测交集 | L3 | 基准动量 | 98.41% | 11.70% | 样本较少，偏小市值层最好 |
| Top500 完整补数 | L2 | 基准动量 | 105.01% | 13.70% | 样本更完整，中等市值层最好 |

Top500 L2 比 304 只交集的 L2 收益提高约 53.84 个百分点，回撤降低约 3.05 个百分点。Top500 L0 也比旧 L0 明显改善，但 Top500 的 L1、L3、L4 不如旧交集口径对应层，说明旧结果里存在“样本交集偏差”，不能直接把 304 只交集的 L3 作为最终候选池。

## 8. 结论

1. Top500 完整口径比 304 只交集口径更适合作为后续股票池研究基准，因为每层都是 100 只且行情补齐。
2. 当前最值得继续研究的是 L2 中等市值层，而不是简单扩大到全 Top500，也不是直接沿用 304 只交集实验的 L3。
3. 板块候选和主线簇匹配加权在 L2 上表现接近基准动量，但仍未稳定超越；它们可以作为风险过滤或评分备选，不建议直接替代基准动量。
4. 当前不建议立刻切换线上模拟账户股票池。下一步应先做候选池组合实验，例如 L2-only、L1-L2、L2-L3，并与当前 Top100 模拟账户口径同周期对比。

## 9. 输出位置

- `data_bundle/theme_tradeable_top500_4y/universe_snapshot_top500.csv`
- `data_bundle/theme_tradeable_top500_4y/processed_qfq/processing_manifest.csv`
- `research_runs/20260509_top500_stock_pool_layer_grid_account/stock_pool_layer_constituents.csv`
- `research_runs/20260509_top500_stock_pool_layer_grid_account/stock_pool_layer_summary.csv`
- `research_runs/20260509_top500_stock_pool_layer_grid_account/stock_pool_layer_grid_summary.csv`
- `research_runs/20260509_top500_stock_pool_layer_grid_account/stock_pool_layer_grid_by_layer_case.csv`
- `research_runs/20260509_top500_stock_pool_layer_grid_account/stock_pool_layer_grid_trade_records.csv`
- `research_runs/20260509_top500_stock_pool_layer_grid_account/stock_pool_layer_grid_report.md`
