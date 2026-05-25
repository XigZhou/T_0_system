from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from overnight_bt.delivery_checks import check_missing_readme_sections, check_missing_required_paths


class DeliveryChecksTest(unittest.TestCase):
    def test_check_missing_readme_sections_returns_missing_titles(self) -> None:
        readme_text = """# 示例项目

## 准备工作

安装依赖。

## 启动方式

运行服务。
"""
        missing = check_missing_readme_sections(readme_text, ["准备工作", "启动方式", "复现结果"])
        self.assertEqual(missing, ["复现结果"])

    def test_check_missing_required_paths_returns_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "README.md").write_text("# 示例\n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "data-dictionary-template.md").write_text("字段说明", encoding="utf-8")

            missing = check_missing_required_paths(
                root,
                [
                    Path("README.md"),
                    Path("docs/data-dictionary-template.md"),
                    Path("docs/indicator-documentation-template.md"),
                ],
            )

        self.assertEqual(missing, [Path("docs/indicator-documentation-template.md")])

    def test_verify_delivery_script_runs_from_repo_root(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "README.md").write_text(
                "# 示例项目\n\n## 准备工作\n\n说明。\n\n## 启动方式\n\n说明。\n\n## 复现结果\n\n说明。\n",
                encoding="utf-8",
            )
            (root / "docs").mkdir()
            (root / "docs" / "data-dictionary-template.md").write_text("字段说明", encoding="utf-8")
            (root / "docs" / "indicator-documentation-template.md").write_text("指标说明", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, "scripts/verify_delivery.py", "--root", str(root)],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("交付检查通过。", result.stdout)

    def test_core_sqlite_scripts_support_repo_root_invocation(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        for script_name in [
            "scripts/init_main_universe_from_tushare.py",
            "scripts/collect_stock_daily_raw.py",
            "scripts/compute_stock_daily_features.py",
            "scripts/run_paper_trading.py",
            "scripts/verify_delivery.py",
        ]:
            result = subprocess.run(
                [sys.executable, script_name, "--help"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=f"{script_name}\n{result.stdout}\n{result.stderr}")

    def test_delivery_checker_tracks_current_sqlite_docs_not_historical_docs(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        checker = (repo_root / "scripts" / "verify_delivery.py").read_text(encoding="utf-8")
        extra_block = checker.split("PROJECT_REMOVED_PATHS =", 1)[0]
        removed_block = checker.split("PROJECT_REMOVED_PATHS =", 1)[1]

        for required in [
            "docs/sqlite-data-dictionary.md",
            "scripts/collect_stock_daily_raw.py",
            "scripts/compute_stock_daily_features.py",
            "scripts/run_core_after_close_pipeline.sh",
            "source=all",
            "market_data.sqlite",
            "stock_daily_features",
        ]:
            self.assertIn(required, checker)

        for historical in [
            "docs/sector-research-system-guide.md",
            "docs/sector-parameter-grid-data-dictionary.md",
            "docs/sector-rotation-grid-data-dictionary.md",
            "docs/stock-pool-template-system-plan.md",
        ]:
            self.assertNotIn(f"Path(\"{historical}\")", extra_block)
            self.assertIn(f"Path(\"{historical}\")", removed_block)


if __name__ == "__main__":
    unittest.main()