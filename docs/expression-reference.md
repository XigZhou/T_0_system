# 表达式说明

本文档说明当前系统中 `buy_condition`、`sell_condition` 与 `score_expression` 的用途、支持语法、可用字段与限制。表达式字段来自 SQLite 主库 `stock_daily_features`。

## 1. 表达式类型

### 1.1 `buy_condition`

用途：筛选 T 日满足条件的信号候选股票。英文逗号分隔，表示全部满足，也就是逻辑 AND。

示例：

```text
m20>0,m5>m5[1],vr<1.2,hs300_pct_chg>-0.8
```

### 1.2 `sell_condition`

用途：持仓期间每天收盘后判断是否应退出。若条件在 T 日满足且达到 `min_hold_days`，系统安排 T+1 开盘卖出。

示例：

```text
close<ma5
```

### 1.3 `score_expression`

用途：对通过买入条件的候选股票打分排序。

示例：

```text
m20 + m5 - abs(pct_chg) * 0.1
```

说明：`open/high/low/close` 是前复权信号价格，实际成交默认使用 `raw_open`。

## 2. 条件语法

基础比较支持：`>`、`>=`、`<`、`<=`、`==`、`!=`、`=`。

示例：

```text
m20>0
ma5>=ma10
close=high_20
```

字段对字段比较：

```text
ma5>ma10
avg5m20>avg10m20
hs300_ma5>hs300_ma10
```

倍数比较：

```text
close<high*0.99
vol5>1.5vol
```

区间写法：

```text
1.0<=vr<=1.5
-2.0<pct_chg<3.0
```

历史偏移：

```text
m5>m5[1]
ret1>ret1[2]
```

`m5[1]` 表示前 1 个交易日的 `m5`。历史偏移只能回看，不能引用未来。

分类字段等值比较支持 `board`、`market`：

```text
board=主板
market!=创业板
board=主板,listed_days>250
```

## 3. 评分语法

支持算术运算：`+`、`-`、`*`、`/`、`%`、`**`。

支持函数：`abs(x)`、`min(a,b)`、`max(a,b)`、`lag(field,n)`。

示例：

```text
(m20 + m10) / 2
body_pct_3avg * 100 - abs(ret_accel_3) * 50
m5 - lag(m5, 1)
```

常用等价写法：`m5[1]` 等价于 `lag(m5, 1)`。

## 4. 当前可用字段

价格与涨跌：`open`、`high`、`low`、`close`、`raw_open`、`raw_close`、`pct_chg`。

收益与动量：`ret1`、`ret2`、`ret3`、`m5`、`m10`、`m20`、`m30`、`m60`、`m120`。

均线和平滑动量：`ma5`、`ma10`、`ma20`、`avg5m5`、`avg5m10`、`avg5m20`、`avg5m30`、`avg5m60`、`avg5m120`、`avg10m5`、`avg10m10`、`avg10m20`、`avg10m30`、`avg10m60`、`avg10m120`。

量价波动：`vol`、`vol5`、`vol10`、`vr`、`amount`、`amount5`、`amount10`、`amp`、`amp5`。

形态和区间：`bias_ma5`、`bias_ma10`、`high_5`、`high_10`、`high_20`、`low_5`、`low_10`、`low_20`、`close_pos_in_bar`、`body_pct`、`upper_shadow_pct`、`lower_shadow_pct`、`vol_ratio_5`、`ret_accel_3`、`vol_ratio_3`、`amount_ratio_3`、`body_pct_3avg`、`close_to_up_limit_3max`。

交易约束和基础面：`can_buy_open_t`、`can_sell_t`、`listed_days`、`total_mv_snapshot`、`turnover_rate_snapshot`、`board`、`market`。

指数环境：`sh_pct_chg`、`sh_m5`、`sh_m20`、`sh_m60`、`hs300_pct_chg`、`hs300_m5`、`hs300_m20`、`hs300_m60`、`cyb_pct_chg`、`cyb_m5`、`cyb_m20`、`cyb_m60`，以及同名前缀的均线和收盘字段。

## 5. 不支持的语法

当前不支持：`OR`、`AND` 关键字、复杂布尔括号嵌套、`if/else`、`sum`、`mean`、`rank`、`log`、`sqrt`、任意字符串字段比较。直接写布尔字面量如 `can_buy_open_t=true` 也不支持，可使用 `can_buy_open_t==1`。

## 6. 异常处理

字段不存在、函数不支持、除零、表达式结果非数值或历史偏移超出可用范围时，后端会返回错误或把该候选过滤掉。策略上线前应先用单股回测和短区间组合回测确认表达式行为。
