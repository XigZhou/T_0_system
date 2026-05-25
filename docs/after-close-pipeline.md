# 收盘后核心调度说明

本文档说明当前腾讯云上的收盘后核心调度。当前正式入口是 SQLite 主线：主股票池日线 raw 采集、指标计算、模拟交易盘后任务和调度记录。

## 1. 核心入口

```bash
scripts/run_core_after_close_pipeline.sh YYYYMMDD
```

兼容入口：

```bash
scripts/run_after_close_pipeline.sh YYYYMMDD
```

当前 `run_after_close_pipeline.sh` 只委托给 `run_core_after_close_pipeline.sh`，保留旧调用习惯。

## 2. 默认环境

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PROJECT_DIR` | `/home/ubuntu/T_0_system` | 项目目录 |
| `VENV_ACTIVATE` | `/home/ubuntu/TencentCloud/myenv/bin/activate` | Python 虚拟环境 |
| `LOG_DIR` | `logs/core_after_close_pipeline` | 核心调度日志目录 |
| `LOCK_DIR` | `/tmp/t0_core_after_close_pipeline.lock` | 防并发锁 |
| `STOCK_POOL_SOURCE` | `all` | 当前等价于主股票池活跃股票 |
| `RUN_PAPER_AFTER_CLOSE` | `1` | 是否执行模拟交易盘后任务 |
| `PAPER_CONFIG_DIR` | `configs/paper_accounts` | 模拟账户兼容模板目录 |
| `T0_SQLITE_ONLY` | `1` | 阻断旧 CSV fallback |

## 3. 执行顺序

| 步骤 | 阶段 | 动作 | 输出 |
| --- | --- | --- | --- |
| 1 | `trade_day` | 判断目标日期是否 A 股交易日 | 非交易日跳过 |
| 2 | `record_start` | 写入调度开始记录 | `scheduler.sqlite` |
| 3 | `sqlite_raw_collect` | `collect_stock_daily_raw.py --source all` | SQLite raw 表 |
| 4 | `sqlite_feature_compute` | `compute_stock_daily_features.py --source all` | `stock_daily_features` |
| 5 | `paper_after_close` | `run_paper_trading_cron.sh after-close` | 持仓估值和 T+1 待执行订单 |
| 6 | `record_success` | 写入成功状态 | `scheduler.sqlite` |

任一阶段失败会写入失败阶段和错误摘要。

## 4. check-only

结构检查：

```bash
scripts/run_core_after_close_pipeline.sh --check-only 20260523
```

检查内容：`scripts/collect_stock_daily_raw.py` 存在，`scripts/compute_stock_daily_features.py` 存在，`scripts/run_paper_trading_cron.sh` 可执行，调度日志和状态写入路径可用。

check-only 不采集数据、不计算指标、不运行模拟交易。

## 5. 日线 raw 采集

核心调度调用：

```bash
python scripts/collect_stock_daily_raw.py \
  --source "$STOCK_POOL_SOURCE" \
  --start-date "$RUN_DATE" \
  --end-date "$RUN_DATE" \
  --include-up-to-date \
  --retry-attempts "$FEATURE_RETRY_ATTEMPTS" \
  --retry-sleep-seconds "$FEATURE_RETRY_SLEEP_SECONDS" \
  --sleep-seconds "$FEATURE_SLEEP_SECONDS"
```

`STOCK_POOL_SOURCE=all` 只代表主股票池活跃股票。raw 采集写入 `market_data.sqlite` 中的 `stock_daily_raw`、`stock_adj_factor`、`stock_stk_limit`、`stock_suspend_d`、`stock_daily_basic`、`trade_calendar` 和 `market_context`。

## 6. 指标计算

核心调度调用：

```bash
python scripts/compute_stock_daily_features.py \
  --source "$STOCK_POOL_SOURCE" \
  --start-date "$RUN_DATE" \
  --end-date "$RUN_DATE" \
  --include-up-to-date \
  --retry-attempts "$FEATURE_RETRY_ATTEMPTS" \
  --retry-sleep-seconds "$FEATURE_RETRY_SLEEP_SECONDS" \
  --sleep-seconds "$FEATURE_SLEEP_SECONDS"
```

指标计算从 SQLite raw 表读取并写入 `stock_daily_features`，不会重新拉取单股日线。若 raw 表缺少目标日期或历史窗口，指标会缺失或任务失败。

## 7. 模拟交易盘后

核心调度默认运行：

```bash
CONFIG_DIR="${PAPER_CONFIG_DIR}" scripts/run_paper_trading_cron.sh after-close "$RUN_DATE"
```

`after-close` 会检查模拟账户绑定股票池在目标日期的行情指标是否齐全，然后先执行 `mark` 更新持仓估值，再执行 `generate` 生成下一交易日待执行订单。

如果只想更新行情和指标，不运行模拟交易：

```bash
RUN_PAPER_AFTER_CLOSE=0 scripts/run_core_after_close_pipeline.sh 20260523
```

## 8. cron 示例

建议晚间运行，避开收盘后数据源尚未稳定的窗口：

```cron
30 21 * * 1-5 cd /home/ubuntu/T_0_system && /home/ubuntu/T_0_system/scripts/run_core_after_close_pipeline.sh >> /home/ubuntu/T_0_system/logs/core_after_close_pipeline/cron.log 2>&1
```

开盘执行待成交订单可以独立设置：

```cron
40 9 * * 1-5 cd /home/ubuntu/T_0_system && /home/ubuntu/T_0_system/scripts/run_paper_trading_cron.sh execute >> /home/ubuntu/T_0_system/logs/paper_trading_cron/cron.log 2>&1
```

脚本内部会再次判断是否 A 股交易日，非交易日自动跳过。

## 9. 失败处理

| 失败点 | 可能原因 | 处理 |
| --- | --- | --- |
| `trade_day` | Tushare token 缺失且本地交易日数据不足 | 补充 `.env` 或先采集交易日历 |
| `sqlite_raw_collect` | Tushare 接口失败、主股票池为空、限流 | 查看日志，必要时调大间隔或分批 |
| `sqlite_feature_compute` | raw 数据缺失、字段异常 | 先补 raw，再重算指标 |
| `paper_after_close` | 模拟账户股票池指标未更新、模板错误 | 修复模板或补齐 `stock_daily_features` |

管理员后台 `/admin` 的调度列表可以查看失败阶段并登记安全重跑请求。登记重跑只写库，不直接执行 shell 命令。

## 10. 辅助研究链路

辅助板块研究入口仍保留：

```bash
scripts/run_aux_research_pipeline.sh 20260523
```

该链路用于刷新 `/sector` 看板数据，不属于每日股票 raw 和指标主链路。辅助研究失败不应阻断核心 SQLite 行情指标链，除非后续明确把板块字段纳入交易策略主输入。
