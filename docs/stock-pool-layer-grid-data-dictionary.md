# L0-L4 股票池分层实验数据说明

本文档说明 `scripts/run_stock_pool_layer_grid.py` 生成的数据来源、字段定义和使用方式。该实验用于回答：主题股票池按市值从 L0 到 L4 分层后，基准动量、板块候选、主线簇匹配加权、避开新能源主线这几类代表策略在哪一层更稳定。

## 1. 数据来源

| 来源 | 默认路径 | 用途 |
| --- | --- | --- |
| 处理后股票日线 | `data_bundle/processed_qfq` | 提供前复权信号字段、原始成交价格、成交约束、总市值快照和回测输入 |
| 个股主题暴露 | `sector_research/data/processed/stock_theme_exposure.csv` | 提供股票命中的主题、子赛道、板块、暴露分 |
| 主题强度日线 | `sector_research/data/processed/theme_strength_daily.csv` | 合并 `sector_strongest_theme_score`、`sector_strongest_theme_rank_pct` 等板块字段 |
| 轮动诊断日频 | `research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv` | 提供 `rotation_top_theme`、`rotation_top_cluster`、`rotation_state` |

当前脚本只纳入“同时存在个股主题暴露和处理后股票日线 CSV”的交集。也就是说，`stock_theme_exposure.csv` 中有 3922 只股票并不代表这次都能回测；如果 `data_bundle/processed_qfq` 里缺少某只股票的历史日线，它不会进入 L0-L4。

如果要做 Top500 完整口径，先用 `scripts/build_theme_tradeable_universe.py` 生成 `theme_tradeable_top500_layers.csv`，再用 `scripts/build_theme_layer_snapshot.py` 转成 Tushare 取数快照，最后把 `--base-processed-dir` 指向专用目录 `data_bundle/theme_tradeable_top500_4y/processed_qfq`。这种方式不会覆盖日常模拟账户的 Top100 目录。

## 2. 分层定义

默认分层方法为 `--layer-method quantile`：

1. 对可回测交集中的股票读取每只 CSV 最后一条非空 `total_mv_snapshot`。
2. 按 `total_mv_snapshot` 从大到小排序，生成 `market_cap_rank`。
3. 按等频方式切成 `--layer-count 5` 层：
   L0 最大市值，L1 偏大市值，L2 中等市值，L3 偏小市值，L4 最小市值。

也可以使用 `--layer-method rank_bands --rank-bands 100,200,300,500`。这种模式按固定排名分层，更适合以后补齐全量 3922 只主题股票行情后复用；在当前 304 只左右可回测交集下，默认不推荐固定排名分层，因为 L3/L4 可能样本过少。

Top500 完整口径推荐直接使用 `theme_tradeable_top500_layers.csv` 中已经按总市值生成的 L0-L4，每层 100 只股票。随后处理后的每只股票 CSV 会带入同一份快照中的 `total_mv` 作为 `total_mv_snapshot`，`run_stock_pool_layer_grid.py` 再次按 `total_mv_snapshot` 等频分层时应得到同样的 100/100/100/100/100 结构。

## 3. 输出文件

| 文件 | 说明 |
| --- | --- |
| `stock_pool_layer_constituents.csv` | L0-L4 每层股票成分、主题、总市值和排名 |
| `stock_pool_layer_summary.csv` | 每层股票数、市值范围、主题命中统计 |
| `stock_pool_layer_grid_summary.csv` | 每层、每个周期、每条代表策略的账户收益、回撤、信号质量 |
| `stock_pool_layer_grid_by_layer_case.csv` | 按年度结果聚合后的稳定性表 |
| `stock_pool_layer_coverage.csv` | 每层每年板块强度和轮动字段覆盖率 |
| `stock_pool_layer_grid_trade_records.csv` | 逐笔买卖记录，包含分层、周期、策略、买卖价格、股数、费用、金额和盈亏 |
| `stock_pool_layer_grid_config.json` | 本次 CLI 参数、分层目录和代表策略清单 |
| `stock_pool_layer_grid_report.md` | 自动生成的中文总结报告 |

## 4. 关键字段

### `stock_pool_layer_constituents.csv`

| 字段 | 定义 |
| --- | --- |
| `layer` | 分层编号，默认 L0-L4 |
| `layer_name` | 分层中文说明 |
| `market_cap_rank` | 在可回测主题交集内按 `total_mv_snapshot` 降序得到的市值排名 |
| `symbol`、`name` | 股票代码和名称 |
| `latest_trade_date` | 该股票处理后 CSV 的最新交易日 |
| `total_mv_trade_date` | 用于分层的总市值快照日期 |
| `total_mv_snapshot` | 用于排序的总市值快照，来自处理后股票 CSV |
| `theme_names` | 股票命中的全部主题，允许多主题 |
| `primary_theme` | 主题暴露表中的主主题，仅作展示，不作为排他分类 |
| `exposure_score` | 个股主题暴露分 |

### `stock_pool_layer_grid_summary.csv`

| 字段 | 定义 |
| --- | --- |
| `period_label` | 周期标签，如 `可比全区间`、`2025`、`最近一年`、`基准历史参考_2021` |
| `period_kind` | 周期类型，`baseline_reference` 只运行基准动量 |
| `case` | 策略名称 |
| `account_total_return` | 账户总收益率 |
| `account_max_drawdown` | 账户最大回撤 |
| `account_buy_count` | 买入次数 |
| `signal_median_trade_return` | 信号逐笔收益中位数 |
| `signal_topn_fill_rate` | TopN 填满率 |
| `risk_note` | 交易次数、回撤、收益和中位数的基础风险提示 |

## 5. 使用方式

```bash
python scripts/run_stock_pool_layer_grid.py \
  --start-date 20210101 \
  --end-date 20260508 \
  --out-dir research_runs/20260509_stock_pool_layer_grid \
  --overwrite
```

长实验可以分批续跑：

```bash
python scripts/run_stock_pool_layer_grid.py \
  --start-date 20210101 \
  --end-date 20260508 \
  --out-dir research_runs/20260509_stock_pool_layer_grid \
  --resume \
  --max-runs 20
```

如果只是先判断 L0-L4 股票池层级是否值得继续研究，可以先跑账户快速版：

```bash
python scripts/run_stock_pool_layer_grid.py \
  --start-date 20210101 \
  --end-date 20260508 \
  --out-dir research_runs/20260509_stock_pool_layer_grid_account \
  --fast-account \
  --overwrite
```

`--fast-account` 使用固定代表策略快速路径，不计算信号质量统计，因此 `signal_*` 字段会留空；账户收益、回撤、买入次数、胜率、逐笔交易记录仍会输出。后续只需要对表现较好的层和策略再补跑完整信号质量。

Top500 完整口径复现命令：

```bash
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

`build_theme_layer_snapshot.py` 输出的 `universe_snapshot_top500.csv` 字段沿用 Tushare 同步脚本需要的快照口径：`ts_code`、`symbol`、`name`、`area`、`industry`、`market`、`list_date`、`close`、`total_mv`、`turnover_rate_f`、`pe_ttm`、`pb`。同名 `.manifest.json` 会记录来源文件、输出行数、层级过滤和生成时间。

## 6. 缺失值与注意事项

- 没有 `total_mv_snapshot` 的股票会被剔除，因为无法做市值排序。
- 板块/轮动策略只在 `sector_*` 和 `rotation_*` 字段达到 `--min-coverage` 后进入公平比较区间。
- 早于板块/轮动覆盖区间的年份只输出 `基准历史参考_*`，不能拿来与板块策略横向比较。
- 脚本会在实验输出目录下生成每层临时处理后目录，不覆盖日常模拟账户使用的 Top100、板块增强和轮动增强目录。
