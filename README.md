# T_0_system A 股 SQLite 量化回测与模拟交易系统

这是当前系统的 GitHub 初始化版本。系统运行主线已经从旧 `data_bundle` / per-stock CSV 链路迁移到 SQLite-first：主股票池、日线 raw 数据、指标、调度状态、认证用户和多账户模拟交易账本都以 SQLite 为核心。

当前生产目录在腾讯云：`/home/ubuntu/T_0_system`。默认服务入口是 FastAPI：`overnight_bt.app:app`，线上端口为 `8083`。

## 核心能力

- 主股票池维护：`main_stock_universe` 控制默认采集、指标计算、回测和模拟交易范围。
- 日线 raw 采集：Tushare `daily`、`adj_factor`、`stk_limit`、`suspend_d`、`daily_basic`、`trade_cal`、指数环境统一写入 `market_data.sqlite`。
- 指标计算：从 SQLite raw 表计算 `stock_daily_features`，信号指标使用前复权价格；买入、卖出、现金、持仓市值和权益使用未复权除权价格与真实成交股数，交易股数不随 `adj_factor` 调整。
- 批量回测：实盘账户回测、信号质量评估和交易流水导出；实盘账户流水可用于审计，信号质量流水是固定100股样本。
- 每日计划：每日收盘选股、持仓卖出提醒、次日计划。
- 单股回测：单只股票策略验证。
- 多账户模拟交易：账户模板、待执行订单、成交、持仓、资产、日志落在 SQLite。
- 系统管理员后台：主股票池维护、一键日线采集、一键指标计算、调度记录查看。
- 股票池模板：普通用户维护自选股票模板，保存时受主股票池约束。
- 板块看板：AKShare 板块研究结果可写入 SQLite 并通过 `/sector` 查看。

## 当前 SQLite 主线

主数据库位于：

```text
data_store/market_data.sqlite
```

关键表：

| 表 | 用途 |
| --- | --- |
| `main_stock_universe` | 主股票池，默认采集和计算范围 |
| `stock_basic` | A 股基础信息缓存 |
| `stock_daily_raw` | Tushare 原始日线 |
| `stock_adj_factor` | 复权因子 |
| `stock_stk_limit` | 涨跌停价格 |
| `stock_suspend_d` | 停复牌数据 |
| `stock_daily_basic` | 市值、换手、估值等日度基础面 |
| `trade_calendar` | 交易日历 |
| `market_context` | 大盘指数环境 |
| `stock_daily_features` | 回测和模拟交易读取的股票日线指标 |
| `sector_dashboard_rows` / `sector_dashboard_meta` | 板块看板数据 |

其他运行库：

| SQLite 文件 | 用途 |
| --- | --- |
| `data_store/stock_pool_templates.sqlite` | 用户、登录会话、股票池模板、legacy 更新任务 |
| `data_store/paper_trading.sqlite` | 多账户模拟交易账本 |
| `data_store/scheduler.sqlite` | 定时任务运行记录 |

说明：`data_store/`、`.env`、`logs/`、`runtime_logs/` 都是运行时数据或敏感配置，不提交 GitHub。

## source=all 的当前含义

当前版本中，`source=all` 不再代表全市场股票。

`source=all` 等价于 `source=main_universe`，只处理 `main_stock_universe` 中 `is_active=1` 的股票。管理员后台默认按钮、`scripts/collect_stock_daily_raw.py`、`scripts/compute_stock_daily_features.py` 和核心调度都遵循这个语义。

如果需要改变系统默认股票范围，应先维护主股票池，而不是依赖 `all` 自动扩到全市场。

## 准备工作

### 1. 安装依赖

```bash
python -m pip install -r requirements.txt
```

腾讯云生产环境使用：

```bash
source /home/ubuntu/TencentCloud/myenv/bin/activate
```

### 2. 配置环境变量

Tushare token 从环境变量或 `.env` 读取：

```bash
export TUSHARE_TOKEN="你的 token"
```

管理员默认登录口令不写在代码里。首次初始化用户库前，如果需要启用 `admin` 登录，请在服务器环境或 `.env` 中设置：

```bash
export T0_ADMIN_DEFAULT_PASSWORD="请替换为强密码"
```

或在本地 `.env` 中配置：

```text
TUSHARE_TOKEN=你的 token
T0_ADMIN_DEFAULT_PASSWORD=请替换为强密码
```

`T0_ADMIN_DEFAULT_PASSWORD` 只在 `admin` 用户没有密码时生效，不会覆盖已有管理员密码。不要把 token、真实管理员口令写入代码、README、文档或提交记录。

### 3. 初始化主股票池

按“非 ST、非退市、市值大于 300 亿”初始化主股票池：

```bash
python scripts/init_main_universe_from_tushare.py \
  --db-path data_store/market_data.sqlite \
  --env-path .env \
  --as-of 20260523 \
  --market-cap-min-yi 300
```

Tushare `daily_basic.total_mv` 单位是万元，因此 300 亿对应 `3,000,000` 万元。

### 4. 采集日线 raw 数据

采集当天主股票池日线 raw 输入：

```bash
python scripts/collect_stock_daily_raw.py \
  --source all \
  --start-date 20260523 \
  --end-date 20260523
```

采集区间：

```bash
python scripts/collect_stock_daily_raw.py \
  --source all \
  --start-date 20240101 \
  --end-date 20260523 \
  --retry-attempts 3 \
  --sleep-seconds 0.2
```

### 5. 计算股票指标

从 SQLite raw 表计算指标：

```bash
python scripts/compute_stock_daily_features.py \
  --source all \
  --start-date 20260523 \
  --end-date 20260523
```

指标计算不会重新拉取单股日线；缺 raw 数据时会报错或记录失败项。

## 启动方式

### 本地/服务器直接启动

```bash
python -m uvicorn overnight_bt.app:app --host 0.0.0.0 --port 8083
```

打开：

```text
http://127.0.0.1:8083/
```

腾讯云 systemd 服务名通常为：

```bash
sudo systemctl start t0-system
sudo systemctl status t0-system
```

健康检查：

```bash
curl -sS http://127.0.0.1:8083/health
```

### 页面入口

| 页面 | URL | 用途 |
| --- | --- | --- |
| 登录 | `/login` | 用户登录 |
| 注册 | `/register` | 用户注册 |
| 组合回测 | `/` | 批量回测和导出 |
| 单股回测 | `/single` | 单股策略验证 |
| 每日计划 | `/daily` | 收盘选股和卖出提醒 |
| 多账户模拟 | `/paper` | 模拟账户运行和账本查看 |
| 模拟账户模板 | `/paper/templates` | 模拟账户模板维护 |
| 股票池模板 | `/stock-pools` | 用户股票池模板维护 |
| 系统管理员 | `/admin` | 主股票池、日线采集、指标计算、调度状态 |
| 用户管理 | `/users` | 管理员管理用户 |
| 板块看板 | `/sector` | 板块研究看板 |

## 每日核心调度

核心收盘后调度脚本：

```bash
scripts/run_core_after_close_pipeline.sh 20260523
```

执行顺序：

1. 判断是否 A 股交易日。
2. `scripts/collect_stock_daily_raw.py --source all` 采集主股票池 raw 输入。
3. `scripts/compute_stock_daily_features.py --source all` 计算主股票池指标。
4. `scripts/run_paper_trading_cron.sh after-close` 生成模拟交易盘后计划。
5. 写入 `scheduler.sqlite` 运行记录。

结构检查：

```bash
scripts/run_core_after_close_pipeline.sh --check-only 20260523
```

辅助研究链路：

```bash
scripts/run_aux_research_pipeline.sh 20260523
```

## 管理员后台功能

`/admin` 当前包含：

- 主股票池读取、解析、追加、替换活跃集合。
- 一键采集当天所有主股票池股票日线 raw 数据。
- 一键计算当天所有主股票池股票指标。
- 一键采集指定开始/结束日期的主股票池日线 raw 数据。
- 一键计算指定开始/结束日期的主股票池指标。
- 调度运行记录查看和失败任务登记安全重跑。

如果当前主股票池新增股票，默认采集会对新增股票补 raw 数据；已有股票按 `only_missing`、`force_full_rebuild`、日期区间和批次参数决定是否跳过或重采。

## 回测与模拟交易口径

默认口径：

- 初始资金常用 `100000`。
- 每笔目标资金常用 `10000`。
- 买入股数必须为 100 股整数倍。
- 买卖手续费默认 `0.003%`，无最低消费。
- 信号指标使用前复权价格。
- 买入和卖出成交使用原始除权价格。
- 回测严格按时间顺序执行，禁止未来函数。

20 日动量公式：

```text
m20 = (T日close - (T-19)日close) / (T-19)日close
```

例如五日动量：

```text
m5 = (T日close - (T-4)日close) / (T-4)日close
```

## 复现结果

### 1. 基础交付检查

```bash
python scripts/verify_delivery.py
```

### 2. 关键测试

```bash
env -u PYTEST_ADDOPTS python -m pytest \
  tests/test_main_universe.py \
  tests/test_market_data_store.py \
  tests/test_stock_pool_templates.py \
  tests/test_api_integration.py \
  tests/test_paper_trading.py \
  tests/test_sqlite_only_guard.py \
  tests/test_sqlite_only_pipeline_scripts.py \
  tests/test_trade_calendar.py \
  -q
```

完整测试：

```bash
env -u PYTEST_ADDOPTS python -m pytest -q
```

### 3. 核心链路冒烟

```bash
scripts/run_core_after_close_pipeline.sh --check-only 20260523
curl -sS http://127.0.0.1:8083/health
```

## 兼容旧链路

以下脚本仍保留，用于历史研究、对照或迁移，不是当前默认主链路：

```bash
python scripts/build_universe_snapshot.py --as-of 20260523
python scripts/sync_tushare_bundle.py --start-date 20160101 --end-date 20260523
python scripts/build_processed_data.py
python scripts/init_stock_pool_feature_store.py --source all --start-date 20220101
python scripts/run_stock_pool_template_update.py --source active_templates --username admin --start-date 20220101
scripts/run_after_close_pipeline.sh 20260523
```

这些旧脚本可能读写 `data_bundle/`、per-stock CSV 或旧模板库。SQLite-only 收口时，应优先使用 `scripts/audit_sqlite_only_read_paths.py` 审计默认路径。

## 板块与研究脚本

板块看板入口为 `/sector`。

常用研究脚本：

```bash
python scripts/run_sector_research.py --start-date 20230101
python scripts/run_sector_parameter_grid.py
python scripts/run_sector_rotation_diagnosis.py
python scripts/run_sector_rotation_grid.py
python scripts/run_stock_pool_layer_grid.py
```

这些脚本主要用于研究和报告生成，不属于每日核心日线/模拟交易闭环。相关数据字典和结果说明在 `docs/` 下。

## 主要文档

| 文档 | 用途 |
| --- | --- |
| `PROJECT_MAP.md` | 当前项目结构、SQLite 主线和迁移地图 |
| `docs/system-documentation.md` | 系统功能使用说明 |
| `docs/paper-trading-system.md` | 多账户模拟交易说明 |
| `docs/stock-pool-template-data-dictionary.md` | 股票池模板和任务表数据字典 |
| `docs/sector-dashboard-sqlite-data-dictionary.md` | 板块看板 SQLite 数据字典 |
| `docs/indicator-reference.md` | 指标说明 |
| `docs/expression-reference.md` | 条件表达式说明 |

## GitHub 初始化版本说明

本仓库提交代码、前端、测试和文档；不提交：

- `.env` / `.env.*`
- `data_store/` SQLite 运行库
- `logs/`、`runtime_logs/`
- `data_bundle/`
- `research_runs/`
- `sector_research/data/`、`sector_research/reports/`
- Python 缓存和临时备份文件

如果需要在新环境恢复完整生产数据，应单独备份和恢复 SQLite 数据库，而不是通过 GitHub 分发运行数据。