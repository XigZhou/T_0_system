# 股票池模板共享行情批量验证记录（2026-05-14）

本文档记录股票池模板共享行情库第二阶段在腾讯云上的真实验证。验证目标是确认 `scripts/run_stock_pool_template_update.sh` 可以从股票池模板读取活跃股票、按批次调用 Tushare 拉取行情、计算批量回测所需指标、写入 SQLite，并生成可追踪日志和任务明细。

## 1. 验证环境

| 项目 | 值 |
| --- | --- |
| 服务器目录 | `/home/ubuntu/T_0_system` |
| Python 环境 | `source /home/ubuntu/TencentCloud/myenv/bin/activate` |
| Git 版本 | `57dbfe0 接入股票池共享行情到收盘后统一调度` |
| 验证日期 | `2026-05-14` |
| 任务截止交易日 | `20260514` |
| SQLite 路径 | `data_store/stock_pool_templates.sqlite` |
| 日志目录 | `logs/stock_pool_template_update/` |
| 验证后磁盘状态 | `/dev/vda2` 40G，剩余约 7.9G，使用率约 80% |

## 2. 数据来源和定义

本次验证使用 `source=active_templates`，默认用户为 `admin`，数据来源为 SQLite 中启用状态的股票池模板。

| 数据 | 来源 | 定义 |
| --- | --- | --- |
| 股票列表 | `stock_pool_templates` + `stock_pool_template_stocks` | `username='admin'` 且 `is_active=1` 的模板股票去重集合 |
| 股票基础信息 | Tushare `stock_basic` | `ts_code`、名称、行业、市场、上市日期等 |
| 日线行情 | Tushare `daily` | 原始开高低收、成交量、成交额、涨跌幅等 |
| 复权因子 | Tushare `adj_factor` | 用于计算前复权价格和信号指标 |
| 涨跌停 | Tushare `stk_limit` | 计算 `can_buy_t`、涨停距离等字段 |
| 停牌 | Tushare `suspend_d` | 计算是否停牌和可买卖状态 |
| 交易日历 | Tushare `trade_cal` | 补齐交易日序列和最新开市日 |
| 大盘环境 | Tushare `index_daily` | 上证、沪深300、创业板指日线和动量字段 |

本次 `admin` 活跃模板去重股票数为 `508`。验证前，`stock_daily_features` 中只有早期测试数据，最新日期为 `20240108`。

## 3. 执行命令

先跑第 0 批 20 只，验证单批补数链路：

```bash
cd /home/ubuntu/T_0_system
source /home/ubuntu/TencentCloud/myenv/bin/activate
STOCK_POOL_BATCH_SIZE=20 \
STOCK_POOL_BATCH_COUNT=1 \
STOCK_POOL_BATCH_INDEX=0 \
STOCK_POOL_RETRY_ATTEMPTS=3 \
STOCK_POOL_RETRY_SLEEP_SECONDS=5 \
STOCK_POOL_SLEEP_SECONDS=0.2 \
scripts/run_stock_pool_template_update.sh 20260514
```

再从第 1 批开始连续跑 2 个批次，验证 `STOCK_POOL_BATCH_COUNT` 的真实连续批次能力：

```bash
cd /home/ubuntu/T_0_system
source /home/ubuntu/TencentCloud/myenv/bin/activate
STOCK_POOL_BATCH_SIZE=20 \
STOCK_POOL_BATCH_COUNT=2 \
STOCK_POOL_BATCH_INDEX=1 \
STOCK_POOL_BATCH_SLEEP_SECONDS=1 \
STOCK_POOL_RETRY_ATTEMPTS=3 \
STOCK_POOL_RETRY_SLEEP_SECONDS=5 \
STOCK_POOL_SLEEP_SECONDS=0.2 \
scripts/run_stock_pool_template_update.sh 20260514
```

之后由于一次 shell 引号误解析，触发了一次未设置批次参数的默认更新命令。该命令仍然运行在“只补缺失”模式下，因此前 60 只已入库股票被自动跳过，只处理剩余 448 只。该任务已完成且失败数为 0。这个结果说明默认全量补缺失链路也可用，但后续人工执行仍应优先显式设置批次参数，避免一次性消耗过多 Tushare 调用。

## 4. 验证结果

| 阶段 | job_id | 批次窗口 | 股票数 | 成功 | 失败 | 截止日期 | 说明 |
| --- | --- | --- | ---: | ---: | ---: | --- | --- |
| batch 0 | `978439b5-c879-4872-a7f1-8cee3b98f4a0` | `[0, 20)` | 20 | 20 | 0 | `20260514` | 单批验证成功 |
| batch 1 | `952ccd91-9f87-4173-a124-1119fd5a3a4f` | `[20, 40)` | 20 | 20 | 0 | `20260514` | 多批次第 1 批成功，前置跳过已入库 20 只 |
| batch 2 | `4ee0c019-28dc-4f8e-b048-50f9b22fe72b` | `[40, 60)` | 20 | 20 | 0 | `20260514` | 多批次第 2 批成功，前置跳过已入库 40 只 |
| 默认只补缺失 | `d13976be-7934-4715-a182-c1919acd3819` | 未切批 | 448 | 448 | 0 | `20260514` | 自动跳过已入库 60 只，补完剩余模板股票 |

最终 SQLite 汇总：

| 指标 | 结果 |
| --- | ---: |
| `admin` 活跃模板去重股票数 | 508 |
| `stock_daily_features` 行数 | 511,172 |
| 已入库股票数 | 508 |
| 最早交易日 | `20220104` |
| 最新交易日 | `20260514` |
| 最新到 `20260514` 的股票数 | 508 |
| SQLite 文件大小 | 约 680 MB |
| 股票池日志目录大小 | 约 392 KB |

## 5. 日志和校验方式

每个 job 会产生三类文件：

| 文件 | 用途 |
| --- | --- |
| `logs/stock_pool_template_update/<job_id>_summary.json` | 查看任务状态、批次窗口、成功失败数、起止日期 |
| `logs/stock_pool_template_update/<job_id>_items.csv` | 查看每只股票的状态、写入行数和失败原因 |
| `logs/stock_pool_template_update/YYYYMMDD_HHMMSS_<job_id>.log` | 查看运行过程、Tushare 调用失败和异常栈 |

本次关键日志文件：

```text
logs/stock_pool_template_update/978439b5-c879-4872-a7f1-8cee3b98f4a0_summary.json
logs/stock_pool_template_update/952ccd91-9f87-4173-a124-1119fd5a3a4f_summary.json
logs/stock_pool_template_update/4ee0c019-28dc-4f8e-b048-50f9b22fe72b_summary.json
logs/stock_pool_template_update/d13976be-7934-4715-a182-c1919acd3819_summary.json
```

可用以下 SQL 复核入库结果：

```sql
SELECT COUNT(*) AS rows,
       COUNT(DISTINCT symbol) AS symbols,
       MIN(trade_date) AS min_date,
       MAX(trade_date) AS max_date
FROM stock_daily_features;

SELECT latest_trade_date, COUNT(*) AS symbol_count
FROM (
    SELECT symbol, MAX(trade_date) AS latest_trade_date
    FROM stock_daily_features
    GROUP BY symbol
)
GROUP BY latest_trade_date
ORDER BY latest_trade_date DESC;

SELECT job_id, status, stock_count, success_count, failed_count, start_date, end_date, message
FROM stock_pool_update_jobs
ORDER BY COALESCE(started_at, created_at) DESC
LIMIT 5;
```

## 6. 结论

本次验证通过。`scripts/run_stock_pool_template_update.sh` 已经能够：

- 从 `admin` 活跃股票池模板解析并去重 508 只股票。
- 按完整股票列表顺序稳定切批，避免前一批入库后后一批错位。
- 使用 Tushare 从 `20220101` 拉取到最新交易日 `20260514`。
- 计算并写入 `stock_daily_features` 所需的价格、动量、均线、涨停距离、可买卖状态、大盘环境等字段。
- 在多批次模式下正确执行 batch 1 和 batch 2，并在批次之间暂停。
- 在默认只补缺失模式下自动跳过已入库股票，并补完剩余 448 只。
- 生成 job 表、item 表、summary JSON、items CSV 和运行日志，便于失败补救。

## 7. 后续建议

1. 当前 `admin` 活跃模板股票已经全部补到 `20260514`，下一步可以先接入每日增量更新，而不是重复全量拉取。
2. 后续夜间统一调度建议显式保留 `STOCK_POOL_BATCH_SIZE=200 STOCK_POOL_BATCH_COUNT=3 STOCK_POOL_BATCH_SLEEP_SECONDS=60` 这类限流参数，避免模板扩容后单次任务过重。
3. 当前模拟账户仍读取 CSV，继续保持 `RUN_STOCK_POOL_UPDATE_REQUIRED=0`；等数据库输入正式接入每日收盘选股、模拟交易、批量回测后，再改为 `1`。
4. 当前 508 只股票约 680 MB，腾讯云剩余约 7.9G，足够支撑模板股票的日常增量；如果后续扩展到全市场 3000 只以上，应先继续清理或扩容。
5. 由于这次已经实际补完 508 只，下一阶段可以优先做“股票池模板数据导出为现有 CSV processed 目录”或“每日增量调度参数固化”，再逐步改造回测/模拟系统输入。