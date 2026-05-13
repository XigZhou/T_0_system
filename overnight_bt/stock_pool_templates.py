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
DEFAULT_USERNAME = "505888"
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


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


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
        now = _now_text()
        conn.execute(
            """
            INSERT INTO users(username, password_hash, display_name, created_at, updated_at)
            VALUES(?, '', ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET updated_at=excluded.updated_at
            """,
            (DEFAULT_USERNAME, DEFAULT_USERNAME, now, now),
        )


def parse_stock_list(text: str) -> StockParseResult:
    raw_items = [item.strip() for item in re.split(r"[\s,，;；]+", str(text or "")) if item.strip()]
    seen: set[str] = set()
    valid: list[dict[str, Any]] = []
    duplicates: list[str] = []
    invalid: list[str] = []
    for item in raw_items:
        match = SYMBOL_PATTERN.fullmatch(item.upper())
        if not match:
            invalid.append(item)
            continue
        symbol = match.group(1)
        if symbol in seen:
            if symbol not in duplicates:
                duplicates.append(symbol)
            continue
        seen.add(symbol)
        valid.append({"symbol": symbol, "ts_code": _symbol_to_ts_code(symbol), "stock_name": ""})
    return StockParseResult(valid_stocks=valid, duplicate_symbols=duplicates, invalid_items=invalid)


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
        stocks = [dict(item) for item in stock_rows]
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


def validate_stock_pool_symbols(stock_text: str) -> dict[str, Any]:
    parsed = parse_stock_list(stock_text)
    return {
        "valid_stocks": parsed.valid_stocks,
        "valid_count": len(parsed.valid_stocks),
        "duplicate_symbols": parsed.duplicate_symbols,
        "duplicate_count": len(parsed.duplicate_symbols),
        "invalid_items": parsed.invalid_items,
        "invalid_count": len(parsed.invalid_items),
    }


def save_stock_pool_template(req: Any, db_path: str | Path | None = None) -> dict[str, Any]:
    init_stock_pool_db(db_path)
    username = str(getattr(req, "username", "") or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME
    old_name = str(getattr(req, "original_template_name", "") or "").strip()
    name = str(getattr(req, "template_name", "") or "").strip()
    if not name:
        raise ValueError("模板名称不能为空")
    description = str(getattr(req, "description", "") or "").strip()
    is_active = bool(getattr(req, "is_active", True))
    overwrite_existing = bool(getattr(req, "overwrite_existing", False))
    parsed = parse_stock_list(str(getattr(req, "stock_text", "") or ""))
    if parsed.invalid_items:
        raise ValueError(f"股票列表包含无法识别的代码: {', '.join(parsed.invalid_items[:10])}")
    if not parsed.valid_stocks:
        raise ValueError("股票列表不能为空")

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
                    updated_at=excluded.updated_at
                """,
                (stock["symbol"], stock["ts_code"], stock.get("stock_name", ""), now),
            )
    data = read_stock_pool_template(name, username=username, db_path=db_path)
    return {
        "template": data,
        "validation": validate_stock_pool_symbols(str(getattr(req, "stock_text", "") or "")),
        "message": f"股票池模板已保存：{name}；第一阶段只保存模板和股票列表，尚未触发行情采集。",
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
        "message": f"股票池模板已删除：{name}；SQLite 日线数据保留不动。",
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
