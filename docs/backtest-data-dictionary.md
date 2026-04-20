# 新 T+1 隔夜回测系统数据字典

本文档说明本项目数据包中各类文件的来源、粒度、字段含义与加工规则。

## 1. `universe_snapshot.csv`

### 1.1 数据概览

- 数据名称：固定快照股票池
- 输出文件路径：`data_bundle/universe_snapshot.csv`
- 数据粒度：快照日每只股票一行
- 主键字段：`ts_code`
- 生成脚本：`scripts/build_universe_snapshot.py`
- 数据用途：确定本次全历史回测使用的股票池范围

### 1.2 来源说明

- 来源接口：`stock_basic` + `daily_basic`
- 权限假设：按 `2000` 积分可用
- 筛选规则：
  - 快照日总市值 `total_mv >= 500亿`
  - 股票名称不含 `ST`

### 1.3 字段说明

| 字段名 | 中文含义 | 类型/单位 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- |
| ts_code | Tushare 股票代码 | 字符串 | 不允许缺失 | 如 `000001.SZ` |
| symbol | 6 位股票代码 | 字符串 | 不允许缺失 | 如 `000001` |
| name | 股票名称 | 字符串 | 不允许缺失 | 快照日名称 |
| area | 地区 | 字符串 | 允许缺失 | 来自 `stock_basic` |
| industry | 行业 | 字符串 | 允许缺失 | 来自 `stock_basic` |
| market | 市场类型 | 字符串 | 允许缺失 | 主板/创业板/科创板等 |
| list_date | 上市日期 | `YYYYMMDD` | 不允许缺失 | 用于上市天数与对齐 |
| close | 快照日收盘价 | 数值 | 允许缺失 | 来自 `daily_basic` |
| total_mv | 总市值 | 万元 | 允许缺失后按 0 过滤 | 500 亿等于 5,000,000 万 |
| turnover_rate_f | 自由流通换手率 | 百分比 | 允许缺失 | 只做元信息保留 |
| pe_ttm | 滚动市盈率 | 数值 | 允许缺失 | 元信息 |
| pb | 市净率 | 数值 | 允许缺失 | 元信息 |

### 1.4 清洗与使用规则

1. `TUSHARE_TOKEN` 优先从本机环境变量读取。
2. 快照日期先通过 `trade_cal` 对齐到最近开市日。
3. `ST` 过滤按快照日名称匹配，不回溯历史改名。
4. 这是固定快照股票池，不做历史成分股动态调整，因此存在生存者偏差。

## 2. `raw_daily/<symbol>.csv`

### 2.1 数据概览

- 数据名称：个股原始日线
- 输出文件路径：`data_bundle/raw_daily/<symbol>.csv`
- 数据粒度：每股每个交易日一行
- 主键字段：`ts_code + trade_date`
- 生成脚本：`scripts/sync_tushare_bundle.py`
- 数据用途：保留真实原始价格，用于审计和复权计算

### 2.2 来源说明

- 来源接口：`daily`
- 权限假设：按 `2000` 积分可用

### 2.3 常用字段说明

| 字段名 | 中文含义 | 类型/单位 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- |
| ts_code | Tushare 股票代码 | 字符串 | 不允许缺失 | 主键字段之一 |
| trade_date | 交易日 | `YYYYMMDD` | 不允许缺失 | 主键字段之一 |
| open | 开盘价 | 元 | 允许缺失 | 停牌日可能缺失 |
| high | 最高价 | 元 | 允许缺失 | 停牌日可能缺失 |
| low | 最低价 | 元 | 允许缺失 | 停牌日可能缺失 |
| close | 收盘价 | 元 | 允许缺失 | 停牌日可能缺失 |
| pre_close | 昨收价 | 元 | 允许缺失 | 原始接口字段 |
| change | 涨跌额 | 元 | 允许缺失 | 原始接口字段 |
| pct_chg | 涨跌幅 | 百分比 | 允许缺失 | 原始接口字段 |
| vol | 成交量 | 手 | 允许缺失 | 用于量能指标 |
| amount | 成交额 | 千元 | 允许缺失 | 用于金额指标 |

### 2.4 清洗规则

1. 文件内按 `trade_date` 升序保存。
2. 不对原始价格做插值或前向填充。
3. 原始日线只记录有交易的日期；停牌日通过 `trade_calendar.csv` 与 `suspend_d.csv` 在加工阶段补齐。

## 3. `adj_factor/<symbol>.csv`

### 3.1 数据概览

- 数据名称：个股复权因子
- 输出文件路径：`data_bundle/adj_factor/<symbol>.csv`
- 数据粒度：每股每个交易日一行
- 主键字段：`ts_code + trade_date`
- 生成脚本：`scripts/sync_tushare_bundle.py`
- 数据用途：离线生成稳定可复现的前复权价格

### 3.2 来源说明

- 来源接口：`adj_factor`
- 权限假设：按 `2000` 积分可用

### 3.3 关键字段

| 字段名 | 中文含义 | 类型/单位 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- |
| ts_code | 股票代码 | 字符串 | 不允许缺失 | 主键字段之一 |
| trade_date | 交易日 | `YYYYMMDD` | 不允许缺失 | 主键字段之一 |
| adj_factor | 复权因子 | 数值 | 前向填充后使用 | 用于生成 `qfq_*` |

### 3.4 复权规则

1. 先按日期升序排序。
2. 使用样本区间内最后一个有效 `adj_factor` 作为基准。
3. 前复权比例：`scale(T) = adj_factor(T) / latest_adj_factor`
4. `qfq_close(T) = raw_close(T) * scale(T)`，其他价格列同理。
5. 回测成交价默认仍使用 `raw_*`，`adj_factor` 额外用于近似修正跨除权夜晚的持仓价值。

## 4. `trade_calendar.csv`

### 4.1 数据概览

- 数据名称：交易日历
- 输出文件路径：`data_bundle/trade_calendar.csv`
- 数据粒度：每个开市日一行
- 主键字段：`trade_date`
- 生成脚本：`scripts/sync_tushare_bundle.py`
- 数据用途：补齐停牌日与加工阶段的日期对齐

### 4.2 来源接口

- `trade_cal`

### 4.3 处理规则

1. 仅保留开市日 `is_open=1`。
2. 处理后每个个股数据都会先与交易日历做左连接，补齐停牌缺口。

## 5. `stk_limit.csv`

### 5.1 数据概览

- 数据名称：涨跌停价
- 输出文件路径：`data_bundle/stk_limit.csv`
- 数据粒度：每股每个交易日一行
- 主键字段：`ts_code + trade_date`
- 生成脚本：`scripts/sync_tushare_bundle.py`
- 数据用途：构造 `can_buy_t` 与 `can_sell_t`

### 5.2 来源接口

- `stk_limit`

### 5.2.1 拉取方式

为避免全市场区间查询被单次返回行数上限截断，当前版本按“股票池逐只股票 + 全历史区间”方式同步 `stk_limit.csv`，再本地汇总去重。

### 5.3 关键字段

| 字段名 | 中文含义 | 类型/单位 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- |
| up_limit | 涨停价 | 元 | 允许缺失 | 缺失时不做涨停拦截 |
| down_limit | 跌停价 | 元 | 允许缺失 | 缺失时不做跌停拦截 |

### 5.4 使用规则

1. 买入约束：
   - 若 `raw_close >= up_limit * 0.9995`，严格成交模式下视为不可买。
2. 卖出约束：
   - 若 `raw_open <= down_limit * 1.0005`，严格成交模式下视为不可卖。

## 6. `suspend_d.csv`

### 6.1 数据概览

- 数据名称：停复牌信息
- 输出文件路径：`data_bundle/suspend_d.csv`
- 数据粒度：每股每个公告日期一行
- 主键字段：`ts_code + trade_date`
- 生成脚本：`scripts/sync_tushare_bundle.py`
- 数据用途：构造 `is_suspended_t`、`is_suspended_t1`

### 6.2 来源接口

- `suspend_d`

### 6.2.1 拉取方式

当前版本按“股票池逐只股票 + 全历史区间”方式同步 `suspend_d.csv`，避免一次性区间查询被截断。

### 6.3 使用规则

1. 当某日落在停牌集合里，或原始日线价格缺失，则 `is_suspended_t=true`。
2. `is_suspended_t1` 为下一交易日的停牌状态。
3. 严格成交模式下，停牌日不能买卖。

## 7. `market_context.csv`

### 7.1 数据概览

- 数据名称：指数市场上下文
- 输出文件路径：`data_bundle/market_context.csv`
- 数据粒度：每个交易日一行
- 主键字段：`trade_date`
- 生成脚本：`scripts/sync_tushare_bundle.py`
- 数据用途：为个股处理后文件补充 `sh_*`、`hs300_*`、`cyb_*` 字段

### 7.2 来源说明

- 来源接口：`index_daily`
- 指数范围：
  - 上证综指 `000001.SH`
  - 沪深300 `000300.SH`
  - 创业板指 `399006.SZ`

### 7.3 处理规则

1. 对三条指数分别计算与个股同口径指标。
2. 再按 `trade_date` 横向合并为一张表。
3. 字段前缀规则：
   - `sh_*`
   - `hs300_*`
   - `cyb_*`

## 8. `processed_qfq/<symbol>.csv`

### 8.1 数据概览

- 数据名称：处理后回测主输入
- 输出文件路径：`data_bundle/processed_qfq/<symbol>.csv`
- 数据粒度：每股每个交易日一行
- 主键字段：`symbol + trade_date`
- 生成脚本：`scripts/build_processed_data.py`
- 数据用途：前端和 API 的主要回测输入

### 8.2 关键字段

| 字段名 | 中文含义 | 类型/单位 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- |
| trade_date | 交易日 | `YYYYMMDD` | 不允许缺失 | 升序且不重复 |
| symbol | 6 位股票代码 | 字符串 | 不允许缺失 | |
| name | 股票名称 | 字符串 | 不允许缺失 | |
| raw_open/raw_high/raw_low/raw_close | 原始价 | 元 | 停牌时允许缺失 | 保留审计口径 |
| adj_factor | 复权因子 | 数值 | 允许缺失 | 用于 `qfq_*` 与原始价执行口径下的持仓修正 |
| qfq_open/qfq_high/qfq_low/qfq_close | 前复权价 | 元 | 停牌时允许缺失 | 回测主价格口径 |
| open/high/low/close | 交易别名 | 元 | 与 `qfq_*` 相同 | 供表达式与回测使用 |
| next_open | 下一交易日复权开盘价 | 元 | 最后一行允许缺失 | 隔夜标签 |
| next_close | 下一交易日复权收盘价 | 元 | 最后一行允许缺失 | 调试用 |
| r_on | 隔夜收益 | 小数 | 最后一行允许缺失 | `next_open / close - 1` |
| next_raw_open | 下一交易日原始开盘价 | 元 | 最后一行允许缺失 | 隔夜研究标签 |
| next_raw_close | 下一交易日原始收盘价 | 元 | 最后一行允许缺失 | 调试与研究辅助 |
| r_on_raw | 原始成交口径隔夜收益 | 小数 | 最后一行允许缺失 | `next_raw_open / raw_close - 1` |
| industry | 快照行业 | 字符串 | 允许缺失 | 来自快照 |
| market | 快照市场类型 | 字符串 | 允许缺失 | 来自快照 |
| board | 板块标签 | 字符串 | 不允许缺失 | 主板/创业板/科创板/北交所 |
| listed_days | 上市天数 | 整数 | 允许缺失 | 按 `trade_date - list_date` 的自然日差计算 |
| total_mv_snapshot | 快照总市值 | 万元 | 允许缺失 | 来自快照 |
| turnover_rate_snapshot | 快照换手率 | 百分比 | 允许缺失 | 来自快照 |
| close_to_up_limit | 收盘价 / 涨停价 | 小数 | 允许缺失 | 隔夜研究特征 |
| high_to_up_limit | 最高价 / 涨停价 | 小数 | 允许缺失 | 隔夜研究特征 |
| close_pos_in_bar | 收盘在日内振幅中的位置 | 小数 | 允许缺失 | 隔夜研究特征 |
| body_pct | 实体涨跌幅 | 小数 | 允许缺失 | `(raw_close-raw_open)/raw_open` |
| upper_shadow_pct | 上影线比例 | 小数 | 允许缺失 | 隔夜研究特征 |
| lower_shadow_pct | 下影线比例 | 小数 | 允许缺失 | 隔夜研究特征 |
| vol_ratio_5 | 当日量 / 5 日均量 | 小数 | 允许缺失 | 隔夜研究特征 |
| ret_accel_3 | 1 日收益相对 3 日均速的加速度 | 小数 | 允许缺失 | v4 短周期特征 |
| vol_ratio_3 | 当日量 / 3 日均量 | 小数 | 允许缺失 | v4 短周期特征 |
| amount_ratio_3 | 当日金额 / 3 日均额 | 小数 | 允许缺失 | v4 短周期特征 |
| body_pct_3avg | 最近 3 日实体均值 | 小数 | 允许缺失 | v4 短周期特征 |
| close_to_up_limit_3max | 最近 3 日收盘距涨停比例最大值 | 小数 | 允许缺失 | v4 短周期特征 |
| up_limit/down_limit | 涨跌停价 | 元 | 允许缺失 | 来自 `stk_limit.csv` |
| is_suspended_t | 当日停牌标记 | 布尔 | 不允许缺失 | |
| is_suspended_t1 | 下一交易日停牌标记 | 布尔 | 不允许缺失 | |
| can_buy_t | 当日可买标记 | 布尔 | 不允许缺失 | 严格成交模式使用 |
| can_sell_t | 当日开盘可卖标记 | 布尔 | 不允许缺失 | 严格成交模式使用 |
| can_sell_t1 | 下一交易日开盘可卖标记 | 布尔 | 不允许缺失 | 诊断辅助 |

### 8.3 加工规则

1. 先按 `trade_calendar.csv` 补齐日期。
2. 再合并原始日线、复权因子、涨跌停、停牌、指数上下文。
3. 使用离线 `adj_factor` 生成 `qfq_*`，避免动态前复权造成复现漂移。
4. 技术指标与表达式信号默认基于 `qfq_*` 计算。
5. 交易执行默认使用 `raw_close/raw_open`；若隔夜跨除权因子变化，则按 `adj_factor` 比例近似修正持仓价值。
6. 隔夜研究特征默认基于 `raw_*`、`up_limit` 与 `vol5` 等字段派生，用于分层扫描和第二版候选条件研究。
7. 最终校验：
   - 日期升序
   - 日期不重复
   - 必备字段齐全

### 8.4 可用于表达式筛选与打分的字段

说明：

- `buy_condition` 和 `score_expression` 并不是对 `processed_qfq/<symbol>.csv` 全字段开放。
- 当前系统只开放“价格/动量/均线/量价/指数上下文”相关字段给表达式系统使用。
- 完整语法见 [expression-reference.md](/D:/量化/Momentum/T_0_system/docs/expression-reference.md)。

#### 8.4.1 当前已开放字段

| 分类 | 可用字段 |
| --- | --- |
| 价格字段 | `open`、`high`、`low`、`close` |
| 涨跌与短期收益 | `pct_chg`、`ret1`、`ret2`、`ret3` |
| 价格动量 | `m5`、`m10`、`m20`、`m30`、`m60`、`m120` |
| 均线 | `ma5`、`ma10`、`ma20` |
| 平滑动量 | `avg5mN`、`avg10mN`，例如 `avg5m20`、`avg10m60` |
| 偏离率 | `bias_ma5`、`bias_ma10` |
| 量能 | `vol`、`vol5`、`vol10`、`vr` |
| 金额 | `amount`、`amount5`、`amount10` |
| 波动 | `amp`、`amp5` |
| 区间高低点 | `high_N`、`low_N`，例如 `high_20`、`low_10` |
| 快照数值字段 | `listed_days`、`total_mv_snapshot`、`turnover_rate_snapshot` |
| 隔夜研究特征 | `close_to_up_limit`、`high_to_up_limit`、`close_pos_in_bar`、`body_pct`、`upper_shadow_pct`、`lower_shadow_pct`、`vol_ratio_5` |
| v4 短周期特征 | `ret_accel_3`、`vol_ratio_3`、`amount_ratio_3`、`body_pct_3avg`、`close_to_up_limit_3max` |
| 分类字段 | `board`、`market`；仅支持 `buy_condition` 中的 `=`/`!=` |
| 指数上下文 | `sh_*`、`hs300_*`、`cyb_*` 前缀字段，例如 `hs300_pct_chg`、`sh_m20`、`cyb_amp5` |

#### 8.4.2 当前未开放为表达式字段

这些字段虽然存在于 `processed_qfq/*.csv`，但当前版本不能直接写进 `buy_condition` 或 `score_expression`：

- 原始价格字段：`raw_open`、`raw_high`、`raw_low`、`raw_close`
- 复权原字段：`qfq_open`、`qfq_high`、`qfq_low`、`qfq_close`
- 下一日标签：`next_open`、`next_close`、`r_on`、`next_raw_open`、`next_raw_close`、`r_on_raw`
- 未开放的快照元信息：`industry`
- 交易约束：`up_limit`、`down_limit`、`can_buy_t`、`can_sell_t`、`can_sell_t1`
- 停牌标记：`is_suspended_t`、`is_suspended_t1`

如果后续你希望把这些字段也纳入筛选，需要同时修改表达式解析器白名单，而不是只改文档。

### 8.5 示例

```text
输入:
symbol=000001
trade_date=20240102
raw_close=10.00
adj_factor=1.00
latest_adj_factor=1.20

输出:
trade_date=20240102
qfq_close=8.3333
close=8.3333
can_buy_t=true
```

## 9. 缺失值、停牌与复权处理总则

1. 原始日线不做价格前向填充。
2. 停牌日通过交易日历补齐后，价格通常为空，`is_suspended_t=true`。
3. 涨跌停价缺失时，不额外阻塞交易。
4. 指标滚动窗口样本不足时置为空。
5. 前复权完全由本地 `adj_factor` 计算，不依赖动态 `pro_bar(qfq)`。
