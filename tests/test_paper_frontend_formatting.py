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
    const children = [];
    elements.set(id, {
      id,
      textContent: "",
      style: {},
      dataset: {},
      value: "",
      options: children,
      classList: { toggle: noop },
      setAttribute: noop,
      addEventListener: noop,
      closest: () => null,
      appendChild: (child) => {
        children.push(child);
        return child;
      },
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
  window: {
    location: { search: "" },
    history: { replaceState: noop },
  },
  Option: function Option(label, value) {
    return { label, value, dataset: {} };
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
  [context.formatValue("20260429", "买入日期"), "20260429"],
  [context.formatValue("20260429", "trade_date"), "20260429"],
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

    def test_paper_template_copy_creates_new_draft(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node is not available")
        repo_root = Path(__file__).resolve().parents[1]
        script = """
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync("static/paper_templates.js", "utf8");
const noop = () => {};
const elements = new Map();
const handlers = new Map();
const checkboxIds = new Set(["tplSkipIfHolding", "tplSkipIfPendingOrder", "tplStrictExecution"]);
function element(id) {
  if (!elements.has(id)) {
    const options = [];
    elements.set(id, {
      id,
      type: checkboxIds.has(id) ? "checkbox" : "text",
      textContent: "",
      style: {},
      value: "",
      checked: false,
      disabled: false,
      href: "",
      options,
      innerHTML: "",
      appendChild: (child) => {
        options.push(child);
        return child;
      },
      addEventListener: (eventName, handler) => {
        handlers.set(`${id}:${eventName}`, handler);
      },
    });
  }
  return elements.get(id);
}
const context = {
  document: { getElementById: element },
  window: {
    location: { pathname: "/paper/templates", search: "" },
    history: { replaceState: noop },
  },
  Option: function Option(label, value) {
    return { label, value, dataset: {} };
  },
  fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({ templates: [{ template_name: "L2_中等市值主题股层", stock_count: 100 }] }) }),
  URLSearchParams,
  Intl,
  Date,
  Number,
  String,
  Boolean,
  Math,
  RegExp,
  console,
};
vm.createContext(context);
vm.runInContext(code, context);
context.populateTemplateEditor({
  file_name: "sector_l2_top500_v1.yaml",
  account_id: "sector_l2_top500_v1",
  account_name: "L2 Top500 模拟账户",
  initial_cash: 100000,
  stock_pool_username: "admin",
  stock_pool_template_name: "L2_中等市值主题股层",
  stock_pool_db_path: "data_store/stock_pool_templates.sqlite",
  buy_condition: "m20>0",
  sell_condition: "",
  score_expression: "m20",
  top_n: 5,
  entry_offset: 1,
  min_hold_days: 0,
  max_hold_days: 15,
  buy_quantity_mode: "固定股数",
  buy_shares: 200,
  buy_lot_size: 100,
  min_buy_amount: 10000,
  buy_min_close: 0,
  buy_max_close: 150,
  price_primary: "东方财富",
  price_fallback: "腾讯股票",
  price_field: "开盘价",
  buy_fee_rate: 0.00003,
  sell_fee_rate: 0.00003,
  stamp_tax_sell: 0,
  slippage_bps: 3,
  min_commission: 0,
  ledger_path: "paper_trading/accounts/sector_l2_top500_v1.xlsx",
  log_dir: "paper_trading/logs",
  skip_if_holding: true,
  skip_if_pending_order: true,
  strict_execution: true,
});
element("configPath").value = "configs/paper_accounts/sector_l2_top500_v1.yaml";
handlers.get("copyTemplateBtn:click")();
const copiedFile = element("tplFileName").value;
const copiedAccount = element("tplAccountId").value;
const copiedLedger = element("tplLedgerPath").value;
const checks = [
  [element("configPath").value, ""],
  [copiedFile.startsWith("sector_l2_top500_v1_"), true],
  [copiedFile.endsWith("_copy.yaml"), true],
  [copiedAccount.startsWith("sector_l2_top500_v1_"), true],
  [copiedLedger.startsWith("paper_trading/accounts/sector_l2_top500_v1_"), true],
  [copiedLedger.endsWith("_copy.xlsx"), true],
  [element("tplAccountName").value.startsWith("L2 Top500 模拟账户_副本_"), true],
  [element("templateStatus").textContent.includes("已复制当前模板为新草稿"), true],
];
for (const [actual, expected] of checks) {
  if (actual !== expected) {
    throw new Error(`${actual} !== ${expected}`);
  }
}
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    def test_stock_pool_js_copy_and_validation_preview(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node is not available")
        repo_root = Path(__file__).resolve().parents[1]
        script = """
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync("static/stock_pools.js", "utf8");
const elements = new Map();
const handlers = new Map();
function element(id) {
  if (!elements.has(id)) {
    const options = [];
    elements.set(id, {
      id,
      type: "text",
      textContent: "",
      style: {},
      value: "",
      checked: false,
      disabled: false,
      options,
      innerHTML: "",
      appendChild: (child) => {
        options.push(child);
        return child;
      },
      addEventListener: (eventName, handler) => {
        handlers.set(`${id}:${eventName}`, handler);
      },
    });
  }
  return elements.get(id);
}
const responses = [];
const context = {
  document: { getElementById: element },
  window: { confirm: () => true },
  Option: function Option(label, value) {
    return { label, value, dataset: {} };
  },
  fetch: (url) => {
    responses.push(url);
    return new Promise(() => {});
  },
  URLSearchParams,
  Intl,
  Date,
  Number,
  String,
  Boolean,
  Math,
  console,
};
vm.createContext(context);
vm.runInContext(code, context);
context.populatePoolEditor({
  username: "admin",
  template_name: "L2_中等市值主题股层",
  original_template_name: "L2_中等市值主题股层",
  description: "测试模板",
  is_active: true,
  stock_count: 2,
  stock_text: "300750\\n600941",
  stocks: [
    { symbol: "300750", ts_code: "300750.SZ", stock_name: "宁德时代", latest_trade_date: "" },
    { symbol: "600941", ts_code: "600941.SH", stock_name: "中国移动", latest_trade_date: "" },
  ],
});
handlers.get("copyPoolBtn:click")();
if (!element("poolTemplateName").value.startsWith("L2_中等市值主题股层_副本_")) {
  throw new Error("copy name not generated");
}
if (element("poolOriginalTemplateName").value !== "") {
  throw new Error("copy should clear original template name");
}
if (context.collectPoolPayload().username !== "admin") {
  throw new Error("default username should be admin");
}
if (!element("poolStatus").textContent.includes("已复制为新股票池草稿")) {
  throw new Error("copy status missing");
}
context.renderStockRows([
  { symbol: "300750", ts_code: "300750.SZ", stock_name: "宁德时代", latest_trade_date: "20260508" },
]);
if (!element("poolStockRows").innerHTML.includes("宁德时代")) {
  throw new Error("stock rows not rendered");
}
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)


    def test_stock_pool_js_admin_refresh_and_jobs(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node is not available")
        repo_root = Path(__file__).resolve().parents[1]
        script = """
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync("static/stock_pools.js", "utf8");
const elements = new Map();
const handlers = new Map();
function element(id) {
  if (!elements.has(id)) {
    const options = [];
    elements.set(id, {
      id,
      type: "text",
      textContent: "",
      style: {},
      value: "",
      checked: false,
      disabled: false,
      hidden: false,
      options,
      innerHTML: "",
      dataset: {},
      appendChild: (child) => {
        options.push(child);
        return child;
      },
      addEventListener: (eventName, handler) => {
        handlers.set(`${id}:${eventName}`, handler);
      },
      querySelectorAll: () => [],
    });
  }
  return elements.get(id);
}
const calls = [];
const context = {
  document: { getElementById: element },
  window: { confirm: () => true },
  Option: function Option(label, value) {
    return { label, value, dataset: {} };
  },
  fetch: (url, options = {}) => {
    calls.push({ url, options });
    if (url.startsWith("/api/stock-pools/templates")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ templates: [{ template_name: "测试池", stock_count: 1 }] }) });
    }
    if (url.startsWith("/api/stock-pools/template?")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ username: "admin", template_name: "测试池", stock_count: 1, stock_text: "300750", stocks: [{ symbol: "300750", ts_code: "300750.SZ", stock_name: "宁德时代", latest_trade_date: "20260514" }] }) });
    }
    if (url.startsWith("/api/stock-pools/jobs")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ jobs: [{ job_id: "abcdef123456", status: "success", job_type: "manual_refresh", template_name: "测试池", stock_count: 1, success_count: 1, failed_count: 0, end_date: "20260514", finished_at: "2026-05-14 20:00:00", log_file: "logs/job.log" }] }) });
    }
    if (url === "/api/stock-pools/template/refresh") {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: "success", message: "刷新完成" }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  },
  URLSearchParams,
  Intl,
  Date,
  Number,
  String,
  Boolean,
  Math,
  console,
};
vm.createContext(context);
vm.runInContext(code, context);
if (element("stockPoolAdminPanel").hidden !== false) {
  throw new Error("admin panel should be visible for admin");
}
context.populatePoolEditor({ username: "admin", template_name: "测试池", original_template_name: "测试池", stock_text: "300750", stocks: [] });
handlers.get("refreshPoolDataBtn:click")();
setTimeout(() => {
  const refreshCall = calls.find((call) => call.url === "/api/stock-pools/template/refresh");
  if (!refreshCall) {
    throw new Error("refresh api not called");
  }
  const payload = JSON.parse(refreshCall.options.body);
  if (payload.username !== "admin" || payload.template_name !== "测试池" || payload.only_missing !== true) {
    throw new Error("refresh payload is wrong");
  }
}, 0);
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
