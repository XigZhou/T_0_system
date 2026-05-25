# 回测数据字典

本文档说明组合回测、信号质量、每日计划和单股回测当前使用的 SQLite 输入、关键字段、输出结构和交易口径。当前正式输入是 `data_store/market_data.sqlite.stock_daily_features`。

## 1. 输入数据集

- 来源：`scripts/compute_stock_daily_features.py` 从 SQLite raw 表计算。
- 输入路径：`data_store/market_data.sqlite`。
- 输入表：`stock_daily_features`。
- 数据粒度：每只股票每个交易日一行。
- 主键：`symbol + trade_date`。
- 更新时间：管理员指标计算按钮或每日核心调度。
- 缺失值处理：指标窗口不足时为空；停牌或价格缺失时不可成交；回测不会对缺失指标做未来填充。
- 复权处理：信号字段使用前复权价格，成交和估值字段使用原始除权价格；实盘账户回测的现金、持仓市值、期末权益、真实交易流水和个股已实现盈亏使用真实成交股数，`adj_factor` 不调整交易股数。

## 2. 股票范围

默认股票范围来自 `main_stock_universe` 的活跃股票。`source=all` 在采集和计算中等价于主股票池，不代表全市场。

股票池模板只用于用户自选范围和模拟账户配置；普通用户模板中的股票必须属于主股票池活跃集合。

## 3. 关键输入字段

| 字段 | 说明 | 用途 |
| --- | --- | --- |
| `symbol` / `ts_code` / `name` | 股票标识 | 展示、交易、导出 |
| `trade_date` | 交易日，`YYYYMMDD` | 时间推进 |
| `open/high/low/close` | 前复权开高低收 | 买入条件、卖出条件、评分、技术指标 |
| `raw_open/raw_high/raw_low/raw_close` | 原始除权开高低收 | 买入、卖出、估值成交价格 |
| `adj_factor` | 复权因子 | 复权和历史对齐 |
| `pct_chg` | 日涨跌幅百分数 | 条件过滤 |
| `can_buy_open_t` | 当日开盘是否允许买入 | 严格成交 |
| `can_sell_t` | 当日开盘是否允许卖出 | 严格成交 |
| `m5/m10/m20/m30/m60/m120` | N 日价格动量 | 买入条件和评分 |
| `ma5/ma10/ma20` | 移动均线 | 趋势过滤 |
| `ret1/ret2/ret3` | 短期收益 | 节奏过滤 |
| `vol/vol5/vol10/vr` | 成交量和量比 | 量能过滤 |
| `amount/amount5/amount10` | 成交额和均额 | 流动性过滤 |
| `board/market` | 市场分类字段 | 分类过滤 |
| `sh_* / hs300_* / cyb_*` | 指数环境字段 | 大盘过滤 |

## 4. 组合回测请求字段

| 字段 | 说明 |
| --- | --- |
| `start_date` / `end_date` | 回测区间 |
| `buy_condition` | 买入条件，逗号分隔表示全部满足 |
| `sell_condition` | 卖出条件，满足后下一交易日开盘卖出 |
| `score_expression` | 候选排序表达式 |
| `top_n` | 每日最多买入数量 |
| `initial_cash` | 初始资金 |
| `target_position_value` | 每只股票目标买入金额 |
| `max_hold_days` | 最大持有交易日数 |
| `min_hold_days` | 卖出条件生效前最短持有天数 |
| `fee_rate` | 买卖手续费率 |
| `slippage_bps` | 滑点，单位 bps |
| `strict_execution` | 是否启用严格成交约束 |
| `stock_pool_market_db_path` | 行情指标 SQLite 路径，空值使用默认主库 |

## 5. 组合回测输出字段

摘要字段：`initial_cash`、`final_equity`、`total_return`、`annual_return`、`max_drawdown`、`trade_count`、`win_rate`、`cash`、`market_value`。

真实交易流水字段：`trade_date`、`signal_date`、`symbol`、`name`、`rank`、`score`、`action`、`price`、`price_basis`、`shares`、`gross_amount`、`fees`、`net_amount`、`cash_after`、`pnl`、`trade_return`、`holding_days`、`exit_reason`、`execution_note`。实盘账户模式中 `shares` 是买入按 `lot_size` 向下取整后的真实成交股数，卖出沿用持仓真实股数。信号质量模式的样本流水固定按 100 股计算金额，不代表真实账户成交。

每日资产字段：`trade_date`、`cash`、`market_value`、`equity`、`positions`、`daily_return`、`drawdown`。

候选列表用于排查买入条件和评分结果，包含信号日期、股票、评分、关键指标和未买入原因。持仓列表包含买入日期、成本、当前价格、市值、持有天数和浮动盈亏。

## 6. 每日计划输出

| 字段 | 说明 |
| --- | --- |
| `trade_date` | 信号日期 |
| `buy_candidates` | 通过买入条件的候选股票 |
| `buy_plan` | 次日计划买入列表 |
| `sell_alerts` | 已持仓股票的卖出提醒 |
| `diagnostics` | 数据缺失、字段缺失、过滤数量等诊断 |

## 7. 单股回测输出

| 字段 | 说明 |
| --- | --- |
| `trades` | 单股买卖流水 |
| `summary` | 收益、胜率、最大回撤、持有天数统计 |
| `signals` | 命中买入/卖出条件的日期 |
| `diagnostics` | 股票解析和数据可用性诊断 |

## 8. 交易约束

买入数量按目标金额折算后向下取 100 股整数倍；不足一手时按配置决定是否跳过。默认手续费为 `0.003%`，无最低消费。滑点按 bps 调整成交价：

```text
买入成交价 = raw_open * (1 + slippage_bps / 10000)
卖出成交价 = raw_open * (1 - slippage_bps / 10000)
```

回测严格按日期升序推进。T 日收盘生成信号，T+1 开盘成交；卖出条件在收盘后判断，下一交易日开盘执行，避免未来函数。

### 8.1 价格与股数口径

- 信号条件、评分表达式和动量指标读取 `open/high/low/close`，这些字段是前复权价格。
- 实盘账户回测买卖成交使用 `raw_open`，截止日持仓估值使用 `raw_close`。
- 实盘账户回测的账户权益、年度稳定性、月度表现和个股贡献按真实账户资金与真实成交股数统计，可用于交易审计。
- 信号质量回测的权益曲线是从 100000 起步、按完成信号平均收益率复利得到的“信号净值”；交易流水是固定 100 股样本流水，不用于账户审计。
- `adj_factor` 只参与前复权价格和指标构造，不会把交易流水、持仓市值或盈亏里的股数乘以复权因子比例。
