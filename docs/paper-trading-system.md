# 多账户模拟交易系统说明

本文档说明多账户模拟交易系统的使用方式、数据来源和运维口径。当前版本使用 SQLite 保存账户模板、订单、成交、持仓、资产和日志；行情与指标默认读取 `data_store/market_data.sqlite.stock_daily_features`。

## 1. 设计目标

- 每个 SQLite 账户模板对应一个独立模拟账户。
- 每个账户可以使用不同买入条件、卖出条件、评分表达式、TopN、股数、费用、股票池模板和价格设置。
- 收盘后基于 T 日 SQLite 指标生成 T+1 待执行订单。
- 开盘后按配置价格模拟成交。
- 已持仓股票不重复买入；已有待买订单时也不重复生成买入订单。
- 账本按 `username + account_id` 隔离。

## 2. 文件与页面

| 类型 | 路径或入口 |
| --- | --- |
| 交易页面 | `/paper` |
| 账户模板管理页面 | `/paper/templates` |
| 股票池模板管理页面 | `/stock-pools` |
| 账户模板和账本库 | `data_store/paper_trading.sqlite` |
| 股票池模板库 | `data_store/stock_pool_templates.sqlite` |
| 行情指标主库 | `data_store/market_data.sqlite` |
| 兼容 YAML 模板目录 | `configs/paper_accounts/` |
| 命令行脚本 | `scripts/run_paper_trading.py` |
| 定时任务脚本 | `scripts/run_paper_trading_cron.sh` |

旧 YAML 只作为兼容导入来源；页面保存后的模板以 SQLite 为准。

## 3. SQLite 表

| 表或视图 | 用途 |
| --- | --- |
| `paper_account_templates` | 账户模板 |
| `paper_config_snapshot` | 每次运行的配置快照 |
| `paper_pending_orders` | 待执行订单 |
| `paper_trades` | 成交流水 |
| `paper_holdings` | 当前持仓 |
| `paper_assets` | 每日资产 |
| `paper_logs` | 运行日志 |
| `paper_account_ledgers` | 账本汇总视图 |

行情读取表：`market_data.sqlite.stock_daily_features`。股票池模板表：`stock_pool_templates` 与 `stock_pool_template_stocks`。

## 4. 账户模板字段

| 字段 | 说明 |
| --- | --- |
| `账户编号` | 模拟账户唯一编号 |
| `账户名称` | 页面展示名称 |
| `初始资金` | 初始现金 |
| `股票池模板` | 要使用的股票池模板名称 |
| `买入条件` | 收盘后筛选明日买入候选 |
| `卖出条件` | 收盘后判断当前持仓是否需要卖出 |
| `评分表达式` | 买入候选排序表达式 |
| `买入排名数量` | 每天最多生成多少只候选买入订单 |
| `买入偏移` | 默认 1，表示 T 日信号、T+1 执行 |
| `最短持有天数` | 卖出条件生效前的持仓天数 |
| `最大持有天数` | 达到后可触发卖出 |
| `买入股数` | 固定股数模式下每笔基础股数 |
| `每手股数` | A 股通常为 100 |
| `最低买入金额` | 若固定股数金额不足，按整手补足 |
| `最低/最高收盘价` | T 日价格过滤 |
| `严格成交` | 是否检查停牌、涨跌停和价格有效性 |
| `买卖费率` | 手续费率 |
| `印花税` | 卖出印花税率 |
| `滑点bps` | 成交价滑点 |
| `最低佣金` | 最低佣金，当前默认可为 0 |

## 5. 每日运行动作

| 动作 | 命令 | 说明 |
| --- | --- | --- |
| 生成订单 | `python scripts/run_paper_trading.py --all --action generate --date YYYYMMDD` | T 日收盘后生成 T+1 待执行订单 |
| 执行订单 | `python scripts/run_paper_trading.py --all --action execute --date YYYYMMDD` | 开盘后执行计划日期不晚于动作日的订单 |
| 收盘估值 | `python scripts/run_paper_trading.py --all --action mark --date YYYYMMDD` | 用 T 日收盘价更新持仓和资产 |
| 刷新估值 | `python scripts/run_paper_trading.py --all --action refresh` | 手工刷新当前持仓价格 |

定时包装：

```bash
scripts/run_paper_trading_cron.sh execute 20260523
scripts/run_paper_trading_cron.sh after-close 20260523
scripts/run_paper_trading_cron.sh --check-only after-close 20260523
```

`after-close` 会先 `mark`，再 `generate`。

## 6. 数据校验

`generate`、`mark` 和 `after-close` 会检查账户绑定股票池中的股票是否在 `stock_daily_features` 中更新到动作日期。缺少行情时任务失败，避免用旧数据生成订单。

`execute` 不做全量股票池日期校验，只读取已生成订单对应股票在执行日的价格；单笔价格缺失会把订单标记为执行失败。

## 7. 成交口径

买入：

```text
买入成交价 = raw_open * (1 + 滑点bps / 10000)
买入成交金额 = 买入成交价 * 股数
买入手续费 = max(买入成交金额 * 买入费率, 最低佣金)
买入总成本 = 买入成交金额 + 买入手续费
```

卖出：

```text
卖出成交价 = raw_open * (1 - 滑点bps / 10000)
卖出成交金额 = 卖出成交价 * 股数
卖出手续费 = max(卖出成交金额 * 卖出费率, 最低佣金)
卖出印花税 = 卖出成交金额 * 印花税率
卖出到账 = 卖出成交金额 - 卖出手续费 - 卖出印花税
实现盈亏 = 卖出到账 - 对应买入成本
```

执行顺序：同一轮既有卖出又有买入时，先执行卖出订单，再执行买入订单。

## 8. 订单状态

| 状态 | 说明 |
| --- | --- |
| `待执行` | 已生成但还未到执行动作 |
| `已成交` | 已按配置成交 |
| `执行失败` | 价格缺失、不可成交、现金不足、重复买入等原因导致失败 |

## 9. 前端使用

`/paper/templates` 用于创建、复制、保存、另存和停用账户模板。`/paper` 用于选择账户、运行 generate/execute/mark/refresh，并查看待执行订单、成交、持仓、资产和日志。

页面不会让用户直接编辑账本路径、日志目录或 SQLite 路径；这些由系统默认决定。

## 10. 异常处理

常见失败：账户模板缺少股票池模板、股票池模板为空、目标日期不是交易日、股票池指标没有更新到目标日期、成交日缺少 `raw_open`、严格成交下涨停不可买、跌停不可卖或停牌不可交易、现金不足或持仓不足。

失败会写入 `paper_logs`，订单级失败会写入 `paper_pending_orders.失败原因`。
