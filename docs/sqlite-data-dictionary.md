# SQLite 数据字典

本文档说明当前系统使用的 SQLite 数据库、表职责、来源接口、主键、更新方式、缺失值处理、复权和停牌处理逻辑。运行库默认位于 `data_store/`，不提交到 GitHub。

## 1. `data_store/market_data.sqlite`

这是当前主行情数据库，默认由管理员后台、核心调度和行情脚本读写。

### 1.1 `main_stock_universe`

- 来源：管理员后台手工维护，或 `scripts/init_main_universe_from_tushare.py` 从 Tushare 初始化。
- 数据粒度：每只股票一行。
- 主键：`symbol`。
- 更新时间：管理员保存主股票池或初始化脚本运行时更新。
- 缺失值处理：名称、`ts_code` 可通过 `stock_basic` 解析补齐；无法解析的输入不会写入。

关键字段：

| 字段 | 说明 |
| --- | --- |
| `symbol` | 6 位股票代码 |
| `ts_code` | Tushare 股票代码 |
| `name` | 股票名称 |
| `source` | 来源标记，如 `admin_upload`、`tushare_non_st_total_mv_gt_300y` |
| `is_active` | 1 表示活跃主股票池；0 表示保留历史但不参与默认采集 |
| `created_at` / `updated_at` | 写入和更新时间 |

### 1.2 `stock_basic`

- 来源接口：Tushare `stock_basic`。
- 数据粒度：每只 A 股股票一行。
- 主键：`symbol` 或 `ts_code` 的规范化映射。
- 更新时间：主股票池初始化、raw 采集或股票名称解析时更新。
- 缺失值处理：元信息缺失允许为空；上市状态筛选由初始化脚本控制。

关键字段：`symbol`、`ts_code`、`name`、`industry`、`market`、`list_date`、`is_active`。

### 1.3 `stock_daily_raw`

- 来源接口：Tushare `daily`。
- 数据粒度：每股每交易日一行。
- 主键：`symbol + trade_date`。
- 更新时间：`scripts/collect_stock_daily_raw.py` 或管理员日线采集按钮。
- 缺失值处理：不插值，不前向填充；停牌日可能没有 raw 行。
- 复权处理：保留原始除权价格，不直接复权。

关键字段：`symbol`、`ts_code`、`trade_date`、`open`、`high`、`low`、`close`、`pre_close`、`change`、`pct_chg`、`vol`、`amount`。

### 1.4 `stock_adj_factor`

- 来源接口：Tushare `adj_factor`。
- 数据粒度：每股每交易日一行。
- 主键：`symbol + trade_date`。
- 更新时间：日线 raw 采集任务同步更新。
- 缺失值处理：指标计算时按交易日合并，必要时使用最近有效复权因子。
- 复权处理：用于计算前复权价格。

前复权规则：

```text
scale(T) = adj_factor(T) / latest_adj_factor
qfq_close(T) = raw_close(T) * scale(T)
qfq_open/qfq_high/qfq_low 同理
```

### 1.5 `stock_stk_limit`

- 来源接口：Tushare `stk_limit`。
- 数据粒度：每股每交易日一行。
- 主键：`symbol + trade_date`。
- 更新时间：日线 raw 采集任务同步更新。
- 缺失值处理：涨跌停价格缺失时，不用该字段限制成交。

关键字段：`up_limit`、`down_limit`。

### 1.6 `stock_suspend_d`

- 来源接口：Tushare `suspend_d`。
- 数据粒度：每股每停复牌记录一行。
- 更新时间：日线 raw 采集任务同步更新。
- 缺失值处理：空表或无记录表示未识别到停牌。

用途：指标计算生成 `is_suspended_t`、`can_buy_open_t`、`can_sell_t` 等交易约束字段。

### 1.7 `stock_daily_basic`

- 来源接口：Tushare `daily_basic`。
- 数据粒度：每股每交易日一行。
- 主键：`symbol + trade_date`。
- 更新时间：日线 raw 采集任务、主股票池初始化。
- 缺失值处理：市值和估值缺失时对应快照字段为空，筛选初始化时按不满足条件处理。

关键字段：`total_mv`、`circ_mv`、`turnover_rate`、`turnover_rate_f`、`volume_ratio`、`pe`、`pb`。

### 1.8 `trade_calendar`

- 来源接口：Tushare `trade_cal`。
- 数据粒度：每个自然日或交易日一行，取决于接口返回。
- 更新时间：raw 采集任务和交易日判断逻辑。
- 缺失值处理：交易日判断会优先访问 Tushare，失败时回落到 SQLite 已有交易日期。

关键字段：`cal_date`、`trade_date`、`is_open`、`pretrade_date`。

### 1.9 `market_context`

- 来源接口：Tushare `index_daily`。
- 数据粒度：每个交易日一行。
- 主键：`trade_date`。
- 更新时间：日线 raw 采集任务同步更新。
- 缺失值处理：指数缺失时相关上下文字段为空。

当前指数范围：上证综指 `000001.SH`、沪深 300 `000300.SH`、创业板指 `399006.SZ`。

常用字段：`sh_close`、`sh_m5`、`sh_m20`、`hs300_close`、`hs300_m20`、`cyb_close`、`cyb_m20` 等。

### 1.10 `stock_daily_features`

- 来源：`stock_daily_raw`、`stock_adj_factor`、`stock_stk_limit`、`stock_suspend_d`、`stock_daily_basic`、`trade_calendar`、`market_context` 计算得到。
- 数据粒度：每股每交易日一行。
- 主键：`symbol + trade_date`。
- 更新时间：`scripts/compute_stock_daily_features.py` 或管理员指标计算按钮。
- 缺失值处理：历史窗口不足时指标为空；停牌或价格缺失时成交约束为不可交易。
- 复权处理：`open/high/low/close` 是前复权信号价格；`raw_open/raw_close` 是成交和估值价格。

关键字段：

| 字段 | 说明 |
| --- | --- |
| `symbol` / `ts_code` / `name` | 股票代码和名称 |
| `trade_date` | 交易日，`YYYYMMDD` |
| `raw_open/raw_high/raw_low/raw_close` | 原始除权价格 |
| `open/high/low/close` | 前复权价格，供信号和指标使用 |
| `adj_factor` | 复权因子 |
| `vol` / `amount` | 成交量、成交额 |
| `pct_chg` | 日涨跌幅百分数 |
| `can_buy_open_t` | 当日开盘是否可买 |
| `can_sell_t` | 当日开盘是否可卖 |
| `m5/m10/m20/m30/m60/m120` | 价格动量 |
| `ma5/ma10/ma20` | 移动均线 |
| `ret1/ret2/ret3` | 短期收益 |
| `amp/amp5` | 单日振幅与 5 日均振幅 |
| `vol5/vol10/vr` | 均量与量比 |
| `amount5/amount10` | 均额 |
| `bias_ma5/bias_ma10` | 均线偏离率 |
| `high_5/high_10/high_20` | 区间最高价 |
| `low_5/low_10/low_20` | 区间最低价 |
| `board/market` | 市场分类字段 |
| `total_mv_snapshot` | 市值快照 |
| `sh_* / hs300_* / cyb_*` | 指数环境字段 |

交易约束口径：

```text
can_buy_open_t:
  非停牌
  且 raw_open 非空
  且未以接近涨停价开盘
  且未以接近跌停价开盘

can_sell_t:
  非停牌
  且 raw_open 非空
  且未以接近跌停价开盘
```

### 1.11 `sector_dashboard_rows` 与 `sector_dashboard_meta`

- 来源：`sector_research/pipeline.py`、`overnight_bt/sector_dashboard_store.py`。
- 数据粒度：`sector_dashboard_rows` 每个 dataset 的每行一条 JSON；`sector_dashboard_meta` 每个元信息键一行。
- 更新时间：运行辅助板块研究链路时更新。
- 缺失值处理：未初始化时 `/sector` 显示暂无数据，不影响核心回测和模拟交易。

## 2. `data_store/stock_pool_templates.sqlite`

这是用户、登录会话和股票池模板库，不是当前行情主库。

| 表 | 用途 | 关键字段 |
| --- | --- | --- |
| `users` | 用户基础信息 | `username`、`password_hash`、`role`、`is_active` |
| `auth_sessions` | 登录会话 | `session_id`、`username`、`expires_at` |
| `stock_pool_templates` | 股票池模板头表 | `username`、`template_name`、`is_active` |
| `stock_pool_template_stocks` | 模板成分股 | `username`、`template_name`、`symbol`、`stock_name` |
| `stock_basic` | 名称解析缓存 | `symbol`、`ts_code`、`name` |
| `stock_daily_features` | 旧共享行情特征表 | 迁移期兼容，不是默认主读取目标 |
| `stock_pool_update_jobs` | legacy 更新任务头表 | `job_id`、`status`、`started_at` |
| `stock_pool_update_job_items` | legacy 更新任务明细 | `job_id`、`symbol`、`status` |

## 3. `data_store/paper_trading.sqlite`

这是模拟交易主账本库。

| 表或视图 | 用途 |
| --- | --- |
| `paper_account_templates` | 模拟账户模板，按 `username + account_id` 管理 |
| `paper_config_snapshot` | 每次运行时的配置快照 |
| `paper_pending_orders` | 待执行订单 |
| `paper_trades` | 成交流水 |
| `paper_holdings` | 当前持仓 |
| `paper_assets` | 每日资产 |
| `paper_logs` | 运行日志 |
| `paper_account_ledgers` | 账本汇总视图 |

## 4. `data_store/scheduler.sqlite`

这是调度状态库。

| 表 | 用途 |
| --- | --- |
| `scheduler_jobs` | 任务名、最近运行、更新时间 |
| `scheduler_job_runs` | 每次运行的状态、目标日期、失败阶段、日志路径和重跑来源 |

管理员后台的“登记重跑”只写入新的 run 记录，不直接执行 shell 命令。

## 5. 更新顺序

日常主链路必须按下面顺序执行：

1. 维护 `main_stock_universe`。
2. 采集 raw 表。
3. 从 raw 表计算 `stock_daily_features`。
4. 回测、每日计划、单股回测和模拟交易读取 `stock_daily_features`。

指标计算不会自动补 raw 数据。若新增主股票池股票，需要先为新增股票采集足够历史区间，再计算指标。
