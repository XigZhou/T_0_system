from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from overnight_bt.models import StockPoolTemplateSaveRequest
from overnight_bt.stock_pool_templates import (
    DEFAULT_USERNAME,
    delete_stock_pool_template,
    init_stock_pool_db,
    list_stock_pool_templates,
    read_stock_pool_template,
    save_stock_pool_template,
    seed_default_stock_pool_templates,
    validate_stock_pool_symbols,
)


class StockPoolTemplateTest(unittest.TestCase):
    def test_validate_stock_list_normalizes_and_reports_errors(self) -> None:
        result = validate_stock_pool_symbols("300750\n600941.SH, 300750  abc 688981")
        self.assertEqual([row["symbol"] for row in result["valid_stocks"]], ["300750", "600941", "688981"])
        self.assertEqual(result["duplicate_symbols"], ["300750"])
        self.assertEqual(result["invalid_items"], ["abc"])
        self.assertEqual(result["valid_count"], 3)

    def test_save_read_delete_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock_pool.sqlite"
            init_stock_pool_db(db_path)
            saved = save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="手工测试股票池",
                    description="测试保存",
                    stock_text="300750\n600941\n688981",
                ),
                db_path=db_path,
            )
            self.assertIn("尚未触发行情采集", saved["message"])
            loaded = read_stock_pool_template("手工测试股票池", db_path=db_path)
            self.assertEqual(loaded["stock_count"], 3)
            self.assertEqual([row["symbol"] for row in loaded["stocks"]], ["300750", "600941", "688981"])
            self.assertTrue(loaded["is_active"])

            listed = list_stock_pool_templates(db_path=db_path)
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["template_name"], "手工测试股票池")

            deleted = delete_stock_pool_template("手工测试股票池", db_path=db_path)
            self.assertIn("日线数据保留", deleted["message"])
            self.assertEqual(list_stock_pool_templates(db_path=db_path), [])

    def test_rename_template_rewrites_stock_relations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock_pool.sqlite"
            save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    template_name="原股票池",
                    description="改名前",
                    stock_text="300750\n600941",
                ),
                db_path=db_path,
            )
            renamed = save_stock_pool_template(
                StockPoolTemplateSaveRequest(
                    username=DEFAULT_USERNAME,
                    original_template_name="原股票池",
                    template_name="新股票池",
                    description="改名后",
                    stock_text="688981\n600941",
                    overwrite_existing=True,
                ),
                db_path=db_path,
            )
            self.assertEqual(renamed["template"]["template_name"], "新股票池")
            self.assertEqual([row["symbol"] for row in renamed["template"]["stocks"]], ["688981", "600941"])
            self.assertEqual(read_stock_pool_template("新股票池", db_path=db_path)["stock_count"], 2)
            with self.assertRaises(FileNotFoundError):
                read_stock_pool_template("原股票池", db_path=db_path)

    def test_seed_default_templates_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock_pool.sqlite"
            first = seed_default_stock_pool_templates(db_path=db_path)
            second = seed_default_stock_pool_templates(db_path=db_path)
            templates = list_stock_pool_templates(db_path=db_path)
            self.assertGreaterEqual(first["created_count"], 0)
            self.assertEqual(second["created_count"], 0)
            self.assertEqual(len(templates), first["created_count"])
            names = {row["template_name"] for row in templates}
            expected = {
                "L0_最大市值主题股层",
                "L1_偏大市值主题股层",
                "L2_中等市值主题股层",
                "L3_偏小市值主题股层",
                "L4_最小市值主题股层",
                "当前多账户模拟股票池",
            }
            self.assertTrue(names.issubset(expected))


if __name__ == "__main__":
    unittest.main()
