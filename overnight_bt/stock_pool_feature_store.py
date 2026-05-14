from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Literal

import pandas as pd

from .config import DEFAULT_INDEXES
from .processing import build_market_context_from_indexes, build_processed_frame, validate_processed_frame
from .stock_pool_templates import (
    DEFAULT_DB_PATH,
    DEFAULT_USERNAME,
    PROJECT_ROOT,
    _connect,
    _db_path,
    _symbol_to_ts_code,
    init_stock_pool_db,
    parse_stock_list,
)
from .utils import ensure_dir, latest_open_trade_date, load_env, normalize_date_text


StockPoolSource = Literal["active_templates", "template", "symbols", "all"]


@dataclass
class StockPoolFeatureUpdateConfig:
    source: StockPoolSource = "active_templates"
    job_type: str = "daily_update"
    username: str = DEFAULT_USERNAME
    template_name: str = ""
    symbols: Iterable[str] | None = None
    stock_text: str = ""
    start_date: str = "20220101"
    end_date: str = ""
    db_path: str | Path | None = None
    env_path: str | Path = PROJECT_ROOT / ".env"
    log_dir: str | Path = PROJECT_ROOT / "logs" / "stock_pool_template_update"
    force_full_rebuild: bool = False
    max_symbols: int = 0
    sleep_seconds: float = 0.2


@dataclass
class StockPoolSyncItem:
    symbol: str
    ts_code: str
    status: str
    start_date: str = ""
    end_date: str = ""
    rows_written: int = 0
    message: str = ""


@dataclass
class StockPoolSyncSummary:
    job_id: str
    job_type: str
    source: str
    username: str
    template_name: str
    status: str
    start_date: str
    end_date: str
    stock_count: int
    success_count: int
    failed_count: int
    skipped_count: int
    log_file: str
    item_csv: str
    summary_json: str
    message: str
    items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "source": self.source,
            "username": self.username,
            "template_name": self.template_name,
            "status": self.status,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "stock_count": self.stock_count,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "log_file": self.log_file,
            "item_csv": self.item_csv,
            "summary_json": self.summary_json,
            "message": self.message,
            "items": self.items,
        }


class TushareStockPoolDataSource:
    def __init__(self, env_path: str | Path = PROJECT_ROOT / ".env") -> None:
        import tushare as ts

        self.env_path = Path(env_path)
        token = load_env(self.env_path).get("TUSHARE_TOKEN", "").strip()
        if not token:
            raise ValueError(f"TUSHARE_TOKEN 为空，无法拉取股票池行情：{self.env_path}")
        self.pro = ts.pro_api(token)

    def latest_trade_date(self, end_date: str) -> str:
        return latest_open_trade_date(self.pro, end_date)

    def load_stock_basic(self) -> pd.DataFrame:
        frame = self.pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,list_date",
        )
        if frame is None or frame.empty:
            raise RuntimeError("Tushare stock_basic 返回空数据")
        return frame

    def load_daily_basic_snapshot(self, trade_date: str) -> pd.DataFrame:
        frame = self.pro.daily_basic(
            trade_date=trade_date,
            fields="ts_code,close,total_mv,turnover_rate_f,pe_ttm,pb",
        )
        if frame is None:
            return pd.DataFrame(columns=["ts_code", "total_mv", "turnover_rate_f"])
        return frame

    def load_trade_calendar(self, start_date: str, end_date: str) -> pd.DataFrame:
        frame = self.pro.trade_cal(
            exchange="",
            start_date=start_date,
            end_date=end_date,
            is_open="1",
            fields="exchange,cal_date,is_open,pretrade_date",
        )
        if frame is None or frame.empty:
            raise RuntimeError(f"Tushare trade_cal 返回空数据：{start_date}-{end_date}")
        frame = frame.rename(columns={"cal_date": "trade_date"})
        return frame

    def load_market_context(self, start_date: str, end_date: str) -> pd.DataFrame:
        index_frames: dict[str, pd.DataFrame] = {}
        for alias, ts_code, _ in DEFAULT_INDEXES:
            frame = self.pro.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if frame is None or frame.empty:
                raise RuntimeError(f"Tushare index_daily 返回空数据：{ts_code}")
            index_frames[alias] = frame
        return build_market_context_from_indexes(index_frames)

    def load_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        frame = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        return frame if frame is not None else pd.DataFrame()

    def load_adj_factor(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        frame = self.pro.adj_factor(ts_code=ts_code, start_date=start_date, end_date=end_date)
        return frame if frame is not None else pd.DataFrame()

    def load_stk_limit(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        frame = self.pro.stk_limit(ts_code=ts_code, start_date=start_date, end_date=end_date)
        return frame if frame is not None else pd.DataFrame(columns=["ts_code", "trade_date", "up_limit", "down_limit"])

    def load_suspend_d(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        frame = self.pro.suspend_d(ts_code=ts_code, start_date=start_date, end_date=end_date)
        return frame if frame is not None else pd.DataFrame(columns=["ts_code", "trade_date", "suspend_type", "suspend_timing"])


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today_text() -> str:
    return datetime.now().strftime("%Y%m%d")


def _normalize_date(value: str, default: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return default
    return normalize_date_text(text)


def _setup_logger(log_dir: Path, job_id: str) -> tuple[logging.Logger, Path]:
    ensure_dir(log_dir)
    log_file = log_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{job_id}.log"
    logger = logging.getLogger(f"stock_pool_feature_store.{job_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger, log_file


def _normalize_symbol_rows_from_text(stock_text: str, symbols: Iterable[str] | None = None) -> list[dict[str, str]]:
    chunks: list[str] = []
    if stock_text:
        chunks.append(stock_text)
    if symbols:
        chunks.extend(str(item) for item in symbols)
    parsed = parse_stock_list("\n".join(chunks))
    if parsed.invalid_items:
        raise ValueError(f"股票代码格式错误：{', '.join(parsed.invalid_items[:10])}")
    return [
        {"symbol": row["symbol"], "ts_code": row["ts_code"], "name": row.get("stock_name", "")}
        for row in parsed.valid_stocks
    ]


def _rows_from_stock_basic_frame(frame: pd.DataFrame) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if frame is None or frame.empty:
        return rows
    for row in frame.to_dict(orient="records"):
        symbol = str(row.get("symbol") or row.get("ts_code") or "").strip()[:6].zfill(6)
        if not symbol.isdigit() or len(symbol) != 6:
            continue
        rows.append(
            {
                "symbol": symbol,
                "ts_code": str(row.get("ts_code") or _symbol_to_ts_code(symbol)).strip(),
                "name": str(row.get("name") or "").strip(),
                "industry": str(row.get("industry") or "").strip(),
                "market": str(row.get("market") or "").strip(),
                "list_date": _normalize_date(str(row.get("list_date") or "")),
            }
        )
    rows.sort(key=lambda item: item["symbol"])
    return rows


def _upsert_stock_basic(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    now = _now_text()
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().zfill(6)
        if not symbol or not symbol.isdigit():
            continue
        conn.execute(
            """
            INSERT INTO stock_basic(symbol, ts_code, name, industry, market, list_date, is_active, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                ts_code=COALESCE(NULLIF(excluded.ts_code, ''), stock_basic.ts_code),
                name=COALESCE(NULLIF(excluded.name, ''), stock_basic.name),
                industry=COALESCE(NULLIF(excluded.industry, ''), stock_basic.industry),
                market=COALESCE(NULLIF(excluded.market, ''), stock_basic.market),
                list_date=COALESCE(NULLIF(excluded.list_date, ''), stock_basic.list_date),
                is_active=excluded.is_active,
                updated_at=excluded.updated_at
            """,
            (
                symbol,
                str(row.get("ts_code") or _symbol_to_ts_code(symbol)).strip(),
                str(row.get("name") or "").strip(),
                str(row.get("industry") or "").strip(),
                str(row.get("market") or "").strip(),
                _normalize_date(str(row.get("list_date") or "")),
                now,
            ),
        )


def _load_active_template_rows(
    conn: sqlite3.Connection,
    username: str,
    template_name: str = "",
) -> list[dict[str, str]]:
    params: list[Any] = []
    where = ["t.is_active=1"]
    if username:
        where.append("t.username=?")
        params.append(username)
    if template_name:
        where.append("t.template_name=?")
        params.append(template_name)
    rows = conn.execute(
        f"""
        SELECT DISTINCT
            s.symbol AS symbol,
            COALESCE(NULLIF(b.ts_code, ''), s.ts_code) AS ts_code,
            COALESCE(NULLIF(b.name, ''), s.stock_name, '') AS name,
            COALESCE(b.industry, '') AS industry,
            COALESCE(b.market, '') AS market,
            COALESCE(b.list_date, '') AS list_date
        FROM stock_pool_template_stocks s
        JOIN stock_pool_templates t
            ON t.username=s.username AND t.template_name=s.template_name
        LEFT JOIN stock_basic b ON b.symbol=s.symbol
        WHERE {' AND '.join(where)}
        ORDER BY s.symbol
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _resolve_symbol_rows(
    conn: sqlite3.Connection,
    config: StockPoolFeatureUpdateConfig,
    data_source: Any,
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    source = config.source
    username = str(config.username or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME
    if source == "symbols":
        rows = _normalize_symbol_rows_from_text(config.stock_text, config.symbols)
    elif source == "template":
        template_name = str(config.template_name or "").strip()
        if not template_name:
            raise ValueError("source=template 时 template_name 不能为空")
        rows = _load_active_template_rows(conn, username=username, template_name=template_name)
    elif source == "active_templates":
        rows = _load_active_template_rows(conn, username=username)
    elif source == "all":
        logger.info("读取 Tushare stock_basic 作为全市场初始化股票范围")
        rows = _rows_from_stock_basic_frame(data_source.load_stock_basic())
        _upsert_stock_basic(conn, rows)
    else:
        raise ValueError(f"未知股票池数据来源：{source}")

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().zfill(6)
        if not symbol.isdigit() or len(symbol) != 6:
            continue
        item = dict(row)
        item["symbol"] = symbol
        item["ts_code"] = str(item.get("ts_code") or _symbol_to_ts_code(symbol)).strip()
        deduped.setdefault(symbol, item)
    resolved = list(deduped.values())
    resolved.sort(key=lambda item: item["symbol"])
    if config.max_symbols and config.max_symbols > 0:
        logger.info("只处理前 %s 只股票，用于测试或分批补数", config.max_symbols)
        resolved = resolved[: config.max_symbols]
    return resolved


def _build_stock_basic_map(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for row in _rows_from_stock_basic_frame(frame):
        mapping[row["symbol"]] = row
    return mapping


def _build_daily_basic_map(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    if frame is None or frame.empty:
        return mapping
    for row in frame.to_dict(orient="records"):
        ts_code = str(row.get("ts_code") or "").strip()
        if not ts_code:
            continue
        mapping[ts_code] = row
    return mapping


def _snapshot_row(
    symbol_row: dict[str, Any],
    stock_basic_map: dict[str, dict[str, Any]],
    daily_basic_map: dict[str, dict[str, Any]],
) -> pd.Series:
    symbol = str(symbol_row.get("symbol") or "").strip().zfill(6)
    ts_code = str(symbol_row.get("ts_code") or _symbol_to_ts_code(symbol)).strip()
    basic = stock_basic_map.get(symbol, {})
    daily_basic = daily_basic_map.get(ts_code, {})
    return pd.Series(
        {
            "ts_code": ts_code,
            "symbol": symbol,
            "name": str(basic.get("name") or symbol_row.get("name") or "").strip(),
            "industry": str(basic.get("industry") or symbol_row.get("industry") or "").strip(),
            "market": str(basic.get("market") or symbol_row.get("market") or "").strip(),
            "list_date": str(basic.get("list_date") or symbol_row.get("list_date") or "").strip(),
            "total_mv": daily_basic.get("total_mv"),
            "turnover_rate_f": daily_basic.get("turnover_rate_f"),
        }
    )


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row["name"]) for row in rows]


def _coerce_db_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, bool):
        return int(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _upsert_feature_frame(conn: sqlite3.Connection, frame: pd.DataFrame) -> int:
    now = _now_text()
    table_cols = _table_columns(conn, "stock_daily_features")
    work = frame.copy()
    work["created_at"] = now
    work["updated_at"] = now
    for col in ["is_suspended_t", "can_buy_t", "can_buy_open_t", "can_sell_t", "can_sell_t1"]:
        if col in work.columns:
            work[col] = work[col].astype("boolean").astype("Int64")
    cols = [col for col in table_cols if col in work.columns]
    if "symbol" not in cols or "trade_date" not in cols:
        raise ValueError("stock_daily_features 入库数据缺少 symbol/trade_date")
    placeholders = ", ".join("?" for _ in cols)
    update_cols = [col for col in cols if col not in {"symbol", "trade_date", "created_at"}]
    updates = ", ".join(f"{col}=excluded.{col}" for col in update_cols)
    sql = f"""
        INSERT INTO stock_daily_features({', '.join(cols)})
        VALUES({placeholders})
        ON CONFLICT(symbol, trade_date) DO UPDATE SET {updates}
    """
    records = [tuple(_coerce_db_value(row.get(col)) for col in cols) for row in work.to_dict(orient="records")]
    if records:
        conn.executemany(sql, records)
    return len(records)


def _latest_dates(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        "SELECT symbol, MAX(trade_date) AS latest_trade_date FROM stock_daily_features GROUP BY symbol"
    ).fetchall()
    return {str(row["symbol"]): str(row["latest_trade_date"] or "") for row in rows}


def _create_job(
    conn: sqlite3.Connection,
    config: StockPoolFeatureUpdateConfig,
    job_id: str,
    stock_count: int,
    end_date: str,
) -> None:
    now = _now_text()
    conn.execute(
        """
        INSERT INTO stock_pool_update_jobs(
            job_id, job_type, username, template_name, status, start_date, end_date,
            stock_count, success_count, failed_count, message, created_at, started_at, finished_at
        ) VALUES(?, ?, ?, ?, 'running', ?, ?, ?, 0, 0, '', ?, ?, '')
        """,
        (
            job_id,
            config.job_type,
            str(config.username or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME,
            str(config.template_name or "").strip(),
            config.start_date,
            end_date,
            stock_count,
            now,
            now,
        ),
    )


def _write_job_item(conn: sqlite3.Connection, job_id: str, item: StockPoolSyncItem) -> None:
    conn.execute(
        """
        INSERT INTO stock_pool_update_job_items(job_id, symbol, status, start_date, end_date, rows_written, message)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id, symbol) DO UPDATE SET
            status=excluded.status,
            start_date=excluded.start_date,
            end_date=excluded.end_date,
            rows_written=excluded.rows_written,
            message=excluded.message
        """,
        (job_id, item.symbol, item.status, item.start_date, item.end_date, item.rows_written, item.message),
    )


def _finish_job(
    conn: sqlite3.Connection,
    job_id: str,
    status: str,
    success_count: int,
    failed_count: int,
    message: str,
) -> None:
    conn.execute(
        """
        UPDATE stock_pool_update_jobs
        SET status=?, success_count=?, failed_count=?, message=?, finished_at=?
        WHERE job_id=?
        """,
        (status, success_count, failed_count, message, _now_text(), job_id),
    )


def _write_runtime_outputs(log_dir: Path, job_id: str, summary: dict[str, Any], items: list[dict[str, Any]]) -> tuple[Path, Path]:
    ensure_dir(log_dir)
    item_csv = log_dir / f"{job_id}_items.csv"
    summary_json = log_dir / f"{job_id}_summary.json"
    pd.DataFrame(items).to_csv(item_csv, index=False, encoding="utf-8-sig")
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return item_csv, summary_json


def run_stock_pool_feature_update(
    config: StockPoolFeatureUpdateConfig,
    data_source: Any | None = None,
) -> dict[str, Any]:
    db_path = _db_path(config.db_path or DEFAULT_DB_PATH)
    init_stock_pool_db(db_path)
    log_dir = Path(config.log_dir)
    if not log_dir.is_absolute():
        log_dir = PROJECT_ROOT / log_dir
    job_id = str(uuid.uuid4())
    logger, log_file = _setup_logger(log_dir, job_id)

    start_date = _normalize_date(config.start_date, default="20220101")
    as_of = _normalize_date(config.end_date, default=_today_text())
    config.start_date = start_date
    if data_source is None:
        data_source = TushareStockPoolDataSource(config.env_path)
    end_date = data_source.latest_trade_date(as_of) if hasattr(data_source, "latest_trade_date") else as_of
    end_date = _normalize_date(end_date, default=as_of)

    items: list[StockPoolSyncItem] = []
    logger.info(
        "股票池数据任务启动：job_id=%s source=%s job_type=%s start=%s end=%s db=%s",
        job_id,
        config.source,
        config.job_type,
        start_date,
        end_date,
        db_path,
    )

    with _connect(db_path) as conn:
        symbol_rows = _resolve_symbol_rows(conn, config, data_source, logger)
        _create_job(conn, config, job_id, len(symbol_rows), end_date)
        if not symbol_rows:
            message = "没有需要处理的股票；请先保存股票池模板或指定股票代码。"
            _finish_job(conn, job_id, "success", 0, 0, message)
            summary_base = {
                "job_id": job_id,
                "status": "success",
                "message": message,
                "stock_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "log_file": str(log_file),
            }
            item_csv, summary_json = _write_runtime_outputs(log_dir, job_id, summary_base, [])
            summary_base.update({"item_csv": str(item_csv), "summary_json": str(summary_json), "items": []})
            logger.info(message)
            return summary_base

        logger.info("本次去重后股票数：%s", len(symbol_rows))
        try:
            stock_basic_frame = data_source.load_stock_basic()
            stock_basic_rows = _rows_from_stock_basic_frame(stock_basic_frame)
            _upsert_stock_basic(conn, stock_basic_rows)
            stock_basic_map = _build_stock_basic_map(stock_basic_frame)
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取 stock_basic 失败，将使用模板内基础信息继续：%s", exc)
            stock_basic_map = {row["symbol"]: row for row in symbol_rows}

        daily_basic_map = _build_daily_basic_map(data_source.load_daily_basic_snapshot(end_date))
        trade_calendar = data_source.load_trade_calendar(start_date, end_date)
        market_context = data_source.load_market_context(start_date, end_date)
        latest_map = _latest_dates(conn)

        for index, symbol_row in enumerate(symbol_rows, start=1):
            symbol = str(symbol_row["symbol"]).zfill(6)
            ts_code = str(symbol_row.get("ts_code") or _symbol_to_ts_code(symbol)).strip()
            latest = latest_map.get(symbol, "")
            logger.info("[%s/%s] 处理 %s %s，库内最新=%s", index, len(symbol_rows), symbol, ts_code, latest or "无")
            if latest and latest >= end_date and not config.force_full_rebuild:
                item = StockPoolSyncItem(
                    symbol=symbol,
                    ts_code=ts_code,
                    status="skipped",
                    start_date="",
                    end_date=end_date,
                    rows_written=0,
                    message=f"已更新到 {latest}，无需重复采集",
                )
                _write_job_item(conn, job_id, item)
                items.append(item)
                logger.info("%s 跳过：%s", symbol, item.message)
                continue

            try:
                raw_df = data_source.load_daily(ts_code, start_date, end_date)
                if raw_df is None or raw_df.empty:
                    raise RuntimeError(f"daily 返回空数据：{ts_code}")
                adj_df = data_source.load_adj_factor(ts_code, start_date, end_date)
                if adj_df is None or adj_df.empty:
                    raise RuntimeError(f"adj_factor 返回空数据：{ts_code}")
                limit_df = data_source.load_stk_limit(ts_code, start_date, end_date)
                suspend_df = data_source.load_suspend_d(ts_code, start_date, end_date)
                frame = build_processed_frame(
                    raw_df=raw_df,
                    adj_df=adj_df,
                    snapshot_row=_snapshot_row(symbol_row, stock_basic_map, daily_basic_map),
                    trade_calendar=trade_calendar,
                    limit_df=limit_df,
                    suspend_df=suspend_df,
                    market_context=market_context,
                    start_date=start_date,
                    end_date=end_date,
                )
                validate_processed_frame(frame)
                rows_written = _upsert_feature_frame(conn, frame)
                item = StockPoolSyncItem(
                    symbol=symbol,
                    ts_code=ts_code,
                    status="success",
                    start_date=start_date,
                    end_date=end_date,
                    rows_written=rows_written,
                    message="行情与指标已入库",
                )
                _write_job_item(conn, job_id, item)
                items.append(item)
                logger.info("%s 完成：upsert %s 行", symbol, rows_written)
                if config.sleep_seconds > 0:
                    time.sleep(config.sleep_seconds)
            except Exception as exc:  # noqa: BLE001
                item = StockPoolSyncItem(
                    symbol=symbol,
                    ts_code=ts_code,
                    status="failed",
                    start_date=start_date,
                    end_date=end_date,
                    rows_written=0,
                    message=str(exc)[:1000],
                )
                _write_job_item(conn, job_id, item)
                items.append(item)
                logger.exception("%s 失败：%s", symbol, exc)

        item_dicts = [item.__dict__ for item in items]
        failed_count = sum(1 for item in items if item.status == "failed")
        skipped_count = sum(1 for item in items if item.status == "skipped")
        success_count = len(items) - failed_count
        status = "success" if failed_count == 0 else "failed"
        message = f"处理 {len(items)} 只股票，成功/跳过 {success_count} 只，失败 {failed_count} 只，跳过 {skipped_count} 只。"
        _finish_job(conn, job_id, status, success_count, failed_count, message)

    summary_obj = StockPoolSyncSummary(
        job_id=job_id,
        job_type=config.job_type,
        source=config.source,
        username=str(config.username or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME,
        template_name=str(config.template_name or "").strip(),
        status=status,
        start_date=start_date,
        end_date=end_date,
        stock_count=len(items),
        success_count=success_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        log_file=str(log_file),
        item_csv="",
        summary_json="",
        message=message,
        items=item_dicts,
    )
    summary = summary_obj.to_dict()
    item_csv, summary_json = _write_runtime_outputs(log_dir, job_id, summary, item_dicts)
    summary["item_csv"] = str(item_csv)
    summary["summary_json"] = str(summary_json)
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(message)
    logger.info("任务输出：items=%s summary=%s log=%s", item_csv, summary_json, log_file)
    return summary


def list_stock_pool_update_jobs(
    limit: int = 50,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    init_stock_pool_db(db_path)
    safe_limit = max(1, min(int(limit or 50), 500))
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM stock_pool_update_jobs
            ORDER BY COALESCE(started_at, created_at) DESC, created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def read_stock_pool_update_job(
    job_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_stock_pool_db(db_path)
    clean_job_id = str(job_id or "").strip()
    if not clean_job_id:
        raise ValueError("job_id 不能为空")
    with _connect(db_path) as conn:
        job = conn.execute("SELECT * FROM stock_pool_update_jobs WHERE job_id=?", (clean_job_id,)).fetchone()
        if job is None:
            raise FileNotFoundError(f"股票池数据任务不存在：{clean_job_id}")
        items = conn.execute(
            """
            SELECT * FROM stock_pool_update_job_items
            WHERE job_id=?
            ORDER BY symbol
            """,
            (clean_job_id,),
        ).fetchall()
        data = dict(job)
        data["items"] = [dict(row) for row in items]
        return data
