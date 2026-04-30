# 收盘后统一调度任务说明

本文档说明腾讯云上如何用一个定时任务统一调度股票数据、独立板块研究、板块字段合并和模拟账户收盘任务。

## 1. 目标

统一入口：

```bash
scripts/run_after_close_pipeline.sh YYYYMMDD
```

该脚本按固定顺序串行运行，前一步失败就停止，避免股票数据、板块数据和模拟交易订单之间出现日期不一致。

## 2. 推荐运行时间

建议在每个 A 股交易日 `21:30` 运行。东方财富和 AKShare 板块数据在 15:00 刚收盘后可能还未完全稳定，晚间运行更适合作为正式收盘后任务。

如果你希望更早看到结果，可以手工在 `17:30` 后试跑；正式自动任务建议保留在 `21:30`，失败概率更低。

## 3. 执行顺序

| 步骤 | 脚本或动作 | 输出或校验 |
| --- | --- | --- |
| 1 | `scripts/run_daily_top100_update.sh` | 更新 Tushare 股票数据、重建 `processed_qfq`、主题前100和行业强度 |
| 2 | 校验 `data_bundle/processed_qfq_theme_focus_top100` | 至少 100 个股票 CSV，最新日期等于任务日期 |
| 3 | `scripts/run_sector_research.py` | 抓取 AKShare 板块历史、成分股和资金流 |
| 4 | 校验 `sector_research/data/processed` | `theme_strength_daily.csv` 与 `sector_board_daily.csv` 最新日期等于任务日期 |
| 5 | `scripts/build_sector_research_features.py` | 生成 `data_bundle/processed_qfq_theme_focus_top100_sector` |
| 6 | `scripts/run_paper_trading_cron.sh after-close` | 收盘估值并生成 T+1 待执行订单 |

## 4. 关键目录

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `TOP100_DIR` | `data_bundle/processed_qfq_theme_focus_top100` | 股票主数据和行业强度目录 |
| `SECTOR_PROCESSED_DIR` | `sector_research/data/processed` | 独立板块研究指标目录 |
| `SECTOR_REPORT_DIR` | `sector_research/reports` | 板块研究报告目录 |
| `SECTOR_OUTPUT_DIR` | `data_bundle/processed_qfq_theme_focus_top100_sector` | 合并板块字段后的增强目录 |
| `PAPER_CONFIG_DIR` | `configs/paper_accounts` | 模拟账户 YAML 模板目录 |

运行产物和日志位于：

```text
logs/after_close_pipeline/
logs/top100_daily_update/
logs/paper_trading_cron/
sector_research/data/
sector_research/reports/
data_bundle/processed_qfq_theme_focus_top100_sector/
```

这些属于运行数据或日志，不提交到 GitHub。

## 5. 手工运行

腾讯云：

```bash
cd /home/ubuntu/T_0_system
source /home/ubuntu/TencentCloud/myenv/bin/activate
scripts/run_after_close_pipeline.sh 20260430
```

只做轻量检查：

```bash
scripts/run_after_close_pipeline.sh --check-only 20260430
```

只生成数据、不触发模拟账户：

```bash
RUN_PAPER_AFTER_CLOSE=0 scripts/run_after_close_pipeline.sh 20260430
```

## 6. cron 示例

编辑 crontab：

```bash
crontab -e
```

加入一条交易日收盘后任务：

```cron
30 21 * * 1-5 cd /home/ubuntu/T_0_system && /home/ubuntu/T_0_system/scripts/run_after_close_pipeline.sh >> /home/ubuntu/T_0_system/logs/after_close_pipeline/cron.log 2>&1
```

脚本内部会再次判断当天是否为 A 股交易日，周末或非交易日会自动跳过。

如果同时使用开盘执行订单，保留独立的开盘任务：

```cron
40 9 * * 1-5 cd /home/ubuntu/T_0_system && /home/ubuntu/T_0_system/scripts/run_paper_trading_cron.sh execute >> /home/ubuntu/T_0_system/logs/paper_trading_cron/cron.log 2>&1
```

## 7. 失败处理

- 如果 Tushare 股票数据没有更新到任务日期，脚本停止，不生成订单。
- 如果 AKShare 板块数据没有更新到任务日期，脚本停止，不生成订单。
- 如果增强目录缺少 `sector_exposure_score`、`sector_strongest_theme_score`、`sector_strongest_theme_rank_pct`，脚本停止。
- 每次成功会写入 `logs/after_close_pipeline/latest_success.txt`。

## 8. 与模拟账户的关系

当前统一调度会生成增强目录 `data_bundle/processed_qfq_theme_focus_top100_sector`。如果模拟账户买入条件或评分表达式要使用板块字段，需要把账户 YAML 中的 `处理后数据目录` 改为这个增强目录。

在未修改账户 YAML 前，模拟账户仍按原有目录和原有条件运行；统一调度只保证增强目录已经准备好，方便后续逐步接入板块字段。
