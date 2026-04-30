# 独立板块研究指标说明

本文档说明 `sector_research/` 生成的主题强度、板块强度和个股主题暴露指标。除特别说明外，指标只使用当日及历史板块数据，不使用未来数据。

## 1. 板块动量 `mN`

- 指标用途：衡量板块指数相对窗口起点的涨跌幅
- 输入字段：`sector_board_daily.csv` 中的 `close`
- 输出字段：`m5`、`m20`、`m60`、`m120`、`m250`
- 窗口参数：`N ∈ {5,20,60,120,250}`

计算公式：

```text
mN(T) = close(T) / close(T-N+1) - 1
```

边界条件：

- 历史样本不足 `N` 条时为空
- 分母为 0 或缺失时为空

示例：

```text
close(T)=1100
close(T-4)=1000
m5=1100/1000-1=0.10
```

## 2. 成交额放大倍数 `amount_ratio_20`

- 指标用途：衡量板块成交额是否相对近期均值放大
- 输入字段：`amount`
- 输出字段：`amount20`、`amount_ratio_20`
- 窗口参数：20 个交易日，最少 5 个样本

计算公式：

```text
amount20(T) = mean(amount(T), ..., amount(T-19))
amount_ratio_20(T) = amount(T) / amount20(T)
```

边界条件：

- 有效样本少于 5 条时为空
- `amount20=0` 时为空

示例：

```text
当日成交额=240亿元
20日均成交额=200亿元
amount_ratio_20=240/200=1.2
```

## 3. 位置与回撤

- 指标用途：判断板块处在长周期区间高位还是低位修复
- 输入字段：`close`、`high`、`low`
- 输出字段：`drawdown_from_120_high`、`position_in_250_range`

计算公式：

```text
drawdown_from_120_high(T) = close(T) / high_120(T) - 1
position_in_250_range(T) = [close(T) - low_250(T)] / [high_250(T) - low_250(T)]
```

边界条件：

- `high_120` 至少需要 20 个样本
- `high_250`、`low_250` 至少需要 40 个样本
- `high_250 == low_250` 时区间位置为空

示例：

```text
close=900
high_120=1000
drawdown_from_120_high=900/1000-1=-0.10

low_250=700
high_250=1100
position_in_250_range=(900-700)/(1100-700)=0.5
```

## 4. 量价齐升分 `volume_price_score`

- 指标用途：寻找趋势延续、成交额同步放大的板块
- 输入字段：`m5`、`m20`、`m60`、`amount_ratio_20`、`pct_chg`
- 输出字段：`volume_price_score`
- 取值范围：`0~1`

计算公式：

```text
scale(x, low, high) = clip((x-low)/(high-low), 0, 1)

trend_core =
  0.30 * scale(m20, -0.05, 0.20)
+ 0.25 * scale(m60, -0.10, 0.30)
+ 0.20 * scale(m5,  -0.02, 0.08)
+ 0.25 * scale(amount_ratio_20, 0.8, 2.0)

volume_price_score =
  0.50 * trend_core
+ 0.30 * scale(amount_ratio_20, 0.8, 2.0)
+ 0.20 * scale(pct_chg/100, -0.01, 0.03)
```

示例：

```text
m20=0.10, m60=0.20, m5=0.04, amount_ratio_20=1.4, pct_chg=2
trend_core=0.6125
volume_price_score=0.50*0.6125+0.30*0.50+0.20*0.75=0.60625
```

## 5. 极弱反转分 `reversal_score`

- 指标用途：寻找长期位置偏低、短期开始放量修复的板块
- 输入字段：`position_in_250_range`、`m5`、`m20`、`m60`、`amount_ratio_20`
- 输出字段：`reversal_score`
- 取值范围：`0~1`

计算公式：

```text
weakness_score = 1 - position_in_250_range
reversal_score =
  0.45 * weakness_score
+ 0.20 * scale(m5, -0.03, 0.08)
+ 0.20 * scale(amount_ratio_20, 0.8, 2.0)
+ 0.15 * scale(m20-m60, -0.05, 0.10)
```

示例：

```text
position_in_250_range=0.25, m5=0.03, amount_ratio_20=1.4, m20=0.02, m60=-0.04
weakness_score=0.75
reversal_score=0.656591
```

## 6. 板块综合分与排名

- 指标用途：在趋势延续和低位反转两类机会之间取更强的一类
- 输入字段：`volume_price_score`、`reversal_score`
- 输出字段：`theme_board_score`、`board_rank_in_theme`、`board_rank_in_theme_pct`、`board_rank_overall`、`board_rank_overall_pct`

计算公式：

```text
theme_board_score = max(volume_price_score, reversal_score)
rank_pct = (降序排名 - 1) / max(有效数量 - 1, 1)
```

示例：

```text
某主题下 3 个板块综合分=[0.80,0.60,0.40]
第1名 rank_pct=(1-1)/(3-1)=0
第2名 rank_pct=(2-1)/(3-1)=0.5
```

## 7. 主题强度 `theme_score`

- 指标用途：把同一主题下多个板块聚合成主题级别强度
- 输入字段：主题下所有板块的 `theme_board_score`
- 输出字段：`theme_score`、`theme_rank`、`theme_rank_pct`

计算公式：

```text
theme_score(T, 主题A) = mean(theme_board_score_i(T)), i 属于主题A
theme_rank_pct = (主题强度降序排名 - 1) / max(主题数量 - 1, 1)
```

示例：

```text
AI 主题下 3 个板块 theme_board_score=[0.70,0.80,0.60]
theme_score=(0.70+0.80+0.60)/3=0.70

当日 5 个主题中 AI 排名第2
theme_rank_pct=(2-1)/(5-1)=0.25
```

## 8. 个股主题暴露 `exposure_score`

- 指标用途：衡量一只股票被多少相关主题板块覆盖
- 输入字段：`theme_constituents_snapshot.csv` 中的成分股映射
- 输出字段：`stock_theme_exposure.csv` 中的 `exposure_score`

计算公式：

```text
exposure_score = board_count / max(board_count)
```

边界条件：

- 成分股快照来自当前最新板块成分，不是历史成分
- 长区间回测存在成分股幸存者偏差，需要在研究报告中说明

示例：

```text
某股票命中 4 个板块
全样本最多命中 8 个板块
exposure_score=4/8=0.5
```

## 9. 合并到股票 CSV 后的主题字段

- 指标用途：把独立板块研究结果作为股票回测的可选过滤字段
- 输入字段：`stock_theme_exposure.csv`、`theme_strength_daily.csv`、处理后股票 CSV 的 `trade_date`
- 输出字段：`sector_strongest_theme_score`、`sector_strongest_theme_rank_pct`、`sector_exposure_score` 等

计算公式：

```text
对每只股票：
1. 找到该股票命中的 theme_names
2. 在每个 trade_date 中，从这些主题里取 theme_score 最高的主题
3. 写入该主题的分数、排名、动量、成交额放大和最强板块
```

边界条件：

- 合并脚本只写入新目录，不覆盖原处理后股票目录
- 如果股票未命中任何主题，`sector_*` 字段为空
- 当前系统是 T 日收盘信号、T+1 开盘买入，因此同日板块强度可作为 T 日收盘信号字段；若改成盘前信号，需要整体滞后一日

示例：

```text
股票A命中主题：AI、半导体芯片
20260427:
AI theme_score=0.72, theme_rank_pct=0.10
半导体芯片 theme_score=0.61, theme_rank_pct=0.30

sector_strongest_theme=AI
sector_strongest_theme_score=0.72
sector_strongest_theme_rank_pct=0.10
```
