# 系统使用文档

本文档说明当前系统各功能模块的用途、输入参数、输出结果与异常处理方式。当前实现以 SQLite 为主数据链路：主股票池、日线 raw、指标、模拟交易账本和调度状态都写入 `data_store/` 下的 SQLite 数据库。

新控制台文档优先使用规范路径；`/single`、`/daily`、`/paper` 等短路径仍作为兼容入口保留，会直接进入对应的新控制台页面。

## 1. 登录、注册与用户管理

入口：`/login`、`/register`、`/system/users`

主要 API：

| API | 用途 |
| --- | --- |
| `GET /api/auth/me` | 查询当前登录用户 |
| `POST /api/auth/register` | 注册普通用户 |
| `POST /api/auth/login` | 登录并写入 session |
| `POST /api/auth/logout` | 退出登录 |
| `GET /api/users` | 管理员查看用户列表 |
| `POST /api/users/{username}/status` | 管理员启停用户 |
| `POST /api/users/{username}/password` | 管理员重置密码 |

数据位置：`data_store/stock_pool_templates.sqlite` 中的 `users` 与 `auth_sessions`。

异常处理：未登录访问受保护页面会跳转登录；非管理员访问管理员接口返回 403；密码缺失或用户不存在返回 400/404。

## 2. 系统管理员后台

入口：`/system/admin`

后台包含运维总览、主股票池维护、日线 raw 采集、指标计算、调度运行记录和失败任务安全重跑登记。

### 2.1 主股票池维护

主股票池表：`data_store/market_data.sqlite.main_stock_universe`

功能：读取活跃或全部主股票池；按股票名称解析股票代码；追加或激活股票；替换活跃集合。替换时，本次未提交的旧股票会被置为 inactive。

主要 API：

| API | 输入 | 输出 |
| --- | --- | --- |
| `GET /api/admin/main-universe` | `include_inactive` | 当前主股票池行 |
| `POST /api/admin/main-universe/resolve` | `names` | 解析成功、未匹配、重复、歧义列表 |
| `POST /api/admin/main-universe/save` | `mode`、`rows`、`source` | 写入数量和诊断信息 |

异常处理：输入空列表、无法解析、歧义名称、非管理员权限会返回错误。解析接口不写库，保存接口才写库。

### 2.2 日线 raw 采集

默认范围：`source=all`，等价于主股票池活跃股票，不代表全市场。

页面按钮：

| 按钮 | API | 日期口径 |
| --- | --- | --- |
| 采集今日日线 | `POST /api/admin/stock-data/daily/today` | 服务器当天日期 |
| 采集区间日线 | `POST /api/admin/stock-data/daily/range` | 页面开始日期到结束日期 |

请求参数：

| 字段 | 说明 |
| --- | --- |
| `start_date` | 区间任务开始日期，`YYYYMMDD` |
| `end_date` | 区间任务结束日期，`YYYYMMDD` |
| `max_symbols` | 最大处理股票数，0 表示不限；常用于测试 |
| `sleep_seconds` | 单股票之间等待秒数 |
| `retry_attempts` | 单股票失败重试次数 |
| `retry_sleep_seconds` | 重试基础等待秒数 |

输出表：`stock_daily_raw`、`stock_adj_factor`、`stock_stk_limit`、`stock_suspend_d`、`stock_daily_basic`、`trade_calendar`、`market_context`。

异常处理：Tushare token 缺失、接口权限不足、日期格式错误、开始日期晚于结束日期、主股票池为空都会失败并返回错误摘要。

### 2.3 指标计算

页面按钮：

| 按钮 | API | 日期口径 |
| --- | --- | --- |
| 计算今日指标 | `POST /api/admin/stock-data/indicators/today` | 服务器当天日期 |
| 计算区间指标 | `POST /api/admin/stock-data/indicators/range` | 页面开始日期到结束日期 |

指标计算从 SQLite raw 表读取，不重新访问单股日线接口。输出写入 `data_store/market_data.sqlite.stock_daily_features`。

边界条件：raw 数据缺失时，对应股票会失败或无有效输出；历史窗口不足时，动量和均线类字段为空；管理员手工任务会覆盖同主键日期范围内的新计算结果。

## 3. 主股票池初始化

命令入口：

```bash
python scripts/init_main_universe_from_tushare.py \
  --db-path data_store/market_data.sqlite \
  --env-path .env \
  --as-of 20260523 \
  --market-cap-min-yi 300
```

逻辑：读取 Tushare `stock_basic` 和最近开市日 `daily_basic.total_mv`，过滤名称包含 `ST` 或 `退` 的股票，再保留总市值大于阈值的股票。Tushare `total_mv` 单位为万元，300 亿对应 `3,000,000` 万元。

输出：更新 `stock_basic` 和 `main_stock_universe`。

## 4. 组合回测

入口：`/backtests/portfolio`

主要 API：`POST /api/run-backtest`、`POST /api/run-signal-quality`、导出接口 `/api/run-backtest-table-export`、`/api/run-backtest-export`

核心输入：

| 字段 | 说明 |
| --- | --- |
| `start_date` / `end_date` | 回测区间 |
| `buy_condition` | 买入条件，逗号分隔表示 AND |
| `sell_condition` | 卖出条件，满足后下一交易日开盘卖出 |
| `score_expression` | 候选排序表达式 |
| `top_n` | 每日最多买入股票数 |
| `initial_cash` | 初始资金 |
| `target_position_value` | 每只股票目标买入金额 |
| `fee_rate` | 买卖手续费率 |
| `slippage_bps` | 滑点 bps |
| `strict_execution` | 是否检查停牌、涨跌停等成交约束 |
| `stock_pool_market_db_path` | 行情指标 SQLite 路径；为空使用 `data_store/market_data.sqlite` |

输出：收益摘要、每日资产、交易流水、持仓、信号候选和导出文件。

成交口径：T 日信号，T+1 开盘买入；卖出使用原始除权开盘价，信号和评分使用前复权指标。回测按日期升序推进，不使用未来数据。

### 组合回测价格与股数口径

- 信号条件、评分表达式和动量指标读取前复权 `open/high/low/close`。
- 实盘账户回测的买入、卖出、现金、持仓市值、期末权益、年度稳定性、月度表现和个股贡献使用未复权除权价格与真实成交股数：成交用 `raw_open`，截止日估值用 `raw_close`。
- 实盘账户回测的 `trade_rows.shares` 是真实成交股数：买入按 `lot_size` 向下取整，卖出沿用持仓真实股数；`adj_factor` 不会调整交易股数。
- 信号质量回测不模拟账户现金和仓位金额占用；其信号样本流水固定按 100 股计算，信号净值从 100000 起步、按每日完成信号平均收益率复利，不代表账户现金加持仓市值。
- 前端“排名质量”只在信号质量回测展示；实盘账户回测页签显示“实盘账户回测不展示排名质量；请使用信号质量回测评估评分表达式排序能力。”

### 组合回测前端结果口径

- 曲线与回撤：信号质量模式看信号净值，实盘账户模式看账户权益。
- 年度稳定性、月度表现：信号质量模式是信号净值稳定性，实盘账户模式是账户权益表现。
- 交易流水：信号质量模式标题为“信号样本流水”，固定 100 股，不用于账户审计；实盘账户模式标题为“真实交易流水”，包含真实股数、成交金额、费用、净金额、交易后现金、盈亏、交易收益和退出原因，可用于审计。
- 个股贡献汇总：信号质量模式展示个股信号收益率贡献，实盘账户模式展示个股已实现盈亏。

## 5. 每日计划

入口：`/trading/daily-plan`

主要 API：`POST /api/daily-plan`

用途：基于某个交易日的 `stock_daily_features` 生成次日买入计划，同时检查已有持仓是否触发卖出条件。

输入：买入条件、卖出条件、评分表达式、目标日期、持仓列表、TopN、价格过滤和 SQLite 路径。

输出：候选股票、计划买入列表、卖出提醒、诊断信息。

## 6. 单股回测

入口：`/backtests/single-stock`

主要 API：`POST /api/run-single-stock`

用途：对单只股票验证买入条件、卖出条件、持有天数、收益和交易明细。

数据来源：默认从 `data_store/market_data.sqlite.stock_daily_features` 读取，股票名称解析依赖主库或股票基础信息。

异常处理：股票无法解析、区间无数据、字段缺失或表达式非法会返回错误。

## 7. 股票池模板

入口：`/portfolio/stock-pools`

主要 API：

| API | 用途 |
| --- | --- |
| `GET /api/stock-pools/templates` | 读取当前用户模板 |
| `POST /api/stock-pools/template` | 保存模板 |
| `POST /api/stock-pools/template/validate` | 校验股票清单 |
| `POST /api/stock-pools/template/refresh` | 兼容入口，按请求范围更新数据 |
| `GET /api/stock-pools/jobs` | 查看历史更新任务 |

当前规则：用户模板中的股票必须在主股票池中处于活跃状态，避免普通用户模板绕过系统主范围。模板库存放在 `stock_pool_templates.sqlite`，不是行情主库。


## 8. 数据行情

控制台入口：`/market-data`

功能：只读展示当前系统已有的行情与指标数据，不执行采集、不执行指标计算，不创建或迁移数据表。页面内部有两个子页签：`因子库` 和 `股票日线数据`。

主要 API：

| API | 用途 |
| --- | --- |
| `GET /api/market-data/factors` | 读取 `stock_daily_features` 中已有的因子字段、公式说明、因子数量和数据时间范围 |
| `GET /api/market-data/stocks` | 读取已有日线数据的股票数量、采集时间范围和每只股票的时间段 |
| `GET /api/market-data/stocks/check` | 按 `stock_name` 检查某只股票是否在当前系统可用 |

输出结果：

| 子页签 | 顶部摘要 | 明细内容 |
| --- | --- | --- |
| 因子库 | 可用因子数量、因子计算开始和结束日期、源表和行数 | 字段、指标名称、分类、输入字段、计算公式、窗口和边界条件 |
| 股票日线数据 | 可用股票数量、股票采集开始和结束日期、源表和行数 | 股票代码、Tushare 代码、股票名称、开始日期、结束日期和行数 |

搜索说明：在“股票日线数据”子页签输入股票名称后点击搜索，系统会弹窗提示该股票在该系统是否可用。可用判断仅基于已落库的日线或指标数据，不触发采集。

异常处理：主行情库不存在、相关表不存在或暂无数据时，接口返回空摘要和只读提示；搜索名称为空时返回 400。

## 9. 多账户模拟交易

入口：`/trading/paper`、`/portfolio/paper-templates`

主要 API：`/api/paper/templates`、`/api/paper/template`、`/api/paper/run`、`/api/paper/ledger`

动作：

| 动作 | 说明 |
| --- | --- |
| `generate` | 收盘后按 T 日信号生成 T+1 待执行订单 |
| `execute` | 开盘后执行到期订单；先卖出后买入 |
| `mark` | 收盘后更新持仓估值和资产 |
| `refresh` | 盘中手工刷新持仓最新价格 |

账本位置：`data_store/paper_trading.sqlite`。

异常处理：订单重复、现金不足、价格缺失、停牌或涨跌停不可成交、股票池指标未更新到目标日，会在订单状态或运行日志中记录。

## 10. 板块看板

入口：`/research/sectors`

主要 API：`GET /api/sector/overview`

用途：展示写入 SQLite 的板块研究结果，包括市场环境、主题排名、强势板块、个股暴露和异常日志。

数据位置：`data_store/market_data.sqlite.sector_dashboard_rows` 与 `sector_dashboard_meta`。如果 SQLite 板块数据未初始化，页面显示暂无数据和提示信息。板块研究脚本仍属于辅助研究链路，不参与每日核心股票 raw 与指标计算。

## 11. 定时任务与调度记录

核心脚本：

```bash
scripts/run_core_after_close_pipeline.sh 20260523
```

兼容入口：

```bash
scripts/run_after_close_pipeline.sh 20260523
```

当前 `run_after_close_pipeline.sh` 委托给核心 SQLite 调度。调度状态写入 `data_store/scheduler.sqlite`，管理员后台只登记安全重跑请求，不直接执行 shell 命令。

## 12. 运维检查

交付检查：

```bash
python scripts/verify_delivery.py
```

核心调度结构检查：

```bash
scripts/run_core_after_close_pipeline.sh --check-only 20260523
```

模拟交易结构检查：

```bash
scripts/run_paper_trading_cron.sh --check-only after-close 20260523
```
