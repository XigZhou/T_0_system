from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from overnight_bt.app import run_signal_quality_api
from overnight_bt.models import SignalQualityRequest
from tests.helpers import make_processed_stock, write_stock_pool_db


class BacktestTradeDisplayTest(unittest.TestCase):
    def test_signal_quality_trade_rows_use_fixed_100_shares(self) -> None:
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
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "unit-test-pool", [stock_a])
            body = run_signal_quality_api(
                SignalQualityRequest(
                    data_source="stock_pool",
                    processed_dir="",
                    stock_pool_template_name="unit-test-pool",
                    stock_pool_db_path=str(db_path),
                    stock_pool_market_db_path=str(db_path),
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
            self.assertEqual(buy_row["shares"], 100.0)
            self.assertEqual(sell_row["shares"], 100.0)
            self.assertAlmostEqual(buy_row["net_amount"], 1020.03, places=2)
            self.assertAlmostEqual(sell_row["pnl"], 49.94, places=2)
            self.assertEqual(round(sell_row["pnl"], 2), sell_row["pnl"])

    def test_signal_quality_ignores_account_budget_inputs(self) -> None:
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
            db_path = write_stock_pool_db(base / "stock_pool.sqlite", "unit-test-pool", [stock_a])
            base_req = dict(
                data_source="stock_pool",
                processed_dir="",
                stock_pool_template_name="unit-test-pool",
                stock_pool_db_path=str(db_path),
                stock_pool_market_db_path=str(db_path),
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
                lot_size=100,
            )
            small = run_signal_quality_api(SignalQualityRequest(**base_req, per_trade_budget=10000.0))
            large = run_signal_quality_api(SignalQualityRequest(**base_req, per_trade_budget=20000.0))
            self.assertEqual(small["summary"]["avg_trade_return"], large["summary"]["avg_trade_return"])
            for small_row, large_row in zip(small["trade_rows"], large["trade_rows"]):
                self.assertEqual(small_row["shares"], large_row["shares"])
                self.assertEqual(small_row["net_amount"], large_row["net_amount"])
                self.assertEqual(small_row.get("trade_return"), large_row.get("trade_return"))
                self.assertEqual(small_row.get("pnl"), large_row.get("pnl"))

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
  [context.formatHeader("best_trade_return"), "最好单笔收益"],
  [context.formatHeader("worst_trade_return"), "最差单笔收益"],
  [context.formatHeader("p10_trade_return"), "单笔收益P10"],
  [context.formatHeader("p90_trade_return"), "单笔收益P90"],
  [context.formatHeader("best_return_since_entry"), "持仓以来最高收益"],
  [context.formatHeader("drawdown_from_peak"), "较高点回撤"],
];
for (const [actual, expected] of checks) {
  if (actual !== expected) throw new Error(`${actual} !== ${expected}`);
}
"""
        result = subprocess.run(["node", "-e", script], cwd=repo_root, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)


    def test_backtest_js_shows_account_rank_notice_in_account_mode(self) -> None:
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
  "realisticExecution", "settlementMode", "slippageBps", "minCommission", "equityTabButton", "yearTabButton",
  "monthTabButton", "contributionTabButton", "tradePanelEyebrow", "tradePanelTitle", "tradePanelNote",
  "rankPanelNote", "accountRankNotice", "signalRankContent"
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
const accountResult = {
  summary: { result_mode: "account" },
  daily_rows: [], pick_rows: [], trade_rows: [], contribution_rows: [], condition_rows: [], year_rows: [], month_rows: [],
  exit_reason_rows: [], open_position_rows: [], pending_sell_rows: [], diagnostics: { data_source: "stock_pool", data_profile: "base", stock_pool_template_name: "测试池", signal_days: 0, candidate_days: 0, picked_days: 0 }
};
context.applyResult(accountResult);
const notice = element("accountRankNotice");
if (notice.hidden !== false) throw new Error("account notice should be visible");
if (notice.textContent !== "实盘账户回测不展示排名质量；请使用信号质量回测评估评分表达式排序能力。") {
  throw new Error(`unexpected notice: ${notice.textContent}`);
}
if (element("signalRankContent").hidden !== true) throw new Error("signal rank tables should be hidden in account mode");
const signalResult = {
  summary: { result_mode: "signal_quality" },
  daily_rows: [], pick_rows: [], trade_rows: [], contribution_rows: [], condition_rows: [], topk_rows: [], rank_rows: [], year_rows: [], month_rows: [],
  exit_reason_rows: [], open_position_rows: [], pending_sell_rows: [], diagnostics: { data_source: "stock_pool", data_profile: "base", stock_pool_template_name: "测试池", signal_days: 0, completed_signal_count: 0, blocked_reentry_count: 0 }
};
context.applyResult(signalResult);
if (notice.hidden !== true) throw new Error("account notice should be hidden in signal mode");
if (element("signalRankContent").hidden !== false) throw new Error("signal rank tables should be visible in signal mode");
"""
        result = subprocess.run(["node", "-e", script], cwd=repo_root, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
