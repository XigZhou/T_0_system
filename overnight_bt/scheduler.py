from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data_store" / "scheduler.sqlite"
SAFE_RETRY_JOB_NAMES = frozenset({"daily_sync", "feature_build", "core_after_close_generate"})


def _db_path(db_path: str | Path | None = None) -> Path:
    return Path(db_path) if db_path is not None else DEFAULT_DB_PATH


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean_required(value: object, field: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise ValueError(f"{field} 不能为空")
    return clean


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def init_scheduler_db(db_path: str | Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduler_jobs (
                job_name TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_run_id TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduler_job_runs (
                run_id TEXT PRIMARY KEY,
                job_name TEXT NOT NULL,
                target_date TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL DEFAULT '',
                duration_seconds REAL,
                failed_stage TEXT NOT NULL DEFAULT '',
                error_summary TEXT NOT NULL DEFAULT '',
                log_file TEXT NOT NULL DEFAULT '',
                retry_of_run_id TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(job_name) REFERENCES scheduler_jobs(job_name)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_scheduler_job_runs_started_at ON scheduler_job_runs(started_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_scheduler_job_runs_job_name ON scheduler_job_runs(job_name, started_at DESC)"
        )


def _upsert_job(conn: sqlite3.Connection, job_name: str, run_id: str, now: str) -> None:
    conn.execute(
        """
        INSERT INTO scheduler_jobs(job_name, created_at, updated_at, last_run_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(job_name) DO UPDATE SET
            updated_at = excluded.updated_at,
            last_run_id = excluded.last_run_id
        """,
        (job_name, now, now, run_id),
    )


def record_run_start(
    job_name: str,
    target_date: str = "",
    log_file: str = "",
    retry_of_run_id: str = "",
    status: str = "running",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    clean_job_name = _clean_required(job_name, "job_name")
    clean_status = _clean_required(status, "status")
    init_scheduler_db(db_path)
    run_id = uuid.uuid4().hex
    now = _now_text()
    with _connect(db_path) as conn:
        _upsert_job(conn, clean_job_name, run_id, now)
        conn.execute(
            """
            INSERT INTO scheduler_job_runs(
                run_id, job_name, target_date, status, started_at, log_file, retry_of_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                clean_job_name,
                str(target_date or "").strip(),
                clean_status,
                now,
                str(log_file or "").strip(),
                str(retry_of_run_id or "").strip(),
            ),
        )
    return get_run(run_id, db_path=db_path)


def _duration_seconds(started_at: str, finished_at: str) -> float:
    try:
        return max(0.0, (datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)).total_seconds())
    except ValueError:
        return 0.0


def record_run_end(
    run_id: str,
    status: str,
    failed_stage: str = "",
    error_summary: str = "",
    log_file: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    clean_run_id = _clean_required(run_id, "run_id")
    clean_status = _clean_required(status, "status")
    run = get_run(clean_run_id, db_path=db_path)
    finished_at = _now_text()
    duration_seconds = _duration_seconds(str(run["started_at"]), finished_at)
    next_log_file = str(run.get("log_file") or "") if log_file is None else str(log_file or "").strip()
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE scheduler_job_runs
            SET status = ?, finished_at = ?, duration_seconds = ?, failed_stage = ?,
                error_summary = ?, log_file = ?
            WHERE run_id = ?
            """,
            (
                clean_status,
                finished_at,
                duration_seconds,
                str(failed_stage or "").strip(),
                str(error_summary or "").strip(),
                next_log_file,
                clean_run_id,
            ),
        )
    return get_run(clean_run_id, db_path=db_path)


def get_run(run_id: str, db_path: str | Path | None = None) -> dict[str, Any]:
    clean_run_id = _clean_required(run_id, "run_id")
    init_scheduler_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM scheduler_job_runs WHERE run_id = ?", (clean_run_id,)).fetchone()
    result = _row_dict(row)
    if result is None:
        raise FileNotFoundError(f"scheduler run 不存在: {clean_run_id}")
    return result


def list_runs(limit: int = 50, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    init_scheduler_db(db_path)
    clean_limit = max(1, min(int(limit), 1000))
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM scheduler_job_runs
            ORDER BY started_at DESC, run_id DESC
            LIMIT ?
            """,
            (clean_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_retry_run(run_id: str, db_path: str | Path | None = None) -> dict[str, Any]:
    original = get_run(run_id, db_path=db_path)
    if original["job_name"] not in SAFE_RETRY_JOB_NAMES:
        raise ValueError(f"任务 {original['job_name']} 不允许安全重跑")
    if str(original.get("status") or "") != "failed":
        raise ValueError("只有失败的任务运行记录可以登记安全重跑")
    return record_run_start(
        job_name=str(original["job_name"]),
        target_date=str(original.get("target_date") or ""),
        log_file=str(original.get("log_file") or ""),
        retry_of_run_id=str(original["run_id"]),
        status="retry_pending",
        db_path=db_path,
    )
