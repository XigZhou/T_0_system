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

    def test_research_and_data_scripts_support_repo_root_invocation(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        for script_name in [
            "scripts/build_universe_snapshot.py",
            "scripts/sync_tushare_bundle.py",
            "scripts/build_processed_data.py",
            "scripts/run_overnight_research.py",
            "scripts/run_overnight_feature_scan.py",
            "scripts/run_buy_condition_grid.py",
            "scripts/run_sell_condition_grid.py",
            "scripts/build_theme_focus_universe.py",
            "scripts/run_universe_hold_compare.py",
            "scripts/run_topn_hold_compare.py",
        ]:
            result = subprocess.run(
                [sys.executable, script_name, "--help"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=f"{script_name}\n{result.stdout}\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()
