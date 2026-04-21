# T 日信号摆动回测系统使用文档

本文档说明系统各功能模块的用途、输入参数、输出结果与异常处理方式。当前系统的默认回测口径为：`T` 日生成信号，`T+1` 日开盘买入，`T+N` 日开盘卖出，`2 <= N <= 5`。

## 1. 固定股票池构建模块

### 功能

- 根据指定日期生成固定快照股票池
- 默认筛选总市值不低于 500 亿且名称不含 `ST`

### 入口

```bash
python scripts/build_universe_snapshot.py --as-of 20260417
```

### 输入参数

| 参数 | 说明 |
| --- | --- |
| `--as-of` | 快照日期，格式 `YYYYMMDD` |
| `TUSHARE_TOKEN` | 本机环境变量中的 Tushare token |

### 输出结果

- `data_bundle/universe_snapshot.csv`

### 异常处理

- 若 `TUSHARE_TOKEN` 缺失，脚本会报认证相关异常
- 若指定日期不是交易日，会对齐到最近开市日

## 2. Tushare 数据同步模块

### 功能

- 下载原始日线、复权因子、交易日历、涨跌停、停牌与指数上下文

### 入口

```bash
python scripts/sync_tushare_bundle.py --start-date 20160101 --end-date 20260417
```

### 输入参数

| 参数 | 说明 |
| --- | --- |
| `--start-date` | 开始日期 |
| `--end-date` | 结束日期 |
| `--bundle-dir` | 输出目录，默认 `data_bundle/` |

### 输出结果

- `data_bundle/raw_daily/*.csv`
- `data_bundle/adj_factor/*.csv`
- `data_bundle/trade_calendar.csv`
- `data_bundle/stk_limit.csv`
- `data_bundle/suspend_d.csv`
- `data_bundle/market_context.csv`

### 异常处理

- 接口权限不足时会抛出 Tushare 访问错误
- 某些接口区间拉取过大时，脚本使用逐股票汇总方式减少截断风险

## 3. 处理后回测输入生成模块

### 功能

- 生成 `processed_qfq/*.csv`
- 构造信号字段、参考标签和开盘成交约束字段

### 入口

```bash
python scripts/build_processed_data.py
```

### 输入参数

| 参数 | 说明 |
| --- | --- |
| `--bundle-dir` | 数据包目录 |
| `--output-dir` | 输出目录，默认 `data_bundle/processed_qfq` |
| `--snapshot-csv` | 自定义股票池快照路径，可选 |

### 输出结果

- `data_bundle/processed_qfq/<symbol>.csv`
- `data_bundle/processed_qfq/processing_manifest.csv`

### 关键输出字段

- 信号价格：`open/high/low/close`
- 成交价格：`raw_open/raw_close`
- 开盘约束：`can_buy_open_t`、`can_sell_t`
- 参考标签：`next_open`、`next_raw_open`、`r_on`、`r_on_raw`

### 异常处理

- 缺少原始日线或复权因子文件时，会在 `processing_manifest.csv` 中记录 `missing_input`
- 必备字段缺失或日期不升序时，会抛出 `ValueError`

## 4. 主题聚焦股票池构建模块

### 功能

- 在现有快照股票池基础上，二次筛选出 AI、机器人、新能源、有色金属、电网等方向
- 生成对应的处理后数据子目录，方便直接做缩池回测

### 入口

```bash
python scripts/build_theme_focus_universe.py
python scripts/build_theme_focus_universe.py --top-k 100 --out-snapshot data_bundle/universe_snapshot_theme_focus_top100.csv --out-processed-dir data_bundle/processed_qfq_theme_focus_top100
```

### 输入参数

| 参数 | 说明 |
| --- | --- |
| `--snapshot-csv` | 原始快照股票池路径 |
| `--processed-dir` | 原始处理后数据目录 |
| `--out-snapshot` | 输出主题池快照路径 |
| `--out-processed-dir` | 输出主题池处理后数据目录 |
| `--top-k` | 可选市值截断；`0` 表示不截断 |

### 输出结果

- `universe_snapshot_theme_focus.csv`
- `processed_qfq_theme_focus/`
- 或者你指定的 `top-k` 版本输出

### 异常处理

- 输入快照不存在时抛出文件读取异常
- 个别股票若缺少处理后文件，则不会复制进目标目录

## 5. 股票池与固定持有期对比模块

### 功能

- 固定当前最优 `Top1` 买入条件
- 在多个股票池上比较不同固定持有天数
- 输出验证期稳定性排序和逐笔交易记录

### 入口

```bash
python scripts/run_universe_hold_compare.py
```

### 默认比较范围

- 股票池：
  - 全量原始池
  - `theme_focus`
  - `theme_focus_top100`
- 固定卖出：
  - `T+4`
  - `T+5`
  - `T+6`
  - `T+7`

### 输出结果

- `train_results.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `universe_hold_summary.json`
- `universe_hold_summary.md`
- `selected_case_trade_records.csv`

### 异常处理

- 股票池目录不存在时抛出 `FileNotFoundError`
- 输出目录不可写时抛出文件系统异常

## 6. 主题前100池 TopN 与固定持有期对比模块

### 功能

- 固定 `theme_focus_top100`
- 比较 `Top1 / Top3 / Top5`
- 比较 `T+4 / T+5 / T+6 / T+7`
- 输出验证期稳定性排序和逐笔交易记录

### 入口

```bash
python scripts/run_topn_hold_compare.py
```

### 输出结果

- `train_results.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `topn_hold_summary.json`
- `topn_hold_summary.md`
- `selected_case_trade_records.csv`

### 异常处理

- 处理后目录不存在时抛出 `FileNotFoundError`
- 输出目录不可写时抛出文件系统异常

## 7. 回测引擎模块

### 功能

- 根据 `T` 日信号生成待执行订单
- 在 `T+1` 日开盘尝试买入
- 在 `T+N` 日开盘尝试卖出
- 支持严格成交模式、滑点、手续费、无最低佣金

### 主要入口

- Python 调用：`overnight_bt.backtest.run_portfolio_backtest`
- API：`POST /api/run-backtest`

### 核心输入参数

| 参数 | 说明 |
| --- | --- |
| `processed_dir` | 处理后数据目录 |
| `start_date/end_date` | 信号日期范围 |
| `buy_condition` | 信号筛选表达式 |
| `sell_condition` | 可选卖出表达式，收盘后判断、次日开盘执行 |
| `score_expression` | 排名打分表达式 |
| `top_n` | 每个信号日最多保留的候选数 |
| `initial_cash` | 初始资金 |
| `per_trade_budget` | 每笔目标资金 |
| `lot_size` | 股数步长，默认 100 |
| `entry_offset` | 买入偏移，当前默认 1 |
| `exit_offset` | 固定退出偏移，未启用卖出条件时按该值退出 |
| `min_hold_days` | 卖出条件开始生效前的最短持有天数 |
| `max_hold_days` | 最大持有天数；大于 0 时作为强制退出上限 |
| `buy_fee_rate/sell_fee_rate` | 买卖手续费率 |
| `stamp_tax_sell` | 卖出税费 |
| `slippage_bps` | 滑点 |
| `realistic_execution` | 是否启用严格成交 |
| `min_commission` | 最低佣金 |

### 输出结果

| 字段 | 说明 |
| --- | --- |
| `summary` | 汇总指标，如收益率、回撤、买卖次数、阻塞次数 |
| `daily_rows` | 每日现金、持仓市值、权益、候选数、买卖数 |
| `pick_rows` | 每个信号日入选股票及计划买卖日期 |
| `trade_rows` | 逐笔买卖与阻塞明细 |
| `contribution_rows` | 个股贡献汇总 |
| `diagnostics` | 文件数量、信号日数量、候选日数量等诊断信息 |

### 异常处理

- `processed_dir` 不存在时抛出 `FileNotFoundError`
- `exit_offset <= entry_offset` 时抛出 `ValueError`
- 表达式非法时抛出 `ValueError` 或表达式解析错误

## 7. 前端页面模块

### 功能

- 提供表单化回测入口
- 展示 summary、资金曲线、信号明细、交易流水、个股贡献

### 入口

```text
http://127.0.0.1:8080/
```

### 页面输入项

- 处理后数据目录
- 开始日期、结束日期
- 买入条件
- 卖出条件
- 评分表达式
- `TopN`
- 初始资金
- 每笔目标资金
- 买入偏移、卖出偏移
- 最短持有天数、最大持有天数
- 每手股数
- 买卖费率、印花税、滑点、最低佣金
- 是否严格成交

### 输出结果

- 组合 summary
- 资金曲线
- 每日信号明细
- 交易流水
- 个股贡献汇总

### 异常处理

- 请求失败时页面状态栏会显示错误信息
- 参数缺失或数据目录错误时，API 会返回 4xx/5xx

## 8. 回测导出模块

### 功能

- 将回测结果打包为 ZIP 下载

### 入口

- API：`POST /api/run-backtest-export`
- 前端按钮：“下载 CSV ZIP”

### 输出文件

- `summary.csv`
- `daily_equity.csv`
- `daily_picks.csv`
- `trades.csv`
- `contributions.csv`

### 异常处理

- 与回测接口相同；若回测失败则不会生成 ZIP

## 9. 特征分层扫描模块

### 功能

- 按 `T+1 open -> T+N open` 的收益标签评估各特征分层效果

### 入口

```bash
python scripts/run_overnight_feature_scan.py --processed-dir data_bundle/processed_qfq --exit-offset 2
```

### 输入参数

| 参数 | 说明 |
| --- | --- |
| `--processed-dir` | 处理后数据目录 |
| `--start-date/--end-date` | 样本区间 |
| `--entry-offset` | 买入偏移，默认 1 |
| `--exit-offset` | 卖出偏移，默认 2 |
| `--per-trade-notional` | 单笔名义资金 |
| `--strict-executable` | 是否只保留可执行样本 |

### 输出结果

- `scan_overview.json`
- `feature_bucket_report.csv`
- `feature_scan_summary.md`

### 异常处理

- 数据目录不存在时抛出 `FileNotFoundError`
- 样本过滤后为空时抛出 `ValueError`

## 10. 参数探索模块

### 功能

- 在训练期批量跑多组 `buy_condition + score_expression + exit_offset`
- 用验证期复核稳定性
- 导出结果排行榜和交易明细

### 入口

```bash
python scripts/run_overnight_research.py --processed-dir data_bundle/processed_qfq --preset swing_v1 --exit-offsets 2,3,4,5
```

### 主要输入参数

| 参数 | 说明 |
| --- | --- |
| `--preset` | 研究预设，默认 `swing_v1` |
| `--train-start/--train-end` | 训练期 |
| `--valid-start/--valid-end` | 验证期 |
| `--entry-offset` | 买入偏移 |
| `--exit-offsets` | 卖出偏移集合 |
| `--top-k` | 训练期保留进入验证的组合数 |
| `--export-top-trades-k` | 额外导出的验证期前几名组合交易明细数 |

### 输出结果

- `train_results.csv`
- `selected_train_cases.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `research_summary.json`
- `research_summary.md`
- `selected_case_trade_records.csv`

### 异常处理

- `exit_offset` 不在 `2~5` 范围时会抛出 `ValueError`
- 预设名不存在时会抛出 `ValueError`

## 11. 买入条件网格测试模块

### 功能

- 用网格方式搜索适合当前系统的买入条件
- 输出稳定性排行榜
- 自动生成总结书和交易明细文件

### 入口

```bash
python scripts/run_buy_condition_grid.py --processed-dir data_bundle/processed_qfq --grid-preset buy_condition_focus_grid_v1 --exit-offsets 4,5
```

### 主要输入参数

| 参数 | 说明 |
| --- | --- |
| `--grid-preset` | 网格预设，当前支持 `buy_condition_grid_v1`、`buy_condition_focus_grid_v1`、`buy_condition_focus_grid_v2`、`buy_condition_topm_grid_v1`、`buy_condition_top1_focus_grid_v1` 与 `buy_condition_top2_focus_grid_v1` |
| `--train-start/--train-end` | 训练期 |
| `--valid-start/--valid-end` | 验证期 |
| `--exit-offsets` | 要测试的卖出偏移集合 |
| `--top-k` | 训练期筛选进入验证的组合数 |
| `--export-top-trades-k` | 导出多少个推荐组合的逐笔交易记录 |

推荐用法：

- `buy_condition_grid_v1`
  粗网格，适合首次扫大方向
- `buy_condition_focus_grid_v1`
  围绕主板老股强趋势条件做第一轮聚焦
- `buy_condition_focus_grid_v2`
  围绕首轮胜出条件做第二轮精细调参
- `buy_condition_topm_grid_v1`
  固定当前最优买入条件，只比较 `TopM` 对交易笔数、胜率和稳定性的影响
- `buy_condition_top1_focus_grid_v1`
  固定 `Top1`，围绕当前最优条件做精细网格
- `buy_condition_top2_focus_grid_v1`
  固定 `Top2`，围绕当前最优条件做精细网格

### 输出结果

- `grid_cases.json`
- `train_results.csv`
- `selected_train_cases.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `grid_summary.json`
- `grid_summary.md`
- `selected_case_trade_records.csv`

### 异常处理

- 网格预设不存在时抛出 `ValueError`
- 输出目录不可写时会抛出文件系统异常
- 数据目录错误时抛出 `FileNotFoundError`

## 12. 卖出指标网格测试模块

### 功能

- 固定当前最优买入条件
- 批量测试不同卖出条件、最短持有天数和最大持有天数
- 输出稳定性排序、总结书和逐笔交易明细

### 入口

```bash
python scripts/run_sell_condition_grid.py --processed-dir data_bundle/processed_qfq
```

### 主要输入参数

| 参数 | 说明 |
| --- | --- |
| `--sell-grid-preset` | 卖出预设；当前支持基础版与高级版 |
| `--buy-condition` | 固定买入条件 |
| `--score-expression` | 固定打分表达式 |
| `--top-n` | 固定持仓名额 |
| `--train-start/--train-end` | 训练期 |
| `--valid-start/--valid-end` | 验证期 |
| `--top-k` | 训练期筛选进入验证的卖出方案数 |

### 输出结果

- `sell_grid_cases.json`
- `train_results.csv`
- `selected_train_cases.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `sell_grid_summary.json`
- `sell_grid_summary.md`
- `selected_case_trade_records.csv`

### 异常处理

- 卖出表达式非法时抛出解析错误
- 数据目录不存在时抛出 `FileNotFoundError`
- `sell_grid_advanced_v1` 会测试止损和浮盈回撤保护两类高级退出
- `holding_return`、`best_return_since_entry`、`drawdown_from_peak` 等字段由回测引擎在持仓期动态计算

## 13. 交付校验模块

### 功能

- 检查 README、核心文档和前端交付文件是否齐全

### 入口

```bash
python scripts/verify_delivery.py
```

### 当前校验内容

- `README.md`
- `docs/backtest-data-dictionary.md`
- `docs/indicator-reference.md`
- `docs/system-documentation.md`
- `static/index.html`
- `static/app.js`
- `static/style.css`
- `overnight_bt/app.py`

### 异常处理

- 若缺文件或 README 缺少关键章节，脚本返回非 0 退出码

## 14. 推荐交付流程

1. 更新或同步数据
2. 重新构建 `processed_qfq/`
3. 运行相关单测
4. 做一次 API/前端本地冒烟验证
5. 运行 `python scripts/verify_delivery.py`
6. 确认通过后再提交或推送
