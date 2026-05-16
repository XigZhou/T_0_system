# 多账户模拟交易系统说明

本文档说明多账户模拟交易系统的使用方式、数据来源和运维口径。当前版本已经全面升级为“账户模板 + 股票池模板 SQLite”模式：账户 YAML 不再填写旧的处理后 CSV 目录，股票范围、信号字段、本地成交价和收盘估值价统一来自股票池模板系统。

## 1. 设计目标

- 每个中文 YAML 模板对应一个独立模拟账户。
- 每个账户可以使用不同买入条件、卖出条件、评分表达式、TopN、买入股数、费用、行情源和股票池模板。
- 收盘后基于 T 日股票池 SQLite 指标生成 T+1 待执行订单，开盘后按配置价格模拟成交。
- 已持仓股票不重复买入；已有待买订单时也不重复生成买入订单。
- 先用 Excel 账本存储交易流水、持仓、资产和日志，后续可迁移到账本数据库。

## 2. 文件位置

| 类型 | 路径 |
| --- | --- |
| 交易页面 | `/paper` |
| 账户模板管理页面 | `/paper/templates` |
| 股票池模板管理页面 | `/stock-pools` |
| 账户模板目录 | `configs/paper_accounts/` |
| 默认账户模板 | `configs/paper_accounts/momentum_top5_v1.yaml` |
| 股票池 SQLite | `data_store/stock_pool_templates.sqlite` |
| 账本目录 | `paper_trading/accounts/` |
| 日志目录 | `paper_trading/logs/` |
| 命令行脚本 | `scripts/run_paper_trading.py` |
| 定时任务脚本 | `scripts/run_paper_trading_cron.sh` |

`paper_trading/` 是运行输出目录，已经加入 `.gitignore`，不会把本地模拟账本误提交到仓库。模板建议使用 UTF-8 编码；系统也兼容历史 Windows 模板常见的 GB18030 编码。

打开 `/paper` 时，页面会自动读取所选模板对应的 Excel 账本，并展示待执行订单、成交流水、当前持仓、每日资产和运行日志。`/paper` 只负责模板选择、账本读取、订单生成、成交执行和持仓估值；模板字段编辑已经独立到 `/paper/templates` 页面。

## 3. 数据来源与字段定义

### 股票池模板

多账户模拟交易通过账户 YAML 中的 `股票池` 节点选择股票池模板：

```yaml
股票池:
  用户: admin
  模板名称: 当前多账户模拟股票池
  数据库路径: data_store/stock_pool_templates.sqlite
```

当前未接入登录系统，股票池用户固定为 `admin`。接入登录系统后，前端应从登录态自动带入用户名，不在页面上提供手工输入。

### SQLite 表

| 表 | 用途 | 主键或唯一约束 |
| --- | --- | --- |
| `stock_pool_templates` | 股票池模板基本信息 | `template_id`；业务唯一键 `username + template_name` |
| `stock_pool_template_stocks` | 模板内股票清单 | `username + template_name + symbol` |
| `stock_daily_features` | 共享日线行情和指标事实表 | `symbol + trade_date` |
| `stock_pool_update_jobs` | 股票池数据更新任务状态 | `job_id` |
| `stock_pool_update_job_items` | 每个任务内每只股票状态 | `job_id + symbol` |

### 多账户使用的字段

| 场景 | 读取字段 |
| --- | --- |
| 收盘生成买入候选 | `trade_date`、`symbol`、`name`、动量字段、量价字段、大盘字段、`raw_close` |
| 卖出提醒 | 当前持仓 + `stock_daily_features` 中的卖出条件字段 |
| T 日价格过滤 | `raw_close` |
| 本地日线开盘成交 | `raw_open` |
| 收盘估值 | `raw_close` |
| 严格成交约束 | `can_buy_open_t`、`can_sell_t` |
| 持仓天数 | 同一股票在 `stock_daily_features` 中的交易日序列 |

当前 `stock_daily_features` 覆盖基准动量、量价、大盘环境、行业/市值快照和交易可行性字段，暂未写入 `sector_*` 和 `rotation_*`。因此多账户模拟交易现阶段只应使用基准动量类条件；板块增强模拟账户需要等板块研究字段和轮动字段入库后再恢复增强条件。

## 4. 中文 YAML 模板

示例：

```yaml
账户编号: 动量Top5_v1
账户名称: 动量Top5模拟账户
初始资金: 100000

买入条件: "m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02"
卖出条件: "m20<0.08,hs300_m20<0.02"
评分表达式: "m20 * 140 + (m20 - m60 / 3) * 90 + (m20 - m120 / 6) * 40 - abs(m5 - 0.03) * 55 - abs(m10 - 0.08) * 30"
买入排名数量: 5
买入偏移: 1
最短持有天数: 3
最大持有天数: 15

买入数量:
  方式: 固定股数
  股数: 200
  每手股数: 100
  最低买入金额: 10000

买入价格筛选:
  最低收盘价: 0
  最高收盘价: 100

行情源:
  首选: 东方财富
  备用: 腾讯股票
  价格字段: 开盘价

交易规则:
  持仓时不重复买入: 是
  有待成交订单时不重复买入: 是
  严格成交: 是

费用:
  买卖费率: 0.00003
  印花税: 0
  滑点bps: 3
  最低佣金: 0

输出:
  账本路径: paper_trading/accounts/动量Top5_v1.xlsx
  日志目录: paper_trading/logs

股票池:
  用户: admin
  模板名称: 当前多账户模拟股票池
  数据库路径: data_store/stock_pool_templates.sqlite
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `账户编号` | 模拟账户唯一编号，也用于默认账本文件名 |
| `账户名称` | 页面和账本里展示的账户名称 |
| `初始资金` | 模拟账户初始现金 |
| `股票池.用户` | 股票池模板所属用户，当前固定为 `admin` |
| `股票池.模板名称` | 要使用的股票池模板，例如 `当前多账户模拟股票池` 或 L0-L4 分层模板 |
| `股票池.数据库路径` | 股票池 SQLite 路径，默认 `data_store/stock_pool_templates.sqlite` |
| `买入条件` | 收盘后筛选明日买入候选的表达式 |
| `卖出条件` | 收盘后判断当前持仓是否需要卖出的表达式 |
| `评分表达式` | 对买入候选排序的表达式 |
| `买入排名数量` | 每天最多生成多少只候选买入订单 |
| `买入偏移` | 默认 `1`，表示 T 日信号、T+1 执行 |
| `最短持有天数` | 持仓达到该天数后卖出条件才生效 |
| `最大持有天数` | 达到后可触发卖出提醒 |
| `买入数量.股数` | 每只股票基础买入股数 |
| `买入数量.最低买入金额` | 用 T 日收盘价估算的最低买入市值；不足时按整手向上补足股数 |
| `行情源.首选` | `东方财富`、`腾讯股票` 或 `本地日线`；本地日线从 SQLite 读取价格 |
| `交易规则.严格成交` | 是否检查涨跌停、停牌等成交约束字段 |
| `输出.账本路径` | Excel 账本路径 |
| `输出.日志目录` | 文本日志目录 |

## 5. 前端模板编辑

`/paper/templates` 会先显示模板目录、模板下拉框和模板路径。选择下拉框中的模板后，页面会自动载入当前 YAML 内容，再把字段展开成表单。

页面能力：

- `载入模板`：读取当前 YAML 并填充表单。
- `新建模板`：初始化空白模板草稿。
- `复制模板`：复制当前表单为新草稿，自动生成新文件名、账户编号、账户名称和账本路径。
- `保存模板`：覆盖当前 `模板路径` 指向的 YAML；新建草稿会自动按另存为处理。
- `另存为新模板`：创建新的 YAML。
- `删除模板`：只删除 YAML 文件，不删除 Excel 账本。

保存规则：

- 模板文件名不能包含目录或 `..`，必须是 `.yaml` 或 `.yml`。
- 新模板或另存为不能复用已有模板文件名、账户编号、账户名称和账本路径。
- 新模板的账本路径如果文件已经存在，也会拒绝保存，避免新策略接着旧账本运行。
- 保存时会校验股票池模板存在；如果股票池模板不存在，后端返回错误。

## 6. 每日运行流程

收盘后生成明日订单：

```bash
python scripts/run_paper_trading.py --config configs/paper_accounts/momentum_top5_v1.yaml --action generate --date 20260416
```

下一交易日开盘后执行订单：

```bash
python scripts/run_paper_trading.py --config configs/paper_accounts/momentum_top5_v1.yaml --action execute --date 20260417
```

收盘后更新持仓估值：

```bash
python scripts/run_paper_trading.py --config configs/paper_accounts/momentum_top5_v1.yaml --action mark --date 20260417
```

盘中或收盘后手动刷新当前持仓最新价格：

```bash
python scripts/run_paper_trading.py --config configs/paper_accounts/momentum_top5_v1.yaml --action refresh
```

运行全部模板：

```bash
python scripts/run_paper_trading.py --config-dir configs/paper_accounts --all --action generate --date 20260416
```

当前内置模板：

| 账户 | 模板路径 | 股票池模板 | 说明 |
| --- | --- | --- | --- |
| 动量Top5模拟账户 | `configs/paper_accounts/momentum_top5_v1.yaml` | `当前多账户模拟股票池` | 基准动量 Top5 |
| 动量Top2模拟账户 | `configs/paper_accounts/momentum_top2_v1.yaml` | `当前多账户模拟股票池` | 基准动量 Top2 |
| 板块候选_score0.4_rank0.7 | `configs/paper_accounts/sector_candidate_score04_rank07_v1.yaml` | `当前多账户模拟股票池` | 原板块增强模板，因 SQLite 暂未入库 `sector_*` 字段，当前先切回基准动量条件 |
| 候选_避开新能源主线 | `configs/paper_accounts/sector_rotation_avoid_new_energy_v1.yaml` | `当前多账户模拟股票池` | 原轮动增强模板，因 SQLite 暂未入库 `rotation_*` 字段，当前先切回基准动量条件 |

## 7. 腾讯云定时任务

命令示例：

```bash
scripts/run_paper_trading_cron.sh execute 20260429
scripts/run_paper_trading_cron.sh after-close 20260429
scripts/run_paper_trading_cron.sh --check-only after-close 20260429
```

推荐 crontab：

```cron
35 9 * * 1-5 /home/ubuntu/T_0_system/scripts/run_paper_trading_cron.sh execute >> /home/ubuntu/T_0_system/logs/paper_trading_cron/cron.log 2>&1
30 21 * * * /home/ubuntu/T_0_system/scripts/run_after_close_pipeline.sh >> /home/ubuntu/T_0_system/logs/after_close_pipeline/cron.log 2>&1
```

说明：

- `execute` 在开盘后执行所有模板账户的待成交订单；同一批到期订单会先执行卖出、再执行买入。
- `after-close` 在股票池模板共享行情库更新完成后运行，先更新持仓估值，再生成下一交易日订单。
- 推荐收盘后正式任务使用 `scripts/run_after_close_pipeline.sh`，它会先执行股票池模板共享行情更新，再调用 `scripts/run_paper_trading_cron.sh after-close`。
- 脚本会先判断是否为 A 股交易日，非交易日自动跳过。
- `after-close`、`generate` 和 `mark` 会校验每个模拟账户绑定的股票池模板中所有股票是否已经在 `stock_daily_features` 更新到动作日期；不再检查旧的处理后 CSV 目录。
- `execute` 不做全量股票池日期校验，因为开盘执行只读取已生成订单对应股票在执行日的价格；缺少价格会把单笔订单标记为 `执行失败`。
- `RUN_STOCK_POOL_UPDATE_REQUIRED=1` 表示股票池更新失败时统一调度立即中止；默认 `0` 时会继续进入模拟账户环节，但模拟账户自身仍会做最终日期校验，数据未更新到动作日期时会失败退出。

## 8. 账本怎么看

| Sheet | 用途 |
| --- | --- |
| `配置快照` | 每次运行时写入模板参数，方便复盘当时用的是什么条件 |
| `待执行订单` | 记录 T 日生成、T+1 执行的买入/卖出订单 |
| `成交流水` | 记录真实模拟成交，包含价格、股数、手续费、总金额、实现盈亏和现金余额 |
| `当前持仓` | 只保留未卖出的持仓，包含成本、市值、浮动盈亏、浮动收益率和持有天数 |
| `每日资产` | 记录现金、持仓市值、总资产、累计收益和持仓数量 |
| `运行日志` | 记录每次运行的动作、成交数量、失败数量和异常说明 |

订单状态：

- `待执行`：已经生成但还没有执行。
- `已成交`：已经按配置行情源模拟成交。
- `执行失败`：开盘不可成交、现金不足、找不到行情、已持仓重复买入等原因导致没有成交。

执行顺序：T 日收盘生成的订单可以同时包含买入和卖出。T+1 开盘执行时，系统会处理所有计划执行日期不晚于动作日期的待执行订单；如果同一轮执行里既有卖出又有买入，系统先执行卖出订单，再执行买入订单，让卖出到账资金可以参与后续模拟买入。

## 9. 成交和盈亏计算

买入：

```text
买入成交价 = 开盘价 * (1 + 滑点bps / 10000)
买入成交金额 = 买入成交价 * 股数
买入手续费 = max(买入成交金额 * 买入费率, 最低佣金)
买入总成本 = 买入成交金额 + 买入手续费
```

卖出：

```text
卖出成交价 = 开盘价 * (1 - 滑点bps / 10000)
卖出成交金额 = 卖出成交价 * 股数
卖出手续费 = max(卖出成交金额 * 卖出费率, 最低佣金)
卖出印花税 = 卖出成交金额 * 印花税
卖出到账金额 = 卖出成交金额 - 卖出手续费 - 卖出印花税
实现盈亏 = 卖出到账金额 - 买入总成本
收益率 = 实现盈亏 / 买入总成本
```

持仓估值：

```text
当前市值 = 当前价格 * 股数
浮动盈亏 = 当前市值 - 买入总成本
浮动收益率 = 浮动盈亏 / 买入总成本
总资产 = 现金 + 当前持仓市值
累计收益 = 总资产 / 初始资金 - 1
```

买入价格和股数：生成 T 日收盘买入候选时，系统会先用 T 日未复权收盘价应用 `买入价格筛选`，被过滤的高价或低价股票不会占用最终 TopN 名额；之后再根据 `买入数量.股数`、`买入数量.最低买入金额` 和 `买入数量.每手股数` 计算计划股数。例如股价 25 元、基础 200 股、最低 10000 元时计划买 400 股；股价 70 元、基础 300 股时基础市值已经 21000 元，就仍计划买 300 股。

## 10. 行情源说明

多账户模拟交易现在统一以股票池模板 SQLite 作为本地行情和指标事实表：

- 收盘生成订单读取 `stock_daily_features` 中的 `raw_close`、动量、量价、大盘环境和可交易字段。
- 本地日线成交价读取 `stock_daily_features.raw_open`，收盘估值读取 `stock_daily_features.raw_close`。
- 严格成交会读取 `can_buy_open_t` 和 `can_sell_t`，用于模拟开盘涨跌停、停牌等不可成交场景。
- 持仓天数根据同一只股票在 `stock_daily_features` 中的交易日序列计算。

模块仍保留实时行情源：

- `腾讯股票`
- `东方财富`

实时行情适合开盘后执行模拟订单或手动刷新持仓最新价；如果行情接口失败，订单会标记为 `执行失败`，不会静默使用旧价格成交。若要做离线复盘测试，可以把模板里的 `行情源.首选` 改成 `本地日线`，此时成交与估值都来自股票池 SQLite。

## 11. 和旧系统的关系

- `/` 组合回测已经支持前端选择股票池模板；后端仍保留 `data_source=csv` 兼容旧脚本。
- `/daily` 每日收盘选股已经支持前端选择股票池模板；后端仍保留 `data_source=csv` 兼容旧调用。
- `/single` 单股回测暂时不变，仍按处理后 CSV 目录读取单股数据。
- 多账户模拟交易已经全面切换为股票池模板 SQLite，不再读取账户 YAML 中的旧 `处理后数据目录` 字段，也不再依赖旧 CSV 日线目录。
- 多账户模拟交易复用已有条件表达式、评分表达式和每日计划能力，但股票范围、信号字段、本地成交价和估值价都从 `stock_daily_features` 读取。

## 12. 异常处理

- 模板不存在或 YAML 格式错误时，API 返回 4xx/5xx，并在前端状态栏显示错误。
- 股票池模板不存在时，保存账户模板会失败。
- 股票池模板内股票没有 `stock_daily_features` 日线，或动作日期缺少价格时，订单会执行失败并写入失败原因。
- `after-close`、`generate`、`mark` 发现股票池没有更新到动作日期时，会中止本次任务，避免用旧数据生成新计划。
- 现金不足、已持仓重复买入、开盘不可成交等情况会把订单标记为 `执行失败`，不会隔天继续误买旧信号。
- 如果使用实时行情源失败，订单不会静默成交，会写入失败原因。

## 13. 测试结果

本轮升级后的验证口径：

- 使用测试 SQLite 股票池生成、执行、卖出、估值和读取 Excel 账本。
- 覆盖先卖后买、价格过滤、实时刷新、模板保存/复制/删除、账户模板 API 和前端复制模板行为。
- 腾讯云执行命令：`python -m pytest tests/test_paper_trading.py tests/test_api_integration.py tests/test_paper_frontend_formatting.py -q`，结果为 `27 passed`。
- 交付前还会继续执行完整相关测试、文档检查、脚本语法检查和服务冒烟。