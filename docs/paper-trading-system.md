# 多账户模拟交易系统说明

本文档说明新增的多账户模拟交易系统。它是独立模块，不改变原有组合回测、信号质量回测、每日收盘选股和单股回测逻辑。

## 1. 设计目标

- 每个中文 YAML 模板对应一个独立模拟账户。
- 每个账户可以使用不同买入条件、卖出条件、评分表达式、TopN、买入股数、费用和行情源。
- 收盘后生成 T+1 待执行订单，开盘后按配置价格模拟成交。
- 已持仓股票不重复买入；已有待买订单时也不重复生成买入订单。
- 先用 Excel 账本存储，后续可迁移到 SQLite。

## 2. 文件位置

| 类型 | 路径 |
| --- | --- |
| 页面入口 | `/paper` |
| 模板管理页面 | `/paper/templates` |
| 模板目录 | `configs/paper_accounts/` |
| 默认模板 | `configs/paper_accounts/momentum_top5_v1.yaml` |
| 账本目录 | `paper_trading/accounts/` |
| 日志目录 | `paper_trading/logs/` |
| 命令行脚本 | `scripts/run_paper_trading.py` |

`paper_trading/` 是运行输出目录，已经加入 `.gitignore`，不会把本地模拟账本误提交到仓库。模板建议使用 UTF-8 编码；系统也兼容历史 Windows 模板常见的 GB18030 编码。

打开 `/paper` 时，页面会自动读取所选模板对应的 Excel 账本，并展示待执行订单、成交流水、当前持仓、每日资产和运行日志。如果需要手动刷新，可以点击“读取账本”。该动作是只读操作，不会生成订单或执行成交；读取成功后页面会自动切到“运行日志”页签，并在摘要区展示最后一条日志。

模板编辑已经独立到 `/paper/templates` 页面。`/paper` 只保留模板选择、账本读取、订单生成、成交执行和持仓估值，避免交易页和模板字段编辑混在一起。模板管理页仍然支持载入当前 YAML、新建模板、复制模板、覆盖保存当前模板、另存为新模板和删除模板。模板编辑只写 `configs/paper_accounts/` 下的 YAML 文件，不直接修改 Excel 账本；复制模板只生成一个未落盘的新草稿；删除模板也只删除 YAML，账本保留不动。保存时后端会检查模板文件名、账户编号、账户名称和账本路径冲突，新模板或另存为不能复用已经存在的账本文件，避免旧历史记录和新策略设置混在一起。

## 3. 中文 YAML 模板

示例：

```yaml
账户编号: 动量Top5_v1
账户名称: 动量Top5模拟账户
初始资金: 100000
处理后数据目录: data_bundle/processed_qfq_theme_focus_top100

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
```

### 前端模板编辑

`/paper/templates` 会先显示模板目录、模板下拉框和模板路径。选择下拉框中的模板后，页面会自动载入当前 YAML 内容，再把字段展开成表单：

- 基础信息：模板文件名、账户编号、账户名称、初始资金、处理后数据目录。
- 策略条件：买入条件、卖出条件、评分表达式、买入排名数量、买入偏移、最短/最大持有天数。
- 买入约束：固定股数、每手股数、最低买入金额、最低/最高收盘价。
- 行情与费用：首选/备用行情源、成交价格字段、买入费率、卖出费率、印花税、滑点和最低佣金。
- 风控开关：持仓时不重复买入、有待成交订单时不重复买入、严格成交。
- 输出位置：Excel 账本路径和文本日志目录。

保存与删除规则：

- `保存模板`：覆盖当前 `模板路径` 指向的 YAML；如果当前是“新建模板”状态、没有 `config_path`，前端会自动按“另存为新模板”处理。
- `复制模板`：把当前表单内容复制成一个新模板草稿，自动生成新的模板文件名、账户编号、账户名称和 Excel 账本路径，并清空 `模板路径`；点击 `保存模板` 后才会真正写入 YAML。
- `另存为新模板`：创建新的 YAML，后端拒绝已有模板文件名、已有账户编号、已有账户名称、已有账本路径。
- 新模板的账本路径如果文件已经存在，也会拒绝保存；这是为了防止新策略接着旧账本运行。
- `删除模板`：只删除 YAML 文件，不删除 `paper_trading/accounts/*.xlsx` 账本。需要清理账本时应单独人工确认。
- 模板目录限制在当前 `模板目录` 内，文件名不能包含目录或 `..`。

## 4. 每日运行流程

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

当前新增两个板块增强模拟账户模板：

| 策略 | 模板路径 | 数据目录 | 账本路径 |
| --- | --- | --- | --- |
| 板块候选_score0.4_rank0.7 | `configs/paper_accounts/sector_candidate_score04_rank07_v1.yaml` | `data_bundle/processed_qfq_theme_focus_top100_sector` | `paper_trading/accounts/板块候选_score04_rank07_v1.xlsx` |
| 候选_避开新能源主线 | `configs/paper_accounts/sector_rotation_avoid_new_energy_v1.yaml` | `data_bundle/processed_qfq_theme_focus_top100_sector_rotation` | `paper_trading/accounts/板块轮动_避开新能源_v1.xlsx` |

策略 1 直接读取板块增强目录，核心买入条件是在基础动量、大盘动量过滤后增加 `sector_exposure_score>0`、`sector_strongest_theme_score>=0.4`、`sector_strongest_theme_rank_pct<=0.7`，并按原动量评分表达式取 Top2。策略 2 在策略 1 的基础上增加 `rotation_top_cluster!=新能源`。

为了保证模拟账户可比，`data_bundle/processed_qfq_theme_focus_top100`、`data_bundle/processed_qfq_theme_focus_top100_sector`、`data_bundle/processed_qfq_theme_focus_top100_sector_rotation` 必须是同一批 100 只股票：基础目录只提供原始股票日线和行业字段，板块增强目录增加 `sector_*` 字段，轮动增强目录再增加 `rotation_*` 和 `stock_matches_rotation_*` 字段。不要手工往增强目录追加旧 CSV。运行前建议用统一调度生成轮动增强目录：

```bash
python scripts/build_sector_rotation_features.py \
  --sector-processed-dir data_bundle/processed_qfq_theme_focus_top100_sector \
  --rotation-daily-path research_runs/latest_sector_rotation_diagnosis/sector_rotation_daily.csv \
  --output-dir data_bundle/processed_qfq_theme_focus_top100_sector_rotation \
  --overwrite
```

轮动增强目录的数据定义：股票日线仍来自 `data_bundle/processed_qfq_theme_focus_top100_sector`，轮动字段来自 `sector_rotation_daily.csv`；新增字段包括 `rotation_state`、`rotation_top_theme`、`rotation_top_cluster`、`rotation_top_score`、`rotation_top_rank_pct`、`stock_theme_cluster`、`stock_matches_rotation_top_cluster`。`rotation_feature_manifest.csv` 和 `rotation_feature_metadata.json` 只用于说明生成时间、源目录、源文件和行数，不参与买卖信号计算。`--overwrite` 会先清理输出目录里的旧 CSV，避免 Top100 更新后残留旧股票。

腾讯云定时任务脚本：

```bash
scripts/run_paper_trading_cron.sh execute 20260429
scripts/run_paper_trading_cron.sh after-close 20260429
scripts/run_paper_trading_cron.sh --check-only after-close 20260429
```

推荐 crontab：

```cron
35 9 * * 1-5 /home/ubuntu/T_0_system/scripts/run_paper_trading_cron.sh execute >> /home/ubuntu/T_0_system/logs/paper_trading_cron/cron.log 2>&1
30 21 * * * /home/ubuntu/T_0_system/scripts/run_paper_trading_cron.sh after-close >> /home/ubuntu/T_0_system/logs/paper_trading_cron/cron.log 2>&1
```

说明：

- `execute` 在开盘后执行所有模板账户的待成交订单，适合使用东方财富或腾讯股票实时行情；同一批到期订单会先执行卖出、再执行买入，避免需要卖出释放现金时新买入先因为现金不足失败。
- `after-close` 在数据更新完成后运行，先更新持仓估值，再生成下一交易日订单。
- 推荐收盘后正式任务使用 `scripts/run_after_close_pipeline.sh`，它会先更新基础 Top100、板块研究、板块增强目录和轮动增强目录，再调用本脚本。
- 脚本会先判断是否为 A 股交易日，非交易日自动跳过。
- `after-close` 会检查传入的处理后数据目录是否已经更新到当天；统一调度默认检查轮动增强目录，避免某个板块/轮动账户用旧数据生成计划。
- 生成买入订单时，系统使用 T 日未复权收盘价做价格筛选；超过 `买入价格筛选.最高收盘价` 的股票不会进入最终 TopN，会继续向后寻找符合价格要求的候选。
- `买入数量.股数` 是基础股数，`买入数量.最低买入金额` 是下限；系统会用 T 日收盘价估算买入市值，并按 `买入数量.每手股数` 向上补足。例如股价 25 元、基础 200 股、最低 10000 元，会计划买 400 股；股价 70 元、基础 300 股时，基础市值已经 21000 元，就仍买 300 股。
- `/paper` 页面里的“获取当前持仓最新价格”会调用 `refresh` 动作，只更新当前持仓价格、市值、浮动盈亏和每日资产，不生成订单、不执行买卖。交易时段一般是盘中最新价；已收盘后通常是当日收盘价或收盘后的最新可用价格；非交易日或节假日通常是最近交易日收盘价或行情源最后可用价格。页面摘要和运行日志会写明当时的行情状态。

## 5. 账本怎么看

| Sheet | 用途 |
| --- | --- |
| `配置快照` | 每次运行时写入模板参数，方便复盘当时用的是什么条件 |
| `待执行订单` | 记录 T 日生成、T+1 执行的买入/卖出订单 |
| `成交流水` | 记录真实模拟成交，包含价格、股数、手续费、总金额、实现盈亏和现金余额 |
| `当前持仓` | 只保留未卖出的持仓，包含成本、市值、浮动盈亏、浮动收益率和持有天数 |
| `每日资产` | 记录现金、持仓市值、总资产、累计收益和持仓数量 |
| `运行日志` | 记录每次运行的动作、成交数量、失败数量和异常说明 |

订单状态说明：

- `待执行`：已经生成但还没有执行。
- `已成交`：已经按配置行情源模拟成交。
- `执行失败`：开盘不可成交、现金不足、找不到行情、已持仓重复买入等原因导致没有成交。

执行顺序说明：

- T 日收盘生成的订单可以同时包含买入和卖出。
- T+1 开盘执行时，系统会处理所有计划执行日期不晚于动作日期的待执行订单。
- 如果同一轮执行里既有卖出又有买入，系统先执行卖出订单，再执行买入订单，让卖出到账资金可以参与后续模拟买入。

## 6. 成交和盈亏计算

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

## 7. 行情源说明

本地 Windows 测试默认使用 `本地日线`：

- 买入和卖出执行价来自处理后 CSV 的 `raw_open`。
- 收盘估值价来自处理后 CSV 的 `raw_close`。
- 严格成交会读取 `can_buy_open_t` 和 `can_sell_t`。

模块已经预留实时行情源：

- `腾讯股票`
- `东方财富`

实时行情适合开盘后执行模拟订单；如果行情接口失败，订单会标记为 `执行失败`，不会静默使用旧价格成交。默认模板已经使用 `东方财富`，备用 `腾讯股票`；如果要做离线复盘测试，可以把模板里的 `行情源.首选` 改回 `本地日线`。

## 8. 和旧系统的关系

- 旧的 `/` 组合回测不变。
- 旧的 `/daily` 每日收盘选股不变。
- 旧的 `/single` 单股回测不变。
- 新系统新增 `/paper`、`/paper/templates`、`/api/paper/templates`、`/api/paper/template`、`/api/paper/ledger`、`/api/paper/run`、`overnight_bt/paper_trading.py` 和 `scripts/run_paper_trading.py`。
- 新系统复用已有条件表达式、评分表达式和处理后数据读取能力，避免重复实现指标逻辑。

## 9. 当前本地测试结果

使用本地 `data_bundle/processed_qfq_theme_focus_top100`，以 `20260416` 为信号日、`20260417` 为执行日测试：

- 生成待执行买入订单：5 条。
- T+1 开盘成交：3 条。
- 资金不足失败：2 条。
- 期末现金：`2217.74`。
- 持仓市值：`97324.00`。
- 总资产：`99541.74`。
- 账本路径：`paper_trading/accounts/动量Top5_v1.xlsx`。

这次测试也说明：固定买入 `200` 股时，高价股会显著占用资金，模拟系统能把资金不足问题明确记录出来。
