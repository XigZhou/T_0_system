# 板块轮动后续验证数据说明

本文档说明 `scripts/run_sector_rotation_followup.py` 生成的研究数据。该脚本用于落实 `docs/sector-rotation-grid-result-20260501.md` 的下一步建议：对三条候选策略做分年度和最近一年对比，并验证把轮动状态改成评分加权后的效果。

## 1. 数据概览

| 数据名称 | 输出文件路径 | 数据粒度 | 主键字段 | 更新时间 | 用途 |
| --- | --- | --- | --- | --- | --- |
| 周期对比汇总 | `research_runs/*_sector_rotation_followup/sector_rotation_period_comparison.csv` | 每个周期、每条策略一行 | `period_label` + `case` | 每次运行脚本生成或续跑更新 | 比较全区间、分年度、最近一年表现 |
| 轮动评分加权汇总 | `research_runs/*_sector_rotation_followup/sector_rotation_weighted_score_summary.csv` | 每组加权策略一行 | `case` | 每次运行脚本生成或续跑更新 | 比较不同轮动评分权重表现 |
| 轮动评分加权交易流水 | `research_runs/*_sector_rotation_followup/sector_rotation_weighted_score_trade_records.csv` | 每组策略的每笔买卖一行 | `case` + `trade_date` + `symbol` + `action` | 每次运行脚本生成；续跑时追加缺失策略 | 复核逐笔买卖、费用、金额和盈亏 |
| 运行配置 | `research_runs/*_sector_rotation_followup/sector_rotation_followup_config.json` | 每次运行一份 | `created_at` | 每次运行脚本覆盖写入 | 记录 CLI 参数、周期定义和策略清单 |
| 自动报告 | `research_runs/*_sector_rotation_followup/sector_rotation_followup_report.md` | 每次运行一份 | 无 | 每次运行脚本覆盖写入 | 中文总结结果和关键判断 |

正式结果记录见 `docs/sector-rotation-followup-result-20260504.md`。`research_runs/` 默认不入库，因此需要通过该结果记录保留关键结论。

## 2. 来源说明

| 输入 | 默认路径 | 来源脚本 | 说明 |
| --- | --- | --- | --- |
| 基准处理后股票目录 | `data_bundle/processed_qfq_theme_focus_top100` | `scripts/build_theme_focus_universe.py` | 主题前 100 股票处理后日线，用于 `基准动量` |
| 板块增强股票目录 | `data_bundle/processed_qfq_theme_focus_top100_sector` | `scripts/build_sector_research_features.py` | 在主题前 100 股票日线上追加 `sector_*` 字段 |
| 轮动日频文件 | `research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv` | `scripts/run_sector_rotation_diagnosis.py` | 每日 Top1 主题、主题簇和轮动状态 |

脚本只读取已有 CSV/JSON 文件，不重新抓取 AKShare 或 Tushare 数据，也不覆盖上述输入目录。Tushare token 只在上游数据准备脚本中使用，本脚本不读取 token。

## 3. 字段说明

### 3.1 周期对比汇总和加权汇总通用字段

| 字段名 | 中文含义 | 类型/单位 | 示例 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `case` | 策略名称 | 文本 | `板块候选_score0.4_rank0.7` | 不允许缺失 | 对比或加权策略名 |
| `family` | 策略家族 | 文本 | `sector_candidate` | 不允许缺失 | `baseline`、`sector_candidate`、`rotation_score_weight` 等 |
| `data_profile` | 数据配置 | 文本 | `sector` | 不允许缺失 | 是否需要板块增强字段 |
| `processed_dir` | 处理后数据目录 | 文本路径 | `data_bundle/processed_qfq_theme_focus_top100_sector` | 不允许缺失 | 回测加载的数据目录 |
| `buy_condition` | 买入条件 | 文本表达式 | `m120>0.02,...` | 不允许缺失 | T 日收盘后计算 |
| `score_expression` | 评分表达式 | 文本表达式 | `m20 * 140 + ...` | 不允许缺失 | 用于日内候选排序 |
| `signal_count` | 入选信号数 | 整数 | `238` | 无信号时为 0 | 信号质量口径 |
| `signal_completed_count` | 完成信号数 | 整数 | `200` | 无信号时为 0 | 已完成买卖或可结算的信号 |
| `signal_avg_trade_return` | 信号平均单笔收益 | 小数 | `0.0123` | 无完成信号时为空 | 0.0123 表示 1.23% |
| `signal_median_trade_return` | 信号中位单笔收益 | 小数 | `-0.0004` | 无完成信号时为空 | 衡量普通一笔信号质量 |
| `signal_win_rate` | 信号胜率 | 小数 | `0.52` | 无完成信号时为空 | 大于 0 的完成信号占比 |
| `signal_profit_factor` | 信号收益因子 | 小数 | `1.35` | 无亏损时可能为空或极大 | 总盈利 / 总亏损绝对值 |
| `signal_curve_return` | 信号净值收益 | 小数 | `0.7586` | 无信号时为 0 | 信号质量曲线口径 |
| `signal_max_drawdown` | 信号最大回撤 | 小数 | `0.119` | 无信号时为 0 | 信号净值曲线回撤 |
| `account_total_return` | 账户总收益 | 小数 | `0.8729` | 无交易时为 0 | 实盘账户回测口径 |
| `account_annualized_return` | 账户年化收益 | 小数 | `0.2176` | 无交易时为空或 0 | 根据回测区间折算 |
| `account_max_drawdown` | 账户最大回撤 | 小数 | `0.1130` | 无交易时为 0 | 账户权益曲线回撤 |
| `account_buy_count` | 买入次数 | 整数 | `212` | 无交易时为 0 | 实际执行买入笔数 |
| `account_sell_count` | 卖出次数 | 整数 | `200` | 无交易时为 0 | 实际执行卖出笔数 |
| `account_win_rate` | 账户胜率 | 小数 | `0.5217` | 无已平仓交易时为空 | 已卖出交易中盈利占比 |
| `account_avg_trade_return` | 账户平均单笔收益 | 小数 | `0.018` | 无已平仓交易时为空 | 按已平仓交易统计 |
| `account_median_trade_return` | 账户中位单笔收益 | 小数 | `-0.0004` | 无已平仓交易时为空 | 按已平仓交易统计 |
| `account_profit_factor` | 账户收益因子 | 小数 | `1.42` | 无亏损时可能为空或极大 | 总盈利 / 总亏损绝对值 |
| `account_ending_equity` | 期末权益 | 金额 | `187290` | 无交易时等于初始资金 | 现金 + 持仓市值 |
| `account_open_position_count` | 期末持仓数 | 整数 | `2` | 无持仓时为 0 | 截止日仍未卖出数量 |
| `grid_score` | 综合排序分 | 小数 | `1.1543` | 根据现有指标计算 | 用于研究排序，不是交易收益 |
| `risk_note` | 风险提示 | 文本 | `信号中位收益不佳` | 无风险时写基础通过提示 | 由脚本按阈值生成 |

### 3.2 `sector_rotation_period_comparison.csv` 专属字段

| 字段名 | 中文含义 | 类型/单位 | 示例 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `period_label` | 周期标签 | 文本 | `2025`、`最近一年` | 不允许缺失 | 全区间、年份或最近一年 |
| `period_start` | 周期开始日期 | `YYYYMMDD` | `20250101` | 不允许缺失 | 信号日期口径 |
| `period_end` | 周期结束日期 | `YYYYMMDD` | `20251231` | 不允许缺失 | 信号日期口径 |
| `period_kind` | 周期类型 | 文本 | `year` | 不允许缺失 | `full`、`year`、`recent_year` |

### 3.3 `sector_rotation_weighted_score_summary.csv` 专属字段

| 字段名 | 中文含义 | 类型/单位 | 示例 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `param_rotation_usage` | 轮动使用方式 | 文本 | `score_weight` | 不允许缺失 | 本文件固定为评分加权 |
| `param_tech_bonus` | 科技成长主线加分 | 小数 | `2` | 不允许缺失 | 乘以 `rotation_top_cluster_tech` |
| `param_new_energy_penalty` | 新能源主线扣分 | 小数 | `4` | 不允许缺失 | 乘以 `rotation_top_cluster_new_energy` 后扣减 |
| `param_new_start_penalty` | 新主线启动扣分 | 小数 | `2` | 不允许缺失 | 乘以 `rotation_is_new_start` 后扣减 |

### 3.4 `sector_rotation_weighted_score_trade_records.csv` 关键字段

交易流水继承账户回测输出字段，并额外在表头追加策略上下文：

| 字段名 | 中文含义 | 类型/单位 | 示例 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `case` | 策略名称 | 文本 | `轮动加权_tech2_ne0_new4` | 不允许缺失 | 对应加权汇总中的 `case` |
| `family` | 策略家族 | 文本 | `rotation_score_weight` | 不允许缺失 | 本文件固定为加权策略 |
| `buy_condition` | 买入条件 | 文本表达式 | `m120>0.02,...` | 不允许缺失 | 便于复核策略条件 |
| `score_expression` | 评分表达式 | 文本表达式 | `m20 * 140 + ...` | 不允许缺失 | 便于复核排序逻辑 |
| `trade_date` | 交易日期 | `YYYYMMDD` | `20250418` | 不允许缺失 | 实际买入或卖出日期 |
| `symbol` | 股票代码 | 文本 | `000063.SZ` | 不允许缺失 | 具体格式沿用账户回测引擎 |
| `name` | 股票名称 | 文本 | `中兴通讯` | 可能为空 | 来自处理后股票 CSV |
| `action` | 交易动作 | 文本 | `buy`、`sell` | 不允许缺失 | 买入或卖出 |
| `price` | 成交价格 | 金额 | `32.15` | 不允许缺失 | 使用原始除权价格并计入滑点口径 |
| `shares` | 股数 | 整数 | `300` | 不允许缺失 | 必须为 `lot_size` 的整数倍 |
| `fee` | 手续费 | 金额 | `0.29` | 无费用时为 0 | 买卖费率默认 `0.00003` |
| `amount` | 成交金额 | 金额 | `9645` | 不允许缺失 | 价格乘股数，方向由动作决定 |
| `realized_pnl` | 已实现盈亏 | 金额 | `450` | 买入行为空或 0 | 卖出行用于复核盈亏 |
| `trade_return` | 单笔收益率 | 小数 | `0.046` | 买入行为空 | 卖出行按成本计算 |

实际交易流水中可能还包含现金、持仓市值、总权益、退出原因等账户回测引擎字段，以回测引擎当前输出为准。

## 4. 加工与清洗规则

1. 脚本先加载基准目录和板块增强目录，再把 `sector_rotation_daily.csv` 的轮动字段按 `trade_date` 合并到板块增强数据的内存副本中，不写回输入目录。
2. 分年度对比会生成 `全区间`、每个自然年、最后一个年份的 `YTD` 以及 `最近一年` 周期；所有周期都使用信号日期 `T` 做起止筛选。
3. 买入条件、卖出条件、评分表达式、费用、滑点、整手买入、停牌和涨跌停约束沿用账户回测引擎；信号指标使用前复权字段，成交使用原始除权价格。
4. `--resume` 会读取已有汇总 CSV，跳过已完成组合；交易流水按策略追加写入，避免长实验一次性占用大量内存。
5. 市场级轮动字段如 `rotation_top_cluster_tech` 在同一交易日对所有候选股票相同；直接加到评分中只会改变当天所有候选的共同常数，不改变日内排序。

## 5. 使用注意事项

- 本脚本是研究脚本，不生成模拟账户订单，不修改 `/paper` 账本。
- 正式复盘时优先查看 `sector_rotation_period_comparison.csv` 判断收益是否集中在少数年份，再查看加权汇总是否真正改变收益、回撤和买入次数。
- 如果继续研究轮动加权，优先使用 `stock_matches_rotation_top_cluster`、`stock_matches_rotation_top_theme` 或二者与 `rotation_is_new_start` 的交互项，因为这些字段在同一天不同股票之间可能不同。
- `research_runs/` 不入库；可复现结论应同步写入 `docs/sector-rotation-followup-result-YYYYMMDD.md`。

## 6. 示例

```text
输入:
case=板块候选_score0.4_rank0.7
period_label=2025
account_total_return=0.4433
account_buy_count=96
signal_median_trade_return=0.0186

解释:
该策略在 2025 年信号区间内账户收益为 44.33%，实际买入 96 次，信号中位单笔收益为 1.86%。
```
