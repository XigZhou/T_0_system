# T_0_system Project Map

生成时间：2026-06-11
来源：腾讯云 `/home/ubuntu/codex_worktrees/frontend-console-shell` 当前开发 worktree；main branch 主目录为 `/home/ubuntu/T_0_system`
状态：系统已收敛为 SQLite-first 主线；当前 worktree 新控制台 UI 已迁移，数据行情页面使用只读 API 展示因子库和股票日线数据
目的：说明当前真实模块边界、worktree/main 数据源链路，避免后续开发被历史文档或旧链路误导。

## 1. 协作约束

- 当前功能开发和验证先在腾讯云 `/home/ubuntu/codex_worktrees/frontend-console-shell` 完成，不直接修改 `/home/ubuntu/T_0_system` 的代码。
- `/home/ubuntu/T_0_system` 是 main branch 主目录；worktree 测试通过并经用户确认后，再合并回 main branch 主目录。
- 除非用户明确要求，不执行 `git add`、`git commit`、`git push`。
- 默认遵循 `AGENTS.md` 与 `.codex/skills/china-quant-backtest/SKILL.md`。
- 修改代码前先分析模块和依赖；优先增量修改；不默认大规模重构；不修改无关模块。
- 涉及回测、策略、数据库结构、交易成本、复权、成交约束时，先说明影响范围和风险。
- 量化逻辑必须避免未来函数、lookahead bias、train/test 泄漏和 survivorship bias；回测必须严格按时间顺序执行。

## 2. 系统一句话

这是一个 A 股 T 日信号摆动研究、回测、每日计划和多账户模拟交易系统。当前主线用 Tushare、AKShare 和 SQLite 构建主股票池、日线 raw 数据、前复权指标、调度状态、板块看板和模拟交易账本，并通过 FastAPI 静态前端提供管理员、回测、选股、账户和研究入口。

## 3. 目标架构

- 主股票范围由 `data_store/market_data.sqlite.main_stock_universe` 控制。
- `source=all` 等价于 `main_universe`，只代表主股票池活跃集合。
- 日线 raw 输入写入 SQLite raw 表，再由指标计算任务生成 `stock_daily_features`。
- 批量回测、每日选股、单股回测、模拟账户和板块看板优先读 SQLite。
- 旧 CSV、旧 YAML、旧研究输出目录只作为显式兼容或历史复现，不再作为默认运行依赖。

## 4. 顶层目录地图

| 路径 | 当前职责 |
| --- | --- |
| `AGENTS.md` | 仓库协作约束 |
| `README.md` | 安装、启动、数据准备和验证入口 |
| `PROJECT_MAP.md` | 当前项目结构地图 |
| `requirements.txt` | Python 依赖 |
| `frontend/` | 新 React/Vite 控制台 UI，当前功能开发主线 |
| `overnight_bt/` | 核心 Python 包 |
| `scripts/` | CLI 数据准备、调度和迁移脚本 |
| `static/` | 旧静态前端页面与后端静态资源，作为兼容入口保留 |
| `docs/` | 当前正式交付文档，不再存放历史实验报告 |
| `tests/` | 单元测试与接口集成测试 |
| `data_store/` | SQLite 运行时数据库，不提交 |
| `logs/` / `runtime_logs/` | 运行日志，不提交 |
| `configs/paper_accounts/` | 旧 YAML 模拟账户模板，兼容导入来源 |
| `sector_research/` | AKShare 板块研究子系统和运行输出 |
| `paper_trading/` | 历史模拟交易目录，主账本已迁入 SQLite |

## 5. SQLite 数据库地图

| 数据库 | 主要职责 |
| --- | --- |
| `data_store/market_data.sqlite` | 主股票池、A 股基础信息、raw 日线输入、指标表、板块看板 |
| `data_store/stock_pool_templates.sqlite` | 用户、登录会话、股票池模板、迁移期更新任务记录 |
| `data_store/paper_trading.sqlite` | 模拟账户模板、待执行订单、成交、持仓、资产、运行日志 |
| `data_store/scheduler.sqlite` | 每日核心调度运行状态、失败阶段和安全重跑登记 |

## 5.1 Worktree 数据源约定

- worktree 下的 `data_store/` 用于隔离开发期写入型运行数据，不代表生产主行情库。
- 主行情真实数据默认在 `/home/ubuntu/T_0_system/data_store/market_data.sqlite`。
- 数据行情页面只读接口支持通过 `T0_MARKET_DATA_DB_PATH` 指向主行情库，仅影响以下接口：`/api/market-data/factors`、`/api/market-data/stocks`、`/api/market-data/stocks/check`。
- 不要把整个 worktree 的 `data_store/` 软链或整体改到 `/home/ubuntu/T_0_system/data_store`，避免开发测试误写 main 目录的用户、股票池、模拟交易、调度和行情数据。
- worktree 后端调试推荐启动：`T0_MARKET_DATA_DB_PATH=/home/ubuntu/T_0_system/data_store/market_data.sqlite /home/ubuntu/TencentCloud/myenv/bin/python -m uvicorn overnight_bt.app:app --host 127.0.0.1 --port 18083`。
- 合并回 `/home/ubuntu/T_0_system` 后，main 环境可不设置 `T0_MARKET_DATA_DB_PATH`，默认读取 main 自己的 `data_store/market_data.sqlite`。

## 6. 后端模块地图

| 模块 | 当前职责 |
| --- | --- |
| `overnight_bt/app.py` | FastAPI 路由、页面入口、认证保护、管理员 API、导出接口；数据行情只读 API 可通过 `T0_MARKET_DATA_DB_PATH` 覆盖行情库路径 |
| `overnight_bt/auth.py` | 用户注册、登录、session、管理员权限 |
| `overnight_bt/main_universe.py` | 主股票池保存、名称解析、代码标准化 |
| `overnight_bt/market_data_store.py` | 初始化/写入/读取 `stock_daily_features` 和主库辅助表 |
| `overnight_bt/stock_pool_feature_store.py` | Tushare raw 采集、SQLite raw 入库、指标计算、任务日志 |
| `overnight_bt/sqlite_only_guard.py` | `T0_SQLITE_ONLY` 下阻断旧 CSV/YAML/fallback |
| `overnight_bt/backtest.py` | 组合回测、资金/仓位/手续费/滑点/严格成交、导出 |
| `overnight_bt/signal_quality.py` | 信号质量评估 |
| `overnight_bt/daily_plan.py` | 每日计划、持仓卖出提醒、次日买入列表 |
| `overnight_bt/single_stock.py` | 单股回测 |
| `overnight_bt/paper_trading.py` | 多账户模拟交易账本和执行逻辑 |
| `overnight_bt/sector_dashboard.py` | 板块看板 payload，默认读 SQLite |
| `overnight_bt/scheduler.py` | 调度运行记录 |
| `overnight_bt/trade_calendar.py` | A 股交易日判断，优先 Tushare，失败时读 SQLite |

## 7. 脚本地图

| 脚本 | 当前用途 |
| --- | --- |
| `scripts/init_main_universe_from_tushare.py` | 按非 ST、非退市、市值阈值初始化主股票池 |
| `scripts/collect_stock_daily_raw.py` | 把主股票池日线 raw 输入采集进 SQLite raw 表 |
| `scripts/compute_stock_daily_features.py` | 从 SQLite raw 表计算 `stock_daily_features` |
| `scripts/run_core_after_close_pipeline.sh` | 每日核心调度：交易日判断、raw 采集、指标计算、模拟交易盘后 |
| `scripts/run_after_close_pipeline.sh` | 兼容入口，当前委托给核心 SQLite 调度 |
| `scripts/run_paper_trading.py` | 手工运行模拟账户 generate/execute/mark/refresh |
| `scripts/run_paper_trading_cron.sh` | 模拟交易定时任务包装 |
| `scripts/migrate_legacy_stock_pool_to_market_data.py` | 迁移旧股票池特征表到主行情库 |
| `scripts/soft_reset_sqlite_runtime.py` | 软重置 SQLite 运行数据并种入样本 |
| `scripts/verify_delivery.py` | 交付前基础文档和入口检查 |

旧研究脚本仍在 `scripts/` 中，但不属于当前日常主链路。

## 8. 前端页面与 API 入口（新控制台优先）

新控制台 React/Vite 入口位于 `frontend/`，旧 `static/` 目录保留为兼容入口或后端静态资源，不再作为新 UI 开发主线。

| 页面 | 文件 | 关键 API |
| --- | --- | --- |
| 新控制台壳 | `frontend/src/app/App.tsx`、`frontend/src/navigation/menu.tsx` | React Router 路由、左侧导航、旧路径 alias |
| 数据行情 / 因子库 | `frontend/src/features/marketData/MarketDataPage.tsx`、`frontend/src/features/marketData/marketData.css` | `/market-data/factors`、`/api/market-data/factors` |
| 数据行情 / 股票日线数据 | `frontend/src/features/marketData/MarketDataPage.tsx`、`frontend/src/features/marketData/marketData.css` | `/market-data/stocks`、`/api/market-data/stocks`、`/api/market-data/stocks/check` |
| 登录/注册 | `static/login.html`、`static/register.html`、`static/auth.js` | `/api/auth/*` |
| 组合回测 | `static/index.html`、`static/app.js` | `/api/run-backtest`、导出接口 |
| 单股回测 | `static/single.html`、`static/single.js` | `/api/run-single-stock` |
| 每日计划 | `static/daily.html`、`static/daily.js` | `/api/daily-plan` |
| 多账户模拟 | `static/paper.html`、`static/paper.js` | `/api/paper/run`、`/api/paper/ledger` |
| 模拟账户模板 | `static/paper_templates.html`、`static/paper_templates.js` | `/api/paper/templates` |
| 股票池模板 | `static/stock_pools.html`、`static/stock_pools.js` | `/api/stock-pools/*` |
| 系统管理员 | `static/admin.html`、`static/admin.js` | `/api/admin/*` |
| 用户管理 | `static/users.html`、`static/users.js` | `/api/users*` |
| 板块看板 | `static/sector.html`、`static/sector.js` | `/api/sector/overview` |

## 9. 核心数据流

管理员触发链路：`/admin` -> 主股票池 -> raw 采集 -> raw tables -> 指标计算 -> `stock_daily_features` -> 回测/每日计划/单股/模拟交易。

每日核心调度链路：`run_core_after_close_pipeline.sh` -> 交易日判断 -> `collect_stock_daily_raw.py --source all` -> `compute_stock_daily_features.py --source all` -> `run_paper_trading_cron.sh after-close` -> `scheduler.sqlite`。

辅助板块链路：`run_aux_research_pipeline.sh` -> `run_sector_research.py` -> AKShare 板块研究 -> `sector_dashboard_rows/meta` -> `/api/sector/overview`。

## 10. 当前正式文档

`docs/` 只保留当前系统说明、SQLite 数据字典、回测字段、指标说明、表达式说明、模拟交易说明、调度说明和两个模板文件。历史研究报告、旧 CSV 数据字典、旧设计稿和 superpowers 过程稿已从 `docs/` 移除。

## 11. 高风险区域

- `overnight_bt/expressions.py`：条件和评分表达式会影响全部策略入口。
- `overnight_bt/processing.py` 与 `overnight_bt/indicators.py`：指标口径变更会影响历史回测对比。
- `overnight_bt/backtest.py` 与 `overnight_bt/paper_trading.py`：成交价格、手续费、滑点、持仓和资金逻辑变更会影响收益。
- `overnight_bt/stock_pool_feature_store.py`：Tushare 采集和 SQLite 写入逻辑变更可能影响每日核心链。
- `scripts/run_core_after_close_pipeline.sh`：每日生产调度入口，改动后必须跑 `--check-only`。
