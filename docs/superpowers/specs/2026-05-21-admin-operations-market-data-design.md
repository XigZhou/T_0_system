# 系统管理员与主数据架构改造设计

生成时间：2026-05-21
适用工作区：/home/ubuntu/T_0_system
状态：已根据讨论结论整理，进入实施计划阶段

## 1. 目标

重新整理系统管理员功能和每日定时任务设计，让系统围绕“生产主数据”和“保障每日模拟账户交易计划”运行。管理员页面不再管理股票池模板数据，而是管理主股票池、核心数据任务、核心交易调度、失败原因和安全重跑。

## 2. 非目标

本次不改变买入条件、卖出条件、手续费、滑点、持仓规则和回测撮合逻辑。本次不删除旧数据库表中的历史数据。本次不把板块研究、轮动研究做成核心交易链路的硬依赖。本次不把完整日志全文写入数据库。

## 3. 当前问题

当前系统把多个职责混在一起：

- 股票池模板既保存股票列表，又通过 `stock_daily_features` 承担行情和指标数据源。
- 系统管理员页把“模板数据刷新”和“最近数据任务”放在主位置，但这些不是每日交易链路的核心。
- 21:30 统一调度把日线更新、板块研究、轮动增强、模板共享行情库、模拟账户 after-close 串成单链路。
- AKShare 板块接口失败会阻断模拟账户生成第二天订单。
- 模板数据更新与主数据更新重复，容易产生两套数据源的日期和字段不一致。

## 4. 核心结论

系统需要拆成四类对象：

1. 主股票池：系统允许采集、计算、回测、选股和交易的股票名单。
2. 主数据：主股票池对应的行情、复权、涨跌停、停牌、指标和交易日历数据。
3. 股票池模板：用户从主股票池中选择的一组股票，只保存股票组合。
4. 调度记录：核心任务和辅助任务每次运行的状态、耗时、错误摘要和日志路径。

生产数据放数据库。日志只用于排障。目录只作为导出、缓存或旧功能兼容，不作为生产真源。

## 5. 数据存储边界

推荐长期结构：

```text
data_store/market_data.sqlite
  main_stock_universe
  stock_basic
  stock_daily_raw
  adj_factor
  stk_limit
  suspend_d
  trade_calendar
  market_context
  stock_daily_features
```

```text
data_store/stock_pool_templates.sqlite
  stock_pool_templates
  stock_pool_template_stocks
```

```text
data_store/scheduler.sqlite
  scheduler_jobs
  scheduler_job_runs
```

```text
logs/
  完整 stdout/stderr 日志文件
```

第一阶段可以保留现有 `data_store/stock_pool_templates.sqlite` 里的旧表，新增代码层抽象把 `stock_daily_features` 视为主数据表，避免一次性破坏迁移。完成兼容后，再把主数据表物理迁移到 `market_data.sqlite`。

## 6. 主股票池设计

主股票池表 `main_stock_universe` 是系统的股票范围源头。它回答“系统要维护哪些股票”，不是行情数据本身。

字段建议：

- `symbol`：六位股票代码，主键。
- `ts_code`：Tushare 代码。
- `stock_name`：股票名称。
- `source`：来源，例如 `admin_upload`、`seed_top100`。
- `is_active`：是否参与主数据采集和指标计算。
- `created_at`、`updated_at`：审计时间。

管理员维护主股票池时仍然输入股票名称，不要求输入股票代码。后端负责把股票名称精确解析为唯一 `symbol`。名称不存在、名称重复或无法唯一匹配时，拒绝写入。

## 7. 股票池模板设计

股票池模板只保存用户选择的股票组合。模板不负责拉行情、不负责算指标、不拥有自己的数据源。

保存模板时：

```text
用户输入股票名称
-> 后端解析股票名称
-> 校验该股票存在于 main_stock_universe 且 is_active=1
-> 校验通过后写入 stock_pool_template_stocks
-> 校验失败则拒绝保存模板
```

因此，模板健康检查不放系统管理员页。模板保存时就必须保证健康。

## 8. 数据采集拆分

核心数据任务只围绕主股票池执行：

1. 主股票池基础信息同步：更新 `stock_basic`，用于名称解析和基础字段。
2. 主股票池日线采集：按 `main_stock_universe` 拉取 `stock_daily_raw`、`adj_factor`、`stk_limit`、`suspend_d`、`trade_calendar`、`market_context`。
3. 主股票池指标计算：基于数据库原始数据计算 `stock_daily_features`。
4. 主数据校验：检查主股票池活跃股票是否更新到目标交易日，必要字段是否存在。

不再有“股票池模板数据更新”核心任务。

## 9. 核心交易调度

每日核心链路：

```text
交易日判断
-> 主股票池日线采集
-> 主股票池指标计算
-> 主数据校验
-> 模拟账户收盘生成下一交易日待执行订单
```

次日开盘链路：

```text
交易日判断
-> 执行待成交订单
-> 更新账本和持仓
```

辅助研究链路：

```text
板块研究
板块增强数据
板块轮动诊断
```

辅助研究失败只在看板报警，不阻断核心订单生成。只有明确使用板块字段的账户才需要在账户级别提示依赖失败。

## 10. 系统管理员页面

管理员页改为“系统运维看板”，保留紧凑中文工作台风格。

页面模块：

1. 核心状态摘要
   - 今日主数据是否更新。
   - 今日指标是否计算。
   - 今日是否生成明日订单。
   - 今日开盘订单是否执行。
   - 最近失败任务和失败摘要。

2. 主股票池维护
   - 当前活跃股票数量。
   - 上传或粘贴股票名称列表。
   - 追加或替换主股票池。
   - 显示解析成功、重复、无法识别、非主板/创业板/科创板等结果。

3. 核心任务运行记录
   - 任务名称。
   - 目标交易日。
   - 状态：成功、失败、运行中、跳过。
   - 开始时间、结束时间、耗时。
   - 失败阶段和错误摘要。
   - 日志路径。

4. 安全重跑
   - 日线采集可重跑。
   - 指标计算可重跑。
   - 收盘生成订单可重跑，但必须幂等，不能重复生成同一订单。
   - 开盘执行订单默认不提供普通重跑按钮，避免重复成交。

管理员页不展示：

- 模板健康检查。
- 模板数据刷新。
- 股票池模板共享行情库。

## 11. 代码职责

新增或调整模块职责如下：

- `overnight_bt/main_universe.py`：主股票池上传、名称解析、保存、替换、追加和查询。
- `overnight_bt/market_data_store.py`：主数据表初始化、读写、按模板股票列表读取指标数据。
- `overnight_bt/market_data_sync.py`：Tushare 主股票池日线采集，写入数据库。
- `overnight_bt/feature_builder.py`：基于数据库原始数据计算指标，写入 `stock_daily_features`。
- `overnight_bt/scheduler.py`：任务定义、运行记录、状态查询、错误摘要、安全重跑。
- `overnight_bt/stock_pool_templates.py`：只负责模板元数据和模板股票列表，不负责行情指标。
- `overnight_bt/paper_trading.py`：读取模板股票列表，再从主数据表读取行情指标，生成或执行模拟账户订单。
- `overnight_bt/backtest.py`、`overnight_bt/daily_plan.py`、`overnight_bt/single_stock.py`：统一使用模板股票列表过滤主数据表。
- `scripts/run_core_after_close_pipeline.sh`：核心收盘链路，只跑采集、计算、校验和订单生成。
- `scripts/run_aux_research_pipeline.sh`：辅助研究链路，单独运行板块和轮动任务。
- `static/admin.html`、`static/admin.js`：系统运维看板。
- `static/stock_pools.html`、`static/stock_pools.js`：模板管理，保存时校验主股票池。

## 12. API 设计

新增或调整 API：

- `GET /api/admin/overview`：管理员看板摘要。
- `GET /api/admin/main-universe`：主股票池列表和统计。
- `POST /api/admin/main-universe/resolve`：解析股票名称列表。
- `POST /api/admin/main-universe/save`：追加或替换主股票池。
- `POST /api/admin/tasks/daily-sync`：手动运行主股票池日线采集。
- `POST /api/admin/tasks/build-features`：手动运行指标计算。
- `GET /api/admin/scheduler/runs`：读取任务运行记录。
- `POST /api/admin/scheduler/runs/{run_id}/retry`：安全重跑失败任务。

保留但降级为 legacy：

- `/api/stock-pools/template/refresh`
- `/api/stock-pools/jobs`
- `/api/stock-pools/jobs/{job_id}`

这些旧 API 不再在系统管理员页展示，不再由核心调度调用。

## 13. 迁移策略

1. 不删除旧表和旧数据。
2. 新增主股票池表和调度表。
3. 把当前模板和已有活跃股票集合导入主股票池。
4. 新的数据读取路径先支持现有 SQLite 中的 `stock_daily_features`，再迁移物理库。
5. 回测、每日选股、单股回测、模拟账户逐步改成“模板列表 + 主数据表”。
6. 从 21:30 调度中移除板块研究硬依赖和股票池模板共享行情库。
7. 管理员页移除模板数据刷新，改成主股票池维护和核心任务看板。

## 14. 风险与控制

- 回测结果风险：数据源切换可能影响 `stock_pool` 模式结果。用相同模板、相同日期、相同条件对比迁移前后结果。
- 订单重复风险：收盘生成订单重跑必须按订单编号或信号日期幂等去重。
- 数据缺失风险：保存模板时严格校验主股票池；生成订单前严格校验主数据目标日期和字段。
- 数据库风险：只新增表和新读写路径，旧表不立即删除。
- 调度风险：辅助研究失败不能阻断核心订单生成，但看板必须暴露失败摘要。

## 15. 验证计划

- 单元测试：主股票池名称解析、模板保存校验、主数据读取过滤、调度状态记录。
- 集成测试：管理员 API、股票池模板 API、模拟账户 after-close、回测 stock_pool 模式。
- 脚本测试：核心收盘链路 check-only、日线采集、指标计算、订单生成。
- 前端冒烟：`/admin`、`/stock-pools`、`/paper`、`/daily`。
- 腾讯云验证：重启 `t0-system` 后检查 `/health`、管理员页、关键 API 和日志。

## 16. 自检结果

本文档已经明确：主数据在数据库中，日志不作为数据源，目录仅做兼容和导出；股票池模板只保存股票组合；系统管理员页只管理主股票池和核心调度；股票池模板数据更新从核心设计中移除。本文档无 TBD/TODO，范围适合拆成多阶段实施计划。
