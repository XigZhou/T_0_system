# T 日信号摆动回测系统表达式说明

本文档说明当前系统中 `buy_condition`、`sell_condition` 与 `score_expression` 的用途、支持语法、可用字段与限制。

## 1. 两类表达式的区别

### 1.1 `buy_condition`

- 用途：筛选 `T` 日满足条件的信号候选股票
- 输入位置：前端“买入条件”
- 类型：布尔条件集合
- 组合方式：英文逗号分隔，表示全部满足，也就是逻辑 `AND`

示例：

```text
m20>0,m5>m5[1],vr<1.2,hs300_pct_chg>-0.8
```

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
注意：

- 表达式中的 `open/high/low/close` 是前复权别名字段
- 实际成交默认不用这些字段成交，而是用 `raw_open`
- `buy_condition` 与 `score_expression` 都只看 `T` 日及历史数据，不读取未来数据

### 1.3 `sell_condition`

- 用途：在持仓期间的每个收盘后判断是否应当退出
- 输入位置：前端“卖出条件”或脚本参数 `sell_condition`
- 类型：布尔条件集合
- 执行方式：若条件在 `T` 日收盘后满足，且已经达到 `min_hold_days`，则安排在 `T+1` 日开盘卖出

示例：

```text
close<ma5
```

说明：

- `sell_condition` 的语法与 `buy_condition` 相同
- 它不在当日收盘直接成交，而是在下一交易日开盘成交
- 若未填写 `sell_condition`，系统按固定 `T+N` 或 `max_hold_days` 退出

## 2. `buy_condition` 支持语法

### 2.1 基础比较

支持：

- `>`
- `>=`
- `<`
- `<=`
- `==`
- `!=`
- `=`，会按 `==` 处理

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

含义：

- `m5[1]` 表示前 1 个交易日的 `m5`
- `ret1[2]` 表示前 2 个交易日的 `ret1`

### 2.6 分类字段等值比较

当前支持以下分类字段做等值筛选：

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

### 2.7 当前不支持的语法

当前版本不支持：

- `OR`
- `AND` 关键字
- 布尔括号嵌套
- `if/else`
- 任意字符串字段比较；目前只有 `board`、`market` 支持
- 直接对布尔字段写条件，例如 `can_buy_open_t=true`

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
(m20 + m10) / 2
body_pct_3avg * 100 - abs(ret_accel_3) * 50
```

### 3.2 内置函数

支持：

- `abs(x)`
- `min(a,b)`
- `max(a,b)`
- `lag(field, n)`，更常用的等价写法是 `field[n]`

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

## 4. 当前可用字段

### 4.1 价格与涨跌

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

- `high_5`
- `high_10`
- `high_20`
- `low_5`
- `low_10`
- `low_20`

### 4.7 快照字段

- `listed_days`
- `total_mv_snapshot`
- `turnover_rate_snapshot`
- `board`
- `market`

### 4.8 K 线研究特征

- `close_to_up_limit`
- `high_to_up_limit`
- `close_pos_in_bar`
- `body_pct`
- `upper_shadow_pct`
- `lower_shadow_pct`
- `vol_ratio_5`

### 4.9 短周期扩展特征

- `ret_accel_3`
- `vol_ratio_3`
- `amount_ratio_3`
- `body_pct_3avg`
- `close_to_up_limit_3max`

### 4.10 指数上下文

所有以下前缀字段都可以直接参与表达式：

- `sh_*`
- `hs300_*`
- `cyb_*`

示例：

- `hs300_pct_chg`
- `sh_m20`
- `cyb_amp5`

### 4.11 持仓态卖出字段

这些字段主要用于 `sell_condition`，在持仓期间由回测引擎动态提供：

- `days_held`
  当前已持有的交易日数量
- `holding_return`
  按当前收盘估值相对买入成本的持仓收益率
- `best_return_since_entry`
  自买入以来到当前为止的最大浮盈收益率
- `drawdown_from_peak`
  当前收益相对持仓历史最大浮盈的回撤幅度

示例：

```text
holding_return<-0.05
best_return_since_entry>0.08,drawdown_from_peak>0.04
days_held>=2,close<ma10
```

## 5. 当前不开放给表达式系统的字段

这些字段虽然存在于 `processed_qfq/*.csv` 中，但当前不能直接写进 `buy_condition` 或 `score_expression`：

- 原始成交价字段：`raw_open`、`raw_high`、`raw_low`、`raw_close`
- 参考标签字段：`next_open`、`next_close`、`r_on`、`next_raw_open`、`next_raw_close`、`r_on_raw`
- 成交约束布尔字段：`can_buy_t`、`can_buy_open_t`、`can_buy_open_t1`、`can_sell_t`、`can_sell_t1`
- 停牌字段：`is_suspended_t`、`is_suspended_t1`

原因：

- 原始成交字段主要用于真实成交与审计，不直接参与信号评分
- 未来标签字段会造成未来函数
- 布尔约束字段属于执行层逻辑，不建议混进信号表达式

## 6. 与当前回测模型的关系

当前系统回测口径是：

1. `T` 日用表达式筛选并打分
2. `T+1` 日开盘尝试买入
3. `T+N` 日开盘卖出，`2 <= N <= 5`

因此表达式系统的职责是：

- 决定 `T` 日该不该发出信号
- 决定多只股票里谁优先级更高

表达式系统不负责：

- 决定实际买入是否成交
- 决定卖出日是否因跌停/停牌而顺延
- 直接读取未来的 `T+1`、`T+N` 标签

## 7. 常见示例

### 7.1 趋势延续型

```text
buy_condition: listed_days>250,m20>0.03,m5>0,vr<1.8,pct_chg>-1.0,pct_chg<5.5
score_expression: m20 * 120 + m5 * 80 + close_pos_in_bar * 5 + body_pct * 40 - upper_shadow_pct * 60
```

### 7.2 强收盘但不过热

```text
buy_condition: listed_days>250,close_pos_in_bar>0.60,body_pct>-0.01,upper_shadow_pct<0.025,vol_ratio_5<1.5
score_expression: close_pos_in_bar * 8 + body_pct * 80 - upper_shadow_pct * 80 + m20 * 100
```

### 7.3 大市值主板过滤

```text
buy_condition: board=主板,listed_days>250,total_mv_snapshot>8000000,turnover_rate_snapshot<3,m20>0.02
score_expression: m20 * 120 + m5 * 80 - amp * 50 - abs(vr - 1.0) * 3
```
