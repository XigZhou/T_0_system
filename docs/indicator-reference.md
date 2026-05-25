# 指标说明

本文档说明 `stock_daily_features` 中主要指标的用途、输入字段、计算公式、窗口参数、边界条件和示例。除特别说明外，信号指标基于前复权价格 `close` 计算，成交和估值使用 `raw_open/raw_close`。

## 1. 前复权价格

用途：让历史价格在复权后可比较，用于动量、均线和评分。

输入字段：`stock_daily_raw` 的原始价格、`stock_adj_factor.adj_factor`。

公式：

```text
scale(T) = adj_factor(T) / latest_adj_factor
close(T) = raw_close(T) * scale(T)
open/high/low 同理
```

边界条件：复权因子缺失时该日复权价格为空或沿用最近有效因子；原始价格缺失时复权价格为空。

示例：最新复权因子为 10，当日复权因子为 8，原始收盘价 12 元，则 `close=12*8/10=9.6`。

## 2. 价格动量 `mN`

用途：衡量当前价格相对窗口起点的涨跌幅。

输入字段：`close`。

输出字段：`m5`、`m10`、`m20`、`m30`、`m60`、`m120`。

公式：

```text
mN(T) = [close(T) - close(T-N+1)] / close(T-N+1)
```

边界条件：历史样本不足 `N` 条时为空；分母为 0 时为空；不使用未来数据。

示例：`close(T)=11.00`，`close(T-4)=10.00`，则 `m5=(11.00-10.00)/10.00=0.10`。

## 3. 移动均线 `maN`

用途：平滑价格波动。

输入字段：`close`。

输出字段：`ma5`、`ma10`、`ma20`。

公式：

```text
maN(T) = mean(close(T), close(T-1), ..., close(T-N+1))
```

边界条件：样本不足 `N` 条时为空。

示例：最近 5 日 close 为 `[10.00, 10.20, 10.10, 10.40, 10.30]`，则 `ma5=10.20`。

## 4. 平滑动量 `avg5mN` 与 `avg10mN`

用途：用均线动量代替原始价格动量，降低噪音。

输入字段：`ma5`、`ma10`。

公式：

```text
avg5mN(T) = [ma5(T) - ma5(T-N+1)] / ma5(T-N+1)
avg10mN(T) = [ma10(T) - ma10(T-N+1)] / ma10(T-N+1)
```

边界条件：均线为空、历史不足或分母为 0 时为空。

示例：`ma5(T)=10.50`，`ma5(T-4)=10.00`，则 `avg5m5=0.05`。

## 5. 短期收益 `ret1/ret2/ret3`

用途：描述极短周期收益节奏。

输入字段：`close`。

公式：

```text
retK(T) = close(T) / close(T-K) - 1
```

边界条件：历史不足或分母为 0 时为空。

示例：`close(T)=10.50`，`close(T-1)=10.00`，则 `ret1=0.05`。

## 6. 涨跌幅 `pct_chg`

用途：过滤极端涨跌日。

输入字段：优先使用 Tushare `daily.pct_chg`，必要时由前复权收盘价近似计算。

公式：

```text
pct_chg(T) = [close(T) / close(T-1) - 1] * 100
```

示例：`close(T)=10.50`，`close(T-1)=10.00`，则 `pct_chg=5.0`。

## 7. 偏离率 `bias_ma5/bias_ma10`

用途：衡量价格距离均线的偏离程度。

输入字段：`close`、`ma5`、`ma10`。

公式：

```text
bias_ma5(T) = [close(T) - ma5(T)] / ma5(T)
bias_ma10(T) = [close(T) - ma10(T)] / ma10(T)
```

边界条件：均线为空或为 0 时为空。

示例：`close=10.80`，`ma5=10.50`，则 `bias_ma5=0.028571`。

## 8. 振幅 `amp` 与 `amp5`

用途：衡量日内波动和近 5 日平均波动。

输入字段：`high`、`low`、`close`。

公式：

```text
amp(T) = [high(T) - low(T)] / close(T)
amp5(T) = mean(amp(T), ..., amp(T-4))
```

边界条件：价格缺失或 `close=0` 时为空；`amp5` 样本不足时为空。

示例：`high=10.50`，`low=10.00`，`close=10.20`，则 `amp=0.04902`。

## 9. 量能指标 `vol5/vol10/vr`

用途：衡量当前成交量相对近期均量的放大或缩小。

输入字段：`vol`。

公式：

```text
vol5(T) = mean(vol(T), ..., vol(T-4))
vol10(T) = mean(vol(T), ..., vol(T-9))
vr(T) = vol(T) / vol5(T)
```

边界条件：样本不足或 `vol5=0` 时为空。

示例：`vol(T)=1200`，`vol5(T)=1000`，则 `vr=1.2`。

## 10. 成交额指标 `amount5/amount10`

用途：衡量金额维度流动性。

输入字段：`amount`。

公式：

```text
amount5(T) = mean(amount(T), ..., amount(T-4))
amount10(T) = mean(amount(T), ..., amount(T-9))
```

示例：最近 5 日 amount 为 `[10000, 11000, 9000, 12000, 13000]`，则 `amount5=11000`。

## 11. 区间高低点 `high_N/low_N`

用途：判断突破、回撤和相对位置。

输入字段：`high`、`low`。

输出字段：`high_5`、`high_10`、`high_20`、`low_5`、`low_10`、`low_20`。

公式：

```text
high_N(T) = max(high(T), ..., high(T-N+1))
low_N(T) = min(low(T), ..., low(T-N+1))
```

边界条件：样本不足时为空。

示例：最近 5 日 high 为 `[10.2, 10.5, 10.4, 10.7, 10.6]`，则 `high_5=10.7`。

## 12. K 线形态字段

用途：描述日内强弱和影线结构。

常用字段：`close_pos_in_bar`、`body_pct`、`upper_shadow_pct`、`lower_shadow_pct`。

公式：

```text
close_pos_in_bar = (close - low) / (high - low)
body_pct = (close - open) / open
upper_shadow_pct = (high - max(open, close)) / close
lower_shadow_pct = (min(open, close) - low) / close
```

边界条件：分母为 0 或价格缺失时为空。

示例：`open=10`，`close=10.5`，`high=10.8`，`low=9.9`，则 `body_pct=0.05`，`close_pos_in_bar=0.6667`。

## 13. 交易约束字段

用途：避免回测和模拟交易在停牌、涨跌停或无价格时成交。

输入字段：`raw_open`、`up_limit`、`down_limit`、停牌记录。

口径：

```text
can_buy_open_t = 非停牌 且 raw_open 有效 且 未接近涨停 且 未接近跌停
can_sell_t = 非停牌 且 raw_open 有效 且 未接近跌停
```

示例：某日 `raw_open=10.00`，`up_limit=10.00`，则视为涨停开盘，`can_buy_open_t=0`；若 `down_limit=9.00` 且 `raw_open=9.00`，则 `can_sell_t=0`。

## 14. 指数环境字段

用途：把大盘状态纳入买入条件和评分。

来源：Tushare `index_daily` 计算上证、沪深 300、创业板指的收益、均线和动量。

命名：`sh_*`、`hs300_*`、`cyb_*`。

示例：`hs300_m20>0.02` 表示沪深 300 近 20 个交易日动量大于 2%。

## 15. 边界原则

所有指标只使用当前交易日及历史数据。T 日信号只能用于 T+1 或之后的成交，不能读取 T+1 开盘价来决定 T 日是否入选。
