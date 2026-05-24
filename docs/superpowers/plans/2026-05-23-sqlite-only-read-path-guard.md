# SQLite-only Read Path Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a SQLite-only guard and audit path so core runtime modules cannot silently read legacy CSV, legacy YAML templates, or legacy stock-pool feature rows during the SQLite master-data migration.

**Architecture:** Introduce a small runtime guard module that is controlled by an environment variable and optional explicit parameters. Keep legacy compatibility available by default for research scripts, but make scheduler/admin runtime able to fail fast when old CSV/YAML/fallback paths are touched.

**Tech Stack:** Python 3.12, pytest, SQLite, existing `overnight_bt` modules, Bash cron scripts.

---

### Task 1: Add Guard API

**Files:**
- Create: `overnight_bt/sqlite_only_guard.py`
- Test: `tests/test_sqlite_only_guard.py`

- [ ] Write tests for disabled/enabled guard, blocked source labels, and allowed source labels.
- [ ] Implement `is_sqlite_only_enabled()`, `assert_sqlite_only_allowed(source, detail='')`, and `sqlite_only_disabled()` context manager.
- [ ] Run: `pytest tests/test_sqlite_only_guard.py -v`.

### Task 2: Block Legacy Feature Fallback In SQLite-only Mode

**Files:**
- Modify: `overnight_bt/market_data_store.py`
- Test: `tests/test_market_data_store.py`

- [ ] Add a failing test showing `read_feature_rows(..., legacy_db_path=legacy_db)` raises when `T0_SQLITE_ONLY=1`.
- [ ] Keep `legacy_db_path=DISABLE_LEGACY_FALLBACK` allowed.
- [ ] Implement guard before `_read_legacy_rows` opens the legacy DB.
- [ ] Run: `pytest tests/test_market_data_store.py -v`.

### Task 3: Block CSV/Excel Runtime Reads In SQLite-only Mode

**Files:**
- Modify: `overnight_bt/backtest.py`
- Modify: `overnight_bt/single_stock.py`
- Test: `tests/test_backtest.py`
- Test: `tests/test_single_stock.py`

- [ ] Add failing tests for `load_processed_folder()` and single-stock CSV/Excel paths under `T0_SQLITE_ONLY=1`.
- [ ] Implement guard in CSV folder loader and Excel loader before file reads.
- [ ] Keep `data_source='stock_pool'` working.
- [ ] Run: `pytest tests/test_backtest.py tests/test_single_stock.py -v`.

### Task 4: Block Legacy YAML Auto-import In SQLite-only Mode

**Files:**
- Modify: `overnight_bt/paper_trading.py`
- Test: `tests/test_paper_trading.py`

- [ ] Add failing test showing `list_paper_account_templates(config_dir_with_yaml)` returns empty instead of importing YAML when `T0_SQLITE_ONLY=1` and SQLite has no templates.
- [ ] Add failing test showing explicit SQLite templates still list normally.
- [ ] Implement guard inside `_legacy_templates_to_sqlite` or its callers so automatic import is skipped in SQLite-only mode.
- [ ] Run: `pytest tests/test_paper_trading.py -v`.

### Task 5: Add Read-path Audit Script

**Files:**
- Create: `scripts/audit_sqlite_only_read_paths.py`
- Test: `tests/test_sqlite_only_audit.py`

- [ ] Write test with temporary files containing `data_bundle`, `pd.read_csv`, YAML import, and legacy fallback markers.
- [ ] Implement script to scan `overnight_bt/`, `scripts/`, and `static/`, output JSON/text summary, and optionally fail with `--fail-on-legacy`.
- [ ] Exclude generated caches and docs from failure by default.
- [ ] Run: `pytest tests/test_sqlite_only_audit.py -v`.

### Task 6: Wire Scheduler Check-only To SQLite-only Mode

**Files:**
- Modify: `scripts/run_paper_trading_cron.sh`
- Modify: `scripts/run_core_after_close_pipeline.sh`
- Test: shell smoke through existing runtime command

- [ ] Export `T0_SQLITE_ONLY=1` for paper-trading cron and core after-close pipeline unless explicitly overridden.
- [ ] Ensure `--check-only after-close 20260521` still passes after soft reset and one-stock collection.
- [ ] Run: `scripts/run_paper_trading_cron.sh --check-only after-close 20260521`.

### Task 7: Verification

**Files:**
- No code files unless fixing test failures.

- [ ] Run targeted tests: `pytest tests/test_sqlite_only_guard.py tests/test_market_data_store.py tests/test_backtest.py tests/test_single_stock.py tests/test_paper_trading.py tests/test_sqlite_only_audit.py -v`.
- [ ] Run delivery check: `python scripts/verify_delivery.py`.
- [ ] Run soft reset + one-stock collection + check-only smoke if runtime data was touched.
- [ ] Report remaining legacy read-path audit findings as follow-up work, not as completed migration.