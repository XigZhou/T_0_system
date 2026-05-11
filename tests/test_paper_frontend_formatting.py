from __future__ import annotations

import subprocess
import shutil
import unittest
from pathlib import Path


class PaperFrontendFormattingTest(unittest.TestCase):
    def test_paper_js_formats_money_and_rate_fields(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node is not available")
        repo_root = Path(__file__).resolve().parents[1]
        script = """
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync("static/paper.js", "utf8");
const noop = () => {};
const elements = new Map();
function element(id) {
  if (!elements.has(id)) {
    elements.set(id, {
      id,
      textContent: "",
      style: {},
      dataset: {},
      classList: { toggle: noop },
      setAttribute: noop,
      addEventListener: noop,
      closest: () => null,
      innerHTML: "",
    });
  }
  return elements.get(id);
}
const context = {
  document: {
    getElementById: element,
    querySelectorAll: () => [],
    createElement: () => ({ className: "", textContent: "" }),
  },
  fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({ templates: [] }) }),
  URLSearchParams,
  Number,
  String,
  Math,
  console,
};
vm.createContext(context);
vm.runInContext(code, context);
const checks = [
  [context.formatValue(0.123456, "浮动收益率"), "12.35%"],
  [context.formatValue(0.089123, "累计收益"), "8.91%"],
  [context.formatValue(1234.567, "浮动盈亏"), "1,234.57 元"],
  [context.formatValue(10.123456, "当前价格"), "10.1235 元"],
  [context.formatValue(3, "持有天数"), "3"],
  [context.chinaDateStamp(new Date("2026-05-10T20:30:00Z")), "20260511"],
];
for (const [actual, expected] of checks) {
  if (actual !== expected) {
    throw new Error(`${actual} !== ${expected}`);
  }
}
"""
        try:
            result = subprocess.run(
                ["node", "-e", script],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
        except PermissionError as exc:
            self.skipTest(f"node is not executable: {exc}")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
