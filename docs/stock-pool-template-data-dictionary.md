# 股票池模板系统数据说明

本文档说明股票池模板系统的数据来源、SQLite 表结构、字段定义、行情与指标入库、日志输出和使用方式。第一阶段负责“模板 + 手工股票列表”的保存、读取、校验和删除；第二阶段已实现共享日线与指标入库；第四阶段已先把批量回测和每日收盘选股接入股票池模板 SQLite。多账户模拟交易、单股回测和板块研究暂时仍沿用原 CSV 输入。

## 1. 数据来源

### 1.1 用户手工输入

- 页面入口：`/stock-pools`
- API：`POST /api/stock-pools/template`
- 输入方式：用户手工粘贴股票代码列表，支持一行一个、空格、逗号、中文逗号、分号、中文分号分隔。
- 支持格式：`300750`、`600941.SH`、`688981.SH`、`430047.BJ`。系统统一保存 6 位 `symbol` 和 Tushare 风格 `ts_code`。
- 默认用户：`admin`。后续接入登录系统后，`username` 将来自登录态。

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

> 当前未接入登录系统，系统固定使用 `admin` 作为模板所属用户。登录系统接入后，前端应从登录态自动带入用户名，不在页面上提供手工输入。所有模板默认参与后续每日更新，第一阶段不提供“不参与更新”选项。校验和保存时，重复股票会自动去重，只保留首次出现的顺序；股票名称会从 SQLite `stock_basic`、Top500 分层文件、当前 Top100 处理后 CSV 和已有股票池快照中尽量回填。
| 前端页面 | `static/stock_pools.html` | 股票池模板管理页面 |
| 前端逻辑 | `static/stock_pools.js` | 模板列表、载入、复制、保存、删除和校验 |
| 后端模块 | `overnight_bt/stock_pool_templates.py` | SQLite 初始化、模板 CRUD、股票列表解析和基础模板初始化 |
| 行情入库模块 | `overnight_bt/stock_pool_feature_store.py` | 股票范围去重、Tushare 拉取、指标计算、SQLite upsert、任务日志 |
| 初始化脚本 | `scripts/init_stock_pool_feature_store.py` | 全市场或指定来源首次入库 |
| 更新脚本 | `scripts/run_stock_pool_template_update.py` | 活跃模板、单模板或手工股票增量更新 |
| 定时任务脚本 | `scripts/run_stock_pool_template_update.sh` | shell 包装、虚拟环境、锁、cron 日志 |

## 3. 数据粒度与主键

| 表名 | 粒度 | 主键或唯一约束 |
| --- | --- | --- |
| `users` | 每个用户一行 | `username` |
| `stock_pool_templates` | 每个用户的每个模板一行 | `template_id`；业务唯一键 `UNIQUE(username, template_name)` |
| `stock_pool_template_stocks` | 每个模板中的每只股票一行 | `PRIMARY KEY(username, template_name, symbol)` |
| `stock_basic` | 每只股票一行 | `symbol` |
| `stock_daily_features` | 每只股票每个交易日一行 | `PRIMARY KEY(symbol, trade_date)`；批量回测以股票池模板关系表限定股票范围，再按该表读取日线和指标 |
| `stock_pool_update_jobs` | 每个数据更新任务一行 | `job_id` |
| `stock_pool_update_job_items` | 每个任务内每只股票一行 | `PRIMARY KEY(job_id, symbol)` |

第一阶段会创建所有表并写入用户、模板、模板股票关系和基础股票信息。第二阶段开始写入 `stock_daily_features`、`stock_pool_update_jobs`、`stock_pool_update_job_items`。

## 4. 表字段定义

### 4.1 `users`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `username` | TEXT | 用户名，当前默认 `admin` |
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

该表为第二阶段行情和指标入库事实表，所有用户和模板共享同一份股票日线与指标。主要字段如下：

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

说明：当前 `stock_daily_features` 覆盖基准动量、量价、大盘环境和行业/市值快照字段，暂未写入 `sector_*` 板块增强字段。批量回测页和每日收盘选股页因此只开放基准动量预设；板块增强预设需要后续把板块研究字段同步入库后再开放。每日收盘选股按 `username + template_name` 从 `stock_pool_template_stocks` 限定股票范围，再读取 `stock_daily_features` 生成候选买入、卖出提醒和持仓诊断。

## 5. 缺失值和去重规则

- 股票代码格式错误会在校验结果中进入 `invalid_items`，保存时会拒绝写入。
- 重复股票只保留首次出现的位置，重复项进入 `duplicate_symbols`。
- 手工输入没有股票名称时，`stock_name` 保存为空字符串。
- 基础模板来源缺少股票名称时，`stock_name` 也保存为空字符串。
- 删除模板只删除 `stock_pool_templates` 和 `stock_pool_template_stocks` 的模板关系，不删除 `stock_basic`，也不会删除后续阶段写入的日线数据。

## 6. 复权、停牌和行情处理

第二阶段抓取行情并计算指标，口径复用当前 `scripts/build_processed_data.py` 背后的 `build_processed_frame`：

- 信号指标使用前复权价格。
- 买入、卖出和估值使用未复权价格。
- `symbol + trade_date` 作为日线唯一主键，避免同一股票被多个模板引用时重复存储。
- 停牌、涨跌停和开盘不可成交约束与现有 `build_processed_data.py` 输出保持一致。
- 大盘环境来自 `DEFAULT_INDEXES`：上证指数 `000001.SH`、沪深300 `000300.SH`、创业板指 `399006.SZ`。
- 指标窗口包含 `m120/m60/m30/m20/m10/m5`、`ma5/ma10/ma20`、收益率、量价、K 线结构、涨停距离、均线动量等当前批量回测需要的字段。

## 7. 使用方式

### 7.1 页面使用

1. 启动 FastAPI 服务后打开 `/stock-pools`。
2. 选择用户，当前默认 `admin`。
3. 选择已有模板并点击“载入模板”，或点击“新建模板”。
4. 在“手工股票列表”中粘贴股票代码。
5. 点击“校验股票列表”，确认有效、重复和错误项。
6. 点击“保存模板”。保存动作只写 SQLite 模板表，不直接拉取行情，避免大股票池保存超时；新增股票会在夜间统一调度中补齐，也可以由 admin 在页面手动刷新当前模板数据。
7. 如需基于已有模板稍作修改，点击“复制模板”，修改名称或股票列表后保存。
8. 删除模板时只删除模板关系，不删除后续日线事实数据。
9. 只有 admin 会看到“模板数据刷新”和“最近任务状态”区域；普通用户只能维护模板，不能触发行情刷新或查看任务明细。

### 7.2 API 使用

| API | 方法 | 说明 |
| --- | --- | --- |
| `/api/stock-pools/templates?username=admin` | GET | 模板列表 |
| `/api/stock-pools/template?username=admin&template_name=模板名` | GET | 读取单个模板 |
| `/api/stock-pools/template` | POST | 保存模板 |
| `/api/stock-pools/template` | DELETE | 删除模板 |
| `/api/stock-pools/template/validate` | POST | 校验手工股票列表 |
| `/api/stock-pools/templates/seed?username=admin` | POST | 手动初始化基础模板 |
| `/api/stock-pools/template/refresh` | POST | 手动触发行情与指标入库任务；仅 admin |
| `/api/stock-pools/jobs?username=admin&limit=50` | GET | 查看最近更新任务；仅 admin |
| `/api/stock-pools/jobs/{job_id}?username=admin` | GET | 查看任务明细；仅 admin |

### 7.2.1 admin-only 数据刷新接口

当前未接入登录系统时，刷新和任务接口使用 `username=admin` 作为过渡权限判断。非 admin 调用会返回 403。接入登录系统后，应由后端从登录态读取用户名和角色，不再信任前端传入的用户名。

刷新当前模板示例：

```json
{
  "source": "template",
  "username": "admin",
  "template_name": "当前多账户模拟股票池",
  "start_date": "20220101",
  "end_date": "",
  "retry_attempts": 3,
  "retry_sleep_seconds": 5,
  "sleep_seconds": 0.5,
  "only_missing": true
}
```

任务状态字段说明：`stock_pool_update_jobs.status` 表示任务状态，`success_count/failed_count` 表示成功和失败股票数，`message` 记录汇总说明，`log_file/item_csv/summary_json` 记录运行日志、逐股票明细和任务摘要路径。旧任务若没有这些路径，前端显示“历史任务未记录”。

保存模板请求示例：

```json
{
  "username": "admin",
  "original_template_name": "",
  "template_name": "我的AI股票池",
  "description": "用户手工维护的 AI 方向股票列表",
  "is_active": true,
  "stock_text": "300750\n688981\n600941",
  "overwrite_existing": false
}
```


### 7.3 第二阶段 CLI 使用

全市场首次初始化，默认从 `20220101` 到最新交易日：

```bash
python scripts/init_stock_pool_feature_store.py --source all --start-date 20220101
```

只初始化或刷新当前活跃模板涉及股票：

```bash
python scripts/run_stock_pool_template_update.py --source active_templates --username admin --start-date 20220101
```

刷新单个模板：

```bash
python scripts/run_stock_pool_template_update.py --source template --template-name L0_最大市值主题股层 --username admin --start-date 20220101
```

小样本验证，避免一次性消耗太多接口调用：

```bash
python scripts/run_stock_pool_template_update.py --source active_templates --max-symbols 3 --sleep-seconds 0.2
```

分批初始化或补数，适合 2000 到 3000 只股票的大批量任务：

```bash
python scripts/init_stock_pool_feature_store.py \
  --source all \
  --start-date 20220101 \
  --batch-size 200 \
  --batch-index 0 \
  --retry-attempts 3 \
  --retry-sleep-seconds 5
```

断点续跑，适合某批中途断开后从最后完成股票之后继续：

```bash
python scripts/run_stock_pool_template_update.py \
  --source active_templates \
  --resume-after-symbol 300750 \
  --max-symbols 100 \
  --retry-attempts 3
```

核心参数定义：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--batch-size` | `0` | 每批处理股票数；`0` 表示不切批 |
| `--batch-index` | `0` | 批次序号，从 `0` 开始；批次窗口基于完整解析股票列表计算，避免前一批已入库后后一批错位 |
| `--offset` | `0` | 从待处理窗口第 N 只开始；填写后优先于 `batch-index` 计算起点 |
| `--resume-after-symbol` | 空 | 从指定股票代码之后继续处理，例如 `300750` 或 `300750.SZ` |
| `--retry-attempts` | `1` | 单只股票拉取 `daily/adj_factor/stk_limit/suspend_d` 失败后的尝试次数 |
| `--retry-sleep-seconds` | `2.0` | 每次失败后的基础等待秒数，第 N 次按 N 倍等待 |
| `--include-up-to-date` | 关闭 | 默认只补库内未更新到截止交易日的股票；打开后会把已最新股票放入本批并记录为 skipped |
| `--force-full-rebuild` | 关闭 | 强制从起始日重算并 upsert，不执行只补缺失过滤 |
| `--max-symbols` | `0` | 在当前批次窗口内再限制前 N 只，主要用于冒烟验证或临时限流 |

定时任务包装脚本：

```bash
bash scripts/run_stock_pool_template_update.sh 20260514
```

正式自动任务已接入收盘后统一调度第 8 步，不建议再单独配置一个股票池 cron，避免和板块增强、模拟账户收盘任务出现日期错位。统一入口：

```bash
scripts/run_after_close_pipeline.sh 20260514
```

如果股票池较大，可让统一调度在第 8 步连续跑多个批次，并在批次之间暂停：

```bash
STOCK_POOL_BATCH_SIZE=200 STOCK_POOL_BATCH_COUNT=5 STOCK_POOL_BATCH_SLEEP_SECONDS=60 scripts/run_after_close_pipeline.sh 20260514
```

包装脚本支持通过环境变量透传批次和重试参数：`STOCK_POOL_BATCH_SIZE`、`STOCK_POOL_BATCH_INDEX`、`STOCK_POOL_BATCH_COUNT`、`STOCK_POOL_BATCH_SLEEP_SECONDS`、`STOCK_POOL_OFFSET`、`STOCK_POOL_RESUME_AFTER_SYMBOL`、`STOCK_POOL_RETRY_ATTEMPTS`、`STOCK_POOL_RETRY_SLEEP_SECONDS`、`STOCK_POOL_SLEEP_SECONDS`、`STOCK_POOL_MAX_SYMBOLS`、`STOCK_POOL_INCLUDE_UP_TO_DATE=1`。当前 CSV 模拟账户尚未依赖 SQLite，统一调度默认 `RUN_STOCK_POOL_UPDATE_REQUIRED=0`；如果以后把 SQLite 作为强依赖，可设为 `1`。

### 7.4 日志和补救方式

每次入库任务会产生四类可追踪信息：

| 位置 | 内容 | 用途 |
| --- | --- | --- |
| `stock_pool_update_jobs` | 任务级状态、股票数、成功数、失败数、起止日期 | 页面或 API 快速判断任务是否完成 |
| `stock_pool_update_job_items` | 每只股票的状态、写入行数、失败原因 | 定位单只股票失败原因 |
| `logs/stock_pool_template_update/*_<job_id>.log` | 逐步运行日志和异常堆栈 | 排查 Tushare、指标计算或数据库错误 |
| `logs/stock_pool_template_update/<job_id>_items.csv` | 任务明细 CSV | 交付或人工复核 |
| `logs/stock_pool_template_update/<job_id>_summary.json` | 任务摘要 JSON | 自动化读取和归档 |

`summary.json` 新增以下批处理字段，便于判断任务跑到哪里：

| 字段 | 说明 |
| --- | --- |
| `resolved_stock_count` | 本次来源解析并去重后的股票总数 |
| `due_stock_count` | 库内未更新到本次截止交易日的股票数 |
| `prefilter_skipped_count` | 已更新到截止交易日、在只补缺失模式下跳过的股票数 |
| `selected_stock_count` | 本次批次窗口内实际需要执行采集的股票数 |
| `batch_size/batch_index/offset` | 本次批次窗口参数 |
| `batch_start/batch_end` | 本次窗口在解析股票列表中的半开区间 `[start, end)` |
| `resume_after_symbol/resume_skipped_count` | 断点续跑股票和实际跳过数量 |
| `retry_attempts/retry_sleep_seconds` | 单只股票失败重试配置 |
| `only_missing` | 是否启用只补缺失过滤 |

补救规则：

- 如果某些股票失败，先用 `GET /api/stock-pools/jobs/{job_id}` 或明细 CSV 找到失败股票和错误信息。
- 若是 Tushare 临时失败，可用 `--source symbols --stock-text "300750 688981" --retry-attempts 3` 单独补跑失败股票。
- 若某一批中途断开，优先看 `_items.csv` 最后一只成功股票，再用 `--resume-after-symbol` 从其后一只继续。
- 若是指标边界或基础信息问题，可加 `--force-full-rebuild` 从起始日全量重算并 upsert。
- 默认只补缺失，已经完整更新到最新交易日的股票不会重复采集；如需在明细中显式记录 skipped，可加 `--include-up-to-date`。
- 删除模板不会删除 `stock_daily_features`，因为同一股票可能仍被其他模板复用。

## 8. 更新时间

- 模板保存、改名、删除时实时更新 SQLite。
- `/stock-pools` 页面和模板列表 API 会在当前用户没有模板时尝试初始化基础模板。
- 第二阶段已提供手动刷新、初始化脚本和每日更新脚本。
- 第三阶段已把 `scripts/run_stock_pool_template_update.sh` 接入 `scripts/run_after_close_pipeline.sh` 统一收盘后调度。默认 `RUN_STOCK_POOL_TEMPLATE_UPDATE=1`；当前 CSV 模拟账户尚未依赖 SQLite，默认 `RUN_STOCK_POOL_UPDATE_REQUIRED=0`，失败只记录警告并继续模拟账户收盘任务。
- 批量验证记录见 `docs/stock-pool-template-batch-validation-20260514.md`。
