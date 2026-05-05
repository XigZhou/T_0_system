# T 日信号摆动回测系统使用文档

本文档说明系统各功能模块的用途、输入参数、输出结果与异常处理方式。当前系统的默认回测口径为：`T` 日生成信号，`T+1` 日开盘买入，卖出按固定偏移、最大持有天数或卖出条件触发；默认结束日采用截止日估值，不使用结束日之后的数据。

## 1. 固定股票池构建模块

### 功能

- 根据指定日期生成固定快照股票池
- 默认筛选总市值不低于 500 亿且名称不含 `ST`

### 入口

```bash
python scripts/build_universe_snapshot.py --as-of 目标交易日
```

### 输入参数

| 参数 | 说明 |
| --- | --- |
| `--as-of` | 快照日期，格式 `YYYYMMDD` |
| `TUSHARE_TOKEN` | 本机环境变量中的 Tushare token |

### 输出结果

- `data_bundle/universe_snapshot.csv`

### 异常处理

- 若 `TUSHARE_TOKEN` 缺失，脚本会报认证相关异常
- 若指定日期不是交易日，会对齐到最近开市日

## 2. Tushare 数据同步模块

### 功能

- 下载原始日线、复权因子、交易日历、涨跌停、停牌与指数上下文

### 入口

```bash
python scripts/sync_tushare_bundle.py --start-date 20160101 --end-date 目标交易日
```

### 输入参数

| 参数 | 说明 |
| --- | --- |
| `--start-date` | 开始日期 |
| `--end-date` | 结束日期 |
| `--bundle-dir` | 输出目录，默认 `data_bundle/` |

### 输出结果

- `data_bundle/raw_daily/*.csv`
- `data_bundle/adj_factor/*.csv`
- `data_bundle/trade_calendar.csv`
- `data_bundle/stk_limit.csv`
- `data_bundle/suspend_d.csv`
- `data_bundle/market_context.csv`

### 异常处理

- 接口权限不足时会抛出 Tushare 访问错误
- 某些接口区间拉取过大时，脚本使用逐股票汇总方式减少截断风险
- 当前同步脚本会覆盖目标股票的原始日线和复权因子 CSV，不是追加合并；如果只把 `--start-date` 填成最新缺失日期，会导致历史数据被截短

## 3. 处理后回测输入生成模块

### 功能

- 生成 `processed_qfq/*.csv`
- 构造信号字段、参考标签和开盘成交约束字段

### 入口

```bash
python scripts/build_processed_data.py
```

### 输入参数

| 参数 | 说明 |
| --- | --- |
| `--bundle-dir` | 数据包目录 |
| `--output-dir` | 输出目录，默认 `data_bundle/processed_qfq` |
| `--snapshot-csv` | 自定义股票池快照路径，可选 |

### 输出结果

- `data_bundle/processed_qfq/<symbol>.csv`
- `data_bundle/processed_qfq/processing_manifest.csv`

### 关键输出字段

- 信号价格：`open/high/low/close`
- 成交价格：`raw_open/raw_close`
- 开盘约束：`can_buy_open_t`、`can_sell_t`
- 参考标签：`next_open`、`next_raw_open`、`r_on`、`r_on_raw`

### 异常处理

- 缺少原始日线或复权因子文件时，会在 `processing_manifest.csv` 中记录 `missing_input`
- 必备字段缺失或日期不升序时，会抛出 `ValueError`

### 行业强度指标增强

当前系统在 2000 积分权限下，不依赖申万行业指数日线，而是用处理后股票日线里的 `industry` 字段自行聚合行业强度。生成或重建处理后目录后，可以运行：

```bash
python scripts/build_industry_strength.py --processed-dir data_bundle/processed_qfq_theme_focus_top100
```

主要输入参数：

| 参数 | 说明 |
| --- | --- |
| `--processed-dir` | 要增强的处理后股票 CSV 目录 |
| `--output-dir` | 可选；填写后写到新目录，不填写则覆盖原目录 |
| `--report-dir` | 可选；生成报告目录，默认写入 `research_runs` |
| `--amount-window` | 行业成交额均值窗口，默认 `20` |
| `--amount-min-periods` | 行业成交额均值最少样本，默认 `5` |

输出结果：

- 每只股票 CSV 新增 `industry_m20`、`industry_m60`、`industry_rank_m20`、`industry_rank_m60`、`industry_up_ratio`、`industry_strong_ratio`、`industry_amount_ratio`、`stock_vs_industry_m20` 等字段
- `research_runs/YYYYMMDD_HHMMSS_industry_strength/industry_strength_summary.md`
- `industry_strength_manifest.csv`
- `industry_strength_config.json`

使用方式：

```text
industry_rank_m20<0.3,industry_m20>0,industry_up_ratio>0.5,stock_vs_industry_m20>0
```

注意：

- `industry_rank_m20` 越小代表行业越强，`0` 表示当日最强行业
- 这些字段只使用当日及历史数据，不使用未来数据
- 行业样本很少时指标会更噪，建议搭配 `industry_stock_count>=3` 或 `industry_valid_m20_count>=3` 做过滤

### 独立板块研究系统

该模块用于研究锂矿锂电、光伏新能源、半导体芯片、存储芯片、AI、机器人、医药等主题方向。它默认使用 AKShare 东方财富行业/概念板块数据，输出只写入 sector_research/，不会覆盖当前回测主目录。

入口：

`ash
python scripts/run_sector_research.py --start-date 20230101
`

主要输入参数：

| 参数 | 说明 |
| --- | --- |
| --config | 主题与子赛道关键词配置，默认 sector_research/configs/themes.yaml |
| --start-date | 板块历史行情起始日期，格式 YYYYMMDD |
| --end-date | 板块历史行情结束日期，留空使用本机当天日期 |
| --raw-dir | 原始标准化数据目录，默认 sector_research/data/raw |
| --processed-dir | 指标数据目录，默认 sector_research/data/processed |
| --report-dir | 报告目录，默认 sector_research/reports |
| --skip-constituents | 跳过成分股抓取，用于快速调试 |

如需把板块研究结果接入现有回测，使用下面脚本生成新的处理后股票 CSV 目录：

`ash
python scripts/build_sector_research_features.py \
  --processed-dir data_bundle/processed_qfq_theme_focus_top100 \
  --sector-processed-dir sector_research/data/processed \
  --output-dir data_bundle/processed_qfq_theme_focus_top100_sector
`

合并后会新增 sector_theme_names、sector_exposure_score、sector_strongest_theme_score、sector_strongest_theme_rank_pct、sector_strongest_theme_m20 等字段。--output-dir 必须不同于 --processed-dir，脚本会拒绝覆盖原目录。
前端工作台：

启动 FastAPI 后打开 `/sector`。该页面是只读看板，不会连接 AKShare，也不会写入 `sector_research/` 或 `data_bundle/`。页面输入参数如下：

| 参数 | 说明 |
| --- | --- |
| 板块指标目录 | 对应 API 参数 `processed_dir`，默认 `sector_research/data/processed` |
| 报告目录 | 对应 API 参数 `report_dir`，默认 `sector_research/reports` |
| 大盘环境文件 | 对应 API 参数 `market_context_path`，默认 `data_bundle/market_context.csv`；前端不提供输入框，默认使用现有大盘数据 |

页面与 API：

| 入口 | 用途 |
| --- | --- |
| `/sector` | 板块研究前端工作台 |
| `GET /api/sector/overview?processed_dir=...&report_dir=...&market_context_path=...` | 读取大盘环境、主题排名、强势板块、个股暴露、主题映射和异常日志 |

输出定义：

| 页签 | 数据来源 | 主要字段 |
| --- | --- | --- |
| 大盘环境 | `data_bundle/market_context.csv` | 上证指数、沪深300、创业板指的 `close`、`pct_chg`、`m5`、`m20`、`m60` |
| 主题排名 | `theme_strength_daily.csv` | `theme_name`、`theme_score`、`volume_price_score`、`reversal_score`、`m5`、`m20`、`strongest_board` |
| 强势板块 | `sector_board_daily.csv` | `board_name`、`board_type`、`theme_board_score`、`m20`、`amount_ratio_20`、资金流字段 |
| 个股暴露 | `stock_theme_exposure.csv` | `stock_code`、`stock_name`、`theme_names`、`board_names`、`exposure_score` |
| 主题映射 | `theme_board_mapping.csv` | `theme_name`、`subtheme_name`、`matched_keyword`、`board_name` |
| 异常日志 | `sector_research_errors.csv` | `stage`、`board_type`、`board_name`、`error` |

大盘环境不会与回测系统已有大盘字段冲突：它读取同一个 `data_bundle/market_context.csv`，只在 `/sector` 看板上展示，不写入 `sector_research/`，也不改变模拟交易和回测的买卖条件。接口会选取不晚于板块最新交易日的最近一条大盘记录，避免使用未来数据。

异常处理：缺少 CSV 时页面显示“暂无数据”并在异常日志页签提示缺失路径；如果传入的目录不在项目根目录内，API 返回 400，避免误读服务器其他目录。

### 板块增强口径接入回测与每日选股

组合回测页 `/` 和每日收盘选股页 `/daily` 都支持“策略预设”：

| 预设 | 处理后数据目录 | 买入条件和评分变化 |
| --- | --- | --- |
| 基准动量 | `data_bundle/processed_qfq_theme_focus_top100` | 沿用原动量、大盘过滤和评分表达式 |
| 板块过滤 | `data_bundle/processed_qfq_theme_focus_top100_sector` | 增加 `sector_exposure_score>0`、`sector_strongest_theme_score>=0.6`、`sector_strongest_theme_rank_pct<=0.5` |
| 板块过滤 + 评分加权 | `data_bundle/processed_qfq_theme_focus_top100_sector` | 在板块过滤基础上，把 `sector_strongest_theme_score`、`sector_exposure_score`、`sector_strongest_theme_rank_pct` 纳入评分 |

当请求的 `data_profile` 为 `sector`，或买入条件/卖出条件/评分表达式中出现 `sector_*` 字段时，后端会按板块增强口径校验数据。校验内容包括：

- 目录下必须存在 `sector_feature_manifest.csv`
- 股票 CSV 必须包含 `sector_exposure_score`、`sector_strongest_theme_score`、`sector_strongest_theme_rank_pct`、`sector_strongest_theme_m20`
- `sector_feature_manifest.csv` 只作为校验清单，不会被误当成股票日线读入

这些字段只来自 `scripts/build_sector_research_features.py` 生成的增强目录，不会覆盖原始主题前 100 处理后目录。

异常处理：

- AKShare 接口不可用或网络失败时，相关阶段错误会写入 sector_research_errors.csv；如果完全无法获取板块列表或历史行情，脚本会直接失败。
- 板块资金流抓取失败不影响历史行情和主题强度计算。
- 成分股快照来自最新板块成分，不是历史成分，长区间回测需要说明可能存在成分股幸存者偏差。
- 当前系统是 T 日收盘信号、T+1 开盘买入，因此 T 日板块强度可以作为 T 日收盘信号字段；若改成盘前信号，需要整体滞后一日。

完整操作流程见 docs/sector-research-system-guide.md，详细字段与指标说明见 docs/sector-research-data-dictionary.md 和 docs/sector-research-indicator-documentation.md。

### 板块参数网格探索

用途：把板块增强参数作为研究变量，统一比较基准动量、板块硬过滤和只评分加权三类策略，帮助决定是否把某组板块条件接入回测系统或模拟账户。

运行命令：

```bash
python scripts/run_sector_parameter_grid.py \
  --start-date 20230101 \
  --score-thresholds 0.4,0.5,0.6 \
  --rank-pcts 0.3,0.5,0.7 \
  --score-weights 10,20,30
```

主要输入参数：

| 参数 | 说明 |
| --- | --- |
| `--base-processed-dir` | 基准处理后股票目录，默认 `data_bundle/processed_qfq_theme_focus_top100` |
| `--sector-processed-dir` | 板块增强股票目录，默认 `data_bundle/processed_qfq_theme_focus_top100_sector` |
| `--score-thresholds` | `hard_filter` 家族使用的 `sector_strongest_theme_score` 阈值列表 |
| `--rank-pcts` | `hard_filter` 家族使用的 `sector_strongest_theme_rank_pct` 阈值列表，越小代表主题越强 |
| `--score-weights` | `score_only` 家族把板块强度加入评分表达式的权重列表 |
| `--skip-trade-records` | 只导出汇总和报告，不导出逐笔交易流水；正式交付建议不要开启 |

输出结果：

| 文件 | 说明 |
| --- | --- |
| `research_runs/*_sector_parameter_grid/sector_parameter_grid_summary.csv` | 每组参数的信号质量、账户收益、回撤、交易次数、胜率和综合排序分 |
| `research_runs/*_sector_parameter_grid/sector_parameter_grid_trade_records.csv` | 每组参数的账户交易流水，含买入、卖出、股票、价格、股数、费用、金额和盈亏 |
| `research_runs/*_sector_parameter_grid/sector_parameter_grid_config.json` | 本次 CLI 参数和展开后的全部策略条件 |
| `research_runs/*_sector_parameter_grid/sector_parameter_grid_report.md` | 中文总结报告、Top 参数、基准对照和风险提示 |

异常处理：脚本会先校验板块增强目录的 `sector_feature_manifest.csv` 和必要 `sector_*` 字段；缺失时直接失败，不会静默退回基准目录。字段定义见 `docs/sector-parameter-grid-data-dictionary.md`。

### 板块效应选股条件探索

用途：在已经确认板块增强目录可用之后，进一步验证“优先选择有板块效应的股票”是否有效。它和板块轮动不同，不使用市场级主线状态，而是在个股层面比较三种方式：不使用板块字段、把板块字段作为买入硬过滤、把板块字段作为评分加权。

运行命令：

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

主要输入参数：

| 参数 | 说明 |
| --- | --- |
| `--base-processed-dir` | 基准处理后目录，默认 `data_bundle/processed_qfq_theme_focus_top100` |
| `--sector-processed-dir` | 板块增强目录，默认 `data_bundle/processed_qfq_theme_focus_top100_sector` |
| `--score-thresholds` | 硬过滤使用的最强主题强度阈值列表 |
| `--rank-pcts` | 硬过滤使用的主题排名百分位阈值，越小越强 |
| `--exposure-mins` | 个股主题暴露分阈值 |
| `--theme-m20-mins` | 最强主题 20 日动量阈值，`any` 表示不启用该过滤 |
| `--amount-ratio-mins` | 最强主题成交额放大倍数阈值，`any` 表示不启用该过滤 |
| `--score-weights` | 评分加权家族使用的板块权重 |
| `--resume` | 读取已有汇总和交易流水，跳过已完成 `case` |

输出结果：

| 文件 | 说明 |
| --- | --- |
| `sector_effect_grid_summary.csv` | 每组策略的信号质量、账户收益、回撤、交易次数和综合排序 |
| `sector_effect_grid_trade_records.csv` | 每组策略的逐笔账户流水；统一列集合后写出，便于 Excel 或 pandas 复核 |
| `sector_effect_grid_config.json` | 本次运行参数和展开后的策略组合 |
| `sector_effect_grid_report.md` | 自动生成的中文 Top 结果和基准对照 |

异常处理：脚本会校验板块增强目录的 manifest 和必要 `sector_*` 字段；旧交易流水如果存在列不一致导致无法续跑，会提示更换输出目录或删除旧文件。字段定义见 `docs/sector-effect-grid-data-dictionary.md`，结果记录见 `docs/sector-effect-grid-result-20260504.md`。

### 板块轮动诊断

用途：判断主题板块之间是否存在轮动，并把候选策略的每笔交易标记到对应轮动状态下，避免只看静态板块强度阈值。

运行命令：

```bash
python scripts/run_sector_rotation_diagnosis.py \
  --theme-strength-path sector_research/data/processed/theme_strength_daily.csv \
  --trade-records-path research_runs/20260501_142052_sector_parameter_grid/sector_parameter_grid_trade_records.csv \
  --sector-processed-dir data_bundle/processed_qfq_theme_focus_top100_sector \
  --cases 基准动量,硬过滤_score0.4_rank0.7
```

主要输入参数：

| 参数 | 说明 |
| --- | --- |
| `--theme-strength-path` | 主题强度日频文件，默认来自独立板块研究系统 |
| `--trade-records-path` | 参数网格探索生成的交易流水 |
| `--sector-processed-dir` | 板块增强股票目录，用于给交易股票补充信号日最强主题 |
| `--cases` | 要比较的策略名称，默认比较 `基准动量` 和 `硬过滤_score0.4_rank0.7` |
| `--strong-rank-pct` | 强主题排名百分位阈值，默认 `0.33` |
| `--fresh-days` | 新主线启动的连续天数上限，默认 `5` |

输出结果：

| 文件 | 说明 |
| --- | --- |
| `sector_rotation_daily.csv` | 每日 Top1 主题、主题簇、领先幅度、持续天数和轮动状态 |
| `sector_rotation_theme_runs.csv` | 每段连续 Top1 主题的开始、结束、持续天数和分数变化 |
| `sector_rotation_transitions.csv` | Top1 主题切换路径和次数 |
| `sector_rotation_labeled_trades.csv` | 每笔交易的信号日轮动状态、股票所属主题和是否匹配主线 |
| `sector_rotation_trade_summary.csv` | 按轮动状态、Top1 主题、主题簇和股票主题聚合的收益统计 |
| `sector_rotation_report.md` | 中文诊断报告 |

异常处理：主题强度文件缺少必要字段时直接报错；某只交易股票找不到板块增强 CSV 时，该笔交易的股票主题字段为空，但不影响轮动状态打标。字段定义见 `docs/sector-rotation-diagnosis-data-dictionary.md`。

### 板块轮动状态条件网格

用途：把轮动诊断结果作为买入条件变量，验证“上一轮最佳板块候选 + 轮动状态/主题簇过滤”是否优于基准动量和原板块候选。

运行命令：

```bash
python scripts/run_sector_rotation_grid.py \
  --rotation-daily-path research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv \
  --start-date 20230101 \
  --end-date 20260429
```

主要输入参数：

| 参数 | 说明 |
| --- | --- |
| `--base-processed-dir` | 基准处理后股票目录 |
| `--sector-processed-dir` | 板块增强股票目录 |
| `--rotation-daily-path` | 轮动诊断生成的 `sector_rotation_daily.csv` |
| `--start-date`、`--end-date` | 回测信号日期区间 |
| `--skip-trade-records` | 是否跳过逐笔交易流水导出 |

默认探索组合包括：

| 策略 | 说明 |
| --- | --- |
| `基准动量` | 不使用板块或轮动字段 |
| `板块候选_score0.4_rank0.7` | 上一步板块参数网格的最佳候选 |
| `候选_新主线启动` | 只在新主线启动状态买入 |
| `候选_主线退潮` | 只在主线退潮状态买入 |
| `候选_轮动观察` | 只在轮动观察状态买入 |
| `候选_退潮或观察` | 主线退潮或轮动观察 |
| `候选_避开新主线启动` | 排除新主线启动 |
| `候选_科技成长主线` | 只在科技成长成为 Top1 主题簇时买入 |
| `候选_科技成长且股票匹配` | 科技成长主线且股票所属主题簇也匹配 |
| `候选_避开新能源主线` | 排除新能源 Top1 主线 |

输出结果：

| 文件 | 说明 |
| --- | --- |
| `sector_rotation_grid_summary.csv` | 每组轮动条件的信号质量、账户收益、回撤和交易次数 |
| `sector_rotation_grid_trade_records.csv` | 每组轮动条件的交易流水 |
| `sector_rotation_grid_config.json` | 本次运行参数和展开后的策略条件 |
| `sector_rotation_grid_report.md` | 中文总结报告 |

异常处理：轮动日频文件缺失必要字段、板块增强目录缺失 manifest 或必要 `sector_*` 字段时直接报错。字段定义见 `docs/sector-rotation-grid-data-dictionary.md`。

### 股票匹配主线轮动 TopN 网格

用途：验证轮动是否能真正配合 TopN 排序。上一轮后续验证已经说明，市场级轮动字段在同一天对所有候选股票相同，直接加到评分里不会改变 TopN。本模块改用股票差异化字段：`stock_matches_rotation_top_cluster` 和 `stock_matches_rotation_top_theme`。

运行命令：

```bash
python scripts/run_sector_rotation_match_grid.py \
  --start-date 20230101 \
  --end-date 20260429 \
  --out-dir research_runs/20260504_191500_sector_rotation_match_grid \
  --cluster-weights 5,10 \
  --theme-weights 8,12 \
  --penalty-weights 5,8
```

主要输入参数：

| 参数 | 说明 |
| --- | --- |
| `--base-processed-dir` | 基准处理后目录，默认 `data_bundle/processed_qfq_theme_focus_top100` |
| `--sector-processed-dir` | 板块增强目录，默认 `data_bundle/processed_qfq_theme_focus_top100_sector` |
| `--rotation-daily-path` | 轮动诊断日频文件 |
| `--cluster-weights` | 股票匹配当日 Top1 主题簇时的评分加权列表 |
| `--theme-weights` | 股票匹配当日 Top1 主题时的评分加权列表 |
| `--penalty-weights` | 新主线启动时，不匹配主线簇股票的扣分列表 |

输出结果：

| 文件 | 说明 |
| --- | --- |
| `sector_rotation_match_grid_summary.csv` | 策略收益、回撤、信号质量和与原板块候选的 TopN 重合率 |
| `sector_rotation_match_grid_trade_records.csv` | 每组策略逐笔账户流水 |
| `sector_rotation_match_grid_pick_records.csv` | 每组策略 TopN 入选股票，额外补充轮动匹配字段 |
| `sector_rotation_match_grid_config.json` | CLI 参数和展开后的策略组合 |
| `sector_rotation_match_grid_report.md` | 自动生成的中文摘要 |

异常处理：板块增强字段或轮动日频字段缺失时直接报错；入选记录补充轮动匹配字段只发生在脚本输出中，不修改回测引擎和输入数据目录。字段定义见 `docs/sector-rotation-match-grid-data-dictionary.md`。

### 板块轮动匹配稳定性验证

用途：验证 `主线簇匹配加权_w5` 是否在分年度、最近一年和滚动窗口中稳定，避免只根据全区间收益决定是否接入模拟账户。

运行命令：

```bash
python scripts/run_sector_rotation_match_stability.py \
  --start-date 20160101 \
  --end-date 20260429 \
  --out-dir research_runs/20260505_120000_sector_rotation_match_stability
```

主要输入参数：

| 参数 | 说明 |
| --- | --- |
| `--base-processed-dir` | 基准处理后股票目录，默认 `data_bundle/processed_qfq_theme_focus_top100` |
| `--sector-processed-dir` | 板块增强股票目录，默认 `data_bundle/processed_qfq_theme_focus_top100_sector` |
| `--rotation-daily-path` | 轮动诊断生成的 `sector_rotation_daily.csv` |
| `--start-date`、`--end-date` | 用户希望检查的总区间；脚本会根据字段覆盖率自动确定板块/轮动公平可比区间 |
| `--rolling-months` | 滚动窗口月份列表，默认 `6,12` |
| `--min-coverage` | 板块和轮动字段进入可比区间的最低覆盖率，默认 `0.95` |
| `--resume` | 同一输出目录已有结果时跳过已完成的 `period_label + case` |
| `--fill-missing-trade-records` | 配合 `--resume` 使用，只补齐已有汇总中缺失的交易流水 |

输出结果：

| 文件 | 说明 |
| --- | --- |
| `sector_rotation_match_stability_summary.csv` | 每个区间、每条策略的收益、回撤、信号质量和交易次数 |
| `sector_rotation_match_stability_by_case.csv` | 每条策略的正收益区间占比、跑赢板块候选次数和跑赢基准次数 |
| `sector_rotation_match_stability_coverage.csv` | 2016-2026 年板块强度和轮动字段覆盖率 |
| `sector_rotation_match_stability_trade_records.csv` | 全部区间策略组合的逐笔账户流水 |
| `sector_rotation_match_stability_config.json` | CLI 参数、区间清单和策略清单 |
| `sector_rotation_match_stability_report.md` | 自动生成的中文报告 |

使用注意：当前可比区间从 `20230403` 开始，因为 2016-2022 缺少板块强度和轮动状态字段。脚本会把 2016-2022 单独作为 `基准历史参考_2016-2022`，只运行 `基准动量`。字段定义见 `docs/sector-rotation-match-stability-data-dictionary.md`，结果记录见 `docs/sector-rotation-match-stability-result-20260505.md`。

### 板块轮动后续验证

用途：落实 `docs/sector-rotation-grid-result-20260501.md` 的下一步建议，对 `基准动量`、`板块候选_score0.4_rank0.7`、`候选_避开新能源主线` 做全区间、分年度和最近一年对比，同时验证“轮动状态不硬过滤，改成评分加权”的效果。

运行命令：

```bash
python scripts/run_sector_rotation_followup.py \
  --start-date 20230101 \
  --end-date 20260429 \
  --out-dir research_runs/20260504_130000_sector_rotation_followup
```

长实验支持续跑和分批：

```bash
python scripts/run_sector_rotation_followup.py \
  --start-date 20230101 \
  --end-date 20260429 \
  --out-dir research_runs/20260504_130000_sector_rotation_followup \
  --resume \
  --max-weighted-runs 2
```

主要输入参数：

| 参数 | 说明 |
| --- | --- |
| `--base-processed-dir` | 基准处理后股票目录，默认 `data_bundle/processed_qfq_theme_focus_top100` |
| `--sector-processed-dir` | 板块增强股票目录，默认 `data_bundle/processed_qfq_theme_focus_top100_sector` |
| `--rotation-daily-path` | 轮动诊断生成的 `sector_rotation_daily.csv` |
| `--start-date`、`--end-date` | 回测信号日期区间 |
| `--tech-bonuses` | `rotation_top_cluster_tech` 的评分加分权重列表，默认 `0,2,4` |
| `--new-energy-penalties` | `rotation_top_cluster_new_energy` 的评分扣分权重列表，默认 `0,2,4` |
| `--new-start-penalties` | `rotation_is_new_start` 的评分扣分权重列表，默认 `0,2,4` |
| `--resume` | 读取已有输出，跳过已经完成的周期和加权组合 |
| `--max-weighted-runs` | 单次最多新增运行的加权组合数量，`0` 表示不限制 |

输出结果：

| 文件 | 说明 |
| --- | --- |
| `sector_rotation_period_comparison.csv` | 三条策略的全区间、分年度和最近一年对比，含账户收益、回撤、买入次数、胜率和信号中位收益 |
| `sector_rotation_weighted_score_summary.csv` | 轮动评分加权网格汇总，含权重、账户收益、信号质量、`grid_score` 和风险提示 |
| `sector_rotation_weighted_score_trade_records.csv` | 加权网格逐笔交易流水，含策略名、买卖日期、股票、价格、股数、费用、金额和盈亏 |
| `sector_rotation_followup_config.json` | 本次 CLI 参数、周期定义、对比策略和加权策略清单 |
| `sector_rotation_followup_report.md` | 自动生成的中文总结报告 |

异常处理：脚本会先加载基准目录、板块增强目录和轮动日频文件；如果板块增强目录缺少 `sector_feature_manifest.csv` 或必要 `sector_*` 字段，会直接失败。续跑时如果输出目录已有部分 CSV，脚本会按 `period_label + case` 和 `case` 跳过已完成组合，交易流水采用追加写入，避免长实验一次性占用过多内存。

字段定义见 `docs/sector-rotation-followup-data-dictionary.md`。当前正式结果见 `docs/sector-rotation-followup-result-20260504.md`。结论是三条策略收益明显集中在 2025，2023 和 2026YTD 偏弱；市场级轮动字段直接加到评分里不会改变日内 TopN，因为同一天所有候选股票获得的是同一个常数加减项。后续继续研究轮动加权时，应改用 `stock_matches_rotation_top_cluster`、`stock_matches_rotation_top_theme` 或二者与 `rotation_is_new_start` 的交互项这类股票差异化字段。

### 板块增强结果接入模拟账户

用途：把已经确认的板块参数候选接入 `/paper` 多账户模拟系统，使用 T 日收盘信号生成 T+1 待执行订单。当前新增两个模板：

| 账户 | 模板 | 处理后数据目录 | 买入条件差异 |
| --- | --- | --- | --- |
| 板块候选_score04_rank07_v1 | `configs/paper_accounts/sector_candidate_score04_rank07_v1.yaml` | `data_bundle/processed_qfq_theme_focus_top100_sector` | 基础动量 + `sector_exposure_score>0` + `sector_strongest_theme_score>=0.4` + `sector_strongest_theme_rank_pct<=0.7` |
| 板块轮动_避开新能源_v1 | `configs/paper_accounts/sector_rotation_avoid_new_energy_v1.yaml` | `data_bundle/processed_qfq_theme_focus_top100_sector_rotation` | 在上一个账户基础上增加 `rotation_top_cluster!=新能源` |

策略 2 的数据目录需要先由下面命令生成：

```bash
python scripts/build_sector_rotation_features.py \
  --sector-processed-dir data_bundle/processed_qfq_theme_focus_top100_sector \
  --rotation-daily-path research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv \
  --output-dir data_bundle/processed_qfq_theme_focus_top100_sector_rotation \
  --overwrite
```

输入来源：`sector_processed_dir` 是已经合并板块研究字段的股票日线目录，`rotation_daily_path` 是轮动诊断脚本输出的每日主线表。输出结果：每只股票 CSV 追加 `rotation_state`、`rotation_top_theme`、`rotation_top_cluster`、`stock_theme_cluster`、`stock_matches_rotation_top_cluster` 等字段，同时生成 `rotation_feature_manifest.csv` 和 `rotation_feature_metadata.json` 记录源路径、生成时间、股票数量和轮动字段清单。异常处理：输出目录不能等于源目录；不加 `--overwrite` 时目录已存在会拒绝覆盖；模拟交易加载目录时会跳过 `rotation_feature_manifest.csv`，避免把元数据误当股票日线。

手动生成计划示例：

```bash
python scripts/run_paper_trading.py --config configs/paper_accounts/sector_candidate_score04_rank07_v1.yaml --action generate --date 20260430
python scripts/run_paper_trading.py --config configs/paper_accounts/sector_rotation_avoid_new_energy_v1.yaml --action generate --date 20260430
```

### 日常补充主题前 100 最新数据

如果 `data_bundle/processed_qfq_theme_focus_top100` 中的股票数据只到旧日期，例如 `20260417`，不要直接手工修改处理后 CSV。正确流程是先补原始数据，再重建处理后目录。

注意：`build_processed_data.py`、`build_theme_focus_universe.py`、`build_industry_strength.py` 都只是基于已有文件重建数据，不会主动连接 Tushare 拉取最新行情。如果 `raw_daily/`、`adj_factor/`、`trade_calendar.csv` 和 `market_context.csv` 仍停在旧日期，只运行这三个脚本不会更新到最新交易日。

1. 更新股票池快照，并重新同步原始数据到目标结束日期。

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

腾讯云服务器示例：

```bash
cd /home/ubuntu/T_0_system
source /home/ubuntu/TencentCloud/myenv/bin/activate

python scripts/build_universe_snapshot.py --env .env --out data_bundle/universe_snapshot.csv --as-of 20260427
python scripts/sync_tushare_bundle.py --env .env --bundle-dir data_bundle --snapshot-csv data_bundle/universe_snapshot.csv --start-date 20160101 --end-date 20260427
```

2. 重建全量处理后数据。

```powershell
python scripts\build_processed_data.py `
  --bundle-dir data_bundle `
  --output-dir data_bundle\processed_qfq
```

3. 重建主题前 100 处理后目录。

```powershell
python scripts\build_theme_focus_universe.py `
  --snapshot-csv data_bundle\universe_snapshot.csv `
  --processed-dir data_bundle\processed_qfq `
  --out-snapshot data_bundle\universe_snapshot_theme_focus_top100.csv `
  --out-processed-dir data_bundle\processed_qfq_theme_focus_top100 `
  --top-k 100
```

如果目标目录之前残留了旧股票 CSV，重建前应先确认并清理 `data_bundle/processed_qfq_theme_focus_top100` 里的旧 CSV，避免目录里混入不属于本次 Top100 的股票。清理前必须确认目标目录路径无误。

4. 重新生成行业强度指标。

```powershell
python scripts\build_industry_strength.py `
  --processed-dir data_bundle\processed_qfq_theme_focus_top100
```

5. 检查某只股票最后日期和行业字段。

```powershell
Import-Csv data_bundle\processed_qfq_theme_focus_top100\000063.csv |
  Select-Object -Last 3 trade_date,name,raw_close,qfq_close,m5,m20,industry_m20,industry_rank_m20
```

说明：

- `--end-date` 应填写你希望补到的目标交易日；如果当天不是交易日，最终数据以 Tushare 交易日历和接口返回为准。
- 当前脚本不是增量更新工具，不建议使用 `--start-date 20260418` 这类缺失起点直接补数据。
- 如果只是为了每日收盘选股，后续建议研发轻量增量更新脚本，避免每天全量重拉。

### 轻量增量更新模块建议

建议后续新增独立脚本，例如 `scripts/update_top100_daily_data.py`，专门服务每日收盘选股。它不应放进前端页面里自动执行，而应作为数据维护步骤独立运行。

建议能力：

- 自动读取 `data_bundle/processed_qfq_theme_focus_top100` 的最后交易日，计算缺失交易日。
- 只针对 `data_bundle/universe_snapshot_theme_focus_top100.csv` 中的股票拉取 `daily`、`adj_factor`、`stk_limit`、`suspend_d`。
- 同步更新指数上下文和交易日历。
- 与现有 `raw_daily/`、`adj_factor/`、`stk_limit.csv`、`suspend_d.csv` 安全去重合并。
- 只重建 `processed_qfq_theme_focus_top100` 目录，避免重建全量股票池。
- 更新完成后输出本次新增日期、成功股票数、失败股票数和失败原因。

这样每日使用流程会变成：

```text
轻量补最新数据 -> 打开 /daily -> 生成明日买入候选和卖出提醒
```

### 腾讯云每日自动更新任务

腾讯云服务器上可以使用下面脚本在每天收盘后自动更新主题前 100 数据：

```bash
/home/ubuntu/T_0_system/scripts/run_daily_top100_update.sh
```

脚本执行逻辑：

- 先读取 `.env` 中的 `TUSHARE_TOKEN`，调用 Tushare 交易日历判断当天是否为 A 股交易日。
- 非交易日只写日志并跳过。
- 交易日会执行：更新 `universe_snapshot.csv`、同步 Tushare 原始数据、重建 `processed_qfq`、清理并重建 `processed_qfq_theme_focus_top100`、重算行业强度、校验 100 个股票文件是否都更新到目标日期。
- 使用锁目录 `/tmp/t0_top100_daily_update.lock` 避免重复运行。
- 日志目录为 `logs/top100_daily_update/`。

推荐 crontab：

```cron
30 19 * * * /home/ubuntu/T_0_system/scripts/run_daily_top100_update.sh >> /home/ubuntu/T_0_system/logs/top100_daily_update/cron.log 2>&1
```

手动检查：

```bash
cd /home/ubuntu/T_0_system
scripts/run_daily_top100_update.sh --check-only 20260427
cat logs/top100_daily_update/latest_success.txt
```

## 4. 腾讯云前端服务运行与代码更新

### 功能

- 启动前端和 FastAPI 后端服务
- 保证退出 SSH 后系统仍可访问
- 说明代码更新后如何让线上服务加载新代码

### 当前访问入口

- 腾讯云访问地址：`http://124.223.140.163:8083/`
- 本机健康检查：`http://127.0.0.1:8083/health`

### 临时前台启动

适合排查问题或开发调试，关闭 SSH 终端后程序会停止：

```bash
cd /home/ubuntu/T_0_system
source /home/ubuntu/TencentCloud/myenv/bin/activate
python -m uvicorn overnight_bt.app:app --host 0.0.0.0 --port 8083
```

开发调试时可以临时加 `--reload`，代码变更后会自动重载；生产后台运行不建议使用 `--reload`。

### nohup 后台启动

当前服务器可以用 `nohup` 让系统在退出 SSH 后继续运行：

```bash
cd /home/ubuntu/T_0_system
mkdir -p logs/t0_server
source /home/ubuntu/TencentCloud/myenv/bin/activate
nohup python -m uvicorn overnight_bt.app:app --host 0.0.0.0 --port 8083 > logs/t0_server/server.log 2>&1 &
echo $! > logs/t0_server/server.pid
```

检查方式：

```bash
curl http://127.0.0.1:8083/health
cat logs/t0_server/server.pid
ss -ltnp | grep ':8083'
tail -n 80 logs/t0_server/server.log
```

停止或重启：

```bash
cd /home/ubuntu/T_0_system
kill $(cat logs/t0_server/server.pid)

source /home/ubuntu/TencentCloud/myenv/bin/activate
nohup python -m uvicorn overnight_bt.app:app --host 0.0.0.0 --port 8083 > logs/t0_server/server.log 2>&1 &
echo $! > logs/t0_server/server.pid
```

### 推荐的长期常驻方式

`nohup` 能解决“退出 SSH 后继续运行”，但不能解决“服务器重启后自动启动”和“进程异常退出后自动拉起”。如果希望 T_0 系统一直跑在后台，推荐使用 `systemd`：

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

常用命令：

```bash
sudo systemctl restart t0-system
sudo systemctl stop t0-system
sudo systemctl status t0-system
journalctl -u t0-system -n 100 --no-pager
```

### 修改代码后是否会自动更新

不会。后台运行的 Python 进程会继续使用启动时加载的代码。修改后端代码、默认参数、表达式解析、回测逻辑或依赖后，都需要重启服务才能生效。

推荐更新流程：

```bash
cd /home/ubuntu/T_0_system
git pull
sudo systemctl restart t0-system
curl http://127.0.0.1:8083/health
```

如果仍使用 `nohup`，则先停止旧进程，再重新执行后台启动命令。前端静态文件修改后，浏览器刷新通常能看到变化；但如果修改涉及后端接口、默认值或 Python 逻辑，仍必须重启后端服务。

## 5. 主题聚焦股票池构建模块

### 功能

- 在现有快照股票池基础上，二次筛选出 AI、机器人、新能源、有色金属、电网等方向
- 生成对应的处理后数据子目录，方便直接做缩池回测

### 入口

```bash
python scripts/build_theme_focus_universe.py
python scripts/build_theme_focus_universe.py --top-k 100 --out-snapshot data_bundle/universe_snapshot_theme_focus_top100.csv --out-processed-dir data_bundle/processed_qfq_theme_focus_top100
```

### 输入参数

| 参数 | 说明 |
| --- | --- |
| `--snapshot-csv` | 原始快照股票池路径 |
| `--processed-dir` | 原始处理后数据目录 |
| `--out-snapshot` | 输出主题池快照路径 |
| `--out-processed-dir` | 输出主题池处理后数据目录 |
| `--top-k` | 可选市值截断；`0` 表示不截断 |

### 输出结果

- `universe_snapshot_theme_focus.csv`
- `processed_qfq_theme_focus/`
- 或者你指定的 `top-k` 版本输出

### 异常处理

- 输入快照不存在时抛出文件读取异常
- 个别股票若缺少处理后文件，则不会复制进目标目录

## 6. 股票池与固定持有期对比模块

### 功能

- 固定当前最优 `Top1` 买入条件
- 在多个股票池上比较不同固定持有天数
- 输出验证期稳定性排序和逐笔交易记录

### 入口

```bash
python scripts/run_universe_hold_compare.py
```

### 默认比较范围

- 股票池：
  - 全量原始池
  - `theme_focus`
  - `theme_focus_top100`
- 固定卖出：
  - `T+4`
  - `T+5`
  - `T+6`
  - `T+7`

### 输出结果

- `train_results.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `universe_hold_summary.json`
- `universe_hold_summary.md`
- `selected_case_trade_records.csv`

### 异常处理

- 股票池目录不存在时抛出 `FileNotFoundError`
- 输出目录不可写时抛出文件系统异常

## 7. 主题前100池 TopN 与固定持有期对比模块

### 功能

- 固定 `theme_focus_top100`
- 比较 `Top1 / Top3 / Top5`
- 比较 `T+4 / T+5 / T+6 / T+7`
- 输出验证期稳定性排序和逐笔交易记录

### 入口

```bash
python scripts/run_topn_hold_compare.py
```

### 输出结果

- `train_results.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `topn_hold_summary.json`
- `topn_hold_summary.md`
- `selected_case_trade_records.csv`

### 异常处理

- 处理后目录不存在时抛出 `FileNotFoundError`
- 输出目录不可写时抛出文件系统异常

## 8. 回测引擎模块

### 功能

- 根据 `T` 日信号生成待执行订单
- 在 `T+1` 日开盘尝试买入
- 在 `T+N` 日开盘尝试卖出
- 支持严格成交模式、滑点、手续费、无最低佣金
- 严格成交模式下，买入会同时规避开盘接近涨停和接近跌停的股票

### 主要入口

- Python 调用：`overnight_bt.backtest.run_portfolio_backtest`
- API：`POST /api/run-backtest`

### 核心输入参数

| 参数 | 说明 |
| --- | --- |
| `processed_dir` | 处理后数据目录 |
| `start_date/end_date` | 信号日期范围 |
| `buy_condition` | 信号筛选表达式 |
| `sell_condition` | 可选卖出表达式，收盘后判断、次日开盘执行 |
| `score_expression` | 排名打分表达式 |
| `top_n` | 每个信号日最多保留的候选数 |
| `initial_cash` | 初始资金 |
| `per_trade_budget` | 每笔目标资金 |
| `lot_size` | 股数步长，默认 100 |
| `entry_offset` | 买入偏移，当前默认 1 |
| `exit_offset` | 固定退出偏移，未启用卖出条件时按该值退出 |
| `min_hold_days` | 卖出条件开始生效前的最短持有天数 |
| `max_hold_days` | 最大持有天数；大于 0 时作为强制退出上限 |
| `buy_fee_rate/sell_fee_rate` | 买卖手续费率 |
| `stamp_tax_sell` | 卖出税费 |
| `slippage_bps` | 滑点 |
| `realistic_execution` | 是否启用严格成交 |
| `min_commission` | 最低佣金 |
| `settlement_mode` | 结束日处理方式；默认 `cutoff` 表示截止日估值，不使用结束日之后的数据；`complete` 表示继续完整结算已有订单和持仓 |

### 输出结果

| 字段 | 说明 |
| --- | --- |
| `summary` | 汇总指标，如收益率、回撤、买卖次数、阻塞次数 |
| `daily_rows` | 每日现金、持仓市值、权益、候选数、买卖数 |
| `pick_rows` | 每个信号日入选股票及计划买卖日期 |
| `trade_rows` | 逐笔买卖与阻塞明细 |
| `contribution_rows` | 个股贡献汇总 |
| `condition_rows` | 买入条件诊断指标与判读说明 |
| `year_rows` | 年度收益、回撤、交易次数和胜率 |
| `month_rows` | 月度收益、回撤、交易次数和胜率 |
| `exit_reason_rows` | 按退出原因分组的交易质量 |
| `open_position_rows` | 截止日仍持有股票的市值、浮动盈亏、持有天数和计划退出状态 |
| `pending_sell_rows` | 截止日收盘触发卖出条件、但未用未来开盘价成交的卖出提醒 |
| `diagnostics` | 文件数量、信号日数量、候选日数量等诊断信息 |

### 结束日口径

- 默认 `settlement_mode=cutoff`：回测只运行到 `end_date` 对应的最后一个交易日，不再买入结束日当天或结束日之后才会成交的订单。
- 截止日仍持有的股票按截止日未复权收盘价计入 `ending_market_value` 和 `ending_equity`。
- 截止日当天仍会按买入条件和评分表达式生成 `pick_rows`，用于提示下一交易日候选买入股票；这些记录只做预测展示，不创建本次回测内的买入成交。
- 如果截止日收盘触发卖出条件，系统只写入 `pending_sell_rows`，提醒下一交易日开盘复核卖出，不会读取结束日之后的开盘价。
- 若研究时需要把区间内产生的订单和持仓全部卖完，可在前端选择“完整结算”，或在 API 中传 `settlement_mode=complete`。

### 异常处理

- `processed_dir` 不存在时抛出 `FileNotFoundError`
- `exit_offset <= entry_offset` 时抛出 `ValueError`
- 表达式非法时抛出 `ValueError` 或表达式解析错误

### 信号质量回测接口

信号质量回测用于先判断“买入条件、卖出条件、评分表达式本身是否有效”。它不模拟账户现金和仓位金额占用，但会按单股虚拟持仓去重，避免同一股票持仓期内连续重复买入。

- Python 调用：`overnight_bt.signal_quality.run_signal_quality`
- API：`POST /api/run-signal-quality`

核心口径：

- 每个信号日仍按 `buy_condition` 过滤，并用 `score_expression` 排序取 `TopN`。
- `TopN` 在信号质量模式下也是 TopK 扫描上限；例如想比较 Top1、Top2、Top3、Top5、Top10，就把 `TopN` 填到 10 或更高。
- 每个入选信号默认 `T+1` 开盘虚拟买入。
- 不使用 `initial_cash`、`per_trade_budget`、`lot_size`、账户现金和资金不足跳过。
- 同一股票从入选后到虚拟卖出前视为已有持仓或待买订单，后续信号日即使仍满足买入条件，也会被跳过，统计在 `blocked_reentry_count`。
- 持有期间仍按 `sell_condition`、`min_hold_days`、`max_hold_days` 和严格成交口径计算退出。
- 默认 `settlement_mode=cutoff` 不读取结束日之后的数据；无法完成买卖的信号展示为未完成或截止日估值，不进入已完成信号统计。

返回字段：

| 字段 | 说明 |
| --- | --- |
| `summary` | 入选信号数、完成信号数、平均/中位单笔收益、胜率、收益因子、信号净值收益、回撤、持仓期跳过信号数 |
| `daily_rows` | 信号净值曲线、每日候选数、入选数、完成信号数、持仓期跳过信号数和平均收益 |
| `pick_rows` | 每日入选信号，包含完成、买入阻塞、未完成和截止日估值状态 |
| `trade_rows` | 已完成的独立信号样本 |
| `topk_rows` | 累计 TopK 扫描结果，比较 Top1、Top2、Top3、Top5、Top10 等买入数量的收益、胜率、收益因子、回撤和辅助推荐分；辅助推荐分会轻微惩罚过大的 TopK，避免把“买几乎所有候选”误判成最佳 |
| `rank_rows` | 按评分排名分组的平均收益、中位收益、胜率和分位数收益 |
| `contribution_rows` | 个股在信号样本中的贡献 |
| `condition_rows` | 信号质量诊断和判读说明 |
| `year_rows/month_rows` | 年度、月度信号净值和信号收益稳定性 |
| `exit_reason_rows` | 卖出条件触发与固定/最大持有退出的信号质量对比 |
| `diagnostics` | 文件数量、信号日数量、候选日数量、完成信号数量、持仓期跳过信号数量 |

## 9. 前端页面模块

### 功能

- 提供表单化回测入口
- 展示组合结果摘要、条件诊断、排名质量、曲线与回撤、年度稳定性、月度表现、退出原因、信号明细、交易流水、个股贡献
- 页面采用“顶部紧凑输入、下方结果”的布局，不再使用左输入右输出的双栏结构
- `组合结果` 摘要固定展示在明细区上方；摘要下方用页签按钮切换条件诊断、排名质量、曲线与回撤、年度稳定性、退出原因、月度表现、期末持仓、选股与交易、个股贡献
- 页面顶部提供 `信号质量回测` 和 `实盘账户回测` 两种模式；默认使用信号质量回测

### 入口

```text
http://127.0.0.1:8083/
```

### 页面输入项

- 处理后数据目录
- 回测模式：`信号质量回测` 或 `实盘账户回测`
- 开始日期、结束日期
- 买入条件
- 卖出条件
- 评分表达式
- `TopN`；在信号质量模式下代表 TopK 扫描上限，想比较 Top10 就填 10 或更高
- 初始资金，仅实盘账户回测使用
- 每笔目标资金，仅实盘账户回测使用
- 买入偏移、卖出偏移
- 最短持有天数、最大持有天数
- 每手股数，仅实盘账户回测使用
- 买卖费率、印花税、滑点、最低佣金
- 是否严格成交
- 结束日处理方式，默认“截止日估值”，适合不想使用未来数据的实盘式回测

### 输出结果

- 组合结果摘要
- 摘要下方的页签按钮用于切换不同明细模块，点击哪个按钮，下方就只显示对应内容
- 条件诊断：信号覆盖、TopN 填满率、交易质量、执行摩擦、时间稳定性，并在页面给出判读说明
- 排名质量：先展示累计 TopK 扫描，比较 Top1、Top2、Top3、Top5、Top10 等口径的平均收益、中位收益、胜率、收益因子、回撤和辅助推荐分，用来判断买前几只更合适
- 单名次质量：按评分排名展示第 1 名到第 N 名各自的平均收益、中位收益、胜率和分位数收益，用来判断评分表达式是否有排序能力
- 曲线与回撤：信号质量模式下看信号净值，实盘账户模式下看账户权益，用于辅助观察收益路径和中途承压
- 年度稳定性：每年收益、回撤、交易次数、胜率
- 月度表现：每月收益、回撤、交易次数、胜率
- 退出原因：卖出条件触发与固定/最大持有退出的交易质量对比
- 期末持仓：显示截止日未平仓股票的市值、浮动盈亏、持有天数和计划退出状态
- 截止日卖出信号：显示结束日收盘触发但未使用未来开盘价成交的卖出提醒
- 每日信号明细
- 交易流水
- 个股贡献汇总
- 首页明细区用页签切换模块，当前页签里的表格自然展开；需要查看更多记录时滚动页面，不再套一个额外的固定高度小窗口

### 异常处理

- 请求失败时页面状态栏会显示错误信息
- 参数缺失或数据目录错误时，API 会返回 4xx/5xx

## 10. 每日收盘选股模块

### 功能

- 用当天收盘后的处理后数据生成明日候选买入名单
- 根据用户输入的当前持仓判断哪些股票触发卖出条件
- 不使用明天开盘价，所有买卖都以“明日开盘复核后执行”的方式提示
- 页面展示方式与组合回测一致：上方是紧凑参数区，下方先展示摘要，再用页签切换“明日买入、卖出提醒、持仓诊断”

### 入口

- 页面：`/daily`
- API：`POST /api/daily-plan`

### 主要输入参数

| 参数 | 说明 |
| --- | --- |
| `processed_dir` | 处理后数据目录 |
| `signal_date` | 信号日期；留空时使用数据中最新交易日；若输入非交易日，使用此前最近交易日 |
| `buy_condition` | 买入筛选条件 |
| `sell_condition` | 当前持仓卖出条件 |
| `score_expression` | 买入候选排序表达式 |
| `top_n` | 明日候选买入数量 |
| `entry_offset` | 买入偏移，页面用于说明计划买入日 |
| `min_hold_days` | 卖出条件开始生效前的最短持有天数 |
| `max_hold_days` | 达到后提示卖出的最大持有天数；`0` 表示不按最大持有天数提示 |
| `per_trade_budget` | 每只候选股票的目标买入金额 |
| `lot_size` | 每手股数，默认 100 |
| `holdings` | 当前持仓列表；前端输入格式为每行 `股票代码,买入日期,买入价,股数,股票名称` |

### 输出结果

| 字段 | 说明 |
| --- | --- |
| `summary` | 信号日期、计划买入日、买入候选数量、卖出提醒数量 |
| `buy_rows` | 明日候选买入股票，包含排名、评分、股票名称、估算股数和开盘复核说明 |
| `sell_rows` | 当前持仓中触发卖出条件或达到最大持有天数的股票 |
| `holding_rows` | 所有输入持仓的浮盈、最大浮盈、从高点回撤和判断说明 |
| `diagnostics` | 数据文件数量、实际使用信号日期、可用股票数量 |

### 使用方式

1. 每天收盘后先更新 Tushare 数据并重建处理后数据。
2. 打开 `/daily`，信号日期可留空，系统会使用最新交易日。
3. 输入或粘贴当前持仓。
4. 点击“生成明日计划”。
5. 第二天开盘前或开盘时复核涨停、跌停、停牌、流动性和账户资金后再执行。

### 异常处理

- 持仓格式不正确时，前端会提示具体行号。
- 股票代码不在处理后目录中时，会在持仓诊断中显示“未找到股票数据”。
- 信号日期没有可用交易日时，API 返回 `ValueError`。

## 11. 多账户模拟交易模块

### 功能

- 使用中文 YAML 模板定义模拟账户，每个模板对应一套独立买入条件、卖出条件、评分表达式、买入股数、费用和账本路径。
- 收盘后根据模板生成 T+1 待执行订单，开盘时按配置行情源模拟成交。
- 当前持仓或已有待买订单的股票不会重复生成买入订单。
- 买入、卖出、持仓、现金、浮动盈亏、实现盈亏和每日资产都写入 Excel 账本。
- 新系统独立于原有组合回测、信号质量回测、单股回测和每日收盘选股；它只复用条件解析、每日计划和处理后行情读取能力，不改变旧系统结果。

### 入口

- 页面：`/paper`
- 模板目录：`configs/paper_accounts/`
- 默认模板：`configs/paper_accounts/momentum_top5_v1.yaml`
- 账本目录：`paper_trading/accounts/`
- 日志目录：`paper_trading/logs/`
- API：`GET /api/paper/templates`
- API：`GET /api/paper/ledger`
- API：`POST /api/paper/run`
- 命令行：`python scripts/run_paper_trading.py --config configs/paper_accounts/momentum_top5_v1.yaml --action generate --date 20260416`
- 定时任务脚本：`scripts/run_paper_trading_cron.sh`

### 中文 YAML 模板字段

| 字段 | 说明 |
| --- | --- |
| `账户编号` | 模拟账户唯一编号，也用于默认账本文件名 |
| `账户名称` | 页面和账本里展示的账户名称 |
| `初始资金` | 模拟账户初始现金 |
| `处理后数据目录` | 每只股票一个 CSV 的处理后数据目录 |
| `买入条件` | 收盘后筛选明日买入候选的表达式 |
| `卖出条件` | 收盘后判断当前持仓是否需要卖出的表达式 |
| `评分表达式` | 对买入候选排序的表达式 |
| `买入排名数量` | 每天最多生成多少只候选买入订单 |
| `买入偏移` | 默认 `1`，表示 T 日信号、T+1 执行 |
| `最短持有天数` | 持仓达到该天数后卖出条件才生效 |
| `最大持有天数` | 达到后可触发卖出提醒 |
| `买入数量.方式` | 当前支持 `固定股数` |
| `买入数量.股数` | 每只股票基础买入股数，例如 `200` |
| `买入数量.每手股数` | 股数向上取整单位，A 股通常填 `100` |
| `买入数量.最低买入金额` | 用 T 日收盘价估算的最低买入市值；不足时按整手向上补足股数，`0` 表示不用金额下限 |
| `买入价格筛选.最低收盘价` | 可选，用 T 日未复权收盘价过滤过低价格股票，`0` 表示不限制 |
| `买入价格筛选.最高收盘价` | 可选，用 T 日未复权收盘价过滤过高价格股票，`0` 表示不限制 |
| `行情源.首选` | 本地测试默认 `本地日线`；后续可切换东方财富或腾讯股票 |
| `行情源.备用` | 首选行情源失败后的备用来源 |
| `行情源.价格字段` | `开盘价` 或 `收盘价` |
| `交易规则.持仓时不重复买入` | 已持仓股票再次入选时是否跳过 |
| `交易规则.有待成交订单时不重复买入` | 已有待买订单时是否跳过重复信号 |
| `交易规则.严格成交` | 是否检查涨跌停、停牌等成交约束字段 |
| `费用.买卖费率` | 买卖默认佣金费率；也可分别配置买入费率和卖出费率 |
| `费用.印花税` | 卖出印花税 |
| `费用.滑点bps` | 成交滑点，买入加价、卖出减价 |
| `费用.最低佣金` | 单笔最低佣金 |
| `输出.账本路径` | Excel 账本路径 |
| `输出.日志目录` | 文本日志目录 |

### 执行动作

| 动作 | 说明 |
| --- | --- |
| `generate` | 收盘后运行，读取模板和当前持仓，生成 T+1 待执行买入/卖出订单 |
| `execute` | 开盘后运行，读取待执行订单，按动作日期价格模拟成交并更新持仓、现金和资产；同一批到期订单先卖出、再买入 |
| `mark` | 收盘后运行，仅更新当前持仓市值、浮动盈亏和每日资产 |
| `refresh` | 手动运行，使用东方财富或腾讯股票最新行情刷新当前持仓价格、市值、浮动盈亏和每日资产；不生成订单、不执行买卖 |
| `after-close` | 定时脚本专用动作，先更新估值，再为所有账户生成下一交易日订单 |

### Excel 账本

| Sheet | 说明 |
| --- | --- |
| `配置快照` | 每次运行时记录模板关键参数 |
| `待执行订单` | T 日生成、T+1 执行的买入/卖出订单及执行状态 |
| `成交流水` | 已成交买卖记录，包含价格、股数、手续费、总金额、实现盈亏和现金余额 |
| `当前持仓` | 未卖出的持仓、成本、当前市值、浮动盈亏和持有天数 |
| `每日资产` | 现金、持仓市值、总资产和累计收益 |
| `运行日志` | 每次运行的动作、状态和异常说明 |

### 使用方式

1. 在 `configs/paper_accounts/` 新增或复制一个中文 YAML 模板。
2. 打开 `/paper`，选择模板。
3. 页面会自动读取所选模板对应的 Excel 账本；如果没有看到日志，可以点击“读取账本”刷新。
4. 收盘后选择“收盘生成待执行订单”，动作日期填信号日。
5. 下一交易日开盘后选择“开盘执行待成交订单”，动作日期填执行日。
6. 收盘后可选择“收盘更新持仓估值”，动作日期填当天交易日。
7. 盘中、收盘后或周末想看当前浮盈时，可以点击“获取当前持仓最新价格”，系统会用实时行情源更新持仓估值和账户权益。
8. 打开对应 Excel 账本，复核订单、成交、持仓、资产和日志。

执行顺序说明：如果 T 日收盘同时生成了卖出和买入订单，T+1 开盘执行时会先处理卖出，再处理买入。这样持仓触发卖出条件时会被模拟卖出，卖出到账资金也可以参与同一轮后续买入。

买入价格和股数说明：生成 T 日收盘买入候选时，系统会先用 T 日未复权收盘价应用 `买入价格筛选`，被过滤的高价或低价股票不会占用最终 TopN 名额；之后再根据 `买入数量.股数`、`买入数量.最低买入金额` 和 `买入数量.每手股数` 计算计划股数。示例：股价 25 元、基础 200 股、最低 10000 元时计划买 400 股；股价 70 元、基础 300 股时基础市值已经 21000 元，就仍计划买 300 股。

实时价格刷新说明：`refresh` 动作不依赖处理后数据是否已经更新到当天，也不会修改待执行订单或成交流水。它只请求实时行情源并重算当前持仓和每日资产；交易时段一般得到盘中最新价，收盘后通常得到当日收盘价或收盘后的最新可用价格，非交易日或节假日通常得到最近交易日收盘价或行情源最后可用价格。若某只股票行情失败，该持仓沿用旧市值并写入警告日志。

### 腾讯云定时任务

推荐 crontab：

```cron
35 9 * * 1-5 /home/ubuntu/T_0_system/scripts/run_paper_trading_cron.sh execute >> /home/ubuntu/T_0_system/logs/paper_trading_cron/cron.log 2>&1
30 21 * * * /home/ubuntu/T_0_system/scripts/run_paper_trading_cron.sh after-close >> /home/ubuntu/T_0_system/logs/paper_trading_cron/cron.log 2>&1
```

运行逻辑：

- 开盘后 `execute`：先判断当天是否为 A 股交易日，是交易日才执行所有模板账户的待成交订单。
- 收盘后 `after-close`：先判断交易日，再确认 `data_bundle/processed_qfq_theme_focus_top100` 已经更新到当天，然后更新估值并生成下一交易日订单。
- 日志目录：`logs/paper_trading_cron/`。
- 检查模式：`scripts/run_paper_trading_cron.sh --check-only after-close 20260429`。

### 异常处理

- 模板不存在或 YAML 格式错误时，API 返回 4xx/5xx，并在前端状态栏显示错误。
- 处理后数据目录不存在或股票文件缺失时，订单会执行失败并写入失败原因。
- 现金不足、已持仓重复买入、开盘不可成交等情况会把订单标记为 `执行失败`，不会隔天继续误买旧信号。
- 如果使用实时行情源失败，订单不会静默成交，会写入失败原因；本地测试默认使用 `本地日线`，避免实时接口波动影响账本逻辑验证。

详细说明见 `docs/paper-trading-system.md`。

## 12. 单股回测模块

### 功能

- 默认从处理后数据目录读取单只股票 CSV，与组合回测和每日收盘选股共用同一份数据
- 展示回测摘要、指标解释、K 线买卖点、交易日志和每日信号表
- 页面展示方式与组合回测一致：上方是紧凑参数区，下方先展示摘要，再用页签切换“指标解释、K 线图、交易日志、信号表”
- 买入条件和卖出条件默认沿用组合回测当前推荐值；由于默认读取同一份处理后数据，`hs300_m20` 等大盘字段可直接共用
- API 仍兼容旧的 `excel_path` 调用方式，但前端默认不再使用 Excel 路径

### 入口

- 页面：`/single`
- API：`POST /api/run-single-stock`

### 主要输入参数

| 参数 | 说明 |
| --- | --- |
| `processed_dir` | 处理后数据目录，与组合回测和每日收盘选股共用 |
| `symbol` | 股票代码或股票名称，例如 `000063` 或 `中兴通讯` |
| `excel_path` | 兼容旧 API 的单个股票 Excel 路径；前端默认不使用 |
| `start_date/end_date` | 回测区间 |
| `buy_condition` | 买入条件 |
| `buy_confirm_days` | 买入连续确认天数 |
| `buy_cooldown_days` | 买入冷却天数 |
| `sell_condition` | 卖出条件 |
| `sell_confirm_days` | 卖出连续确认天数 |
| `execution_timing` | `same_day_close` 或 `next_day_open` |
| `initial_cash` | 初始资金 |
| `per_trade_budget` | 每次目标买入金额 |
| `lot_size` | 每手股数 |
| `buy_fee_rate/sell_fee_rate` | 买卖费率 |
| `stamp_tax_sell` | 卖出印花税 |

### 输出结果

- `summary`
- `metric_definitions`
- `trade_rows`
- `signal_rows`

### 页面内容

- **A** 回测摘要：显示主要指标，并给出每个指标的公式和中文解释
- **B** K 线图：买点卖点直接标在图上，鼠标悬浮显示开、高、低、收、量与信号
- **C** 股票交易日志：展示买卖日期、股数、价格、手续费、剩余现金、交易后持仓和持仓市值、单笔盈亏
- **D** 股票信号表：记录回测区间内每一天的买入信号、卖出信号、执行情况和日末资金状态

### 异常处理

- 处理后数据目录不存在时抛出 `FileNotFoundError`
- 股票代码或名称找不到时抛出 `ValueError`
- 旧 Excel 兼容模式下，Excel 路径不存在时抛出 `FileNotFoundError`
- 缺少 `trade_date` 或执行所需价格列时抛出 `ValueError`

### 当前推荐结果的前端复现示例

如果你要复现当前“主题前100池 + Top2 + 动量买入 + 大盘强度过滤 + 大盘卖出门槛”的推荐结果，可以在前端填写；这些参数也是首页和每日收盘选股页的默认值，单股表格回测页也默认使用同一组买入和卖出条件：

- 处理后数据目录：`D:/量化/Momentum/T_0_system/data_bundle/processed_qfq_theme_focus_top100`
- 开始日期：`20230101`
- 结束日期：`20251231`
- 买入条件：`m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02`
- 卖出条件：`m20<0.08,hs300_m20<0.02`
- 评分表达式：`m20 * 140 + (m20 - m60 / 3) * 90 + (m20 - m120 / 6) * 40 - abs(m5 - 0.03) * 55 - abs(m10 - 0.08) * 30`
- `TopN=2`
- `entry_offset=1`
- `exit_offset=5`
- `min_hold_days=3`
- `max_hold_days=15`

其余交易参数保持：

- 初始资金 `100000`
- 每笔目标资金 `10000`
- 每手股数 `100`
- 买卖费率 `0.00003`
- 印花税 `0`
- 滑点 `3`
- 最低佣金 `0`
- 严格成交 `是`

说明：大盘指标同时放在买入和卖出条件里；买入时要求沪深300二十日动量 `hs300_m20>0.02`，卖出时当个股 `m20<0.08` 且沪深300 `hs300_m20<0.02` 才触发退出，减少弱市买入和强市中过早卖出的情况。

## 13. 回测导出模块

### 功能

- 将回测结果打包为 ZIP 下载

### 入口

- API：`POST /api/run-backtest-export`
- 前端按钮：“下载表格压缩包”；该导出当前仅用于实盘账户回测

### 输出文件

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

说明：ZIP 内 CSV 文件名和 CSV 表头均为中文，适合直接用 Excel 打开查看。

### 异常处理

- 与回测接口相同；若回测失败则不会生成 ZIP

## 14. 特征分层扫描模块

### 功能

- 按 `T+1 open -> T+N open` 的收益标签评估各特征分层效果

### 入口

```bash
python scripts/run_overnight_feature_scan.py --processed-dir data_bundle/processed_qfq --exit-offset 2
```

### 输入参数

| 参数 | 说明 |
| --- | --- |
| `--processed-dir` | 处理后数据目录 |
| `--start-date/--end-date` | 样本区间 |
| `--entry-offset` | 买入偏移，默认 1 |
| `--exit-offset` | 卖出偏移，默认 2 |
| `--per-trade-notional` | 单笔名义资金 |
| `--strict-executable` | 是否只保留可执行样本 |

### 输出结果

- `scan_overview.json`
- `feature_bucket_report.csv`
- `feature_scan_summary.md`

### 异常处理

- 数据目录不存在时抛出 `FileNotFoundError`
- 样本过滤后为空时抛出 `ValueError`

## 15. 参数探索模块

### 功能

- 在训练期批量跑多组 `buy_condition + score_expression + exit_offset`
- 用验证期复核稳定性
- 导出结果排行榜和交易明细

### 入口

```bash
python scripts/run_overnight_research.py --processed-dir data_bundle/processed_qfq --preset swing_v1 --exit-offsets 2,3,4,5
```

### 主要输入参数

| 参数 | 说明 |
| --- | --- |
| `--preset` | 研究预设，默认 `swing_v1` |
| `--train-start/--train-end` | 训练期 |
| `--valid-start/--valid-end` | 验证期 |
| `--entry-offset` | 买入偏移 |
| `--exit-offsets` | 卖出偏移集合 |
| `--top-k` | 训练期保留进入验证的组合数 |
| `--export-top-trades-k` | 额外导出的验证期前几名组合交易明细数 |

### 输出结果

- `train_results.csv`
- `selected_train_cases.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `research_summary.json`
- `research_summary.md`
- `selected_case_trade_records.csv`

### 异常处理

- `exit_offset` 不在 `2~5` 范围时会抛出 `ValueError`
- 预设名不存在时会抛出 `ValueError`

## 16. 买入条件网格测试模块

### 功能

- 用网格方式搜索适合当前系统的买入条件
- 输出稳定性排行榜
- 自动生成总结书和交易明细文件

### 入口

```bash
python scripts/run_buy_condition_grid.py --processed-dir data_bundle/processed_qfq --grid-preset buy_condition_focus_grid_v1 --exit-offsets 4,5
```

### 主要输入参数

| 参数 | 说明 |
| --- | --- |
| `--grid-preset` | 网格预设，当前支持 `buy_condition_grid_v1`、`buy_condition_focus_grid_v1`、`buy_condition_focus_grid_v2`、`buy_condition_topm_grid_v1`、`buy_condition_top1_focus_grid_v1` 与 `buy_condition_top2_focus_grid_v1` |
| `--train-start/--train-end` | 训练期 |
| `--valid-start/--valid-end` | 验证期 |
| `--exit-offsets` | 要测试的卖出偏移集合 |
| `--top-k` | 训练期筛选进入验证的组合数 |
| `--export-top-trades-k` | 导出多少个推荐组合的逐笔交易记录 |

推荐用法：

- `buy_condition_grid_v1`
  粗网格，适合首次扫大方向
- `buy_condition_focus_grid_v1`
  围绕主板老股强趋势条件做第一轮聚焦
- `buy_condition_focus_grid_v2`
  围绕首轮胜出条件做第二轮精细调参
- `buy_condition_topm_grid_v1`
  固定当前最优买入条件，只比较 `TopM` 对交易笔数、胜率和稳定性的影响
- `buy_condition_top1_focus_grid_v1`
  固定 `Top1`，围绕当前最优条件做精细网格
- `buy_condition_top2_focus_grid_v1`
  固定 `Top2`，围绕当前最优条件做精细网格

### 输出结果

- `grid_cases.json`
- `train_results.csv`
- `selected_train_cases.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `grid_summary.json`
- `grid_summary.md`
- `selected_case_trade_records.csv`

### 异常处理

- 网格预设不存在时抛出 `ValueError`
- 输出目录不可写时会抛出文件系统异常
- 数据目录错误时抛出 `FileNotFoundError`

## 17. 卖出指标网格测试模块

### 功能

- 固定当前最优买入条件
- 批量测试不同卖出条件、最短持有天数和最大持有天数
- 输出稳定性排序、总结书和逐笔交易明细

### 入口

```bash
python scripts/run_sell_condition_grid.py --processed-dir data_bundle/processed_qfq
```

### 主要输入参数

| 参数 | 说明 |
| --- | --- |
| `--sell-grid-preset` | 卖出预设；当前支持基础版、高级版和高级微调版 |
| `--buy-condition` | 固定买入条件 |
| `--score-expression` | 固定打分表达式 |
| `--top-n` | 固定持仓名额 |
| `--train-start/--train-end` | 训练期 |
| `--valid-start/--valid-end` | 验证期 |
| `--top-k` | 训练期筛选进入验证的卖出方案数 |

### 输出结果

- `sell_grid_cases.json`
- `train_results.csv`
- `selected_train_cases.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `sell_grid_summary.json`
- `sell_grid_summary.md`
- `selected_case_trade_records.csv`

### 异常处理

- 卖出表达式非法时抛出解析错误
- 数据目录不存在时抛出 `FileNotFoundError`
- `sell_grid_advanced_v1` 会测试止损和浮盈回撤保护两类高级退出
- `holding_return`、`best_return_since_entry`、`drawdown_from_peak` 等字段由回测引擎在持仓期动态计算
- `sell_grid_advanced_v2_micro` 用于围绕当前最佳浮盈回撤退出做更细的参数微调

## 18. 信号中位收益优化扫描模块

### 功能

- 面向信号质量回测中“平均收益为正、但中位单笔收益为负”的情况
- 在当前基础买入条件上批量增加短期动量、大盘动量、K线质量、主板成熟股、行业强度等过滤条件
- 同时比较当前卖出条件、十日转弱退出、五日转弱退出
- 优先按中位单笔收益排序，再参考收益因子、平均收益、胜率、样本数和回撤

### 入口

```bash
python scripts/run_signal_median_scan.py --processed-dir data_bundle/processed_qfq_theme_focus_top100 --start-date 20230101 --end-date 20251231
```

### 主要输入参数

| 参数 | 说明 |
| --- | --- |
| `--processed-dir` | 处理后数据目录 |
| `--start-date/--end-date` | 扫描日期区间 |
| `--buy-condition` | 基础买入条件 |
| `--sell-condition` | 基础卖出条件 |
| `--score-expression` | 评分表达式 |
| `--pool-top-n` | 每个信号日先取多少名候选进入复用池，默认 `20` |
| `--top-k-values` | 要比较的累计 TopK，默认 `1,2,3,5,10,20` |
| `--min-completed` | 推荐结果要求的最低完成信号数，默认 `200` |
| `--sell-scope` | `all` 扫描全部内置卖出条件，`current` 只扫描当前卖出条件 |

### 输出结果

- `中位收益优化结果.csv`：全部组合的中位收益、平均收益、胜率、收益因子、回撤和样本数
- `最佳组合信号明细.csv`：最佳组合下逐笔信号明细，包含买入日期、卖出日期、股票代码、股票名称、执行价、费用、收益率和关键指标
- `中位收益优化总结.md`：中文总结与前 20 名结果
- `扫描配置.json`：本次扫描参数

### 使用提醒

- 该模块是信号质量口径，不模拟账户现金和仓位金额占用，但会跳过同一股票持仓期内的重复信号
- 如果已运行 `scripts/build_industry_strength.py`，扫描会包含行业强度过滤；如果未生成行业字段，行业过滤组合会因为字段缺失而没有有效信号
- 如果最佳中位收益仍小于 0，说明当前动量候选池的普通样本仍偏弱，需要继续收紧买入过滤或调整评分表达式
- 如果中位收益转正但样本数明显下降，需要再回到实盘账户回测验证资金利用率和可执行性

## 19. 交付校验模块

### 功能

- 检查 README、核心文档和前端交付文件是否齐全

### 入口

```bash
python scripts/verify_delivery.py
```

### 当前校验内容

- `README.md`
- `docs/backtest-data-dictionary.md`
- `docs/indicator-reference.md`
- `docs/system-documentation.md`
- `static/index.html`
- `static/app.js`
- `static/style.css`
- `overnight_bt/app.py`

### 异常处理

- 若缺文件或 README 缺少关键章节，脚本返回非 0 退出码

## 20. 推荐交付流程

1. 更新或同步数据
2. 重新构建 `processed_qfq/`
3. 运行相关单测
4. 做一次 API/前端本地冒烟验证
5. 运行 `python scripts/verify_delivery.py`
6. 确认通过后再提交或推送
