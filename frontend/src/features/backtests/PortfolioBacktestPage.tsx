import { useEffect, useMemo, useState } from "react";
import { Download, ExternalLink, Play, RefreshCw } from "lucide-react";
import { compactDate, formatHeader, formatValue } from "./format";
import "./portfolioBacktest.css";

type BacktestMode = "signal_quality" | "account";
type ExitMode = "fixed" | "sell_condition_with_fallback" | "sell_condition_only";
type ResultRow = Record<string, unknown>;

type BacktestResult = {
  summary?: Record<string, unknown>;
  daily_rows?: ResultRow[];
  pick_rows?: ResultRow[];
  trade_rows?: ResultRow[];
  contribution_rows?: ResultRow[];
  condition_rows?: ResultRow[];
  topk_rows?: ResultRow[];
  rank_rows?: ResultRow[];
  year_rows?: ResultRow[];
  month_rows?: ResultRow[];
  exit_reason_rows?: ResultRow[];
  open_position_rows?: ResultRow[];
  pending_sell_rows?: ResultRow[];
  diagnostics?: Record<string, unknown>;
};

type CurrentUser = { username?: string; role?: string; display_name?: string };
type StockPoolTemplate = { template_name?: string; stock_count?: number };

type FormState = {
  mode: BacktestMode;
  stock_pool_template_name: string;
  start_date: string;
  end_date: string;
  buy_condition: string;
  sell_condition: string;
  score_expression: string;
  top_n: string;
  initial_cash: string;
  per_trade_budget: string;
  entry_offset: string;
  exit_offset: string;
  min_hold_days: string;
  max_hold_days: string;
  exit_mode: ExitMode;
  lot_size: string;
  buy_fee_rate: string;
  sell_fee_rate: string;
  stamp_tax_sell: string;
  slippage_bps: string;
  min_commission: string;
  realistic_execution: "true" | "false";
  settlement_mode: "cutoff" | "complete";
};

const t = {
  title: "\u7ec4\u5408\u56de\u6d4b",
  eyebrow: "Portfolio Backtest",
  oldPage: "\u6253\u5f00\u65e7\u9875",
  reload: "\u5237\u65b0\u6a21\u677f",
  run: "\u8fd0\u884c\u56de\u6d4b",
  running: "\u8fd0\u884c\u4e2d...",
  signal: "\u4fe1\u53f7\u8d28\u91cf",
  account: "\u8d26\u6237\u56de\u6d4b",
  conditions: "\u4fe1\u53f7\u6761\u4ef6",
  execution: "\u6267\u884c\u53c2\u6570",
  buy: "\u4e70\u5165\u6761\u4ef6",
  sell: "\u5356\u51fa\u6761\u4ef6",
  score: "\u8bc4\u5206\u516c\u5f0f",
  pool: "\u80a1\u7968\u6c60\u6a21\u677f",
  dateRange: "\u65e5\u671f\u8303\u56f4",
  entryOffset: "\u4e70\u5165\u504f\u79fb",
  exitOffset: "\u5356\u51fa\u504f\u79fb",
  minHold: "\u6700\u77ed\u6301\u6709",
  maxHold: "\u6700\u957f\u6301\u6709",
  exitMode: "\u9000\u51fa\u6a21\u5f0f",
  initialCash: "\u521d\u59cb\u8d44\u91d1",
  budget: "\u5355\u7968\u9884\u7b97",
  lotSize: "\u6bcf\u624b\u80a1\u6570",
  buyFee: "\u4e70\u5165\u8d39\u7387",
  sellFee: "\u5356\u51fa\u8d39\u7387",
  stampTax: "\u5370\u82b1\u7a0e",
  slippage: "\u6ed1\u70b9bps",
  minCommission: "\u6700\u4f4e\u4f63\u91d1",
  realisticExecution: "\u4e25\u683c\u6210\u4ea4",
  settlementMode: "\u7ed3\u7b97\u53e3\u5f84",
  ready: "\u65b0\u7ec4\u5408\u56de\u6d4b\u9875\u5df2\u5c31\u7eea\uff0c\u7ed3\u679c\u53e3\u5f84\u6cbf\u7528\u65e7 API\u3002",
  noPool: "\u8bf7\u5148\u9009\u62e9\u80a1\u7968\u6c60\u6a21\u677f\u3002",
  loadingPools: "\u6b63\u5728\u8bfb\u53d6\u80a1\u7968\u6c60\u6a21\u677f...",
  loadedPools: "\u80a1\u7968\u6c60\u6a21\u677f\u5df2\u8bfb\u53d6\u3002",
  noRows: "\u6682\u65e0\u7ed3\u679c",
  equity: "\u6743\u76ca\u66f2\u7ebf",
  trades: "\u4ea4\u6613\u6d41\u6c34",
  picks: "\u9009\u80a1\u660e\u7ec6",
  yearly: "\u5e74\u5ea6\u8868\u73b0",
  diagnostics: "\u6761\u4ef6\u8bca\u65ad",
  rankQuality: "\u6392\u540d\u8d28\u91cf",
  monthly: "\u6708\u5ea6\u8868\u73b0",
  exitReasons: "\u9000\u51fa\u539f\u56e0",
  contribution: "\u4e2a\u80a1\u8d21\u732e",
  cutoff: "\u671f\u672b\u6301\u4ed3",
  resultSummary: "\u7ed3\u679c\u6458\u8981",
  portfolioResult: "\u7ec4\u5408\u7ed3\u679c",
  topkScan: "\u7d2f\u8ba1TopK\u626b\u63cf",
  rankDetail: "\u5355\u540d\u6b21\u8d28\u91cf",
  openPositions: "\u671f\u672b\u6301\u4ed3",
  pendingSells: "\u622a\u6b62\u65e5\u5356\u51fa\u63d0\u9192",
  exportPicks: "\u9009\u80a1Excel",
  exportTrades: "\u4ea4\u6613Excel",
  exporting: "\u5bfc\u51fa\u4e2d...",
  fallbackUser: "admin",
  drawdown: "\u5f53\u524d\u56de\u64a4",
  note: "\u5df2\u63a5\u5165\u5f53\u524d\u7528\u6237\u3001Excel \u5bfc\u51fa\u548c\u4e3b\u8981\u7ed3\u679c\u8868\uff0c\u53ef\u4e0e\u65e7\u9875\u5bf9\u7167\u9a8c\u8bc1\u3002"
};

const defaultForm: FormState = {
  mode: "signal_quality",
  stock_pool_template_name: "",
  start_date: "20230101",
  end_date: "20251231",
  buy_condition: "m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02",
  sell_condition: "m20<0.08,hs300_m20<0.02",
  score_expression: "m20 * 140 + (m20 - m60 / 3) * 90 + (m20 - m120 / 6) * 40 - abs(m5 - 0.03) * 55 - abs(m10 - 0.08) * 30",
  top_n: "2",
  initial_cash: "100000",
  per_trade_budget: "10000",
  entry_offset: "1",
  exit_offset: "5",
  min_hold_days: "3",
  max_hold_days: "15",
  exit_mode: "sell_condition_with_fallback",
  lot_size: "100",
  buy_fee_rate: "0.00003",
  sell_fee_rate: "0.00003",
  stamp_tax_sell: "0",
  slippage_bps: "3",
  min_commission: "0",
  realistic_execution: "true",
  settlement_mode: "cutoff"
};

const signalSummaryMetrics = [
  ["data_profile", "\u6570\u636e\u53e3\u5f84"],
  ["signal_count", "\u5165\u9009\u4fe1\u53f7\u6570"],
  ["completed_signal_count", "\u5b8c\u6210\u4fe1\u53f7\u6570"],
  ["avg_trade_return", "\u5e73\u5747\u5355\u7b14\u6536\u76ca"],
  ["median_trade_return", "\u4e2d\u4f4d\u5355\u7b14\u6536\u76ca"],
  ["win_rate", "\u80dc\u7387"],
  ["profit_factor", "\u6536\u76ca\u56e0\u5b50"],
  ["recommended_top_k", "\u5efa\u8baeTopK"],
  ["signal_curve_return", "\u4fe1\u53f7\u51c0\u503c\u6536\u76ca"],
  ["max_drawdown", "\u4fe1\u53f7\u51c0\u503c\u56de\u64a4"],
  ["candidate_day_ratio", "\u6709\u5019\u9009\u65e5\u5360\u6bd4"],
  ["topn_fill_rate", "TopN\u586b\u6ee1\u7387"],
  ["avg_holding_days", "\u5e73\u5747\u6301\u6709\u5929\u6570"],
  ["blocked_entry_count", "\u4e70\u5165\u963b\u585e\u4fe1\u53f7"],
  ["blocked_reentry_count", "\u6301\u4ed3\u671f\u8df3\u8fc7\u4fe1\u53f7"],
  ["open_signal_count", "\u672a\u5b8c\u6210\u4fe1\u53f7"],
  ["best_trade_return", "\u6700\u597d\u5355\u7b14"],
  ["worst_trade_return", "\u6700\u5dee\u5355\u7b14"],
  ["avg_signals_per_day", "\u5e73\u5747\u6bcf\u65e5\u4fe1\u53f7"]
] as const;

const accountSummaryMetrics = [
  ["data_profile", "\u6570\u636e\u53e3\u5f84"],
  ["ending_equity", "\u671f\u672b\u6743\u76ca"],
  ["ending_cash", "\u671f\u672b\u73b0\u91d1"],
  ["ending_market_value", "\u671f\u672b\u6301\u4ed3\u5e02\u503c"],
  ["total_return", "\u603b\u6536\u76ca\u7387"],
  ["annualized_return", "\u5e74\u5316\u6536\u76ca\u7387"],
  ["max_drawdown", "\u6700\u5927\u56de\u64a4"],
  ["buy_count", "\u4e70\u5165\u6b21\u6570"],
  ["sell_count", "\u5356\u51fa\u6b21\u6570"],
  ["win_rate", "\u80dc\u7387"],
  ["avg_trade_return", "\u5e73\u5747\u5355\u7b14\u6536\u76ca"],
  ["median_trade_return", "\u4e2d\u4f4d\u5355\u7b14\u6536\u76ca"],
  ["profit_factor", "\u6536\u76ca\u56e0\u5b50"],
  ["avg_holding_days", "\u5e73\u5747\u6301\u6709\u5929\u6570"],
  ["total_fees", "\u624b\u7eed\u8d39\u6ed1\u70b9\u6210\u672c"],
  ["open_position_count", "\u671f\u672b\u6301\u4ed3\u6570"],
  ["pending_sell_signal_count", "\u622a\u6b62\u65e5\u5356\u51fa\u63d0\u9192"]
] as const;

const tradeColumns = ["trade_date", "signal_date", "symbol", "name", "action", "rank", "score", "price", "shares", "gross_amount", "fees", "pnl", "trade_return", "holding_days"];
const pickColumns = ["trade_date", "signal_date", "symbol", "name", "rank", "score", "candidate_count", "picked_count"];
const yearColumns = ["period", "period_return", "max_drawdown", "win_rate", "avg_trade_return", "buy_count", "sell_count", "ending_equity"];
const conditionColumns = ["category", "metric", "value", "reading"];
const topkColumns = ["recommended", "top_k", "signal_count", "completed_signal_count", "picked_days", "topk_fill_rate", "win_rate", "avg_trade_return", "median_trade_return", "profit_factor", "signal_curve_return", "max_drawdown", "profitable_years", "year_count", "recommendation_score", "quality_note"];
const rankColumns = ["rank", "signal_count", "win_rate", "avg_trade_return", "median_trade_return", "p10_trade_return", "p90_trade_return", "avg_holding_days"];
const monthColumns = ["period", "period_return", "max_drawdown", "win_rate", "avg_trade_return", "buy_count", "sell_count", "ending_equity"];
const exitColumns = ["exit_type", "reason", "trade_count", "win_rate", "avg_trade_return", "median_trade_return", "avg_holding_days", "total_pnl"];
const contributionColumns = ["symbol", "name", "trade_count", "signal_count", "realized_pnl", "total_signal_return", "pnl", "total_return", "avg_trade_return", "median_trade_return", "win_rate", "holding_days"];
const openPositionColumns = ["valuation_date", "symbol", "name", "shares", "buy_date", "buy_price", "current_raw_close", "market_value", "unrealized_pnl", "unrealized_return", "holding_days", "planned_exit_date"];
const pendingSellColumns = ["signal_date", "planned_sell_date", "symbol", "name", "shares", "buy_date", "buy_price", "current_raw_close", "holding_return", "best_return_since_entry", "drawdown_from_peak", "sell_condition", "reason"];

function toNumber(value: string): number {
  return Number(value || 0);
}

async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { credentials: "include", ...options });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function buildPayload(form: FormState, username: string) {
  if (!form.stock_pool_template_name) throw new Error(t.noPool);
  const payload: Record<string, unknown> = {
    data_source: "stock_pool",
    processed_dir: "",
    stock_pool_username: username || t.fallbackUser,
    stock_pool_template_name: form.stock_pool_template_name,
    data_profile: "base",
    start_date: form.start_date.trim(),
    end_date: form.end_date.trim(),
    buy_condition: form.buy_condition.trim(),
    sell_condition: form.sell_condition.trim(),
    score_expression: form.score_expression.trim(),
    top_n: toNumber(form.top_n),
    exit_mode: form.exit_mode,
    entry_offset: toNumber(form.entry_offset),
    exit_offset: form.exit_mode === "sell_condition_only" ? null : toNumber(form.exit_offset),
    min_hold_days: toNumber(form.min_hold_days),
    max_hold_days: toNumber(form.max_hold_days),
    buy_fee_rate: toNumber(form.buy_fee_rate),
    sell_fee_rate: toNumber(form.sell_fee_rate),
    stamp_tax_sell: toNumber(form.stamp_tax_sell),
    realistic_execution: form.realistic_execution === "true",
    settlement_mode: form.settlement_mode,
    slippage_bps: toNumber(form.slippage_bps),
    per_trade_budget: toNumber(form.per_trade_budget),
    lot_size: toNumber(form.lot_size),
    min_commission: toNumber(form.min_commission)
  };
  if (form.mode === "account") payload.initial_cash = toNumber(form.initial_cash);
  return payload;
}

export function PortfolioBacktestPage() {
  const [form, setForm] = useState<FormState>(defaultForm);
  const [templates, setTemplates] = useState<StockPoolTemplate[]>([]);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [activeTab, setActiveTab] = useState("equity");
  const [status, setStatus] = useState(t.ready);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState<"" | "pick_rows" | "trade_rows">("");
  const username = currentUser?.username || t.fallbackUser;

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function loadTemplates(showStatus = false, targetUsername = username) {
    if (showStatus) {
      setStatus(t.loadingPools);
      setError(false);
    }
    const data = await fetchJson<{ templates: StockPoolTemplate[] }>(`/api/stock-pools/templates?username=${encodeURIComponent(targetUsername || t.fallbackUser)}`);
    setTemplates(data.templates || []);
    setForm((current) => current.stock_pool_template_name ? current : { ...current, stock_pool_template_name: data.templates?.[0]?.template_name || "" });
    if (showStatus) setStatus(t.loadedPools);
  }

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      const auth = await fetchJson<{ authenticated: boolean; user?: CurrentUser | null }>("/api/auth/me");
      if (cancelled) return;
      const nextUser = auth.authenticated ? auth.user || null : null;
      const nextUsername = nextUser?.username || t.fallbackUser;
      setCurrentUser(nextUser);
      await loadTemplates(false, nextUsername);
    }
    boot().catch((err) => {
      if (cancelled) return;
      setError(true);
      setStatus(`\u8bfb\u53d6\u6a21\u677f\u5931\u8d25\uff1a${err.message}`);
    });
    return () => { cancelled = true; };
  }, []);

  async function runBacktest() {
    let payload: Record<string, unknown>;
    try {
      payload = buildPayload(form, username);
    } catch (err) {
      setError(true);
      setStatus(err instanceof Error ? err.message : String(err));
      return;
    }
    setLoading(true);
    setError(false);
    setStatus(form.mode === "signal_quality" ? "\u6b63\u5728\u8fd0\u884c\u4fe1\u53f7\u8d28\u91cf\u56de\u6d4b..." : "\u6b63\u5728\u8fd0\u884c\u8d26\u6237\u56de\u6d4b...");
    try {
      const endpoint = form.mode === "signal_quality" ? "/api/run-signal-quality" : "/api/run-backtest";
      const data = await fetchJson<BacktestResult>(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      setResult(data);
      setActiveTab("equity");
      setStatus(form.mode === "signal_quality" ? "\u4fe1\u53f7\u8d28\u91cf\u56de\u6d4b\u5b8c\u6210\u3002" : "\u8d26\u6237\u56de\u6d4b\u5b8c\u6210\u3002");
    } catch (err) {
      setError(true);
      setStatus(`\u56de\u6d4b\u5931\u8d25\uff1a${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function downloadResultTable(table: "pick_rows" | "trade_rows") {
    let payload: Record<string, unknown>;
    try {
      payload = buildPayload(form, username);
    } catch (err) {
      setError(true);
      setStatus(err instanceof Error ? err.message : String(err));
      return;
    }
    setExporting(table);
    setError(false);
    setStatus(table === "pick_rows" ? "\u6b63\u5728\u5bfc\u51fa\u9009\u80a1\u660e\u7ec6..." : "\u6b63\u5728\u5bfc\u51fa\u4ea4\u6613\u6d41\u6c34...");
    try {
      const response = await fetch(`/api/run-backtest-table-export?mode=${encodeURIComponent(form.mode)}&table=${encodeURIComponent(table)}`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = table === "pick_rows" ? "daily_picks.xlsx" : "trade_flows.xlsx";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setStatus(table === "pick_rows" ? "\u9009\u80a1\u660e\u7ec6 Excel \u5df2\u751f\u6210\u3002" : "\u4ea4\u6613\u6d41\u6c34 Excel \u5df2\u751f\u6210\u3002");
    } catch (err) {
      setError(true);
      setStatus(`Excel \u5bfc\u51fa\u5931\u8d25\uff1a${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setExporting("");
    }
  }

  const summary = result?.summary || {};
  const isAccountMode = form.mode === "account";
  const resultTabs = useMemo(() => {
    const tabs = [["equity", t.equity], ["picks", t.picks], ["trades", t.trades], ["rank", t.rankQuality], ["year", t.yearly], ["month", t.monthly], ["exit", t.exitReasons]];
    if (isAccountMode) tabs.push(["cutoff", t.cutoff]);
    tabs.push(["contribution", t.contribution], ["condition", t.diagnostics]);
    return tabs;
  }, [isAccountMode]);
  const summaryMetrics = (summary.result_mode === "signal_quality" ? signalSummaryMetrics : accountSummaryMetrics).filter(([key]) => summary[key] !== undefined);
  const dailyRows = result?.daily_rows || [];
  const linePoints = useMemo(() => buildLinePoints(dailyRows), [dailyRows]);
  const drawdownPoints = useMemo(() => buildDrawdownPoints(dailyRows), [dailyRows]);

  useEffect(() => {
    if (!isAccountMode && activeTab === "cutoff") setActiveTab("equity");
  }, [isAccountMode, activeTab]);

  return (
    <section className="portfolio-page">
      <div className="portfolio-header">
        <div>
          <p className="page-eyebrow">{t.eyebrow}</p>
          <h1>{t.title}</h1>
          <p className="portfolio-note">{t.note}</p>
        </div>
        <div className="portfolio-header-actions">
          <a className="secondary-link" href="/__legacy/index" target="_blank" rel="noreferrer"><ExternalLink size={14} />{t.oldPage}</a>
          <button className="secondary-link" type="button" onClick={() => void loadTemplates(true, username)}><RefreshCw size={14} />{t.reload}</button>
        </div>
      </div>

      <div className="portfolio-runbar">
        <div className="segmented-control" role="radiogroup">
          <button className={form.mode === "signal_quality" ? "active" : ""} type="button" onClick={() => update("mode", "signal_quality")}>{t.signal}</button>
          <button className={form.mode === "account" ? "active" : ""} type="button" onClick={() => update("mode", "account")}>{t.account}</button>
        </div>
        <label><span>{t.pool}</span><select value={form.stock_pool_template_name} onChange={(event) => update("stock_pool_template_name", event.target.value)}>{templates.length ? templates.map((item) => <option key={item.template_name || ""} value={item.template_name || ""}>{item.template_name || "-"} ({item.stock_count || 0})</option>) : <option value="">-</option>}</select></label>
        <label><span>{t.dateRange}</span><div className="date-pair"><input value={form.start_date} onChange={(event) => update("start_date", event.target.value)} /><input value={form.end_date} onChange={(event) => update("end_date", event.target.value)} /></div></label>
        <button className="primary-button" type="button" onClick={() => void runBacktest()} disabled={loading}><Play size={14} />{loading ? t.running : t.run}</button>
        <button className="secondary-link" type="button" onClick={() => void downloadResultTable("pick_rows")} disabled={loading || Boolean(exporting)}><Download size={14} />{exporting === "pick_rows" ? t.exporting : t.exportPicks}</button>
        <button className="secondary-link" type="button" onClick={() => void downloadResultTable("trade_rows")} disabled={loading || Boolean(exporting)}><Download size={14} />{exporting === "trade_rows" ? t.exporting : t.exportTrades}</button>
      </div>

      <div className="portfolio-grid">
        <section className="portfolio-panel">
          <div className="panel-header"><h2>{t.conditions}</h2></div>
          <div className="portfolio-form-grid one-col">
            <TextArea label={t.buy} value={form.buy_condition} onChange={(value) => update("buy_condition", value)} />
            <TextArea label={t.sell} value={form.sell_condition} onChange={(value) => update("sell_condition", value)} />
            <TextArea label={t.score} value={form.score_expression} onChange={(value) => update("score_expression", value)} />
          </div>
        </section>
        <section className="portfolio-panel">
          <div className="panel-header"><h2>{t.execution}</h2></div>
          <div className="portfolio-form-grid">
            <Field label="Top N" value={form.top_n} onChange={(value) => update("top_n", value)} />
            <Field label={t.entryOffset} value={form.entry_offset} onChange={(value) => update("entry_offset", value)} />
            <Field label={t.exitOffset} value={form.exit_offset} onChange={(value) => update("exit_offset", value)} disabled={form.exit_mode === "sell_condition_only"} />
            <Field label={t.minHold} value={form.min_hold_days} onChange={(value) => update("min_hold_days", value)} />
            <Field label={t.maxHold} value={form.max_hold_days} onChange={(value) => update("max_hold_days", value)} />
            <label>
              <span>{t.exitMode}</span>
              <select value={form.exit_mode} onChange={(event) => update("exit_mode", event.target.value as ExitMode)}>
                <option value="sell_condition_with_fallback">sell+fallback</option>
                <option value="fixed">fixed</option>
                <option value="sell_condition_only">sell only</option>
              </select>
            </label>
            <Field label={t.initialCash} value={form.initial_cash} onChange={(value) => update("initial_cash", value)} disabled={form.mode === "signal_quality"} />
            <Field label={t.budget} value={form.per_trade_budget} onChange={(value) => update("per_trade_budget", value)} />
            <Field label={t.lotSize} value={form.lot_size} onChange={(value) => update("lot_size", value)} />
            <Field label={t.buyFee} value={form.buy_fee_rate} onChange={(value) => update("buy_fee_rate", value)} step="0.00001" />
            <Field label={t.sellFee} value={form.sell_fee_rate} onChange={(value) => update("sell_fee_rate", value)} step="0.00001" />
            <Field label={t.stampTax} value={form.stamp_tax_sell} onChange={(value) => update("stamp_tax_sell", value)} step="0.00001" />
            <Field label={t.slippage} value={form.slippage_bps} onChange={(value) => update("slippage_bps", value)} step="0.1" />
            <Field label={t.minCommission} value={form.min_commission} onChange={(value) => update("min_commission", value)} />
            <label>
              <span>{t.realisticExecution}</span>
              <select value={form.realistic_execution} onChange={(event) => update("realistic_execution", event.target.value as FormState["realistic_execution"])}>
                <option value="true">true</option>
                <option value="false">false</option>
              </select>
            </label>
            <label>
              <span>{t.settlementMode}</span>
              <select value={form.settlement_mode} onChange={(event) => update("settlement_mode", event.target.value as FormState["settlement_mode"])}>
                <option value="cutoff">cutoff</option>
                <option value="complete">complete</option>
              </select>
            </label>
          </div>
        </section>
      </div>

      <p className={error ? "portfolio-status error" : "portfolio-status"}>{status}</p>

      <section className="portfolio-summary">
        <div className="summary-intro">
          <p className="page-eyebrow">{t.resultSummary}</p>
          <h2>{t.portfolioResult}</h2>
        </div>
        <div className="metric-strip portfolio-metrics">
          {summaryMetrics.length ? summaryMetrics.map(([key, label]) => <div className="metric-tile" key={key}><span>{label}</span><strong>{formatValue(key, summary[key])}</strong></div>) : <div className="metric-tile"><span>Status</span><strong>-</strong></div>}
        </div>
      </section>

      <section className="portfolio-results">
        <div className="result-tabs">{resultTabs.map(([key, label]) => <button key={key} className={activeTab === key ? "active" : ""} type="button" onClick={() => setActiveTab(key)}>{label}</button>)}</div>
        {activeTab === "equity" && <EquityPanel rows={dailyRows} points={linePoints} drawdownPoints={drawdownPoints} />}
        {activeTab === "trades" && <DataTable rows={(result?.trade_rows || []).slice(0, 80)} columns={tradeColumns} />}
        {activeTab === "picks" && <DataTable rows={(result?.pick_rows || []).slice(0, 80)} columns={pickColumns} />}
        {activeTab === "rank" && <RankQualityPanel topkRows={(result?.topk_rows || []).slice(0, 80)} rankRows={(result?.rank_rows || []).slice(0, 80)} />}
        {activeTab === "year" && <DataTable rows={(result?.year_rows || []).slice(0, 80)} columns={yearColumns} />}
        {activeTab === "month" && <DataTable rows={(result?.month_rows || []).slice(0, 80)} columns={monthColumns} />}
        {activeTab === "exit" && <DataTable rows={(result?.exit_reason_rows || []).slice(0, 80)} columns={exitColumns} />}
        {isAccountMode && activeTab === "cutoff" && <CutoffPanel openRows={(result?.open_position_rows || []).slice(0, 80)} pendingRows={(result?.pending_sell_rows || []).slice(0, 80)} />}
        {activeTab === "contribution" && <DataTable rows={(result?.contribution_rows || []).slice(0, 80)} columns={contributionColumns} />}
        {activeTab === "condition" && <DataTable rows={(result?.condition_rows || []).slice(0, 80)} columns={conditionColumns} />}
      </section>
    </section>
  );
}

function Field({ label, value, onChange, step, disabled = false }: { label: string; value: string; onChange: (value: string) => void; step?: string; disabled?: boolean }) {
  return <label><span>{label}</span><input type="number" step={step} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} /></label>;
}

function TextArea({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label><span>{label}</span><textarea rows={3} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function buildLinePoints(rows: ResultRow[]) {
  const values = rows.map((row) => Number(row.equity ?? row.signal_equity ?? row.signal_curve ?? 0)).filter((value) => Number.isFinite(value) && value > 0);
  if (values.length < 2) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1);
  return values.map((value, index) => `${((index / Math.max(values.length - 1, 1)) * 100).toFixed(2)},${(64 - ((value - min) / span) * 58).toFixed(2)}`).join(" ");
}

function buildDrawdownPoints(rows: ResultRow[]) {
  const values = rows.map((row) => Math.abs(Number(row.drawdown ?? 0))).filter((value) => Number.isFinite(value));
  if (values.length < 2 || Math.max(...values) <= 0) return "";
  const max = Math.max(...values, 0.001);
  return values.map((value, index) => `${((index / Math.max(values.length - 1, 1)) * 100).toFixed(2)},${(76 + (value / max) * 18).toFixed(2)}`).join(" ");
}

function EquityPanel({ rows, points, drawdownPoints }: { rows: ResultRow[]; points: string; drawdownPoints: string }) {
  const latest = rows[rows.length - 1];
  const latestDrawdown = Number(latest?.drawdown ?? 0);
  return <div className="equity-panel">{points ? <svg viewBox="0 0 100 100" preserveAspectRatio="none"><line className="chart-divider" x1="0" y1="70" x2="100" y2="70" /><polyline className="equity-line" points={points} />{drawdownPoints ? <polyline className="drawdown-line" points={drawdownPoints} /> : null}</svg> : <div className="empty-state">{t.noRows}</div>}<div className="equity-footer"><span>{rows.length ? compactDate(String(latest?.trade_date || "")) : "-"}</span><strong>{rows.length ? formatValue("equity", latest?.equity ?? latest?.signal_equity ?? latest?.signal_curve) : "-"}</strong><span>{rows.length ? `${t.drawdown}: ${formatValue("drawdown", Math.abs(latestDrawdown))}` : "-"}</span></div></div>;
}

function RankQualityPanel({ topkRows, rankRows }: { topkRows: ResultRow[]; rankRows: ResultRow[] }) {
  return (
    <div className="stacked-results">
      <section className="result-subpanel">
        <h3>{t.topkScan}</h3>
        <DataTable rows={topkRows} columns={topkColumns} />
      </section>
      <section className="result-subpanel">
        <h3>{t.rankDetail}</h3>
        <DataTable rows={rankRows} columns={rankColumns} />
      </section>
    </div>
  );
}

function CutoffPanel({ openRows, pendingRows }: { openRows: ResultRow[]; pendingRows: ResultRow[] }) {
  return (
    <div className="stacked-results">
      <section className="result-subpanel">
        <h3>{t.openPositions}</h3>
        <DataTable rows={openRows} columns={openPositionColumns} />
      </section>
      <section className="result-subpanel">
        <h3>{t.pendingSells}</h3>
        <DataTable rows={pendingRows} columns={pendingSellColumns} />
      </section>
    </div>
  );
}

function DataTable({ rows, columns }: { rows: ResultRow[]; columns: string[] }) {
  if (!rows.length) return <div className="empty-state">{t.noRows}</div>;
  const rowKeys = Array.from(rows.reduce((keys, row) => {
    Object.keys(row).forEach((key) => keys.add(key));
    return keys;
  }, new Set<string>()));
  const visibleColumns = [...columns.filter((key) => rowKeys.includes(key)), ...rowKeys.filter((key) => !columns.includes(key))];
  return <div className="table-wrap portfolio-table-wrap"><table><thead><tr>{visibleColumns.map((key) => <th key={key}>{formatHeader(key)}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{visibleColumns.map((key) => <td key={key}>{formatValue(key, row[key])}</td>)}</tr>)}</tbody></table></div>;
}
