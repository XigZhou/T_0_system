# T 日信号摆动回测系统数据字典

本文档说明本项目数据包中各类文件的来源接口、输出路径、数据粒度、主键、字段含义，以及缺失值、停牌和复权处理逻辑。

## 1. `universe_snapshot.csv`

- 来源接口：`stock_basic` + `daily_basic`
- 输出文件路径：`data_bundle/universe_snapshot.csv`
- 数据粒度：快照日每只股票一行
- 主键字段：`ts_code`
- 更新时间：执行 `python scripts/build_universe_snapshot.py --as-of YYYYMMDD` 时生成
- 缺失值处理：`total_mv` 缺失按不满足筛选处理，其余元信息允许缺失
- 停牌/复权处理：不涉及

关键字段：

| 字段名 | 解释 |
| --- | --- |
| ts_code | Tushare 股票代码 |
| symbol | 6 位股票代码 |
| name | 股票名称 |
| industry | 行业 |
| market | 市场类型 |
| list_date | 上市日期 |
| total_mv | 总市值，单位万元 |
| turnover_rate_f | 自由流通换手率 |

## 2. `raw_daily/<symbol>.csv`

- 来源接口：`daily`
- 输出文件路径：`data_bundle/raw_daily/<symbol>.csv`
- 数据粒度：每股每交易日一行
- 主键字段：`ts_code + trade_date`
- 更新时间：执行 `python scripts/sync_tushare_bundle.py` 时生成
- 缺失值处理：不插值，不前向填充
- 停牌处理：原始日线只保留有行情的日期，停牌缺口在 `processed_qfq` 加工阶段用交易日历补齐
- 复权处理：保留原始除权价格，不直接复权

常用字段：

| 字段名 | 解释 |
| --- | --- |
| open/high/low/close | 原始开高低收 |
| pre_close | 昨收 |
| change | 涨跌额 |
| pct_chg | 涨跌幅，百分比 |
| vol | 成交量，手 |
| amount | 成交额，千元 |

## 3. `adj_factor/<symbol>.csv`

- 来源接口：`adj_factor`
- 输出文件路径：`data_bundle/adj_factor/<symbol>.csv`
- 数据粒度：每股每交易日一行
- 主键字段：`ts_code + trade_date`
- 更新时间：执行 `python scripts/sync_tushare_bundle.py` 时生成
- 缺失值处理：加工时按日期前向填充
- 停牌处理：停牌日若缺少复权因子，沿用最近有效值
- 复权处理：用于生成离线前复权价格 `qfq_*`

复权规则：

```text
scale(T) = adj_factor(T) / latest_adj_factor
qfq_close(T) = raw_close(T) * scale(T)
qfq_open/qfq_high/qfq_low 同理
```

## 4. `trade_calendar.csv`

- 来源接口：`trade_cal`
- 输出文件路径：`data_bundle/trade_calendar.csv`
- 数据粒度：每个开市日一行
- 主键字段：`trade_date`
- 更新时间：执行 `python scripts/sync_tushare_bundle.py` 时生成
- 缺失值处理：不允许缺失
- 停牌处理：个股加工时先按该表补齐所有交易日
- 复权处理：不涉及

## 5. `stk_limit.csv`

- 来源接口：`stk_limit`
- 输出文件路径：`data_bundle/stk_limit.csv`
- 数据粒度：每股每交易日一行
- 主键字段：`ts_code + trade_date`
- 更新时间：执行 `python scripts/sync_tushare_bundle.py` 时生成
- 缺失值处理：缺失时不做涨跌停约束
- 停牌处理：不直接标停牌，只提供价格边界
- 复权处理：保留原始涨跌停价

关键字段：

| 字段名 | 解释 |
| --- | --- |
| up_limit | 涨停价 |
| down_limit | 跌停价 |

## 6. `suspend_d.csv`

- 来源接口：`suspend_d`
- 输出文件路径：`data_bundle/suspend_d.csv`
- 数据粒度：每股每停复牌日期一行
- 主键字段：`ts_code + trade_date`
- 更新时间：执行 `python scripts/sync_tushare_bundle.py` 时生成
- 缺失值处理：空表表示没有停牌记录
- 停牌处理：加工阶段与交易日历合并，生成布尔停牌标记
- 复权处理：不涉及

## 7. `market_context.csv`

- 来源接口：`index_daily`
- 输出文件路径：`data_bundle/market_context.csv`
- 数据粒度：每个交易日一行
- 主键字段：`trade_date`
- 更新时间：执行 `python scripts/sync_tushare_bundle.py` 时生成
- 缺失值处理：指数缺失时相关上下文字段留空
- 停牌处理：不涉及
- 复权处理：指数指标按各自日线计算

当前指数范围：

- 上证综指 `000001.SH`
- 沪深300 `000300.SH`
- 创业板指 `399006.SZ`

## 8. `processed_qfq/<symbol>.csv`

- 来源接口：由 `raw_daily`、`adj_factor`、`trade_calendar`、`stk_limit`、`suspend_d`、`market_context` 加工得到
- 输出文件路径：`data_bundle/processed_qfq/<symbol>.csv`
- 数据粒度：每股每交易日一行
- 主键字段：`symbol + trade_date`
- 更新时间：执行 `python scripts/build_processed_data.py` 时生成
- 缺失值处理：
  - 价格与成交量字段允许在停牌日为空
  - 技术指标样本不足时为空
  - 快照字段允许为空但不会前向扩散为其他股票
- 停牌处理：
  - 先按交易日历补齐日期
  - 若日期在 `suspend_d` 中或原始价格缺失，则 `is_suspended_t=true`
  - 严格成交模式依赖停牌和涨跌停标记决定能否买卖
- 复权处理：
  - `open/high/low/close` 是 `qfq_*` 的别名，专供信号与指标计算
  - 实际买卖默认仍用 `raw_open/raw_close`
  - 持仓跨复权因子变化时，按 `adj_factor` 比例近似修正持股数量对应价值

### 8.1 核心字段

| 字段名 | 解释 |
| --- | --- |
| trade_date | 交易日，`YYYYMMDD`，升序且不重复 |
| symbol/name | 股票代码与名称 |
| raw_open/raw_high/raw_low/raw_close | 原始除权价格 |
| qfq_open/qfq_high/qfq_low/qfq_close | 前复权价格 |
| open/high/low/close | `qfq_*` 别名 |
| adj_factor | 复权因子 |
| next_open/next_close | 下一交易日前复权开盘/收盘价，主要用于单日参考标签 |
| next_raw_open/next_raw_close | 下一交易日原始开盘/收盘价，主要用于调试和对照 |
| r_on/r_on_raw | 单日隔夜参考标签，不再是当前主回测收益口径 |

### 8.2 交易约束字段

| 字段名 | 解释 |
| --- | --- |
| is_suspended_t | 当日停牌标记 |
| is_suspended_t1 | 下一交易日停牌标记 |
| can_buy_t | 当日按原始收盘价近似可买标记，保留兼容旧逻辑 |
| can_buy_open_t | 当日按原始开盘价可买标记，当前主回测买入约束字段 |
| can_buy_open_t1 | 下一交易日按原始开盘价可买标记，诊断辅助 |
| can_sell_t | 当日按原始开盘价可卖标记，当前主回测卖出约束字段 |
| can_sell_t1 | 下一交易日按原始开盘价可卖标记，诊断辅助 |

约束口径：

```text
can_buy_open_t:
  非停牌 且 raw_open 非空 且 (up_limit 缺失 或 raw_open < up_limit * 0.9995)

can_sell_t:
  非停牌 且 raw_open 非空 且 (down_limit 缺失 或 raw_open > down_limit * 1.0005)
```

### 8.3 信号与研究特征字段

| 字段名 | 解释 |
| --- | --- |
| m5/m10/m20/m30/m60/m120 | N 日价格动量，按前复权收盘价计算 |
| ma5/ma10/ma20 | N 日均线 |
| ret1/ret2/ret3 | 1/2/3 日收益 |
| amp/amp5 | 振幅与 5 日平均振幅 |
| vol5/vol10/vr | 均量与量比 |
| amount5/amount10 | 均额 |
| bias_ma5/bias_ma10 | 均线偏离率 |
| high_5/high_10/high_20 | N 日最高价 |
| low_5/low_10/low_20 | N 日最低价 |
| close_to_up_limit | 收盘价相对涨停价比例 |
| high_to_up_limit | 最高价相对涨停价比例 |
| close_pos_in_bar | 收盘在日内振幅中的位置 |
| body_pct | 实体涨跌幅 |
| upper_shadow_pct/lower_shadow_pct | 上下影线比例 |
| vol_ratio_5 | 当日量相对 5 日均量比例 |
| ret_accel_3 | 1 日收益相对 3 日收益均速的加速度 |
| vol_ratio_3/amount_ratio_3 | 当日相对 3 日均量/均额比例 |
| body_pct_3avg | 最近 3 日实体均值 |
| close_to_up_limit_3max | 最近 3 日收盘接近涨停的最大程度 |
| listed_days | 上市天数 |
| total_mv_snapshot | 快照总市值 |
| turnover_rate_snapshot | 快照换手率 |
| board/market | 板块与市场分类字段 |
| sh_* / hs300_* / cyb_* | 指数上下文字段 |

### 8.4 当前主回测口径

当前系统实际回测不是直接使用 `next_raw_open` 做卖出，而是：

1. `T` 日根据 `buy_condition + score_expression` 选出信号。
2. `T+1` 日开盘按 `raw_open` 买入。
3. `T+N` 日开盘按 `raw_open` 卖出，`N` 由回测请求参数决定，当前支持 `2~5`。
4. 若严格成交模式下卖出日不可卖，则顺延到下一个可卖开盘。

因此：

- `r_on`、`r_on_raw` 属于参考标签
- 当前研究主标签应以 `T+1 open -> T+N open` 的净收益为准
