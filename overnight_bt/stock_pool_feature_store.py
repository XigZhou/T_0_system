from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Literal

import pandas as pd

from .config import DEFAULT_INDEXES
from .main_universe import DEFAULT_DB_PATH as DEFAULT_MARKET_DB_PATH, list_main_universe, ts_code_from_symbol
from .market_data_store import upsert_feature_rows
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


StockPoolSource = Literal["active_templates", "template", "symbols", "all", "main_universe"]


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
    market_db_path: str | Path | None = None
    env_path: str | Path = PROJECT_ROOT / ".env"
    log_dir: str | Path = PROJECT_ROOT / "logs" / "stock_pool_template_update"
    force_full_rebuild: bool = False
    max_symbols: int = 0
    sleep_seconds: float = 0.2
    batch_size: int = 0
    batch_index: int = 0
    offset: int = 0
    resume_after_symbol: str = ""
    retry_attempts: int = 1
    retry_sleep_seconds: float = 2.0
    only_missing: bool = True


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
    resolved_stock_count: int = 0
    due_stock_count: int = 0
    prefilter_skipped_count: int = 0
    selected_stock_count: int = 0
    resume_skipped_count: int = 0
    batch_start: int = 0
    batch_end: int = 0
    batch_size: int = 0
    batch_index: int = 0
    offset: int = 0
    resume_after_symbol: str = ""
    retry_attempts: int = 1
    retry_sleep_seconds: float = 0.0
    only_missing: bool = True
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
            "resolved_stock_count": self.resolved_stock_count,
            "due_stock_count": self.due_stock_count,
            "prefilter_skipped_count": self.prefilter_skipped_count,
            "selected_stock_count": self.selected_stock_count,
            "resume_skipped_count": self.resume_skipped_count,
            "batch_start": self.batch_start,
            "batch_end": self.batch_end,
            "batch_size": self.batch_size,
            "batch_index": self.batch_index,
            "offset": self.offset,
            "resume_after_symbol": self.resume_after_symbol,
            "retry_attempts": self.retry_attempts,
            "retry_sleep_seconds": self.retry_sleep_seconds,
            "only_missing": self.only_missing,
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


def _lookback_start_date(start_date: str, calendar_days: int = 260) -> str:
    parsed = datetime.strptime(start_date, "%Y%m%d")
    return (parsed - timedelta(days=calendar_days)).strftime("%Y%m%d")


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


def _load_active_main_universe_rows(market_db_path: str | Path | None = None) -> list[dict[str, Any]]:
    rows = list_main_universe(db_path=market_db_path or DEFAULT_MARKET_DB_PATH, include_inactive=False)
    result: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().zfill(6)
        if not symbol.isdigit() or len(symbol) != 6:
            continue
        result.append(
            {
                "symbol": symbol,
                "ts_code": str(row.get("ts_code") or "").strip() or ts_code_from_symbol(symbol),
                "name": str(row.get("name") or "").strip(),
                "industry": str(row.get("industry") or "").strip(),
                "market": str(row.get("market") or "").strip(),
                "list_date": str(row.get("list_date") or "").strip(),
            }
        )
    return result


def _stock_basic_rows_from_symbol_rows(symbol_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in symbol_rows:
        symbol = str(row.get("symbol") or "").strip().zfill(6)
        if not symbol.isdigit() or len(symbol) != 6:
            continue
        rows.append(
            {
                "symbol": symbol,
                "ts_code": str(row.get("ts_code") or "").strip() or ts_code_from_symbol(symbol),
                "name": str(row.get("name") or "").strip(),
                "industry": str(row.get("industry") or "").strip(),
                "market": str(row.get("market") or "").strip(),
                "list_date": str(row.get("list_date") or "").strip(),
            }
        )
    return rows


def _is_main_universe_source(source: str) -> bool:
    return source in {"all", "main_universe"}


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
    market_db_path: str | Path | None = None,
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
    elif source == "main_universe":
        logger.info("读取主股票池作为股票范围")
        rows = _load_active_main_universe_rows(market_db_path)
    elif source == "all":
        logger.info("source=all 已映射为主股票池范围，不再代表全市场股票")
        rows = _load_active_main_universe_rows(market_db_path)
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


def _upsert_market_feature_frame(frame: pd.DataFrame, db_path: str | Path | None) -> int:
    if db_path is None:
        return 0
    records = [
        {key: _coerce_db_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]
    result = upsert_feature_rows(records, db_path=db_path)
    return int(result.get("rows_written", 0) or 0)


def _resolve_market_db_path(
    stock_pool_db_path: str | Path,
    configured_market_db_path: str | Path | None,
) -> Path | None:
    if configured_market_db_path is not None:
        path = Path(configured_market_db_path)
        return path if path.is_absolute() else PROJECT_ROOT / path
    if Path(stock_pool_db_path).resolve() == _db_path(DEFAULT_DB_PATH).resolve():
        return DEFAULT_MARKET_DB_PATH
    return None


def _latest_dates(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT symbol, MAX(trade_date) AS latest_trade_date
        FROM stock_daily_features
        WHERE raw_close IS NOT NULL AND raw_close>0
            AND close IS NOT NULL AND close>0
        GROUP BY symbol
        """
    ).fetchall()
    return {str(row["symbol"]): str(row["latest_trade_date"] or "") for row in rows}


def _positive_int(value: Any, default: int = 0) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return default
    return max(number, 0)


def _positive_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value or 0.0)
    except (TypeError, ValueError):
        return default
    return max(number, 0.0)


def _filter_due_symbol_rows(
    symbol_rows: list[dict[str, Any]],
    latest_map: dict[str, str],
    end_date: str,
    config: StockPoolFeatureUpdateConfig,
    logger: logging.Logger,
) -> tuple[list[dict[str, Any]], int]:
    if config.force_full_rebuild or not config.only_missing:
        return list(symbol_rows), 0
    due_rows: list[dict[str, Any]] = []
    skipped_count = 0
    for row in symbol_rows:
        symbol = str(row.get("symbol") or "").strip().zfill(6)
        latest = latest_map.get(symbol, "")
        if latest and latest >= end_date:
            skipped_count += 1
            continue
        due_rows.append(row)
    if skipped_count:
        logger.info("只补缺失模式：%s 只股票已更新到 %s 或之后，任务前置跳过", skipped_count, end_date)
    return due_rows, skipped_count


def _apply_batch_window(
    symbol_rows: list[dict[str, Any]],
    config: StockPoolFeatureUpdateConfig,
    logger: logging.Logger,
) -> tuple[list[dict[str, Any]], dict[str, int | str]]:
    rows = list(symbol_rows)
    resume_after_symbol = str(config.resume_after_symbol or "").strip()
    if resume_after_symbol:
        resume_after_symbol = resume_after_symbol.split(".", 1)[0].zfill(6)
    resume_skipped = 0
    if resume_after_symbol:
        next_rows: list[dict[str, Any]] = []
        found = False
        for row in rows:
            symbol = str(row.get("symbol") or "").strip().zfill(6)
            if found:
                next_rows.append(row)
                continue
            resume_skipped += 1
            if symbol == resume_after_symbol:
                found = True
        if found:
            rows = next_rows
            logger.info("断点续跑：跳过到 %s 之后，实际跳过 %s 只", resume_after_symbol, resume_skipped)
        else:
            logger.warning("断点续跑股票 %s 不在待处理列表内，本批次为空", resume_after_symbol)
            resume_skipped = len(symbol_rows)
            rows = []
    batch_size = _positive_int(config.batch_size)
    batch_index = _positive_int(config.batch_index)
    offset = _positive_int(config.offset)
    if batch_size > 0:
        start = offset if offset > 0 else batch_index * batch_size
        end = start + batch_size
        selected = rows[start:end]
        logger.info("批次窗口：batch_size=%s batch_index=%s offset=%s，选择 [%s, %s) 共 %s 只", batch_size, batch_index, offset, start, end, len(selected))
    else:
        start = offset
        selected = rows[offset:] if offset > 0 else rows
        end = start + len(selected)
        if offset > 0:
            logger.info("偏移窗口：offset=%s，选择 %s 只", offset, len(selected))
    max_symbols = _positive_int(config.max_symbols)
    if max_symbols > 0 and len(selected) > max_symbols:
        logger.info("max_symbols=%s，仅保留当前窗口前 %s 只用于测试或限流", max_symbols, max_symbols)
        selected = selected[:max_symbols]
        end = start + len(selected)
    meta: dict[str, int | str] = {
        "resume_skipped_count": resume_skipped,
        "batch_start": start,
        "batch_end": end,
        "batch_size": batch_size,
        "batch_index": batch_index,
        "offset": offset,
        "resume_after_symbol": resume_after_symbol,
    }
    return selected, meta


def _call_with_retry(
    label: str,
    func: Any,
    logger: logging.Logger,
    retry_attempts: int,
    retry_sleep_seconds: float,
) -> Any:
    attempts = max(1, _positive_int(retry_attempts, default=1))
    sleep_seconds = _positive_float(retry_sleep_seconds)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= attempts:
                break
            wait_seconds = sleep_seconds * attempt
            logger.warning("%s 第 %s/%s 次失败：%s；%.2f 秒后重试", label, attempt, attempts, exc, wait_seconds)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{label} 调用失败")


def _load_symbol_inputs_with_retry(
    data_source: Any,
    ts_code: str,
    start_date: str,
    end_date: str,
    logger: logging.Logger,
    retry_attempts: int,
    retry_sleep_seconds: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    def load_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        raw_df = data_source.load_daily(ts_code, start_date, end_date)
        if raw_df is None or raw_df.empty:
            raise RuntimeError(f"daily 返回空数据：{ts_code}")
        adj_df = data_source.load_adj_factor(ts_code, start_date, end_date)
        if adj_df is None or adj_df.empty:
            raise RuntimeError(f"adj_factor 返回空数据：{ts_code}")
        limit_df = data_source.load_stk_limit(ts_code, start_date, end_date)
        suspend_df = data_source.load_suspend_d(ts_code, start_date, end_date)
        return raw_df, adj_df, limit_df, suspend_df

    return _call_with_retry(
        f"{ts_code} 行情输入",
        load_all,
        logger,
        retry_attempts=retry_attempts,
        retry_sleep_seconds=retry_sleep_seconds,
    )


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


def _set_job_output_paths(
    conn: sqlite3.Connection,
    job_id: str,
    log_file: str | Path,
    item_csv: str | Path,
    summary_json: str | Path,
) -> None:
    conn.execute(
        """
        UPDATE stock_pool_update_jobs
        SET log_file=?, item_csv=?, summary_json=?
        WHERE job_id=?
        """,
        (str(log_file), str(item_csv), str(summary_json), job_id),
    )


def _write_runtime_outputs(log_dir: Path, job_id: str, summary: dict[str, Any], items: list[dict[str, Any]]) -> tuple[Path, Path]:
    ensure_dir(log_dir)
    item_csv = log_dir / f"{job_id}_items.csv"
    summary_json = log_dir / f"{job_id}_summary.json"
    pd.DataFrame(items).to_csv(item_csv, index=False, encoding="utf-8-sig")
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return item_csv, summary_json


def _empty_summary(
    config: StockPoolFeatureUpdateConfig,
    job_id: str,
    log_file: Path,
    start_date: str,
    end_date: str,
    message: str,
    counts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    counts = counts or {}
    summary_base = {
        "job_id": job_id,
        "job_type": config.job_type,
        "source": config.source,
        "username": str(config.username or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME,
        "template_name": str(config.template_name or "").strip(),
        "status": "success",
        "start_date": start_date,
        "end_date": end_date,
        "stock_count": 0,
        "success_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "log_file": str(log_file),
        "item_csv": "",
        "summary_json": "",
        "message": message,
        "resolved_stock_count": int(counts.get("resolved_stock_count", 0) or 0),
        "due_stock_count": int(counts.get("due_stock_count", 0) or 0),
        "prefilter_skipped_count": int(counts.get("prefilter_skipped_count", 0) or 0),
        "selected_stock_count": 0,
        "resume_skipped_count": int(counts.get("resume_skipped_count", 0) or 0),
        "batch_start": int(counts.get("batch_start", 0) or 0),
        "batch_end": int(counts.get("batch_end", 0) or 0),
        "batch_size": int(counts.get("batch_size", 0) or 0),
        "batch_index": int(counts.get("batch_index", 0) or 0),
        "offset": int(counts.get("offset", 0) or 0),
        "resume_after_symbol": str(counts.get("resume_after_symbol", "") or ""),
        "retry_attempts": max(1, _positive_int(config.retry_attempts, default=1)),
        "retry_sleep_seconds": _positive_float(config.retry_sleep_seconds),
        "only_missing": bool(config.only_missing),
    }
    return summary_base


def run_stock_pool_feature_update(
    config: StockPoolFeatureUpdateConfig,
    data_source: Any | None = None,
) -> dict[str, Any]:
    db_path = _db_path(config.db_path or DEFAULT_DB_PATH)
    market_db_path = _resolve_market_db_path(db_path, config.market_db_path)
    init_stock_pool_db(db_path)
    log_dir = Path(config.log_dir)
    if not log_dir.is_absolute():
        log_dir = PROJECT_ROOT / log_dir
    job_id = str(uuid.uuid4())
    logger, log_file = _setup_logger(log_dir, job_id)

    start_date = _normalize_date(config.start_date, default="20220101")
    as_of = _normalize_date(config.end_date, default=_today_text())
    fetch_start_date = _lookback_start_date(start_date)
    config.start_date = start_date
    config.retry_attempts = max(1, _positive_int(config.retry_attempts, default=1))
    config.retry_sleep_seconds = _positive_float(config.retry_sleep_seconds)
    config.batch_size = _positive_int(config.batch_size)
    config.batch_index = _positive_int(config.batch_index)
    config.offset = _positive_int(config.offset)
    config.max_symbols = _positive_int(config.max_symbols)
    if data_source is None:
        data_source = TushareStockPoolDataSource(config.env_path)
    end_date = data_source.latest_trade_date(as_of) if hasattr(data_source, "latest_trade_date") else as_of
    end_date = _normalize_date(end_date, default=as_of)

    items: list[StockPoolSyncItem] = []
    logger.info(
        "股票池数据任务启动：job_id=%s source=%s job_type=%s start=%s fetch_start=%s end=%s db=%s market_db=%s only_missing=%s batch_size=%s batch_index=%s offset=%s resume_after=%s retry=%s",
        job_id,
        config.source,
        config.job_type,
        start_date,
        fetch_start_date,
        end_date,
        db_path,
        market_db_path or "",
        config.only_missing,
        config.batch_size,
        config.batch_index,
        config.offset,
        config.resume_after_symbol or "",
        config.retry_attempts,
    )

    counts: dict[str, Any] = {}
    with _connect(db_path) as conn:
        resolved_rows = _resolve_symbol_rows(conn, config, data_source, logger, market_db_path=market_db_path)
        counts["resolved_stock_count"] = len(resolved_rows)
        if not resolved_rows:
            _create_job(conn, config, job_id, 0, end_date)
            message = "没有需要处理的股票；请先保存股票池模板或指定股票代码。"
            _finish_job(conn, job_id, "success", 0, 0, message)
            summary_base = _empty_summary(config, job_id, log_file, start_date, end_date, message, counts)
            item_csv, summary_json = _write_runtime_outputs(log_dir, job_id, summary_base, [])
            summary_base.update({"item_csv": str(item_csv), "summary_json": str(summary_json), "items": []})
            summary_json.write_text(json.dumps(summary_base, ensure_ascii=False, indent=2), encoding="utf-8")
            _set_job_output_paths(conn, job_id, log_file, item_csv, summary_json)
            logger.info(message)
            return summary_base

        logger.info("本次解析去重后股票数：%s", len(resolved_rows))
        latest_map = _latest_dates(conn)
        due_rows, prefilter_skipped_count = _filter_due_symbol_rows(
            resolved_rows,
            latest_map=latest_map,
            end_date=end_date,
            config=config,
            logger=logger,
        )
        window_rows, batch_meta = _apply_batch_window(resolved_rows, config, logger)
        if config.only_missing and not config.force_full_rebuild:
            selected_rows = [
                row for row in window_rows
                if not latest_map.get(str(row.get("symbol") or "").strip().zfill(6), "")
                or latest_map.get(str(row.get("symbol") or "").strip().zfill(6), "") < end_date
            ]
            skipped_in_window = len(window_rows) - len(selected_rows)
            if skipped_in_window:
                logger.info("当前批次内 %s 只股票已更新到 %s 或之后，跳过采集", skipped_in_window, end_date)
        else:
            selected_rows = window_rows
        counts.update(batch_meta)
        counts["due_stock_count"] = len(due_rows)
        counts["prefilter_skipped_count"] = prefilter_skipped_count
        counts["selected_stock_count"] = len(selected_rows)

        _create_job(conn, config, job_id, len(selected_rows), end_date)
        if not selected_rows:
            if prefilter_skipped_count and config.only_missing and not config.force_full_rebuild:
                message = f"解析 {len(resolved_rows)} 只股票，均已更新到 {end_date} 或不在当前批次，无需补数。"
            else:
                message = "当前筛选、断点或批次窗口下没有需要处理的股票。"
            _finish_job(conn, job_id, "success", 0, 0, message)
            summary_base = _empty_summary(config, job_id, log_file, start_date, end_date, message, counts)
            item_csv, summary_json = _write_runtime_outputs(log_dir, job_id, summary_base, [])
            summary_base.update({"item_csv": str(item_csv), "summary_json": str(summary_json), "items": []})
            summary_json.write_text(json.dumps(summary_base, ensure_ascii=False, indent=2), encoding="utf-8")
            _set_job_output_paths(conn, job_id, log_file, item_csv, summary_json)
            logger.info(message)
            return summary_base

        logger.info(
            "本次执行股票数：%s；解析数=%s，待补数=%s，前置跳过=%s",
            len(selected_rows),
            len(resolved_rows),
            len(due_rows),
            prefilter_skipped_count,
        )

        if _is_main_universe_source(config.source):
            stock_basic_rows = _stock_basic_rows_from_symbol_rows(resolved_rows)
            _upsert_stock_basic(conn, stock_basic_rows)
            if market_db_path is not None:
                upsert_stock_basic_rows(stock_basic_rows, db_path=market_db_path)
            stock_basic_map = {row["symbol"]: row for row in stock_basic_rows}
        else:
            try:
                stock_basic_frame = data_source.load_stock_basic()
                stock_basic_rows = _rows_from_stock_basic_frame(stock_basic_frame)
                _upsert_stock_basic(conn, stock_basic_rows)
                stock_basic_map = _build_stock_basic_map(stock_basic_frame)
            except Exception as exc:  # noqa: BLE001
                logger.warning("读取 stock_basic 失败，将使用模板内基础信息继续：%s", exc)
                stock_basic_map = {row["symbol"]: row for row in resolved_rows}
        daily_basic_map = _build_daily_basic_map(data_source.load_daily_basic_snapshot(end_date))
        trade_calendar = data_source.load_trade_calendar(fetch_start_date, end_date)
        market_context = data_source.load_market_context(fetch_start_date, end_date)

        for index, symbol_row in enumerate(selected_rows, start=1):
            symbol = str(symbol_row["symbol"]).zfill(6)
            ts_code = str(symbol_row.get("ts_code") or _symbol_to_ts_code(symbol)).strip()
            latest = latest_map.get(symbol, "")
            logger.info("[%s/%s] 处理 %s %s，库内最新=%s", index, len(selected_rows), symbol, ts_code, latest or "无")
            if config.only_missing and latest and latest >= end_date and not config.force_full_rebuild:
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
                raw_df, adj_df, limit_df, suspend_df = _load_symbol_inputs_with_retry(
                    data_source=data_source,
                    ts_code=ts_code,
                    start_date=fetch_start_date,
                    end_date=end_date,
                    logger=logger,
                    retry_attempts=config.retry_attempts,
                    retry_sleep_seconds=config.retry_sleep_seconds,
                )
                frame = build_processed_frame(
                    raw_df=raw_df,
                    adj_df=adj_df,
                    snapshot_row=_snapshot_row(symbol_row, stock_basic_map, daily_basic_map),
                    trade_calendar=trade_calendar,
                    limit_df=limit_df,
                    suspend_df=suspend_df,
                    market_context=market_context,
                    start_date=fetch_start_date,
                    end_date=end_date,
                )
                validate_processed_frame(frame)
                frame = frame[(frame["trade_date"].astype(str) >= start_date) & (frame["trade_date"].astype(str) <= end_date)].copy()
                rows_written = _upsert_feature_frame(conn, frame)
                market_rows_written = _upsert_market_feature_frame(frame, market_db_path)
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
                logger.info("%s 完成：旧模板库 upsert %s 行，主行情库 upsert %s 行", symbol, rows_written, market_rows_written)
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
        success_count = sum(1 for item in items if item.status in {"success", "skipped"})
        status = "success" if failed_count == 0 else "failed"
        message = (
            f"解析 {len(resolved_rows)} 只股票，待补 {len(due_rows)} 只，执行 {len(items)} 只，"
            f"成功/跳过 {success_count} 只，失败 {failed_count} 只，前置跳过 {prefilter_skipped_count} 只。"
        )
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
        resolved_stock_count=len(resolved_rows),
        due_stock_count=len(due_rows),
        prefilter_skipped_count=prefilter_skipped_count,
        selected_stock_count=len(selected_rows),
        resume_skipped_count=int(counts.get("resume_skipped_count", 0) or 0),
        batch_start=int(counts.get("batch_start", 0) or 0),
        batch_end=int(counts.get("batch_end", 0) or 0),
        batch_size=config.batch_size,
        batch_index=config.batch_index,
        offset=config.offset,
        resume_after_symbol=str(counts.get("resume_after_symbol", "") or ""),
        retry_attempts=config.retry_attempts,
        retry_sleep_seconds=config.retry_sleep_seconds,
        only_missing=bool(config.only_missing),
        items=item_dicts,
    )
    summary = summary_obj.to_dict()
    item_csv, summary_json = _write_runtime_outputs(log_dir, job_id, summary, item_dicts)
    summary["item_csv"] = str(item_csv)
    summary["summary_json"] = str(summary_json)
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with _connect(db_path) as conn:
        _set_job_output_paths(conn, job_id, log_file, item_csv, summary_json)
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

# --- Split raw collection / feature computation tasks ---------------------------
from .market_data_store import (  # noqa: E402
    latest_daily_raw_dates,
    read_adj_factor_rows,
    read_daily_basic_snapshot,
    read_daily_raw_rows,
    read_market_context_rows,
    read_stock_basic_rows,
    read_stk_limit_rows,
    read_suspend_rows,
    read_trade_calendar_rows,
    upsert_adj_factor_rows,
    upsert_daily_basic_rows,
    upsert_daily_raw_rows,
    upsert_market_context_rows,
    upsert_stk_limit_rows,
    upsert_stock_basic_rows,
    upsert_suspend_rows,
    upsert_trade_calendar_rows,
)


def _summary_from_items(
    config: StockPoolFeatureUpdateConfig,
    job_id: str,
    log_file: Path,
    log_dir: Path,
    start_date: str,
    end_date: str,
    resolved_rows: list[dict[str, Any]],
    due_rows: list[dict[str, Any]],
    selected_rows: list[dict[str, Any]],
    prefilter_skipped_count: int,
    counts: dict[str, Any],
    items: list[StockPoolSyncItem],
    message_prefix: str,
) -> dict[str, Any]:
    item_dicts = [item.__dict__ for item in items]
    failed_count = sum(1 for item in items if item.status == "failed")
    skipped_count = sum(1 for item in items if item.status == "skipped")
    success_count = sum(1 for item in items if item.status in {"success", "skipped"})
    status = "success" if failed_count == 0 else "failed"
    message = (
        f"{message_prefix}: resolved {len(resolved_rows)} symbols, due {len(due_rows)}, executed {len(items)}, "
        f"success_or_skipped {success_count}, failed {failed_count}, prefilter_skipped {prefilter_skipped_count}."
    )
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
        resolved_stock_count=len(resolved_rows),
        due_stock_count=len(due_rows),
        prefilter_skipped_count=prefilter_skipped_count,
        selected_stock_count=len(selected_rows),
        resume_skipped_count=int(counts.get("resume_skipped_count", 0) or 0),
        batch_start=int(counts.get("batch_start", 0) or 0),
        batch_end=int(counts.get("batch_end", 0) or 0),
        batch_size=config.batch_size,
        batch_index=config.batch_index,
        offset=config.offset,
        resume_after_symbol=str(counts.get("resume_after_symbol", "") or ""),
        retry_attempts=config.retry_attempts,
        retry_sleep_seconds=config.retry_sleep_seconds,
        only_missing=bool(config.only_missing),
        items=item_dicts,
    )
    summary = summary_obj.to_dict()
    item_csv, summary_json = _write_runtime_outputs(log_dir, job_id, summary, item_dicts)
    summary["item_csv"] = str(item_csv)
    summary["summary_json"] = str(summary_json)
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _prepare_split_task(
    config: StockPoolFeatureUpdateConfig,
    data_source: Any | None,
) -> tuple[Path, Path | None, Path, str, logging.Logger, Path, str, str, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int, dict[str, Any], Any]:
    db_path = _db_path(config.db_path or DEFAULT_DB_PATH)
    market_db_path = _resolve_market_db_path(db_path, config.market_db_path)
    init_stock_pool_db(db_path)
    log_dir = Path(config.log_dir)
    if not log_dir.is_absolute():
        log_dir = PROJECT_ROOT / log_dir
    job_id = str(uuid.uuid4())
    logger, log_file = _setup_logger(log_dir, job_id)

    start_date = _normalize_date(config.start_date, default="20220101")
    as_of = _normalize_date(config.end_date, default=_today_text())
    config.start_date = start_date
    config.retry_attempts = max(1, _positive_int(config.retry_attempts, default=1))
    config.retry_sleep_seconds = _positive_float(config.retry_sleep_seconds)
    config.batch_size = _positive_int(config.batch_size)
    config.batch_index = _positive_int(config.batch_index)
    config.offset = _positive_int(config.offset)
    config.max_symbols = _positive_int(config.max_symbols)
    if data_source is None:
        data_source = TushareStockPoolDataSource(config.env_path)
    end_date = data_source.latest_trade_date(as_of) if hasattr(data_source, "latest_trade_date") else as_of
    end_date = _normalize_date(end_date, default=as_of)

    with _connect(db_path) as conn:
        resolved_rows = _resolve_symbol_rows(conn, config, data_source, logger, market_db_path=market_db_path)
        latest_map = latest_daily_raw_dates([str(row.get("symbol") or "") for row in resolved_rows], market_db_path)
        due_rows, prefilter_skipped_count = _filter_due_symbol_rows(
            resolved_rows,
            latest_map=latest_map,
            end_date=end_date,
            config=config,
            logger=logger,
        )
        window_rows, counts = _apply_batch_window(resolved_rows, config, logger)
        if config.only_missing and not config.force_full_rebuild:
            selected_rows = [
                row for row in window_rows
                if not latest_map.get(str(row.get("symbol") or "").strip().zfill(6), "")
                or latest_map.get(str(row.get("symbol") or "").strip().zfill(6), "") < end_date
            ]
        else:
            selected_rows = window_rows
        counts["due_stock_count"] = len(due_rows)
        counts["prefilter_skipped_count"] = prefilter_skipped_count
        counts["selected_stock_count"] = len(selected_rows)
        _create_job(conn, config, job_id, len(selected_rows), end_date)
    return (
        db_path,
        market_db_path,
        log_dir,
        job_id,
        logger,
        log_file,
        start_date,
        end_date,
        resolved_rows,
        due_rows,
        selected_rows,
        prefilter_skipped_count,
        counts,
        data_source,
    )


def _finish_split_task(db_path: Path, job_id: str, log_file: Path, summary: dict[str, Any], logger: logging.Logger) -> dict[str, Any]:
    with _connect(db_path) as conn:
        _finish_job(
            conn,
            job_id,
            str(summary.get("status") or "failed"),
            int(summary.get("success_count") or 0),
            int(summary.get("failed_count") or 0),
            str(summary.get("message") or ""),
        )
        _set_job_output_paths(conn, job_id, log_file, str(summary.get("item_csv") or ""), str(summary.get("summary_json") or ""))
    logger.info(str(summary.get("message") or ""))
    return summary


def _frame_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [
        {key: _coerce_db_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def run_stock_daily_raw_collection(
    config: StockPoolFeatureUpdateConfig,
    data_source: Any | None = None,
) -> dict[str, Any]:
    (
        db_path,
        market_db_path,
        log_dir,
        job_id,
        logger,
        log_file,
        start_date,
        end_date,
        resolved_rows,
        due_rows,
        selected_rows,
        prefilter_skipped_count,
        counts,
        data_source,
    ) = _prepare_split_task(config, data_source)
    target_db = market_db_path or db_path
    fetch_start_date = _lookback_start_date(start_date)
    items: list[StockPoolSyncItem] = []
    if not selected_rows:
        summary = _summary_from_items(config, job_id, log_file, log_dir, start_date, end_date, resolved_rows, due_rows, [], prefilter_skipped_count, counts, [], "raw collection")
        return _finish_split_task(db_path, job_id, log_file, summary, logger)

    try:
        if _is_main_universe_source(config.source):
            stock_basic_rows = _stock_basic_rows_from_symbol_rows(resolved_rows)
        else:
            stock_basic_frame = data_source.load_stock_basic()
            stock_basic_rows = _rows_from_stock_basic_frame(stock_basic_frame)
        with _connect(db_path) as conn:
            _upsert_stock_basic(conn, stock_basic_rows)
        upsert_stock_basic_rows(stock_basic_rows, db_path=target_db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("load stock_basic failed; continue raw collection: %s", exc)
    try:
        trade_calendar = data_source.load_trade_calendar(fetch_start_date, end_date)
        market_context = data_source.load_market_context(fetch_start_date, end_date)
        daily_basic = data_source.load_daily_basic_snapshot(end_date)
        upsert_trade_calendar_rows(_frame_rows(trade_calendar), db_path=target_db)
        upsert_market_context_rows(_frame_rows(market_context), db_path=target_db)
        daily_basic_rows = _frame_rows(daily_basic)
        for row in daily_basic_rows:
            row.setdefault("trade_date", end_date)
        upsert_daily_basic_rows(daily_basic_rows, db_path=target_db)
    except Exception as exc:  # noqa: BLE001
        logger.exception("common raw input collection failed: %s", exc)
        items = [
            StockPoolSyncItem(
                symbol=str(row.get("symbol") or "").zfill(6),
                ts_code=str(row.get("ts_code") or ""),
                status="failed",
                start_date=start_date,
                end_date=end_date,
                rows_written=0,
                message=str(exc)[:1000],
            )
            for row in selected_rows
        ]
        summary = _summary_from_items(config, job_id, log_file, log_dir, start_date, end_date, resolved_rows, due_rows, selected_rows, prefilter_skipped_count, counts, items, "raw collection")
        with _connect(db_path) as conn:
            for item in items:
                _write_job_item(conn, job_id, item)
        return _finish_split_task(db_path, job_id, log_file, summary, logger)

    with _connect(db_path) as conn:
        for index, symbol_row in enumerate(selected_rows, start=1):
            symbol = str(symbol_row["symbol"]).zfill(6)
            ts_code = str(symbol_row.get("ts_code") or _symbol_to_ts_code(symbol)).strip()
            logger.info("[%s/%s] collect raw inputs %s %s", index, len(selected_rows), symbol, ts_code)
            try:
                raw_df, adj_df, limit_df, suspend_df = _load_symbol_inputs_with_retry(
                    data_source=data_source,
                    ts_code=ts_code,
                    start_date=fetch_start_date,
                    end_date=end_date,
                    logger=logger,
                    retry_attempts=config.retry_attempts,
                    retry_sleep_seconds=config.retry_sleep_seconds,
                )
                raw_written = int(upsert_daily_raw_rows(_frame_rows(raw_df), db_path=target_db).get("rows_written") or 0)
                upsert_adj_factor_rows(_frame_rows(adj_df), db_path=target_db)
                upsert_stk_limit_rows(_frame_rows(limit_df), db_path=target_db)
                upsert_suspend_rows(_frame_rows(suspend_df), db_path=target_db)
                item = StockPoolSyncItem(symbol=symbol, ts_code=ts_code, status="success", start_date=start_date, end_date=end_date, rows_written=raw_written, message="raw inputs stored")
                _write_job_item(conn, job_id, item)
                items.append(item)
                if config.sleep_seconds > 0:
                    time.sleep(config.sleep_seconds)
            except Exception as exc:  # noqa: BLE001
                item = StockPoolSyncItem(symbol=symbol, ts_code=ts_code, status="failed", start_date=start_date, end_date=end_date, rows_written=0, message=str(exc)[:1000])
                _write_job_item(conn, job_id, item)
                items.append(item)
                logger.exception("%s raw input collection failed: %s", symbol, exc)
    summary = _summary_from_items(config, job_id, log_file, log_dir, start_date, end_date, resolved_rows, due_rows, selected_rows, prefilter_skipped_count, counts, items, "raw collection")
    return _finish_split_task(db_path, job_id, log_file, summary, logger)


def _stock_basic_map_from_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("symbol") or "").zfill(6): dict(row) for row in rows if str(row.get("symbol") or "").strip()}


def _daily_basic_map_from_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for row in rows:
        ts_code = str(row.get("ts_code") or "").strip()
        if ts_code:
            mapping[ts_code] = row
    return mapping


def run_stock_daily_feature_computation(
    config: StockPoolFeatureUpdateConfig,
    data_source: Any | None = None,
) -> dict[str, Any]:
    (
        db_path,
        market_db_path,
        log_dir,
        job_id,
        logger,
        log_file,
        start_date,
        end_date,
        resolved_rows,
        due_rows,
        selected_rows,
        prefilter_skipped_count,
        counts,
        data_source,
    ) = _prepare_split_task(config, data_source)
    target_db = market_db_path or db_path
    fetch_start_date = _lookback_start_date(start_date)
    items: list[StockPoolSyncItem] = []
    trade_calendar = pd.DataFrame(read_trade_calendar_rows(fetch_start_date, end_date, db_path=target_db))
    market_context = pd.DataFrame(read_market_context_rows(fetch_start_date, end_date, db_path=target_db))
    stock_basic_map = _stock_basic_map_from_rows(read_stock_basic_rows(db_path=target_db))
    daily_basic_map = _daily_basic_map_from_rows(read_daily_basic_snapshot(end_date, db_path=target_db))
    with _connect(db_path) as conn:
        for index, symbol_row in enumerate(selected_rows, start=1):
            symbol = str(symbol_row["symbol"]).zfill(6)
            ts_code = str(symbol_row.get("ts_code") or _symbol_to_ts_code(symbol)).strip()
            logger.info("[%s/%s] compute features from SQLite raw inputs %s %s", index, len(selected_rows), symbol, ts_code)
            try:
                raw_df = pd.DataFrame(read_daily_raw_rows(symbol, fetch_start_date, end_date, db_path=target_db))
                adj_df = pd.DataFrame(read_adj_factor_rows(symbol, fetch_start_date, end_date, db_path=target_db))
                limit_df = pd.DataFrame(read_stk_limit_rows(symbol, fetch_start_date, end_date, db_path=target_db))
                suspend_df = pd.DataFrame(read_suspend_rows(symbol, fetch_start_date, end_date, db_path=target_db))
                if raw_df.empty:
                    raise RuntimeError(f"SQLite raw daily missing: {symbol}")
                if adj_df.empty:
                    raise RuntimeError(f"SQLite raw daily missing: {symbol}")
                if trade_calendar.empty:
                    raise RuntimeError(f"SQLite trade calendar missing: {fetch_start_date}-{end_date}")
                if market_context.empty:
                    raise RuntimeError(f"SQLite market context missing: {fetch_start_date}-{end_date}")
                frame = build_processed_frame(
                    raw_df=raw_df,
                    adj_df=adj_df,
                    snapshot_row=_snapshot_row(symbol_row, stock_basic_map, daily_basic_map),
                    trade_calendar=trade_calendar,
                    limit_df=limit_df,
                    suspend_df=suspend_df,
                    market_context=market_context,
                    start_date=fetch_start_date,
                    end_date=end_date,
                )
                validate_processed_frame(frame)
                frame = frame[(frame["trade_date"].astype(str) >= start_date) & (frame["trade_date"].astype(str) <= end_date)].copy()
                rows_written = _upsert_feature_frame(conn, frame)
                market_rows_written = _upsert_market_feature_frame(frame, target_db)
                item = StockPoolSyncItem(symbol=symbol, ts_code=ts_code, status="success", start_date=start_date, end_date=end_date, rows_written=rows_written, message=f"features stored; market db wrote {market_rows_written} rows")
                _write_job_item(conn, job_id, item)
                items.append(item)
                if config.sleep_seconds > 0:
                    time.sleep(config.sleep_seconds)
            except Exception as exc:  # noqa: BLE001
                item = StockPoolSyncItem(symbol=symbol, ts_code=ts_code, status="failed", start_date=start_date, end_date=end_date, rows_written=0, message=str(exc)[:1000])
                _write_job_item(conn, job_id, item)
                items.append(item)
                logger.exception("%s SQLite feature computation failed: %s", symbol, exc)
    summary = _summary_from_items(config, job_id, log_file, log_dir, start_date, end_date, resolved_rows, due_rows, selected_rows, prefilter_skipped_count, counts, items, "SQLite feature computation")
    return _finish_split_task(db_path, job_id, log_file, summary, logger)

class SQLiteFeatureComputationDataSource:
    def __init__(self, db_path: str | Path | None) -> None:
        self.db_path = db_path

    def latest_trade_date(self, end_date: str) -> str:
        rows = read_trade_calendar_rows("", end_date, db_path=self.db_path)
        open_dates = [str(row.get("trade_date") or "") for row in rows if str(row.get("is_open") or "1") == "1"]
        return max(open_dates) if open_dates else end_date

    def load_stock_basic(self) -> pd.DataFrame:
        return pd.DataFrame(read_stock_basic_rows(db_path=self.db_path))


_previous_run_stock_daily_feature_computation = run_stock_daily_feature_computation


def run_stock_daily_feature_computation(
    config: StockPoolFeatureUpdateConfig,
    data_source: Any | None = None,
) -> dict[str, Any]:  # type: ignore[no-redef]
    if data_source is None:
        db_path = _db_path(config.db_path or DEFAULT_DB_PATH)
        market_db_path = _resolve_market_db_path(db_path, config.market_db_path)
        data_source = SQLiteFeatureComputationDataSource(market_db_path or db_path)
    return _previous_run_stock_daily_feature_computation(config, data_source=data_source)

class SQLiteFeatureComputationDataSource:
    def __init__(self, db_path: str | Path | None, start_date: str = "", end_date: str = "") -> None:
        self.db_path = db_path
        self.start_date = _lookback_start_date(_normalize_date(start_date, default="20220101")) if start_date else ""
        self.end_date = _normalize_date(end_date, default="99999999") if end_date else "99999999"

    def latest_trade_date(self, end_date: str) -> str:
        rows = read_trade_calendar_rows("", end_date, db_path=self.db_path)
        open_dates = [str(row.get("trade_date") or "") for row in rows if str(row.get("is_open") or "1") == "1"]
        return max(open_dates) if open_dates else end_date

    def load_stock_basic(self) -> pd.DataFrame:
        basic_rows = read_stock_basic_rows(db_path=self.db_path)
        if not basic_rows:
            return pd.DataFrame()
        raw_latest = latest_daily_raw_dates([str(row.get("symbol") or "") for row in basic_rows], db_path=self.db_path)
        raw_symbols = {symbol for symbol, latest in raw_latest.items() if latest and latest >= self.start_date}
        filtered = [row for row in basic_rows if str(row.get("symbol") or "").zfill(6) in raw_symbols]
        return pd.DataFrame(filtered)


def run_stock_daily_feature_computation(
    config: StockPoolFeatureUpdateConfig,
    data_source: Any | None = None,
) -> dict[str, Any]:  # type: ignore[no-redef]
    if data_source is None:
        db_path = _db_path(config.db_path or DEFAULT_DB_PATH)
        market_db_path = _resolve_market_db_path(db_path, config.market_db_path)
        data_source = SQLiteFeatureComputationDataSource(market_db_path or db_path, config.start_date, config.end_date)
    return _previous_run_stock_daily_feature_computation(config, data_source=data_source)
