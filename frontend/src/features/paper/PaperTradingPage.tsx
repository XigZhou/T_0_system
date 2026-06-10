import { useEffect, useMemo, useState } from "react";
import { Database, ExternalLink, Play, RefreshCw, RotateCcw } from "lucide-react";
import { formatHeader, formatValue } from "../backtests/format";
import "./paperTrading.css";

type ResultRow = Record<string, unknown>;
type CurrentUser = { username?: string; role?: string; display_name?: string };
type PaperAction = "generate" | "execute" | "mark";

type PaperTemplate = {
  account_id?: string;
  account_name?: string;
  error?: string | boolean;
};

type PaperResult = {
  summary?: Record<string, unknown>;
  pending_order_rows?: ResultRow[];
  trade_rows?: ResultRow[];
  holding_rows?: ResultRow[];
  asset_rows?: ResultRow[];
  log_rows?: ResultRow[];
  diagnostics?: Record<string, unknown>;
};

type FormState = {
  config_dir: string;
  account_id: string;
  action: PaperAction;
  trade_date: string;
};

const t = {
  title: "\u591a\u8d26\u6237\u6a21\u62df\u4ea4\u6613",
  eyebrow: "Paper Trading",
  note: "\u8bfb\u53d6\u6a21\u62df\u8d26\u6237\u6a21\u677f\u548c SQLite \u8d26\u672c\uff0c\u539f API \u884c\u4e3a\u4fdd\u6301\u4e0d\u53d8\u3002",
  oldPage: "\u6253\u5f00\u65e7\u9875",
  templates: "\u6a21\u677f\u7ba1\u7406",
  accountTemplate: "\u6a21\u62df\u8d26\u6237\u6a21\u677f",
  action: "\u6267\u884c\u52a8\u4f5c",
  tradeDate: "\u52a8\u4f5c\u65e5\u671f",
  tradeDateHint: "\u4f8b\u5982 20260511\uff1b\u7559\u7a7a\u81ea\u52a8\u8bc6\u522b",
  marketNote: "\u884c\u60c5\u8bf4\u660e",
  marketValue: "\u672c\u5730\u6a21\u5f0f\u8bfb\u53d6\u80a1\u7968\u6c60 SQLite \u65e5\u7ebf\u4ef7\u683c",
  run: "\u8fd0\u884c\u6a21\u62df\u8d26\u6237",
  running: "\u8fd0\u884c\u4e2d...",
  refreshQuotes: "\u83b7\u53d6\u6301\u4ed3\u6700\u65b0\u4ef7\u683c",
  loadingQuotes: "\u5237\u65b0\u4e2d...",
  loadLedger: "\u8bfb\u53d6 SQLite \u8d26\u672c",
  reloadTemplates: "\u5237\u65b0\u6a21\u677f",
  summaryEyebrow: "\u8d26\u6237\u6458\u8981",
  summaryTitle: "\u6a21\u62df\u8fd0\u884c\u7ed3\u679c",
  statusReady: "\u6b63\u5728\u8bfb\u53d6\u6a21\u677f\u3002",
  loadingTemplates: "\u6b63\u5728\u8bfb\u53d6\u6a21\u62df\u8d26\u6237\u6a21\u677f...",
  loadedTemplates: "\u5df2\u8bfb\u53d6\u6a21\u677f\uff0c\u6b63\u5728\u8bfb\u53d6\u8d26\u672c\u3002",
  noTemplates: "\u6ca1\u6709\u627e\u5230\u6a21\u677f\uff0c\u8bf7\u5148\u5230\u6a21\u677f\u7ba1\u7406\u521b\u5efa\u6a21\u62df\u8d26\u6237\u6a21\u677f\u3002",
  noAccount: "\u8bf7\u5148\u9009\u62e9\u6a21\u62df\u8d26\u6237\u6a21\u677f\u3002",
  ledgerLoading: "\u6b63\u5728\u8bfb\u53d6\u8d26\u672c...",
  ledgerLoaded: "SQLite \u8d26\u672c\u8bfb\u53d6\u5b8c\u6210\u3002",
  ledgerEmpty: "SQLite \u8d26\u672c\u8fd8\u6ca1\u6709\u8bb0\u5f55\uff0c\u5148\u8fd0\u884c\u4e00\u6b21\u6a21\u62df\u8d26\u6237\u4f1a\u81ea\u52a8\u521b\u5efa\u3002",
  runLoading: "\u6b63\u5728\u8fd0\u884c\u6a21\u62df\u8d26\u6237...",
  runDone: "\u8fd0\u884c\u5b8c\u6210\uff0c\u7ed3\u679c\u5df2\u5199\u5165 SQLite \u8d26\u672c\u3002",
  refreshLoading: "\u6b63\u5728\u83b7\u53d6\u5f53\u524d\u6301\u4ed3\u6700\u65b0\u4ef7\u683c...",
  refreshDone: "\u5f53\u524d\u6301\u4ed3\u6700\u65b0\u4ef7\u683c\u5df2\u5237\u65b0\u3002",
  failedTemplates: "\u8bfb\u53d6\u6a21\u677f\u5931\u8d25",
  failedLedger: "\u8bfb\u53d6\u8d26\u672c\u5931\u8d25",
  failedRun: "\u8fd0\u884c\u5931\u8d25",
  failedRefresh: "\u5237\u65b0\u6700\u65b0\u4ef7\u683c\u5931\u8d25",
  empty: "\u6682\u65e0\u7ed3\u679c",
  fallbackUser: "admin"
};

const actionLabels: Record<PaperAction | "refresh", string> = {
  generate: "\u6536\u76d8\u751f\u6210\u5f85\u6267\u884c\u8ba2\u5355",
  execute: "\u5f00\u76d8\u6267\u884c\u5f85\u6210\u4ea4\u8ba2\u5355",
  mark: "\u6536\u76d8\u66f4\u65b0\u6301\u4ed3\u4f30\u503c",
  refresh: "\u83b7\u53d6\u5f53\u524d\u6301\u4ed3\u6700\u65b0\u4ef7\u683c"
};

const defaultForm: FormState = {
  config_dir: "configs/paper_accounts",
  account_id: "",
  action: "generate",
  trade_date: ""
};

const summaryKeys = [
  "account_id",
  "account_name",
  "action",
  "signal_date",
  "trade_date",
  "planned_buy_count",
  "planned_sell_count",
  "price_filtered_count",
  "added_order_count",
  "executed_count",
  "failed_count",
  "updated_holding_count",
  "failed_holding_count",
  "cash",
  "market_value",
  "total_equity",
  "market_status",
  "quote_source",
  "ledger_storage",
  "ledger_exists",
  "order_count",
  "trade_count",
  "holding_count",
  "asset_count",
  "log_count",
  "last_log_time",
  "last_log_action",
  "last_log_level"
];

async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { credentials: "include", ...options });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function templateLabel(item: PaperTemplate): string {
  if (item.error) return `${item.account_id || "-"}\uff1a\u8bfb\u53d6\u5931\u8d25`;
  return `${item.account_name || item.account_id || "-"}\uff08${item.account_id || "-"}\uff09`;
}

function buildPayload(form: FormState, username: string, action: PaperAction | "refresh") {
  if (!form.account_id) throw new Error(t.noAccount);
  return {
    account_id: form.account_id,
    username: username || t.fallbackUser,
    config_dir: form.config_dir || defaultForm.config_dir,
    action,
    trade_date: form.trade_date.trim()
  };
}

export function PaperTradingPage() {
  const [form, setForm] = useState<FormState>(defaultForm);
  const [templates, setTemplates] = useState<PaperTemplate[]>([]);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [result, setResult] = useState<PaperResult | null>(null);
  const [activeTab, setActiveTab] = useState("orders");
  const [status, setStatus] = useState(t.statusReady);
  const [error, setError] = useState(false);
  const [loadingAction, setLoadingAction] = useState<"templates" | "ledger" | "run" | "refresh" | "">("");
  const username = currentUser?.username || t.fallbackUser;
  const summary = result?.summary || {};
  const visibleSummary = useMemo(() => summaryKeys.filter((key) => summary[key] !== undefined), [summary]);
  const selectedTemplate = templates.find((item) => item.account_id === form.account_id);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function renderResult(nextResult: PaperResult, nextStatus: string, preferredTab = "") {
    setResult(nextResult);
    if (preferredTab) setActiveTab(preferredTab);
    setStatus(nextStatus);
    setError(false);
  }

  async function loadLedger(showStatus = true, accountId = form.account_id, targetUsername = username, configDir = form.config_dir) {
    if (!accountId) {
      if (showStatus) {
        setError(true);
        setStatus(t.noAccount);
      }
      return;
    }
    if (showStatus) {
      setLoadingAction("ledger");
      setError(false);
      setStatus(t.ledgerLoading);
    }
    try {
      const params = new URLSearchParams({ account_id: accountId, username: targetUsername || t.fallbackUser, config_dir: configDir || defaultForm.config_dir });
      const data = await fetchJson<PaperResult>(`/api/paper/ledger?${params.toString()}`);
      const ledgerExists = Boolean(data.summary?.ledger_exists);
      renderResult(data, ledgerExists ? t.ledgerLoaded : t.ledgerEmpty, (data.log_rows || []).length ? "logs" : "orders");
    } catch (err) {
      setError(true);
      setStatus(`${t.failedLedger}\uff1a${err instanceof Error ? err.message : String(err)}`);
    } finally {
      if (showStatus) setLoadingAction("");
    }
  }

  async function loadTemplates(showStatus = false, targetUsername = username) {
    if (showStatus) {
      setLoadingAction("templates");
      setError(false);
      setStatus(t.loadingTemplates);
    }
    try {
      const configDir = form.config_dir || defaultForm.config_dir;
      const data = await fetchJson<{ templates: PaperTemplate[] }>(`/api/paper/templates?config_dir=${encodeURIComponent(configDir)}&username=${encodeURIComponent(targetUsername || t.fallbackUser)}`);
      const nextTemplates = data.templates || [];
      setTemplates(nextTemplates);
      if (!nextTemplates.length) {
        setForm((current) => ({ ...current, account_id: "" }));
        setError(true);
        setStatus(t.noTemplates);
        return;
      }
      const currentAccount = form.account_id;
      const nextAccount = currentAccount && nextTemplates.some((item) => item.account_id === currentAccount) ? currentAccount : nextTemplates[0]?.account_id || "";
      setForm((current) => ({ ...current, account_id: nextAccount }));
      if (showStatus) setStatus(t.loadedTemplates);
      await loadLedger(false, nextAccount, targetUsername, configDir);
    } catch (err) {
      setError(true);
      setStatus(`${t.failedTemplates}\uff1a${err instanceof Error ? err.message : String(err)}`);
    } finally {
      if (showStatus) setLoadingAction("");
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function boot() {
      const auth = await fetchJson<{ authenticated: boolean; user?: CurrentUser | null }>("/api/auth/me");
      if (cancelled) return;
      const nextUser = auth.authenticated ? auth.user || null : null;
      setCurrentUser(nextUser);
      await loadTemplates(false, nextUser?.username || t.fallbackUser);
    }
    boot().catch((err) => {
      if (cancelled) return;
      setError(true);
      setStatus(`${t.failedTemplates}\uff1a${err instanceof Error ? err.message : String(err)}`);
    });
    return () => { cancelled = true; };
  }, []);

  async function runPaper(action: PaperAction | "refresh" = form.action) {
    let payload: Record<string, unknown>;
    try {
      payload = buildPayload(form, username, action);
    } catch (err) {
      setError(true);
      setStatus(err instanceof Error ? err.message : String(err));
      return;
    }
    const isRefresh = action === "refresh";
    setLoadingAction(isRefresh ? "refresh" : "run");
    setError(false);
    setStatus(isRefresh ? t.refreshLoading : t.runLoading);
    try {
      const data = await fetchJson<PaperResult>("/api/paper/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const nextTab = isRefresh ? "holdings" : (data.log_rows || []).length ? "logs" : "orders";
      const marketStatus = data.summary?.market_status ? `\uff1a${String(data.summary.market_status)}` : "";
      renderResult(data, isRefresh ? `${t.refreshDone}${marketStatus}` : t.runDone, nextTab);
    } catch (err) {
      setError(true);
      setStatus(`${isRefresh ? t.failedRefresh : t.failedRun}\uff1a${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoadingAction("");
    }
  }

  const tabs = [
    { key: "orders", label: "\u5f85\u6267\u884c\u8ba2\u5355", rows: result?.pending_order_rows || [] },
    { key: "trades", label: "\u6210\u4ea4\u6d41\u6c34", rows: result?.trade_rows || [] },
    { key: "holdings", label: "\u5f53\u524d\u6301\u4ed3", rows: result?.holding_rows || [] },
    { key: "assets", label: "\u6bcf\u65e5\u8d44\u4ea7", rows: result?.asset_rows || [] },
    { key: "logs", label: "\u8fd0\u884c\u65e5\u5fd7", rows: result?.log_rows || [] }
  ];
  const activeRows = tabs.find((tab) => tab.key === activeTab)?.rows || [];

  return (
    <section className="paper-trading-page">
      <div className="paper-header">
        <div>
          <p className="page-eyebrow">{t.eyebrow}</p>
          <h1>{t.title}</h1>
          <p className="paper-note">{t.note}</p>
        </div>
        <div className="paper-header-actions">
          <a className="secondary-link" href="/paper" target="_blank" rel="noreferrer"><ExternalLink size={14} />{t.oldPage}</a>
          <a className="secondary-link" href="#/portfolio/paper-templates"><ExternalLink size={14} />{t.templates}</a>
        </div>
      </div>

      <div className="paper-runbar">
        <label className="template-select"><span>{t.accountTemplate}</span><select value={form.account_id} onChange={(event) => { update("account_id", event.target.value); void loadLedger(false, event.target.value, username, form.config_dir); }}>{templates.length ? templates.map((item) => <option key={item.account_id || ""} value={item.account_id || ""}>{templateLabel(item)}</option>) : <option value="">-</option>}</select></label>
        <label><span>{t.action}</span><select value={form.action} onChange={(event) => update("action", event.target.value as PaperAction)}><option value="generate">{actionLabels.generate}</option><option value="execute">{actionLabels.execute}</option><option value="mark">{actionLabels.mark}</option></select></label>
        <label><span>{t.tradeDate}</span><input value={form.trade_date} placeholder={t.tradeDateHint} onChange={(event) => update("trade_date", event.target.value)} /></label>
        <label className="market-source"><span>{t.marketNote}</span><input value={t.marketValue} readOnly /></label>
        <button className="primary-button write-button" type="button" onClick={() => void runPaper(form.action)} disabled={loadingAction === "run"}><Play size={14} />{loadingAction === "run" ? t.running : t.run}</button>
      </div>

      <div className="paper-actionbar">
        <button className="secondary-link" type="button" onClick={() => void runPaper("refresh")} disabled={loadingAction === "refresh"}><RefreshCw size={14} />{loadingAction === "refresh" ? t.loadingQuotes : t.refreshQuotes}</button>
        <button className="secondary-link" type="button" onClick={() => void loadLedger(true)} disabled={loadingAction === "ledger"}><Database size={14} />{t.loadLedger}</button>
        <button className="secondary-link" type="button" onClick={() => void loadTemplates(true, username)} disabled={loadingAction === "templates"}><RotateCcw size={14} />{t.reloadTemplates}</button>
      </div>

      <p className={error ? "paper-status error" : "paper-status"}>{status}</p>

      <section className="paper-summary">
        <div className="summary-intro">
          <p className="page-eyebrow">{t.summaryEyebrow}</p>
          <h2>{selectedTemplate?.account_name || t.summaryTitle}</h2>
        </div>
        <div className="metric-strip paper-metrics">
          {visibleSummary.length ? visibleSummary.map((key) => <div className="metric-tile" key={key}><span>{formatHeader(key)}</span><strong>{formatValue(key, summary[key])}</strong></div>) : <div className="metric-tile"><span>Status</span><strong>-</strong></div>}
        </div>
      </section>

      <section className="paper-results">
        <div className="result-tabs">{tabs.map((tab) => <button key={tab.key} className={activeTab === tab.key ? "active" : ""} type="button" onClick={() => setActiveTab(tab.key)}>{tab.label}</button>)}</div>
        <DataTable rows={activeRows} />
      </section>
    </section>
  );
}

function DataTable({ rows }: { rows: ResultRow[] }) {
  if (!rows.length) return <div className="empty-state">{t.empty}</div>;
  const columns = Array.from(rows.reduce((keys, row) => {
    Object.keys(row).forEach((key) => keys.add(key));
    return keys;
  }, new Set<string>()));
  return <div className="table-wrap paper-table-wrap"><table><thead><tr>{columns.map((key) => <th key={key}>{formatHeader(key)}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map((key) => <td key={key}>{formatValue(key, row[key])}</td>)}</tr>)}</tbody></table></div>;
}
