# 独立板块研究系统数据说明

本文档说明 `sector_research/` 独立板块研究系统的数据来源、输出文件、字段定义、清洗规则与使用方式。该系统默认只写入 `sector_research/` 目录；如需并入当前回测系统，必须通过独立输出目录生成增强后的股票 CSV 副本，不覆盖现有 `data_bundle/processed_qfq*` 主目录。

## 1. 数据概览

- 数据名称：板块主题研究数据
- 输出根目录：`sector_research/`
- 数据粒度：板块日频、主题日频、成分股快照、个股主题暴露快照
- 主键字段：
  - 板块日线：`trade_date + board_type + board_name + theme_name + subtheme_name`
  - 主题日线：`trade_date + theme_name`
  - 个股主题暴露：`stock_code + stock_name`
- 更新时间：执行 `python scripts/run_sector_research.py` 时生成
- 数据用途：研究锂矿锂电、光伏新能源、半导体芯片、存储芯片、AI、机器人、医药等主题方向的板块强弱，并为后续回测提供主题过滤或增强因子

## 2. 来源说明

默认数据源为 AKShare 对东方财富板块数据的封装：

| 数据 | AKShare 接口 | 说明 |
| --- | --- | --- |
| 行业板块列表 | `stock_board_industry_name_em` | 东方财富行业板块列表 |
| 概念板块列表 | `stock_board_concept_name_em` | 东方财富概念板块列表 |
| 行业板块历史行情 | `stock_board_industry_hist_em` | 板块日线行情 |
| 概念板块历史行情 | `stock_board_concept_hist_em` | 板块日线行情 |
| 行业板块成分股 | `stock_board_industry_cons_em` | 最新成分股快照 |
| 概念板块成分股 | `stock_board_concept_cons_em` | 最新成分股快照 |
| 板块资金流排名 | `stock_sector_fund_flow_rank` | 今日、5日、10日主力资金流 |

辅助校验数据源可使用 Tushare：

| 数据 | Tushare 接口 | 默认用途 |
| --- | --- | --- |
| 申万行业分类 | `index_classify` | 后续校验行业口径 |
| 申万行业成分 | `index_member_all` | 后续校验行业成分 |

权限假设：

- AKShare 不需要本项目保存 token，但依赖外部公开数据源可访问。
- Tushare 默认按 2000 积分权限规划；高积分概念接口不作为必备路径。
- 任何 token 都从环境变量或本地 `.env` 读取，不写入代码、文档或提交记录。

## 3. 主题配置

主题配置文件为：

```text
sector_research/configs/themes.yaml
```

当前覆盖：

| 主题 | 子赛道 |
| --- | --- |
| 锂矿锂电 | 锂矿资源、锂电池本体、锂电材料、回收设备 |
| 光伏新能源 | 光伏主链、光伏新技术、储能逆变器、新能源车、风电电力设备 |
| 半导体芯片 | 芯片设计、晶圆制造、设备材料、封测先进封装、功率化合物 |
| 存储芯片 | DRAM/HBM、NAND/NOR、存储链条 |
| AI | AI芯片算力、数据中心液冷、光通信连接、PCB电源配套、模型应用、终端软件数据 |
| 机器人 | 机器人本体、传动执行、控制系统、感知交互、工业应用 |
| 医药 | 创新药生物药、CXO服务、医疗器械IVD、中药原料药、消费医疗 |

匹配规则：

- 用每个子赛道的关键词匹配 AKShare 返回的 `board_name`。
- 同一个板块可以同时命中多个主题或子赛道。
- 关键词只做包含匹配，不做语义推断；因此新增主题时应优先使用真实板块名中常见的关键词。

## 4. 输出文件

### 4.1 `sector_research/data/raw/board_list.csv`

- 数据粒度：板块快照
- 主键：`board_type + board_name`
- 来源：AKShare 行业板块列表、概念板块列表

| 字段名 | 中文含义 | 类型/单位 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- |
| `board_type` | 板块类型 | `industry`/`concept` | 不允许缺失 | 行业或概念 |
| `board_code` | 板块代码 | 字符串 | 允许为空 | 取决于 AKShare 返回 |
| `board_name` | 板块名称 | 字符串 | 空值剔除 | 主题匹配字段 |
| `latest_price` | 最新价 | 数值 | 无法解析为空 | 板块指数价格 |
| `pct_chg` | 最新涨跌幅 | 百分点 | 无法解析为空 | 例如 `2.35` 表示 2.35% |
| `amount` | 成交额 | 元 | 无法解析为空 | `万`、`亿` 会转成数值 |
| `turnover_rate` | 换手率 | 百分点 | 无法解析为空 | 取决于源数据 |
| `up_count` | 上涨家数 | 只 | 无法解析为空 | 板块快照字段 |
| `down_count` | 下跌家数 | 只 | 无法解析为空 | 板块快照字段 |
| `leader_stock` | 领涨股票 | 字符串 | 允许为空 | 源数据字段 |
| `source` | 数据来源 | 字符串 | 不允许缺失 | 默认 `AKShare` |
| `fetched_at` | 抓取时间 | `YYYY-MM-DD HH:MM:SS` | 不允许缺失 | 本地运行时间 |

### 4.2 `sector_research/data/raw/board_daily_raw.csv`

- 数据粒度：板块日线
- 主键：`trade_date + board_type + board_name + theme_name + subtheme_name`
- 来源：AKShare 行业/概念板块历史行情

| 字段名 | 中文含义 | 类型/单位 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- |
| `trade_date` | 交易日期 | `YYYYMMDD` | 空值剔除 | 由源日期转成无横线格式 |
| `board_type` | 板块类型 | 字符串 | 不允许缺失 | 行业或概念 |
| `board_name` | 板块名称 | 字符串 | 不允许缺失 | |
| `open` | 开盘价 | 数值 | 无法解析为空 | 板块指数价格 |
| `close` | 收盘价 | 数值 | 无法解析为空 | 板块强度主输入 |
| `high` | 最高价 | 数值 | 无法解析为空 | |
| `low` | 最低价 | 数值 | 无法解析为空 | |
| `pct_chg` | 涨跌幅 | 百分点 | 无法解析为空 | |
| `vol` | 成交量 | 源单位 | 无法解析为空 | AKShare 原始口径 |
| `amount` | 成交额 | 元 | 无法解析为空 | |
| `turnover_rate` | 换手率 | 百分点 | 无法解析为空 | |
| `source` | 数据来源 | 字符串 | 不允许缺失 | |
| `theme_name` | 主题名称 | 字符串 | 不允许缺失 | 来自配置匹配 |
| `subtheme_name` | 子赛道名称 | 字符串 | 不允许缺失 | 来自配置匹配 |
| `matched_keyword` | 命中关键词 | 字符串 | 不允许缺失 | 便于审计 |
| `board_code` | 板块代码 | 字符串 | 允许为空 | |

### 4.3 `sector_research/data/raw/board_fund_flow_rank.csv`

- 数据粒度：板块资金流快照
- 主键：`board_type + fund_flow_indicator + board_name`
- 来源：AKShare `stock_sector_fund_flow_rank`

| 字段名 | 中文含义 | 类型/单位 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- |
| `board_type` | 板块类型 | 字符串 | 不允许缺失 | |
| `fund_flow_indicator` | 资金流区间 | `今日`/`5日`/`10日` | 不允许缺失 | |
| `board_name` | 板块名称 | 字符串 | 空值剔除 | |
| `pct_chg` | 涨跌幅 | 百分点 | 无法解析为空 | |
| `main_net_inflow` | 主力净流入净额 | 元 | 无法解析为空 | |
| `main_net_inflow_ratio` | 主力净流入占比 | 百分点 | 无法解析为空 | |
| `super_net_inflow` | 超大单净流入净额 | 元 | 无法解析为空 | |
| `source` | 数据来源 | 字符串 | 不允许缺失 | |
| `fetched_at` | 抓取时间 | 时间文本 | 不允许缺失 | |

如果资金流抓取失败，会记录到 `sector_research/reports/sector_research_errors.csv`，不会阻断历史行情和主题强度计算。

### 4.4 `sector_research/data/processed/theme_board_mapping.csv`

- 数据粒度：主题与板块映射
- 主键：`theme_name + subtheme_name + board_type + board_name`

| 字段名 | 中文含义 | 类型/单位 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- |
| `theme_name` | 主题名称 | 字符串 | 不允许缺失 | |
| `subtheme_name` | 子赛道名称 | 字符串 | 不允许缺失 | |
| `matched_keyword` | 命中关键词 | 字符串 | 不允许缺失 | |
| `board_type` | 板块类型 | 字符串 | 不允许缺失 | |
| `board_code` | 板块代码 | 字符串 | 允许为空 | |
| `board_name` | 板块名称 | 字符串 | 不允许缺失 | |
| `source` | 数据来源 | 字符串 | 不允许缺失 | |
| `fetched_at` | 抓取时间 | 时间文本 | 不允许缺失 | |

### 4.5 `sector_research/data/processed/sector_board_daily.csv`

- 数据粒度：板块日频强度
- 主键：`trade_date + board_type + board_name + theme_name + subtheme_name`

除 `board_daily_raw.csv` 字段外，新增：

| 字段名 | 中文含义 | 类型/单位 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- |
| `m5`、`m20`、`m60`、`m120`、`m250` | 板块动量 | 小数 | 样本不足为空 | 基于板块 `close` |
| `amount20` | 20日成交额均值 | 元 | 至少 5 个样本，否则为空 | |
| `amount_ratio_20` | 成交额放大倍数 | 倍 | 分母为空或为0时为空 | |
| `high_120` | 120日最高价 | 数值 | 至少20个样本 | |
| `high_250` | 250日最高价 | 数值 | 至少40个样本 | |
| `low_250` | 250日最低价 | 数值 | 至少40个样本 | |
| `drawdown_from_120_high` | 距120日高点回撤 | 小数 | 依赖 `high_120` | |
| `position_in_250_range` | 250日区间位置 | `0~1` | 分母为0时为空 | 越高越接近区间高位 |
| `volume_price_score` | 量价齐升分 | `0~1` | 依赖基础指标 | 趋势增强分 |
| `reversal_score` | 极弱反转分 | `0~1` | 依赖基础指标 | 低位修复分 |
| `theme_board_score` | 板块综合分 | `0~1` | 依赖基础指标 | 取两个子分较高值 |
| `board_rank_in_theme` | 主题内板块排名 | 正整数 | 分数为空则为空 | 1 为最强 |
| `board_rank_in_theme_pct` | 主题内排名百分位 | `0~1` | 分数为空则为空 | 越小越强 |
| `board_rank_overall` | 全部匹配板块排名 | 正整数 | 分数为空则为空 | 1 为最强 |
| `board_rank_overall_pct` | 全部匹配板块排名百分位 | `0~1` | 分数为空则为空 | 越小越强 |
| `main_net_inflow_today`、`main_net_inflow_5d`、`main_net_inflow_10d` | 主力净流入 | 元 | 抓取失败为空 | 只合并到最新交易日 |
| `main_net_inflow_ratio_today`、`main_net_inflow_ratio_5d`、`main_net_inflow_ratio_10d` | 主力净流入占比 | 百分点 | 抓取失败为空 | 只合并到最新交易日 |

### 4.6 `sector_research/data/processed/theme_strength_daily.csv`

- 数据粒度：主题日频强度
- 主键：`trade_date + theme_name`

| 字段名 | 中文含义 | 类型/单位 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- |
| `trade_date` | 交易日期 | `YYYYMMDD` | 不允许缺失 | |
| `theme_name` | 主题名称 | 字符串 | 不允许缺失 | |
| `board_count` | 匹配板块数 | 个 | 不允许缺失 | |
| `subtheme_count` | 匹配子赛道数 | 个 | 不允许缺失 | |
| `m5`、`m20`、`m60`、`m120` | 主题平均动量 | 小数 | 全部为空则为空 | 对主题下板块取均值 |
| `amount_ratio_20` | 主题成交额放大均值 | 倍 | 全部为空则为空 | |
| `board_up_ratio` | 板块上涨比例 | `0~1` | 不允许缺失 | |
| `positive_m20_ratio` | 20日正动量板块比例 | `0~1` | 不允许缺失 | |
| `volume_price_score` | 量价齐升均值 | `0~1` | 全部为空则为空 | |
| `reversal_score` | 极弱反转均值 | `0~1` | 全部为空则为空 | |
| `theme_score` | 主题综合分 | `0~1` | 全部为空则为空 | 主题强度排序主字段 |
| `strongest_board` | 当日最强板块 | 字符串 | 允许为空 | |
| `strongest_subtheme` | 当日最强子赛道 | 字符串 | 允许为空 | |
| `strongest_board_score` | 当日最强板块分 | `0~1` | 允许为空 | |
| `theme_rank` | 当日主题排名 | 正整数 | 分数为空则为空 | 1 为最强 |
| `theme_rank_pct` | 当日主题排名百分位 | `0~1` | 分数为空则为空 | 越小越强 |

### 4.7 `sector_research/data/processed/theme_constituents_snapshot.csv`

- 数据粒度：板块成分股快照
- 主键：`board_type + board_name + stock_code + stock_name`

| 字段名 | 中文含义 | 类型/单位 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- |
| `board_type` | 板块类型 | 字符串 | 不允许缺失 | |
| `board_name` | 板块名称 | 字符串 | 不允许缺失 | |
| `stock_code` | 股票代码 | 6位字符串 | 代码和名称至少一个非空 | 会补齐前导零 |
| `stock_name` | 股票名称 | 字符串 | 代码和名称至少一个非空 | |
| `latest_price` | 最新价 | 数值 | 无法解析为空 | 快照字段 |
| `pct_chg` | 涨跌幅 | 百分点 | 无法解析为空 | 快照字段 |
| `amount` | 成交额 | 元 | 无法解析为空 | 快照字段 |
| `turnover_rate` | 换手率 | 百分点 | 无法解析为空 | 快照字段 |
| `source` | 数据来源 | 字符串 | 不允许缺失 | |
| `fetched_at` | 抓取时间 | 时间文本 | 不允许缺失 | |
| `theme_name` | 主题名称 | 字符串 | 不允许缺失 | |
| `subtheme_name` | 子赛道名称 | 字符串 | 不允许缺失 | |
| `matched_keyword` | 命中关键词 | 字符串 | 不允许缺失 | |
| `board_code` | 板块代码 | 字符串 | 允许为空 | |

### 4.8 `sector_research/data/processed/stock_theme_exposure.csv`

- 数据粒度：个股主题暴露快照
- 主键：`stock_code + stock_name`

| 字段名 | 中文含义 | 类型/单位 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- |
| `stock_code` | 股票代码 | 6位字符串 | 不允许缺失 | |
| `stock_name` | 股票名称 | 字符串 | 允许为空 | |
| `theme_count` | 命中主题数 | 个 | 不允许缺失 | |
| `subtheme_count` | 命中子赛道数 | 个 | 不允许缺失 | |
| `board_count` | 命中板块数 | 个 | 不允许缺失 | |
| `theme_names` | 命中主题集合 | 字符串 | 允许为空 | 多值用 `、` 分隔 |
| `subtheme_names` | 命中子赛道集合 | 字符串 | 允许为空 | 多值用 `、` 分隔 |
| `board_types` | 命中板块类型集合 | 字符串 | 允许为空 | |
| `board_names` | 命中板块集合 | 字符串 | 允许为空 | |
| `matched_keywords` | 命中关键词集合 | 字符串 | 允许为空 | |
| `sources` | 数据来源集合 | 字符串 | 允许为空 | |
| `latest_fetched_at` | 最新抓取时间 | 时间文本 | 允许为空 | |
| `primary_theme` | 首个主题标签 | 字符串 | 允许为空 | 便于快速浏览 |
| `primary_subtheme` | 首个子赛道标签 | 字符串 | 允许为空 | 便于快速浏览 |
| `exposure_score` | 主题暴露分 | `0~1` | 不允许缺失 | `board_count / 全样本最大 board_count` |

### 4.9 `sector_research/reports/`

| 文件 | 内容 |
| --- | --- |
| `theme_strength_report.md` | 最新主题排名、强势板块、个股主题暴露 Top20 |
| `theme_strength_latest.xlsx` | 最新主题强度、板块强度、映射、个股暴露和成分股快照 |
| `sector_research_summary.json` | 本次运行概要 |
| `sector_research_errors.csv` | 抓取或处理异常明细 |

### 4.10 合并到回测副本目录后的字段

执行 `scripts/build_sector_research_features.py` 后，会在指定 `--output-dir` 中生成股票 CSV 副本，并增加：

| 字段名 | 中文含义 | 类型/单位 | 缺失值处理 | 备注 |
| --- | --- | --- | --- | --- |
| `sector_theme_names` | 股票命中的主题集合 | 字符串 | 未命中为空 | 静态暴露字段 |
| `sector_subtheme_names` | 股票命中的子赛道集合 | 字符串 | 未命中为空 | |
| `sector_board_names` | 股票命中的板块集合 | 字符串 | 未命中为空 | |
| `sector_theme_count` | 命中主题数 | 个 | 未命中为空 | |
| `sector_subtheme_count` | 命中子赛道数 | 个 | 未命中为空 | |
| `sector_board_count` | 命中板块数 | 个 | 未命中为空 | |
| `sector_exposure_score` | 主题暴露分 | `0~1` | 未命中为空 | |
| `sector_strongest_theme` | 当日该股票命中主题中最强主题 | 字符串 | 无日线匹配为空 | 按 `theme_score` 取最大 |
| `sector_strongest_theme_rank` | 最强主题当日排名 | 正整数 | 为空则不可用 | 1 为最强 |
| `sector_strongest_theme_rank_pct` | 最强主题排名百分位 | `0~1` | 为空则不可用 | 越小越强 |
| `sector_strongest_theme_score` | 最强主题综合分 | `0~1` | 为空则不可用 | |
| `sector_strongest_theme_m5`、`sector_strongest_theme_m20`、`sector_strongest_theme_m60` | 最强主题动量 | 小数 | 为空则不可用 | |
| `sector_strongest_theme_amount_ratio_20` | 最强主题成交额放大倍数 | 倍 | 为空则不可用 | |
| `sector_strongest_theme_board_up_ratio` | 最强主题板块上涨比例 | `0~1` | 为空则不可用 | |
| `sector_strongest_theme_positive_m20_ratio` | 最强主题正动量板块比例 | `0~1` | 为空则不可用 | |
| `sector_strongest_board` | 最强主题内最强板块 | 字符串 | 为空则不可用 | |
| `sector_strongest_subtheme` | 最强主题内最强子赛道 | 字符串 | 为空则不可用 | |

输出目录还会生成 `sector_feature_manifest.csv`，记录每个股票文件是否命中板块主题。

## 5. 加工与清洗规则

1. 字段标准化：AKShare 返回的中文列名统一映射为英文列名。
2. 日期标准化：`YYYY-MM-DD` 转为 `YYYYMMDD`。
3. 股票代码标准化：提取数字并补齐为 6 位，例如 `1` 转为 `000001`。
4. 数值标准化：去掉 `%`、`,`，并将 `万`、`亿`、`万亿` 转为数值。
5. 重复处理：板块列表按 `board_type + board_name` 去重；成分股按 `board_type + board_name + stock_code + stock_name` 去重。
6. 缺失处理：关键名称为空的板块会剔除；数值无法解析时保留为空，不做填充。
7. 复权处理：板块指数直接使用 AKShare/东方财富返回口径，当前不做前复权或后复权调整。
8. 停牌处理：板块研究只处理板块指数和成分股快照，不单独判断个股停牌；真正买卖成交仍由当前回测系统的 `can_buy_open_t`、`can_sell_t` 等字段控制。
9. 资金流处理：资金流只合并到最新交易日；抓取失败会记录错误，不影响核心强度结果。

## 6. 使用注意事项

- 独立运行不会修改当前回测主数据。
- 合并脚本要求 `--output-dir` 与 `--processed-dir` 不同，防止覆盖原始处理后股票 CSV。
- 板块日线字段用同一 `trade_date` 对齐股票日线。当前系统的交易假设是 T 日收盘后生成信号、T+1 开盘买入，因此 T 日板块强度可以作为 T 日信号字段使用。
- 如果用于盘中或开盘前信号，必须把板块强度整体滞后一日，避免未来函数。
- 板块与个股映射来自最新成分股快照，不是历史成分股，回测很长区间时可能存在成分股幸存者偏差。第一阶段用于主题研究和辅助过滤，正式策略评估时要在报告里说明该限制。

## 7. 示例

独立生成板块研究数据：

```bash
python scripts/run_sector_research.py --start-date 20230101
```

生成增强后的股票 CSV 副本：

```bash
python scripts/build_sector_research_features.py \
  --processed-dir data_bundle/processed_qfq_theme_focus_top100 \
  --sector-processed-dir sector_research/data/processed \
  --output-dir data_bundle/processed_qfq_theme_focus_top100_sector
```

指标公式详见 `docs/sector-research-indicator-documentation.md`。

前端或回测条件示例：

```text
sector_strongest_theme_score>=0.65,sector_strongest_theme_rank_pct<=0.4,sector_exposure_score>0
```
