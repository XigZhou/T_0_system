# 股票池模板系统数据说明

本文档说明第一阶段股票池模板系统的数据来源、SQLite 表结构、字段定义和使用方式。第一阶段只负责“模板 + 手工股票列表”的保存、读取、校验和删除，不抓取行情，不计算指标，也不改变每日收盘选股、多账户模拟交易、批量回测、单股回测和板块研究的现有 CSV 输入。

## 1. 数据来源

### 1.1 用户手工输入

- 页面入口：`/stock-pools`
- API：`POST /api/stock-pools/template`
- 输入方式：用户手工粘贴股票代码列表，支持一行一个、空格、逗号、中文逗号、分号、中文分号分隔。
- 支持格式：`300750`、`600941.SH`、`688981.SH`、`430047.BJ`。系统统一保存 6 位 `symbol` 和 Tushare 风格 `ts_code`。
- 默认用户：`505888`。后续接入登录系统后，`username` 将来自登录态。

### 1.2 基础模板初始化来源

页面打开或调用模板列表 API 时，如果默认用户还没有模板，系统会尝试初始化基础模板：

| 模板 | 来源 | 说明 |
| --- | --- | --- |
| `L0_最大市值主题股层` 到 `L4_最小市值主题股层` | `research_runs/20260509_top500_stock_pool_layer_grid_account/stock_pool_layer_constituents.csv` | 读取 `layer=L0` 到 `layer=L4` 的 Top500 分层成分 |
| `当前多账户模拟股票池` | `data_bundle/processed_qfq_theme_focus_top100/*.csv` | 读取当前多账户模拟默认 Top100 处理后目录中的股票文件名 |

如果上述来源文件或目录不存在，初始化会跳过对应模板，不影响手工新建模板。

## 2. 输出位置

| 项目 | 路径 | 说明 |
| --- | --- | --- |
| SQLite 数据库 | `data_store/stock_pool_templates.sqlite` | 运行时数据库，已加入 `.gitignore`，不提交到 Git |
| 前端页面 | `static/stock_pools.html` | 股票池模板管理页面 |
| 前端逻辑 | `static/stock_pools.js` | 模板列表、载入、复制、保存、删除和校验 |
| 后端模块 | `overnight_bt/stock_pool_templates.py` | SQLite 初始化、模板 CRUD、股票列表解析和基础模板初始化 |

## 3. 数据粒度与主键

| 表名 | 粒度 | 主键或唯一约束 |
| --- | --- | --- |
| `users` | 每个用户一行 | `username` |
| `stock_pool_templates` | 每个用户的每个模板一行 | `template_id`；业务唯一键 `UNIQUE(username, template_name)` |
| `stock_pool_template_stocks` | 每个模板中的每只股票一行 | `PRIMARY KEY(username, template_name, symbol)` |
| `stock_basic` | 每只股票一行 | `symbol` |
| `stock_daily_features` | 每只股票每个交易日一行 | `PRIMARY KEY(symbol, trade_date)` |
| `stock_pool_update_jobs` | 每个数据更新任务一行 | `job_id` |
| `stock_pool_update_job_items` | 每个任务内每只股票一行 | `PRIMARY KEY(job_id, symbol)` |

第一阶段会创建所有表，但只写入用户、模板、模板股票关系和基础股票信息。`stock_daily_features`、`stock_pool_update_jobs`、`stock_pool_update_job_items` 是第二阶段和第三阶段预留表。

## 4. 表字段定义

### 4.1 `users`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `username` | TEXT | 用户名，当前默认 `505888` |
| `password_hash` | TEXT | 后续登录系统预留字段，第一阶段为空 |
| `display_name` | TEXT | 展示名，默认同用户名 |
| `created_at` | TEXT | 创建时间，格式 `YYYY-MM-DD HH:MM:SS` |
| `updated_at` | TEXT | 更新时间 |

### 4.2 `stock_pool_templates`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `template_id` | TEXT | UUID，系统内部模板 ID |
| `username` | TEXT | 模板所属用户 |
| `template_name` | TEXT | 模板名称，同一用户下唯一 |
| `description` | TEXT | 模板说明 |
| `is_active` | INTEGER | 是否参与后续每日更新；第一阶段只保存该标记 |
| `created_at` | TEXT | 创建时间 |
| `updated_at` | TEXT | 更新时间 |

### 4.3 `stock_pool_template_stocks`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `username` | TEXT | 用户名 |
| `template_name` | TEXT | 模板名称 |
| `symbol` | TEXT | 6 位股票代码，例如 `300750` |
| `ts_code` | TEXT | Tushare 风格代码，例如 `300750.SZ` |
| `stock_name` | TEXT | 股票名称；手工输入时可为空，基础模板会尽量从来源文件读取 |
| `display_order` | INTEGER | 股票在用户输入列表中的顺序 |
| `created_at` | TEXT | 加入模板时间 |

### 4.4 `stock_basic`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `symbol` | TEXT | 6 位股票代码 |
| `ts_code` | TEXT | Tushare 风格代码 |
| `name` | TEXT | 股票名称，第一阶段可为空 |
| `industry` | TEXT | 行业，第二阶段补充 |
| `market` | TEXT | 市场，第二阶段补充 |
| `list_date` | TEXT | 上市日期，第二阶段补充 |
| `is_active` | INTEGER | 是否正常上市，第二阶段补充 |
| `updated_at` | TEXT | 更新时间 |

### 4.5 `stock_daily_features`

该表为第二阶段行情和指标入库预留，第一阶段不会写入行情。主要字段如下：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `symbol` | TEXT | 6 位股票代码 |
| `trade_date` | TEXT | 交易日期，格式 `YYYYMMDD` |
| `raw_open/raw_high/raw_low/raw_close` | REAL | 未复权价格，用于后续成交和估值 |
| `qfq_open/qfq_high/qfq_low/qfq_close` | REAL | 前复权价格 |
| `open/high/low/close` | REAL | 回测信号字段，计划与前复权价格保持一致 |
| `vol/amount` | REAL | 成交量、成交额 |
| `up_limit/down_limit` | REAL | 涨跌停价格 |
| `is_suspended_t` | INTEGER | 当日是否停牌 |
| `can_buy_t/can_buy_open_t/can_sell_t/can_sell_t1` | INTEGER | 买卖可执行约束 |
| `m120/m60/m30/m20/m10/m5` | REAL | 动量指标 |
| `ma5/ma10/ma20` | REAL | 均线 |
| `ret1/ret2/ret3/pct_chg` | REAL | 收益率和涨跌幅字段 |
| `bias_ma5/bias_ma10` | REAL | 乖离率 |
| `amp/amp5/high_5/low_5/high_10/low_10/high_20/low_20` | REAL | 波动和区间高低位 |
| `vol5/vol10/vr/amount5/amount10` | REAL | 成交量和成交额指标 |
| `close_to_up_limit/high_to_up_limit/close_pos_in_bar` | REAL | 收盘或最高价相对涨停价、收盘在当日 K 线区间的位置 |
| `body_pct/upper_shadow_pct/lower_shadow_pct` | REAL | K 线实体、上影线、下影线比例 |
| `vol_ratio_3/amount_ratio_3/body_pct_3avg/close_to_up_limit_3max` | REAL | 3 日量价形态指标 |
| `avg5m* / avg10m*` | REAL | 5 日均线和 10 日均线动量，窗口包括 120、60、30、20、10、5 |
| `sh_* / hs300_* / cyb_*` | REAL | 上证指数、沪深300、创业板指的大盘环境字段 |
| `industry/market/board` | TEXT | 行业、市场和板块 |
| `listed_days` | INTEGER | 上市天数 |
| `total_mv_snapshot/turnover_rate_snapshot` | REAL | 市值和换手率快照 |
| `created_at/updated_at` | TEXT | 入库和更新时间 |

## 5. 缺失值和去重规则

- 股票代码格式错误会在校验结果中进入 `invalid_items`，保存时会拒绝写入。
- 重复股票只保留首次出现的位置，重复项进入 `duplicate_symbols`。
- 手工输入没有股票名称时，`stock_name` 保存为空字符串。
- 基础模板来源缺少股票名称时，`stock_name` 也保存为空字符串。
- 删除模板只删除 `stock_pool_templates` 和 `stock_pool_template_stocks` 的模板关系，不删除 `stock_basic`，也不会删除后续阶段写入的日线数据。

## 6. 复权、停牌和行情处理

第一阶段不抓取行情，因此不进行复权、停牌、涨跌停或成交约束计算。第二阶段实现行情入库时需要遵循当前回测系统口径：

- 信号指标使用前复权价格。
- 买入、卖出和估值使用未复权价格。
- `symbol + trade_date` 作为日线唯一主键，避免同一股票被多个模板引用时重复存储。
- 停牌、涨跌停和开盘不可成交约束需要与现有 `build_processed_data.py` 输出保持一致。

## 7. 使用方式

### 7.1 页面使用

1. 启动 FastAPI 服务后打开 `/stock-pools`。
2. 选择用户，当前默认 `505888`。
3. 选择已有模板并点击“载入模板”，或点击“新建模板”。
4. 在“手工股票列表”中粘贴股票代码。
5. 点击“校验股票列表”，确认有效、重复和错误项。
6. 点击“保存模板”。第一阶段保存后只写 SQLite 模板表，不会拉取行情。
7. 如需基于已有模板稍作修改，点击“复制模板”，修改名称或股票列表后保存。
8. 删除模板时只删除模板关系，不删除后续日线事实数据。

### 7.2 API 使用

| API | 方法 | 说明 |
| --- | --- | --- |
| `/api/stock-pools/templates?username=505888` | GET | 模板列表 |
| `/api/stock-pools/template?username=505888&template_name=模板名` | GET | 读取单个模板 |
| `/api/stock-pools/template` | POST | 保存模板 |
| `/api/stock-pools/template` | DELETE | 删除模板 |
| `/api/stock-pools/template/validate` | POST | 校验手工股票列表 |
| `/api/stock-pools/templates/seed?username=505888` | POST | 手动初始化基础模板 |

保存模板请求示例：

```json
{
  "username": "505888",
  "original_template_name": "",
  "template_name": "我的AI股票池",
  "description": "用户手工维护的 AI 方向股票列表",
  "is_active": true,
  "stock_text": "300750\n688981\n600941",
  "overwrite_existing": false
}
```

## 8. 更新时间

- 模板保存、改名、删除时实时更新 SQLite。
- `/stock-pools` 页面和模板列表 API 会在当前用户没有模板时尝试初始化基础模板。
- 第一阶段没有每日定时行情更新任务。
- 第二阶段和第三阶段会增加首次行情采集、指标计算和每日晚间更新任务。
