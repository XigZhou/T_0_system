# 新 T+1 隔夜回测系统表达式说明

本文档说明当前系统中 `buy_condition` 与 `score_expression` 的用途、支持语法、可用字段与限制。

## 1. 两类表达式的区别

### 1.1 `buy_condition`

- 用途：筛选当天满足条件的候选股票
- 输入位置：前端“买入条件”
- 类型：布尔表达式集合
- 组合方式：用英文逗号分隔，表示全部同时满足，即 `AND`

示例：

```text
m20>0,m5>m5[1],vr<1.2,hs300_pct_chg>-0.8
```

含义：

1. `m20 > 0`
2. `m5 > m5[1]`
3. `vr < 1.2`
4. `hs300_pct_chg > -0.8`

### 1.2 `score_expression`

- 用途：对通过 `buy_condition` 的候选股票打分排序
- 输入位置：前端“评分表达式”
- 类型：算术表达式
- 输出要求：必须得到数值

示例：

```text
m20 + m5 - abs(pct_chg) * 0.1
```

系统会按得分从高到低排序，再取 `TopN`。

补充口径说明：

- 表达式里出现的 `open/high/low/close` 是处理后 `qfq_open/qfq_high/qfq_low/qfq_close` 的别名，用于信号计算与筛选。
- 实际回测成交价默认不用这 4 个字段成交，而是用原始除权口径的 `raw_close` 买入、`raw_open` 卖出。
- `raw_*` 价格列保留在 CSV 里供审计与成交使用，但当前不开放给表达式解析器直接调用。

## 2. `buy_condition` 支持语法

### 2.1 基础比较

支持：

- `>`
- `>=`
- `<`
- `<=`
- `==`
- `!=`
- `=`，会被当成 `==`

示例：

```text
m20>0
ma5>=ma10
close=high_20
```

### 2.2 字段对字段比较

示例：

```text
ma5>ma10
avg5m20>avg10m20
hs300_ma5>hs300_ma10
```

### 2.3 右侧倍数比较

示例：

```text
close<high*0.99
vol5>1.5vol
```

### 2.4 区间写法

示例：

```text
1.0<=vr<=1.5
-2.0<pct_chg<3.0
```

### 2.5 历史偏移写法

示例：

```text
m5>m5[1]
ret1>ret1[2]
```

说明：

- `m5[1]` 表示上一个交易日的 `m5`
- `ret1[2]` 表示向前第 2 个交易日的 `ret1`

### 2.6 分类字段等值比较

当前版本额外支持少量分类字段做等值筛选：

- `board`
- `market`

支持运算符：

- `=`
- `==`
- `!=`

示例：

```text
board=主板
market!=创业板
board=主板,listed_days>250
```

说明：

- 分类字段目前只允许出现在 `buy_condition`
- 分类字段不支持 `>`、`<`、区间比较
- 分类字段不支持历史偏移，如 `board[1]`

### 2.7 当前不支持的语法

当前版本不支持：

- `OR`
- `AND` 关键字
- 括号布尔嵌套
- `if/else`
- 任意字符串字段比较；目前仅 `board`、`market` 支持等值比较
- 直接对布尔字段写条件，如 `can_buy_t=true`

## 3. `score_expression` 支持语法

### 3.1 算术运算

支持：

- `+`
- `-`
- `*`
- `/`
- `%`
- `**`

示例：

```text
m20 + m5
avg5m20 - avg5m5
(m20 + m10) / 2
```

### 3.2 内置函数

支持：

- `abs(x)`
- `min(a,b)`
- `max(a,b)`
- `lag(field, n)`，前端更常用写法是 `field[n]`

示例：

```text
abs(pct_chg)
max(m20, m10)
m5 - m5[1]
```

### 3.3 当前不支持的函数

当前版本不支持：

- `sum`
- `mean`
- `rank`
- `log`
- `sqrt`
- 自定义函数

## 4. 当前可用字段清单

### 4.1 价格与涨跌

说明：以下 `open/high/low/close` 均为前复权信号口径别名，不是实际成交价字段。

- `open`
- `high`
- `low`
- `close`
- `pct_chg`

### 4.2 收益与动量

- `ret1`
- `ret2`
- `ret3`
- `m5`
- `m10`
- `m20`
- `m30`
- `m60`
- `m120`

### 4.3 均线与平滑动量

- `ma5`
- `ma10`
- `ma20`
- `avg5mN`
- `avg10mN`

示例：

- `avg5m5`
- `avg5m20`
- `avg10m60`

### 4.4 偏离率

- `bias_ma5`
- `bias_ma10`

### 4.5 量价波动

- `vol`
- `vol5`
- `vol10`
- `vr`
- `amount`
- `amount5`
- `amount10`
- `amp`
- `amp5`

### 4.6 区间高低点

- `high_N`
- `low_N`

示例：

- `high_5`
- `high_10`
- `high_20`
- `low_5`
- `low_10`
- `low_20`

### 4.7 指数前缀字段

支持以下三类前缀：

- `sh_*`
- `hs300_*`
- `cyb_*`

示例：

- `sh_pct_chg`
- `hs300_pct_chg`
- `cyb_ma5`
- `sh_m20`
- `hs300_avg5m20`
- `cyb_amp5`

### 4.8 快照与上市天数字段

- `listed_days`
- `total_mv_snapshot`
- `turnover_rate_snapshot`

示例：

- `listed_days>250`
- `total_mv_snapshot>8000000`
- `turnover_rate_snapshot<2`

### 4.9 隔夜研究特征

- `close_to_up_limit`
- `high_to_up_limit`
- `close_pos_in_bar`
- `body_pct`
- `upper_shadow_pct`
- `lower_shadow_pct`
- `vol_ratio_5`

示例：

- `close_to_up_limit<0.985`
- `close_pos_in_bar>0.6`
- `body_pct>0.01`
- `upper_shadow_pct<0.02`
- `vol_ratio_5<1.8`

### 4.10 短周期隔夜研究特征

- `ret_accel_3`
- `vol_ratio_3`
- `amount_ratio_3`
- `body_pct_3avg`
- `close_to_up_limit_3max`

示例：

- `ret_accel_3>-0.02`
- `vol_ratio_3<=1.1`
- `amount_ratio_3<=1.15`
- `body_pct_3avg>0.012`
- `close_to_up_limit_3max>=0.98`

## 5. 当前不能直接用于表达式的字段

虽然下面这些字段存在于 `processed_qfq/*.csv`，但当前版本不能直接写进表达式：

- `raw_open`
- `raw_high`
- `raw_low`
- `raw_close`
- `qfq_open`
- `qfq_high`
- `qfq_low`
- `qfq_close`
- `next_open`
- `next_close`
- `r_on`
- `next_raw_open`
- `next_raw_close`
- `r_on_raw`
- `industry`
- `up_limit`
- `down_limit`
- `is_suspended_t`
- `is_suspended_t1`
- `can_buy_t`
- `can_sell_t`
- `can_sell_t1`

补充说明：

- `board`、`market` 可以用于 `buy_condition` 的等值筛选，但不能用于 `score_expression`。
- `listed_days`、`total_mv_snapshot`、`turnover_rate_snapshot` 属于当前已开放的数值字段。
- 当前表达式解析器对白名单做了显式限制，交易约束字段、原始成交价字段、标签字段仍未开放。

## 6. 常见示例

### 6.1 趋势 + 量能 + 市场过滤

```text
m20>0,m5>m5[1],vr<1.2,hs300_pct_chg>-0.8
```

### 6.2 回撤日排序

```text
m20 + avg5m20 - abs(pct_chg) * 0.1
```

### 6.3 区间位置过滤

```text
close<high_20*0.98,m10>0
```

### 6.4 指数共振过滤

```text
hs300_pct_chg>0,cyb_pct_chg>0,m20>0
```

### 6.5 隔夜研究候选过滤

```text
listed_days>250,close_to_up_limit<0.985,close_pos_in_bar>0.60,upper_shadow_pct<0.02,body_pct>0.005,vol_ratio_5<1.8
```

### 6.6 隔夜研究排序

```text
close_pos_in_bar * 10 + body_pct * 100 - upper_shadow_pct * 100 - abs(close_to_up_limit - 0.975) * 50
```

### 6.7 第四版短周期条件

```text
listed_days>250,0.96<=close_to_up_limit<=0.995,body_pct>0.03,upper_shadow_pct<0.02,lower_shadow_pct<0.03,vol_ratio_5<=1.0,vol_ratio_3<=1.1,amount_ratio_3<=1.1,ret_accel_3>-0.015
```

### 6.8 第四版短周期排序

```text
body_pct_3avg * 100 + body_pct * 50 + close_pos_in_bar * 5 - abs(ret_accel_3) * 50 - abs(vol_ratio_3 - 1.0) * 10 - abs(amount_ratio_3 - 1.0) * 5 - abs(close_to_up_limit_3max - 0.99) * 100
```

## 7. 当前版本限制与后续扩展

当前版本有两个重要限制：

1. `buy_condition` 只支持逗号分隔的 `AND` 条件，不支持 `OR`
2. 表达式字段白名单没有开放全部 CSV 字段

如果后续要支持：

- `raw_close>20`
- `qfq_close/qfq_open` 直接写入表达式
- `can_buy_t=true`

就需要同步修改表达式解析器，而不是只改文档。
