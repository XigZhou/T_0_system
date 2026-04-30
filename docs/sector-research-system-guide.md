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

## 7. 交易日对齐规则

- 当前回测系统默认是 T 日收盘产生信号，T+1 日开盘买入。
- 板块研究的 T 日主题强度只使用 T 日及历史数据，可以作为 T 日收盘信号字段。
- 如果未来改成盘前信号，必须把板块强度整体滞后一日，避免未来函数。
- 成分股数据是最新快照，不是历史成分，长区间回测时需要说明可能存在幸存者偏差。

## 8. 腾讯云同步流程

本地完成提交并推送后，在腾讯云执行：

```bash
ssh ubuntu@124.223.140.163
cd /home/ubuntu/T_0_system
git pull --ff-only origin master
source /home/ubuntu/TencentCloud/myenv/bin/activate
python -m pip install -r requirements.txt
python -m pytest tests/test_sector_research.py tests/test_delivery_checks.py
```

如果只是同步板块研究代码，不需要重启 `t0-system` 服务；因为当前前端/API 还没有直接调用 `sector_research/`。如果后续把板块研究字段作为前端默认目录或接口逻辑的一部分，则修改后端代码后需要重启：

```bash
sudo systemctl restart t0-system
curl http://127.0.0.1:8083/health
```

## 9. 常见异常

| 异常 | 处理方式 |
| --- | --- |
| AKShare 连接东方财富失败 | 等待数据源恢复，或在网络更稳定的环境重试 |
| `No module named akshare` | 执行 `python -m pip install -r requirements.txt` |
| 没有匹配到任何板块 | 检查 `sector_research/configs/themes.yaml` 的关键词是否贴近真实板块名 |
| 资金流抓取失败 | 可先忽略，历史行情和主题强度仍会生成 |
| 合并脚本拒绝覆盖目录 | 确认 `--output-dir` 与 `--processed-dir` 不同 |

## 10. 交付检查

建议每次改完板块研究系统后执行：

```bash
python -m pytest tests/test_sector_research.py tests/test_delivery_checks.py
python scripts/verify_delivery.py
```

正式交付前再跑全量测试：

```bash
python -m pytest
```
