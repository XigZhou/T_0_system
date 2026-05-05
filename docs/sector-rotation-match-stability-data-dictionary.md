# 板块轮动匹配稳定性验证数据说明

本文档说明 `scripts/run_sector_rotation_match_stability.py` 生成的稳定性验证数据。该脚本用于落实 `docs/sector-rotation-match-grid-result-20260504.md` 的下一步建议：验证 `主线簇匹配加权_w5` 是否在分年度、最近一年和滚动窗口中稳定，而不是只依赖某一段行情。

## 1. 数据概览

| 数据名称 | 输出文件路径 | 数据粒度 | 主键字段 | 更新时间 | 用途 |
| --- | --- | --- | --- | --- | --- |
| 稳定性区间汇总 | `research_runs/*_sector_rotation_match_stability/sector_rotation_match_stability_summary.csv` | 每个区间、每条策略一行 | `period_label` + `case` | 每完成一个区间策略组合后更新 | 比较收益、回撤、信号质量、交易次数 |
| 稳定性策略汇总 | `research_runs/*_sector_rotation_match_stability/sector_rotation_match_stability_by_case.csv` | 每条策略一行 | `case` | 每次运行结束后更新 | 统计正收益区间占比、跑赢基准或板块候选次数 |
| 字段覆盖表 | `research_runs/*_sector_rotation_match_stability/sector_rotation_match_stability_coverage.csv` | 每年一行 | `year` | 每次运行开始时生成 | 校验板块字段和轮动字段是否覆盖 |
| 交易流水 | `research_runs/*_sector_rotation_match_stability/sector_rotation_match_stability_trade_records.csv` | 每个区间、每条策略、每笔账户流水一行 | `period_label` + `case` + `trade_date` + `symbol` + `action` | 每完成一个账户回测后追加 | 逐笔复核买入、卖出、费用、金额和盈亏 |
| 运行配置 | `research_runs/*_sector_rotation_match_stability/sector_rotation_match_stability_config.json` | 每次运行一份 | `created_at` | 每次运行开始时生成 | 记录 CLI 参数、区间清单和策略清单 |
| 自动报告 | `research_runs/*_sector_rotation_match_stability/sector_rotation_match_stability_report.md` | 每次运行一份 | 无 | 每次运行结束后生成 | 中文摘要报告 |

`research_runs/` 默认不入库，正式结论需要同步写入 `docs/sector-rotation-match-stability-result-YYYYMMDD.md`。

## 2. 数据来源

| 输入 | 默认路径 | 来源脚本 | 说明 |
| --- | --- | --- | --- |
| 基准处理后股票目录 | `data_bundle/processed_qfq_theme_focus_top100` | `scripts/build_theme_focus_universe.py` | 主题前 100 股票处理后日线，用于基准动量 |
| 板块增强股票目录 | `data_bundle/processed_qfq_theme_focus_top100_sector` | `scripts/build_sector_research_features.py` | 在基准日线上追加 `sector_*` 字段 |
| 每日轮动状态 | `research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv` | `scripts/run_sector_rotation_diagnosis.py` | 每日 Top1 主题、主题簇和轮动状态 |

脚本只读取已有 CSV，不抓取 AKShare 或 Tushare，也不写回输入目录。轮动字段只在内存里合并到板块增强股票数据。

## 3. 策略定义

| 策略 | 数据目录 | 买入条件 | 评分表达式 |
| --- | --- | --- | --- |
| `基准动量` | `data_bundle/processed_qfq_theme_focus_top100` | `m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02` | 基础动量评分 |
| `板块候选_score0.4_rank0.7` | `data_bundle/processed_qfq_theme_focus_top100_sector` | 基础动量 + `sector_exposure_score>0` + `sector_strongest_theme_score>=0.4` + `sector_strongest_theme_rank_pct<=0.7` | 基础动量评分 |
| `主线簇匹配加权_w5` | `data_bundle/processed_qfq_theme_focus_top100_sector` | 同上 | 基础动量评分 + `stock_matches_rotation_top_cluster * 5` |
| `候选_避开新能源主线` | `data_bundle/processed_qfq_theme_focus_top100_sector` | 板块候选 + `rotation_top_cluster!=新能源` | 基础动量评分 |

基础评分表达式：

```text
m20 * 140 + (m20 - m60 / 3) * 90 + (m20 - m120 / 6) * 40
- abs(m5 - 0.03) * 55 - abs(m10 - 0.08) * 30
```

信号指标使用前复权价格字段，买入和卖出使用原始除权开盘价，费用和滑点沿用账户回测引擎。

## 4. 区间定义

脚本不会简单把 `--start-date` 到 `--end-date` 全部混在一起比较，而是先检查板块字段和轮动字段覆盖率。默认 `--min-coverage=0.95`，只有覆盖率达到阈值后的日期才进入板块/轮动策略的公平比较。

输出区间包括：

| 区间类型 | 定义 |
| --- | --- |
| `full` | 板块/轮动字段覆盖后的完整可比区间 |
| `year` | 可比区间内的自然年，最后一年不足全年时标记为 `YYYYYTD` |
| `recent_year` | 截止 `--end-date` 的最近一年 |
| `rolling_6m` | 从结束日向前切分的 6 个月滚动窗口 |
| `rolling_12m` | 从结束日向前切分的 12 个月滚动窗口 |
| `baseline_reference` | `2016-2022` 基准历史参考；因缺少板块和轮动字段，只运行 `基准动量` |

## 5. 关键字段

### 区间汇总字段

| 字段 | 中文含义 | 类型/单位 | 示例 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `period_label` | 区间名称 | 文本 | `2024` | 不允许缺失 | 与 `period_kind` 一起定位区间 |
| `period_kind` | 区间类型 | 文本 | `year` | 不允许缺失 | `full/year/recent_year/rolling_6m/rolling_12m/baseline_reference` |
| `period_start` | 区间开始日期 | `YYYYMMDD` | `20240101` | 不允许缺失 | 信号日期口径 |
| `period_end` | 区间结束日期 | `YYYYMMDD` | `20241231` | 不允许缺失 | 默认截止日估值，不用结束日之后数据 |
| `case` | 策略名称 | 文本 | `主线簇匹配加权_w5` | 不允许缺失 | 对应策略定义 |
| `signal_count` | 信号数量 | 整数 | `180` | 无信号为 `0` | 信号质量模块输出 |
| `signal_median_trade_return` | 信号中位收益 | 小数 | `0.0167` | 无完成信号为 `0` | 便于观察是否只靠少数大赢 |
| `signal_topn_fill_rate` | TopN 填满率 | 小数 | `0.82` | 无候选时为 `0` | 越低代表候选不足 |
| `account_total_return` | 账户总收益 | 小数 | `0.2348` | 回测失败时报错 | `0.2348` 表示 `23.48%` |
| `account_annualized_return` | 年化收益 | 小数 | `0.2456` | 区间过短时可能偏高 | 短窗口仅作参考 |
| `account_max_drawdown` | 最大回撤 | 小数 | `0.0655` | 无交易时为 `0` | 正数表示回撤幅度 |
| `account_buy_count` | 买入成交次数 | 整数 | `66` | 无交易为 `0` | 每次买入按 100 股整数手约束 |
| `account_win_rate` | 已完成交易胜率 | 小数 | `0.5469` | 无完成交易为 `0` | 卖出单口径 |
| `grid_score` | 综合排序分 | 小数 | `0.4123` | 脚本计算 | 只用于横向排序，不是收益 |
| `risk_note` | 风险提示 | 文本 | `信号中位收益不佳` | 无风险时为 `通过基础风险筛选` | 自动提示交易少、收益负、回撤高等 |

### 策略汇总字段

| 字段 | 中文含义 | 计算方式 |
| --- | --- | --- |
| `period_count` | 可比区间数量 | 排除 `baseline_reference` 后的区间数 |
| `positive_period_count` | 正收益区间数量 | `account_total_return > 0` 的区间数 |
| `positive_period_ratio` | 正收益区间占比 | `positive_period_count / period_count` |
| `avg_period_return` | 平均区间收益 | 各区间 `account_total_return` 均值 |
| `min_period_return` | 最差区间收益 | 各区间 `account_total_return` 最小值 |
| `max_drawdown` | 最大区间回撤 | 各区间 `account_max_drawdown` 最大值 |
| `beat_sector_candidate_count` | 跑赢板块候选次数 | 与同区间 `板块候选_score0.4_rank0.7` 比较 |
| `beat_sector_candidate_ratio` | 跑赢板块候选占比 | 跑赢次数 / 可比较次数 |
| `avg_excess_vs_sector_candidate` | 相对板块候选平均超额 | 与同区间板块候选收益差的均值 |
| `beat_baseline_count` | 跑赢基准次数 | 与同区间 `基准动量` 比较 |
| `beat_baseline_ratio` | 跑赢基准占比 | 跑赢次数 / 可比较次数 |

### 覆盖表字段

| 字段 | 中文含义 | 说明 |
| --- | --- | --- |
| `sector_strongest_theme_score_coverage` | 板块强度覆盖率 | 每年非空 `sector_strongest_theme_score` 占比 |
| `sector_strongest_theme_rank_pct_coverage` | 板块排名覆盖率 | 每年非空 `sector_strongest_theme_rank_pct` 占比 |
| `rotation_top_cluster_coverage` | 轮动主线簇覆盖率 | 每年非空 `rotation_top_cluster` 占比 |
| `rotation_state_coverage` | 轮动状态覆盖率 | 每年非空 `rotation_state` 占比 |

## 6. 使用示例

完整稳定性验证：

```bash
python scripts/run_sector_rotation_match_stability.py \
  --start-date 20160101 \
  --end-date 20260429 \
  --out-dir research_runs/20260505_120000_sector_rotation_match_stability
```

中断后续跑：

```bash
python scripts/run_sector_rotation_match_stability.py \
  --start-date 20160101 \
  --end-date 20260429 \
  --out-dir research_runs/20260505_120000_sector_rotation_match_stability \
  --resume
```

如果前一次为了快速补汇总使用了 `--skip-trade-records`，可以只补缺失交易流水：

```bash
python scripts/run_sector_rotation_match_stability.py \
  --start-date 20160101 \
  --end-date 20260429 \
  --out-dir research_runs/20260505_120000_sector_rotation_match_stability \
  --resume \
  --fill-missing-trade-records
```

校验交易流水覆盖是否完整：

```bash
python - <<'PY'
from pathlib import Path
import pandas as pd
out = Path("research_runs/20260505_120000_sector_rotation_match_stability")
summary = pd.read_csv(out / "sector_rotation_match_stability_summary.csv", encoding="utf-8-sig")
trades = pd.read_csv(out / "sector_rotation_match_stability_trade_records.csv", encoding="utf-8-sig")
summary_keys = set(zip(summary["period_label"].astype(str), summary["case"].astype(str)))
trade_keys = set(zip(trades["period_label"].astype(str), trades["case"].astype(str)))
print(len(summary_keys), len(trade_keys), sorted(summary_keys - trade_keys))
PY
```

## 7. 异常处理

- 板块增强目录缺少 `sector_feature_manifest.csv` 或必要 `sector_*` 字段时直接报错。
- 轮动日频文件缺少 `trade_date`、`top_theme`、`top_cluster`、`rotation_state` 时直接报错。
- 若板块/轮动覆盖率不足，脚本会把可比起点推迟到覆盖达标日期；缺字段年份不会被纳入板块轮动结论。
- `--resume` 以 `period_label + case` 判断是否已经完成；如果改了策略定义或回测参数，建议换一个新的 `--out-dir`，避免新旧口径混用。
- `--fill-missing-trade-records` 只补交易流水，不重算汇总；使用前应确认汇总表已经完整。
