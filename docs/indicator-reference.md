# T 日信号摆动回测系统指标说明

本文档说明 `processed_qfq/*.csv` 中主要指标的用途、输入字段、计算公式、窗口参数、边界条件，以及带数字的示例。除特别说明外，指标均基于前复权价格计算。

## 1. 价格动量 `mN`

- 指标用途：衡量当前价格相对窗口起点的涨跌幅
- 输入字段：`close`
- 输出字段：`m5`、`m10`、`m20`、`m30`、`m60`、`m120`
- 窗口参数：`N ∈ {5, 10, 20, 30, 60, 120}`

计算公式：

```text
mN(T) = [close(T) - close(T-N+1)] / close(T-N+1)
```

边界条件：

- 历史样本不足 `N` 条时为空
- 分母为 0 时为空
- 不使用未来数据

示例：

```text
close(T)=11.00
close(T-4)=10.00
m5(T)=(11.00-10.00)/10.00=0.10
```

## 2. 均线 `maN`

- 指标用途：平滑短期噪音，辅助判断趋势
- 输入字段：`close`
- 输出字段：`ma5`、`ma10`、`ma20`
- 窗口参数：`N ∈ {5, 10, 20}`

计算公式：

```text
maN(T) = mean(close(T), close(T-1), ..., close(T-N+1))
```

边界条件：

- 样本不足 `N` 条时为空

示例：

```text
最近 5 日 close = [10.00, 10.20, 10.10, 10.40, 10.30]
ma5 = 10.20
```

## 3. 平滑动量 `avg5mN` 与 `avg10mN`

- 指标用途：用均线动量代替原始价格动量，降低波动噪音
- 输入字段：`ma5`、`ma10`
- 输出字段：`avg5m5~avg5m120`、`avg10m5~avg10m120`
- 窗口参数：与 `mN` 相同

计算公式：

```text
avg5mN(T) = [ma5(T) - ma5(T-N+1)] / ma5(T-N+1)
avg10mN(T) = [ma10(T) - ma10(T-N+1)] / ma10(T-N+1)
```

边界条件：

- 均线本身为空时为空
- 分母为 0 时为空

示例：

```text
ma5(T)=10.50
ma5(T-4)=10.00
avg5m5=(10.50-10.00)/10.00=0.05
```

## 4. 短期收益 `ret1`、`ret2`、`ret3`

- 指标用途：描述极短周期收益节奏
- 输入字段：`close`
- 输出字段：`ret1`、`ret2`、`ret3`

计算公式：

```text
ret1(T) = close(T) / close(T-1) - 1
ret2(T) = close(T) / close(T-2) - 1
ret3(T) = close(T) / close(T-3) - 1
```

边界条件：

- 历史不足时为空
- 分母为 0 时为空

示例：

```text
close(T)=10.50
close(T-1)=10.00
ret1=0.05
```

## 5. 涨跌幅 `pct_chg`

- 指标用途：快速过滤极端涨跌日
- 输入字段：`close`
- 输出字段：`pct_chg`

计算公式：

```text
pct_chg(T) = [close(T) / close(T-1) - 1] * 100
```

边界条件：

- 前一日收盘为空时为空

示例：

```text
close(T)=10.50
close(T-1)=10.00
pct_chg=5.0
```

## 6. 偏离率 `bias_ma5`、`bias_ma10`

- 指标用途：衡量价格距离均线的偏离程度
- 输入字段：`close`、`ma5`、`ma10`
- 输出字段：`bias_ma5`、`bias_ma10`

计算公式：

```text
bias_ma5(T) = [close(T) - ma5(T)] / ma5(T)
bias_ma10(T) = [close(T) - ma10(T)] / ma10(T)
```

边界条件：

- 均线为空或为 0 时为空

示例：

```text
close=10.80
ma5=10.50
bias_ma5=(10.80-10.50)/10.50=0.028571
```

## 7. 振幅 `amp` 与 `amp5`

- 指标用途：衡量单日波动与近 5 日平均波动
- 输入字段：`high`、`low`、`close`
- 输出字段：`amp`、`amp5`

计算公式：

```text
amp(T) = [high(T) - low(T)] / close(T)
amp5(T) = mean(amp(T), ..., amp(T-4))
```

边界条件：

- `close(T)=0` 时为空
- `amp5` 样本不足时为空

示例：

```text
high=10.50
low=10.00
close=10.20
amp=0.04902
```

## 8. 量能指标 `vol5`、`vol10`、`vr`

- 指标用途：衡量当前成交量相对近期均量的放大或缩小
- 输入字段：`vol`
- 输出字段：`vol5`、`vol10`、`vr`

计算公式：

```text
vol5(T) = mean(vol(T), ..., vol(T-4))
vol10(T) = mean(vol(T), ..., vol(T-9))
vr(T) = vol(T) / vol5(T)
```

边界条件：

- 样本不足时为空
- `vol5(T)=0` 时 `vr` 为空

示例：

```text
vol(T)=1200
vol5(T)=1000
vr=1.2
```

## 9. 资金活跃度 `amount5`、`amount10`

- 指标用途：衡量金额维度的流动性
- 输入字段：`amount`
- 输出字段：`amount5`、`amount10`

计算公式：

```text
amount5(T) = mean(amount(T), ..., amount(T-4))
amount10(T) = mean(amount(T), ..., amount(T-9))
```

边界条件：

- 样本不足时为空

示例：

```text
最近 5 日 amount = [10000, 11000, 9000, 12000, 13000]
amount5=11000
```

## 10. 区间高低点 `high_N`、`low_N`

- 指标用途：判断突破、回撤和相对位置
- 输入字段：`high`、`low`
- 输出字段：`high_5`、`high_10`、`high_20`、`low_5`、`low_10`、`low_20`
- 窗口参数：`N ∈ {5, 10, 20}`

计算公式：

```text
high_N(T) = max(high(T), ..., high(T-N+1))
low_N(T) = min(low(T), ..., low(T-N+1))
```

边界条件：

- 样本不足时为空

示例：

```text
最近 5 日 high = [10.2, 10.5, 10.4, 10.7, 10.6]
high_5 = 10.7
```

## 11. K 线形态研究特征

### 11.1 `close_to_up_limit`

- 指标用途：衡量收盘价是否逼近涨停
- 输入字段：`raw_close`、`up_limit`
- 计算公式：`close_to_up_limit = raw_close / up_limit`
- 边界条件：`up_limit` 缺失或为 0 时为空

示例：

```text
raw_close=10.30
up_limit=11.33
close_to_up_limit=0.909973
```

### 11.2 `high_to_up_limit`

- 指标用途：衡量盘中最高价是否逼近涨停
- 输入字段：`raw_high`、`up_limit`
- 计算公式：`high_to_up_limit = raw_high / up_limit`
- 边界条件：同上

### 11.3 `close_pos_in_bar`

- 指标用途：衡量收盘在日内振幅中的相对位置
- 输入字段：`raw_low`、`raw_high`、`raw_close`
- 计算公式：

```text
close_pos_in_bar = (raw_close - raw_low) / (raw_high - raw_low)
```

- 边界条件：`raw_high == raw_low` 时为空

示例：

```text
raw_low=9.80
raw_high=10.40
raw_close=10.30
close_pos_in_bar=(10.30-9.80)/(10.40-9.80)=0.833333
```

### 11.4 `body_pct`

- 指标用途：衡量实体强弱
- 输入字段：`raw_open`、`raw_close`
- 计算公式：

```text
body_pct = (raw_close - raw_open) / raw_open
```

- 边界条件：`raw_open=0` 时为空

示例：

```text
raw_open=10.00
raw_close=10.30
body_pct=0.03
```

### 11.5 `upper_shadow_pct` 与 `lower_shadow_pct`

- 指标用途：识别冲高回落或下探回收程度
- 输入字段：`raw_open`、`raw_close`、`raw_high`、`raw_low`
- 计算公式：

```text
upper_shadow_pct = (raw_high - max(raw_open, raw_close)) / raw_open
lower_shadow_pct = (min(raw_open, raw_close) - raw_low) / raw_open
```

- 边界条件：`raw_open=0` 时为空

## 12. 短周期扩展特征

### 12.1 `vol_ratio_5`

- 指标用途：识别当日量相对 5 日均量的放大倍数
- 输入字段：`vol`、`vol5`
- 计算公式：`vol_ratio_5 = vol / vol5`
- 边界条件：`vol5=0` 时为空

### 12.2 `ret_accel_3`

- 指标用途：衡量 1 日收益相对 3 日收益均速的加速度
- 输入字段：`ret1`、`ret3`
- 计算公式：

```text
ret_accel_3 = ret1 - ret3 / 3
```

示例：

```text
ret1=0.0092
ret3=0.0680
ret_accel_3=0.0092-0.0680/3=-0.013467
```

### 12.3 `vol_ratio_3`、`amount_ratio_3`

- 指标用途：衡量当日量能和金额相对 3 日均值的偏离
- 输入字段：`vol`、`amount`
- 计算公式：

```text
vol_ratio_3 = vol / mean(vol(T), vol(T-1), vol(T-2))
amount_ratio_3 = amount / mean(amount(T), amount(T-1), amount(T-2))
```

### 12.4 `body_pct_3avg`

- 指标用途：平滑近 3 日实体强弱
- 输入字段：`body_pct`
- 计算公式：`body_pct_3avg = mean(body_pct(T), body_pct(T-1), body_pct(T-2))`

### 12.5 `close_to_up_limit_3max`

- 指标用途：观察最近 3 日最接近涨停的程度
- 输入字段：`close_to_up_limit`
- 计算公式：`close_to_up_limit_3max = max(close_to_up_limit(T), close_to_up_limit(T-1), close_to_up_limit(T-2))`

## 13. 参考标签与当前主标签的区别

### 13.1 参考单日标签 `r_on` 与 `r_on_raw`

- 指标用途：保留旧的一日隔夜参考标签，便于对照和调试
- 输入字段：
  - `r_on` 使用 `close` 与 `next_open`
  - `r_on_raw` 使用 `raw_close` 与 `next_raw_open`
- 计算公式：

```text
r_on(T) = next_open(T) / close(T) - 1
r_on_raw(T) = next_raw_open(T) / raw_close(T) - 1
```

边界条件：

- 最后一行通常为空
- 不再是当前主回测收益口径

### 13.2 当前主研究标签

当前系统真正研究的是：

```text
主标签(T, N) = T+1 日原始开盘买入，到 T+N 日原始开盘卖出的净收益
```

其中：

- `N` 当前支持 `2~5`
- 买卖手续费、滑点、最低佣金由回测请求参数控制
- 若严格成交模式下 `T+N` 日无法卖出，则顺延到下一个可卖开盘
