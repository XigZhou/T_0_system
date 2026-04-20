# 新 T+1 隔夜回测系统 V1

本项目用于研究 A 股 `T` 日收盘买入、`T+1` 日开盘卖出的批量组合回测，支持：

- 固定快照股票池
- Tushare 原始数据同步
- 原始价格与前复权价格双口径保留
- 每股一个 `processed_qfq/*.csv`
- 前端批量回测与结果导出

## 默认假设

- 默认按 `2000` 积分的 Tushare 账号规划数据接口。
- 默认使用的接口：`stock_basic`、`daily_basic`、`daily`、`adj_factor`、`trade_cal`、`stk_limit`、`suspend_d`、`index_daily`。
- `TUSHARE_TOKEN` 默认优先从本机环境变量读取；如果环境变量缺失，再回退到本地 `.env` 文件。
- 固定快照默认按 `2026-04-17` 当天或此前最近开市日筛选 `总市值 >= 500亿` 且非 `ST` 股票。
- 信号与指标默认按前复权 `qfq_*` 计算，但买入/卖出成交价默认使用原始除权价 `raw_close/raw_open`。
- 为了近似处理隔夜除权除息，若持仓跨过复权因子变动日，回测会按 `adj_factor` 比例修正持仓价值。

这些假设会影响结果正确性，正式跑全量回测前建议先确认你的 Tushare 账号与本机环境一致。

## 准备工作

### 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 配置 Token

推荐方式：

```powershell
$env:TUSHARE_TOKEN="你的本机 token"
```

回退方式：

- 在本地 `.env` 中配置 `TUSHARE_TOKEN=...`
- 不要把 token 明文写入代码、文档或提交记录

### 项目结构

- [overnight_bt](/D:/量化/Momentum/T_0_system/overnight_bt)
  后端逻辑、数据加工、表达式解析与组合回测引擎
- [scripts](/D:/量化/Momentum/T_0_system/scripts)
  数据准备与交付校验脚本
- [static](/D:/量化/Momentum/T_0_system/static)
  前端页面
- [docs](/D:/量化/Momentum/T_0_system/docs)
  中文数据说明与指标说明
- [tests](/D:/量化/Momentum/T_0_system/tests)
  单元测试与集成测试

## 数据准备

### 先生成固定快照股票池

```bash
python scripts/build_universe_snapshot.py --as-of 20260417
```

输出：

- `data_bundle/universe_snapshot.csv`

### 再同步原始数据包

```bash
python scripts/sync_tushare_bundle.py --start-date 20160101 --end-date 20260417
```

输出目录建议结构：

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

### 最后生成处理后回测输入

```bash
python scripts/build_processed_data.py
```

输出：

- `data_bundle/processed_qfq/*.csv`
- `data_bundle/processed_qfq/processing_manifest.csv`

如果你刚刚修改过处理逻辑或新增了隔夜研究字段，需要重新执行这一步，重建整套 `processed_qfq/`。

## 启动方式

```bash
python -m uvicorn overnight_bt.app:app --reload --host 127.0.0.1 --port 8080
```

打开 [http://127.0.0.1:8080](http://127.0.0.1:8080)。

接口入口：

- `GET /health`
- `POST /api/run-backtest`
- `POST /api/run-backtest-export`

## 前端输入与回测逻辑

前端输入项：

- 处理后数据目录
- 开始/结束日期
- 买入条件 `buy_condition`
- 评分表达式 `score_expression`
- `top_n`
- 初始资金
- 每手股数
- 买卖费率
- 印花税
- 滑点
- 最低佣金
- 是否启用严格成交

回测逻辑：

1. `T` 日开盘先处理前一交易日持仓卖出
2. `T` 日收盘前扫描全部股票
3. 用 `buy_condition` 过滤候选
4. 用 `score_expression` 排序
5. 取 `TopN`
6. 用当日原始收盘价 `raw_close` 等权买入，`T+1` 用原始开盘价 `raw_open` 卖出

## 表达式说明

买入条件示例：

```text
m20>0,m5>m5[1],vr<1.2,hs300_pct_chg>-0.8
```

也支持快照与分类过滤，例如：

```text
board=主板,listed_days>250,total_mv_snapshot>8000000,turnover_rate_snapshot<2,pct_chg>2.0
```

评分表达式示例：

```text
m20 + m5 - abs(pct_chg) * 0.1
```

评分表达式支持：

- `+ - * /`
- 圆括号
- `abs(x)`、`min(a,b)`、`max(a,b)`
- 字段偏移，如 `m5[1]`

## 研究脚本

如果你要做“训练期选参数、验证期只复核”的研究，可以运行：

```bash
python scripts/run_overnight_research.py --processed-dir data_bundle/processed_qfq --preset baseline_v1
```

默认配置：

- 训练期：`20190101` 到 `20221231`
- 验证期：`20230101` 到 `20251231`
- 输出目录：`research_runs/20260419_train_valid_v1`

输出文件包括：

- `train_results.csv`
- `selected_train_cases.csv`
- `validation_results.csv`
- `leaderboard.csv`
- `research_summary.json`

如果你要先看“哪些隔夜形态/分层值得研究”，建议先跑特征扫描：

```bash
python scripts/run_overnight_feature_scan.py --processed-dir data_bundle/processed_qfq --start-date 20190101 --end-date 20251231
```

默认输出目录：

- `research_runs/20260419_feature_scan_v1`

输出文件包括：

- `scan_overview.json`
- `feature_bucket_report.csv`
- `feature_scan_summary.md`

如果你要基于新增的隔夜研究字段跑第二版正式候选条件，可以运行：

```bash
python scripts/run_overnight_research.py --processed-dir data_bundle/processed_qfq --preset overnight_v2
```

如果你要基于“更窄的涨停距离区间 + 强实体 + 小上影 + 低放量”跑第三版窄条件研究，可以运行：

```bash
python scripts/run_overnight_research.py --processed-dir data_bundle/processed_qfq --preset overnight_v3
```

如果你要基于“2 到 3 日短周期特征 + v3 窄区间底板”跑第四版研究，可以运行：

```bash
python scripts/run_overnight_research.py --processed-dir data_bundle/processed_qfq --preset overnight_v4
```

## 复现结果

1. 准备好完整 `data_bundle/`
2. 确认其中包含 `processed_qfq/`
3. 启动服务
4. 打开前端并填写：
   - 处理后数据目录
   - 起止日期
   - `buy_condition`
   - `score_expression`
   - `top_n`
   - 资金与交易成本参数
5. 点击“运行回测”
6. 查看：
   - 组合 summary
   - 资金曲线
   - 每日选股
   - 交易流水
   - 个股贡献
7. 如需归档，点击“下载 CSV ZIP”

## 文档入口

- 数据文档：[backtest-data-dictionary.md](/D:/量化/Momentum/T_0_system/docs/backtest-data-dictionary.md)
- 指标文档：[indicator-reference.md](/D:/量化/Momentum/T_0_system/docs/indicator-reference.md)
- 表达式文档：[expression-reference.md](/D:/量化/Momentum/T_0_system/docs/expression-reference.md)

## 交付前校验

```bash
python scripts/verify_delivery.py
python -m unittest discover -s tests -p "test_*.py" -v
```

如果当前目录不是 Git 仓库，不能声称已经完成 GitHub 上传；当前这个工作区就属于这种情况。
