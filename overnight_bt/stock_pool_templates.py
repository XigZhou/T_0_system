from __future__ import annotations

import csv
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data_store" / "stock_pool_templates.sqlite"
DEFAULT_USERNAME = "admin"
ADMIN_USERNAME = "admin"
TOP500_LAYER_CONSTITUENTS = PROJECT_ROOT / "research_runs" / "20260509_top500_stock_pool_layer_grid_account" / "stock_pool_layer_constituents.csv"
DEFAULT_PAPER_PROCESSED_DIR = PROJECT_ROOT / "data_bundle" / "processed_qfq_theme_focus_top100"

SYMBOL_PATTERN = re.compile(r"(?<!\d)(\d{6})(?:\.(?:SH|SZ|BJ))?(?!\d)", re.IGNORECASE)


@dataclass
class StockParseResult:
    valid_stocks: list[dict[str, Any]]
    duplicate_symbols: list[str]
    invalid_items: list[str]


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _symbol_to_ts_code(symbol: str) -> str:
    code = str(symbol).strip()[:6]
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def _db_path(db_path: str | Path | None = None) -> Path:
    path = Path(db_path or DEFAULT_DB_PATH)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _connect_readonly(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"stock pool db not found: {path}")
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn



def _ensure_columns(conn: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    existing = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    for column_name, column_definition in columns.items():
        if column_name not in existing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None



def read_template_symbols(
    username: str,
    template_name: str,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    clean_username = str(username or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME
    clean_template = str(template_name or "").strip()
    if not clean_template:
        raise ValueError("请选择股票池模板")
    with _connect_readonly(db_path) as conn:
        template = conn.execute(
            "SELECT 1 FROM stock_pool_templates WHERE username=? AND template_name=?",
            (clean_username, clean_template),
        ).fetchone()
        if template is None:
            raise FileNotFoundError(f"股票池模板不存在: {clean_username}/{clean_template}")
        rows = conn.execute(
            """
            SELECT symbol, ts_code, stock_name, display_order
            FROM stock_pool_template_stocks
            WHERE username=? AND template_name=?
            ORDER BY display_order, symbol
            """,
            (clean_username, clean_template),
        ).fetchall()
    if not rows:
        raise ValueError(f"股票池模板没有股票: {clean_template}")
    result: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row["symbol"] or "").strip().zfill(6)
        result.append(
            {
                "symbol": symbol,
                "ts_code": str(row["ts_code"] or _symbol_to_ts_code(symbol)).strip(),
                "stock_name": str(row["stock_name"] or "").strip(),
                "display_order": int(row["display_order"] or 0),
            }
        )
    return result

def init_stock_pool_db(db_path: str | Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT DEFAULT '',
                display_name TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stock_pool_templates (
                template_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                template_name TEXT NOT NULL,
                description TEXT DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(username, template_name)
            );

            CREATE TABLE IF NOT EXISTS stock_pool_template_stocks (
                username TEXT NOT NULL,
                template_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                ts_code TEXT NOT NULL,
                stock_name TEXT DEFAULT '',
                display_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                PRIMARY KEY(username, template_name, symbol),
                FOREIGN KEY(username, template_name)
                    REFERENCES stock_pool_templates(username, template_name)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS stock_basic (
                symbol TEXT PRIMARY KEY,
                ts_code TEXT NOT NULL,
                name TEXT DEFAULT '',
                industry TEXT DEFAULT '',
                market TEXT DEFAULT '',
                list_date TEXT DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stock_daily_features (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                ts_code TEXT DEFAULT '',
                name TEXT DEFAULT '',
                raw_open REAL,
                raw_high REAL,
                raw_low REAL,
                raw_close REAL,
                qfq_open REAL,
                qfq_high REAL,
                qfq_low REAL,
                qfq_close REAL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                vol REAL,
                amount REAL,
                up_limit REAL,
                down_limit REAL,
                is_suspended_t INTEGER,
                can_buy_t INTEGER,
                can_buy_open_t INTEGER,
                can_sell_t INTEGER,
                can_sell_t1 INTEGER,
                m120 REAL,
                m60 REAL,
                m30 REAL,
                m20 REAL,
                m10 REAL,
                m5 REAL,
                ma5 REAL,
                ma10 REAL,
                ma20 REAL,
                ret1 REAL,
                ret2 REAL,
                ret3 REAL,
                pct_chg REAL,
                bias_ma5 REAL,
                bias_ma10 REAL,
                amp REAL,
                amp5 REAL,
                high_5 REAL,
                low_5 REAL,
                high_10 REAL,
                low_10 REAL,
                high_20 REAL,
                low_20 REAL,
                vol5 REAL,
                vol10 REAL,
                vr REAL,
                amount5 REAL,
                amount10 REAL,
                close_to_up_limit REAL,
                high_to_up_limit REAL,
                close_pos_in_bar REAL,
                body_pct REAL,
                upper_shadow_pct REAL,
                lower_shadow_pct REAL,
                vol_ratio_3 REAL,
                amount_ratio_3 REAL,
                body_pct_3avg REAL,
                close_to_up_limit_3max REAL,
                ret_accel_3 REAL,
                vol_ratio_5 REAL,
                avg5m120 REAL,
                avg5m60 REAL,
                avg5m30 REAL,
                avg5m20 REAL,
                avg5m10 REAL,
                avg5m5 REAL,
                avg10m120 REAL,
                avg10m60 REAL,
                avg10m30 REAL,
                avg10m20 REAL,
                avg10m10 REAL,
                avg10m5 REAL,
                sh_open REAL,
                sh_high REAL,
                sh_low REAL,
                sh_close REAL,
                sh_vol REAL,
                sh_amount REAL,
                sh_m120 REAL,
                sh_m60 REAL,
                sh_m30 REAL,
                sh_m20 REAL,
                sh_m10 REAL,
                sh_m5 REAL,
                sh_ma5 REAL,
                sh_ma10 REAL,
                sh_ma20 REAL,
                sh_ret1 REAL,
                sh_ret2 REAL,
                sh_ret3 REAL,
                sh_pct_chg REAL,
                sh_bias_ma5 REAL,
                sh_bias_ma10 REAL,
                hs300_open REAL,
                hs300_high REAL,
                hs300_low REAL,
                hs300_close REAL,
                hs300_vol REAL,
                hs300_amount REAL,
                hs300_m120 REAL,
                hs300_m60 REAL,
                hs300_m30 REAL,
                hs300_m20 REAL,
                hs300_m10 REAL,
                hs300_m5 REAL,
                hs300_ma5 REAL,
                hs300_ma10 REAL,
                hs300_ma20 REAL,
                hs300_ret1 REAL,
                hs300_ret2 REAL,
                hs300_ret3 REAL,
                hs300_pct_chg REAL,
                hs300_bias_ma5 REAL,
                hs300_bias_ma10 REAL,
                cyb_open REAL,
                cyb_high REAL,
                cyb_low REAL,
                cyb_close REAL,
                cyb_vol REAL,
                cyb_amount REAL,
                cyb_m120 REAL,
                cyb_m60 REAL,
                cyb_m30 REAL,
                cyb_m20 REAL,
                cyb_m10 REAL,
                cyb_m5 REAL,
                cyb_ma5 REAL,
                cyb_ma10 REAL,
                cyb_ma20 REAL,
                cyb_ret1 REAL,
                cyb_ret2 REAL,
                cyb_ret3 REAL,
                cyb_pct_chg REAL,
                cyb_bias_ma5 REAL,
                cyb_bias_ma10 REAL,
                industry TEXT,
                market TEXT,
                board TEXT,
                listed_days INTEGER,
                total_mv_snapshot REAL,
                turnover_rate_snapshot REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(symbol, trade_date)
            );

            CREATE TABLE IF NOT EXISTS stock_pool_update_jobs (
                job_id TEXT PRIMARY KEY,
                job_type TEXT NOT NULL,
                username TEXT DEFAULT '',
                template_name TEXT DEFAULT '',
                status TEXT NOT NULL,
                start_date TEXT DEFAULT '',
                end_date TEXT DEFAULT '',
                stock_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                message TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                started_at TEXT DEFAULT '',
                finished_at TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS stock_pool_update_job_items (
                job_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL,
                start_date TEXT DEFAULT '',
                end_date TEXT DEFAULT '',
                rows_written INTEGER DEFAULT 0,
                message TEXT DEFAULT '',
                PRIMARY KEY(job_id, symbol)
            );
            """
        )
        _ensure_columns(
            conn,
            "stock_pool_update_jobs",
            {
                "log_file": "TEXT DEFAULT ''",
                "item_csv": "TEXT DEFAULT ''",
                "summary_json": "TEXT DEFAULT ''",
            },
        )
        now = _now_text()
        conn.execute(
            """
            INSERT INTO users(username, password_hash, display_name, created_at, updated_at)
            VALUES(?, '', ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET updated_at=excluded.updated_at
            """,
            (DEFAULT_USERNAME, DEFAULT_USERNAME, now, now),
        )


def parse_stock_list(text: str, db_path: str | Path | None = None) -> StockParseResult:
    raw_items = [item.strip() for item in re.split(r"[\s,，;；]+", str(text or "")) if item.strip()]
    name_lookup = _load_stock_name_lookup(db_path)
    name_reverse = _build_stock_name_reverse_lookup(name_lookup)
    seen: set[str] = set()
    valid: list[dict[str, Any]] = []
    duplicates: list[str] = []
    invalid: list[str] = []
    for item in raw_items:
        stock_name = ""
        match = SYMBOL_PATTERN.fullmatch(item.upper())
        if match:
            symbol = match.group(1)
            stock_name = name_lookup.get(symbol, "")
        else:
            name_key = _normalize_stock_name(item)
            if not name_key:
                invalid.append(item)
                continue
            candidates = name_reverse.get(name_key, [])
            if not candidates:
                invalid.append(f"{item}(名称未匹配)")
                continue
            if len(candidates) > 1:
                hint = ",".join(candidates[:3])
                invalid.append(f"{item}(名称重复:{hint})")
                continue
            symbol = candidates[0]
            stock_name = name_lookup.get(symbol, str(item).strip())
        if symbol in seen:
            if symbol not in duplicates:
                duplicates.append(symbol)
            continue
        seen.add(symbol)
        valid.append({"symbol": symbol, "ts_code": _symbol_to_ts_code(symbol), "stock_name": stock_name})
    return StockParseResult(valid_stocks=valid, duplicate_symbols=duplicates, invalid_items=invalid)


STOCK_NAME_LOOKUP_FILES = (
    PROJECT_ROOT / "data_bundle" / "theme_tradeable_top500_4y" / "universe_snapshot_top500.csv",
    PROJECT_ROOT / "data_bundle" / "universe_snapshot_theme_focus_top100.csv",
    PROJECT_ROOT / "data_bundle" / "universe_snapshot_theme_focus.csv",
    PROJECT_ROOT / "data_bundle" / "universe_snapshot.csv",
    PROJECT_ROOT / "sector_research" / "data" / "processed" / "stock_theme_exposure.csv",
    PROJECT_ROOT / "sector_research" / "data" / "processed" / "theme_tradeable_universe" / "theme_tradeable_universe_snapshot.csv",
)


def _normalize_stock_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    match = SYMBOL_PATTERN.search(text)
    return match.group(1) if match else ""


def _normalize_stock_name(value: Any) -> str:
    text = str(value or "").strip()
    return text.replace(" ", "").replace("　", "")


def _row_symbol(row: dict[str, Any]) -> str:
    for key in ("symbol", "stock_code", "code", "ts_code", "????"):
        symbol = _normalize_stock_symbol(row.get(key))
        if symbol:
            return symbol
    return ""


def _row_stock_name(row: dict[str, Any]) -> str:
    for key in ("stock_name", "name", "stockName", "sec_name", "????", "??"):
        value = str(row.get(key) or "").strip()
        if value and value.lower() != "nan":
            return value
    return ""


def _merge_name(mapping: dict[str, str], symbol: str, name: str) -> None:
    symbol = _normalize_stock_symbol(symbol)
    name = str(name or "").strip()
    if symbol and name and symbol not in mapping:
        mapping[symbol] = name


def _read_csv_name_lookup(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not path.exists() or not path.is_file():
        return mapping
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                symbol = _row_symbol(row)
                name = _row_stock_name(row)
                _merge_name(mapping, symbol, name)
    except Exception:
        return {}
    return mapping


def _load_stock_name_lookup(db_path: str | Path | None = None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    try:
        with _connect(db_path) as conn:
            rows = conn.execute("SELECT symbol, name FROM stock_basic WHERE COALESCE(name, '') <> ''").fetchall()
            for row in rows:
                _merge_name(mapping, row["symbol"], row["name"])
    except Exception:
        pass
    for rows in _read_layer_constituents().values():
        for row in rows:
            _merge_name(mapping, row.get("symbol", ""), row.get("stock_name", ""))
    for row in _read_current_paper_symbols():
        _merge_name(mapping, row.get("symbol", ""), row.get("stock_name", ""))
    for path in STOCK_NAME_LOOKUP_FILES:
        for symbol, name in _read_csv_name_lookup(path).items():
            _merge_name(mapping, symbol, name)
    return mapping


def _build_stock_name_reverse_lookup(name_lookup: dict[str, str]) -> dict[str, list[str]]:
    reverse: dict[str, list[str]] = {}
    for symbol, name in name_lookup.items():
        key = _normalize_stock_name(name)
        if not key:
            continue
        reverse.setdefault(key, []).append(symbol)
    return reverse




def _enrich_stock_names(stocks: list[dict[str, Any]], db_path: str | Path | None = None) -> list[dict[str, Any]]:
    lookup = _load_stock_name_lookup(db_path)
    for stock in stocks:
        if not str(stock.get("stock_name") or "").strip():
            stock["stock_name"] = lookup.get(str(stock.get("symbol") or ""), "")
    return stocks


def _stock_text_from_rows(rows: list[dict[str, Any]]) -> str:
    return "\n".join(str(row["symbol"]) for row in rows)


def _template_summary(conn: sqlite3.Connection, username: str, row: sqlite3.Row) -> dict[str, Any]:
    stocks = conn.execute(
        """
        SELECT symbol FROM stock_pool_template_stocks
        WHERE username=? AND template_name=?
        ORDER BY display_order, symbol
        """,
        (username, row["template_name"]),
    ).fetchall()
    return {
        "template_id": row["template_id"],
        "username": row["username"],
        "template_name": row["template_name"],
        "description": row["description"] or "",
        "is_active": bool(row["is_active"]),
        "stock_count": len(stocks),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_stock_pool_templates(username: str = DEFAULT_USERNAME, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    init_stock_pool_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM stock_pool_templates
            WHERE username=?
            ORDER BY updated_at DESC, template_name
            """,
            (username,),
        ).fetchall()
        return [_template_summary(conn, username, row) for row in rows]


def read_stock_pool_template(
    template_name: str,
    username: str = DEFAULT_USERNAME,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_stock_pool_db(db_path)
    name = str(template_name or "").strip()
    if not name:
        raise ValueError("模板名称不能为空")
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM stock_pool_templates WHERE username=? AND template_name=?",
            (username, name),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"股票池模板不存在: {name}")
        stock_rows = conn.execute(
            """
            SELECT symbol, ts_code, stock_name, display_order, created_at
            FROM stock_pool_template_stocks
            WHERE username=? AND template_name=?
            ORDER BY display_order, symbol
            """,
            (username, name),
        ).fetchall()
        stocks = _enrich_stock_names([dict(item) for item in stock_rows], db_path=db_path)
        latest = conn.execute(
            """
            SELECT s.symbol, MAX(f.trade_date) AS latest_trade_date
            FROM stock_pool_template_stocks s
            LEFT JOIN stock_daily_features f ON f.symbol=s.symbol
            WHERE s.username=? AND s.template_name=?
            GROUP BY s.symbol
            """,
            (username, name),
        ).fetchall()
        latest_map = {item["symbol"]: item["latest_trade_date"] for item in latest}
        for stock in stocks:
            stock["latest_trade_date"] = latest_map.get(stock["symbol"]) or ""
        data = _template_summary(conn, username, row)
        data["stocks"] = stocks
        data["stock_text"] = _stock_text_from_rows(stocks)
        data["db_path"] = str(_db_path(db_path))
        return data


def validate_stock_pool_symbols(
    stock_text: str,
    db_path: str | Path | None = None,
    main_universe_db_path: str | Path | None = None,
) -> dict[str, Any]:
    if main_universe_db_path is not None:
        parsed = _parse_stock_list_against_main_universe(stock_text, main_universe_db_path)
    else:
        parsed = parse_stock_list(stock_text, db_path=db_path)
        _enrich_stock_names(parsed.valid_stocks, db_path=db_path)
    return {
        "valid_stocks": parsed.valid_stocks,
        "valid_count": len(parsed.valid_stocks),
        "duplicate_symbols": parsed.duplicate_symbols,
        "duplicate_count": len(parsed.duplicate_symbols),
        "invalid_items": parsed.invalid_items,
        "invalid_count": len(parsed.invalid_items),
    }


MAIN_UNIVERSE_NOT_READY_MESSAGE = "\u4e3b\u80a1\u7968\u6c60\u5c1a\u672a\u521d\u59cb\u5316\uff0c\u8bf7\u5148\u5728\u7cfb\u7edf\u7ba1\u7406\u5458\u4e2d\u7ef4\u62a4\u4e3b\u80a1\u7968\u6c60"


def _load_active_main_universe_rows_without_init(db_path: str | Path) -> list[dict[str, Any]]:
    path = Path(db_path)
    if not path.exists():
        raise ValueError(MAIN_UNIVERSE_NOT_READY_MESSAGE)
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise ValueError(MAIN_UNIVERSE_NOT_READY_MESSAGE) from exc
    conn.row_factory = sqlite3.Row
    try:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='main_stock_universe'"
        ).fetchone()
        if table is None:
            raise ValueError(MAIN_UNIVERSE_NOT_READY_MESSAGE)
        rows = conn.execute(
            """
            SELECT symbol, ts_code, name
            FROM main_stock_universe
            WHERE is_active = 1
            ORDER BY name, symbol
            """
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        raise ValueError(MAIN_UNIVERSE_NOT_READY_MESSAGE)

    active_rows: list[dict[str, Any]] = []
    for row in rows:
        symbol = _normalize_stock_symbol(row["symbol"] or row["ts_code"])
        if not symbol:
            continue
        active_rows.append(
            {
                "symbol": symbol,
                "ts_code": str(row["ts_code"] or _symbol_to_ts_code(symbol)).strip() or _symbol_to_ts_code(symbol),
                "stock_name": str(row["name"] or "").strip(),
            }
        )
    if not active_rows:
        raise ValueError(MAIN_UNIVERSE_NOT_READY_MESSAGE)
    return active_rows


def _parse_stock_list_against_main_universe(
    text: str,
    main_universe_db_path: str | Path,
) -> StockParseResult:
    raw_items = [item.strip() for item in re.split(r"[\s,\uFF0C;\uFF1B]+", str(text or "")) if item.strip()]
    active_rows = _load_active_main_universe_rows_without_init(main_universe_db_path)
    by_symbol = {row["symbol"]: row for row in active_rows}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in active_rows:
        name_key = _normalize_stock_name(row.get("stock_name"))
        if name_key:
            by_name.setdefault(name_key, []).append(row)

    seen: set[str] = set()
    valid: list[dict[str, Any]] = []
    duplicates: list[str] = []
    invalid: list[str] = []
    for item in raw_items:
        match = SYMBOL_PATTERN.fullmatch(item.upper())
        if match:
            symbol = match.group(1)
            row = by_symbol.get(symbol)
            if row is None:
                invalid.append(f"{item}(\u4e0d\u5728\u4e3b\u80a1\u7968\u6c60)")
                continue
        else:
            name_key = _normalize_stock_name(item)
            if not name_key:
                invalid.append(item)
                continue
            candidates = by_name.get(name_key, [])
            if not candidates:
                invalid.append(f"{item}(\u4e0d\u5728\u4e3b\u80a1\u7968\u6c60)")
                continue
            if len(candidates) > 1:
                hint = ",".join(row["symbol"] for row in candidates[:3])
                invalid.append(f"{item}(\u540d\u79f0\u91cd\u590d:{hint})")
                continue
            row = candidates[0]
            symbol = row["symbol"]
        if symbol in seen:
            if symbol not in duplicates:
                duplicates.append(symbol)
            continue
        seen.add(symbol)
        valid.append({"symbol": symbol, "ts_code": row["ts_code"], "stock_name": row.get("stock_name", "")})
    return StockParseResult(valid_stocks=valid, duplicate_symbols=duplicates, invalid_items=invalid)


def save_stock_pool_template(
    req: Any,
    db_path: str | Path | None = None,
    main_universe_db_path: str | Path | None = None,
) -> dict[str, Any]:
    username = str(getattr(req, "username", "") or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME
    old_name = str(getattr(req, "original_template_name", "") or "").strip()
    name = str(getattr(req, "template_name", "") or "").strip()
    if not name:
        raise ValueError("\u6a21\u677f\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a")
    description = str(getattr(req, "description", "") or "").strip()
    is_active = True
    overwrite_existing = bool(getattr(req, "overwrite_existing", False))
    stock_text = str(getattr(req, "stock_text", "") or "")
    if main_universe_db_path is not None:
        parsed = _parse_stock_list_against_main_universe(stock_text, main_universe_db_path)
    else:
        init_stock_pool_db(db_path)
        parsed = parse_stock_list(stock_text, db_path=db_path)
        _enrich_stock_names(parsed.valid_stocks, db_path=db_path)
    if parsed.invalid_items:
        if main_universe_db_path is not None:
            raise ValueError(f"\u80a1\u7968\u4e0d\u5728\u4e3b\u80a1\u7968\u6c60\u6216\u672a\u542f\u7528: {', '.join(parsed.invalid_items[:10])}")
        raise ValueError(f"\u80a1\u7968\u5217\u8868\u5305\u542b\u65e0\u6cd5\u8bc6\u522b\u7684\u4ee3\u7801: {', '.join(parsed.invalid_items[:10])}")
    if not parsed.valid_stocks:
        raise ValueError("\u80a1\u7968\u5217\u8868\u4e0d\u80fd\u4e3a\u7a7a")

    init_stock_pool_db(db_path)
    now = _now_text()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO users(username, password_hash, display_name, created_at, updated_at)
            VALUES(?, '', ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET updated_at=excluded.updated_at
            """,
            (username, username, now, now),
        )
        target = conn.execute(
            "SELECT * FROM stock_pool_templates WHERE username=? AND template_name=?",
            (username, name),
        ).fetchone()
        source = None
        if old_name:
            source = conn.execute(
                "SELECT * FROM stock_pool_templates WHERE username=? AND template_name=?",
                (username, old_name),
            ).fetchone()

        is_same_template = bool(source and target and source["template_id"] == target["template_id"])
        if target is not None and not is_same_template and not overwrite_existing:
            raise ValueError(f"模板名称已存在: {name}")
        if target is not None and not is_same_template and overwrite_existing:
            raise ValueError("覆盖保存只能写回当前模板；如需新模板请更换名称")

        if source is not None:
            template_id = source["template_id"]
            if old_name != name:
                conn.execute(
                    """
                    DELETE FROM stock_pool_template_stocks
                    WHERE username=? AND template_name=?
                    """,
                    (username, old_name),
                )
            conn.execute(
                """
                UPDATE stock_pool_templates
                SET template_name=?, description=?, is_active=?, updated_at=?
                WHERE template_id=?
                """,
                (name, description, 1 if is_active else 0, now, template_id),
            )
        else:
            template_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO stock_pool_templates(template_id, username, template_name, description, is_active, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (template_id, username, name, description, 1 if is_active else 0, now, now),
            )

        conn.execute(
            "DELETE FROM stock_pool_template_stocks WHERE username=? AND template_name=?",
            (username, name),
        )
        for idx, stock in enumerate(parsed.valid_stocks, start=1):
            conn.execute(
                """
                INSERT INTO stock_pool_template_stocks(username, template_name, symbol, ts_code, stock_name, display_order, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (username, name, stock["symbol"], stock["ts_code"], stock.get("stock_name", ""), idx, now),
            )
            conn.execute(
                """
                INSERT INTO stock_basic(symbol, ts_code, name, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    ts_code=excluded.ts_code,
                    name=COALESCE(NULLIF(excluded.name, ''), stock_basic.name),
                    updated_at=excluded.updated_at
                """,
                (stock["symbol"], stock["ts_code"], stock.get("stock_name", ""), now),
            )
    data = read_stock_pool_template(name, username=username, db_path=db_path)
    return {
        "template": data,
        "validation": validate_stock_pool_symbols(str(getattr(req, "stock_text", "") or ""), db_path=db_path),
        "message": f"股票池模板已保存：{name}；模板只保存股票集合，行情与指标由主行情库和统一调度维护。",
    }


def delete_stock_pool_template(
    template_name: str,
    username: str = DEFAULT_USERNAME,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_stock_pool_db(db_path)
    name = str(template_name or "").strip()
    if not name:
        raise ValueError("模板名称不能为空")
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM stock_pool_templates WHERE username=? AND template_name=?",
            (username, name),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"股票池模板不存在: {name}")
        stock_count = conn.execute(
            "SELECT COUNT(*) AS count FROM stock_pool_template_stocks WHERE username=? AND template_name=?",
            (username, name),
        ).fetchone()["count"]
        conn.execute(
            "DELETE FROM stock_pool_templates WHERE username=? AND template_name=?",
            (username, name),
        )
    return {
        "deleted_template_name": name,
        "username": username,
        "stock_count": stock_count,
        "message": f"股票池模板已删除：{name}；主行情库数据保留不动。",
    }


def _read_layer_constituents() -> dict[str, list[dict[str, str]]]:
    if not TOP500_LAYER_CONSTITUENTS.exists():
        return {}
    rows_by_layer: dict[str, list[dict[str, str]]] = {}
    with TOP500_LAYER_CONSTITUENTS.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            layer = str(row.get("layer") or "").strip()
            symbol = str(row.get("symbol") or "").strip().zfill(6)
            if not layer or not symbol:
                continue
            rows_by_layer.setdefault(layer, []).append(
                {"symbol": symbol, "stock_name": str(row.get("name") or "").strip()}
            )
    return rows_by_layer


def _read_current_paper_symbols() -> list[dict[str, str]]:
    if not DEFAULT_PAPER_PROCESSED_DIR.exists():
        return []
    rows: list[dict[str, str]] = []
    for path in sorted(DEFAULT_PAPER_PROCESSED_DIR.glob("*.csv")):
        if path.name in {"processing_manifest.csv", "sector_feature_manifest.csv", "rotation_feature_manifest.csv"}:
            continue
        symbol = path.stem[:6]
        if not symbol.isdigit():
            continue
        stock_name = ""
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                first = next(reader, None)
                if first:
                    stock_name = str(first.get("name") or first.get("stock_name") or "").strip()
        except Exception:
            stock_name = ""
        rows.append({"symbol": symbol, "stock_name": stock_name})
    return rows


def _save_seed_template(
    conn: sqlite3.Connection,
    username: str,
    template_name: str,
    description: str,
    stocks: list[dict[str, str]],
) -> bool:
    if not stocks:
        return False
    exists = conn.execute(
        "SELECT 1 FROM stock_pool_templates WHERE username=? AND template_name=?",
        (username, template_name),
    ).fetchone()
    if exists:
        return False
    now = _now_text()
    conn.execute(
        """
        INSERT INTO stock_pool_templates(template_id, username, template_name, description, is_active, created_at, updated_at)
        VALUES(?, ?, ?, ?, 1, ?, ?)
        """,
        (str(uuid.uuid4()), username, template_name, description, now, now),
    )
    seen: set[str] = set()
    order = 0
    for stock in stocks:
        symbol = str(stock.get("symbol") or "").strip().zfill(6)
        if not symbol.isdigit() or symbol in seen:
            continue
        seen.add(symbol)
        order += 1
        stock_name = str(stock.get("stock_name") or "").strip()
        ts_code = _symbol_to_ts_code(symbol)
        conn.execute(
            """
            INSERT INTO stock_pool_template_stocks(username, template_name, symbol, ts_code, stock_name, display_order, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (username, template_name, symbol, ts_code, stock_name, order, now),
        )
        conn.execute(
            """
            INSERT INTO stock_basic(symbol, ts_code, name, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                ts_code=excluded.ts_code,
                name=COALESCE(NULLIF(excluded.name, ''), stock_basic.name),
                updated_at=excluded.updated_at
            """,
            (symbol, ts_code, stock_name, now),
        )
    return True


def seed_default_stock_pool_templates(
    username: str = DEFAULT_USERNAME,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_stock_pool_db(db_path)
    created: list[str] = []
    layer_names = {
        "L0": "L0_最大市值主题股层",
        "L1": "L1_偏大市值主题股层",
        "L2": "L2_中等市值主题股层",
        "L3": "L3_偏小市值主题股层",
        "L4": "L4_最小市值主题股层",
    }
    layer_rows = _read_layer_constituents()
    with _connect(db_path) as conn:
        for layer, name in layer_names.items():
            if _save_seed_template(
                conn,
                username,
                name,
                f"来自 Top500 股票池分层实验的 {layer} 基础模板。",
                layer_rows.get(layer, []),
            ):
                created.append(name)
        if _save_seed_template(
            conn,
            username,
            "当前多账户模拟股票池",
            "来自 data_bundle/processed_qfq_theme_focus_top100 的当前多账户模拟默认股票范围。",
            _read_current_paper_symbols(),
        ):
            created.append("当前多账户模拟股票池")
    return {
        "username": username,
        "created_templates": created,
        "created_count": len(created),
        "message": f"默认股票池模板初始化完成，新增 {len(created)} 个模板。",
    }


def ensure_default_stock_pool_templates(
    username: str = DEFAULT_USERNAME,
    db_path: str | Path | None = None,
) -> None:
    init_stock_pool_db(db_path)
    with _connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM stock_pool_templates WHERE username=?",
            (username,),
        ).fetchone()["count"]
    if count == 0:
        seed_default_stock_pool_templates(username=username, db_path=db_path)
