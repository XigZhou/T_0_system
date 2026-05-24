from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from overnight_bt.app import (
    _direct_user,
    admin_overview_api,
    admin_scheduler_retry_run_api,
    admin_scheduler_runs_api,
)
from overnight_bt.models import SchedulerRetryRequest
from overnight_bt.scheduler import create_retry_run, list_runs, record_run_end, record_run_start


class SchedulerRunStoreTest(unittest.TestCase):
    def test_failed_run_lists_failed_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scheduler.sqlite"

            run = record_run_start(
                job_name="daily_sync",
                target_date="20260521",
                log_file="logs/daily-sync.log",
                db_path=db_path,
            )
            record_run_end(
                run["run_id"],
                status="failed",
                failed_stage="fetch_daily",
                error_summary="Tushare 数据拉取失败",
                db_path=db_path,
            )

            rows = list_runs(db_path=db_path)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["run_id"], run["run_id"])
        self.assertEqual(rows[0]["status"], "failed")
        self.assertEqual(rows[0]["failed_stage"], "fetch_daily")
        self.assertEqual(rows[0]["error_summary"], "Tushare 数据拉取失败")
        self.assertGreaterEqual(rows[0]["duration_seconds"], 0)

    def test_retry_helper_allows_only_safe_scheduler_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scheduler.sqlite"
            allowed_names = ["daily_sync", "feature_build", "core_after_close_generate"]
            for job_name in allowed_names:
                original = record_run_start(job_name=job_name, target_date="20260521", db_path=db_path)
                with self.assertRaisesRegex(ValueError, "只有失败"):
                    create_retry_run(original["run_id"], db_path=db_path)
                record_run_end(
                    original["run_id"],
                    status="failed",
                    failed_stage="pytest",
                    error_summary="测试失败任务重跑",
                    db_path=db_path,
                )
                retry = create_retry_run(original["run_id"], db_path=db_path)
                self.assertEqual(retry["job_name"], job_name)
                self.assertEqual(retry["retry_of_run_id"], original["run_id"])
                self.assertEqual(retry["status"], "retry_pending")

            for job_name in ["open_execute", "execute"]:
                original = record_run_start(job_name=job_name, target_date="20260521", db_path=db_path)
                with self.assertRaisesRegex(ValueError, "不允许安全重跑"):
                    create_retry_run(original["run_id"], db_path=db_path)

    def test_admin_scheduler_api_lists_runs_and_records_safe_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scheduler.sqlite"
            original = record_run_start(
                job_name="core_after_close_generate",
                target_date="20260521",
                db_path=db_path,
            )
            record_run_end(
                original["run_id"],
                status="failed",
                failed_stage="generate",
                error_summary="生成失败",
                db_path=db_path,
            )

            with patch("overnight_bt.app.SCHEDULER_DB_PATH", db_path):
                overview = admin_overview_api(current_user=_direct_user())
                listed = admin_scheduler_runs_api(current_user=_direct_user())
                retried = admin_scheduler_retry_run_api(
                    run_id=original["run_id"],
                    req=SchedulerRetryRequest(),
                    current_user=_direct_user(),
                )

        self.assertIn("scheduler", overview)
        self.assertEqual(overview["scheduler"]["run_count"], 1)
        self.assertEqual(listed["runs"][0]["run_id"], original["run_id"])
        self.assertEqual(retried["retry_run"]["retry_of_run_id"], original["run_id"])
        self.assertEqual(retried["retry_run"]["status"], "retry_pending")
        self.assertIn("已登记安全重跑请求", retried["message"])

    def test_admin_scheduler_retry_rejects_open_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "scheduler.sqlite"
            run = record_run_start(job_name="open_execute", target_date="20260521", db_path=db_path)
            record_run_end(
                run["run_id"],
                status="failed",
                failed_stage="execute",
                error_summary="开盘执行失败",
                db_path=db_path,
            )

            with patch("overnight_bt.app.SCHEDULER_DB_PATH", db_path):
                with self.assertRaises(HTTPException) as caught:
                    admin_scheduler_retry_run_api(
                        run_id=run["run_id"],
                        req=SchedulerRetryRequest(),
                        current_user=_direct_user(),
                    )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("不允许安全重跑", caught.exception.detail)


if __name__ == "__main__":
    unittest.main()
