# 独立板块研究系统使用说明

本文档说明 `sector_research/` 独立板块研究系统如何安装、运行、查看结果，以及如何把结果安全接入当前回测系统。该系统的设计目标是先独立研究板块与主题强度，不直接修改现有 T+1 回测主数据。

## 1. 系统定位

- 模块目录：`sector_research/`
- 本地入口：`python scripts/run_sector_research.py`
- 回测桥接入口：`python scripts/build_sector_research_features.py`
- 默认输出目录：`sector_research/data/` 与 `sector_research/reports/`
- 腾讯云项目目录：`/home/ubuntu/T_0_system`

当前主题覆盖：

| 主题 | 子赛道 |
| --- | --- |
| 锂矿锂电 | 锂矿资源、锂电池本体、锂电材料、回收设备 |
| 光伏新能源 | 光伏主链、光伏新技术、储能逆变器、新能源车、风电电力设备 |
| 半导体芯片 | 芯片设计、晶圆制造、设备材料、封测先进封装、功率化合物 |
| 存储芯片 | DRAM/HBM、NAND/NOR、存储链条 |
| AI | AI芯片算力、数据中心液冷、光通信连接、PCB电源配套、模型应用、终端软件数据 |
| 机器人 | 机器人本体、传动执行、控制系统、感知交互、工业应用 |
| 医药 | 创新药生物药、CXO服务、医疗器械IVD、中药原料药、消费医疗 |

## 2. 数据来源

默认使用 AKShare 对东方财富板块数据的封装：

| 数据 | 接口 |
| --- | --- |
| 行业板块列表 | `stock_board_industry_name_em` |
| 概念板块列表 | `stock_board_concept_name_em` |
| 行业板块历史行情 | `stock_board_industry_hist_em` |
| 概念板块历史行情 | `stock_board_concept_hist_em` |
| 行业板块成分股 | `stock_board_industry_cons_em` |
| 概念板块成分股 | `stock_board_concept_cons_em` |
| 板块资金流 | `stock_sector_fund_flow_rank` |

可选校验数据源为 Tushare 的申万行业分类与成分接口。默认仍按 2000 积分权限规划，不依赖高积分概念成分接口。

## 3. 准备工作

本地安装依赖：

```bash
python -m pip install -r requirements.txt
```

腾讯云进入项目和虚拟环境：

```bash
cd /home/ubuntu/T_0_system
source /home/ubuntu/TencentCloud/myenv/bin/activate
python -m pip install -r requirements.txt
```

说明：

- AKShare 板块研究不需要在仓库里保存 token。
- 如果后续使用 Tushare 校验数据，仍从环境变量或本地 `.env` 读取 `TUSHARE_TOKEN`。
- 不要把 token 明文写入代码、文档或提交记录。

## 4. 运行板块研究

本地运行：

```bash
cd D:\量化\Momentum\T_0_system
python scripts/run_sector_research.py --start-date 20230101
```

腾讯云运行：

```bash
cd /home/ubuntu/T_0_system
source /home/ubuntu/TencentCloud/myenv/bin/activate
python scripts/run_sector_research.py --start-date 20230101
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--config` | 主题配置，默认 `sector_research/configs/themes.yaml` |
| `--start-date` | 板块历史行情起始日期，格式 `YYYYMMDD` |
| `--end-date` | 结束日期，留空使用本机当天日期 |
| `--raw-dir` | 原始标准化数据目录 |
| `--processed-dir` | 处理后指标目录 |
| `--report-dir` | 报告目录 |
| `--skip-constituents` | 跳过成分股抓取，用于快速调试 |

## 5. 查看输出

核心输出：

| 文件 | 用途 |
| --- | --- |
| `sector_research/data/raw/board_list.csv` | AKShare 行业/概念板块列表标准化结果 |
| `sector_research/data/raw/board_daily_raw.csv` | 板块历史行情标准化结果 |
| `sector_research/data/raw/board_fund_flow_rank.csv` | 板块资金流快照 |
| `sector_research/data/processed/theme_board_mapping.csv` | 主题、子赛道与板块映射 |
| `sector_research/data/processed/sector_board_daily.csv` | 板块日频强度指标 |
| `sector_research/data/processed/theme_strength_daily.csv` | 主题日频强度指标 |
| `sector_research/data/processed/theme_constituents_snapshot.csv` | 板块成分股快照 |
| `sector_research/data/processed/stock_theme_exposure.csv` | 个股主题暴露 |
| `sector_research/reports/theme_strength_report.md` | 最新主题强度研究报告 |
| `sector_research/reports/theme_strength_latest.xlsx` | Excel 汇总报告 |
| `sector_research/reports/sector_research_errors.csv` | 抓取或处理异常明细 |

详细字段说明见：

- `docs/sector-research-data-dictionary.md`
- `docs/sector-research-indicator-documentation.md`

前端工作台：

```bash
python -m uvicorn overnight_bt.app:app --host 127.0.0.1 --port 8083
```

启动后打开 `http://127.0.0.1:8083/sector`。页面只读取已经生成的文件，不触发 AKShare 抓取，也不写入任何数据目录。

| 页面区域 | 数据来源 | 用途 |
| --- | --- | --- |
| 大盘环境 | `data_bundle/market_context.csv` | 读取已有上证指数、沪深300、创业板指上下文字段，辅助判断板块强弱所处的大盘背景 |
| 主题排名 | `sector_research/data/processed/theme_strength_daily.csv` | 查看锂矿锂电、光伏新能源、半导体芯片、存储芯片、AI、机器人、医药等主题强弱 |
| 强势板块 | `sector_research/data/processed/sector_board_daily.csv` | 查看具体行业/概念板块的综合分、动量、成交额放大和资金流 |
| 个股暴露 | `sector_research/data/processed/stock_theme_exposure.csv` | 查看股票代码、股票名称、命中主题、命中板块和暴露分 |
| 主题映射 | `sector_research/data/processed/theme_board_mapping.csv` | 校验主题关键词匹配到了哪些 AKShare 板块 |
| 异常日志 | `sector_research/reports/sector_research_errors.csv` | 查看抓取或处理失败的阶段、板块和错误信息 |

前端 API 为 `GET /api/sector/overview?processed_dir=...&report_dir=...&market_context_path=...`。`processed_dir` 默认 `sector_research/data/processed`，`report_dir` 默认 `sector_research/reports`，`market_context_path` 默认 `data_bundle/market_context.csv`；这些路径都必须位于项目根目录内。

大盘环境面板只读 `market_context.csv`，不会触发 Tushare 或 AKShare 抓取。接口会优先选取“不晚于板块最新交易日”的最近一条大盘记录，用于避免自定义旧板块目录时误展示未来的大盘数据。展示字段包括上证指数、沪深300、创业板指的收盘点位、日涨跌幅、5 日动量、20 日动量和 60 日动量；字段定义见 `docs/backtest-data-dictionary.md` 的 `market_context.csv` 章节。

## 6. 接入当前回测系统

不要直接覆盖当前处理后股票目录。应生成一个增强后的副本目录：

```bash
python scripts/build_sector_research_features.py ^
  --processed-dir data_bundle/processed_qfq_theme_focus_top100 ^
  --sector-processed-dir sector_research/data/processed ^
  --output-dir data_bundle/processed_qfq_theme_focus_top100_sector
```

Linux/Tencent Cloud 写法：

```bash
python scripts/build_sector_research_features.py \
  --processed-dir data_bundle/processed_qfq_theme_focus_top100 \
  --sector-processed-dir sector_research/data/processed \
  --output-dir data_bundle/processed_qfq_theme_focus_top100_sector
```

新增字段示例：

| 字段 | 说明 |
| --- | --- |
| `sector_theme_names` | 股票命中的主题集合 |
| `sector_subtheme_names` | 股票命中的子赛道集合 |
| `sector_board_names` | 股票命中的板块集合 |
| `sector_exposure_score` | 个股主题暴露分 |
| `sector_strongest_theme` | 当日该股票命中主题中最强主题 |
| `sector_strongest_theme_score` | 最强主题综合分 |
| `sector_strongest_theme_rank_pct` | 最强主题排名百分位，越小越强 |
| `sector_strongest_theme_m20` | 最强主题 20 日动量 |
| `sector_strongest_theme_amount_ratio_20` | 最强主题成交额放大倍数 |

回测或前端条件示例：

```text
sector_strongest_theme_score>=0.65,sector_strongest_theme_rank_pct<=0.4,sector_exposure_score>0
```

组合回测页和每日收盘选股页已经内置三套策略预设：

| 预设 | 数据目录 | 说明 |
| --- | --- | --- |
| 基准动量 | `data_bundle/processed_qfq_theme_focus_top100` | 不使用 `sector_*` 字段，用于和增强策略对照 |
| 板块过滤 | `data_bundle/processed_qfq_theme_focus_top100_sector` | 使用板块暴露分、最强主题分和主题排名百分位做买入过滤 |
| 板块过滤 + 评分加权 | `data_bundle/processed_qfq_theme_focus_top100_sector` | 在板块过滤基础上，把主题强度和暴露分加入评分排序 |

板块增强口径会校验 `sector_feature_manifest.csv` 和必要 `sector_*` 字段，缺失时直接报错，避免回测或每日选股误用未增强的数据目录。

## 7. 板块参数网格探索

生成 `data_bundle/processed_qfq_theme_focus_top100_sector` 后，可以运行参数网格探索，比较板块增强到底是提升信号质量，还是只是减少交易次数。

```bash
python scripts/run_sector_parameter_grid.py \
  --start-date 20230101 \
  --score-thresholds 0.4,0.5,0.6 \
  --rank-pcts 0.3,0.5,0.7 \
  --score-weights 10,20,30
```

默认探索三类策略：

| 家族 | 数据目录 | 作用 |
| --- | --- | --- |
| `baseline` | `data_bundle/processed_qfq_theme_focus_top100` | 不使用板块字段，作为收益和活跃度对照 |
| `hard_filter` | `data_bundle/processed_qfq_theme_focus_top100_sector` | 在基础动量条件上增加主题强度阈值、主题排名百分位和个股板块暴露过滤 |
| `score_only` | `data_bundle/processed_qfq_theme_focus_top100_sector` | 不增加板块硬过滤，只把主题强度、暴露分和排名惩罚加入排序分 |

默认基础买入条件：

```text
m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02
```

默认卖出条件：

```text
m20<0.08,hs300_m20<0.02
```

输出目录默认为 `research_runs/YYYYMMDD_HHMMSS_sector_parameter_grid/`：

| 文件 | 用途 |
| --- | --- |
| `sector_parameter_grid_summary.csv` | 每组参数的信号质量、账户收益、回撤、交易次数、胜率和综合排序分 |
| `sector_parameter_grid_trade_records.csv` | 每组参数的完整账户交易流水，便于复核买入、卖出、费用、金额和盈亏 |
| `sector_parameter_grid_config.json` | 本次运行 CLI 参数、策略家族、展开后的买入条件和评分表达式 |
| `sector_parameter_grid_report.md` | 中文 Top 参数总结、基准对照和风险提示 |

脚本只读取既有数据，不触发 AKShare 或 Tushare 抓取。运行前会校验板块增强目录是否存在 `sector_feature_manifest.csv`，以及必要的 `sector_*` 字段是否完整。详细字段定义见 `docs/sector-parameter-grid-data-dictionary.md`。

## 8. 板块效应选股条件探索

如果板块参数网格已经说明某组板块候选有价值，下一步可以进一步验证“有板块效应的股票”本身是否应该优先买。对应脚本为：

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

该脚本比较：

| 家族 | 说明 |
| --- | --- |
| `baseline` | 不使用板块字段的基准动量 |
| `hard_filter` | 把板块暴露、主题强度、主题排名、主题 m20 和成交额放大作为买入过滤 |
| `score_weight` | 买入条件不变，把板块强度字段加入 TopN 评分 |

输出包括 `sector_effect_grid_summary.csv`、`sector_effect_grid_trade_records.csv`、`sector_effect_grid_config.json` 和 `sector_effect_grid_report.md`。交易流水会统一所有动作的列集合后写出，便于后续用 Excel 或 pandas 校验逐笔买卖。字段说明见 `docs/sector-effect-grid-data-dictionary.md`，正式结果记录见 `docs/sector-effect-grid-result-20260504.md`。

## 9. 板块轮动诊断

参数网格探索找出候选组合后，建议继续运行板块轮动诊断，判断收益是否来自主线轮动，而不是少数个股或单段行情。

```bash
python scripts/run_sector_rotation_diagnosis.py \
  --theme-strength-path sector_research/data/processed/theme_strength_daily.csv \
  --trade-records-path research_runs/20260501_142052_sector_parameter_grid/sector_parameter_grid_trade_records.csv \
  --sector-processed-dir data_bundle/processed_qfq_theme_focus_top100_sector \
  --cases 基准动量,硬过滤_score0.4_rank0.7
```

默认主题簇：

| 主题簇 | 包含主题 |
| --- | --- |
| 科技成长 | `AI`、`半导体芯片`、`存储芯片`、`机器人` |
| 新能源 | `光伏新能源`、`锂矿锂电` |
| 医药防御 | `医药` |

默认输出目录为 `research_runs/YYYYMMDD_HHMMSS_sector_rotation_diagnosis/`。核心输出包括：

| 文件 | 用途 |
| --- | --- |
| `sector_rotation_daily.csv` | 每日 Top1 主题、主题簇、持续天数、领先幅度和轮动状态 |
| `sector_rotation_theme_runs.csv` | 每段连续主线的开始、结束、持续天数和分数变化 |
| `sector_rotation_transitions.csv` | Top1 主题之间的切换次数 |
| `sector_rotation_labeled_trades.csv` | 给每笔交易标记信号日主线、股票所属主题和是否匹配主线 |
| `sector_rotation_trade_summary.csv` | 按轮动状态、Top1 主题、主题簇和股票主题统计收益 |
| `sector_rotation_report.md` | 中文诊断报告 |

轮动状态只用于研究分组，不会直接修改买入或卖出逻辑。字段和分类规则见 `docs/sector-rotation-diagnosis-data-dictionary.md`。

## 10. 股票匹配主线轮动 TopN 网格

市场级轮动字段直接加到评分里不会改变同日 TopN，因为同一天所有候选股票得到的是同一个常数。要让轮动真正影响 TopN，应使用股票差异化字段：

```bash
python scripts/run_sector_rotation_match_grid.py \
  --start-date 20230101 \
  --end-date 20260429 \
  --out-dir research_runs/20260504_191500_sector_rotation_match_grid \
  --cluster-weights 5,10 \
  --theme-weights 8,12 \
  --penalty-weights 5,8
```

该脚本会比较：

| 家族 | 说明 |
| --- | --- |
| `rotation_match_filter` | 股票必须匹配当日 Top1 主题或主题簇 |
| `rotation_match_score` | 股票匹配主线时加分，不硬过滤 |
| `rotation_cluster_guard` | 避开某类市场主线，例如新能源 |

输出中的 `sector_rotation_match_grid_pick_records.csv` 会补充 `stock_matches_rotation_top_cluster` 和 `stock_matches_rotation_top_theme`，汇总表会计算与原 `板块候选_score0.4_rank0.7` 的 TopN 重合率。字段说明见 `docs/sector-rotation-match-grid-data-dictionary.md`。

## 11. 板块轮动状态条件网格

轮动诊断确认某些状态或主题簇更有价值后，可以继续运行轮动状态条件网格，验证“上一轮最佳板块候选 + 轮动过滤”是否优于基准和原候选。

```bash
python scripts/run_sector_rotation_grid.py \
  --rotation-daily-path research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv \
  --start-date 20230101 \
  --end-date 20260429
```

默认先沿用上一轮最佳板块候选：

```text
sector_exposure_score>0,sector_strongest_theme_score>=0.4,sector_strongest_theme_rank_pct<=0.7
```

再叠加以下轮动条件：

| 策略 | 用途 |
| --- | --- |
| `候选_新主线启动` | 验证追新主线是否有效 |
| `候选_主线退潮` | 验证主线退潮状态是否更适合板块过滤 |
| `候选_轮动观察` | 验证轮动观察状态是否更适合板块过滤 |
| `候选_退潮或观察` | 合并上一轮诊断中相对更好的状态 |
| `候选_避开新主线启动` | 验证剔除追新后是否改善 |
| `候选_科技成长主线` | 只保留科技成长成为主线的信号 |
| `候选_科技成长且股票匹配` | 科技成长主线下只买科技成长股票 |
| `候选_避开新能源主线` | 验证新能源主线较弱时是否应剔除 |

输出目录为 `research_runs/YYYYMMDD_HHMMSS_sector_rotation_grid/`，包含汇总表、交易流水、参数配置和中文报告。字段定义见 `docs/sector-rotation-grid-data-dictionary.md`。

该脚本在内存里把轮动字段合并到板块增强股票数据，不覆盖 `data_bundle/processed_qfq_theme_focus_top100_sector`。

## 12. 交易日对齐规则

- 当前回测系统默认是 T 日收盘产生信号，T+1 日开盘买入。
- 板块研究的 T 日主题强度只使用 T 日及历史数据，可以作为 T 日收盘信号字段。
- 如果未来改成盘前信号，必须把板块强度整体滞后一日，避免未来函数。
- 成分股数据是最新快照，不是历史成分，长区间回测时需要说明可能存在幸存者偏差。

## 13. 腾讯云同步流程

本地完成提交并推送后，在腾讯云执行：

```bash
ssh ubuntu@124.223.140.163
cd /home/ubuntu/T_0_system
git pull --ff-only origin master
source /home/ubuntu/TencentCloud/myenv/bin/activate
python -m pip install -r requirements.txt
python -m pytest tests/test_sector_research.py tests/test_delivery_checks.py
```

如果改动包含 `/sector` 页面、`/api/sector/overview` 接口或 `overnight_bt/sector_dashboard.py`，需要重启 `t0-system` 服务或重新启动临时 `uvicorn`，否则后台进程仍会使用旧代码：

```bash
sudo systemctl restart t0-system
curl http://127.0.0.1:8083/health
```

## 14. 常见异常

| 异常 | 处理方式 |
| --- | --- |
| AKShare 连接东方财富失败 | 等待数据源恢复，或在网络更稳定的环境重试 |
| `No module named akshare` | 执行 `python -m pip install -r requirements.txt` |
| 没有匹配到任何板块 | 检查 `sector_research/configs/themes.yaml` 的关键词是否贴近真实板块名 |
| 资金流抓取失败 | 可先忽略，历史行情和主题强度仍会生成 |
| 合并脚本拒绝覆盖目录 | 确认 `--output-dir` 与 `--processed-dir` 不同 |
| 网格探索提示缺少 `sector_feature_manifest.csv` | 先运行 `scripts/build_sector_research_features.py` 生成板块增强目录 |
| 轮动诊断交易股票缺少主题字段 | 确认 `--sector-processed-dir` 指向板块增强目录，而不是基准目录 |
| 轮动状态网格提示不支持 `rotation_*` 字段 | 确认代码已包含 `overnight_bt/rotation_features.py`，并且表达式白名单已更新 |

## 15. 交付检查

建议每次改完板块研究系统后执行：

```bash
python -m pytest tests/test_sector_research.py tests/test_sector_parameter_grid.py tests/test_sector_rotation_diagnosis.py tests/test_sector_rotation_grid.py tests/test_delivery_checks.py
python scripts/verify_delivery.py
```

正式交付前再跑全量测试：

```bash
python -m pytest
```
