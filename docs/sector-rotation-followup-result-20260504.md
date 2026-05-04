# 板块轮动后续验证结果记录（2026-05-04）

本文落实 `docs/sector-rotation-grid-result-20260501.md` 里的下一步建议：对三条候选策略做分年度和最近一年对比，并验证“轮动状态不硬过滤、改为评分加权”的可行性。

## 1. 运行命令

```bash
cd /home/ubuntu/T_0_system
source /home/ubuntu/TencentCloud/myenv/bin/activate

python scripts/run_sector_rotation_followup.py \
  --start-date 20230101 \
  --end-date 20260429 \
  --out-dir research_runs/20260504_130000_sector_rotation_followup
```

长实验支持中断续跑。本次实际使用过分批续跑，命令示例：

```bash
python scripts/run_sector_rotation_followup.py \
  --start-date 20230101 \
  --end-date 20260429 \
  --out-dir research_runs/20260504_130000_sector_rotation_followup \
  --resume \
  --max-weighted-runs 2
```

## 2. 数据来源

| 数据 | 路径 | 说明 |
| --- | --- | --- |
| 基准处理后股票 | `data_bundle/processed_qfq_theme_focus_top100` | 主题前 100 股票处理后日线 |
| 板块增强股票 | `data_bundle/processed_qfq_theme_focus_top100_sector` | 含 `sector_*` 字段的增强目录 |
| 每日轮动状态 | `research_runs/20260501_153900_sector_rotation_diagnosis/sector_rotation_daily.csv` | 板块轮动诊断输出 |

脚本只读取上述输入，不抓取 AKShare 或 Tushare，也不覆盖原始处理后目录。

## 3. 输出文件

| 文件 | 路径 | 是否入库 |
| --- | --- | --- |
| 结果报告 | `research_runs/20260504_130000_sector_rotation_followup/sector_rotation_followup_report.md` | 不入库，随运行产物保留 |
| 分年度和最近一年对比 | `research_runs/20260504_130000_sector_rotation_followup/sector_rotation_period_comparison.csv` | 不入库 |
| 加权评分汇总 | `research_runs/20260504_130000_sector_rotation_followup/sector_rotation_weighted_score_summary.csv` | 不入库 |
| 加权评分交易流水 | `research_runs/20260504_130000_sector_rotation_followup/sector_rotation_weighted_score_trade_records.csv` | 不入库，约 9.8MB |
| 参数配置 | `research_runs/20260504_130000_sector_rotation_followup/sector_rotation_followup_config.json` | 不入库 |

## 4. 分年度和最近一年对比

| 周期 | 策略 | 账户收益 | 最大回撤 | 买入次数 | 账户胜率 | 信号中位收益 | 结论 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 全区间 | 基准动量 | 75.86% | 11.90% | 238 | 51.50% | 0.28% | 通过基础风险筛选 |
| 全区间 | 板块候选_score0.4_rank0.7 | 87.29% | 11.30% | 212 | 52.17% | -0.04% | 收益最高，但中位信号偏弱 |
| 全区间 | 候选_避开新能源主线 | 79.40% | 11.18% | 167 | 54.32% | 0.03% | 保守备选 |
| 2023 | 基准动量 | 0.49% | 10.85% | 50 | 40.00% | -1.75% | 弱 |
| 2023 | 板块候选_score0.4_rank0.7 | -1.71% | 10.16% | 28 | 32.14% | -1.83% | 弱 |
| 2023 | 候选_避开新能源主线 | -0.46% | 3.76% | 14 | 35.71% | -1.74% | 样本少但回撤低 |
| 2024 | 基准动量 | 16.85% | 7.12% | 72 | 56.06% | -0.32% | 可用 |
| 2024 | 板块候选_score0.4_rank0.7 | 22.78% | 6.58% | 67 | 52.31% | -0.32% | 三者最好 |
| 2024 | 候选_避开新能源主线 | 21.54% | 6.64% | 62 | 55.00% | 0.15% | 更稳 |
| 2025 | 基准动量 | 53.47% | 11.59% | 93 | 57.14% | 3.31% | 三者最好 |
| 2025 | 板块候选_score0.4_rank0.7 | 44.33% | 10.80% | 96 | 57.78% | 1.86% | 可用 |
| 2025 | 候选_避开新能源主线 | 46.83% | 11.39% | 72 | 61.76% | 2.41% | 胜率更高 |
| 2026YTD | 基准动量 | -1.33% | 11.73% | 16 | 36.36% | -0.81% | 弱 |
| 2026YTD | 板块候选_score0.4_rank0.7 | -2.41% | 5.54% | 13 | 12.50% | -0.70% | 弱 |
| 2026YTD | 候选_避开新能源主线 | -2.41% | 5.54% | 13 | 12.50% | -0.70% | 弱 |
| 最近一年 | 基准动量 | 59.41% | 7.59% | 96 | 61.54% | 4.23% | 最强 |
| 最近一年 | 板块候选_score0.4_rank0.7 | 58.47% | 8.88% | 100 | 61.05% | 2.42% | 接近基准 |
| 最近一年 | 候选_避开新能源主线 | 59.19% | 7.65% | 75 | 65.71% | 2.69% | 更少交易、更高胜率 |

年度集中度：

- `基准动量` 最好年份为 `2025`，收益 `53.47%`，占正收益年份合计的 `75.51%`。
- `板块候选_score0.4_rank0.7` 最好年份为 `2025`，收益 `44.33%`，占正收益年份合计的 `66.06%`。
- `候选_避开新能源主线` 最好年份为 `2025`，收益 `46.83%`，占正收益年份合计的 `68.49%`。

结论：三条策略都明显受 2025 年贡献影响，2023 和 2026YTD 偏弱。因此不能只看全区间收益，后续更需要滚动窗口或分市场环境验证。

## 5. 轮动加权评分实验

本次测试了 27 组权重：

```text
基础评分
+ rotation_top_cluster_tech * {0,2,4}
- rotation_top_cluster_new_energy * {0,2,4}
- rotation_is_new_start * {0,2,4}
```

结果：27 组完全相同。

| 指标 | 数值 |
| --- | ---: |
| 账户收益 | 87.29% |
| 年化收益 | 21.76% |
| 最大回撤 | 11.30% |
| 买入次数 | 212 |
| 胜率 | 52.17% |
| 信号中位收益 | -0.04% |

原因：`rotation_top_cluster_tech`、`rotation_top_cluster_new_energy`、`rotation_is_new_start` 都是“信号日市场级字段”。同一个交易日里，所有候选股票的这些值相同；把它们加到评分表达式后，只会给当天所有候选整体加减同一个常数，不会改变同一天候选股票之间的排序。因此它不会影响 TopN，也不会改变交易结果。

## 6. 策略判断

1. `板块候选_score0.4_rank0.7` 仍是全区间最高收益方案，但中位信号略负，且收益集中在 2024-2025。
2. `候选_避开新能源主线` 适合作为保守账户继续观察：全区间收益低于板块候选，但胜率更高、信号中位收益为正，最近一年与基准非常接近。
3. 轮动“市场级状态”不适合直接作为评分加权项，因为不会改变日内股票排序。
4. 如果继续研究轮动加权，应改成股票差异化字段，例如 `stock_matches_rotation_top_cluster`、`stock_matches_rotation_top_theme`、`stock_theme_cluster=科技成长` 等；这些字段在同一天不同股票之间可能不同，才可能改变 TopN。

## 7. 下一步建议

下一步不建议继续扩大 `rotation_top_cluster_*` 这类市场级评分权重。更合理的方向：

1. 做“股票是否匹配当日主线”的加权评分实验：

```text
基础评分
+ stock_matches_rotation_top_cluster * 权重
+ stock_matches_rotation_top_theme * 权重
- rotation_is_new_start * stock_matches_rotation_top_cluster * 权重
```

2. 保留两个模拟账户继续观察：
   - `板块候选_score04_rank07_v1`
   - `板块轮动_避开新能源_v1`
3. 后续做滚动窗口稳定性验证，尤其关注 2023、2026YTD 这种弱行情区间。
