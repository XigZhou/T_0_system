# 板块看板 SQLite 数据字典

## 数据集概览

- 数据来源：`sector_research.pipeline.run_sector_research` 运行 AKShare 板块研究流程后，同步调用 `overnight_bt.sector_dashboard_store.upsert_sector_dashboard_rows` 写入 SQLite。
- 主库路径：默认 `data_store/market_data.sqlite`，可通过 `scripts/run_sector_research.py --market-db` 指定。
- 读取入口：`/api/sector/overview` 默认 `source=sqlite`，前端板块研究工作台默认只读 SQLite 主库。
- 数据粒度：按板块研究产物分组存储，主题强度和板块强度为日频，个股暴露和主题映射为快照，异常记录和摘要为运行级数据。
- 更新时间：每次运行 `scripts/run_sector_research.py` 或辅助研究调度时整组替换写入。
- SQLite-only 行为：旧 CSV 读取仅保留 `source=csv` 显式兼容入口；`T0_SQLITE_ONLY=1` 时会阻断旧 CSV 路径。

## 表：sector_dashboard_rows

用途：保存板块看板展示所需的行数据，避免看板依赖 `sector_research/data/processed` 或 `data_bundle` CSV。

主键：`dataset, row_key`。

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| dataset | TEXT | 数据集名称，取值包括 `theme_strength`、`board_strength`、`stock_exposure`、`mapping`、`errors`、`market_context`。 |
| row_key | TEXT | 行内顺序键，当前按写入顺序生成 `0000000000` 这类字符串。 |
| position | INTEGER | 展示顺序。 |
| row_json | TEXT | 原始行 JSON，字段结构保持板块研究产物列名。 |
| updated_at | TEXT | 写入时间，格式 `YYYY-MM-DD HH:MM:SS`。 |

各 dataset 说明：

| dataset | 原 CSV 产物 | 粒度 | 主要字段 |
| --- | --- | --- | --- |
| theme_strength | `theme_strength_daily.csv` | 主题-交易日 | `trade_date`、`theme_name`、`theme_score`、`m5`、`m20`、`theme_rank`。 |
| board_strength | `sector_board_daily.csv` | 板块-交易日 | `trade_date`、`theme_name`、`board_name`、`theme_board_score`、`pct_chg`、`m20`。 |
| stock_exposure | `stock_theme_exposure.csv` | 个股快照 | `stock_code`、`stock_name`、`theme_names`、`board_names`、`exposure_score`。 |
| mapping | `theme_board_mapping.csv` | 主题-板块映射 | `theme_name`、`subtheme_name`、`board_type`、`board_code`、`board_name`。 |
| errors | `sector_research_errors.csv` | 运行异常记录 | `stage`、`board_type`、`board_name`、`error`。 |
| market_context | 原 `data_bundle/market_context.csv` 对应的大盘上下文 | 指数-交易日宽表 | `trade_date`、`sh_m20`、`hs300_m20`、`cyb_m20` 等。 |

缺失值处理：写入前将 Pandas 缺失值转为 JSON `null`；读取看板时再转换为前端可展示的空值，数值列按展示函数统一格式化。

复权或停牌处理：板块看板表只保存板块研究聚合结果和大盘上下文，不直接参与个股复权或停牌判断。个股行情、复权价格和交易限制仍由 `stock_daily_features` 主表维护。

## 表：sector_dashboard_meta

用途：保存板块看板运行摘要。

主键：`meta_key`。

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| meta_key | TEXT | 当前主要为 `summary`。 |
| value_json | TEXT | 摘要 JSON，包括 `latest_trade_date`、`mapping_count`、`board_daily_rows`、`theme_daily_rows`、`stock_exposure_rows`、`error_count`。 |
| updated_at | TEXT | 写入时间。 |

## 初始化建议

系统软重置后该表可以为空。板块页会返回 `status=empty` 并提示“SQLite 板块研究数据未初始化”。完成主行情和模拟账户初始化后，再运行板块研究采集即可填充看板数据。
