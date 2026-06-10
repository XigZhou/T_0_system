import { useEffect, useMemo, useState } from "react";
import { Eraser, ExternalLink, Play, RefreshCw } from "lucide-react";
import { formatHeader, formatValue } from "../backtests/format";
import "./dailyPlan.css";

type ResultRow = Record<string, unknown>;
type CurrentUser = { username?: string; role?: string; display_name?: string };
type StockPoolTemplate = { template_name?: string; stock_count?: number };

type DailyResult = {
  summary?: Record<string, unknown>;
  buy_rows?: ResultRow[];
  sell_rows?: ResultRow[];
  holding_rows?: ResultRow[];
  diagnostics?: Record<string, unknown>;
};

type FormState = {
  stock_pool_template_name: string;
  signal_date: string;
  top_n: string;
  buy_condition: string;
  sell_condition: string;
  score_expression: string;
  entry_offset: string;
  min_hold_days: string;
  max_hold_days: string;
  per_trade_budget: string;
  lot_size: string;
  holdings_text: string;
};

const t = {
  title: "\u6bcf\u65e5\u6536\u76d8\u9009\u80a1",
  eyebrow: "Daily Close Plan",
  note: "\u6536\u76d8\u540e\u751f\u6210\u660e\u65e5\u5019\u9009\u4e70\u5165\u548c\u5356\u51fa\u63d0\u9192\uff0c\u7ed3\u679c\u53e3\u5f84\u6cbf\u7528\u65e7 API\u3002",
  oldPage: "\u6253\u5f00\u65e7\u9875",
  reload: "\u5237\u65b0\u6a21\u677f",
  run: "\u751f\u6210\u660e\u65e5\u8ba1\u5212",
  running: "\u751f\u6210\u4e2d...",
  clear: "\u6e05\u7a7a\u6301\u4ed3",
  pool: "\u80a1\u7968\u6c60\u6a21\u677f",
  signalDate: "\u4fe1\u53f7\u65e5\u671f",
  signalDateHint: "\u7559\u7a7a\u4f7f\u7528\u6700\u65b0\u4ea4\u6613\u65e5",
  topN: "\u9009\u80a1\u6570\u91cf",
  conditions: "\u7b56\u7565\u6761\u4ef6",
  execution: "\u6267\u884c\u53c2\u6570",
  holdings: "\u5f53\u524d\u6301\u4ed3",
  holdingPlaceholder: "000001,20240103,10.25,900,\u5e73\u5b89\u94f6\u884c",
  buyCondition: "\u4e70\u5165\u6761\u4ef6",
  sellCondition: "\u5356\u51fa\u6761\u4ef6",
  scoreExpression: "\u8bc4\u5206\u8868\u8fbe\u5f0f",
  entryOffset: "\u4e70\u5165\u504f\u79fb",
  minHold: "\u6700\u77ed\u6301\u6709",
  maxHold: "\u6700\u957f\u6301\u6709",
  budget: "\u6bcf\u7b14\u76ee\u6807\u8d44\u91d1",
  lotSize: "\u6bcf\u624b\u80a1\u6570",
  summaryEyebrow: "\u8ba1\u5212\u6458\u8981",
  summaryTitle: "\u660e\u65e5\u4ea4\u6613\u51c6\u5907",
  buyTab: "\u660e\u65e5\u4e70\u5165",
  sellTab: "\u5356\u51fa\u63d0\u9192",
  holdingTab: "\u6301\u4ed3\u8bca\u65ad",
  noRows: "\u6682\u65e0\u7ed3\u679c",
  ready: "\u7b49\u5f85\u8f93\u5165\u3002",
  loadingPools: "\u6b63\u5728\u8bfb\u53d6\u80a1\u7968\u6c60\u6a21\u677f...",
  loadedPools: "\u80a1\u7968\u6c60\u6a21\u677f\u5df2\u8bfb\u53d6\u3002",
  noPool: "\u8bf7\u5148\u9009\u62e9\u80a1\u7968\u6c60\u6a21\u677f\u3002",
  fallbackUser: "admin"
};

const defaultForm: FormState = {
  stock_pool_template_name: "",
  signal_date: "",
  top_n: "2",
  buy_condition: "m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02",
  sell_condition: "m20<0.08,hs300_m20<0.02",
  score_expression: "m20 * 140 + (m20 - m60 / 3) * 90 + (m20 - m120 / 6) * 40 - abs(m5 - 0.03) * 55 - abs(m10 - 0.08) * 30",
  entry_offset: "1",
  min_hold_days: "3",
  max_hold_days: "15",
  per_trade_budget: "10000",
  lot_size: "100",
  holdings_text: ""
};

const summaryMetrics = [
  ["signal_date", "\u4fe1\u53f7\u65e5\u671f"],
  ["data_profile", "\u6570\u636e\u53e3\u5f84"],
  ["planned_buy_date", "\u8ba1\u5212\u4e70\u5165\u65e5"],
  ["buy_candidate_count", "\u4e70\u5165\u5019\u9009\u6570"],
  ["sell_signal_count", "\u5356\u51fa\u63d0\u9192\u6570"],
  ["holding_count", "\u8f93\u5165\u6301\u4ed3\u6570"],
  ["date_note", "\u65e5\u671f\u8bf4\u660e"]
] as const;

const buyColumns = ["signal_date", "planned_buy_date", "symbol", "name", "rank", "score", "signal_raw_close", "estimated_shares", "estimated_budget", "open_check"];
const sellColumns = ["signal_date", "planned_sell_date", "symbol", "name", "shares", "buy_date", "buy_price", "current_raw_close", "holding_return", "best_return_since_entry", "drawdown_from_peak", "sell_reason", "open_check"];
const holdingColumns = ["signal_date", "symbol", "name", "shares", "buy_date", "buy_price", "current_raw_close", "holding_days", "holding_return", "best_return_since_entry", "drawdown_from_peak", "sell_reason", "condition_note"];

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

function parseHoldings(text: string) {
  return String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const parts = line.split(",").map((part) => part.trim());
      if (parts.length < 4) throw new Error(`\u7b2c ${index + 1} \u884c\u6301\u4ed3\u683c\u5f0f\u4e0d\u6b63\u786e\uff0c\u5e94\u4e3a\uff1a\u80a1\u7968\u4ee3\u7801,\u4e70\u5165\u65e5\u671f,\u4e70\u5165\u4ef7,\u80a1\u6570,\u80a1\u7968\u540d\u79f0`);
      const [symbol, buy_date, buy_price, shares, name = ""] = parts;
      const priceValue = Number(buy_price);
      const shareValue = Number(shares);
      if (!symbol || !buy_date || !Number.isFinite(priceValue) || !Number.isFinite(shareValue)) throw new Error(`\u7b2c ${index + 1} \u884c\u6301\u4ed3\u5b58\u5728\u7a7a\u503c\u6216\u6570\u5b57\u4e0d\u6b63\u786e`);
      return { symbol, buy_date, buy_price: priceValue, shares: Math.trunc(shareValue), name };
    });
}

function buildPayload(form: FormState, username: string) {
  if (!form.stock_pool_template_name) throw new Error(t.noPool);
  return {
    data_source: "stock_pool",
    processed_dir: "",
    stock_pool_username: username || t.fallbackUser,
    stock_pool_template_name: form.stock_pool_template_name,
    data_profile: "base",
    signal_date: form.signal_date.trim(),
    buy_condition: form.buy_condition.trim(),
    sell_condition: form.sell_condition.trim(),
    score_expression: form.score_expression.trim(),
    top_n: toNumber(form.top_n),
    entry_offset: toNumber(form.entry_offset),
    min_hold_days: toNumber(form.min_hold_days),
    max_hold_days: toNumber(form.max_hold_days),
    per_trade_budget: toNumber(form.per_trade_budget),
    lot_size: toNumber(form.lot_size),
    holdings: parseHoldings(form.holdings_text)
  };
}

export function DailyPlanPage() {
  const [form, setForm] = useState<FormState>(defaultForm);
  const [templates, setTemplates] = useState<StockPoolTemplate[]>([]);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [result, setResult] = useState<DailyResult | null>(null);
  const [activeTab, setActiveTab] = useState("buy");
  const [status, setStatus] = useState(t.ready);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const username = currentUser?.username || t.fallbackUser;
  const summary = result?.summary || {};
  const visibleMetrics = useMemo(() => summaryMetrics.filter(([key]) => summary[key] !== undefined), [summary]);

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
      setStatus(`\u8bfb\u53d6\u6a21\u677f\u5931\u8d25\uff1a${err instanceof Error ? err.message : String(err)}`);
    });
    return () => { cancelled = true; };
  }, []);

  async function runDailyPlan() {
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
    setStatus("\u6b63\u5728\u751f\u6210\u6bcf\u65e5\u8ba1\u5212...");
    try {
      const data = await fetchJson<DailyResult>("/api/daily-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      setResult(data);
      setActiveTab("buy");
      const diag = data.diagnostics || {};
      const sourceLabel = diag.data_source === "stock_pool" ? `\u80a1\u7968\u6c60\u6a21\u677f ${diag.stock_pool_template_name || form.stock_pool_template_name}` : `${diag.file_count || 0} \u4e2a\u6587\u4ef6`;
      setStatus(`\u8ba1\u5212\u751f\u6210\u5b8c\u6210\uff1a${formatValue("data_profile", diag.data_profile)}\uff0c\u8f7d\u5165 ${sourceLabel}\uff0c\u4f7f\u7528 ${data.summary?.signal_date || "-"}\u3002`);
    } catch (err) {
      setError(true);
      setStatus(`\u751f\u6210\u5931\u8d25\uff1a${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="daily-page">
      <div className="daily-header">
        <div>
          <p className="page-eyebrow">{t.eyebrow}</p>
          <h1>{t.title}</h1>
          <p className="daily-note">{t.note}</p>
        </div>
        <div className="daily-header-actions">
          <a className="secondary-link" href="/daily" target="_blank" rel="noreferrer"><ExternalLink size={14} />{t.oldPage}</a>
          <button className="secondary-link" type="button" onClick={() => void loadTemplates(true, username)}><RefreshCw size={14} />{t.reload}</button>
        </div>
      </div>

      <div className="daily-runbar">
        <label><span>{t.pool}</span><select value={form.stock_pool_template_name} onChange={(event) => update("stock_pool_template_name", event.target.value)}>{templates.length ? templates.map((item) => <option key={item.template_name || ""} value={item.template_name || ""}>{item.template_name || "-"} ({item.stock_count || 0})</option>) : <option value="">-</option>}</select></label>
        <label><span>{t.signalDate}</span><input value={form.signal_date} placeholder={t.signalDateHint} onChange={(event) => update("signal_date", event.target.value)} /></label>
        <Field label={t.topN} value={form.top_n} onChange={(value) => update("top_n", value)} />
        <button className="primary-button" type="button" onClick={() => void runDailyPlan()} disabled={loading}><Play size={14} />{loading ? t.running : t.run}</button>
        <button className="secondary-link" type="button" onClick={() => { update("holdings_text", ""); setStatus("\u5df2\u6e05\u7a7a\u6301\u4ed3\u8f93\u5165\u3002"); }}><Eraser size={14} />{t.clear}</button>
      </div>

      <div className="daily-grid">
        <section className="daily-panel">
          <div className="panel-header"><h2>{t.conditions}</h2></div>
          <div className="daily-form-grid one-col">
            <TextArea label={t.buyCondition} value={form.buy_condition} onChange={(value) => update("buy_condition", value)} />
            <TextArea label={t.scoreExpression} value={form.score_expression} onChange={(value) => update("score_expression", value)} />
            <TextArea label={t.sellCondition} value={form.sell_condition} onChange={(value) => update("sell_condition", value)} />
          </div>
        </section>
        <section className="daily-panel">
          <div className="panel-header"><h2>{t.execution}</h2></div>
          <div className="daily-form-grid">
            <Field label={t.entryOffset} value={form.entry_offset} onChange={(value) => update("entry_offset", value)} />
            <Field label={t.minHold} value={form.min_hold_days} onChange={(value) => update("min_hold_days", value)} />
            <Field label={t.maxHold} value={form.max_hold_days} onChange={(value) => update("max_hold_days", value)} />
            <Field label={t.budget} value={form.per_trade_budget} onChange={(value) => update("per_trade_budget", value)} />
            <Field label={t.lotSize} value={form.lot_size} onChange={(value) => update("lot_size", value)} />
          </div>
          <div className="daily-form-grid one-col holdings-editor">
            <TextArea label={t.holdings} rows={5} value={form.holdings_text} placeholder={t.holdingPlaceholder} onChange={(value) => update("holdings_text", value)} />
          </div>
        </section>
      </div>

      <p className={error ? "daily-status error" : "daily-status"}>{status}</p>

      <section className="daily-summary">
        <div className="summary-intro">
          <p className="page-eyebrow">{t.summaryEyebrow}</p>
          <h2>{t.summaryTitle}</h2>
        </div>
        <div className="metric-strip daily-metrics">
          {visibleMetrics.length ? visibleMetrics.map(([key, label]) => <div className="metric-tile" key={key}><span>{label}</span><strong>{formatValue(key, summary[key])}</strong></div>) : <div className="metric-tile"><span>Status</span><strong>-</strong></div>}
        </div>
      </section>

      <section className="daily-results">
        <div className="result-tabs">{[["buy", t.buyTab], ["sell", t.sellTab], ["holding", t.holdingTab]].map(([key, label]) => <button key={key} className={activeTab === key ? "active" : ""} type="button" onClick={() => setActiveTab(key)}>{label}</button>)}</div>
        {activeTab === "buy" && <DataTable rows={result?.buy_rows || []} columns={buyColumns} />}
        {activeTab === "sell" && <DataTable rows={result?.sell_rows || []} columns={sellColumns} />}
        {activeTab === "holding" && <DataTable rows={result?.holding_rows || []} columns={holdingColumns} />}
      </section>
    </section>
  );
}

function Field({ label, value, onChange, step, disabled = false }: { label: string; value: string; onChange: (value: string) => void; step?: string; disabled?: boolean }) {
  return <label><span>{label}</span><input type="number" step={step} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} /></label>;
}

function TextArea({ label, value, onChange, rows = 3, placeholder = "" }: { label: string; value: string; onChange: (value: string) => void; rows?: number; placeholder?: string }) {
  return <label><span>{label}</span><textarea rows={rows} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} /></label>;
}

function DataTable({ rows, columns }: { rows: ResultRow[]; columns: string[] }) {
  if (!rows.length) return <div className="empty-state">{t.noRows}</div>;
  const rowKeys = Array.from(rows.reduce((keys, row) => {
    Object.keys(row).forEach((key) => keys.add(key));
    return keys;
  }, new Set<string>()));
  const visibleColumns = [...columns.filter((key) => rowKeys.includes(key)), ...rowKeys.filter((key) => !columns.includes(key))];
  return <div className="table-wrap daily-table-wrap"><table><thead><tr>{visibleColumns.map((key) => <th key={key}>{formatHeader(key)}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{visibleColumns.map((key) => <td key={key}>{formatValue(key, row[key])}</td>)}</tr>)}</tbody></table></div>;
}
