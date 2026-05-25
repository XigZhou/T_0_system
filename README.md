# T_0_system A 股 SQLite 量化回测与模拟交易系统

T_0_system 是运行在腾讯云 `/home/ubuntu/T_0_system` 的 A 股日线量化系统。当前主线已经收敛为 SQLite-first：主股票池、日线 raw 数据、指标、定时任务状态、认证用户和多账户模拟交易账本都以 SQLite 为核心。旧 `data_bundle` / per-stock CSV 链路只作为历史兼容脚本保留，不再是系统默认依赖。

默认服务入口是 FastAPI：`overnight_bt.app:app`，线上端口为 `8083`。

## 核心能力

- 系统管理员后台：维护主股票池，一键采集日线 raw，一键计算指标，查看和登记调度重跑。
- 主股票池：`main_stock_universe` 控制默认采集、指标计算、回测、每日计划和模拟交易范围。
- 日线 raw 采集：Tushare `daily`、`adj_factor`、`stk_limit`、`suspend_d`、`daily_basic`、`trade_cal` 和指数环境统一写入 `market_data.sqlite`。
- 指标计算：从 SQLite raw 表生成 `stock_daily_features`，信号指标使用前复权价格，买卖成交使用原始除权价格。
- 批量回测、信号质量、每日计划、单股回测：默认读取 SQLite 指标表。
- 多账户模拟交易：账户模板、待执行订单、成交、持仓、资产和日志写入 `paper_trading.sqlite`。
- 认证与用户管理：用户、登录 session 和股票池模板写入 `stock_pool_templates.sqlite`。
- 板块看板：AKShare 板块研究结果可写入 SQLite，并通过 `/sector` 展示。

## 当前 SQLite 主线

主行情数据库：`data_store/market_data.sqlite`

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
| `market_context` | 上证、沪深 300、创业板指环境字段 |
| `stock_daily_features` | 回测、每日计划、单股和模拟交易主输入 |
| `sector_dashboard_rows` / `sector_dashboard_meta` | 板块看板数据 |

其他运行库：

| SQLite 文件 | 用途 |
| --- | --- |
| `data_store/stock_pool_templates.sqlite` | 用户、登录会话、股票池模板、legacy 更新任务记录 |
| `data_store/paper_trading.sqlite` | 多账户模拟交易账本 |
| `data_store/scheduler.sqlite` | 定时任务运行记录 |

`data_store/`、`.env`、`logs/`、`runtime_logs/`、`paper_trading/` 是运行时数据或敏感配置，不提交 GitHub。

## source=all 的当前含义

当前版本中，`source=all` 不再代表全市场股票。`source=all` 等价于 `source=main_universe`，只处理 `main_stock_universe` 中 `is_active=1` 的股票。管理员后台默认按钮、`scripts/collect_stock_daily_raw.py`、`scripts/compute_stock_daily_features.py` 和核心调度都遵循这个语义。

如果需要改变系统默认股票范围，应先维护主股票池。

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
export T0_ADMIN_DEFAULT_PASSWORD="请替换为强密码"
```

`T0_ADMIN_DEFAULT_PASSWORD` 只在 `admin` 用户没有密码时生效，不会覆盖已有管理员密码。不要把 token 或真实管理员口令写入代码、README、文档或提交记录。

### 3. 初始化主股票池

按“非 ST、非退市、市值大于 300 亿”初始化主股票池：

```bash
python scripts/init_main_universe_from_tushare.py \
  --db-path data_store/market_data.sqlite \
  --env-path .env \
  --as-of 20260523 \
  --market-cap-min-yi 300
```

Tushare `daily_basic.total_mv` 单位是万元，300 亿对应 `3,000,000` 万元。

### 4. 采集日线 raw 数据

采集当天主股票池日线 raw 输入：

```bash
python scripts/collect_stock_daily_raw.py --source all --start-date 20260523 --end-date 20260523
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
python scripts/compute_stock_daily_features.py --source all --start-date 20260523 --end-date 20260523
```

指标计算不会重新拉取单股日线；缺 raw 数据时会报错或记录失败项。通常先采集 raw，再计算指标。

## 启动方式

直接启动：

```bash
python -m uvicorn overnight_bt.app:app --host 0.0.0.0 --port 8083
curl -sS http://127.0.0.1:8083/health
```

腾讯云 systemd 服务名通常为：

```bash
sudo systemctl start t0-system
sudo systemctl status t0-system
```

页面入口：`/login`、`/register`、`/`、`/single`、`/daily`、`/paper`、`/paper/templates`、`/stock-pools`、`/admin`、`/users`、`/sector`。

## 每日核心调度

核心收盘后调度脚本：

```bash
scripts/run_core_after_close_pipeline.sh 20260523
```

执行顺序：

1. 判断是否 A 股交易日。
2. `scripts/collect_stock_daily_raw.py --source all` 采集主股票池 raw 输入。
3. `scripts/compute_stock_daily_features.py --source all` 计算主股票池指标。
4. `scripts/run_paper_trading_cron.sh after-close` 先估值持仓，再生成下一交易日待执行订单。
5. 写入 `scheduler.sqlite` 运行记录。

结构检查：

```bash
scripts/run_core_after_close_pipeline.sh --check-only 20260523
```

## 回测与模拟交易口径

- 初始资金常用 `100000`。
- 每笔目标资金常用 `10000`。
- 买入股数必须为 100 股整数倍。
- 买卖手续费默认 `0.003%`，无最低消费。
- 信号指标使用前复权价格。
- 买入和卖出成交使用原始除权价格。
- 回测严格按时间顺序执行，禁止未来函数。

20 日动量公式：

```text
m20 = (T日close - (T-19日close)) / (T-19日close)
```

例如五日动量：

```text
m5 = (T日close - (T-4日close)) / (T-4日close)
```

## 当前文档

| 文档 | 用途 |
| --- | --- |
| `PROJECT_MAP.md` | 当前项目结构、模块边界和迁移状态 |
| `docs/system-documentation.md` | 系统功能使用说明 |
| `docs/sqlite-data-dictionary.md` | 当前 SQLite 数据字典 |
| `docs/backtest-data-dictionary.md` | 回测输入输出字段说明 |
| `docs/indicator-reference.md` | 指标公式说明 |
| `docs/expression-reference.md` | 条件和评分表达式语法 |
| `docs/paper-trading-system.md` | 多账户模拟交易说明 |
| `docs/after-close-pipeline.md` | 定时任务与调度说明 |
| `docs/data-dictionary-template.md` | 数据字典模板 |
| `docs/indicator-documentation-template.md` | 指标文档模板 |

历史研究报告、旧 CSV 数据字典和 superpowers 过程稿已从 `docs/` 移除，避免和当前 SQLite 主线混用。

## 复现结果

基础交付检查：

```bash
python scripts/verify_delivery.py
```

相关测试：

```bash
env -u PYTEST_ADDOPTS python -m pytest \
  tests/test_delivery_checks.py \
  tests/test_auth.py \
  tests/test_main_universe.py \
  tests/test_market_data_store.py \
  tests/test_sqlite_only_guard.py \
  tests/test_sqlite_only_pipeline_scripts.py \
  tests/test_trade_calendar.py -q
```

核心调度结构检查：

```bash
scripts/run_core_after_close_pipeline.sh --check-only 20260523
```

## 旧链路说明

仓库中仍保留若干旧研究脚本，例如 `scripts/build_processed_data.py`、`scripts/sync_tushare_bundle.py`、`scripts/run_sector_*` 和旧 CSV 增强脚本。这些脚本用于历史复现或迁移对照，不代表当前系统默认依赖。当前日常运行请优先使用 SQLite 主链路：主股票池 -> raw 采集 -> 指标计算 -> 回测/每日计划/模拟交易。
