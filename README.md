# T 日信号摆动回测系统 V2

本项目用于研究 A 股日线信号策略：

- `T` 日只使用当日及历史数据生成买入信号
- `T+1` 日按原始开盘价 `raw_open` 买入
- 默认可按 `T+N` 日原始开盘价 `raw_open` 卖出，也支持“收盘触发卖出条件，下一交易日开盘执行”的混合退出模型
- 信号与指标按前复权价格 `qfq_*` 计算
- 买卖成交按原始除权价格 `raw_*` 计算

项目当前包含：

- 固定快照股票池构建
- Tushare 原始数据同步
- 处理后回测主输入生成
- 前端批量回测页面
- 独立板块主题研究系统
- 每日收盘选股与持仓卖出提醒页面
- API 导出交易流水
- 特征分层扫描
- 训练期/验证期参数探索

说明：

- 脚本文件名仍沿用早期的 `run_overnight_*` 命名，但内部逻辑已经切到新的摆动持有模型。

## 默认假设

- 默认按 `2000` 积分 Tushare 权限规划实现。
- 默认接口：`stock_basic`、`daily_basic`、`daily`、`adj_factor`、`trade_cal`、`stk_limit`、`suspend_d`、`index_daily`。
- `TUSHARE_TOKEN` 优先从本机环境变量读取；若缺失，再回退到本地 `.env`。
- 固定快照默认按指定日期或此前最近开市日筛选 `总市值 >= 500亿` 且非 `ST` 股票。
- 信号与指标基于前复权价格；实际成交和资金结算基于原始除权价格。
- 默认探索参数：
  - 初始资金 `100000`
  - 每笔目标资金 `10000`
  - 每手 `100` 股
  - 买卖手续费各 `0.003%`
  - 默认无印花税、无最低佣金
  - 严格成交模式默认开启

这些假设会影响结果正确性。正式跑全量研究前，建议先确认本机数据、交易成本和 Tushare 账号权限与目标环境一致。

## 准备工作

### 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 配置环境变量

推荐直接在本机环境里设置：

```powershell
$env:TUSHARE_TOKEN="你的本机 token"
```

回退方式：

- 在本地 `.env` 中配置 `TUSHARE_TOKEN=...`
- 不要把 token 明文写入代码、文档或提交记录

### 项目结构

- [overnight_bt](/D:/量化/Momentum/T_0_system/overnight_bt)
  回测引擎、处理逻辑、表达式解析、研究与交付检查模块
- [scripts](/D:/量化/Momentum/T_0_system/scripts)
  数据准备、研究、特征扫描与交付校验脚本
- [sector_research](/D:/量化/Momentum/T_0_system/sector_research)
  独立板块研究系统，默认只写自己的数据与报告，不覆盖当前回测主目录
- [static](/D:/量化/Momentum/T_0_system/static)
  前端页面
- [docs](/D:/量化/Momentum/T_0_system/docs)
  中文数据说明、指标说明、表达式说明与系统使用文档
- [tests](/D:/量化/Momentum/T_0_system/tests)
  单元测试与接口集成测试

## 数据准备

### 1. 生成固定快照股票池

```bash
python scripts/build_universe_snapshot.py --as-of 目标交易日
```

输出：

- `data_bundle/universe_snapshot.csv`

### 2. 同步原始数据包

```bash
python scripts/sync_tushare_bundle.py --start-date 20160101 --end-date 目标交易日
```

建议输出目录结构：

```text
data_bundle/
  universe_snapshot.csv
  trade_calendar.csv
  stk_limit.csv
  suspend_d.csv
  market_context.csv
  raw_daily/
  adj_factor/
```

### 3. 生成处理后回测输入

```bash
python scripts/build_processed_data.py
```

输出：

- `data_bundle/processed_qfq/*.csv`
- `data_bundle/processed_qfq/processing_manifest.csv`

如果你改过以下任一内容，需要重新构建 `processed_qfq/`：

- 涨跌停或停牌约束逻辑
- 前复权处理逻辑
- 新增信号特征字段
- `can_buy_open_t` 等开盘成交约束字段

### 4. 生成主题聚焦股票池

如果你要把股票池缩到 AI、机器人、新能源、有色金属、电网等方向，可以运行：

```bash
python scripts/build_theme_focus_universe.py
python scripts/build_theme_focus_universe.py --top-k 100 --out-snapshot data_bundle/universe_snapshot_theme_focus_top100.csv --out-processed-dir data_bundle/processed_qfq_theme_focus_top100
```

输出：

- `data_bundle/universe_snapshot_theme_focus.csv`
- `data_bundle/processed_qfq_theme_focus/`
- `data_bundle/universe_snapshot_theme_focus_top100.csv`
- `data_bundle/processed_qfq_theme_focus_top100/`

说明：

- `theme_focus` 是按主题规则筛出来的全量主题池
- `theme_focus_top100` 是在主题池基础上按总市值取前 100

### 5. 生成行业强度指标

当前 2000 积分方案不依赖 Tushare 行业指数行情，而是用处理后股票日线里的 `industry` 字段自行聚合行业强度。生成或重建 `processed_qfq_theme_focus_top100/` 后，建议继续运行：

```bash
python scripts/build_industry_strength.py --processed-dir data_bundle/processed_qfq_theme_focus_top100
```

默认会把行业指标写回原目录中的每只股票 CSV，并在 `research_runs/YYYYMMDD_HHMMSS_industry_strength/` 生成报告。新增字段包括：

- `industry_m20`、`industry_m60`：行业内股票 20/60 日动量均值
- `industry_rank_m20`、`industry_rank_m60`：行业强度排名百分位，越小越强
- `industry_up_ratio`：行业内当日上涨股票占比
- `industry_strong_ratio`：行业内 `m20>0` 的股票占比
- `industry_amount_ratio`：行业成交额相对 20 日均额的放大倍数
- `stock_vs_industry_m20`、`stock_vs_industry_m60`：个股相对所属行业的动量差

运行后前端条件可以直接写：

```text
industry_rank_m20<0.3,industry_m20>0,industry_up_ratio>0.5,stock_vs_industry_m20>0
```

如果只是想先生成到新目录核对，不覆盖原目录，可以加 `--output-dir`：

```bash
python scripts/build_industry_strength.py --processed-dir data_bundle/processed_qfq_theme_focus_top100 --output-dir data_bundle/processed_qfq_theme_focus_top100_industry
```

### 6. 生成独立板块研究数据

如果你要研究锂矿锂电、光伏新能源、半导体芯片、存储芯片、AI、机器人、医药等方向，可以先独立运行板块研究系统。它默认使用 AKShare 东方财富行业/概念板块、板块历史行情、板块成分股和资金流数据，输出只写入 sector_research/，不会影响当前回测主数据。

```bash
python scripts/run_sector_research.py --start-date 20230101
```

主要输出：

- sector_research/data/raw/board_list.csv
- sector_research/data/raw/board_daily_raw.csv
- sector_research/data/raw/board_fund_flow_rank.csv
- sector_research/data/processed/theme_board_mapping.csv
- sector_research/data/processed/sector_board_daily.csv
- sector_research/data/processed/theme_strength_daily.csv
- sector_research/data/processed/theme_constituents_snapshot.csv
- sector_research/data/processed/stock_theme_exposure.csv
- sector_research/reports/theme_strength_report.md
- sector_research/reports/theme_strength_latest.xlsx
前端查看：

```bash
python -m uvicorn overnight_bt.app:app --host 127.0.0.1 --port 8083
```

启动后打开 `http://127.0.0.1:8083/sector`。页面只读取已经生成的 CSV/JSON，不会触发 AKShare 抓取，也不会触发 Tushare 指数更新。接口为 `GET /api/sector/overview?processed_dir=...&report_dir=...&market_context_path=...`，默认读取 `sector_research/data/processed`、`sector_research/reports` 和 `data_bundle/market_context.csv`。

页面数据来源：大盘环境来自已有 `data_bundle/market_context.csv`，主题排名来自 `theme_strength_daily.csv`，强势板块来自 `sector_board_daily.csv`，个股暴露来自 `stock_theme_exposure.csv`，主题映射来自 `theme_board_mapping.csv`，异常日志来自 `sector_research_errors.csv`。大盘环境面板只展示上证指数、沪深300、创业板指的收盘、日涨跌、5/20/60 日动量；不会写入板块研究目录，也不会和回测、模拟交易已有大盘字段产生重复。

如果要把板块研究字段接入回测，必须写入一个新的处理后目录，例如：

```bash
python scripts/build_sector_research_features.py \
  --processed-dir data_bundle/processed_qfq_theme_focus_top100 \
  --sector-processed-dir sector_research/data/processed \
  --output-dir data_bundle/processed_qfq_theme_focus_top100_sector
```

这样会复制原股票 CSV 并增加 `sector_strongest_theme_score`、`sector_strongest_theme_rank_pct`、`sector_exposure_score` 等字段，原 `data_bundle/processed_qfq_theme_focus_top100` 不会被覆盖。

如果要把“板块轮动诊断”的每日主线字段接入模拟账户，继续生成一个独立轮动增强目录：

```bash
python scripts/build_sector_rotation_features.py \
  --sector-processed-dir data_bundle/processed_qfq_theme_focus_top100_sector \
  --rotation-daily-path research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv \
  --output-dir data_bundle/processed_qfq_theme_focus_top100_sector_rotation \
  --overwrite
```

该目录的数据来源是 `data_bundle/processed_qfq_theme_focus_top100_sector` 与 `sector_rotation_daily.csv`，会给每只股票 CSV 增加 `rotation_state`、`rotation_top_theme`、`rotation_top_cluster`、`stock_matches_rotation_top_cluster` 等字段；`rotation_feature_manifest.csv` 只是生成清单，不会被当成股票日线读取。当前已经提供两个模拟账户模板：`configs/paper_accounts/sector_candidate_score04_rank07_v1.yaml` 对应“板块候选_score0.4_rank0.7”，`configs/paper_accounts/sector_rotation_avoid_new_energy_v1.yaml` 对应“候选_避开新能源主线”。更多运行方式见 `docs/paper-trading-system.md`。

组合回测页和每日收盘选股页提供三套策略预设：

| 预设 | 数据目录 | 用途 |
| --- | --- | --- |
| 基准动量 | `data_bundle/processed_qfq_theme_focus_top100` | 沿用原条件和评分表达式 |
| 板块过滤 | `data_bundle/processed_qfq_theme_focus_top100_sector` | 增加 `sector_exposure_score>0`、主题强度和排名过滤 |
| 板块过滤 + 评分加权 | `data_bundle/processed_qfq_theme_focus_top100_sector` | 在板块过滤基础上把主题强度、暴露分和主题排名纳入评分 |

选择板块增强预设时，后端会校验增强目录是否存在 `sector_feature_manifest.csv`，以及股票 CSV 是否包含 `sector_exposure_score`、`sector_strongest_theme_score`、`sector_strongest_theme_rank_pct`、`sector_strongest_theme_m20`。缺失时会直接报错，不会静默退回原数据。

可用于前端或研究脚本的条件示例：

```text
sector_strongest_theme_score>=0.65,sector_strongest_theme_rank_pct<=0.4,sector_exposure_score>0
```

### 7. 板块参数网格探索

板块增强目录生成后，可以用网格探索脚本批量比较“基准动量”“板块硬过滤”“只评分加权”三类参数。脚本只读取已经生成的数据目录，不重新抓取 AKShare 或 Tushare 数据。

```bash
python scripts/run_sector_parameter_grid.py \
  --start-date 20230101 \
  --score-thresholds 0.4,0.5,0.6 \
  --rank-pcts 0.3,0.5,0.7 \
  --score-weights 10,20,30
```

默认输入：

- 基准目录：`data_bundle/processed_qfq_theme_focus_top100`
- 板块增强目录：`data_bundle/processed_qfq_theme_focus_top100_sector`
- 买入基础条件：`m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02`
- 卖出条件：`m20<0.08,hs300_m20<0.02`

默认输出写入 `research_runs/YYYYMMDD_HHMMSS_sector_parameter_grid/`：

- `sector_parameter_grid_summary.csv`：每组参数的信号质量、账户收益、回撤、交易次数和综合排序分
- `sector_parameter_grid_trade_records.csv`：每组参数的账户买卖流水，含买入、卖出、价格、股数、手续费、金额和盈亏字段
- `sector_parameter_grid_config.json`：本次运行参数和展开后的全部策略条件
- `sector_parameter_grid_report.md`：中文总结报告和 Top 参数排序

字段与使用说明见 `docs/sector-parameter-grid-data-dictionary.md`，指标口径见 `docs/sector-research-indicator-documentation.md` 的 `grid_score` 章节。

### 8. 板块轮动诊断

如果要判断板块增强收益是否来自主题轮动，而不是少数个股或单段行情，可以在参数网格探索后运行轮动诊断脚本。脚本会读取主题强度日频数据和参数网格交易流水，输出每日主线状态、主题切换路径、交易轮动打标和分组收益。

```bash
python scripts/run_sector_rotation_diagnosis.py \
  --theme-strength-path sector_research/data/processed/theme_strength_daily.csv \
  --trade-records-path research_runs/20260501_142052_sector_parameter_grid/sector_parameter_grid_trade_records.csv \
  --sector-processed-dir data_bundle/processed_qfq_theme_focus_top100_sector \
  --cases 基准动量,硬过滤_score0.4_rank0.7
```

默认把主题分为三类：

- 科技成长：`AI`、`半导体芯片`、`存储芯片`、`机器人`
- 新能源：`光伏新能源`、`锂矿锂电`
- 医药防御：`医药`

默认输出写入 `research_runs/YYYYMMDD_HHMMSS_sector_rotation_diagnosis/`：

- `sector_rotation_daily.csv`：每日 Top1 主题、主题簇、持续天数和轮动状态
- `sector_rotation_labeled_trades.csv`：给每笔交易标记信号日主线主题、股票所属主题和是否匹配主线
- `sector_rotation_trade_summary.csv`：按轮动状态、Top1 主题、主题簇、股票主题统计收益
- `sector_rotation_report.md`：中文轮动诊断报告

字段说明见 `docs/sector-rotation-diagnosis-data-dictionary.md`。当前轮动状态只用于研究分组，不直接触发买卖。

### 9. 板块轮动状态条件网格

轮动诊断之后，可以继续运行轮动状态条件网格，验证“上一轮最佳板块候选 + 某类轮动状态”是否优于基准动量和原板块候选。

```bash
python scripts/run_sector_rotation_grid.py \
  --rotation-daily-path research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv \
  --start-date 20230101 \
  --end-date 20260429
```

默认比较：

- `基准动量`
- `板块候选_score0.4_rank0.7`
- `候选_新主线启动`
- `候选_主线退潮`
- `候选_轮动观察`
- `候选_退潮或观察`
- `候选_避开新主线启动`
- `候选_科技成长主线`
- `候选_科技成长且股票匹配`
- `候选_避开新能源主线`

默认输出写入 `research_runs/YYYYMMDD_HHMMSS_sector_rotation_grid/`：

- `sector_rotation_grid_summary.csv`
- `sector_rotation_grid_trade_records.csv`
- `sector_rotation_grid_config.json`
- `sector_rotation_grid_report.md`

字段说明见 `docs/sector-rotation-grid-data-dictionary.md`。该网格仍然是研究脚本，不会修改模拟账户。

### 10. 板块轮动后续验证

`docs/sector-rotation-grid-result-20260501.md` 建议继续做两类验证：一是把 `基准动量`、`板块候选_score0.4_rank0.7`、`候选_避开新能源主线` 做分年度和最近一年对比；二是把轮动状态从硬过滤改成评分加权。对应脚本为：

```bash
python scripts/run_sector_rotation_followup.py \
  --start-date 20230101 \
  --end-date 20260429 \
  --out-dir research_runs/20260504_130000_sector_rotation_followup
```

长实验可以分批续跑：

```bash
python scripts/run_sector_rotation_followup.py \
  --start-date 20230101 \
  --end-date 20260429 \
  --out-dir research_runs/20260504_130000_sector_rotation_followup \
  --resume \
  --max-weighted-runs 2
```

默认输入：

- 基准目录：`data_bundle/processed_qfq_theme_focus_top100`
- 板块增强目录：`data_bundle/processed_qfq_theme_focus_top100_sector`
- 轮动日频文件：`research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv`

默认输出写入 `research_runs/YYYYMMDD_HHMMSS_sector_rotation_followup/`：

- `sector_rotation_period_comparison.csv`：三条策略的全区间、分年度和最近一年账户/信号对比
- `sector_rotation_weighted_score_summary.csv`：轮动评分加权网格汇总
- `sector_rotation_weighted_score_trade_records.csv`：轮动评分加权实验逐笔交易流水
- `sector_rotation_followup_config.json`：本次运行参数和展开后的策略清单
- `sector_rotation_followup_report.md`：自动生成的中文总结报告

字段说明见 `docs/sector-rotation-followup-data-dictionary.md`。本次正式结果记录见 `docs/sector-rotation-followup-result-20260504.md`。关键结论是：三条策略收益明显集中在 2025；市场级轮动字段直接加到评分里不会改变日内 TopN，因为同一天所有候选股票获得的是同一个常数加减项。后续如果继续研究轮动加权，应优先使用 `stock_matches_rotation_top_cluster`、`stock_matches_rotation_top_theme` 这类股票差异化字段。

### 11. 板块效应选股条件探索

如果想回答“优先选择有板块效应的股票，到底是更适合做硬过滤，还是更适合只加权评分”，可以运行新的板块效应网格脚本。它复用现有的基准处理后目录和板块增强目录，不会重新抓取 AKShare 或 Tushare。

```bash
python scripts/run_sector_effect_grid.py \
  --start-date 20230101 \
  --end-date 20260429 \
  --out-dir research_runs/20260504_181000_sector_effect_grid_fixed \
  --score-thresholds 0.4,0.5 \
  --rank-pcts 0.7 \
  --exposure-mins 0 \
  --theme-m20-mins any,0 \
  --amount-ratio-mins any,1.0 \
  --score-weights 5,10,15 \
  --resume
```

默认比较三类策略：

- `baseline`：基准动量，不使用板块字段
- `hard_filter`：在买入条件里要求板块暴露和最强主题强度/排名/成交额满足阈值
- `score_weight`：买入条件不变，只把板块强度字段加到评分里

输出目录默认写入 `research_runs/YYYYMMDD_HHMMSS_sector_effect_grid/`，主要文件为：

- `sector_effect_grid_summary.csv`
- `sector_effect_grid_trade_records.csv`
- `sector_effect_grid_config.json`
- `sector_effect_grid_report.md`

字段定义见 `docs/sector-effect-grid-data-dictionary.md`，正式结果见 `docs/sector-effect-grid-result-20260504.md`。

### 12. 补充或重拉主题前 100 股票最新数据

如果 `data_bundle/processed_qfq_theme_focus_top100` 里的股票数据只到某个日期，例如 `20260417`，需要先补 Tushare 原始数据，再重建处理后目录。不要直接手工修改 `processed_qfq_theme_focus_top100`。

注意：`build_processed_data.py`、`build_theme_focus_universe.py`、`build_industry_strength.py` 都只是“重建已有数据”，不会主动拉取 Tushare 最新行情。如果原始目录 `raw_daily/` 和 `adj_factor/` 还停在旧日期，只运行这三个脚本不会得到最新数据。

当前 `scripts/sync_tushare_bundle.py` 是按 `start-date/end-date` 重新拉取并覆盖每只股票的原始 CSV，不是追加合并。因此不要把 `--start-date` 直接填成 `20260418` 做增量，否则历史数据会被截短。推荐用完整起点重新拉到目标结束日期：

```powershell
cd D:\量化\Momentum\T_0_system

python scripts\build_universe_snapshot.py `
  --env .env `
  --out data_bundle\universe_snapshot.csv `
  --as-of 20260427

python scripts\sync_tushare_bundle.py `
  --env .env `
  --bundle-dir data_bundle `
  --snapshot-csv data_bundle\universe_snapshot.csv `
  --start-date 20160101 `
  --end-date 20260427
```

腾讯云服务器上同样使用相对路径，先进入项目目录并激活虚拟环境：

```bash
cd /home/ubuntu/T_0_system
source /home/ubuntu/TencentCloud/myenv/bin/activate

python scripts/build_universe_snapshot.py --env .env --out data_bundle/universe_snapshot.csv --as-of 20260427
python scripts/sync_tushare_bundle.py --env .env --bundle-dir data_bundle --snapshot-csv data_bundle/universe_snapshot.csv --start-date 20160101 --end-date 20260427
```

然后重建全量处理后数据：

```powershell
python scripts\build_processed_data.py `
  --bundle-dir data_bundle `
  --output-dir data_bundle\processed_qfq
```

最后重建主题前 100 处理后目录：

```powershell
python scripts\build_theme_focus_universe.py `
  --snapshot-csv data_bundle\universe_snapshot.csv `
  --processed-dir data_bundle\processed_qfq `
  --out-snapshot data_bundle\universe_snapshot_theme_focus_top100.csv `
  --out-processed-dir data_bundle\processed_qfq_theme_focus_top100 `
  --top-k 100
```

如果你之前误把数据写到了错误目录，或目标目录里残留了旧股票文件，重建 top100 前应先确认并清理目标目录中的旧 CSV，只保留本次 `--top-k 100` 生成的 100 只股票。清理前务必确认目录就是 `data_bundle/processed_qfq_theme_focus_top100`。

然后重新生成行业强度指标：

```powershell
python scripts\build_industry_strength.py `
  --processed-dir data_bundle\processed_qfq_theme_focus_top100
```

执行后可以任选一个股票文件检查最后日期：

```powershell
Import-Csv data_bundle\processed_qfq_theme_focus_top100\000063.csv | Select-Object -Last 3 trade_date,name,raw_close,qfq_close,m5,m20
```

建议后续单独开发一个轻量更新脚本，例如 `scripts/update_top100_daily_data.py`，专门更新 `theme_focus_top100` 的最新交易日数据。这个脚本应只拉取最新交易日或缺失日期，并安全合并到 `raw_daily/`、`adj_factor/`、`stk_limit.csv`、`suspend_d.csv`、`market_context.csv`，再只重建主题前 100 对应的处理后 CSV。每日收盘选股页面负责读数据和出计划，不建议在页面里直接拉 Tushare 数据，以免交易计划和数据维护耦合。

### 8. 腾讯云每日自动更新主题前 100

腾讯云上已经提供自动化脚本：

```bash
/home/ubuntu/T_0_system/scripts/run_daily_top100_update.sh
```

脚本逻辑：

- 每天运行时先用 Tushare 交易日历判断当天是否为 A 股交易日。
- 如果不是交易日，直接跳过，不拉数、不重建。
- 如果是交易日，依次执行股票池快照、Tushare 原始数据同步、`processed_qfq` 重建、主题前 100 重建、行业强度重算和最终日期校验。
- 成功日志写入 `logs/top100_daily_update/YYYYMMDD.log`，最近一次成功状态写入 `logs/top100_daily_update/latest_success.txt`。

服务器 crontab 示例：

```cron
30 19 * * * /home/ubuntu/T_0_system/scripts/run_daily_top100_update.sh >> /home/ubuntu/T_0_system/logs/top100_daily_update/cron.log 2>&1
```

手动检查脚本和交易日判断：

```bash
cd /home/ubuntu/T_0_system
scripts/run_daily_top100_update.sh --check-only 20260427
```

查看最近一次是否成功：

```bash
cat /home/ubuntu/T_0_system/logs/top100_daily_update/latest_success.txt
tail -n 80 /home/ubuntu/T_0_system/logs/top100_daily_update/cron.log
```

## 启动方式

### 本地或临时前台启动

```bash
cd /home/ubuntu/T_0_system
source /home/ubuntu/TencentCloud/myenv/bin/activate
python -m uvicorn overnight_bt.app:app --host 0.0.0.0 --port 8083
```

本机开发时可以把目录换成本机项目目录，并打开 [http://127.0.0.1:8083](http://127.0.0.1:8083)。如果只是开发调试，可以临时加 `--reload`，这样 Python 代码变更后会自动重载；生产或腾讯云后台运行不建议使用 `--reload`。

### 腾讯云临时后台启动

如果暂时不配置系统服务，可以用 `nohup` 方式启动 8083 服务。它能在退出 SSH 后继续运行，但服务器重启或进程崩溃后不会自动拉起。

```bash
cd /home/ubuntu/T_0_system
mkdir -p logs/t0_server
source /home/ubuntu/TencentCloud/myenv/bin/activate
nohup python -m uvicorn overnight_bt.app:app --host 0.0.0.0 --port 8083 > logs/t0_server/server.log 2>&1 &
echo $! > logs/t0_server/server.pid
```

检查服务状态：

```bash
curl http://127.0.0.1:8083/health
cat logs/t0_server/server.pid
ss -ltnp | grep ':8083'
tail -n 80 logs/t0_server/server.log
```

停止或重启服务：

```bash
cd /home/ubuntu/T_0_system
kill $(cat logs/t0_server/server.pid)

source /home/ubuntu/TencentCloud/myenv/bin/activate
nohup python -m uvicorn overnight_bt.app:app --host 0.0.0.0 --port 8083 > logs/t0_server/server.log 2>&1 &
echo $! > logs/t0_server/server.pid
```

如果希望系统真正长期常驻，推荐改成 `systemd` 服务。当前腾讯云服务器已经按这种方式启用 `t0-system` 服务。`systemd` 可以开机自启，并在程序异常退出后自动重启：

```bash
sudo tee /etc/systemd/system/t0-system.service >/dev/null <<'EOF'
[Unit]
Description=T_0 System FastAPI
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/T_0_system
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/ubuntu/TencentCloud/myenv/bin/python -m uvicorn overnight_bt.app:app --host 0.0.0.0 --port 8083
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now t0-system
sudo systemctl status t0-system
```

常用维护命令：

```bash
sudo systemctl restart t0-system
sudo systemctl stop t0-system
sudo systemctl status t0-system
journalctl -u t0-system -n 100 --no-pager
```

### 修改代码后是否自动生效

不会。生产环境里已经运行的 `uvicorn` 进程会继续使用启动时加载的 Python 代码。修改后端代码、默认参数或依赖后，需要重启服务；如果使用 `systemd`，执行：

```bash
cd /home/ubuntu/T_0_system
git pull
sudo systemctl restart t0-system
curl http://127.0.0.1:8083/health
```

如果仍使用 `nohup`，则先 `kill $(cat logs/t0_server/server.pid)`，再重新执行后台启动命令。前端静态文件有时刷新浏览器即可看到变化，但如果改动涉及后端接口、默认值或 Python 逻辑，仍必须重启后端服务。

## 核心功能入口

### 前端页面

- 入口：`/`
- 页面布局：顶部紧凑输入区，`组合结果` 固定在结果区上方；明细结果放在页签中切换查看
- 回测模式：
- `信号质量回测`：默认模式，不使用初始资金、每笔目标资金和现金不足约束，但会按单股虚拟持仓去重，适合先判断条件本身是否有效
  - `实盘账户回测`：模拟现金、仓位、100 股整数倍和资金不足跳过，适合验证真实账户能否执行
- 主要输入项：
  - 处理后数据目录
  - 起止日期
  - `buy_condition`
  - `sell_condition`
  - `score_expression`
  - `top_n`；在信号质量模式下它也是 TopK 扫描上限，想比较 Top10 就填 10 或更高
  - `per_trade_budget`，仅实盘账户回测使用
  - `entry_offset`
  - `exit_offset`
  - `min_hold_days`
  - `max_hold_days`
  - `initial_cash`，仅实盘账户回测使用
  - `lot_size`，仅实盘账户回测使用
  - 买卖费率、印花税、滑点、最低佣金
  - 是否启用严格成交
  - 结束日处理方式：默认“截止日估值”，不使用结束日之后的数据；研究时可切换为“完整结算”
- 结果区怎么看：
  - 信号质量模式下，`组合结果` 看入选信号数、完成信号数、平均/中位单笔收益、胜率、收益因子、信号净值收益和回撤
  - 实盘账户模式下，`组合结果` 看最终权益、现金、持仓市值、收益、回撤、胜率、收益因子和交易成本
  - `组合结果` 下方的页签按钮用于切换 `条件诊断`、`排名质量`、`曲线与回撤`、`年度稳定性`、`退出原因`、`月度表现`、`期末持仓`、`选股与交易`、`个股贡献`
  - `排名质量` 先看 `累计TopK扫描`，比较 Top1、Top2、Top3、Top5、Top10 等口径的平均收益、中位收益、胜率、收益因子、回撤和辅助推荐分，用来判断实际买前几只更合适
  - `排名质量` 里的 `单名次质量` 看第 1 名到第 N 名各自的表现，用来判断评分表达式是否真的有排序能力
  - `期末持仓` 看截止日仍未卖出的股票市值、浮动盈亏和持有天数
  - `截止日卖出信号` 看结束日收盘触发但未使用未来开盘价成交的卖出提醒
  - 截止日当天仍会生成 `每日选股明细`，用于提示下一交易日候选买入股票；这些预测不会在本次回测内成交，也不会读取下一交易日开盘价
  - `条件诊断` 看信号覆盖、TopN 填满率、执行阻塞、交易质量和时间稳定性；这是判断买入条件是否可靠的主入口
  - `曲线与回撤` 在信号质量模式下看信号净值，在实盘账户模式下看账户权益；它只适合辅助判断，不应单独决定条件好坏
  - `年度稳定性` 和 `月度表现` 看条件是否只在少数年份或月份有效
  - `退出原因` 对比卖出条件触发和固定/最大持有退出的收益质量
  - `每日选股明细`、`交易流水`、`个股贡献汇总` 用于复核每笔信号、成交和个股盈亏来源
  - 首页明细区用页签切换模块，当前页签里的表格自然展开；需要查看更多记录时滚动页面，不再套一个额外的固定高度小窗口

### 单股页面

- 入口：`/single`
- 页面布局：与组合回测一致，上方为紧凑参数区，下方为摘要和页签内容
- 主要输入项：
  - 处理后数据目录，与组合回测和每日收盘选股共用同一份数据
  - 股票代码或股票名称
  - 起止日期
  - 买入条件、卖出条件
  - 买入确认天数、买入冷却天数、卖出确认天数
  - 执行时点
  - 初始资金、每笔目标资金、每手股数
  - 买卖费率、印花税
- 页面输出：
  - 单股回测摘要
  - 页签式结果区：指标解释表、K 线图与买卖点、股票交易日志、股票信号表
- 买入条件和卖出条件默认沿用组合回测当前推荐值，因为默认读取同一份处理后数据，`hs300_m20` 等大盘字段可直接共用

### 每日收盘选股页面

- 入口：`/daily`
- 用途：每天收盘采集完数据后，生成“明天准备买入的股票”和“当前持仓里明天需要卖出的股票”
- 主要输入项：
  - 处理后数据目录
  - 信号日期；留空时默认使用数据中的最新交易日
  - 买入条件、卖出条件、评分表达式
  - `TopN`
  - 买入偏移、最短持有天数、最大持有天数
  - 每笔目标资金、每手股数
  - 当前持仓，格式为每行 `股票代码,买入日期,买入价,股数,股票名称`
- 页面输出：
  - 页签式结果区：候选买入股票、卖出提醒、当前持仓诊断
  - 候选买入股票：按评分排序，显示股票代码、股票名称、评分、估算股数和明日开盘复核要求
  - 卖出提醒：根据当前持仓的浮盈、持仓以来最大收益和从高点回撤判断是否触发卖出条件
  - 当前持仓诊断：帮助复核每只持仓为什么继续观察或需要卖出
- 页面展示方式与组合回测保持一致：上方为紧凑参数区，下方为摘要和页签内容
- 注意：每日页面只使用信号日及历史数据，不使用明天开盘价；明天开盘若涨停、跌停、停牌或流动性不足，需要人工或交易程序复核后再执行

### 多账户模拟交易页面

- 入口：`/paper`
- 用途：把多套中文 YAML 模板当成多个独立模拟账户，每个账户独立生成待执行订单、模拟成交、记录持仓、计算盈亏和写入 Excel 账本
- 默认模板目录：`configs/paper_accounts/`
- 默认账本目录：`paper_trading/accounts/`
- 默认日志目录：`paper_trading/logs/`
- 主要输入项：
  - 模板目录
  - 模拟账户模板
  - 执行动作：`收盘生成待执行订单`、`开盘执行待成交订单`、`收盘更新持仓估值`
  - 动作日期；留空时会按数据最新交易日自动识别
- 页面按钮：
  - `获取当前持仓最新价格`：使用东方财富或腾讯股票最新行情刷新当前持仓、市值、浮动盈亏和每日资产，不生成订单、不执行买卖
- 页面输出：
  - 账户摘要
  - `待执行订单`
  - `成交流水`
  - `当前持仓`
  - `每日资产`
  - `运行日志`
- 当前本地测试默认用处理后日线的 `raw_open` 作为 T+1 开盘成交价；模板中已经预留 `行情源` 字段，后续可切换到东方财富或腾讯股票实时行情
- 买入候选支持按 T 日未复权收盘价过滤，例如在 YAML 中配置 `买入价格筛选.最高收盘价: 100` 后，超过 100 元的股票不会进入最终 TopN
- 买入股数支持最低买入金额下限：`买入数量.股数` 是基础股数，`买入数量.最低买入金额` 会按 T 日收盘价和 `每手股数` 向上补足，例如 25 元股票基础 200 股会补到 400 股以超过 10000 元
- 实时刷新在交易时段通常使用盘中最新价，收盘后通常使用当日收盘价或收盘后的最新可用价格，非交易日或节假日通常使用最近交易日收盘价或行情源最后可用价格；页面摘要和运行日志会写明行情状态
- 每个模板互不影响：不同模板写入不同 Excel 账本，适合同步观察 Top3、Top5、行业增强、大盘过滤等多套实盘模拟效果

命令行示例：

```bash
python scripts/run_paper_trading.py --config configs/paper_accounts/momentum_top5_v1.yaml --action generate --date 20260416
python scripts/run_paper_trading.py --config configs/paper_accounts/momentum_top5_v1.yaml --action execute --date 20260417
python scripts/run_paper_trading.py --config configs/paper_accounts/momentum_top5_v1.yaml --action mark --date 20260417
python scripts/run_paper_trading.py --config configs/paper_accounts/momentum_top5_v1.yaml --action refresh
```

运行全部模板：

```bash
python scripts/run_paper_trading.py --config-dir configs/paper_accounts --all --action generate --date 20260416
```

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

脚本会先判断当天是否为 A 股交易日；非交易日自动跳过。`execute` 用于开盘后执行所有账户已有的待成交订单，`after-close` 用于在数据更新完成后更新估值并生成下一交易日订单。

详细字段和账本解释见 `docs/paper-trading-system.md`。

### API

- `GET /health`
- `POST /api/run-signal-quality`
- `POST /api/run-backtest`
- `POST /api/run-backtest-export`
- `POST /api/daily-plan`
- `GET /api/paper/templates`
- `GET /api/paper/ledger`
- `POST /api/paper/run`
- `POST /api/run-single-stock`

`/api/run-backtest` 返回：

- `summary`
- `daily_rows`
- `pick_rows`
- `trade_rows`
- `contribution_rows`
- `condition_rows`
- `year_rows`
- `month_rows`
- `exit_reason_rows`
- `open_position_rows`
- `pending_sell_rows`
- `diagnostics`

`/api/run-signal-quality` 返回：

- `summary`
- `daily_rows`，信号净值曲线和每日完成信号统计
- `pick_rows`，每日入选信号，包含完成、买入阻塞、未完成和截止日估值状态
- `trade_rows`，已完成的独立信号样本
- `topk_rows`，累计 TopK 扫描结果，用于比较 Top1、Top2、Top3、Top5、Top10 等买入数量
- `rank_rows`，按评分排名分组的收益质量
- `contribution_rows`
- `condition_rows`
- `year_rows`
- `month_rows`
- `exit_reason_rows`
- `diagnostics`

说明：该接口不使用 `initial_cash`、`per_trade_budget`、`lot_size` 和账户现金占用；但同一股票在虚拟持仓或待买期间不会重复入选，避免连续加仓高估信号质量。

`/api/run-backtest-export` 返回 ZIP，包含：

- `汇总.csv`
- `每日资金曲线.csv`
- `每日选股明细.csv`
- `交易流水.csv`
- `个股贡献汇总.csv`
- `条件诊断.csv`
- `年度稳定性.csv`
- `月度表现.csv`
- `退出原因统计.csv`
- `期末持仓.csv`
- `截止日卖出提醒.csv`

说明：导出的 CSV 文件名和表头均为中文，便于直接用 Excel 打开核对。

`/api/daily-plan` 返回：

- `summary`
- `buy_rows`
- `sell_rows`
- `holding_rows`
- `diagnostics`

`/api/paper/run` 返回：

- `summary`
- `pending_order_rows`
- `trade_rows`
- `holding_rows`
- `asset_rows`
- `log_rows`
- `diagnostics`

`/api/paper/ledger` 是只读接口，用于前端打开 `/paper` 时直接读取已有 Excel 账本，不会生成新订单或执行成交。

`/api/run-single-stock` 返回：

- `stock_code`
- `stock_name`
- `summary`
- `metric_definitions`
- `trade_rows`
- `signal_rows`

## 回测逻辑

当前系统有两种回测口径。

### 信号质量回测

1. `T` 日收盘后扫描全部股票。
2. 用 `buy_condition` 过滤候选。
3. 用 `score_expression` 排序。
4. 取 `TopN` 作为入选信号；同时按累计 TopK 口径统计 Top1、Top2、Top3、Top5、Top10 等组合质量。
5. 每个入选信号默认在 `T+1` 日开盘虚拟买入。
6. 不检查账户现金、不按资金占用限制买入数量，但同一股票在虚拟持仓或待买期间会跳过后续重复信号。
7. 持有期间按 `sell_condition`、`min_hold_days` 和 `max_hold_days` 计算退出。
8. 默认“截止日估值”不读取结束日之后的数据；无法完成买卖的信号只展示为未完成或截止日估值，不进入已完成信号统计。
9. 输出重点是平均单笔收益、中位单笔收益、胜率、收益因子、累计 TopK 扫描、单名次排名质量和年度/月度稳定性。
10. `累计TopK扫描` 的辅助推荐分只用于排序提示，会轻微惩罚过大的 TopK，避免把“买几乎所有候选”误判成最佳；最终要结合样本数量、最差年份、最大回撤和实盘账户资金约束判断。

### 实盘账户回测

实盘账户回测使用以下口径：

1. `T` 日收盘后扫描全部股票。
2. 用 `buy_condition` 过滤候选。
3. 用 `score_expression` 排序。
4. 取 `TopN` 作为信号列表。
5. 对入选信号在 `T+1` 日开盘尝试买入。
6. 每笔按 `per_trade_budget` 计算可买手数，股数必须为 `lot_size` 的整数倍。
7. 如果未配置 `sell_condition`，默认在 `T+N` 日开盘卖出。
8. 如果配置了 `sell_condition`，系统会在每个收盘后判断是否触发；满足 `min_hold_days` 后若触发，则安排下一交易日开盘卖出。
9. 若设置了 `max_hold_days`，则达到最大持有天数后，不论卖出条件是否触发，都会在下一到期开盘强制退出。
10. 若严格成交模式下卖出日开盘跌停或停牌，则顺延到下一个可卖开盘。
11. 若严格成交模式下买入日开盘接近涨停、接近跌停或停牌，则该信号取消，不追买。

默认成交口径：

- 信号字段：`qfq_*`
- 买卖成交：`raw_open`
- 资金估值：持仓期间按 `raw_close` 逐日估值

## 研究脚本

### 1. 特征分层扫描

按 `T+1 open -> T+N open` 的标签看哪些日线特征更值得研究：

```bash
python scripts/run_overnight_feature_scan.py --processed-dir data_bundle/processed_qfq --start-date 20190101 --end-date 20251231 --exit-offset 2
```

主要参数：

- `--entry-offset`：默认 `1`
- `--exit-offset`：默认 `2`，支持 `2~5`
- `--per-trade-notional`：默认 `10000`

输出：

- `scan_overview.json`
- `feature_bucket_report.csv`
- `feature_scan_summary.md`

### 2. 训练期/验证期参数探索

```bash
python scripts/run_overnight_research.py --processed-dir data_bundle/processed_qfq --preset swing_v1 --exit-offsets 2,3,4,5
```

主要参数：

- `--preset`：默认 `swing_v1`
- `--entry-offset`：默认 `1`
- `--exit-offsets`：默认 `2,3,4,5`
- `--top-k`：训练期保留多少组进入验证
- `--per-trade-budget`：默认 `10000`

输出文件：

- `train_results.csv`
- `selected_train_cases.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `research_summary.json`
- `research_summary.md`
- `selected_case_trade_records.csv`

其中：

- `research_summary.md` 用于记录本次探索的条件与结果
- `selected_case_trade_records.csv` 用于记录验证期优先组合的逐笔买卖明细，包含日期、买卖动作、股票代码、股票名称、价格、数量、手续费、总金额、收益率与价差

### 3. 买入条件网格测试

如果你要系统化搜索更稳定的买入条件，可以运行：

```bash
python scripts/run_buy_condition_grid.py --processed-dir data_bundle/processed_qfq --grid-preset buy_condition_focus_grid_v1 --exit-offsets 4,5
```

如果你要围绕首轮胜出条件做第二轮更细的搜索，可以运行：

```bash
python scripts/run_buy_condition_grid.py --processed-dir data_bundle/processed_qfq --grid-preset buy_condition_focus_grid_v2 --exit-offsets 5
```

如果你要专门测试“每次只买 TopM 个”的影响，可以运行：

```bash
python scripts/run_buy_condition_grid.py --processed-dir data_bundle/processed_qfq --grid-preset buy_condition_topm_grid_v1 --exit-offsets 5
```

如果你要继续细化 `Top1` 或 `Top2` 下最合适的买入条件，可以运行：

```bash
python scripts/run_buy_condition_grid.py --processed-dir data_bundle/processed_qfq --grid-preset buy_condition_top1_focus_grid_v1 --exit-offsets 5
python scripts/run_buy_condition_grid.py --processed-dir data_bundle/processed_qfq --grid-preset buy_condition_top2_focus_grid_v1 --exit-offsets 5
```

### 4. 卖出指标网格测试

如果你要固定当前最优买入条件，转而探索不同卖出逻辑，可以运行：

```bash
python scripts/run_sell_condition_grid.py --processed-dir data_bundle/processed_qfq
```

如果你要测试更高级的退出逻辑，例如止损和浮盈回撤保护，可以运行：

```bash
python scripts/run_sell_condition_grid.py --sell-grid-preset sell_grid_advanced_v1 --processed-dir data_bundle/processed_qfq_theme_focus_top100 --top-n 5
```

如果你要围绕当前最佳的高级退出继续微调参数，可以运行：

```bash
python scripts/run_sell_condition_grid.py --sell-grid-preset sell_grid_advanced_v2_micro --processed-dir data_bundle/processed_qfq_theme_focus_top100 --top-n 5 --top-k 28
```

输出文件包括：

- `sell_grid_cases.json`
- `train_results.csv`
- `selected_train_cases.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `sell_grid_summary.json`
- `sell_grid_summary.md`
- `selected_case_trade_records.csv`

高级退出支持的动态字段包括：

- `holding_return`
- `best_return_since_entry`
- `drawdown_from_peak`
- `days_held`

### 5. 股票池与固定持有期对比

如果你要在固定 `Top1` 和固定买入条件下，比较不同股票池与 `T+4/T+5/T+6/T+7` 固定卖出的差异，可以运行：

```bash
python scripts/run_universe_hold_compare.py
```

默认会比较：

- 原始全量股票池
- 主题聚焦股票池
- 主题聚焦前100市值股票池

输出文件包括：

- `train_results.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `universe_hold_summary.json`
- `universe_hold_summary.md`
- `selected_case_trade_records.csv`

### 6. 主题前100池 TopN 与固定持有期对比

如果你要固定 `theme_focus_top100` 股票池，再比较 `Top1 / Top3 / Top5` 与 `T+4 / T+5 / T+6 / T+7` 的差异，可以运行：

```bash
python scripts/run_topn_hold_compare.py
```

输出文件包括：

- `train_results.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `topn_hold_summary.json`
- `topn_hold_summary.md`
- `selected_case_trade_records.csv`

### 7. 信号中位收益优化扫描

如果信号质量回测出现“平均收益为正、但中位单笔收益为负”，可以运行中位收益优化扫描，重点寻找让普通一笔更接近不亏的买入过滤、卖出条件和 TopK：

```bash
python scripts/run_signal_median_scan.py --processed-dir data_bundle/processed_qfq_theme_focus_top100 --start-date 20230101 --end-date 20251231
```

默认扫描：

- 基础买入条件：`m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1`
- 基础卖出条件：`m20<0.08,hs300_m20<0.02`
- TopK：`1,2,3,5,10,20`
- 买入过滤：短期动量为正、短期不过热、动量形态向上、大盘动量、K线质量、主板成熟股、行业强度等组合
- 卖出条件：当前卖出条件、十日转弱退出、五日转弱退出

如果已经运行 `scripts/build_industry_strength.py`，该扫描还会测试 `industry_rank_m20`、`industry_up_ratio`、`stock_vs_industry_m20` 等行业过滤组合，用来验证“强市场里的强行业里的强个股”是否更稳。

可选参数：

- `--pool-top-n`：每个信号日先取多少名候选进入复用池，默认 `20`
- `--top-k-values`：扫描哪些累计 TopK，默认 `1,2,3,5,10,20`
- `--min-completed`：推荐结果要求的最低完成信号数，默认 `200`
- `--sell-scope current`：只扫描当前卖出条件，适合快速验证买入过滤方向

输出目录默认在 `research_runs/YYYYMMDD_HHMMSS_signal_median_scan/`，包含：

- `中位收益优化结果.csv`：全部组合的中位收益、平均收益、胜率、收益因子、回撤和样本数
- `最佳组合信号明细.csv`：最佳组合下逐笔信号明细，包含买入日期、卖出日期、股票代码、股票名称、执行价、费用、收益率和关键指标
- `中位收益优化总结.md`：中文总结与前 20 名结果
- `扫描配置.json`：本次扫描参数

注意：该脚本仍是信号质量口径，不模拟账户现金和仓位金额占用，但会跳过同一股票持仓期内的重复信号。它适合先找到“普通信号更稳”的条件，再回到前端或账户回测验证可执行性。

## 单股回测使用说明

当前单股页面默认读取组合回测同一份处理后数据，因此大盘指标、行业强度指标和个股指标口径保持一致：

1. 打开 `http://127.0.0.1:8083/single`
2. 填入处理后数据目录，例如 `D:/量化/Momentum/T_0_system/data_bundle/processed_qfq_theme_focus_top100`
3. 填入股票代码或名称，例如 `000063` 或 `中兴通讯`
4. 填入买入条件、卖出条件和确认参数
5. 点击“运行单股回测”
6. 查看：
   - 回测摘要
   - 指标解释
   - K 线图上的买卖点
   - 交易日志
   - 每日信号表

说明：

- 鼠标移动到 K 线图任意一天，会显示这一天的开盘、收盘、最高、最低、成交量和买卖信号
- 交易日志会展示买卖后剩余现金、持仓股数、持仓市值、总资产和已实现盈亏

### 7. 当前推荐结果的前端复现

当前这条“主题前100池 + Top2 + 动量买入 + 大盘强度过滤 + 大盘卖出门槛”的推荐结果，已经设置为组合回测和每日收盘选股的默认值；单股表格回测页也默认使用同一组买入和卖出条件。也可以按下面参数复现：

- 处理后数据目录：`D:/量化/Momentum/T_0_system/data_bundle/processed_qfq_theme_focus_top100`
- 开始日期：`20230101`
- 结束日期：`20251231`
- 买入条件：`m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02`
- 卖出条件：`m20<0.08,hs300_m20<0.02`
- 评分表达式：`m20 * 140 + (m20 - m60 / 3) * 90 + (m20 - m120 / 6) * 40 - abs(m5 - 0.03) * 55 - abs(m10 - 0.08) * 30`
- `TopN`：`2`
- 买入偏移：`1`
- 固定卖出偏移：`5`
- 最短持有天数：`3`
- 最大持有天数：`15`
- 初始资金：`100000`
- 每笔目标资金：`10000`
- 每手股数：`100`
- 买卖费率：`0.00003`
- 印花税：`0`
- 滑点(bps)：`3`
- 最低佣金：`0`
- 严格成交：`是`

说明：

- 这组参数对应的中位收益优化结果见 `research_runs/20260427_171050_signal_median_scan_strict_all/`
- 大盘指标同时放在买入和卖出条件里：买入时要求沪深300二十日动量 `hs300_m20>0.02`，卖出时当个股 `m20<0.08` 且沪深300 `hs300_m20<0.02` 才触发退出，避免弱市买入、强市中过早下车。

当前脚本会输出两类核心结果：

- `sell_grid_summary.md`
  这次网格测试的总结书，包含测试范围、稳定性筛选口径、推荐条件和排行榜
- `selected_case_trade_records.csv`
  推荐组合的逐笔交易记录，包含买入、卖出、股票代码、股票名称、价格、数量、手续费、总金额、收益率和价差

完整输出通常包括：

- `sell_grid_cases.json`
- `train_results.csv`
- `selected_train_cases.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `sell_grid_summary.json`
- `sell_grid_summary.md`
- `selected_case_trade_records.csv`

## 复现结果

1. 准备好完整 `data_bundle/`
2. 确认其中包含 `processed_qfq/`
3. 启动服务
4. 打开前端并填写：
   - 处理后数据目录
   - 起止日期
   - `buy_condition`
   - 如有需要，填写 `sell_condition`
   - `score_expression`
   - `top_n`
   - `per_trade_budget`
   - `entry_offset=1`
   - `exit_offset`
   - 可选 `min_hold_days` / `max_hold_days`
   - 资金与交易成本参数
5. 点击“运行回测”
6. 查看：
   - 组合 summary
   - 资金曲线
   - 每日信号明细
   - 交易流水
   - 个股贡献
7. 如需归档，切换到实盘账户回测后点击“下载表格压缩包”

## 文档入口

- 数据文档：[backtest-data-dictionary.md](/D:/量化/Momentum/T_0_system/docs/backtest-data-dictionary.md)
- 指标文档：[indicator-reference.md](/D:/量化/Momentum/T_0_system/docs/indicator-reference.md)
- 表达式文档：[expression-reference.md](/D:/量化/Momentum/T_0_system/docs/expression-reference.md)
- 系统文档：[system-documentation.md](/D:/量化/Momentum/T_0_system/docs/system-documentation.md)
- 主题股票池文档：[theme-focus-universe-data-dictionary.md](/D:/量化/Momentum/T_0_system/docs/theme-focus-universe-data-dictionary.md)
- 板块研究使用说明：[sector-research-system-guide.md](/D:/量化/Momentum/T_0_system/docs/sector-research-system-guide.md)
- 板块研究数据文档：[sector-research-data-dictionary.md](/D:/量化/Momentum/T_0_system/docs/sector-research-data-dictionary.md)
- 板块研究指标文档：[sector-research-indicator-documentation.md](/D:/量化/Momentum/T_0_system/docs/sector-research-indicator-documentation.md)
- 板块轮动后续验证数据说明：[sector-rotation-followup-data-dictionary.md](/D:/量化/Momentum/T_0_system/docs/sector-rotation-followup-data-dictionary.md)
- 板块轮动后续验证结果：[sector-rotation-followup-result-20260504.md](/D:/量化/Momentum/T_0_system/docs/sector-rotation-followup-result-20260504.md)
- 板块效应选股条件数据说明：[sector-effect-grid-data-dictionary.md](/D:/量化/Momentum/T_0_system/docs/sector-effect-grid-data-dictionary.md)
- 板块效应选股条件结果：[sector-effect-grid-result-20260504.md](/D:/量化/Momentum/T_0_system/docs/sector-effect-grid-result-20260504.md)

## 交付前校验

```bash
python scripts/verify_delivery.py
python -m unittest discover -s tests -p "test_*.py" -v
```

如果本次改动涉及 API 或前端，交付前还应做一次本地启动冒烟验证。当前项目推荐最少执行：

```bash
python -m unittest tests.test_backtest tests.test_api_integration tests.test_feature_scan tests.test_research tests.test_processing -v
python -m uvicorn overnight_bt.app:app --host 127.0.0.1 --port 8083
```
