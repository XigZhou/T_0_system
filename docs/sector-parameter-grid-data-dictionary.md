# 板块参数网格探索数据说明

本文档说明 `scripts/run_sector_parameter_grid.py` 生成的研究数据。该脚本用于比较不同板块增强参数对信号质量、组合回测收益和交易活跃度的影响。

## 1. 数据来源

输入数据来自两个已经生成好的处理后股票目录：

| 输入 | 默认路径 | 来源 |
| --- | --- | --- |
| 基准处理后股票目录 | `data_bundle/processed_qfq_theme_focus_top100` | `scripts/build_theme_focus_universe.py` 从主题前 100 股票池生成 |
| 板块增强股票目录 | `data_bundle/processed_qfq_theme_focus_top100_sector` | `scripts/build_sector_research_features.py` 把 `sector_research/data/processed` 合并到基准处理后股票目录生成 |

脚本只读取本地 CSV，不重新抓取 AKShare 或 Tushare 数据。

板块增强目录必须包含：

- `sector_feature_manifest.csv`
- 股票 CSV 中的 `sector_exposure_score`
- 股票 CSV 中的 `sector_strongest_theme_score`
- 股票 CSV 中的 `sector_strongest_theme_rank_pct`
- 股票 CSV 中的 `sector_strongest_theme_m20`

## 2. 输出文件

默认输出目录：

```text
research_runs/YYYYMMDD_HHMMSS_sector_parameter_grid/
```

| 文件 | 数据粒度 | 主键字段 | 更新时间 |
| --- | --- | --- | --- |
| `sector_parameter_grid_summary.csv` | 每组策略参数一行 | `case` | 每次运行覆盖输出目录内同名文件 |
| `sector_parameter_grid_trade_records.csv` | 每组策略的每笔账户流水一行 | `case` + `trade_date` + `symbol` + `action` | 每次运行结束生成 |
| `sector_parameter_grid_config.json` | 每次运行一份配置 | `created_at` | 每次运行开始生成 |
| `sector_parameter_grid_report.md` | 每次运行一份中文报告 | 无 | 每次运行结束生成 |

## 3. 策略家族定义

| family | 数据目录 | 定义 |
| --- | --- | --- |
| `baseline` | 基准处理后股票目录 | 不使用 `sector_*` 字段，只作为对照组 |
| `hard_filter` | 板块增强股票目录 | 基础动量条件之外，增加个股板块暴露、最强主题分和主题排名百分位过滤 |
| `score_only` | 板块增强股票目录 | 买入条件不增加板块过滤，只把板块强度加入评分排序 |

默认基础买入条件：

```text
m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02
```

默认卖出条件：

```text
m20<0.08,hs300_m20<0.02
```

默认账户参数：

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `initial_cash` | `100000` | 初始资金 |
| `per_trade_budget` | `10000` | 每只股票目标买入金额 |
| `lot_size` | `100` | 买入股数必须是 100 股整数倍 |
| `buy_fee_rate` | `0.00003` | 买入手续费 0.003% |
| `sell_fee_rate` | `0.00003` | 卖出手续费 0.003% |
| `stamp_tax_sell` | `0` | 默认不计印花税 |
| `min_commission` | `0` | 默认无最低佣金 |
| `slippage_bps` | `3` | 默认单边滑点 3 bps |

## 4. `sector_parameter_grid_summary.csv` 字段

| 字段 | 定义 |
| --- | --- |
| `case` | 策略名称 |
| `family` | 策略家族：`baseline`、`hard_filter`、`score_only` |
| `data_profile` | 数据口径：基准为 `auto`，板块增强为 `sector` |
| `processed_dir` | 本组策略读取的数据目录 |
| `buy_condition` | 买入过滤条件 |
| `score_expression` | TopN 排序评分表达式 |
| `signal_count` | 信号质量回测中生成的信号数量 |
| `signal_completed_count` | 已完成买卖闭环的信号数量 |
| `signal_avg_trade_return` | 信号质量口径平均单笔收益 |
| `signal_median_trade_return` | 信号质量口径单笔收益中位数 |
| `signal_win_rate` | 信号质量口径胜率 |
| `signal_profit_factor` | 信号质量口径盈亏比 |
| `signal_curve_return` | 信号质量口径资金曲线收益 |
| `signal_max_drawdown` | 信号质量口径最大回撤 |
| `signal_candidate_day_ratio` | 有候选股票的交易日占比 |
| `signal_topn_fill_rate` | TopN 被填满的比例 |
| `account_total_return` | 账户回测总收益率 |
| `account_annualized_return` | 账户回测年化收益率 |
| `account_max_drawdown` | 账户回测最大回撤 |
| `account_buy_count` | 账户买入次数 |
| `account_sell_count` | 账户卖出次数 |
| `account_win_rate` | 账户已完成交易胜率 |
| `account_avg_trade_return` | 账户平均单笔收益 |
| `account_median_trade_return` | 账户单笔收益中位数 |
| `account_profit_factor` | 账户盈亏比 |
| `account_ending_equity` | 期末权益 |
| `account_open_position_count` | 期末仍持仓数量 |
| `param_score_threshold` | `hard_filter` 使用的主题强度阈值 |
| `param_rank_pct` | `hard_filter` 使用的主题排名百分位阈值 |
| `param_score_weight` | `score_only` 使用的板块评分权重 |
| `param_hard_filter` | 是否使用板块硬过滤 |
| `grid_score` | 综合排序分，定义见 `docs/sector-research-indicator-documentation.md` |
| `risk_note` | 自动风险提示，例如交易次数偏少、收益为负、回撤偏高等 |

## 5. `sector_parameter_grid_trade_records.csv` 字段

该文件在账户回测交易流水基础上增加策略维度字段：

| 字段 | 定义 |
| --- | --- |
| `case` | 策略名称 |
| `family` | 策略家族 |
| `buy_condition` | 本组策略买入条件 |
| `score_expression` | 本组策略评分表达式 |
| `trade_date` | 实际流水日期 |
| `signal_date` | 产生买入信号的日期 |
| `planned_entry_date` | 计划买入日期，默认 T+1 |
| `planned_exit_date` | 计划或实际卖出参考日期 |
| `symbol` | 股票代码 |
| `name` | 股票名称 |
| `action` | 流水类型，例如 `BUY`、`SELL`、`BUY_BLOCKED`、`SELL_BLOCKED` |
| `price` | 成交或阻塞参考价格 |
| `shares` | 股数 |
| `gross_amount` | 不含费用的成交金额 |
| `fees` | 手续费、滑点和相关费用 |
| `net_amount` | 含费用后的现金变动金额 |
| `cash_after` | 该笔流水后的现金 |
| `trade_return` | 卖出单对应的单笔收益率 |
| `price_pnl` | 卖出单对应的价格盈亏金额 |

具体交易字段随账户回测引擎输出扩展，新增字段会原样保留。

## 6. 缺失值与异常处理

- 板块增强目录缺少 `sector_feature_manifest.csv` 时，脚本直接报错。
- 任意股票 CSV 缺少必要 `sector_*` 字段时，脚本直接报错。
- 某组策略没有交易流水时，`sector_parameter_grid_trade_records.csv` 仍会生成空 CSV。
- `signal_*` 或 `account_*` 指标为空时，排序计算会按 0 处理，避免单组缺失导致整体失败。
- `sector_feature_manifest.csv` 只用于校验，不会被当成股票日线参与回测。

## 7. 复权与停牌处理

- 信号指标、买入条件和评分表达式使用处理后股票 CSV 中的前复权指标，例如 `m5`、`m20`、`m60`、`m120`。
- 实际买入和卖出价格使用 `raw_open` 等原始除权价格。
- 停牌、涨跌停和开盘不可成交约束沿用账户回测引擎中的 `can_buy_open_t`、`can_sell_t`、`can_sell_t1` 等字段。
- 该脚本不修改任何输入 CSV，只在 `research_runs/` 下写入研究结果。
