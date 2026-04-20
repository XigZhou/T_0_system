# 新 T+1 隔夜回测系统指标说明

本文档说明 `processed_qfq/*.csv` 中主要指标的用途、公式、边界条件与示例。

## 1. 价格动量 `mN`

- 指标名称：N 日价格动量
- 输出字段名：`m5`、`m10`、`m20`、`m30`、`m60`、`m120`
- 指标用途：衡量当前收盘价相对过去某一窗口起点的涨跌幅
- 适用频率：日频

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| close | 前复权收盘价 | `processed_qfq/*.csv` | 即 `qfq_close` |

### 计算公式

```text
mN(T) = [close(T) - close(T-N+1)] / close(T-N+1)
```

### 参数说明

- 窗口长度：`5/10/20/30/60/120`
- 默认参数：固定为上述六组窗口

### 边界条件

- 历史不足 `N` 条时为空
- 基准价格为 0 时为空
- 不使用未来数据

### 计算示例

```text
close(T)=11.00
close(T-4)=10.00
m5(T)=(11.00-10.00)/10.00=0.10
```

### 风险与解释

- 对趋势延续敏感
- 窗口越短越容易被短期波动放大

## 2. 均线 `maN`

- 指标名称：N 日均线
- 输出字段名：`ma5`、`ma10`、`ma20`
- 指标用途：平滑价格噪音，辅助判断趋势与价格偏离

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| close | 前复权收盘价 | `processed_qfq/*.csv` | |

### 计算公式

```text
maN(T) = mean(close(T), close(T-1), ..., close(T-N+1))
```

### 边界条件

- 样本不足 `N` 条时为空

### 计算示例

```text
最近 5 日 close = [10.00, 10.20, 10.10, 10.40, 10.30]
ma5 = (10.00 + 10.20 + 10.10 + 10.40 + 10.30) / 5 = 10.20
```

## 3. 平滑动量 `avg5mN` 与 `avg10mN`

- 指标名称：均线动量
- 输出字段名：`avg5m5~avg5m120`、`avg10m5~avg10m120`
- 指标用途：用均线代替原始价格，降低短期噪音

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| ma5 | 5 日均线 | `processed_qfq/*.csv` | 对应 `avg5mN` |
| ma10 | 10 日均线 | `processed_qfq/*.csv` | 对应 `avg10mN` |

### 计算公式

```text
avg5mN(T) = [ma5(T) - ma5(T-N+1)] / ma5(T-N+1)
avg10mN(T) = [ma10(T) - ma10(T-N+1)] / ma10(T-N+1)
```

### 边界条件

- 均线本身样本不足时为空
- `ma5(T-N+1)` 或 `ma10(T-N+1)` 为 0 时为空

### 计算示例

```text
ma5(T)=10.50
ma5(T-4)=10.00
avg5m5=(10.50-10.00)/10.00=0.05
```

## 4. 短期收益 `ret1`、`ret2`、`ret3`

- 指标名称：1/2/3 日收益
- 输出字段名：`ret1`、`ret2`、`ret3`
- 指标用途：描述极短周期的价格变化

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| close | 前复权收盘价 | `processed_qfq/*.csv` | |

### 计算公式

```text
ret1(T) = close(T) / close(T-1) - 1
ret2(T) = close(T) / close(T-2) - 1
ret3(T) = close(T) / close(T-3) - 1
```

### 计算示例

```text
close(T)=10.50
close(T-1)=10.00
ret1=10.50/10.00-1=0.05
```

## 5. 涨跌幅 `pct_chg`

- 指标名称：当日涨跌幅
- 输出字段名：`pct_chg`
- 指标用途：在表达式里快速过滤极端涨跌日

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| close | 前复权收盘价 | `processed_qfq/*.csv` | |

### 计算公式

```text
pct_chg(T) = [close(T) / close(T-1) - 1] * 100
```

### 说明

- 本系统内部 `pct_chg` 用百分比数值
- 若 `close(T-1)` 缺失，则为空

## 6. 偏离率 `bias_ma5`、`bias_ma10`

- 指标名称：均线偏离率
- 输出字段名：`bias_ma5`、`bias_ma10`
- 指标用途：衡量价格离均线有多远

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| close | 前复权收盘价 | `processed_qfq/*.csv` | |
| ma5 / ma10 | 5/10 日均线 | `processed_qfq/*.csv` | |

### 计算公式

```text
bias_ma5(T) = [close(T) - ma5(T)] / ma5(T)
bias_ma10(T) = [close(T) - ma10(T)] / ma10(T)
```

### 计算示例

```text
close=10.80
ma5=10.50
bias_ma5=(10.80-10.50)/10.50=0.028571
```

## 7. 振幅 `amp` 与 `amp5`

- 指标名称：单日振幅与 5 日平均振幅
- 输出字段名：`amp`、`amp5`
- 指标用途：识别波动过大或过小的交易日

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| high | 前复权最高价 | `processed_qfq/*.csv` | |
| low | 前复权最低价 | `processed_qfq/*.csv` | |
| close | 前复权收盘价 | `processed_qfq/*.csv` | |

### 计算公式

```text
amp(T) = [high(T) - low(T)] / close(T)
amp5(T) = mean(amp(T), amp(T-1), ..., amp(T-4))
```

### 边界条件

- `close(T)=0` 时为空
- `amp5` 样本不足 5 条时为空

### 计算示例

```text
high=10.50
low=10.00
close=10.20
amp=(10.50-10.00)/10.20=0.04902
```

## 8. 均量 `vol5`、`vol10` 与量比 `vr`

- 指标名称：5/10 日平均成交量与量比
- 输出字段名：`vol5`、`vol10`、`vr`
- 指标用途：衡量当前成交量相对近期均量的放大或缩小

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| vol | 成交量 | `processed_qfq/*.csv` | 原始日线透传 |

### 计算公式

```text
vol5(T) = mean(vol(T), vol(T-1), ..., vol(T-4))
vol10(T) = mean(vol(T), vol(T-1), ..., vol(T-9))
vr(T) = vol(T) / vol5(T)
```

### 边界条件

- 均量窗口不足时为空
- `vol5(T)=0` 时 `vr` 为空

### 计算示例

```text
vol(T)=1200
过去 5 日均量 vol5=1000
vr=1200/1000=1.2
```

## 9. 金额均值 `amount5`、`amount10`

- 指标名称：5/10 日平均成交额
- 输出字段名：`amount5`、`amount10`
- 指标用途：判断金额维度的流动性

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| amount | 成交额 | `processed_qfq/*.csv` | 原始日线透传 |

### 计算公式

```text
amount5(T) = mean(amount(T), amount(T-1), ..., amount(T-4))
amount10(T) = mean(amount(T), amount(T-1), ..., amount(T-9))
```

## 10. 区间高低点 `high_N`、`low_N`

- 指标名称：N 日区间最高价与最低价
- 输出字段名：`high_5`、`high_10`、`high_20`、`low_5`、`low_10`、`low_20`
- 指标用途：做突破、回撤位置与相对位置判断

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| high | 前复权最高价 | `processed_qfq/*.csv` | |
| low | 前复权最低价 | `processed_qfq/*.csv` | |

### 计算公式

```text
high_N(T) = max(high(T), high(T-1), ..., high(T-N+1))
low_N(T) = min(low(T), low(T-1), ..., low(T-N+1))
```

### 计算示例

```text
最近 5 日 high = [10.2, 10.5, 10.4, 10.7, 10.6]
high_5 = 10.7
```

## 11. 隔夜标签 `r_on`

- 指标名称：隔夜收益标签
- 输出字段名：`r_on`
- 指标用途：衡量 `T` 日收盘买入、`T+1` 日开盘卖出的原始隔夜收益

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| close | T 日前复权收盘价 | `processed_qfq/*.csv` | |
| next_open | 下一交易日前复权开盘价 | `processed_qfq/*.csv` | |

### 计算公式

```text
r_on(T) = next_open(T) / close(T) - 1
```

### 边界条件

- 最后一行没有下一日开盘价，因此为空
- 若下一交易日停牌或缺价，也为空

### 计算示例

```text
close(T)=10.00
next_open(T)=10.30
r_on=10.30/10.00-1=0.03
```

## 12. 指数前缀字段 `sh_*`、`hs300_*`、`cyb_*`

- 指标名称：指数上下文字段
- 输出字段名：如 `hs300_pct_chg`、`sh_m20`、`cyb_amp5`
- 指标用途：在个股筛选时引入市场环境过滤

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| index_daily 原始列 | 指数日线 | `market_context.csv` | 先独立计算，再按日期合并 |

### 说明

1. 计算公式与个股同口径。
2. 只是数据源不同，字段前缀不同。
3. 例如：

```text
hs300_pct_chg > -0.8
```

表示当日沪深300涨跌幅不低于 `-0.8%`。

## 13. 原始隔夜标签 `r_on_raw`

- 指标名称：原始成交口径隔夜收益
- 输出字段名：`r_on_raw`
- 指标用途：衡量 `T` 日按原始收盘价买入、`T+1` 日按原始开盘价卖出的毛收益

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| raw_close | `T` 日原始收盘价 | `processed_qfq/*.csv` | |
| next_raw_open | 下一交易日原始开盘价 | `processed_qfq/*.csv` | |

### 计算公式

```text
r_on_raw(T) = next_raw_open(T) / raw_close(T) - 1
```

### 边界条件

- 最后一行没有下一日原始开盘价时为空
- 下一交易日停牌或缺价时为空

### 计算示例

```text
raw_close(T)=10.30
next_raw_open(T)=10.50
r_on_raw=10.50/10.30-1=0.019417
```

## 14. 涨停距离 `close_to_up_limit` 与 `high_to_up_limit`

- 指标名称：收盘/最高价距离涨停比例
- 输出字段名：`close_to_up_limit`、`high_to_up_limit`
- 指标用途：衡量个股是否已经逼近涨停，从而辅助识别“强但不过热”的隔夜买点

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| raw_close | 原始收盘价 | `processed_qfq/*.csv` | 对应 `close_to_up_limit` |
| raw_high | 原始最高价 | `processed_qfq/*.csv` | 对应 `high_to_up_limit` |
| up_limit | 涨停价 | `processed_qfq/*.csv` | |

### 计算公式

```text
close_to_up_limit(T) = raw_close(T) / up_limit(T)
high_to_up_limit(T) = raw_high(T) / up_limit(T)
```

### 边界条件

- `up_limit` 缺失时为空
- 指标大于等于 1 说明价格已触及或逼近涨停

### 计算示例

```text
raw_close=10.30
raw_high=10.40
up_limit=11.33
close_to_up_limit=10.30/11.33=0.909091
high_to_up_limit=10.40/11.33=0.917917
```

## 15. K 线区间位置 `close_pos_in_bar`

- 指标名称：收盘价在当日振幅区间中的位置
- 输出字段名：`close_pos_in_bar`
- 指标用途：判断收盘是否接近当日高位，辅助识别“尾盘收得强不强”

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| raw_high | 原始最高价 | `processed_qfq/*.csv` | |
| raw_low | 原始最低价 | `processed_qfq/*.csv` | |
| raw_close | 原始收盘价 | `processed_qfq/*.csv` | |

### 计算公式

```text
close_pos_in_bar(T) = [raw_close(T) - raw_low(T)] / [raw_high(T) - raw_low(T)]
```

### 边界条件

- 若 `raw_high = raw_low`，则为空
- 结果越接近 1，说明收盘越靠近当日高位

### 计算示例

```text
raw_high=10.40
raw_low=9.80
raw_close=10.30
close_pos_in_bar=(10.30-9.80)/(10.40-9.80)=0.833333
```

## 16. 实体与上下影线比例 `body_pct`、`upper_shadow_pct`、`lower_shadow_pct`

- 指标名称：K 线实体与影线比例
- 输出字段名：`body_pct`、`upper_shadow_pct`、`lower_shadow_pct`
- 指标用途：识别冲高回落、尾盘抢筹或长下影等形态

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| raw_open | 原始开盘价 | `processed_qfq/*.csv` | |
| raw_high | 原始最高价 | `processed_qfq/*.csv` | |
| raw_low | 原始最低价 | `processed_qfq/*.csv` | |
| raw_close | 原始收盘价 | `processed_qfq/*.csv` | |

### 计算公式

```text
body_pct(T) = [raw_close(T) - raw_open(T)] / raw_open(T)
upper_shadow_pct(T) = [raw_high(T) - max(raw_open(T), raw_close(T))] / raw_open(T)
lower_shadow_pct(T) = [min(raw_open(T), raw_close(T)) - raw_low(T)] / raw_open(T)
```

### 边界条件

- `raw_open=0` 时为空
- `body_pct` 为正表示阳线，为负表示阴线

### 计算示例

```text
raw_open=10.00
raw_high=10.40
raw_low=9.80
raw_close=10.30
body_pct=(10.30-10.00)/10.00=0.03
upper_shadow_pct=(10.40-10.30)/10.00=0.01
lower_shadow_pct=(10.00-9.80)/10.00=0.02
```

## 17. 5 日量能比 `vol_ratio_5`

- 指标名称：当前成交量相对 5 日均量的比例
- 输出字段名：`vol_ratio_5`
- 指标用途：判断当天放量或缩量程度，比直接用 `vr` 更适合做研究报表分层

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| vol | 当日成交量 | `processed_qfq/*.csv` | 原始日线透传 |
| vol5 | 5 日平均成交量 | `processed_qfq/*.csv` | |

### 计算公式

```text
vol_ratio_5(T) = vol(T) / vol5(T)
```

### 边界条件

- `vol5=0` 或缺失时为空
- 与 `vr` 在数值上接近，但该字段明确作为隔夜研究特征保留

### 计算示例

```text
vol=1500
vol5=1300
vol_ratio_5=1500/1300=1.153846
```

## 18. 3 日动量加速度 `ret_accel_3`

- 指标名称：1 日收益相对 3 日累计收益的加速度
- 输出字段名：`ret_accel_3`
- 指标用途：判断最近 1 天的强弱是否相对最近 3 天均速在加速或减速

### 输入字段

| 字段名 | 中文含义 | 来源文件 | 备注 |
| --- | --- | --- | --- |
| ret1 | 1 日收益 | `processed_qfq/*.csv` | 由前复权价计算 |
| ret3 | 3 日收益 | `processed_qfq/*.csv` | 由前复权价计算 |

### 计算公式

```text
ret_accel_3(T) = ret1(T) - ret3(T) / 3
```

### 解释

- 大于 0：最近 1 天强于最近 3 天平均速度
- 小于 0：最近 1 天相对 3 天均速在减速

## 19. 3 日量能与金额比 `vol_ratio_3`、`amount_ratio_3`

- 指标名称：当日成交量/成交额相对 3 日均值的比例
- 输出字段名：`vol_ratio_3`、`amount_ratio_3`
- 指标用途：比 `vol_ratio_5` 更敏感地识别最近 2 到 3 日是否突然放量

### 计算公式

```text
vol_ratio_3(T) = vol(T) / mean(vol(T), vol(T-1), vol(T-2))
amount_ratio_3(T) = amount(T) / mean(amount(T), amount(T-1), amount(T-2))
```

### 边界条件

- 前 2 个样本不足时为空
- 分母为 0 时为空

## 20. 3 日实体均值 `body_pct_3avg`

- 指标名称：最近 3 日实体涨跌幅平均值
- 输出字段名：`body_pct_3avg`
- 指标用途：识别最近 3 日是否持续出现偏强实体，而不是单日偶发拉升

### 计算公式

```text
body_pct_3avg(T) = mean(body_pct(T), body_pct(T-1), body_pct(T-2))
```

## 21. 3 日近涨停记忆 `close_to_up_limit_3max`

- 指标名称：最近 3 日收盘距涨停比例的最大值
- 输出字段名：`close_to_up_limit_3max`
- 指标用途：识别最近 3 日内是否至少有一天非常接近涨停，从而保留“近涨停记忆”

### 计算公式

```text
close_to_up_limit_3max(T) = max(close_to_up_limit(T), close_to_up_limit(T-1), close_to_up_limit(T-2))
```
