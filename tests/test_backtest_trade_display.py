from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from overnight_bt.app import run_signal_quality_api
from overnight_bt.models import SignalQualityRequest
from tests.helpers import make_processed_stock, write_processed_dir


class BacktestTradeDisplayTest(unittest.TestCase):
    def test_signal_quality_trade_rows_use_budget_sized_shares(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            stock_a = make_processed_stock(
                "000001",
                "平安银行",
                [
                    {"trade_date": "20240102", "raw_open": 10.0, "raw_high": 10.2, "raw_low": 9.8, "raw_close": 10.0, "m20": 0.2, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240103", "raw_open": 10.2, "raw_high": 10.4, "raw_low": 10.1, "raw_close": 10.3, "m20": 0.18, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240104", "raw_open": 10.5, "raw_high": 10.7, "raw_low": 10.4, "raw_close": 10.6, "m20": 0.05, "can_buy_open_t": True, "can_sell_t": True},
                    {"trade_date": "20240105", "raw_open": 10.7, "raw_high": 10.8, "raw_low": 10.6, "raw_close": 10.7, "m20": 0.04, "can_buy_open_t": True, "can_sell_t": True},
                ],
            )
            processed_dir = write_processed_dir(base, [stock_a])
            body = run_signal_quality_api(
                SignalQualityRequest(
                    processed_dir=str(processed_dir),
                    start_date="20240102",
                    end_date="20240102",
                    buy_condition="m20>0",
                    sell_condition="m20<0.1",
                    score_expression="m20",
                    top_n=1,
                    entry_offset=1,
                    exit_offset=2,
                    min_hold_days=0,
                    max_hold_days=2,
                    settlement_mode="complete",
                    realistic_execution=True,
                    slippage_bps=0.0,
                    per_trade_budget=10000.0,
                    lot_size=100,
                )
            )

            buy_row = next(row for row in body["trade_rows"] if row["action"] == "BUY")
            sell_row = next(row for row in body["trade_rows"] if row["action"] == "SELL")
            self.assertEqual(buy_row["shares"], 900)
            self.assertEqual(sell_row["shares"], 900.0)
            self.assertNotEqual(sell_row["shares"], 1)
            self.assertAlmostEqual(buy_row["net_amount"], 9180.28, places=2)
            self.assertAlmostEqual(sell_row["pnl"], 449.44, places=2)
            self.assertEqual(round(sell_row["pnl"], 2), sell_row["pnl"])

    def test_backtest_js_formats_money_fields_to_two_decimals(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = """
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync("static/app.js", "utf8");
const noop = () => {};
const ids = [
  "btForm", "runBtn", "exportBtn", "downloadPickRowsBtn", "downloadTradeRowsBtn", "exitMode", "exitOffset",
  "exitOffsetField", "status", "summaryGrid", "equityChart", "pickTable", "tradeTable", "contributionTable",
  "conditionTable", "topKTable", "rankTable", "yearTable", "monthTable", "exitReasonTable", "openPositionTable",
  "pendingSellTable", "diagText", "strategyPreset", "backtestPoolUser", "stockPoolTemplateSelect", "reloadBacktestPoolsBtn",
  "startDate", "endDate", "buyCondition", "sellCondition", "scoreExpression", "topN", "initialCash", "perTradeBudget",
  "entryOffset", "minHoldDays", "maxHoldDays", "lotSize", "buyFeeRate", "sellFeeRate", "stampTaxSell",
  "realisticExecution", "settlementMode", "slippageBps", "minCommission"
];
const elements = new Map();
function makeElement(id) {
  const children = [];
  return {
    id,
    textContent: "",
    innerHTML: "",
    value: id === "stockPoolTemplateSelect" ? "测试池" : "",
    checked: false,
    disabled: false,
    hidden: false,
    style: {},
    dataset: {},
    options: children,
    classList: { toggle: noop, contains: () => false },
    closest: () => null,
    querySelector: () => null,
    appendChild: (child) => { children.push(child); return child; },
    remove: noop,
    focus: noop,
    scrollIntoView: noop,
    addEventListener: noop,
  };
}
function element(id) {
  if (!elements.has(id)) elements.set(id, makeElement(id));
  return elements.get(id);
}
for (const id of ids) element(id);
const context = {
  document: {
    getElementById: element,
    querySelectorAll: () => [],
    createElement: () => makeElement("created"),
    body: { appendChild: noop, classList: { toggle: noop } },
  },
  window: { setTimeout: noop },
  Option: function Option(label, value) { return { label, value }; },
  fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({ templates: [{ template_name: "测试池", stock_count: 1 }] }) }),
  URL: { createObjectURL: () => "blob:test", revokeObjectURL: noop },
  Number, String, Math, Set, Array, console,
};
vm.createContext(context);
vm.runInContext(code, context);
const checks = [
  [context.formatCellValue("pnl", 119.384321), "119.38"],
  [context.formatCellValue("ending_equity", 101234.5678), "101,234.57"],
  [context.formatCellValue("price", 20.2345), "20.23"],
  [context.formatCellValue("trade_return", 0.012345), "1.23%"],
  [context.formatCellValue("score", 8.123456), "8.123456"],
];
for (const [actual, expected] of checks) {
  if (actual !== expected) throw new Error(`${actual} !== ${expected}`);
}
"""
        result = subprocess.run(["node", "-e", script], cwd=repo_root, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
