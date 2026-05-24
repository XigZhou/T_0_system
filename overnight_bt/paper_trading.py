from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - zoneinfo exists in supported runtimes
    ZoneInfo = None

import httpx
import pandas as pd

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised on minimal server envs
    yaml = None

from .daily_plan import build_daily_plan
from .models import DailyHolding, DailyPlanRequest, PaperTemplateSaveRequest, PaperTradingRunRequest
from . import market_data_store
from .sqlite_only_guard import is_sqlite_only_enabled
from .stock_pool_templates import DEFAULT_DB_PATH, DEFAULT_USERNAME, _connect, init_stock_pool_db, read_stock_pool_template, read_template_symbols
from .utils import to_float


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "configs" / "paper_accounts"
DEFAULT_LEDGER_DIR = PROJECT_ROOT / "paper_trading" / "accounts"
DEFAULT_LOG_DIR = PROJECT_ROOT / "paper_trading" / "logs"
DEFAULT_PAPER_DB_PATH = PROJECT_ROOT / "data_store" / "paper_trading.sqlite"

PENDING_COLUMNS = [
    "订单编号",
    "账户编号",
    "账户名称",
    "订单方向",
    "状态",
    "信号日期",
    "计划执行日期",
    "股票代码",
    "股票名称",
    "排名",
    "评分",
    "信号收盘价",
    "计划股数",
    "最低买入金额",
    "生成时间",
    "执行时间",
    "成交价格",
    "成交金额",
    "手续费",
    "印花税",
    "滑点bps",
    "失败原因",
]

TRADE_COLUMNS = [
    "交易编号",
    "账户编号",
    "账户名称",
    "订单编号",
    "交易日期",
    "交易方向",
    "股票代码",
    "股票名称",
    "成交价格",
    "股数",
    "成交金额",
    "手续费",
    "印花税",
    "总金额",
    "买入成本",
    "实现盈亏",
    "收益率",
    "现金余额",
    "备注",
]

HOLDING_COLUMNS = [
    "账户编号",
    "账户名称",
    "股票代码",
    "股票名称",
    "买入日期",
    "买入价格",
    "股数",
    "买入成交金额",
    "买入手续费",
    "买入总成本",
    "当前价格",
    "当前市值",
    "浮动盈亏",
    "浮动收益率",
    "持有天数",
    "最后估值日期",
    "来源订单编号",
]

ASSET_COLUMNS = [
    "账户编号",
    "账户名称",
    "日期",
    "现金",
    "持仓市值",
    "总资产",
    "初始资金",
    "累计收益",
    "持仓数量",
    "备注",
]

LOG_COLUMNS = ["时间", "账户编号", "账户名称", "动作", "级别", "信息"]
CONFIG_COLUMNS = ["字段", "值"]
SHEET_NAMES = ["配置快照", "待执行订单", "成交流水", "当前持仓", "每日资产", "运行日志"]
LEDGER_TABLES: dict[str, tuple[str, list[str]]] = {
    "配置快照": ("paper_config_snapshot", CONFIG_COLUMNS),
    "待执行订单": ("paper_pending_orders", PENDING_COLUMNS),
    "成交流水": ("paper_trades", TRADE_COLUMNS),
    "当前持仓": ("paper_holdings", HOLDING_COLUMNS),
    "每日资产": ("paper_assets", ASSET_COLUMNS),
    "运行日志": ("paper_logs", LOG_COLUMNS),
}


@dataclass
class PaperAccountConfig:
    account_id: str
    account_name: str
    initial_cash: float
    stock_pool_username: str
    stock_pool_template_name: str
    stock_pool_db_path: str
    buy_condition: str
    sell_condition: str
    score_expression: str
    top_n: int
    entry_offset: int
    min_hold_days: int
    max_hold_days: int
    buy_quantity_mode: str
    buy_shares: int
    buy_lot_size: int
    min_buy_amount: float
    buy_min_close: float
    buy_max_close: float
    price_primary: str
    price_fallback: str
    price_field: str
    skip_if_holding: bool
    skip_if_pending_order: bool
    strict_execution: bool
    buy_fee_rate: float
    sell_fee_rate: float
    stamp_tax_sell: float
    slippage_bps: float
    min_commission: float
    ledger_path: Path
    log_dir: Path
    raw_config: dict[str, Any]
    username: str = DEFAULT_USERNAME
    paper_db_path: Path = DEFAULT_PAPER_DB_PATH


@dataclass
class PriceQuote:
    symbol: str
    name: str
    trade_date: str
    price: float
    close_price: float | None
    can_buy: bool
    can_sell: bool
    source: str


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_path(path_text: str | Path, base: Path = PROJECT_ROOT) -> Path:
    path = Path(str(path_text).strip()).expanduser()
    if not path.is_absolute():
        path = base / path
    return path


def _stock_pool_db_path(path_text: str | Path | None = None) -> Path:
    if path_text is None or str(path_text).strip() == "":
        return DEFAULT_DB_PATH
    return _normalize_path(path_text)


def _stock_pool_db_path_text(path_text: str | Path | None = None) -> str:
    return _relative_text(_stock_pool_db_path(path_text))


def _market_data_db_path() -> Path | None:
    path_text = os.environ.get("MARKET_DATA_DB_PATH", "").strip()
    return _normalize_path(path_text) if path_text else None


def _paper_db_path(path_text: str | Path | None = None) -> Path:
    if path_text is None or str(path_text).strip() == "":
        return DEFAULT_PAPER_DB_PATH
    return _normalize_path(path_text)


def _paper_db_path_text(path_text: str | Path | None = None) -> str:
    return _relative_text(_paper_db_path(path_text))


def _paper_context_db_path(config_dir: str | Path = DEFAULT_CONFIG_DIR, config_path: str | Path | None = None) -> Path:
    path_text = str(config_path or "").strip()
    if path_text:
        candidate = Path(path_text).expanduser()
        if candidate.suffix.lower() in {".yaml", ".yml"} and candidate.is_absolute():
            folder = candidate.parent
        else:
            folder = _normalize_template_dir(config_dir)
    else:
        folder = _normalize_template_dir(config_dir)
    if _is_relative_to(folder, PROJECT_ROOT):
        return DEFAULT_PAPER_DB_PATH
    if folder.name == "paper_accounts" and folder.parent.name == "configs":
        root = folder.parent.parent
    else:
        root = folder.parent
    return (root / "data_store" / "paper_trading.sqlite").resolve()


def _paper_connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _paper_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _json_dumps(data: Any) -> str:
    return json.dumps(data if data is not None else {}, ensure_ascii=False, sort_keys=True)


def _json_loads(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _frame_to_json(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "[]"
    clean = frame.astype(object).where(pd.notna(frame), None)
    return _json_dumps(clean.to_dict(orient="records"))


def _frame_from_json(text: str | None, columns: list[str]) -> pd.DataFrame:
    rows = _json_loads(text, [])
    if not isinstance(rows, list):
        rows = []
    frame = pd.DataFrame(rows)
    for col in columns:
        if col not in frame.columns:
            frame[col] = pd.NA
    return frame[columns]


def init_paper_trading_db(db_path: str | Path | None = None) -> None:
    with _paper_connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS paper_account_templates (
                template_id TEXT PRIMARY KEY,
                username TEXT NOT NULL DEFAULT 'admin',
                account_id TEXT NOT NULL,
                account_name TEXT NOT NULL,
                initial_cash REAL NOT NULL DEFAULT 100000,
                stock_pool_username TEXT NOT NULL DEFAULT 'admin',
                stock_pool_template_name TEXT NOT NULL,
                stock_pool_db_path TEXT NOT NULL DEFAULT '',
                buy_condition TEXT NOT NULL,
                sell_condition TEXT NOT NULL DEFAULT '',
                score_expression TEXT NOT NULL DEFAULT 'm20',
                top_n INTEGER NOT NULL DEFAULT 5,
                entry_offset INTEGER NOT NULL DEFAULT 1,
                min_hold_days INTEGER NOT NULL DEFAULT 0,
                max_hold_days INTEGER NOT NULL DEFAULT 15,
                buy_quantity_mode TEXT NOT NULL DEFAULT '固定股数',
                buy_shares INTEGER NOT NULL DEFAULT 200,
                buy_lot_size INTEGER NOT NULL DEFAULT 100,
                min_buy_amount REAL NOT NULL DEFAULT 10000,
                buy_min_close REAL NOT NULL DEFAULT 0,
                buy_max_close REAL NOT NULL DEFAULT 150,
                price_primary TEXT NOT NULL DEFAULT '东方财富',
                price_fallback TEXT NOT NULL DEFAULT '腾讯股票',
                price_field TEXT NOT NULL DEFAULT '开盘价',
                skip_if_holding INTEGER NOT NULL DEFAULT 1,
                skip_if_pending_order INTEGER NOT NULL DEFAULT 1,
                strict_execution INTEGER NOT NULL DEFAULT 1,
                buy_fee_rate REAL NOT NULL DEFAULT 0.00003,
                sell_fee_rate REAL NOT NULL DEFAULT 0.00003,
                stamp_tax_sell REAL NOT NULL DEFAULT 0,
                slippage_bps REAL NOT NULL DEFAULT 3,
                min_commission REAL NOT NULL DEFAULT 0,
                raw_config_json TEXT NOT NULL DEFAULT '{}',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(username, account_id),
                UNIQUE(username, account_name)
            );

            CREATE TABLE IF NOT EXISTS paper_config_snapshot (
                username TEXT NOT NULL DEFAULT 'admin',
                account_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                row_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(username, account_id, position)
            );

            CREATE TABLE IF NOT EXISTS paper_pending_orders (
                username TEXT NOT NULL DEFAULT 'admin',
                account_id TEXT NOT NULL,
                row_key TEXT NOT NULL,
                position INTEGER NOT NULL,
                row_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(username, account_id, row_key)
            );

            CREATE TABLE IF NOT EXISTS paper_trades (
                username TEXT NOT NULL DEFAULT 'admin',
                account_id TEXT NOT NULL,
                row_key TEXT NOT NULL,
                position INTEGER NOT NULL,
                row_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(username, account_id, row_key)
            );

            CREATE TABLE IF NOT EXISTS paper_holdings (
                username TEXT NOT NULL DEFAULT 'admin',
                account_id TEXT NOT NULL,
                row_key TEXT NOT NULL,
                position INTEGER NOT NULL,
                row_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(username, account_id, row_key)
            );

            CREATE TABLE IF NOT EXISTS paper_assets (
                username TEXT NOT NULL DEFAULT 'admin',
                account_id TEXT NOT NULL,
                row_key TEXT NOT NULL,
                position INTEGER NOT NULL,
                row_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(username, account_id, row_key)
            );

            CREATE TABLE IF NOT EXISTS paper_logs (
                username TEXT NOT NULL DEFAULT 'admin',
                account_id TEXT NOT NULL,
                row_key TEXT NOT NULL,
                position INTEGER NOT NULL,
                row_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(username, account_id, row_key)
            );

            CREATE VIEW IF NOT EXISTS paper_account_ledgers AS
                SELECT username, account_id, '配置快照' AS sheet_name, COUNT(*) AS row_count FROM paper_config_snapshot GROUP BY username, account_id
                UNION ALL
                SELECT username, account_id, '待执行订单' AS sheet_name, COUNT(*) AS row_count FROM paper_pending_orders GROUP BY username, account_id
                UNION ALL
                SELECT username, account_id, '成交流水' AS sheet_name, COUNT(*) AS row_count FROM paper_trades GROUP BY username, account_id
                UNION ALL
                SELECT username, account_id, '当前持仓' AS sheet_name, COUNT(*) AS row_count FROM paper_holdings GROUP BY username, account_id
                UNION ALL
                SELECT username, account_id, '每日资产' AS sheet_name, COUNT(*) AS row_count FROM paper_assets GROUP BY username, account_id
                UNION ALL
                SELECT username, account_id, '运行日志' AS sheet_name, COUNT(*) AS row_count FROM paper_logs GROUP BY username, account_id;

            CREATE INDEX IF NOT EXISTS idx_paper_templates_user_active
                ON paper_account_templates(username, is_active, updated_at);
            CREATE INDEX IF NOT EXISTS idx_paper_pending_orders_position
                ON paper_pending_orders(username, account_id, position);
            CREATE INDEX IF NOT EXISTS idx_paper_trades_position
                ON paper_trades(username, account_id, position);
            CREATE INDEX IF NOT EXISTS idx_paper_holdings_position
                ON paper_holdings(username, account_id, position);
            CREATE INDEX IF NOT EXISTS idx_paper_assets_position
                ON paper_assets(username, account_id, position);
            CREATE INDEX IF NOT EXISTS idx_paper_logs_position
                ON paper_logs(username, account_id, position);
            """
        )
        existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(paper_account_templates)").fetchall()}
        migrations = {
            "username": "TEXT NOT NULL DEFAULT 'admin'",
            "raw_config_json": "TEXT NOT NULL DEFAULT '{}'",
            "is_active": "INTEGER NOT NULL DEFAULT 1",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for column_name, definition in migrations.items():
            if column_name not in existing:
                conn.execute(f"ALTER TABLE paper_account_templates ADD COLUMN {column_name} {definition}")
        now = _now_text()
        conn.execute("UPDATE paper_account_templates SET created_at=? WHERE created_at=''", (now,))
        conn.execute("UPDATE paper_account_templates SET updated_at=? WHERE updated_at=''", (now,))
        conn.commit()


def _clean_username(username: str | None = None) -> str:
    return str(username or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME


def _ledger_storage_id(cfg: PaperAccountConfig | None = None) -> str:
    if cfg is None:
        return _paper_db_path_text()
    return _paper_db_path_text(cfg.paper_db_path)


def _ledger_exists(cfg: PaperAccountConfig) -> bool:
    init_paper_trading_db(cfg.paper_db_path)
    with _paper_connect(cfg.paper_db_path) as conn:
        for table_name, _columns in LEDGER_TABLES.values():
            row = conn.execute(
                f"SELECT 1 FROM {table_name} WHERE username=? AND account_id=? LIMIT 1",
                (_clean_username(cfg.username), cfg.account_id),
            ).fetchone()
            if row is not None:
                return True
    return False


def _ledger_path_for_account(account_id: str) -> Path:
    return _paper_db_path(DEFAULT_PAPER_DB_PATH)


def _log_dir_for_account(username: str, account_id: str) -> Path:
    return DEFAULT_LOG_DIR / _clean_username(username) / str(account_id or "default")


def _template_id(username: str, account_id: str) -> str:
    return f"{_clean_username(username)}:{str(account_id).strip()}"


def _row_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(int(value))


def _template_row_values(cfg: PaperAccountConfig, now: str) -> tuple[Any, ...]:
    return (
        _template_id(cfg.username, cfg.account_id),
        _clean_username(cfg.username),
        cfg.account_id,
        cfg.account_name,
        cfg.initial_cash,
        cfg.stock_pool_username,
        cfg.stock_pool_template_name,
        cfg.stock_pool_db_path,
        cfg.buy_condition,
        cfg.sell_condition,
        cfg.score_expression,
        cfg.top_n,
        cfg.entry_offset,
        cfg.min_hold_days,
        cfg.max_hold_days,
        cfg.buy_quantity_mode,
        cfg.buy_shares,
        cfg.buy_lot_size,
        cfg.min_buy_amount,
        cfg.buy_min_close,
        cfg.buy_max_close,
        cfg.price_primary,
        cfg.price_fallback,
        cfg.price_field,
        1 if cfg.skip_if_holding else 0,
        1 if cfg.skip_if_pending_order else 0,
        1 if cfg.strict_execution else 0,
        cfg.buy_fee_rate,
        cfg.sell_fee_rate,
        cfg.stamp_tax_sell,
        cfg.slippage_bps,
        cfg.min_commission,
        _json_dumps(cfg.raw_config),
        now,
        now,
    )


def _template_config_from_row(row: sqlite3.Row) -> PaperAccountConfig:
    data = dict(row)
    username = _clean_username(data.get("username"))
    account_id = str(data.get("account_id") or "").strip()
    account_name = str(data.get("account_name") or account_id).strip()
    raw_config = _json_loads(data.get("raw_config_json"), {})
    if not isinstance(raw_config, dict):
        raw_config = {}
    stock_pool_db_path = _stock_pool_db_path_text(data.get("stock_pool_db_path") or "")
    return PaperAccountConfig(
        account_id=account_id,
        account_name=account_name,
        initial_cash=_as_float(data.get("initial_cash"), 100_000.0),
        stock_pool_username=str(data.get("stock_pool_username") or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME,
        stock_pool_template_name=str(data.get("stock_pool_template_name") or "").strip(),
        stock_pool_db_path=stock_pool_db_path,
        buy_condition=str(data.get("buy_condition") or "").strip(),
        sell_condition=str(data.get("sell_condition") or "").strip(),
        score_expression=str(data.get("score_expression") or "m20").strip() or "m20",
        top_n=max(1, _as_int(data.get("top_n"), 5)),
        entry_offset=max(1, _as_int(data.get("entry_offset"), 1)),
        min_hold_days=max(0, _as_int(data.get("min_hold_days"), 0)),
        max_hold_days=max(0, _as_int(data.get("max_hold_days"), 15)),
        buy_quantity_mode=str(data.get("buy_quantity_mode") or "固定股数").strip(),
        buy_shares=max(1, _as_int(data.get("buy_shares"), 200)),
        buy_lot_size=max(1, _as_int(data.get("buy_lot_size"), 100)),
        min_buy_amount=max(0.0, _as_float(data.get("min_buy_amount"), 0.0)),
        buy_min_close=max(0.0, _as_float(data.get("buy_min_close"), 0.0)),
        buy_max_close=max(0.0, _as_float(data.get("buy_max_close"), 0.0)),
        price_primary=str(data.get("price_primary") or "东方财富").strip(),
        price_fallback=str(data.get("price_fallback") or "腾讯股票").strip(),
        price_field=str(data.get("price_field") or "开盘价").strip(),
        skip_if_holding=_row_bool(data.get("skip_if_holding"), True),
        skip_if_pending_order=_row_bool(data.get("skip_if_pending_order"), True),
        strict_execution=_row_bool(data.get("strict_execution"), True),
        buy_fee_rate=_as_float(data.get("buy_fee_rate"), 0.00003),
        sell_fee_rate=_as_float(data.get("sell_fee_rate"), 0.00003),
        stamp_tax_sell=_as_float(data.get("stamp_tax_sell"), 0.0),
        slippage_bps=_as_float(data.get("slippage_bps"), 0.0),
        min_commission=_as_float(data.get("min_commission"), 0.0),
        ledger_path=_ledger_path_for_account(account_id),
        log_dir=_log_dir_for_account(username, account_id),
        raw_config=raw_config,
        username=username,
        paper_db_path=_paper_db_path(raw_config.get("_paper_db_path") or ""),
    )


def _read_template_by_account(account_id: str, username: str = DEFAULT_USERNAME, db_path: str | Path | None = None) -> PaperAccountConfig:
    clean_user = _clean_username(username)
    clean_account = str(account_id or "").strip()
    if not clean_account:
        raise ValueError("请先选择模拟账户模板")
    init_paper_trading_db(db_path)
    with _paper_connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM paper_account_templates
            WHERE username=? AND account_id=? AND is_active=1
            """,
            (clean_user, clean_account),
        ).fetchone()
    if row is None:
        raise FileNotFoundError(f"找不到模拟账户模板: {clean_user}/{clean_account}")
    return _template_config_from_row(row)


def _save_cfg_to_sqlite(cfg: PaperAccountConfig, overwrite_existing: bool, require_existing: bool = False, template_db_path: str | Path | None = None) -> PaperAccountConfig:
    clean_user = _clean_username(cfg.username)
    cfg.username = clean_user
    cfg.paper_db_path = _paper_db_path(cfg.paper_db_path)
    cfg.ledger_path = _ledger_path_for_account(cfg.account_id)
    cfg.log_dir = _log_dir_for_account(clean_user, cfg.account_id)
    template_db = _paper_db_path(template_db_path or cfg.paper_db_path)
    init_paper_trading_db(template_db)
    now = _now_text()
    with _paper_connect(template_db) as conn:
        duplicate = conn.execute(
            """
            SELECT account_id, account_name
            FROM paper_account_templates
            WHERE username=? AND is_active=1 AND (account_id=? OR account_name=?)
            """,
            (clean_user, cfg.account_id, cfg.account_name),
        ).fetchone()
        if duplicate is not None and str(duplicate["account_id"]) != cfg.account_id:
            raise ValueError(f"账户名称已被其他模板使用: {cfg.account_name}")
        if duplicate is not None and not overwrite_existing and str(duplicate["account_id"]) == cfg.account_id:
            raise ValueError(f"账户编号已被其他模板使用: {cfg.account_id}")
        if overwrite_existing:
            existing = conn.execute(
                """
                SELECT account_id
                FROM paper_account_templates
                WHERE username=? AND account_id=? AND is_active=1
                """,
                (clean_user, cfg.account_id),
            ).fetchone()
            if require_existing and existing is None:
                raise ValueError("覆盖保存必须选择当前已有账户模板；如需新模板请使用另存为")
        conn.execute(
            """
            INSERT INTO paper_account_templates (
                template_id, username, account_id, account_name, initial_cash,
                stock_pool_username, stock_pool_template_name, stock_pool_db_path,
                buy_condition, sell_condition, score_expression, top_n, entry_offset,
                min_hold_days, max_hold_days, buy_quantity_mode, buy_shares, buy_lot_size,
                min_buy_amount, buy_min_close, buy_max_close, price_primary, price_fallback,
                price_field, skip_if_holding, skip_if_pending_order, strict_execution,
                buy_fee_rate, sell_fee_rate, stamp_tax_sell, slippage_bps, min_commission,
                raw_config_json, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(username, account_id) DO UPDATE SET
                account_name=excluded.account_name,
                initial_cash=excluded.initial_cash,
                stock_pool_username=excluded.stock_pool_username,
                stock_pool_template_name=excluded.stock_pool_template_name,
                stock_pool_db_path=excluded.stock_pool_db_path,
                buy_condition=excluded.buy_condition,
                sell_condition=excluded.sell_condition,
                score_expression=excluded.score_expression,
                top_n=excluded.top_n,
                entry_offset=excluded.entry_offset,
                min_hold_days=excluded.min_hold_days,
                max_hold_days=excluded.max_hold_days,
                buy_quantity_mode=excluded.buy_quantity_mode,
                buy_shares=excluded.buy_shares,
                buy_lot_size=excluded.buy_lot_size,
                min_buy_amount=excluded.min_buy_amount,
                buy_min_close=excluded.buy_min_close,
                buy_max_close=excluded.buy_max_close,
                price_primary=excluded.price_primary,
                price_fallback=excluded.price_fallback,
                price_field=excluded.price_field,
                skip_if_holding=excluded.skip_if_holding,
                skip_if_pending_order=excluded.skip_if_pending_order,
                strict_execution=excluded.strict_execution,
                buy_fee_rate=excluded.buy_fee_rate,
                sell_fee_rate=excluded.sell_fee_rate,
                stamp_tax_sell=excluded.stamp_tax_sell,
                slippage_bps=excluded.slippage_bps,
                min_commission=excluded.min_commission,
                raw_config_json=excluded.raw_config_json,
                is_active=1,
                updated_at=excluded.updated_at
            """,
            _template_row_values(cfg, now),
        )
        conn.commit()
    return cfg


def _has_paper_account_templates(db_path: str | Path, username: str = DEFAULT_USERNAME) -> bool:
    init_paper_trading_db(db_path)
    with _paper_connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM paper_account_templates WHERE username=?",
            (_clean_username(username),),
        ).fetchone()[0]
    return int(count or 0) > 0


def _legacy_templates_to_sqlite(config_dir: str | Path = DEFAULT_CONFIG_DIR, username: str = DEFAULT_USERNAME) -> None:
    if is_sqlite_only_enabled():
        return
    folder = _normalize_path(config_dir)
    if not folder.exists():
        return
    clean_user = _clean_username(username)
    context_db = _paper_context_db_path(config_dir)
    init_paper_trading_db(context_db)
    for path in sorted(folder.glob("*.yaml")):
        try:
            cfg = load_paper_account_config(path)
            cfg.username = clean_user
            cfg.paper_db_path = context_db
            with _paper_connect(context_db) as conn:
                existing = conn.execute(
                    "SELECT is_active FROM paper_account_templates WHERE username=? AND account_id=?",
                    (clean_user, cfg.account_id),
                ).fetchone()
            if existing is not None:
                continue
            cfg.raw_config["_legacy_config_path"] = str(path)
            cfg.raw_config["_paper_db_path"] = _paper_db_path_text(context_db)
            _save_cfg_to_sqlite(cfg, overwrite_existing=True, require_existing=False, template_db_path=context_db)
        except Exception:
            continue

def _daily_plan_source_kwargs(cfg: PaperAccountConfig) -> dict[str, Any]:
    return {
        "data_source": "stock_pool",
        "processed_dir": "",
        "stock_pool_username": cfg.stock_pool_username,
        "stock_pool_template_name": cfg.stock_pool_template_name,
        "stock_pool_db_path": cfg.stock_pool_db_path,
        "stock_pool_market_db_path": str(_market_data_db_path() or ""),
        "stock_pool_feature_legacy_fallback": False,
    }


def _symbol_key(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text.zfill(6) if text.isdigit() else text


def _ts_code(symbol: str) -> str:
    key = _symbol_key(symbol)
    if str(symbol).strip().upper().endswith((".SH", ".SZ")):
        return str(symbol).strip().upper()
    if key.startswith(("6", "9")):
        return f"{key}.SH"
    return f"{key}.SZ"


def _format_date(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


def _next_weekday(date_text: str) -> str:
    current = datetime.strptime(date_text, "%Y%m%d")
    while True:
        current += timedelta(days=1)
        if current.weekday() < 5:
            return _format_date(current)


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"是", "true", "1", "yes", "y", "启用"}:
        return True
    if text in {"否", "false", "0", "no", "n", "停用"}:
        return False
    return default


def _as_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _sheet(df_map: dict[str, pd.DataFrame], name: str, columns: list[str]) -> pd.DataFrame:
    frame = df_map.get(name)
    if frame is None:
        return pd.DataFrame(columns=columns)
    frame = frame.copy()
    for col in columns:
        if col not in frame.columns:
            frame[col] = pd.NA
    return frame[columns]


def _parse_scalar(value: str) -> Any:
    text = value.strip()
    if not text:
        return ""
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    if text in {"是", "否"}:
        return text
    try:
        if any(ch in text for ch in [".", "e", "E"]):
            return float(text)
        return int(text)
    except ValueError:
        return text


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Fallback parser for the project's simple Chinese YAML templates."""
    root: dict[str, Any] = {}
    current_key = ""
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if indent == 0:
            if value:
                root[key] = _parse_scalar(value)
                current_key = ""
            else:
                root[key] = {}
                current_key = key
        elif current_key:
            nested = root.setdefault(current_key, {})
            if isinstance(nested, dict):
                nested[key] = _parse_scalar(value)
    return root


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"模拟账户模板不存在: {path}")
    text = ""
    last_error: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    if not text and last_error is not None:
        raise last_error
    data = yaml.safe_load(text) if yaml is not None else _parse_simple_yaml(text)
    data = data or {}
    if not isinstance(data, dict):
        raise ValueError(f"模拟账户模板格式不正确，根节点必须是对象: {path}")
    return data


def _relative_text(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _normalize_template_dir(config_dir: str | Path) -> Path:
    folder = _normalize_path(config_dir or DEFAULT_CONFIG_DIR)
    return folder.resolve()


def _normalize_template_file_name(file_name: str, account_id: str) -> str:
    raw = str(file_name or "").strip() or f"{account_id}.yaml"
    raw = raw.replace("\\", "/")
    if "/" in raw or raw in {".", ".."} or ".." in Path(raw).parts:
        raise ValueError("模板文件名只能填写文件名，不能包含目录或上级路径")
    if not raw.lower().endswith((".yaml", ".yml")):
        raw = f"{raw}.yaml"
    if not raw.lower().endswith(".yaml"):
        raise ValueError("模板文件必须使用 .yaml 后缀")
    return raw


def _resolve_template_path(config_path: str | Path, config_dir: str | Path) -> Path:
    folder = _normalize_template_dir(config_dir)
    path_text = str(config_path or "").strip()
    if not path_text:
        raise ValueError("请先选择或填写模板路径")
    raw_path = Path(path_text).expanduser()
    if not raw_path.is_absolute() and len(raw_path.parts) == 1:
        path = (folder / raw_path).resolve()
    else:
        path = _normalize_path(path_text).resolve()
    if path.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError("模板路径必须是 .yaml 或 .yml 文件")
    if not _is_relative_to(path, folder):
        raise ValueError("模板路径必须位于当前模板目录内")
    return path


def _template_payload_from_config(cfg: PaperAccountConfig, config_path: Path | str | None = None) -> dict[str, Any]:
    config_path_text = "" if config_path is None else str(config_path)
    file_name = Path(config_path_text).name if config_path_text else f"{cfg.account_id}.sqlite"
    return {
        "username": cfg.username,
        "template_id": _template_id(cfg.username, cfg.account_id),
        "config_dir": "",
        "config_path": config_path_text,
        "file_name": file_name,
        "account_id": cfg.account_id,
        "account_name": cfg.account_name,
        "initial_cash": cfg.initial_cash,
        "stock_pool_username": cfg.stock_pool_username,
        "stock_pool_template_name": cfg.stock_pool_template_name,
        "stock_pool_db_path": cfg.stock_pool_db_path,
        "buy_condition": cfg.buy_condition,
        "sell_condition": cfg.sell_condition,
        "score_expression": cfg.score_expression,
        "top_n": cfg.top_n,
        "entry_offset": cfg.entry_offset,
        "min_hold_days": cfg.min_hold_days,
        "max_hold_days": cfg.max_hold_days,
        "buy_quantity_mode": cfg.buy_quantity_mode,
        "buy_shares": cfg.buy_shares,
        "buy_lot_size": cfg.buy_lot_size,
        "min_buy_amount": cfg.min_buy_amount,
        "buy_min_close": cfg.buy_min_close,
        "buy_max_close": cfg.buy_max_close,
        "price_primary": cfg.price_primary,
        "price_fallback": cfg.price_fallback,
        "price_field": cfg.price_field,
        "skip_if_holding": cfg.skip_if_holding,
        "skip_if_pending_order": cfg.skip_if_pending_order,
        "strict_execution": cfg.strict_execution,
        "buy_fee_rate": cfg.buy_fee_rate,
        "sell_fee_rate": cfg.sell_fee_rate,
        "stamp_tax_sell": cfg.stamp_tax_sell,
        "slippage_bps": cfg.slippage_bps,
        "min_commission": cfg.min_commission,
        "ledger_path": _ledger_storage_id(cfg),
        "ledger_storage": "SQLite",
        "ledger_exists": _ledger_exists(cfg),
        "log_dir": "SQLite运行日志",
        "paper_db_path": _paper_db_path_text(cfg.paper_db_path),
        "raw_config": cfg.raw_config,
    }


def load_paper_account_config(config_path: str | Path) -> PaperAccountConfig:
    path = _normalize_path(config_path)
    data = _read_yaml(path)
    quantity = data.get("买入数量") or {}
    price_filter = data.get("买入价格筛选") or {}
    source = data.get("行情源") or {}
    rules = data.get("交易规则") or {}
    fees = data.get("费用") or {}
    output = data.get("输出") or {}
    stock_pool = data.get("股票池") or {}
    account_id = str(data.get("账户编号") or path.stem).strip()
    account_name = str(data.get("账户名称") or account_id).strip()
    stock_pool_username = str(stock_pool.get("用户") or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME
    stock_pool_template_name = str(stock_pool.get("模板名称") or "").strip()
    if not stock_pool_template_name:
        raise ValueError("模拟账户模板缺少 股票池.模板名称；请在账户模板管理页面选择股票池模板并保存")
    stock_pool_db_path = _stock_pool_db_path_text(stock_pool.get("数据库路径") or "")
    buy_fee_rate = _as_float(fees.get("买入费率", fees.get("买卖费率")), 0.00003)
    sell_fee_rate = _as_float(fees.get("卖出费率", fees.get("买卖费率")), 0.00003)
    ledger_path = output.get("账本路径") or DEFAULT_LEDGER_DIR / f"{account_id}.xlsx"
    log_dir = output.get("日志目录") or DEFAULT_LOG_DIR
    return PaperAccountConfig(
        account_id=account_id,
        account_name=account_name,
        initial_cash=_as_float(data.get("初始资金"), 100_000.0),
        stock_pool_username=stock_pool_username,
        stock_pool_template_name=stock_pool_template_name,
        stock_pool_db_path=stock_pool_db_path,
        buy_condition=str(data.get("买入条件") or "").strip(),
        sell_condition=str(data.get("卖出条件") or "").strip(),
        score_expression=str(data.get("评分表达式") or "m20").strip(),
        top_n=max(1, _as_int(data.get("买入排名数量"), 5)),
        entry_offset=max(1, _as_int(data.get("买入偏移"), 1)),
        min_hold_days=max(0, _as_int(data.get("最短持有天数"), 0)),
        max_hold_days=max(0, _as_int(data.get("最大持有天数"), 15)),
        buy_quantity_mode=str(quantity.get("方式") or "固定股数").strip(),
        buy_shares=max(1, _as_int(quantity.get("股数"), 200)),
        buy_lot_size=max(1, _as_int(quantity.get("每手股数"), 100)),
        min_buy_amount=max(0.0, _as_float(quantity.get("最低买入金额"), 0.0)),
        buy_min_close=max(0.0, _as_float(price_filter.get("最低收盘价"), 0.0)),
        buy_max_close=max(0.0, _as_float(price_filter.get("最高收盘价"), 0.0)),
        price_primary=str(source.get("首选") or "本地日线").strip(),
        price_fallback=str(source.get("备用") or "").strip(),
        price_field=str(source.get("价格字段") or "开盘价").strip(),
        skip_if_holding=_truthy(rules.get("持仓时不重复买入"), True),
        skip_if_pending_order=_truthy(rules.get("有待成交订单时不重复买入"), True),
        strict_execution=_truthy(rules.get("严格成交"), True),
        buy_fee_rate=buy_fee_rate,
        sell_fee_rate=sell_fee_rate,
        stamp_tax_sell=_as_float(fees.get("印花税"), 0.0),
        slippage_bps=_as_float(fees.get("滑点bps"), 0.0),
        min_commission=_as_float(fees.get("最低佣金"), 0.0),
        ledger_path=_normalize_path(ledger_path),
        log_dir=_normalize_path(log_dir),
        raw_config=data,
    )



def _request_username(req: PaperTemplateSaveRequest | PaperTradingRunRequest | None = None, username: str | None = None) -> str:
    if username:
        return _clean_username(username)
    if req is not None and hasattr(req, "username"):
        return _clean_username(getattr(req, "username"))
    return DEFAULT_USERNAME


def _paper_config_from_request(req: PaperTemplateSaveRequest, username: str | None = None) -> PaperAccountConfig:
    clean_user = _request_username(req, username)
    account_id = req.account_id.strip()
    account_name = req.account_name.strip()
    if not account_id:
        raise ValueError("账户编号不能为空")
    if not account_name:
        raise ValueError("账户名称不能为空")
    stock_pool_username = req.stock_pool_username.strip() or clean_user or DEFAULT_USERNAME
    stock_pool_db_path = _stock_pool_db_path_text(req.stock_pool_db_path or "")
    raw_config = _template_config_from_request(
        req,
        _ledger_path_for_account(account_id),
        _log_dir_for_account(clean_user, account_id),
    )
    raw_config["_paper_db_path"] = _paper_db_path_text()
    return PaperAccountConfig(
        account_id=account_id,
        account_name=account_name,
        initial_cash=float(req.initial_cash),
        stock_pool_username=stock_pool_username,
        stock_pool_template_name=req.stock_pool_template_name.strip(),
        stock_pool_db_path=stock_pool_db_path,
        buy_condition=req.buy_condition.strip(),
        sell_condition=req.sell_condition.strip(),
        score_expression=req.score_expression.strip() or "m20",
        top_n=max(1, int(req.top_n)),
        entry_offset=max(1, int(req.entry_offset)),
        min_hold_days=max(0, int(req.min_hold_days)),
        max_hold_days=max(0, int(req.max_hold_days)),
        buy_quantity_mode=req.buy_quantity_mode.strip() or "固定股数",
        buy_shares=max(1, int(req.buy_shares)),
        buy_lot_size=max(1, int(req.buy_lot_size)),
        min_buy_amount=max(0.0, float(req.min_buy_amount)),
        buy_min_close=max(0.0, float(req.buy_min_close)),
        buy_max_close=max(0.0, float(req.buy_max_close)),
        price_primary=req.price_primary.strip() or "东方财富",
        price_fallback=req.price_fallback.strip(),
        price_field=req.price_field.strip() or "开盘价",
        skip_if_holding=bool(req.skip_if_holding),
        skip_if_pending_order=bool(req.skip_if_pending_order),
        strict_execution=bool(req.strict_execution),
        buy_fee_rate=float(req.buy_fee_rate),
        sell_fee_rate=float(req.sell_fee_rate),
        stamp_tax_sell=float(req.stamp_tax_sell),
        slippage_bps=float(req.slippage_bps),
        min_commission=float(req.min_commission),
        ledger_path=_ledger_path_for_account(account_id),
        log_dir=_log_dir_for_account(clean_user, account_id),
        raw_config=raw_config,
        username=clean_user,
        paper_db_path=_paper_db_path(),
    )


def list_paper_account_templates(
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
    username: str = DEFAULT_USERNAME,
) -> list[dict[str, Any]]:
    clean_user = _clean_username(username)
    context_db = _paper_context_db_path(config_dir)
    if not _has_paper_account_templates(context_db, clean_user):
        _legacy_templates_to_sqlite(config_dir, clean_user)
    rows: list[dict[str, Any]] = []
    with _paper_connect(context_db) as conn:
        db_rows = conn.execute(
            """
            SELECT *
            FROM paper_account_templates
            WHERE username=? AND is_active=1
            ORDER BY updated_at DESC, account_id ASC
            """,
            (clean_user,),
        ).fetchall()
    for row in db_rows:
        cfg = _template_config_from_row(row)
        if is_sqlite_only_enabled() and cfg.raw_config.get("_legacy_config_path"):
            continue
        rows.append(
            {
                "username": cfg.username,
                "template_id": _template_id(cfg.username, cfg.account_id),
                "account_id": cfg.account_id,
                "account_name": cfg.account_name,
                "config_path": cfg.account_id,
                "ledger_path": _ledger_storage_id(cfg),
                "ledger_storage": "SQLite",
                "ledger_exists": _ledger_exists(cfg),
                "stock_pool_username": cfg.stock_pool_username,
                "stock_pool_template_name": cfg.stock_pool_template_name,
                "stock_pool_db_path": cfg.stock_pool_db_path,
                "top_n": cfg.top_n,
                "buy_shares": cfg.buy_shares,
                "buy_lot_size": cfg.buy_lot_size,
                "min_buy_amount": cfg.min_buy_amount,
                "buy_min_close": cfg.buy_min_close,
                "buy_max_close": cfg.buy_max_close,
                "price_primary": cfg.price_primary,
            }
        )
    return rows


def _account_id_from_template_selector(
    config_path: str = "",
    account_id: str = "",
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
    username: str = DEFAULT_USERNAME,
) -> str:
    if str(account_id or "").strip():
        return str(account_id).strip()
    text = str(config_path or "").strip()
    if text:
        candidate = Path(text).expanduser()
        if candidate.suffix.lower() in {".yaml", ".yml"}:
            path = candidate.resolve() if candidate.is_absolute() else _resolve_template_path(text, config_dir)
            if not path.exists():
                raise FileNotFoundError(f"模拟账户模板不存在: {path}")
            context_db = _paper_context_db_path(config_dir, path)
            cfg = load_paper_account_config(path)
            cfg.username = _clean_username(username)
            cfg.paper_db_path = context_db
            init_paper_trading_db(context_db)
            with _paper_connect(context_db) as conn:
                existing = conn.execute(
                    "SELECT is_active FROM paper_account_templates WHERE username=? AND account_id=?",
                    (cfg.username, cfg.account_id),
                ).fetchone()
            if existing is not None:
                return cfg.account_id
            cfg.raw_config["_legacy_config_path"] = str(path)
            cfg.raw_config["_paper_db_path"] = _paper_db_path_text(context_db)
            _save_cfg_to_sqlite(cfg, overwrite_existing=True, require_existing=False, template_db_path=context_db)
            return cfg.account_id
        return text
    templates = list_paper_account_templates(config_dir, username=username)
    if not templates:
        raise FileNotFoundError("没有找到任何模拟账户模板")
    return str(templates[0]["account_id"])


def read_paper_account_template(
    config_path: str = "",
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
    account_id: str = "",
    username: str = DEFAULT_USERNAME,
) -> dict[str, Any]:
    context_db = _paper_context_db_path(config_dir, config_path)
    resolved_account_id = _account_id_from_template_selector(config_path, account_id, config_dir, username)
    cfg = _read_template_by_account(resolved_account_id, username, db_path=context_db)
    return _template_payload_from_config(cfg, cfg.account_id)


def _template_config_from_request(req: PaperTemplateSaveRequest, ledger_path: Path, log_dir: Path) -> dict[str, Any]:
    fees: dict[str, Any] = {
        "印花税": req.stamp_tax_sell,
        "滑点bps": req.slippage_bps,
        "最低佣金": req.min_commission,
    }
    if abs(float(req.buy_fee_rate) - float(req.sell_fee_rate)) < 1e-12:
        fees["买卖费率"] = req.buy_fee_rate
    else:
        fees["买入费率"] = req.buy_fee_rate
        fees["卖出费率"] = req.sell_fee_rate
    return {
        "账户编号": req.account_id.strip(),
        "账户名称": req.account_name.strip(),
        "初始资金": req.initial_cash,
        "股票池": {
            "用户": req.stock_pool_username.strip() or DEFAULT_USERNAME,
            "模板名称": req.stock_pool_template_name.strip(),
            "数据库路径": _stock_pool_db_path_text(req.stock_pool_db_path),
        },
        "买入条件": req.buy_condition.strip(),
        "卖出条件": req.sell_condition.strip(),
        "评分表达式": req.score_expression.strip(),
        "买入排名数量": req.top_n,
        "买入偏移": req.entry_offset,
        "最短持有天数": req.min_hold_days,
        "最大持有天数": req.max_hold_days,
        "买入数量": {
            "方式": req.buy_quantity_mode.strip() or "固定股数",
            "股数": req.buy_shares,
            "每手股数": req.buy_lot_size,
            "最低买入金额": req.min_buy_amount,
        },
        "买入价格筛选": {
            "最低收盘价": req.buy_min_close,
            "最高收盘价": req.buy_max_close,
        },
        "行情源": {
            "首选": req.price_primary.strip() or "东方财富",
            "备用": req.price_fallback.strip(),
            "价格字段": req.price_field.strip() or "开盘价",
        },
        "交易规则": {
            "持仓时不重复买入": "是" if req.skip_if_holding else "否",
            "有待成交订单时不重复买入": "是" if req.skip_if_pending_order else "否",
            "严格成交": "是" if req.strict_execution else "否",
        },
        "费用": fees,
        "输出": {
            "账本路径": _paper_db_path_text(),
            "日志目录": "SQLite运行日志",
        },
    }


def _write_template_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is not None:
        text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    else:  # pragma: no cover - PyYAML is available in normal dev/test envs
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                for sub_key, sub_value in value.items():
                    lines.append(f"  {sub_key}: {sub_value}")
            else:
                lines.append(f"{key}: {value}")
        text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")


def _config_from_request(req: PaperTemplateSaveRequest) -> PaperAccountConfig:
    account_id = req.account_id.strip()
    account_name = req.account_name.strip()
    if not account_id:
        raise ValueError("账户编号不能为空")
    if not account_name:
        raise ValueError("账户名称不能为空")
    owner_username = _request_username(req)
    stock_pool_username = _clean_username(req.stock_pool_username or owner_username)
    context_db = _paper_context_db_path(req.config_dir, req.config_path)
    stock_pool_db_path = _stock_pool_db_path_text(req.stock_pool_db_path)
    raw_config = _template_config_from_request(req, _ledger_path_for_account(account_id), _log_dir_for_account(owner_username, account_id))
    raw_config["_paper_db_path"] = _paper_db_path_text(context_db)
    return PaperAccountConfig(
        account_id=account_id,
        account_name=account_name,
        initial_cash=req.initial_cash,
        stock_pool_username=stock_pool_username,
        stock_pool_template_name=req.stock_pool_template_name.strip(),
        stock_pool_db_path=stock_pool_db_path,
        buy_condition=req.buy_condition.strip(),
        sell_condition=req.sell_condition.strip(),
        score_expression=req.score_expression.strip() or "m20",
        top_n=req.top_n,
        entry_offset=req.entry_offset,
        min_hold_days=req.min_hold_days,
        max_hold_days=req.max_hold_days,
        buy_quantity_mode=req.buy_quantity_mode.strip() or "固定股数",
        buy_shares=req.buy_shares,
        buy_lot_size=req.buy_lot_size,
        min_buy_amount=req.min_buy_amount,
        buy_min_close=req.buy_min_close,
        buy_max_close=req.buy_max_close,
        price_primary=req.price_primary.strip() or "东方财富",
        price_fallback=req.price_fallback.strip(),
        price_field=req.price_field.strip() or "开盘价",
        skip_if_holding=req.skip_if_holding,
        skip_if_pending_order=req.skip_if_pending_order,
        strict_execution=req.strict_execution,
        buy_fee_rate=req.buy_fee_rate,
        sell_fee_rate=req.sell_fee_rate,
        stamp_tax_sell=req.stamp_tax_sell,
        slippage_bps=req.slippage_bps,
        min_commission=req.min_commission,
        ledger_path=_ledger_path_for_account(account_id),
        log_dir=_log_dir_for_account(owner_username, account_id),
        raw_config=raw_config,
        username=owner_username,
        paper_db_path=context_db,
    )


def save_paper_account_template(req: PaperTemplateSaveRequest) -> dict[str, Any]:
    cfg = _config_from_request(req)
    read_stock_pool_template(
        template_name=cfg.stock_pool_template_name,
        username=cfg.stock_pool_username,
        db_path=cfg.stock_pool_db_path or None,
    )
    overwrite_existing = bool(req.overwrite_existing)
    if overwrite_existing and req.config_path.strip():
        current_account_id = _account_id_from_template_selector(req.config_path, "", req.config_dir, cfg.username)
        if current_account_id != cfg.account_id:
            raise ValueError("覆盖保存不能切换账户编号；如需新账户请使用另存为新模板")
    cfg = _save_cfg_to_sqlite(cfg, overwrite_existing=overwrite_existing, require_existing=overwrite_existing, template_db_path=cfg.paper_db_path)
    return {
        "template": _template_payload_from_config(cfg, cfg.account_id),
        "message": f"模板已保存到 SQLite：{cfg.account_name}；账本数据未被修改。",
    }


def delete_paper_account_template(
    config_path: str = "",
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
    account_id: str = "",
    username: str = DEFAULT_USERNAME,
) -> dict[str, Any]:
    clean_user = _clean_username(username)
    context_db = _paper_context_db_path(config_dir, config_path)
    resolved_account_id = _account_id_from_template_selector(config_path, account_id, config_dir, clean_user)
    cfg = _read_template_by_account(resolved_account_id, clean_user, db_path=context_db)
    init_paper_trading_db(context_db)
    with _paper_connect(context_db) as conn:
        conn.execute(
            "UPDATE paper_account_templates SET is_active=0, updated_at=? WHERE username=? AND account_id=?",
            (_now_text(), clean_user, resolved_account_id),
        )
        conn.commit()
    return {
        "deleted_template_path": resolved_account_id,
        "account_id": resolved_account_id,
        "ledger_path": _ledger_storage_id(cfg),
        "ledger_storage": "SQLite",
        "ledger_exists": _ledger_exists(cfg),
        "message": f"模板已删除：{cfg.account_name}；SQLite 账本数据保留不动。",
    }


def _empty_ledger() -> dict[str, pd.DataFrame]:
    return {
        "配置快照": pd.DataFrame(columns=CONFIG_COLUMNS),
        "待执行订单": pd.DataFrame(columns=PENDING_COLUMNS),
        "成交流水": pd.DataFrame(columns=TRADE_COLUMNS),
        "当前持仓": pd.DataFrame(columns=HOLDING_COLUMNS),
        "每日资产": pd.DataFrame(columns=ASSET_COLUMNS),
        "运行日志": pd.DataFrame(columns=LOG_COLUMNS),
    }


def _row_key(row: dict[str, Any], index: int, columns: list[str]) -> str:
    for key in ("订单编号", "交易编号"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    if "日期" in columns and row.get("日期"):
        return str(row.get("日期"))
    if "股票代码" in columns and row.get("股票代码"):
        parts = [str(row.get("股票代码") or "")]
        for key in ("买入日期", "来源订单编号", "最后估值日期"):
            if row.get(key):
                parts.append(str(row.get(key)))
        return "|".join(parts)
    if "时间" in columns:
        return f"{index:08d}"
    return f"{index:08d}"


def _read_ledger(cfg_or_path: PaperAccountConfig | Path) -> dict[str, pd.DataFrame]:
    if isinstance(cfg_or_path, PaperAccountConfig):
        cfg = cfg_or_path
        init_paper_trading_db(cfg.paper_db_path)
        ledger = _empty_ledger()
        with _paper_connect(cfg.paper_db_path) as conn:
            for sheet_name, (table_name, columns) in LEDGER_TABLES.items():
                rows = conn.execute(
                    f"SELECT row_json FROM {table_name} WHERE username=? AND account_id=? ORDER BY position ASC",
                    (_clean_username(cfg.username), cfg.account_id),
                ).fetchall()
                decoded = [_json_loads(row["row_json"], {}) for row in rows]
                frame = pd.DataFrame([row for row in decoded if isinstance(row, dict)])
                for col in columns:
                    if col not in frame.columns:
                        frame[col] = pd.NA
                ledger[sheet_name] = frame[columns]
        return ledger
    path = Path(cfg_or_path)
    if not path.exists():
        return _empty_ledger()
    loaded = pd.read_excel(path, sheet_name=None, dtype=object)
    return {
        "配置快照": _sheet(loaded, "配置快照", CONFIG_COLUMNS),
        "待执行订单": _sheet(loaded, "待执行订单", PENDING_COLUMNS),
        "成交流水": _sheet(loaded, "成交流水", TRADE_COLUMNS),
        "当前持仓": _sheet(loaded, "当前持仓", HOLDING_COLUMNS),
        "每日资产": _sheet(loaded, "每日资产", ASSET_COLUMNS),
        "运行日志": _sheet(loaded, "运行日志", LOG_COLUMNS),
    }


def _write_ledger(cfg_or_path: PaperAccountConfig | Path, ledger: dict[str, pd.DataFrame]) -> None:
    if isinstance(cfg_or_path, PaperAccountConfig):
        cfg = cfg_or_path
        init_paper_trading_db(cfg.paper_db_path)
        now = _now_text()
        with _paper_connect(cfg.paper_db_path) as conn:
            for sheet_name, (table_name, columns) in LEDGER_TABLES.items():
                frame = ledger.get(sheet_name, pd.DataFrame(columns=columns)).copy()
                for col in columns:
                    if col not in frame.columns:
                        frame[col] = pd.NA
                frame = frame[columns].astype(object).where(pd.notna(frame), None)
                conn.execute(
                    f"DELETE FROM {table_name} WHERE username=? AND account_id=?",
                    (_clean_username(cfg.username), cfg.account_id),
                )
                for position, row in enumerate(frame.to_dict(orient="records")):
                    if table_name == "paper_config_snapshot":
                        conn.execute(
                            f"""
                            INSERT INTO {table_name} (username, account_id, position, row_json, updated_at)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (_clean_username(cfg.username), cfg.account_id, position, _json_dumps(row), now),
                        )
                    else:
                        key = _row_key(row, position, columns)
                        conn.execute(
                            f"""
                            INSERT INTO {table_name} (username, account_id, row_key, position, row_json, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (_clean_username(cfg.username), cfg.account_id, key, position, _json_dumps(row), now),
                        )
            conn.commit()
        return
    path = Path(cfg_or_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name in SHEET_NAMES:
            ledger[sheet_name].to_excel(writer, sheet_name=sheet_name, index=False)


def _config_snapshot(cfg: PaperAccountConfig) -> pd.DataFrame:
    rows = [
        ("账户编号", cfg.account_id),
        ("账户名称", cfg.account_name),
        ("初始资金", cfg.initial_cash),
        ("股票池用户", cfg.stock_pool_username),
        ("股票池模板", cfg.stock_pool_template_name),
        ("股票池数据库", cfg.stock_pool_db_path),
        ("买入条件", cfg.buy_condition),
        ("卖出条件", cfg.sell_condition),
        ("评分表达式", cfg.score_expression),
        ("买入排名数量", cfg.top_n),
        ("买入偏移", cfg.entry_offset),
        ("最短持有天数", cfg.min_hold_days),
        ("最大持有天数", cfg.max_hold_days),
        ("买入数量方式", cfg.buy_quantity_mode),
        ("买入股数", cfg.buy_shares),
        ("每手股数", cfg.buy_lot_size),
        ("最低买入金额", cfg.min_buy_amount),
        ("买入最低收盘价", cfg.buy_min_close),
        ("买入最高收盘价", cfg.buy_max_close),
        ("行情源首选", cfg.price_primary),
        ("行情源备用", cfg.price_fallback),
        ("价格字段", cfg.price_field),
        ("持仓时不重复买入", "是" if cfg.skip_if_holding else "否"),
        ("有待成交订单时不重复买入", "是" if cfg.skip_if_pending_order else "否"),
        ("严格成交", "是" if cfg.strict_execution else "否"),
        ("买入费率", cfg.buy_fee_rate),
        ("卖出费率", cfg.sell_fee_rate),
        ("印花税", cfg.stamp_tax_sell),
        ("滑点bps", cfg.slippage_bps),
        ("最低佣金", cfg.min_commission),
        ("账本存储", _ledger_storage_id(cfg)),
        ("日志存储", "SQLite运行日志"),
        ("最后更新时间", _now_text()),
    ]
    return pd.DataFrame(rows, columns=CONFIG_COLUMNS)


def _append_log(ledger: dict[str, pd.DataFrame], cfg: PaperAccountConfig, action: str, level: str, message: str) -> None:
    row = {
        "时间": _now_text(),
        "账户编号": cfg.account_id,
        "账户名称": cfg.account_name,
        "动作": action,
        "级别": level,
        "信息": message,
    }
    ledger["运行日志"] = pd.concat([ledger["运行日志"], pd.DataFrame([row])], ignore_index=True)


def _write_text_log(cfg: PaperAccountConfig, message: str) -> None:
    # 多账户模拟交易的运行日志统一保存在 SQLite 账本表，保留函数名兼容既有调用点。
    return None


def _cash_balance(cfg: PaperAccountConfig, trades: pd.DataFrame) -> float:
    if trades.empty:
        return round(float(cfg.initial_cash), 2)
    cash = float(cfg.initial_cash)
    for _, row in trades.iterrows():
        direction = str(row.get("交易方向") or "")
        total = _as_float(row.get("总金额"), 0.0)
        if direction == "买入":
            cash -= total
        elif direction == "卖出":
            cash += total
    return round(cash, 2)


def _open_holding_symbols(holdings: pd.DataFrame) -> set[str]:
    if holdings.empty:
        return set()
    return {_symbol_key(value) for value in holdings["股票代码"].dropna().astype(str).tolist()}


def _pending_buy_symbols(pending: pd.DataFrame) -> set[str]:
    if pending.empty:
        return set()
    frame = pending[(pending["状态"].astype(str) == "待执行") & (pending["订单方向"].astype(str) == "买入")]
    return {_symbol_key(value) for value in frame["股票代码"].dropna().astype(str).tolist()}


def _daily_holdings_from_ledger(holdings: pd.DataFrame) -> list[DailyHolding]:
    out: list[DailyHolding] = []
    for _, row in holdings.iterrows():
        symbol = str(row.get("股票代码") or "").strip()
        buy_date = str(row.get("买入日期") or "").strip()
        buy_price = _as_float(row.get("买入价格"), 0.0)
        shares = _as_int(row.get("股数"), 0)
        if not symbol or not buy_date or buy_price <= 0 or shares <= 0:
            continue
        out.append(
            DailyHolding(
                symbol=symbol,
                buy_date=buy_date,
                buy_price=buy_price,
                shares=shares,
                name=str(row.get("股票名称") or ""),
            )
        )
    return out


def _order_id(cfg: PaperAccountConfig, direction: str, signal_date: str, execute_date: str, symbol: str) -> str:
    return f"{cfg.account_id}-{signal_date}-{execute_date}-{direction}-{_symbol_key(symbol)}"


def _trade_id(cfg: PaperAccountConfig, trade_date: str, symbol: str, direction: str, index: int) -> str:
    return f"{cfg.account_id}-{trade_date}-{direction}-{_symbol_key(symbol)}-{index:04d}"


def _dedupe_append(base: pd.DataFrame, rows: list[dict[str, Any]], key: str, columns: list[str]) -> tuple[pd.DataFrame, int]:
    if not rows:
        return base, 0
    existing = set(base[key].dropna().astype(str).tolist()) if key in base.columns else set()
    filtered = [row for row in rows if str(row.get(key) or "") not in existing]
    if not filtered:
        return base, 0
    return pd.concat([base, pd.DataFrame(filtered)], ignore_index=True)[columns], len(filtered)


def _resolve_signal_date(cfg: PaperAccountConfig, signal_date: str) -> str:
    requested = str(signal_date or "").strip()
    return _latest_available_date(cfg, requested)


def _planned_trade_date(cfg: PaperAccountConfig, planned_date: Any, signal_date: str) -> str:
    text = str(planned_date or "").strip()
    if text and text != "下一交易日":
        return text
    return _next_trade_date_from_stock_pool(cfg, signal_date)


def _round_up_to_lot(shares: int, lot_size: int) -> int:
    lot = max(1, int(lot_size))
    return int(math.ceil(max(0, int(shares)) / lot) * lot)


def _planned_buy_shares(cfg: PaperAccountConfig, signal_close: float | None) -> int:
    fixed_shares = _round_up_to_lot(cfg.buy_shares, cfg.buy_lot_size)
    if cfg.min_buy_amount <= 0 or signal_close is None or signal_close <= 0:
        return fixed_shares
    min_shares = _round_up_to_lot(math.ceil(cfg.min_buy_amount / signal_close), cfg.buy_lot_size)
    return max(fixed_shares, min_shares)


def _buy_price_filter_reason(cfg: PaperAccountConfig, signal_close: float | None) -> str:
    if cfg.buy_min_close <= 0 and cfg.buy_max_close <= 0 and cfg.min_buy_amount <= 0:
        return ""
    if signal_close is None or signal_close <= 0:
        return "缺少有效 T 日收盘价，无法做买入价格筛选或最低买入金额计算"
    if cfg.buy_min_close > 0 and signal_close < cfg.buy_min_close:
        return f"T日收盘价 {signal_close:.2f} 低于最低收盘价 {cfg.buy_min_close:.2f}"
    if cfg.buy_max_close > 0 and signal_close > cfg.buy_max_close:
        return f"T日收盘价 {signal_close:.2f} 高于最高收盘价 {cfg.buy_max_close:.2f}"
    return ""


def _generate_orders(cfg: PaperAccountConfig, ledger: dict[str, pd.DataFrame], signal_date: str) -> dict[str, Any]:
    holdings = ledger["当前持仓"]
    pending = ledger["待执行订单"]
    holding_symbols = _open_holding_symbols(holdings)
    pending_buy_symbols = _pending_buy_symbols(pending)
    request_top_n = min(
        500,
        max(cfg.top_n, cfg.top_n * 10, 100) + (len(pending_buy_symbols) if cfg.skip_if_pending_order else 0),
    )
    plan = build_daily_plan(
        DailyPlanRequest(
            **_daily_plan_source_kwargs(cfg),
            signal_date=signal_date,
            buy_condition=cfg.buy_condition,
            sell_condition=cfg.sell_condition,
            score_expression=cfg.score_expression,
            top_n=max(cfg.top_n, request_top_n),
            entry_offset=cfg.entry_offset,
            min_hold_days=cfg.min_hold_days,
            max_hold_days=cfg.max_hold_days,
            per_trade_budget=max(cfg.buy_shares, 1),
            lot_size=1,
            holdings=_daily_holdings_from_ledger(holdings),
        )
    )
    actual_signal_date = str(plan["summary"]["signal_date"])
    created_at = _now_text()
    new_rows: list[dict[str, Any]] = []
    buy_count = 0
    price_filtered_count = 0
    for row in plan["buy_rows"]:
        symbol_key = _symbol_key(row["symbol"])
        if cfg.skip_if_holding and symbol_key in holding_symbols:
            continue
        if cfg.skip_if_pending_order and symbol_key in pending_buy_symbols:
            continue
        signal_close = to_float(row.get("signal_raw_close"))
        price_filter_reason = _buy_price_filter_reason(cfg, signal_close)
        if price_filter_reason:
            price_filtered_count += 1
            continue
        execute_date = _planned_trade_date(cfg, row.get("planned_buy_date"), actual_signal_date)
        planned_shares = _planned_buy_shares(cfg, signal_close)
        new_rows.append(
            {
                "订单编号": _order_id(cfg, "买入", actual_signal_date, execute_date, row["symbol"]),
                "账户编号": cfg.account_id,
                "账户名称": cfg.account_name,
                "订单方向": "买入",
                "状态": "待执行",
                "信号日期": actual_signal_date,
                "计划执行日期": execute_date,
                "股票代码": _ts_code(str(row["symbol"])),
                "股票名称": row.get("name", ""),
                "排名": row.get("rank"),
                "评分": row.get("score"),
                "信号收盘价": round(float(signal_close), 4) if signal_close is not None else math.nan,
                "计划股数": planned_shares,
                "最低买入金额": cfg.min_buy_amount,
                "生成时间": created_at,
                "执行时间": "",
                "成交价格": math.nan,
                "成交金额": math.nan,
                "手续费": math.nan,
                "印花税": math.nan,
                "滑点bps": cfg.slippage_bps,
                "失败原因": "",
            }
        )
        buy_count += 1
        if buy_count >= cfg.top_n:
            break

    for row in plan["sell_rows"]:
        execute_date = _planned_trade_date(cfg, row.get("planned_sell_date"), actual_signal_date)
        new_rows.append(
            {
                "订单编号": _order_id(cfg, "卖出", actual_signal_date, execute_date, row["symbol"]),
                "账户编号": cfg.account_id,
                "账户名称": cfg.account_name,
                "订单方向": "卖出",
                "状态": "待执行",
                "信号日期": actual_signal_date,
                "计划执行日期": execute_date,
                "股票代码": _ts_code(str(row["symbol"])),
                "股票名称": row.get("name", ""),
                "排名": "",
                "评分": "",
                "信号收盘价": row.get("current_raw_close", math.nan),
                "计划股数": row.get("shares", 0),
                "最低买入金额": "",
                "生成时间": created_at,
                "执行时间": "",
                "成交价格": math.nan,
                "成交金额": math.nan,
                "手续费": math.nan,
                "印花税": math.nan,
                "滑点bps": cfg.slippage_bps,
                "失败原因": row.get("sell_reason", ""),
            }
        )

    ledger["待执行订单"], added_count = _dedupe_append(ledger["待执行订单"], new_rows, "订单编号", PENDING_COLUMNS)
    _append_log(ledger, cfg, "生成订单", "信息", f"信号日 {actual_signal_date} 生成 {added_count} 条新订单")
    _write_text_log(cfg, f"生成订单: 信号日 {actual_signal_date}, 新订单 {added_count}")
    return {
        "signal_date": actual_signal_date,
        "planned_buy_count": sum(1 for row in new_rows if row["订单方向"] == "买入"),
        "planned_sell_count": sum(1 for row in new_rows if row["订单方向"] == "卖出"),
        "price_filtered_count": price_filtered_count,
        "added_order_count": added_count,
        "plan_summary": plan["summary"],
    }


class StockPoolDailyPriceProvider:
    def __init__(self, cfg: PaperAccountConfig, price_field: str) -> None:
        self.username = cfg.stock_pool_username
        self.template_name = cfg.stock_pool_template_name
        self.db_path = _stock_pool_db_path(cfg.stock_pool_db_path)
        self.price_field = price_field
        self.template_by_symbol = {
            str(item["symbol"]).zfill(6): item
            for item in read_template_symbols(self.username, self.template_name, db_path=self.db_path)
        }

    def quote(self, symbol: str, trade_date: str) -> PriceQuote:
        key = _symbol_key(symbol)
        template_stock = self.template_by_symbol.get(key)
        if template_stock is None:
            raise ValueError(f"{symbol} 不在股票池模板中: {self.username}/{self.template_name}")
        data = market_data_store.read_feature_row(
            key,
            str(trade_date),
            db_path=_market_data_db_path(),
            legacy_db_path=market_data_store.DISABLE_LEGACY_FALLBACK,
        )
        if data is None:
            raise ValueError(f"{symbol} 没有 {trade_date} 的market data日线数据")
        price_col = "raw_open" if "开盘" in self.price_field else "raw_close"
        price = to_float(data.get(price_col))
        if price is None or price <= 0:
            raise ValueError(f"{symbol} {trade_date} 缺少有效 {price_col}")
        close_price = to_float(data.get("raw_close"))
        return PriceQuote(
            symbol=_ts_code(str(data.get("ts_code") or template_stock.get("ts_code") or key)),
            name=str(data.get("name") or template_stock.get("stock_name") or ""),
            trade_date=str(data.get("trade_date") or trade_date),
            price=float(price),
            close_price=close_price,
            can_buy=_truthy(data.get("can_buy_open_t"), True),
            can_sell=_truthy(data.get("can_sell_t"), True),
            source="market data SQLite",
        )


class RealtimeQuoteProvider:
    def __init__(self, primary: str, fallback: str, price_field: str) -> None:
        self.primary = primary
        self.fallback = fallback
        self.price_field = price_field

    def quote(self, symbol: str, trade_date: str) -> PriceQuote:
        errors: list[str] = []
        for source in [self.primary, self.fallback]:
            source = str(source or "").strip()
            if not source:
                continue
            try:
                if "腾讯" in source:
                    return self._quote_tencent(symbol, trade_date)
                if "东方" in source or "东财" in source:
                    return self._quote_eastmoney(symbol, trade_date)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{source}: {exc}")
        raise ValueError("实时行情获取失败：" + "；".join(errors))

    def _quote_tencent(self, symbol: str, trade_date: str) -> PriceQuote:
        key = _symbol_key(symbol)
        market = "sh" if key.startswith(("6", "9")) else "sz"
        url = f"https://qt.gtimg.cn/q={market}{key}"
        text = httpx.get(url, timeout=5.0).text
        if "~" not in text:
            raise ValueError("腾讯行情返回格式异常")
        parts = text.split('"')[1].split("~")
        name = parts[1]
        current = _as_float(parts[3], 0.0)
        open_price = _as_float(parts[5], 0.0)
        price = open_price if "开盘" in self.price_field and open_price > 0 else current
        if price <= 0:
            raise ValueError("腾讯行情缺少有效价格")
        return PriceQuote(_ts_code(symbol), name, trade_date, price, current, True, True, "腾讯股票")

    def _quote_eastmoney(self, symbol: str, trade_date: str) -> PriceQuote:
        key = _symbol_key(symbol)
        market = "1" if key.startswith(("6", "9")) else "0"
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        params = {"secid": f"{market}.{key}", "fields": "f43,f46,f57,f58"}
        payload = httpx.get(url, params=params, timeout=5.0).json()
        data = payload.get("data") or {}
        name = str(data.get("f58") or "")
        current = _as_float(data.get("f43"), 0.0) / 100.0
        open_price = _as_float(data.get("f46"), 0.0) / 100.0
        price = open_price if "开盘" in self.price_field and open_price > 0 else current
        if price <= 0:
            raise ValueError("东方财富行情缺少有效价格")
        return PriceQuote(_ts_code(symbol), name, trade_date, price, current, True, True, "东方财富")


def _price_provider(cfg: PaperAccountConfig) -> StockPoolDailyPriceProvider | RealtimeQuoteProvider:
    if "本地" in cfg.price_primary or "日线" in cfg.price_primary or "SQLite" in cfg.price_primary:
        return StockPoolDailyPriceProvider(cfg, cfg.price_field)
    return RealtimeQuoteProvider(cfg.price_primary, cfg.price_fallback, cfg.price_field)


def _fee(amount: float, rate: float, min_commission: float) -> float:
    if amount <= 0:
        return 0.0
    return round(max(float(amount) * float(rate), float(min_commission)), 2)


def _execute_orders(cfg: PaperAccountConfig, ledger: dict[str, pd.DataFrame], trade_date: str) -> dict[str, Any]:
    provider = _price_provider(cfg)
    pending = ledger["待执行订单"].copy()
    trades = ledger["成交流水"].copy()
    holdings = ledger["当前持仓"].copy()
    cash = _cash_balance(cfg, trades)
    executed_count = 0
    failed_count = 0
    trade_rows: list[dict[str, Any]] = []

    due_orders: list[tuple[int, Any]] = []
    for position, (idx, order) in enumerate(pending.iterrows()):
        if str(order.get("状态") or "") != "待执行":
            continue
        planned_date = str(order.get("计划执行日期") or "")
        if planned_date > trade_date:
            continue
        due_orders.append((position, idx))

    def _execution_order_key(item: tuple[int, Any]) -> tuple[int, str, int]:
        position, idx = item
        order = pending.loc[idx]
        direction = str(order.get("订单方向") or "")
        direction_rank = 0 if direction == "卖出" else 1 if direction == "买入" else 2
        planned_date = str(order.get("计划执行日期") or "")
        return direction_rank, planned_date, position

    # 同一天既有卖出又有买入时，先卖出释放现金，再执行新买入。
    for _, idx in sorted(due_orders, key=_execution_order_key):
        order = pending.loc[idx]
        direction = str(order.get("订单方向") or "")
        symbol = str(order.get("股票代码") or "")
        shares = _as_int(order.get("计划股数"), 0)
        try:
            quote = provider.quote(symbol, trade_date)
            if direction == "买入":
                if cfg.strict_execution and not quote.can_buy:
                    raise ValueError("开盘不可买入")
                if cfg.skip_if_holding and _symbol_key(symbol) in _open_holding_symbols(holdings):
                    raise ValueError("当前已持仓，跳过重复买入")
                price = round(float(quote.price) * (1.0 + cfg.slippage_bps / 10000.0), 4)
                gross = round(price * shares, 2)
                commission = _fee(gross, cfg.buy_fee_rate, cfg.min_commission)
                total = round(gross + commission, 2)
                if total > cash:
                    raise ValueError(f"现金不足：需要 {total:.2f}，当前 {cash:.2f}")
                cash = round(cash - total, 2)
                holding = {
                    "账户编号": cfg.account_id,
                    "账户名称": cfg.account_name,
                    "股票代码": quote.symbol,
                    "股票名称": quote.name or order.get("股票名称", ""),
                    "买入日期": trade_date,
                    "买入价格": price,
                    "股数": shares,
                    "买入成交金额": gross,
                    "买入手续费": commission,
                    "买入总成本": total,
                    "当前价格": quote.close_price or price,
                    "当前市值": round((quote.close_price or price) * shares, 2),
                    "浮动盈亏": round((quote.close_price or price) * shares - total, 2),
                    "浮动收益率": round(((quote.close_price or price) * shares - total) / total, 6) if total else 0.0,
                    "持有天数": 0,
                    "最后估值日期": trade_date,
                    "来源订单编号": order.get("订单编号", ""),
                }
                holdings = pd.concat([holdings, pd.DataFrame([holding])], ignore_index=True)[HOLDING_COLUMNS]
                trade_total = total
                realized_pnl = math.nan
                return_rate = math.nan
                remark = f"{quote.source}成交"
            elif direction == "卖出":
                if cfg.strict_execution and not quote.can_sell:
                    raise ValueError("开盘不可卖出")
                matched = holdings[holdings["股票代码"].astype(str).map(_symbol_key) == _symbol_key(symbol)]
                if matched.empty:
                    raise ValueError("没有对应持仓")
                hold_idx = matched.index[0]
                hold = holdings.loc[hold_idx]
                shares = min(shares, _as_int(hold.get("股数"), 0))
                price = round(float(quote.price) * (1.0 - cfg.slippage_bps / 10000.0), 4)
                gross = round(price * shares, 2)
                commission = _fee(gross, cfg.sell_fee_rate, cfg.min_commission)
                stamp_tax = round(gross * cfg.stamp_tax_sell, 2)
                trade_total = round(gross - commission - stamp_tax, 2)
                buy_cost = _as_float(hold.get("买入总成本"), 0.0)
                realized_pnl = round(trade_total - buy_cost, 2)
                return_rate = round(realized_pnl / buy_cost, 6) if buy_cost > 0 else 0.0
                cash = round(cash + trade_total, 2)
                holdings = holdings.drop(index=hold_idx).reset_index(drop=True)[HOLDING_COLUMNS]
                remark = f"{quote.source}成交"
            else:
                raise ValueError(f"未知订单方向: {direction}")

            pending.loc[idx, "状态"] = "已成交"
            pending.loc[idx, "执行时间"] = _now_text()
            pending.loc[idx, "成交价格"] = price
            pending.loc[idx, "成交金额"] = gross
            pending.loc[idx, "手续费"] = commission
            pending.loc[idx, "印花税"] = stamp_tax if direction == "卖出" else 0.0
            pending.loc[idx, "失败原因"] = ""
            trade_row = {
                "交易编号": _trade_id(cfg, trade_date, symbol, direction, len(trades) + len(trade_rows) + 1),
                "账户编号": cfg.account_id,
                "账户名称": cfg.account_name,
                "订单编号": order.get("订单编号", ""),
                "交易日期": trade_date,
                "交易方向": direction,
                "股票代码": _ts_code(symbol),
                "股票名称": quote.name or order.get("股票名称", ""),
                "成交价格": price,
                "股数": shares,
                "成交金额": gross,
                "手续费": commission,
                "印花税": stamp_tax if direction == "卖出" else 0.0,
                "总金额": trade_total,
                "买入成本": buy_cost if direction == "卖出" else trade_total,
                "实现盈亏": realized_pnl,
                "收益率": return_rate,
                "现金余额": cash,
                "备注": remark,
            }
            trade_rows.append(trade_row)
            executed_count += 1
        except Exception as exc:  # noqa: BLE001
            pending.loc[idx, "状态"] = "执行失败"
            pending.loc[idx, "执行时间"] = _now_text()
            pending.loc[idx, "失败原因"] = str(exc)
            failed_count += 1

    if trade_rows:
        trades = pd.concat([trades, pd.DataFrame(trade_rows)], ignore_index=True)[TRADE_COLUMNS]
    ledger["待执行订单"] = pending[PENDING_COLUMNS]
    ledger["成交流水"] = trades
    ledger["当前持仓"] = holdings[HOLDING_COLUMNS]
    _append_log(ledger, cfg, "执行订单", "信息", f"交易日 {trade_date} 成交 {executed_count} 条，失败 {failed_count} 条")
    _write_text_log(cfg, f"执行订单: 交易日 {trade_date}, 成交 {executed_count}, 失败 {failed_count}")
    return {"trade_date": trade_date, "executed_count": executed_count, "failed_count": failed_count, "cash": cash}


def _mark_to_market(cfg: PaperAccountConfig, ledger: dict[str, pd.DataFrame], trade_date: str, note: str = "收盘估值") -> dict[str, Any]:
    provider = StockPoolDailyPriceProvider(cfg, "收盘价")
    holdings = ledger["当前持仓"].copy()
    market_value = 0.0
    updated = 0
    for idx, row in holdings.iterrows():
        symbol = str(row.get("股票代码") or "")
        try:
            quote = provider.quote(symbol, trade_date)
            price = float(quote.close_price or quote.price)
            shares = _as_int(row.get("股数"), 0)
            cost = _as_float(row.get("买入总成本"), 0.0)
            value = round(price * shares, 2)
            buy_date = str(row.get("买入日期") or "")
            holding_days = _count_trade_days(cfg, symbol, buy_date, trade_date)
            holdings.loc[idx, "当前价格"] = round(price, 4)
            holdings.loc[idx, "当前市值"] = value
            holdings.loc[idx, "浮动盈亏"] = round(value - cost, 2)
            holdings.loc[idx, "浮动收益率"] = round((value - cost) / cost, 6) if cost > 0 else 0.0
            holdings.loc[idx, "持有天数"] = holding_days
            holdings.loc[idx, "最后估值日期"] = trade_date
            market_value += value
            updated += 1
        except Exception as exc:  # noqa: BLE001
            fallback_value = _as_float(row.get("当前市值"), 0.0)
            market_value += fallback_value
            _append_log(ledger, cfg, "收盘估值", "警告", f"{symbol} 估值失败: {exc}")
    trades = ledger["成交流水"]
    cash = _cash_balance(cfg, trades)
    total = round(cash + market_value, 2)
    asset_row = {
        "账户编号": cfg.account_id,
        "账户名称": cfg.account_name,
        "日期": trade_date,
        "现金": cash,
        "持仓市值": round(market_value, 2),
        "总资产": total,
        "初始资金": cfg.initial_cash,
        "累计收益": round(total / cfg.initial_cash - 1.0, 6) if cfg.initial_cash > 0 else 0.0,
        "持仓数量": len(holdings),
        "备注": note,
    }
    assets = ledger["每日资产"]
    if not assets.empty:
        assets = assets[~((assets["账户编号"].astype(str) == cfg.account_id) & (assets["日期"].astype(str) == trade_date))]
    ledger["每日资产"] = pd.concat([assets, pd.DataFrame([asset_row])], ignore_index=True)[ASSET_COLUMNS]
    ledger["当前持仓"] = holdings[HOLDING_COLUMNS]
    _append_log(ledger, cfg, "收盘估值", "信息", f"{trade_date} 更新 {updated} 个持仓，总资产 {total:.2f}")
    _write_text_log(cfg, f"收盘估值: {trade_date}, 总资产 {total:.2f}")
    return {"trade_date": trade_date, "cash": cash, "market_value": round(market_value, 2), "total_equity": total, "updated_holding_count": updated}


def _china_now() -> datetime:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    return datetime.now()


def _today_china_text() -> str:
    return _china_now().strftime("%Y%m%d")


def _template_stock_by_symbol(cfg: PaperAccountConfig) -> dict[str, dict[str, Any]]:
    rows = read_template_symbols(
        cfg.stock_pool_username,
        cfg.stock_pool_template_name,
        db_path=_stock_pool_db_path(cfg.stock_pool_db_path),
    )
    return {str(row["symbol"]).zfill(6): row for row in rows}


def _template_market_rows(cfg: PaperAccountConfig, start_date: str = "", end_date: str = "") -> list[dict[str, Any]]:
    stock_by_symbol = _template_stock_by_symbol(cfg)
    if not stock_by_symbol:
        return []
    return market_data_store.read_feature_rows(
        list(stock_by_symbol),
        start_date=start_date,
        end_date=end_date,
        db_path=_market_data_db_path(),
        legacy_db_path=market_data_store.DISABLE_LEGACY_FALLBACK,
    )


def _stock_pool_has_trade_date(cfg: PaperAccountConfig, trade_date: str) -> bool:
    for row in _template_market_rows(cfg, start_date=str(trade_date), end_date=str(trade_date)):
        raw_close = to_float(row.get("raw_close"))
        close = to_float(row.get("close"))
        if raw_close is not None and raw_close > 0 and close is not None and close > 0:
            return True
    return False


def _realtime_market_note(cfg: PaperAccountConfig, trade_date: str) -> str:
    now = _china_now()
    today = now.strftime("%Y%m%d")
    if trade_date != today:
        return "动作日期不是今天，实时行情源仍返回当前最新价，不是历史日期价格"

    if not _stock_pool_has_trade_date(cfg, trade_date) and now.weekday() >= 5:
        return "周末或股票池SQLite尚无当天数据，行情源通常返回最近交易日收盘价或最后可用价格"

    current_minutes = now.hour * 60 + now.minute
    if current_minutes < 9 * 60 + 30:
        return "交易日未开盘，行情源通常返回昨收或集合竞价前后的最新可用价格"
    if 9 * 60 + 30 <= current_minutes <= 11 * 60 + 30:
        return "交易时段，按行情源盘中最新价估值"
    if 11 * 60 + 30 < current_minutes < 13 * 60:
        return "午间休市，按上午收盘前后的最新可用价格估值"
    if 13 * 60 <= current_minutes <= 15 * 60:
        return "交易时段，按行情源盘中最新价估值"
    return "交易日已收盘，行情源通常返回当日收盘价或收盘后的最新可用价格"



def _realtime_price_provider(cfg: PaperAccountConfig) -> RealtimeQuoteProvider:
    primary = cfg.price_primary
    fallback = cfg.price_fallback
    if "本地" in primary or "日线" in primary:
        primary = "东方财富"
        fallback = fallback or "腾讯股票"
    if not fallback or "本地" in fallback or "日线" in fallback:
        fallback = "腾讯股票"
    return RealtimeQuoteProvider(primary, fallback, "最新价")


def _refresh_realtime_positions(cfg: PaperAccountConfig, ledger: dict[str, pd.DataFrame], trade_date: str) -> dict[str, Any]:
    trade_date = trade_date or _today_china_text()
    provider = _realtime_price_provider(cfg)
    holdings = ledger["当前持仓"].copy()
    market_value = 0.0
    updated = 0
    failed = 0
    sources: set[str] = set()
    market_note = _realtime_market_note(cfg, trade_date)

    for idx, row in holdings.iterrows():
        symbol = str(row.get("股票代码") or "")
        try:
            quote = provider.quote(symbol, trade_date)
            price = float(quote.close_price or quote.price)
            shares = _as_int(row.get("股数"), 0)
            cost = _as_float(row.get("买入总成本"), 0.0)
            value = round(price * shares, 2)
            buy_date = str(row.get("买入日期") or "")
            holding_days = _count_trade_days(cfg, symbol, buy_date, trade_date)
            if holding_days <= 0 and buy_date != trade_date:
                holding_days = _as_int(row.get("持有天数"), 0)
            holdings.loc[idx, "当前价格"] = round(price, 4)
            holdings.loc[idx, "当前市值"] = value
            holdings.loc[idx, "浮动盈亏"] = round(value - cost, 2)
            holdings.loc[idx, "浮动收益率"] = round((value - cost) / cost, 6) if cost > 0 else 0.0
            holdings.loc[idx, "持有天数"] = holding_days
            holdings.loc[idx, "最后估值日期"] = trade_date
            market_value += value
            updated += 1
            sources.add(quote.source)
        except Exception as exc:  # noqa: BLE001
            fallback_value = _as_float(row.get("当前市值"), 0.0)
            market_value += fallback_value
            failed += 1
            _append_log(ledger, cfg, "实时估值", "警告", f"{symbol} 最新价格刷新失败，沿用旧市值: {exc}")

    trades = ledger["成交流水"]
    cash = _cash_balance(cfg, trades)
    total = round(cash + market_value, 2)
    source_text = "、".join(sorted(sources)) if sources else "无成功行情"
    asset_row = {
        "账户编号": cfg.account_id,
        "账户名称": cfg.account_name,
        "日期": trade_date,
        "现金": cash,
        "持仓市值": round(market_value, 2),
        "总资产": total,
        "初始资金": cfg.initial_cash,
        "累计收益": round(total / cfg.initial_cash - 1.0, 6) if cfg.initial_cash > 0 else 0.0,
        "持仓数量": len(holdings),
        "备注": f"实时行情估值；{market_note}；行情源：{source_text}",
    }
    assets = ledger["每日资产"]
    if not assets.empty:
        assets = assets[~((assets["账户编号"].astype(str) == cfg.account_id) & (assets["日期"].astype(str) == trade_date))]
    ledger["每日资产"] = pd.concat([assets, pd.DataFrame([asset_row])], ignore_index=True)[ASSET_COLUMNS]
    ledger["当前持仓"] = holdings[HOLDING_COLUMNS]
    _append_log(
        ledger,
        cfg,
        "实时估值",
        "信息",
        f"{trade_date} 实时刷新 {updated} 个持仓，失败 {failed} 个，总资产 {total:.2f}；{market_note}；行情源：{source_text}",
    )
    _write_text_log(cfg, f"实时估值: {trade_date}, 更新 {updated}, 失败 {failed}, 总资产 {total:.2f}, {market_note}")
    return {
        "trade_date": trade_date,
        "cash": cash,
        "market_value": round(market_value, 2),
        "total_equity": total,
        "updated_holding_count": updated,
        "failed_holding_count": failed,
        "market_status": market_note,
        "quote_source": source_text,
    }


def _next_trade_date_from_stock_pool(cfg: PaperAccountConfig, signal_date: str) -> str:
    next_dates = [
        str(row.get("trade_date") or "")
        for row in _template_market_rows(cfg, start_date=str(signal_date))
        if str(row.get("trade_date") or "") > str(signal_date)
    ]
    return min(next_dates) if next_dates else _next_weekday(signal_date)


def _count_trade_days(cfg: PaperAccountConfig, symbol: str, start_date: str, end_date: str) -> int:
    if not start_date or not end_date:
        return 0
    key = _symbol_key(symbol)
    try:
        rows = market_data_store.read_feature_rows(
            [key],
            start_date=str(start_date),
            end_date=str(end_date),
            db_path=_market_data_db_path(),
            legacy_db_path=market_data_store.DISABLE_LEGACY_FALLBACK,
        )
        dates = [str(row.get("trade_date") or "") for row in rows]
        if start_date not in dates or end_date not in dates:
            return 0
        return max(0, dates.index(end_date) - dates.index(start_date))
    except Exception:
        return 0


def _latest_available_date(cfg: PaperAccountConfig, requested_date: str = "") -> str:
    rows = _template_market_rows(cfg, end_date=str(requested_date or ""))
    available_dates = []
    for row in rows:
        raw_close = to_float(row.get("raw_close"))
        close = to_float(row.get("close"))
        trade_date = str(row.get("trade_date") or "")
        if trade_date and raw_close is not None and raw_close > 0 and close is not None and close > 0:
            available_dates.append(trade_date)
    latest = max(available_dates) if available_dates else ""
    if not latest:
        scope = f"{requested_date} 或之前" if requested_date else "当前"
        raise ValueError(f"股票池模板在{scope}没有可用日线数据: {cfg.stock_pool_username}/{cfg.stock_pool_template_name}")
    return latest


def _tail_rows(frame: pd.DataFrame, limit: int = 200) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    tail = frame.tail(limit).astype(object)
    return tail.where(pd.notna(tail), None).to_dict(orient="records")


def _resolve_run_config(req: PaperTradingRunRequest) -> PaperAccountConfig:
    username = _request_username(req)
    context_db = _paper_context_db_path(req.config_dir, req.config_path)
    if not _has_paper_account_templates(context_db, username):
        _legacy_templates_to_sqlite(req.config_dir, username)
    account_id = _account_id_from_template_selector(
        config_path=req.config_path,
        account_id=req.account_id,
        config_dir=req.config_dir,
        username=username,
    )
    cfg = _read_template_by_account(account_id, username, db_path=context_db)
    cfg.raw_config["_config_path"] = cfg.account_id
    return cfg


def _ledger_response(cfg: PaperAccountConfig, ledger: dict[str, pd.DataFrame], action: str) -> dict[str, Any]:
    pending = ledger["待执行订单"]
    trades = ledger["成交流水"]
    holdings = ledger["当前持仓"]
    assets = ledger["每日资产"]
    logs = ledger["运行日志"]
    summary: dict[str, Any] = {
        "action": action,
        "username": cfg.username,
        "account_id": cfg.account_id,
        "account_name": cfg.account_name,
        "ledger_path": _ledger_storage_id(cfg),
        "ledger_storage": "SQLite",
        "ledger_exists": _ledger_exists(cfg),
        "stock_pool_username": cfg.stock_pool_username,
        "stock_pool_template_name": cfg.stock_pool_template_name,
        "order_count": len(pending),
        "trade_count": len(trades),
        "holding_count": len(holdings),
        "asset_count": len(assets),
        "log_count": len(logs),
    }
    if not logs.empty:
        last_log = logs.iloc[-1]
        summary.update(
            {
                "last_log_time": str(last_log.get("时间", "")),
                "last_log_action": str(last_log.get("动作", "")),
                "last_log_level": str(last_log.get("级别", "")),
                "last_log_message": str(last_log.get("信息", "")),
            }
        )
    if not assets.empty:
        last_asset = assets.iloc[-1]
        summary.update(
            {
                "trade_date": str(last_asset.get("日期", "")),
                "cash": _as_float(last_asset.get("现金"), 0.0),
                "market_value": _as_float(last_asset.get("持仓市值"), 0.0),
                "total_equity": _as_float(last_asset.get("总资产"), 0.0),
            }
        )
    return {
        "summary": summary,
        "pending_order_rows": _tail_rows(pending),
        "trade_rows": _tail_rows(trades),
        "holding_rows": _tail_rows(holdings),
        "asset_rows": _tail_rows(assets),
        "log_rows": _tail_rows(logs),
        "diagnostics": {
            "config_path": cfg.account_id,
            "ledger_path": _ledger_storage_id(cfg),
            "ledger_storage": "SQLite",
            "log_dir": "SQLite运行日志",
            "stock_pool_username": cfg.stock_pool_username,
            "stock_pool_template_name": cfg.stock_pool_template_name,
            "stock_pool_db_path": cfg.stock_pool_db_path,
            "template_count": len(list_paper_account_templates(DEFAULT_CONFIG_DIR, username=cfg.username)),
        },
    }


def read_paper_trading_ledger(req: PaperTradingRunRequest) -> dict[str, Any]:
    cfg = _resolve_run_config(req)
    ledger = _read_ledger(cfg)
    return _ledger_response(cfg, ledger, "读取账本")


def run_paper_trading(req: PaperTradingRunRequest) -> dict[str, Any]:
    cfg = _resolve_run_config(req)
    ledger = _read_ledger(cfg)
    ledger["配置快照"] = _config_snapshot(cfg)
    action = req.action
    trade_date = str(req.trade_date or "").strip()
    started = time.time()
    if action == "generate":
        trade_date = _resolve_signal_date(cfg, trade_date)
        summary = {"action": "生成收盘信号", **_generate_orders(cfg, ledger, trade_date)}
    elif action == "execute":
        if not trade_date:
            trade_date = _latest_available_date(cfg)
        summary = {"action": "执行待成交订单", **_execute_orders(cfg, ledger, trade_date)}
        summary.update(_mark_to_market(cfg, ledger, trade_date, note="开盘成交后估值"))
    elif action == "mark":
        if not trade_date:
            trade_date = _latest_available_date(cfg)
        summary = {"action": "收盘估值", **_mark_to_market(cfg, ledger, trade_date)}
    elif action == "refresh":
        summary = {"action": "实时刷新持仓价格", **_refresh_realtime_positions(cfg, ledger, trade_date)}
    else:
        raise ValueError(f"未知模拟交易动作: {action}")

    _write_ledger(cfg, ledger)
    elapsed = round(time.time() - started, 3)
    summary.update(
        {
            "username": cfg.username,
            "account_id": cfg.account_id,
            "account_name": cfg.account_name,
            "stock_pool_username": cfg.stock_pool_username,
            "stock_pool_template_name": cfg.stock_pool_template_name,
            "ledger_path": _ledger_storage_id(cfg),
            "ledger_storage": "SQLite",
            "elapsed_seconds": elapsed,
        }
    )
    return {
        "summary": summary,
        "pending_order_rows": _tail_rows(ledger["待执行订单"]),
        "trade_rows": _tail_rows(ledger["成交流水"]),
        "holding_rows": _tail_rows(ledger["当前持仓"]),
        "asset_rows": _tail_rows(ledger["每日资产"]),
        "log_rows": _tail_rows(ledger["运行日志"]),
        "diagnostics": {
            "config_path": cfg.account_id,
            "ledger_path": _ledger_storage_id(cfg),
            "ledger_storage": "SQLite",
            "log_dir": "SQLite运行日志",
            "stock_pool_username": cfg.stock_pool_username,
            "stock_pool_template_name": cfg.stock_pool_template_name,
            "stock_pool_db_path": cfg.stock_pool_db_path,
            "template_count": len(list_paper_account_templates(req.config_dir, username=cfg.username)),
        },
    }


def run_all_paper_accounts(
    config_dir: str | Path,
    action: Literal["generate", "execute", "mark", "refresh"],
    trade_date: str = "",
    username: str = DEFAULT_USERNAME,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    clean_user = _clean_username(username)
    for item in list_paper_account_templates(config_dir, username=clean_user):
        if item.get("error"):
            results.append({"summary": {"account_id": item.get("account_id"), "error": item["error"]}})
            continue
        try:
            results.append(
                run_paper_trading(
                    PaperTradingRunRequest(
                        account_id=str(item["account_id"]),
                        action=action,
                        trade_date=trade_date,
                        config_dir=str(config_dir),
                        username=clean_user,
                    )
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "summary": {
                        "account_id": item.get("account_id"),
                        "account_name": item.get("account_name"),
                        "action": action,
                        "error": str(exc),
                    }
                }
            )
    return results
