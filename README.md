# T 日信号摆动回测系统 V2

本项目用于研究 A 股日线信号策略：

- `T` 日只使用当日及历史数据生成买入信号
- `T+1` 日按原始开盘价 `raw_open` 买入
- 默认可按 `T+N` 日原始开盘价 `raw_open` 卖出，也支持“收盘触发卖出条件，下一交易日开盘执行”的混合退出模型
- 信号与指标按前复权价格 `qfq_*` 计算
- 买卖成交按原始除权价格 `raw_*` 计算

项目当前包含：

- 固定快照股票池构建
- Tushare 原始数据同步
- 处理后回测主输入生成
- 前端批量回测页面
- API 导出交易流水
- 特征分层扫描
- 训练期/验证期参数探索

说明：

- 脚本文件名仍沿用早期的 `run_overnight_*` 命名，但内部逻辑已经切到新的摆动持有模型。

## 默认假设

- 默认按 `2000` 积分 Tushare 权限规划实现。
- 默认接口：`stock_basic`、`daily_basic`、`daily`、`adj_factor`、`trade_cal`、`stk_limit`、`suspend_d`、`index_daily`。
- `TUSHARE_TOKEN` 优先从本机环境变量读取；若缺失，再回退到本地 `.env`。
- 固定快照默认按指定日期或此前最近开市日筛选 `总市值 >= 500亿` 且非 `ST` 股票。
- 信号与指标基于前复权价格；实际成交和资金结算基于原始除权价格。
- 默认探索参数：
  - 初始资金 `100000`
  - 每笔目标资金 `10000`
  - 每手 `100` 股
  - 买卖手续费各 `0.003%`
  - 默认无印花税、无最低佣金
  - 严格成交模式默认开启

这些假设会影响结果正确性。正式跑全量研究前，建议先确认本机数据、交易成本和 Tushare 账号权限与目标环境一致。

## 准备工作

### 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 配置环境变量

推荐直接在本机环境里设置：

```powershell
$env:TUSHARE_TOKEN="你的本机 token"
```

回退方式：

- 在本地 `.env` 中配置 `TUSHARE_TOKEN=...`
- 不要把 token 明文写入代码、文档或提交记录

### 项目结构

- [overnight_bt](/D:/量化/Momentum/T_0_system/overnight_bt)
  回测引擎、处理逻辑、表达式解析、研究与交付检查模块
- [scripts](/D:/量化/Momentum/T_0_system/scripts)
  数据准备、研究、特征扫描与交付校验脚本
- [static](/D:/量化/Momentum/T_0_system/static)
  前端页面
- [docs](/D:/量化/Momentum/T_0_system/docs)
  中文数据说明、指标说明、表达式说明与系统使用文档
- [tests](/D:/量化/Momentum/T_0_system/tests)
  单元测试与接口集成测试

## 数据准备

### 1. 生成固定快照股票池

```bash
python scripts/build_universe_snapshot.py --as-of 20260417
```

输出：

- `data_bundle/universe_snapshot.csv`

### 2. 同步原始数据包

```bash
python scripts/sync_tushare_bundle.py --start-date 20160101 --end-date 20260417
```

建议输出目录结构：

```text
data_bundle/
  universe_snapshot.csv
  trade_calendar.csv
  stk_limit.csv
  suspend_d.csv
  market_context.csv
  raw_daily/
  adj_factor/
```

### 3. 生成处理后回测输入

```bash
python scripts/build_processed_data.py
```

输出：

- `data_bundle/processed_qfq/*.csv`
- `data_bundle/processed_qfq/processing_manifest.csv`

如果你改过以下任一内容，需要重新构建 `processed_qfq/`：

- 涨跌停或停牌约束逻辑
- 前复权处理逻辑
- 新增信号特征字段
- `can_buy_open_t` 等开盘成交约束字段

### 4. 生成主题聚焦股票池

如果你要把股票池缩到 AI、机器人、新能源、有色金属、电网等方向，可以运行：

```bash
python scripts/build_theme_focus_universe.py
python scripts/build_theme_focus_universe.py --top-k 100 --out-snapshot data_bundle/universe_snapshot_theme_focus_top100.csv --out-processed-dir data_bundle/processed_qfq_theme_focus_top100
```

输出：

- `data_bundle/universe_snapshot_theme_focus.csv`
- `data_bundle/processed_qfq_theme_focus/`
- `data_bundle/universe_snapshot_theme_focus_top100.csv`
- `data_bundle/processed_qfq_theme_focus_top100/`

说明：

- `theme_focus` 是按主题规则筛出来的全量主题池
- `theme_focus_top100` 是在主题池基础上按总市值取前 100

## 启动方式

```bash
python -m uvicorn overnight_bt.app:app --reload --host 127.0.0.1 --port 8083
```

打开 [http://127.0.0.1:8080](http://127.0.0.1:8080)。

## 核心功能入口

### 前端页面

- 入口：`/`
- 主要输入项：
  - 处理后数据目录
  - 起止日期
  - `buy_condition`
  - `sell_condition`
  - `score_expression`
  - `top_n`
  - `per_trade_budget`
  - `entry_offset`
  - `exit_offset`
  - `min_hold_days`
  - `max_hold_days`
  - `initial_cash`
  - `lot_size`
  - 买卖费率、印花税、滑点、最低佣金
  - 是否启用严格成交

### API

- `GET /health`
- `POST /api/run-backtest`
- `POST /api/run-backtest-export`

`/api/run-backtest` 返回：

- `summary`
- `daily_rows`
- `pick_rows`
- `trade_rows`
- `contribution_rows`
- `diagnostics`

`/api/run-backtest-export` 返回 ZIP，包含：

- `summary.csv`
- `daily_equity.csv`
- `daily_picks.csv`
- `trades.csv`
- `contributions.csv`

## 回测逻辑

当前系统使用以下回测口径：

1. `T` 日收盘后扫描全部股票。
2. 用 `buy_condition` 过滤候选。
3. 用 `score_expression` 排序。
4. 取 `TopN` 作为信号列表。
5. 对入选信号在 `T+1` 日开盘尝试买入。
6. 每笔按 `per_trade_budget` 计算可买手数，股数必须为 `lot_size` 的整数倍。
7. 如果未配置 `sell_condition`，默认在 `T+N` 日开盘卖出。
8. 如果配置了 `sell_condition`，系统会在每个收盘后判断是否触发；满足 `min_hold_days` 后若触发，则安排下一交易日开盘卖出。
9. 若设置了 `max_hold_days`，则达到最大持有天数后，不论卖出条件是否触发，都会在下一到期开盘强制退出。
10. 若严格成交模式下卖出日开盘跌停或停牌，则顺延到下一个可卖开盘。
11. 若严格成交模式下买入日开盘涨停或停牌，则该信号取消，不追买。

默认成交口径：

- 信号字段：`qfq_*`
- 买卖成交：`raw_open`
- 资金估值：持仓期间按 `raw_close` 逐日估值

## 研究脚本

### 1. 特征分层扫描

按 `T+1 open -> T+N open` 的标签看哪些日线特征更值得研究：

```bash
python scripts/run_overnight_feature_scan.py --processed-dir data_bundle/processed_qfq --start-date 20190101 --end-date 20251231 --exit-offset 2
```

主要参数：

- `--entry-offset`：默认 `1`
- `--exit-offset`：默认 `2`，支持 `2~5`
- `--per-trade-notional`：默认 `10000`

输出：

- `scan_overview.json`
- `feature_bucket_report.csv`
- `feature_scan_summary.md`

### 2. 训练期/验证期参数探索

```bash
python scripts/run_overnight_research.py --processed-dir data_bundle/processed_qfq --preset swing_v1 --exit-offsets 2,3,4,5
```

主要参数：

- `--preset`：默认 `swing_v1`
- `--entry-offset`：默认 `1`
- `--exit-offsets`：默认 `2,3,4,5`
- `--top-k`：训练期保留多少组进入验证
- `--per-trade-budget`：默认 `10000`

输出文件：

- `train_results.csv`
- `selected_train_cases.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `research_summary.json`
- `research_summary.md`
- `selected_case_trade_records.csv`

其中：

- `research_summary.md` 用于记录本次探索的条件与结果
- `selected_case_trade_records.csv` 用于记录验证期优先组合的逐笔买卖明细，包含日期、买卖动作、股票代码、股票名称、价格、数量、手续费、总金额、收益率与价差

### 3. 买入条件网格测试

如果你要系统化搜索更稳定的买入条件，可以运行：

```bash
python scripts/run_buy_condition_grid.py --processed-dir data_bundle/processed_qfq --grid-preset buy_condition_focus_grid_v1 --exit-offsets 4,5
```

如果你要围绕首轮胜出条件做第二轮更细的搜索，可以运行：

```bash
python scripts/run_buy_condition_grid.py --processed-dir data_bundle/processed_qfq --grid-preset buy_condition_focus_grid_v2 --exit-offsets 5
```

如果你要专门测试“每次只买 TopM 个”的影响，可以运行：

```bash
python scripts/run_buy_condition_grid.py --processed-dir data_bundle/processed_qfq --grid-preset buy_condition_topm_grid_v1 --exit-offsets 5
```

如果你要继续细化 `Top1` 或 `Top2` 下最合适的买入条件，可以运行：

```bash
python scripts/run_buy_condition_grid.py --processed-dir data_bundle/processed_qfq --grid-preset buy_condition_top1_focus_grid_v1 --exit-offsets 5
python scripts/run_buy_condition_grid.py --processed-dir data_bundle/processed_qfq --grid-preset buy_condition_top2_focus_grid_v1 --exit-offsets 5
```

### 4. 卖出指标网格测试

如果你要固定当前最优买入条件，转而探索不同卖出逻辑，可以运行：

```bash
python scripts/run_sell_condition_grid.py --processed-dir data_bundle/processed_qfq
```

如果你要测试更高级的退出逻辑，例如止损和浮盈回撤保护，可以运行：

```bash
python scripts/run_sell_condition_grid.py --sell-grid-preset sell_grid_advanced_v1 --processed-dir data_bundle/processed_qfq_theme_focus_top100 --top-n 5
```

如果你要围绕当前最佳的高级退出继续微调参数，可以运行：

```bash
python scripts/run_sell_condition_grid.py --sell-grid-preset sell_grid_advanced_v2_micro --processed-dir data_bundle/processed_qfq_theme_focus_top100 --top-n 5 --top-k 28
```

输出文件包括：

- `sell_grid_cases.json`
- `train_results.csv`
- `selected_train_cases.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `sell_grid_summary.json`
- `sell_grid_summary.md`
- `selected_case_trade_records.csv`

高级退出支持的动态字段包括：

- `holding_return`
- `best_return_since_entry`
- `drawdown_from_peak`
- `days_held`

### 5. 股票池与固定持有期对比

如果你要在固定 `Top1` 和固定买入条件下，比较不同股票池与 `T+4/T+5/T+6/T+7` 固定卖出的差异，可以运行：

```bash
python scripts/run_universe_hold_compare.py
```

默认会比较：

- 原始全量股票池
- 主题聚焦股票池
- 主题聚焦前100市值股票池

输出文件包括：

- `train_results.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `universe_hold_summary.json`
- `universe_hold_summary.md`
- `selected_case_trade_records.csv`

### 6. 主题前100池 TopN 与固定持有期对比

如果你要固定 `theme_focus_top100` 股票池，再比较 `Top1 / Top3 / Top5` 与 `T+4 / T+5 / T+6 / T+7` 的差异，可以运行：

```bash
python scripts/run_topn_hold_compare.py
```

输出文件包括：

- `train_results.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `topn_hold_summary.json`
- `topn_hold_summary.md`
- `selected_case_trade_records.csv`

### 7. 当前推荐结果的前端复现

当前这条“主题前100池 + Top5 + 高级退出”的最佳结果，可以在前端按下面参数复现：

- 处理后数据目录：`D:/量化/Momentum/T_0_system/data_bundle/processed_qfq_theme_focus_top100`
- 开始日期：`20230101`
- 结束日期：`20251231`
- 买入条件：`board=主板,listed_days>500,m20>0.03,m5>0,pct_chg>-1.0,pct_chg<3.0,close_pos_in_bar>0.65,upper_shadow_pct<0.02,body_pct>0.0,vr<1.6,hs300_pct_chg>-1.0`
- 卖出条件：`best_return_since_entry>0.11,drawdown_from_peak>0.05`
- 评分表达式：`m20 * 155 + close_pos_in_bar * 6 + body_pct * 90 - upper_shadow_pct * 120 - abs(vr - 1.0) * 3`
- `TopN`：`5`
- 买入偏移：`1`
- 固定卖出偏移：`5`
- 最短持有天数：`3`
- 最大持有天数：`15`
- 初始资金：`100000`
- 每笔目标资金：`10000`
- 每手股数：`100`
- 买卖费率：`0.00003`
- 印花税：`0`
- 滑点(bps)：`3`
- 最低佣金：`0`
- 严格成交：`是`

说明：

- 这组参数对应的结果见 `research_runs/20260422_sell_condition_grid_top5_theme_focus_top100_micro/`
- 如果你要复现当前全局更稳的版本，则仍然优先看 `full_universe + Top1 + T+5`

当前脚本会输出两类核心结果：

- `sell_grid_summary.md`
  这次网格测试的总结书，包含测试范围、稳定性筛选口径、推荐条件和排行榜
- `selected_case_trade_records.csv`
  推荐组合的逐笔交易记录，包含买入、卖出、股票代码、股票名称、价格、数量、手续费、总金额、收益率和价差

完整输出通常包括：

- `sell_grid_cases.json`
- `train_results.csv`
- `selected_train_cases.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `sell_grid_summary.json`
- `sell_grid_summary.md`
- `selected_case_trade_records.csv`

## 复现结果

1. 准备好完整 `data_bundle/`
2. 确认其中包含 `processed_qfq/`
3. 启动服务
4. 打开前端并填写：
   - 处理后数据目录
   - 起止日期
   - `buy_condition`
   - 如有需要，填写 `sell_condition`
   - `score_expression`
   - `top_n`
   - `per_trade_budget`
   - `entry_offset=1`
   - `exit_offset`
   - 可选 `min_hold_days` / `max_hold_days`
   - 资金与交易成本参数
5. 点击“运行回测”
6. 查看：
   - 组合 summary
   - 资金曲线
   - 每日信号明细
   - 交易流水
   - 个股贡献
7. 如需归档，点击“下载 CSV ZIP”

## 文档入口

- 数据文档：[backtest-data-dictionary.md](/D:/量化/Momentum/T_0_system/docs/backtest-data-dictionary.md)
- 指标文档：[indicator-reference.md](/D:/量化/Momentum/T_0_system/docs/indicator-reference.md)
- 表达式文档：[expression-reference.md](/D:/量化/Momentum/T_0_system/docs/expression-reference.md)
- 系统文档：[system-documentation.md](/D:/量化/Momentum/T_0_system/docs/system-documentation.md)
- 主题股票池文档：[theme-focus-universe-data-dictionary.md](/D:/量化/Momentum/T_0_system/docs/theme-focus-universe-data-dictionary.md)

## 交付前校验

```bash
python scripts/verify_delivery.py
python -m unittest discover -s tests -p "test_*.py" -v
```

如果本次改动涉及 API 或前端，交付前还应做一次本地启动冒烟验证。当前项目推荐最少执行：

```bash
python -m unittest tests.test_backtest tests.test_api_integration tests.test_feature_scan tests.test_research tests.test_processing -v
python -m uvicorn overnight_bt.app:app --host 127.0.0.1 --port 8080
```
