# Admin Operations Market Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the admin system around main stock universe maintenance, database-backed market data, core scheduler visibility, and safe daily trading operations.

**Architecture:** Introduce a main universe and market-data access layer, make stock pool templates reference only validated symbols, route backtests and paper trading through the shared market-data store, and split core trading schedules from auxiliary research schedules. Admin UI becomes an operations dashboard rather than a template-data refresh page.

**Tech Stack:** FastAPI, Pydantic, SQLite, pandas, Tushare, existing vanilla HTML/CSS/JS frontend, pytest, shell scripts on Tencent Cloud.

---

## File Structure

- Create `overnight_bt/main_universe.py`: main stock universe schema, name resolution, append/replace operations, and read APIs.
- Create `overnight_bt/market_data_store.py`: initialize and read/write production market-data tables, with a compatibility bridge to existing `stock_daily_features`.
- Create `overnight_bt/scheduler.py`: scheduler job/run tables, log parsing helpers, and retry metadata.
- Modify `overnight_bt/stock_pool_templates.py`: remove data-refresh responsibility from template creation and validate symbols against main universe.
- Modify `overnight_bt/app.py`: add admin universe and scheduler APIs, keep legacy stock-pool refresh APIs hidden from admin UI.
- Modify `overnight_bt/models.py`: add request/response models for universe upload, task runs, and retry actions.
- Modify `overnight_bt/paper_trading.py`: read template symbols from templates DB and prices/features from market data DB.
- Modify `overnight_bt/backtest.py`, `overnight_bt/daily_plan.py`, `overnight_bt/single_stock.py`: make `stock_pool` mode filter market data by template symbols.
- Modify `scripts/run_after_close_pipeline.sh`: reduce to core trading chain or replace with a core script wrapper.
- Create `scripts/run_core_after_close_pipeline.sh`: core after-close chain.
- Create `scripts/run_aux_research_pipeline.sh`: non-blocking sector/rotation research chain.
- Modify `static/admin.html`, `static/admin.js`, `static/style.css`: admin operations dashboard.
- Modify `static/stock_pools.html`, `static/stock_pools.js`: keep template name input UX, validate against main universe, remove data refresh affordances.
- Modify docs: `docs/system-documentation.md`, `docs/stock-pool-template-system-plan.md`, `docs/stock-pool-template-data-dictionary.md`, `docs/after-close-pipeline.md`.
- Add tests: `tests/test_main_universe.py`, `tests/test_market_data_store.py`, `tests/test_scheduler.py`, plus focused updates to existing API, paper trading, backtest, daily plan, single stock, and stock pool tests.

AGENTS.md says only commit/push when the user explicitly asks for GitHub delivery. During implementation, replace commit checkpoints with status checkpoints unless the user asks to commit.

---

### Task 1: Add Main Universe Schema And Name Resolution

**Files:**
- Create: `overnight_bt/main_universe.py`
- Modify: `overnight_bt/models.py`
- Test: `tests/test_main_universe.py`

- [ ] **Step 1: Write failing tests for exact name resolution**

Create `tests/test_main_universe.py` with tests covering:

```python
from pathlib import Path

import pytest

from overnight_bt.main_universe import (
    MainUniverseSaveRequest,
    init_main_universe_db,
    list_main_universe,
    resolve_stock_names,
    save_main_universe,
)


def test_resolve_stock_names_requires_unique_name(tmp_path: Path):
    db_path = tmp_path / "market_data.sqlite"
    init_main_universe_db(db_path)
    save_main_universe(
        MainUniverseSaveRequest(
            mode="replace",
            rows=[
                {"symbol": "300750", "ts_code": "300750.SZ", "stock_name": "宁德时代"},
                {"symbol": "601138", "ts_code": "601138.SH", "stock_name": "工业富联"},
            ],
            source="seed",
        ),
        db_path=db_path,
    )

    result = resolve_stock_names(["宁德时代", "不存在公司"], db_path=db_path)

    assert result["resolved"][0]["symbol"] == "300750"
    assert result["unresolved"] == ["不存在公司"]
    assert result["duplicate_inputs"] == []


def test_save_main_universe_replace_deactivates_missing_rows(tmp_path: Path):
    db_path = tmp_path / "market_data.sqlite"
    init_main_universe_db(db_path)
    save_main_universe(
        MainUniverseSaveRequest(
            mode="replace",
            rows=[
                {"symbol": "300750", "ts_code": "300750.SZ", "stock_name": "宁德时代"},
                {"symbol": "601138", "ts_code": "601138.SH", "stock_name": "工业富联"},
            ],
            source="seed",
        ),
        db_path=db_path,
    )
    save_main_universe(
        MainUniverseSaveRequest(
            mode="replace",
            rows=[{"symbol": "300750", "ts_code": "300750.SZ", "stock_name": "宁德时代"}],
            source="admin_upload",
        ),
        db_path=db_path,
    )

    rows = list_main_universe(db_path=db_path, include_inactive=True)
    by_symbol = {row["symbol"]: row for row in rows}
    assert by_symbol["300750"]["is_active"] == 1
    assert by_symbol["601138"]["is_active"] == 0
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
pytest tests/test_main_universe.py -v
```

Expected: FAIL because `overnight_bt.main_universe` does not exist.

- [ ] **Step 3: Implement `overnight_bt/main_universe.py`**

Create a focused module with:

```python
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Literal

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MARKET_DB_PATH = PROJECT_ROOT / "data_store" / "market_data.sqlite"


@dataclass
class MainUniverseSaveRequest:
    mode: Literal["append", "replace"]
    rows: list[dict[str, str]]
    source: str = "admin_upload"


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _db_path(db_path: str | Path | None = None) -> Path:
    path = Path(db_path or DEFAULT_MARKET_DB_PATH)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_main_universe_db(db_path: str | Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS main_stock_universe (
                symbol TEXT PRIMARY KEY,
                ts_code TEXT NOT NULL,
                stock_name TEXT NOT NULL,
                source TEXT DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_main_universe_name ON main_stock_universe(stock_name)")


def normalize_symbol(symbol: str) -> str:
    text = str(symbol or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) != 6:
        raise ValueError(f"股票代码格式错误：{symbol}")
    return digits


def ts_code_from_symbol(symbol: str) -> str:
    code = normalize_symbol(symbol)
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def save_main_universe(req: MainUniverseSaveRequest, db_path: str | Path | None = None) -> dict:
    init_main_universe_db(db_path)
    now = _now_text()
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in req.rows:
        symbol = normalize_symbol(str(row.get("symbol") or ""))
        if symbol in seen:
            continue
        seen.add(symbol)
        stock_name = str(row.get("stock_name") or row.get("name") or "").strip()
        if not stock_name:
            raise ValueError(f"{symbol} 缺少股票名称")
        cleaned.append(
            {
                "symbol": symbol,
                "ts_code": str(row.get("ts_code") or ts_code_from_symbol(symbol)).strip(),
                "stock_name": stock_name,
            }
        )
    with _connect(db_path) as conn:
        if req.mode == "replace":
            conn.execute("UPDATE main_stock_universe SET is_active=0, updated_at=?", (now,))
        for row in cleaned:
            conn.execute(
                """
                INSERT INTO main_stock_universe(symbol, ts_code, stock_name, source, is_active, created_at, updated_at)
                VALUES(?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    ts_code=excluded.ts_code,
                    stock_name=excluded.stock_name,
                    source=excluded.source,
                    is_active=1,
                    updated_at=excluded.updated_at
                """,
                (row["symbol"], row["ts_code"], row["stock_name"], req.source, now, now),
            )
    return {"saved_count": len(cleaned), "mode": req.mode}


def list_main_universe(db_path: str | Path | None = None, include_inactive: bool = False) -> list[dict]:
    init_main_universe_db(db_path)
    where = "" if include_inactive else "WHERE is_active=1"
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT symbol, ts_code, stock_name, source, is_active, created_at, updated_at FROM main_stock_universe {where} ORDER BY symbol"
        ).fetchall()
    return [dict(row) for row in rows]


def resolve_stock_names(names: Iterable[str], db_path: str | Path | None = None) -> dict:
    init_main_universe_db(db_path)
    resolved: list[dict] = []
    unresolved: list[str] = []
    duplicate_inputs: list[str] = []
    seen_inputs: set[str] = set()
    with _connect(db_path) as conn:
        for raw in names:
            name = str(raw or "").strip()
            if not name:
                continue
            if name in seen_inputs:
                duplicate_inputs.append(name)
                continue
            seen_inputs.add(name)
            rows = conn.execute(
                """
                SELECT symbol, ts_code, stock_name
                FROM main_stock_universe
                WHERE is_active=1 AND stock_name=?
                ORDER BY symbol
                """,
                (name,),
            ).fetchall()
            if len(rows) == 1:
                resolved.append(dict(rows[0]))
            else:
                unresolved.append(name)
    return {"resolved": resolved, "unresolved": unresolved, "duplicate_inputs": duplicate_inputs}
```

- [ ] **Step 4: Add Pydantic request models**

In `overnight_bt/models.py`, add:

```python
class MainUniverseResolveRequest(BaseModel):
    stock_names: list[str] = Field(default_factory=list, description="股票名称列表")


class MainUniverseSaveApiRequest(BaseModel):
    mode: Literal["append", "replace"] = Field("append", description="append=追加，replace=替换主股票池")
    rows: list[dict] = Field(default_factory=list, description="已解析股票行")
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/test_main_universe.py -v
```

Expected: PASS.

---

### Task 2: Move Template Validation To Main Universe

**Files:**
- Modify: `overnight_bt/stock_pool_templates.py`
- Modify: `overnight_bt/app.py`
- Test: `tests/test_stock_pool_templates.py`

- [ ] **Step 1: Add failing template validation test**

Add a test that attempts to save a template with a stock name that is not in `main_stock_universe`:

```python
import pytest

from overnight_bt.main_universe import MainUniverseSaveRequest, save_main_universe
from overnight_bt.stock_pool_templates import save_stock_pool_template


def test_template_save_rejects_names_outside_main_universe(tmp_path):
    db_path = tmp_path / "stock_pool_templates.sqlite"
    market_db_path = tmp_path / "market_data.sqlite"
    save_main_universe(
        MainUniverseSaveRequest(
            mode="replace",
            rows=[{"symbol": "300750", "ts_code": "300750.SZ", "stock_name": "宁德时代"}],
        ),
        db_path=market_db_path,
    )

    with pytest.raises(ValueError, match="不在主股票池"):
        save_stock_pool_template(
            username="admin",
            template_name="测试模板",
            description="",
            stock_text="不存在公司",
            db_path=db_path,
            main_universe_db_path=market_db_path,
        )
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
pytest tests/test_stock_pool_templates.py::test_template_save_rejects_names_outside_main_universe -v
```

Expected: FAIL because `save_stock_pool_template` does not accept `main_universe_db_path` yet.

- [ ] **Step 3: Update template save implementation**

In `overnight_bt/stock_pool_templates.py`, import `resolve_stock_names` and change save-time parsing so stock names are resolved against the main universe. Keep existing symbol parsing as compatibility, but require the final symbol to exist in `main_stock_universe`.

Implementation rule:

```python
def save_stock_pool_template(..., main_universe_db_path: str | Path | None = None):
    parsed_names = parse_stock_names_or_symbols(stock_text)
    resolved = resolve_stock_names(parsed_names.names, db_path=main_universe_db_path)
    if resolved["unresolved"]:
        raise ValueError("以下股票不在主股票池，不能保存模板：" + "、".join(resolved["unresolved"][:20]))
    # write resolved symbol + stock_name to stock_pool_template_stocks
```

- [ ] **Step 4: Update API boundary**

In `overnight_bt/app.py`, pass the default main universe DB path when saving templates. The API must reject invalid template stocks before writing any template rows.

- [ ] **Step 5: Run template tests**

Run:

```bash
pytest tests/test_stock_pool_templates.py -v
```

Expected: PASS.

---

### Task 3: Add Market Data Store Read Layer

**Files:**
- Create: `overnight_bt/market_data_store.py`
- Test: `tests/test_market_data_store.py`

- [ ] **Step 1: Write failing tests for filtering by symbols**

Create `tests/test_market_data_store.py`:

```python
from pathlib import Path

from overnight_bt.market_data_store import init_market_data_db, read_feature_rows, upsert_feature_rows


def test_read_feature_rows_filters_symbols_and_dates(tmp_path: Path):
    db_path = tmp_path / "market_data.sqlite"
    init_market_data_db(db_path)
    upsert_feature_rows(
        [
            {"symbol": "300750", "trade_date": "20260520", "ts_code": "300750.SZ", "name": "宁德时代", "raw_open": 200.0, "raw_close": 201.0, "close": 201.0},
            {"symbol": "601138", "trade_date": "20260520", "ts_code": "601138.SH", "name": "工业富联", "raw_open": 50.0, "raw_close": 51.0, "close": 51.0},
        ],
        db_path=db_path,
    )

    rows = read_feature_rows(["300750"], start_date="20260520", end_date="20260520", db_path=db_path)

    assert len(rows) == 1
    assert rows[0]["symbol"] == "300750"
    assert rows[0]["raw_open"] == 200.0
```

- [ ] **Step 2: Run failing test**

Run:

```bash
pytest tests/test_market_data_store.py -v
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement market data store**

Create `overnight_bt/market_data_store.py` with table initialization and read/upsert helpers. Include at least columns used by paper trading and current condition parsing:

```python
CREATE TABLE IF NOT EXISTS stock_daily_features (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    ts_code TEXT DEFAULT '',
    name TEXT DEFAULT '',
    raw_open REAL,
    raw_close REAL,
    close REAL,
    can_buy_open_t INTEGER,
    can_sell_t INTEGER,
    m5 REAL,
    m10 REAL,
    m20 REAL,
    amount REAL,
    PRIMARY KEY(symbol, trade_date)
)
```

Use dynamic column filtering when reading so extra existing indicator columns remain available to expressions.

- [ ] **Step 4: Run market data tests**

Run:

```bash
pytest tests/test_market_data_store.py -v
```

Expected: PASS.

---

### Task 4: Route Backtest, Daily Plan, Single Stock Through Template Symbols Plus Market Data

**Files:**
- Modify: `overnight_bt/backtest.py`
- Modify: `overnight_bt/daily_plan.py`
- Modify: `overnight_bt/single_stock.py`
- Test: `tests/test_api_integration.py`
- Test: `tests/test_single_stock.py`

- [ ] **Step 1: Add regression tests for stock_pool mode**

Add tests proving that:

```text
stock_pool_template_stocks supplies the symbols
stock_daily_features from market data supplies rows
no template-specific feature update is required
```

Use a temporary template DB and market DB. Insert one template row for `300750` and one feature row for `300750`.

- [ ] **Step 2: Run failing tests**

Run:

```bash
pytest tests/test_api_integration.py tests/test_single_stock.py -k stock_pool -v
```

Expected: FAIL where existing code still joins template stocks to the old `stock_daily_features` table in the template DB.

- [ ] **Step 3: Add helper to read template symbols**

Add or reuse a function:

```python
def read_template_symbols(username: str, template_name: str, db_path: str | Path | None = None) -> list[dict]:
    # returns [{"symbol": "300750", "stock_name": "宁德时代"}]
```

- [ ] **Step 4: Replace stock_pool data loading**

In each affected module:

```python
symbols = read_template_symbols(username, template_name, db_path=template_db_path)
feature_rows = read_feature_rows([row["symbol"] for row in symbols], start_date=start_date, end_date=end_date)
```

Convert rows to the same DataFrame shape expected by existing downstream logic.

- [ ] **Step 5: Run regression tests**

Run:

```bash
pytest tests/test_api_integration.py tests/test_single_stock.py -k stock_pool -v
```

Expected: PASS.

---

### Task 5: Route Paper Trading Through Market Data Store

**Files:**
- Modify: `overnight_bt/paper_trading.py`
- Modify: `scripts/run_paper_trading_cron.sh`
- Test: `tests/test_paper_trading.py`

- [ ] **Step 1: Add failing tests for after-close without template feature update**

Add a test where:

```text
template DB has stock_pool_template_stocks
market data DB has stock_daily_features
template DB does not have stock_daily_features
after-close can still generate orders
```

- [ ] **Step 2: Run failing test**

Run:

```bash
pytest tests/test_paper_trading.py -k "after_close and market_data" -v
```

Expected: FAIL because `run_paper_trading_cron.sh` and `paper_trading.py` still check the template DB feature table.

- [ ] **Step 3: Replace `StockPoolDailyPriceProvider`**

Change it to read from `market_data_store.read_feature_row(symbol, trade_date)` instead of joining `stock_daily_features` inside `stock_pool_templates.sqlite`.

- [ ] **Step 4: Replace latest-date checks**

Replace `ensure_stock_pool_latest()` in `scripts/run_paper_trading_cron.sh` with a market-data check:

```text
for each account template:
  read template symbols
  ensure market data has target trade_date for all required symbols
```

The check must not depend on the old template feature update table.

- [ ] **Step 5: Run paper trading tests**

Run:

```bash
pytest tests/test_paper_trading.py -v
```

Expected: PASS.

---

### Task 6: Add Scheduler Run Store

**Files:**
- Create: `overnight_bt/scheduler.py`
- Modify: `overnight_bt/models.py`
- Modify: `overnight_bt/app.py`
- Test: `tests/test_scheduler.py`

- [ ] **Step 1: Write failing scheduler tests**

Create tests for:

```python
from overnight_bt.scheduler import init_scheduler_db, record_run_end, record_run_start, list_runs


def test_scheduler_records_failed_run(tmp_path):
    db_path = tmp_path / "scheduler.sqlite"
    init_scheduler_db(db_path)
    run_id = record_run_start("core_after_close", "20260521", db_path=db_path)
    record_run_end(run_id, status="failed", failed_stage="build_features", error_summary="字段缺失", log_file="logs/x.log", db_path=db_path)

    rows = list_runs(limit=5, db_path=db_path)
    assert rows[0]["status"] == "failed"
    assert rows[0]["failed_stage"] == "build_features"
```

- [ ] **Step 2: Run failing test**

Run:

```bash
pytest tests/test_scheduler.py -v
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement scheduler DB**

Create `scheduler_jobs` and `scheduler_job_runs` tables in `data_store/scheduler.sqlite`.

`scheduler_job_runs` fields:

```text
run_id, job_name, target_date, status, started_at, finished_at,
duration_seconds, failed_stage, error_summary, log_file, retry_of_run_id
```

- [ ] **Step 4: Add admin APIs**

In `overnight_bt/app.py`, add:

```text
GET /api/admin/overview
GET /api/admin/scheduler/runs
POST /api/admin/scheduler/runs/{run_id}/retry
```

Retry API only allows safe tasks: daily sync, feature build, core after-close generate. It must reject open execute retry with HTTP 400.

- [ ] **Step 5: Run scheduler tests**

Run:

```bash
pytest tests/test_scheduler.py -v
```

Expected: PASS.

---

### Task 7: Split Core And Auxiliary Pipelines

**Files:**
- Create: `scripts/run_core_after_close_pipeline.sh`
- Create: `scripts/run_aux_research_pipeline.sh`
- Modify: `scripts/run_after_close_pipeline.sh`
- Test: `tests/test_delivery_checks.py`

- [ ] **Step 1: Add delivery check expectations**

Update delivery checks so core script exists and is executable:

```python
def test_core_after_close_script_exists():
    path = Path("scripts/run_core_after_close_pipeline.sh")
    assert path.exists()
```

- [ ] **Step 2: Run failing delivery test**

Run:

```bash
pytest tests/test_delivery_checks.py -k core_after_close -v
```

Expected: FAIL because script does not exist.

- [ ] **Step 3: Create core script**

The core script must:

```text
1. determine target trade date
2. record scheduler run start
3. run main-universe daily sync
4. run feature build
5. validate feature data date
6. run paper after-close
7. record scheduler success or failure
```

It must not run sector research, rotation diagnosis, or stock pool template feature update.

- [ ] **Step 4: Create auxiliary script**

Move sector and rotation commands to `scripts/run_aux_research_pipeline.sh`. Its failure must write scheduler failure but not affect core after-close.

- [ ] **Step 5: Keep old script as compatibility wrapper**

Change `scripts/run_after_close_pipeline.sh` to call the core script by default and print a clear message that auxiliary research is separate.

- [ ] **Step 6: Run script checks**

Run:

```bash
bash -n scripts/run_core_after_close_pipeline.sh
bash -n scripts/run_aux_research_pipeline.sh
bash -n scripts/run_after_close_pipeline.sh
```

Expected: all commands exit 0.

---

### Task 8: Rewrite Admin Page Into Operations Dashboard

**Files:**
- Modify: `static/admin.html`
- Modify: `static/admin.js`
- Modify: `static/style.css`
- Test: `tests/test_api_integration.py`

- [ ] **Step 1: Add API smoke test**

Add tests that admin can load overview and scheduler runs:

```python
def test_admin_overview_requires_admin(authenticated_admin_client):
    response = authenticated_admin_client.get("/api/admin/overview")
    assert response.status_code == 200
    assert "core_tasks" in response.json()
```

- [ ] **Step 2: Update HTML layout**

Remove:

```text
模板数据
刷新指定股票池模板
最近数据任务 from stock pool feature update
```

Add sections:

```text
核心任务状态
主股票池维护
任务运行记录
安全重跑
```

- [ ] **Step 3: Update JS data flow**

`static/admin.js` should call:

```text
/api/admin/overview
/api/admin/main-universe
/api/admin/main-universe/resolve
/api/admin/main-universe/save
/api/admin/scheduler/runs
/api/admin/scheduler/runs/{run_id}/retry
```

Status text must say whether data was written.

- [ ] **Step 4: Run frontend/API tests**

Run:

```bash
pytest tests/test_api_integration.py -k admin -v
```

Expected: PASS.

---

### Task 9: Remove Template Data Refresh From User-Facing Flows

**Files:**
- Modify: `static/stock_pools.html`
- Modify: `static/stock_pools.js`
- Modify: `overnight_bt/app.py`
- Modify: docs about stock pool templates
- Test: `tests/test_stock_pool_templates.py`

- [ ] **Step 1: Remove refresh controls**

Remove buttons and copy that imply templates have their own data refresh task.

- [ ] **Step 2: Keep legacy API hidden**

Keep `/api/stock-pools/template/refresh` callable for now, but do not link it from admin or stock-pools UI. Add response field:

```json
{"legacy": true}
```

or document it as legacy in API docs.

- [ ] **Step 3: Update docs**

State:

```text
股票池模板只保存股票集合。模板保存时必须通过主股票池校验。模板不再拥有独立行情指标更新任务。
```

- [ ] **Step 4: Run stock pool tests**

Run:

```bash
pytest tests/test_stock_pool_templates.py -v
```

Expected: PASS.

---

### Task 10: Full Verification On Tencent Cloud

**Files:**
- No new files unless fixes are needed.

- [ ] **Step 1: Run unit and integration tests**

Run:

```bash
pytest tests/test_main_universe.py tests/test_market_data_store.py tests/test_scheduler.py -v
pytest tests/test_stock_pool_templates.py tests/test_paper_trading.py tests/test_single_stock.py -v
pytest tests/test_api_integration.py -v
```

Expected: PASS.

- [ ] **Step 2: Run delivery check**

Run:

```bash
python scripts/verify_delivery.py
```

Expected: PASS or only documented unrelated pre-existing warnings.

- [ ] **Step 3: Restart FastAPI service**

Run on Tencent Cloud:

```bash
sudo systemctl restart t0-system
curl -s http://127.0.0.1:8083/health
```

Expected:

```json
{"status":"ok"}
```

- [ ] **Step 4: Smoke test admin and stock pool pages**

Run:

```bash
curl -I http://127.0.0.1:8083/admin
curl -I http://127.0.0.1:8083/stock-pools
```

Expected: authenticated environment returns 200 or unauthenticated redirect behavior matching auth design.

- [ ] **Step 5: Check core script syntax**

Run:

```bash
bash -n scripts/run_core_after_close_pipeline.sh
bash -n scripts/run_paper_trading_cron.sh
```

Expected: both exit 0.

---

## Self-Review

Spec coverage:

- Main universe maintenance is covered by Tasks 1, 2, and 8.
- Database-backed market data is covered by Tasks 3, 4, and 5.
- Template data refresh removal is covered by Tasks 2 and 9.
- Core and auxiliary schedule split is covered by Tasks 6 and 7.
- Admin operations dashboard is covered by Task 8.
- Verification is covered by Task 10.

Placeholder scan:

- No TBD/TODO placeholders are present.
- Legacy behavior is explicitly scoped and not left undefined.

Type consistency:

- `MainUniverseSaveRequest`, `main_stock_universe`, `stock_daily_features`, `scheduler_job_runs`, and API path names are used consistently across tasks.

Execution note:

- Do not commit automatically. AGENTS.md says commit/push only when the user explicitly asks for GitHub delivery.
