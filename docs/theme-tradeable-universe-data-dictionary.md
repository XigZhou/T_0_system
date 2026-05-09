# 统一主题可交易股票池数据说明

## 1. 用途

本文档说明 `scripts/build_theme_tradeable_universe.py` 生成的统一主题可交易股票池快照。这个数据集用于先统一股票池口径，再决定是否给 Top500、Top1000 或其他候选池补最近四年日线数据并做 L0-L4 回测。

它不会拉取四年日线，不会修改当前模拟账户正在使用的处理后股票目录，也不会覆盖 `data_bundle/processed_qfq_theme_focus_top100`、`data_bundle/processed_qfq_theme_focus_top100_sector` 或 `data_bundle/processed_qfq_theme_focus_top100_sector_rotation`。

## 2. 数据来源

| 来源 | 默认路径或接口 | 用途 |
| --- | --- | --- |
| 个股主题暴露 | `sector_research/data/processed/stock_theme_exposure.csv` | 提供主题、子主题、板块映射和主题暴露分数。 |
| Tushare `stock_basic` | `ts_code,symbol,name,area,industry,market,list_date,list_status` | 提供上市状态、上市日期、行业、市场和股票名称。 |
| Tushare `daily_basic` | `ts_code,trade_date,close,total_mv,turnover_rate_f,volume_ratio,pe_ttm,pb` | 提供最新交易日总市值、换手率和估值字段。 |
| 当前模拟 Top100 快照 | `data_bundle/universe_snapshot_theme_focus_top100.csv` | 用来标记当前模拟系统股票池在统一母池和 L0-L4 分层中的位置。 |

Tushare token 默认从环境变量或 `.env` 中读取，字段不会写入输出文件或文档。

## 3. 生成命令

腾讯云默认运行方式：

```bash
cd /home/ubuntu/T_0_system
source /home/ubuntu/TencentCloud/myenv/bin/activate

python scripts/build_theme_tradeable_universe.py \
  --as-of 20260508 \
  --top-sizes 500,1000 \
  --min-total-mv-yi 30 \
  --min-listed-days 250
```

常用参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--exposure-path` | `sector_research/data/processed/stock_theme_exposure.csv` | 个股主题暴露输入文件。 |
| `--current-top100-snapshot` | `data_bundle/universe_snapshot_theme_focus_top100.csv` | 当前模拟 Top100 对照输入。 |
| `--out-dir` | `sector_research/data/processed/theme_tradeable_universe` | 输出目录。 |
| `--as-of` | 当前日期 | 用此前最近一个开市日的 Tushare 最新市值数据。 |
| `--top-sizes` | `500,1000` | 需要生成 L0-L4 分层的 TopN 股票池。 |
| `--layer-count` | `5` | 分层数量，默认 L0-L4 五层。 |
| `--min-total-mv-yi` | `30` | 母池最低总市值，单位亿元。 |
| `--min-listed-days` | `250` | 最低上市天数。 |
| `--exclude-markets` | `北交所` | 默认先排除北交所，保持交易规则更接近当前模拟系统。 |
| `--include-st` | 关闭 | 开启后不剔除名称含 ST 的股票；默认剔除。 |

## 4. 输出文件

默认输出目录：`sector_research/data/processed/theme_tradeable_universe/`。

| 文件 | 粒度 | 主键 | 说明 |
| --- | --- | --- | --- |
| `theme_tradeable_universe_snapshot.csv` | 股票 | `symbol` | 统一主题母池快照，包含全部主题暴露股票和过滤原因。 |
| `theme_tradeable_universe_summary.csv` | 范围 | `scope` | 全部主题股、可交易母池、Top500、Top1000 的数量和主题覆盖摘要。 |
| `theme_tradeable_top500_layers.csv` | 股票 | `pool_name + symbol` | Top500 市值分层明细，L0 最大市值，L4 最小市值。 |
| `theme_tradeable_top500_layer_summary.csv` | 分层 | `pool_name + layer` | Top500 各层数量、市值范围、主题覆盖和当前 Top100 重合数量。 |
| `theme_tradeable_top1000_layers.csv` | 股票 | `pool_name + symbol` | Top1000 市值分层明细。 |
| `theme_tradeable_top1000_layer_summary.csv` | 分层 | `pool_name + layer` | Top1000 各层摘要。 |
| `theme_tradeable_layer_summary_all.csv` | 分层 | `pool_name + layer` | 合并版分层摘要，方便直接对比 Top500 与 Top1000。 |
| `current_top100_layer_compare.csv` | 股票 | `symbol` | 当前模拟 Top100 与统一母池、Top500、Top1000 分层的对照表。 |
| `theme_tradeable_universe_manifest.json` | 运行 | 无 | 记录生成时间、TopN 参数和输出路径。 |
| `source/stock_basic_YYYYMMDD.csv` | 股票 | `ts_code` | 本次使用的 Tushare 股票基础信息快照。 |
| `source/daily_basic_YYYYMMDD.csv` | 股票 | `ts_code + trade_date` | 本次使用的 Tushare 最新交易日市值和换手率快照。 |

## 5. 关键字段

### `theme_tradeable_universe_snapshot.csv`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tradeable_rank` | 整数 | 可交易母池内按总市值降序排名；不满足过滤条件则为空。 |
| `is_tradeable_base` | 布尔 | 是否进入统一主题可交易母池。 |
| `filter_reasons` | 文本 | 未进入母池的原因，多个原因用分号分隔。 |
| `as_of_trade_date` | 日期 | 本次使用的最新开市日。 |
| `symbol` | 文本 | 6 位股票代码。 |
| `ts_code` | 文本 | Tushare 股票代码。 |
| `name` | 文本 | Tushare 股票简称，缺失时回退到主题暴露表名称。 |
| `industry` | 文本 | Tushare 行业。 |
| `market` | 文本 | 市场板块，例如主板、创业板、科创板、北交所。 |
| `list_status` | 文本 | 上市状态，默认只保留 `L`。 |
| `list_date` | 日期 | 上市日期。 |
| `listed_days` | 数值 | `as_of_trade_date - list_date` 的自然日天数。 |
| `is_st` | 布尔 | 股票简称是否包含 `ST`。 |
| `close` | 数值 | 最新交易日收盘价，来自 `daily_basic`。 |
| `total_mv` | 数值 | Tushare 总市值，单位万元。 |
| `total_mv_yi` | 数值 | 总市值亿元，计算公式为 `total_mv / 10000`。 |
| `turnover_rate_f` | 数值 | 自由流通股换手率。 |
| `volume_ratio` | 数值 | 量比，来自 `daily_basic`。 |
| `pe_ttm` | 数值 | 滚动市盈率。 |
| `pb` | 数值 | 市净率。 |
| `theme_names` | 文本 | 命中的主题，多个主题用 `、` 分隔。 |
| `primary_theme` | 文本 | 当前主题暴露系统给出的主主题。 |
| `primary_subtheme` | 文本 | 当前主题暴露系统给出的主子主题。 |
| `exposure_score` | 数值 | 主题暴露分数。 |
| `current_top100_symbol` | 布尔 | 是否属于当前模拟系统的 Top100 快照。 |

### 分层文件

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `pool_name` | 文本 | 股票池名称，例如 `Top500`、`Top1000`。 |
| `pool_rank` | 整数 | 在该 TopN 池内按总市值降序排名。 |
| `layer_index` | 整数 | 分层编号，0 到 4。 |
| `layer` | 文本 | `L0` 到 `L4`，L0 为最大市值层。 |
| `layer_name` | 文本 | 分层中文名称。 |

## 6. 过滤和分层逻辑

默认过滤条件：

1. 必须出现在 `stock_theme_exposure.csv`。
2. Tushare `stock_basic.list_status` 必须为 `L`。
3. 股票简称不包含 `ST`。
4. 默认排除北交所。
5. 上市天数不少于 `250` 天。
6. 最新总市值不少于 `30` 亿元。
7. 必须能在最新 `daily_basic` 中拿到总市值。

分层逻辑：

1. 对可交易母池按 `total_mv` 降序排序，`turnover_rate_f` 和 `symbol` 用于并列排序。
2. 取 Top500 或 Top1000。
3. 在各自 TopN 内等频分成五层，L0 最大市值，L4 最小市值。

举例：Top500 每层约 100 只，L0 基本对应“统一主题母池里的最大市值前 100 只”；Top1000 每层约 200 只，L0 为前 200 只。

## 7. 本次快照摘要（2026-05-08）

本次在腾讯云生成的快照使用最新开市日 `20260508`：

| 范围 | 股票数 | 可交易数 | 当前 Top100 命中数 |
| --- | ---: | ---: | ---: |
| 全部主题暴露股 | 3922 | 3267 | 100 |
| 可交易主题母池 | 3267 | 3267 | 95 |
| Top500 | 500 | 500 | 95 |
| Top1000 | 1000 | 1000 | 95 |

Top500 分层中，当前模拟 Top100 分布为：L0 63 只、L1 31 只、L2 1 只、5 只不在可交易母池或 Top500。Top1000 分层中，当前模拟 Top100 分布为：L0 94 只、L1 1 只、5 只不在可交易母池或 Top1000。

重点主题覆盖数量：

| 股票池 | 存储芯片 | AI | 机器人 | 光伏新能源 | 锂矿锂电 | 半导体芯片 | 医药 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Top500 | 48 | 202 | 119 | 214 | 161 | 186 | 68 |
| Top1000 | 80 | 390 | 266 | 439 | 301 | 331 | 146 |

## 8. 缺失值处理

- 如果股票在 `stock_theme_exposure.csv` 中存在，但 Tushare 最新基础信息缺失，则 `list_status` 会记为 `MISSING`，不会进入可交易母池。
- 如果 `daily_basic.total_mv` 缺失，则 `filter_reasons` 记录 `缺少最新总市值`。
- 主题字段缺失不会导致剔除，因为进入本数据集的前提已经是出现在主题暴露表中。
- 当前模拟 Top100 中若有股票不在统一母池中，会在 `current_top100_layer_compare.csv` 中保留，并标记 `in_tradeable_universe=false`。

## 9. 使用建议

这个数据集只用于股票池设计，不直接用于交易。建议先检查：

1. `theme_tradeable_universe_summary.csv` 中可交易母池数量是否合理。
2. `theme_tradeable_layer_summary_all.csv` 中各层的主题覆盖是否均衡。
3. `current_top100_layer_compare.csv` 中当前模拟 Top100 与 Top500 L0、Top1000 L0 的重合程度。
4. 存储芯片、AI、机器人、光伏新能源、锂矿锂电、医药在 Top500/Top1000 各层是否有足够样本。

只有当这些结构合理后，再选择 Top500 或 Top1000 拉最近四年日线并做真实 L0-L4 回测。
