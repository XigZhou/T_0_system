# 板块效应选股条件探索数据说明

本文档说明 `scripts/run_sector_effect_grid.py` 生成的研究数据。该脚本用于验证“优先选择有板块效应的股票”是否比单纯使用基准动量更好，重点比较板块硬过滤和板块评分加权两种接入方式。

## 1. 数据概览

| 数据名称 | 输出文件路径 | 数据粒度 | 主键字段 | 更新时间 | 用途 |
| --- | --- | --- | --- | --- | --- |
| 板块效应网格汇总 | `research_runs/*_sector_effect_grid*/sector_effect_grid_summary.csv` | 每组策略参数一行 | `case` | 每次运行脚本生成；`--resume` 时保留已完成组合 | 比较信号质量、账户收益、回撤、交易次数和综合排序 |
| 板块效应交易流水 | `research_runs/*_sector_effect_grid*/sector_effect_grid_trade_records.csv` | 每组策略的每笔账户流水一行 | `case` + `trade_date` + `symbol` + `action` | 每完成一个组合后重写统一列文件 | 复核逐笔买入、卖出、费用、金额和盈亏 |
| 运行配置 | `research_runs/*_sector_effect_grid*/sector_effect_grid_config.json` | 每次运行一份 | `created_at` | 每次运行或续跑时覆盖写入 | 记录 CLI 参数、展开后的策略组合和运行口径 |
| 自动报告 | `research_runs/*_sector_effect_grid*/sector_effect_grid_report.md` | 每次运行一份 | 无 | 每次运行结束生成 | 中文 Top 结果、基准对照和风险提示 |

`research_runs/` 默认不入库，因此正式结论需要同步写入 `docs/sector-effect-grid-result-YYYYMMDD.md`。

## 2. 数据来源

| 输入 | 默认路径 | 来源脚本 | 说明 |
| --- | --- | --- | --- |
| 基准处理后股票目录 | `data_bundle/processed_qfq_theme_focus_top100` | `scripts/build_theme_focus_universe.py` | 主题前 100 股票处理后日线，用于基准动量对照 |
| 板块增强股票目录 | `data_bundle/processed_qfq_theme_focus_top100_sector` | `scripts/build_sector_research_features.py` | 在基准处理后日线上追加 `sector_*` 字段 |
| 板块研究数据 | `sector_research/data/processed` | `scripts/run_sector_research.py` | 上游使用 AKShare 东方财富行业/概念板块、历史行情、成分股和资金流数据生成 |

本脚本只读取已有 CSV 文件，不重新抓取 AKShare 或 Tushare，不读取 `TUSHARE_TOKEN`，也不覆盖上述输入目录。

## 3. 策略家族

| family | 数据目录 | 定义 |
| --- | --- | --- |
| `baseline` | `data_bundle/processed_qfq_theme_focus_top100` | 不使用任何 `sector_*` 字段，只作为收益、回撤和活跃度对照 |
| `hard_filter` | `data_bundle/processed_qfq_theme_focus_top100_sector` | 在基准动量买入条件上增加个股板块暴露、最强主题强度、主题排名、主题 20 日动量和成交额放大过滤 |
| `score_weight` | `data_bundle/processed_qfq_theme_focus_top100_sector` | 买入条件仍使用基准动量，只把板块效应字段加入 TopN 排序评分 |

默认基础买入条件：

```text
m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02
```

默认卖出条件：

```text
m20<0.08,hs300_m20<0.02
```

默认账户参数：

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `initial_cash` | `100000` | 初始资金 |
| `per_trade_budget` | `10000` | 每只股票目标买入金额 |
| `lot_size` | `100` | 买入股数必须是 100 股整数倍 |
| `buy_fee_rate` | `0.00003` | 买入手续费 0.003% |
| `sell_fee_rate` | `0.00003` | 卖出手续费 0.003% |
| `stamp_tax_sell` | `0` | 默认不计印花税 |
| `min_commission` | `0` | 默认无最低佣金 |
| `slippage_bps` | `3` | 单边滑点 3 bps |
| `entry_offset` | `1` | T 日信号，T+1 开盘买入 |
| `exit_offset` | `5` | 固定退出参考偏移 |
| `min_hold_days` / `max_hold_days` | `3` / `15` | 卖出条件触发前最短持有 3 天，最长持有 15 天 |

## 4. 必要板块字段

板块增强目录必须包含 `sector_feature_manifest.csv`，且每只股票 CSV 必须包含下列字段：

| 字段名 | 中文含义 | 类型/单位 | 示例 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `sector_exposure_score` | 个股主题暴露分 | 小数 | `0.42` | 缺字段直接报错；行级空值在条件中视为不满足 | 来自个股命中的主题和板块数量 |
| `sector_strongest_theme_score` | 个股命中主题中最强主题综合分 | 小数 | `0.68` | 同上 | 分数越高代表主题越强 |
| `sector_strongest_theme_rank_pct` | 最强主题排名百分位 | 小数 | `0.12` | 同上 | 越小越强，`0` 接近当日最强主题 |
| `sector_strongest_theme_m20` | 最强主题 20 日动量 | 小数 | `0.08` | 同上 | 使用板块研究的主题日频强度 |
| `sector_strongest_theme_amount_ratio_20` | 最强主题成交额放大倍数 | 倍数 | `1.25` | 同上 | 大于 1 表示高于 20 日均额 |
| `sector_strongest_theme_board_up_ratio` | 最强主题内上涨板块占比 | 小数 | `0.67` | 同上 | 用于评分加权 |
| `sector_strongest_theme_positive_m20_ratio` | 最强主题内 20 日动量为正的板块占比 | 小数 | `0.75` | 同上 | 当前用于完整性校验，后续可纳入扩展网格 |

## 5. 字段说明

### 5.1 `sector_effect_grid_summary.csv`

| 字段 | 定义 |
| --- | --- |
| `case` | 策略名称 |
| `family` | 策略家族：`baseline`、`hard_filter`、`score_weight` |
| `data_profile` | 数据口径：基准为 `auto`，板块增强为 `sector` |
| `processed_dir` | 本组策略读取的数据目录 |
| `buy_condition` | 买入过滤条件，按 T 日及历史字段计算 |
| `score_expression` | TopN 排序评分表达式 |
| `signal_count` | 信号质量回测生成的信号数量 |
| `signal_completed_count` | 已完成买卖闭环的信号数量 |
| `signal_avg_trade_return` | 信号质量口径平均单笔收益 |
| `signal_median_trade_return` | 信号质量口径单笔收益中位数 |
| `signal_win_rate` | 信号质量口径胜率 |
| `signal_profit_factor` | 信号质量口径收益因子 |
| `signal_curve_return` | 信号净值曲线收益 |
| `signal_max_drawdown` | 信号净值曲线最大回撤 |
| `signal_candidate_day_ratio` | 有候选股票的交易日占比 |
| `signal_topn_fill_rate` | TopN 被填满比例 |
| `account_total_return` | 账户回测总收益率 |
| `account_annualized_return` | 账户回测年化收益率 |
| `account_max_drawdown` | 账户回测最大回撤 |
| `account_buy_count` | 实际买入次数 |
| `account_sell_count` | 实际卖出次数 |
| `account_win_rate` | 账户已完成交易胜率 |
| `account_avg_trade_return` | 账户平均单笔收益 |
| `account_median_trade_return` | 账户单笔收益中位数 |
| `account_profit_factor` | 账户收益因子 |
| `account_ending_equity` | 期末权益 |
| `account_open_position_count` | 期末仍持仓数量 |
| `param_effect_usage` | 板块效应使用方式：`none`、`hard_filter`、`score_weight` |
| `param_score_threshold` | `hard_filter` 使用的主题强度阈值 |
| `param_rank_pct` | `hard_filter` 使用的主题排名百分位阈值 |
| `param_exposure_min` | `hard_filter` 使用的个股主题暴露分阈值 |
| `param_theme_m20_min` | `hard_filter` 使用的主题 20 日动量阈值 |
| `param_amount_ratio_min` | `hard_filter` 使用的主题成交额放大阈值 |
| `param_score_weight` | `score_weight` 使用的板块评分权重 |
| `grid_score` | 综合排序分，只用于研究排序，不是交易收益 |
| `risk_note` | 自动风险提示，例如交易次数偏少、回撤偏高、信号中位收益不佳 |

### 5.2 `sector_effect_grid_trade_records.csv`

交易流水继承账户回测引擎输出，并在表头追加策略上下文。脚本会统一所有动作的列集合后重写 CSV，因此 `BUY`、`SELL`、`BUY_BLOCKED`、`SELL_BLOCKED`、`BUY_SKIPPED_CASH` 等不同动作可以稳定放在同一文件里。

| 字段 | 定义 |
| --- | --- |
| `case` | 策略名称 |
| `family` | 策略家族 |
| `buy_condition` | 本组策略买入条件 |
| `score_expression` | 本组策略评分表达式 |
| `param_*` | 本组策略参数 |
| `trade_date` | 实际流水日期 |
| `signal_date` | 产生买入信号的日期 |
| `planned_entry_date` | 计划买入日期，默认 T+1 |
| `planned_exit_date` | 计划或实际卖出参考日期 |
| `max_exit_date` | 最大退出日期 |
| `symbol` | 股票代码 |
| `name` | 股票名称 |
| `action` | 流水类型 |
| `price` | 成交或阻塞参考价格 |
| `shares` | 股数 |
| `gross_amount` | 不含费用的成交金额 |
| `fees` | 手续费 |
| `net_amount` | 含费用后的现金变动金额 |
| `cash_after` | 该笔流水后的现金 |
| `rank` | 买入信号当日排序 |
| `score` | 买入信号当日评分 |
| `holding_days` | 卖出时持有天数 |
| `trade_return` | 卖出单对应的单笔收益率 |
| `price_pnl` | 卖出单对应的价格盈亏 |
| `exit_reason` | 卖出原因 |
| `reason` | 账户回测引擎给出的流水说明 |

## 6. 计算公式

### 6.1 硬过滤条件

当某个组合设置 `score_threshold=0.4`、`rank_pct=0.7`、`exposure_min=0`、`theme_m20_min=0`、`amount_ratio_min=1` 时，买入条件为：

```text
m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02,
sector_exposure_score>0,
sector_strongest_theme_score>=0.4,
sector_strongest_theme_rank_pct<=0.7,
sector_strongest_theme_m20>=0,
sector_strongest_theme_amount_ratio_20>=1
```

解释：个股先满足基准动量和大盘过滤，再要求它命中板块研究主题，且命中的最强主题当日不弱。

### 6.2 板块评分加权

`score_weight=w` 时，评分表达式为：

```text
基础动量评分
+ sector_strongest_theme_score * w
+ sector_exposure_score * max(w/2, 1)
- sector_strongest_theme_rank_pct * max(w/2, 1)
+ sector_strongest_theme_m20 * max(w*3, 1)
+ (sector_strongest_theme_amount_ratio_20 - 1) * max(w/3, 1)
+ sector_strongest_theme_board_up_ratio * max(w/3, 1)
```

它不会减少候选数量，而是在同一天候选股票之间重新排序。

### 6.3 综合排序分

`grid_score` 用于研究排序：

```text
account_total_return * 1.1
+ signal_median_trade_return * 2
+ account_win_rate * 0.2
+ signal_topn_fill_rate * 0.05
+ min(account_buy_count / 120, 1) * 0.08
- account_max_drawdown * 0.8
```

示例：若某组策略 `account_total_return=0.80`、`signal_median_trade_return=0.001`、`account_win_rate=0.52`、`signal_topn_fill_rate=0.30`、`account_buy_count=100`、`account_max_drawdown=0.11`，则：

```text
grid_score = 0.80*1.1 + 0.001*2 + 0.52*0.2 + 0.30*0.05 + min(100/120,1)*0.08 - 0.11*0.8
           = 0.9797
```

## 7. 缺失值、复权和异常处理

- 必要 `sector_*` 字段缺失时脚本直接报错，不允许误用未增强目录。
- 行级 `sector_*` 数值为空时，硬过滤条件通常不通过；评分加权若算出 `NaN`，该候选不会进入 TopN。
- 信号指标、买入条件和评分表达式使用处理后 CSV 中的前复权指标，例如 `m5`、`m20`、`m60`、`m120`。
- 实际买入和卖出使用原始除权开盘价 `raw_open`，并计入滑点和手续费。
- 停牌、涨跌停和开盘不可成交约束沿用账户回测引擎中的 `can_buy_open_t`、`can_sell_t` 等字段。
- `--resume` 会读取已有汇总和交易流水，跳过已完成 `case`；若旧交易流水列不一致导致无法读取，脚本会要求更换输出目录或删除旧文件。

## 8. 使用示例

```bash
python scripts/run_sector_effect_grid.py \
  --start-date 20230101 \
  --end-date 20260429 \
  --out-dir research_runs/20260504_181000_sector_effect_grid_fixed \
  --score-thresholds 0.4,0.5 \
  --rank-pcts 0.7 \
  --exposure-mins 0 \
  --theme-m20-mins any,0 \
  --amount-ratio-mins any,1.0 \
  --score-weights 5,10,15 \
  --resume
```

复核交易流水：

```bash
python - <<'PY'
import pandas as pd
path = "research_runs/20260504_181000_sector_effect_grid_fixed/sector_effect_grid_trade_records.csv"
df = pd.read_csv(path)
print(df.groupby(["case", "action"]).size())
PY
```
