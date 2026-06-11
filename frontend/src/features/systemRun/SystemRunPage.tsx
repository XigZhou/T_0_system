import { useEffect, useMemo, useState } from "react";
import { Play, RefreshCw, RotateCcw, Save, Search, ShieldAlert } from "lucide-react";
import "./systemRun.css";

type User = { username?: string; display_name?: string; role?: string; is_admin?: boolean };
type Row = Record<string, unknown>;
type StatusState = { text: string; error?: boolean };
type Overview = { scheduler?: Row; core_tasks?: Record<string, Row> };
type UniverseRow = { symbol?: string; ts_code?: string; name?: string; stock_name?: string; source?: string; is_active?: number | boolean; updated_at?: string };
type RunRow = { run_id?: string; job_name?: string; target_date?: string; status?: string; started_at?: string; finished_at?: string; failed_stage?: string; error_summary?: string; log_file?: string };
type ResolveResult = { resolved?: Row[]; unresolved?: string[]; ambiguous?: Row[]; duplicate_inputs?: string[]; message?: string; written?: boolean };

const txt = {
  title: "\u7cfb\u7edf\u7ef4\u62a4",
  eyebrow: "Operations",
  note: "\u96c6\u4e2d\u67e5\u770b\u6838\u5fc3\u4efb\u52a1\u3001\u4e3b\u80a1\u7968\u6c60\u548c\u8c03\u5ea6\u8fd0\u884c\u8bb0\u5f55\u3002",
  refreshOverview: "\u5237\u65b0\u603b\u89c8",
  refreshRuns: "\u5237\u65b0\u8fd0\u884c\u8bb0\u5f55",
  refreshUniverse: "\u5237\u65b0\u4e3b\u80a1\u7968\u6c60",
  checking: "\u6b63\u5728\u6821\u9a8c\u767b\u5f55\u7528\u6237\u3002",
  denied: "\u53ea\u6709 admin \u7528\u6237\u53ef\u4ee5\u67e5\u770b\u7cfb\u7edf\u7ef4\u62a4\u3002",
  overviewReady: "\u8fd0\u7ef4\u770b\u677f\u5df2\u8bfb\u53d6\uff1b\u5f53\u524d\u6ca1\u6709\u5199\u5165\u6570\u636e\u3002",
  overviewLoading: "\u6b63\u5728\u8bfb\u53d6\u8fd0\u7ef4\u603b\u89c8\uff1b\u672c\u6b21\u4e0d\u4f1a\u5199\u5165\u6570\u636e\u3002",
  overviewDone: "\u8fd0\u7ef4\u603b\u89c8\u5df2\u5237\u65b0\uff1b\u672c\u6b21\u4ec5\u8bfb\u53d6\uff0c\u6ca1\u6709\u5199\u5165\u6570\u636e\u3002",
  overviewFail: "\u8bfb\u53d6\u8fd0\u7ef4\u770b\u677f\u5931\u8d25",
  summaryTitle: "\u8fd0\u7ef4\u603b\u89c8",
  summaryEyebrow: "\u6838\u5fc3\u4efb\u52a1\u72b6\u6001",
  summaryNote: "\u6309\u8c03\u5ea6\u8fd0\u884c\u8bb0\u5f55\u6c47\u603b\u6838\u5fc3\u4efb\u52a1\u6700\u8fd1\u72b6\u6001\uff1b\u672c\u533a\u57df\u53ea\u8bfb\u53d6\u3002",
  stockTitle: "\u65e5\u7ebf\u4e0e\u6307\u6807",
  stockEyebrow: "\u4e3b\u5e93\u6570\u636e\u7ef4\u62a4",
  stockNote: "\u5199\u5165\u4e3b\u80a1\u7968\u6c60\u8303\u56f4\u5185\u7684 SQLite \u884c\u60c5\u6307\u6807\u4e3b\u5e93\u3002",
  todayTask: "\u5f53\u5929\u4efb\u52a1",
  todayNote: "\u6309\u670d\u52a1\u5668\u5f53\u5929\u65e5\u671f\u63d0\u4ea4\uff1b\u975e\u4ea4\u6613\u65e5\u7531\u884c\u60c5\u94fe\u8def\u56de\u843d\u5230\u6700\u8fd1\u5f00\u5e02\u65e5\u3002",
  collectToday: "\u91c7\u96c6\u4eca\u65e5\u65e5\u7ebf",
  computeToday: "\u8ba1\u7b97\u4eca\u65e5\u6307\u6807",
  collectRange: "\u91c7\u96c6\u533a\u95f4\u65e5\u7ebf",
  computeRange: "\u8ba1\u7b97\u533a\u95f4\u6307\u6807",
  startDate: "\u5f00\u59cb\u65e5\u671f",
  endDate: "\u7ed3\u675f\u65e5\u671f",
  maxSymbols: "\u6700\u5927\u80a1\u7968\u6570",
  sleepSeconds: "\u95f4\u9694\u79d2\u6570",
  stockReady: "\u7b49\u5f85\u7ba1\u7406\u5458\u63d0\u4ea4\uff1b\u8fd9\u4e9b\u52a8\u4f5c\u4f1a\u5199\u5165 SQLite \u4e3b\u5e93\u3002",
  universeTitle: "\u540d\u79f0\u89e3\u6790\u4e0e\u4fdd\u5b58",
  universeEyebrow: "\u4e3b\u80a1\u7968\u6c60\u7ef4\u62a4",
  universeNote: "\u89e3\u6790\u4e0d\u4f1a\u5199\u5165\uff1b\u4fdd\u5b58\u4f1a\u5199\u5165\u4e3b\u80a1\u7968\u6c60\u3002",
  universeInput: "\u80a1\u7968\u540d\u79f0\u6216\u4ee3\u7801\uff0c\u6bcf\u884c\u4e00\u53ea",
  universePlaceholder: "\u5e73\u5b89\u94f6\u884c\n000001 \u5e73\u5b89\u94f6\u884c",
  includeInactive: "\u5305\u542b\u505c\u7528",
  appendMode: "\u8ffd\u52a0\u6216\u6fc0\u6d3b",
  replaceMode: "\u66ff\u6362\u6d3b\u8dc3\u96c6\u5408",
  resolveNames: "\u89e3\u6790\u540d\u79f0",
  saveUniverse: "\u4fdd\u5b58\u4e3b\u80a1\u7968\u6c60",
  universeReady: "\u7b49\u5f85\u8f93\u5165\uff1b\u5f53\u524d\u6ca1\u6709\u5199\u5165\u6570\u636e\u3002",
  noResolve: "\u6682\u65e0\u89e3\u6790\u7ed3\u679c\u3002",
  runsTitle: "\u8c03\u5ea6\u6d41\u6c34",
  runsEyebrow: "\u4efb\u52a1\u8fd0\u884c\u8bb0\u5f55",
  runsNote: "\u5931\u8d25\u4e14\u53ef\u91cd\u8dd1\u7684\u8bb0\u5f55\u53ef\u767b\u8bb0\u5b89\u5168\u91cd\u8dd1\u8bf7\u6c42\u3002",
  runsReady: "\u7b49\u5f85\u8bfb\u53d6\u8fd0\u884c\u8bb0\u5f55\uff1b\u8bfb\u53d6\u4e0d\u4f1a\u5199\u5165\u6570\u636e\u3002",
  noRows: "\u6682\u65e0\u6570\u636e",
  retry: "\u767b\u8bb0\u91cd\u8dd1",
  confirmRetry: "\u786e\u8ba4\u767b\u8bb0\u5b89\u5168\u91cd\u8dd1\u8bf7\u6c42\uff1f\u672c\u64cd\u4f5c\u53ea\u5199\u5165\u5f85\u91cd\u8dd1\u8bb0\u5f55\uff0c\u4e0d\u76f4\u63a5\u6267\u884c\u4efb\u52a1\u3002",
  dateInvalid: "\u8bf7\u8f93\u5165 YYYYMMDD \u683c\u5f0f\u7684\u5f00\u59cb\u65e5\u671f\u548c\u7ed3\u675f\u65e5\u671f",
  dateOrderInvalid: "\u5f00\u59cb\u65e5\u671f\u4e0d\u80fd\u665a\u4e8e\u7ed3\u675f\u65e5\u671f",
  needNames: "\u8bf7\u8f93\u5165\u81f3\u5c11\u4e00\u4e2a\u80a1\u7968\u540d\u79f0\u518d\u89e3\u6790\uff1b\u672c\u6b21\u6ca1\u6709\u5199\u5165\u6570\u636e\u3002",
  needRows: "\u8bf7\u8f93\u5165\u81f3\u5c11\u4e00\u53ea\u80a1\u7968\u518d\u4fdd\u5b58\uff1b\u672c\u6b21\u6ca1\u6709\u5199\u5165\u6570\u636e\u3002"
};

const TASK_LABELS: Record<string, string> = {
  core_after_close_generate: "\u6838\u5fc3\u6536\u76d8\u751f\u6210",
  daily_sync: "\u65e5\u7ebf\u540c\u6b65",
  feature_build: "\u6307\u6807\u6784\u5efa",
  safe_retry: "\u5b89\u5168\u91cd\u8dd1"
};

const RETRYABLE_JOBS = new Set(["daily_sync", "feature_build", "core_after_close_generate"]);
const statusLabels: Record<string, string> = {
  success: "\u6210\u529f",
  failed: "\u5931\u8d25",
  running: "\u8fd0\u884c\u4e2d",
  retry_pending: "\u5f85\u91cd\u8dd1",
  skipped_locked: "\u9501\u5b9a\u8df3\u8fc7",
  skipped_non_trade_day: "\u975e\u4ea4\u6613\u65e5\u8df3\u8fc7",
  check_only: "\u4ec5\u68c0\u67e5"
};

function isAdminUser(user: User | null): boolean {
  return user?.role === "admin" || user?.is_admin === true;
}

function formatNumber(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return value.toLocaleString("zh-CN");
  return String(value);
}

function formatStatus(value: unknown): string {
  const key = String(value || "").trim();
  return statusLabels[key] || key || "-";
}

function formatJobName(value: unknown): string {
  const key = String(value || "").trim();
  return TASK_LABELS[key] || key || "-";
}

function shortId(value: unknown): string {
  const text = String(value || "");
  return text.length > 10 ? text.slice(0, 10) : text || "-";
}

function detailText(error: unknown): string {
  return error instanceof Error ? error.message : String(error || "");
}

async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { credentials: "include", ...options });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function normalizeAdminDate(value = ""): string {
  const text = String(value || "").trim().replace(/[-/]/g, "");
  return /^\d{8}$/.test(text) ? text : "";
}

function rowText(row: Row, key: string): string {
  return String(row[key] ?? "");
}

function canRetry(row: RunRow): boolean {
  return row.status === "failed" && RETRYABLE_JOBS.has(row.job_name || "");
}
export function SystemRunPage() {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [overview, setOverview] = useState<Overview>({});
  const [universeRows, setUniverseRows] = useState<UniverseRow[]>([]);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [universeText, setUniverseText] = useState("");
  const [includeInactive, setIncludeInactive] = useState(false);
  const [universeMode, setUniverseMode] = useState<"append" | "replace">("append");
  const [resolvedDetail, setResolvedDetail] = useState(txt.noResolve);
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [maxSymbols, setMaxSymbols] = useState("0");
  const [sleepSeconds, setSleepSeconds] = useState("0.2");
  const [busy, setBusy] = useState(false);
  const [overviewStatus, setOverviewStatus] = useState<StatusState>({ text: txt.checking });
  const [stockDataStatus, setStockDataStatus] = useState<StatusState>({ text: txt.stockReady });
  const [universeStatus, setUniverseStatus] = useState<StatusState>({ text: txt.universeReady });
  const [runStatus, setRunStatus] = useState<StatusState>({ text: txt.runsReady });
  const isAdmin = isAdminUser(currentUser);
  const username = currentUser?.username || "admin";

  async function loadOverview(showStatus = true) {
    if (showStatus) setOverviewStatus({ text: txt.overviewLoading });
    const data = await fetchJson<Overview>("/api/admin/overview");
    setOverview(data);
    if (showStatus) setOverviewStatus({ text: txt.overviewDone });
  }

  async function loadMainUniverse(showStatus = true, nextIncludeInactive = includeInactive) {
    if (showStatus) setUniverseStatus({ text: "\u6b63\u5728\u8bfb\u53d6\u4e3b\u80a1\u7968\u6c60\uff1b\u672c\u6b21\u4e0d\u4f1a\u5199\u5165\u6570\u636e\u3002" });
    const data = await fetchJson<{ rows?: UniverseRow[]; count?: number; message?: string }>(`/api/admin/main-universe?include_inactive=${nextIncludeInactive ? "true" : "false"}`);
    setUniverseRows(data.rows || []);
    if (showStatus) setUniverseStatus({ text: data.message || `\u5df2\u8bfb\u53d6 ${formatNumber(data.count || 0)} \u53ea\u80a1\u7968\uff1b\u672c\u6b21\u6ca1\u6709\u5199\u5165\u6570\u636e\u3002` });
  }

  async function loadSchedulerRuns(showStatus = true) {
    if (showStatus) setRunStatus({ text: "\u6b63\u5728\u8bfb\u53d6\u4efb\u52a1\u8fd0\u884c\u8bb0\u5f55\uff1b\u672c\u6b21\u4e0d\u4f1a\u5199\u5165\u6570\u636e\u3002" });
    const data = await fetchJson<{ runs?: RunRow[] }>("/api/admin/scheduler/runs?limit=50");
    setRuns(data.runs || []);
    if (showStatus) setRunStatus({ text: `\u5df2\u8bfb\u53d6 ${(data.runs || []).length} \u6761\u8fd0\u884c\u8bb0\u5f55\uff1b\u672c\u6b21\u6ca1\u6709\u5199\u5165\u6570\u636e\u3002` });
  }

  async function boot() {
    setAuthLoading(true);
    try {
      const auth = await fetchJson<{ authenticated?: boolean; user?: User | null }>("/api/auth/me");
      const user = auth.authenticated ? auth.user || null : null;
      setCurrentUser(user);
      if (!isAdminUser(user)) {
        setOverviewStatus({ text: txt.denied, error: true });
        return;
      }
      await Promise.all([loadOverview(false), loadMainUniverse(false), loadSchedulerRuns(false)]);
      setOverviewStatus({ text: txt.overviewReady });
    } catch (error) {
      setOverviewStatus({ text: `${txt.overviewFail}\uff1a${detailText(error)}`, error: true });
    } finally {
      setAuthLoading(false);
    }
  }

  useEffect(() => {
    void boot();
  }, []);

  const summaryCards = useMemo(() => {
    const scheduler = overview.scheduler || {};
    const tasks = overview.core_tasks || {};
    const cards = Object.entries(TASK_LABELS).map(([key, label]) => {
      const task = tasks[key] || {};
      const latest = task.latest_run as Row | undefined;
      return {
        key,
        label,
        value: latest ? formatStatus(latest.status) : "\u6682\u65e0",
        meta: `\u65e5\u671f ${latest?.target_date || "-"} \u00b7 \u8fd0\u884c ${formatNumber(task.run_count || 0)} \u00b7 \u5931\u8d25 ${formatNumber((task.status_counts as Row | undefined)?.failed || 0)}`
      };
    });
    cards.push({
      key: "scheduler",
      label: "\u8c03\u5ea6\u8bb0\u5f55",
      value: formatNumber(scheduler.run_count || 0),
      meta: `\u6700\u8fd1\u72b6\u6001 ${formatStatus((scheduler.latest_run as Row | undefined)?.status)}`
    });
    return cards;
  }, [overview]);
  function parseUniverseLines() {
    return universeText.split(/\n+/).map((line) => line.trim()).filter(Boolean).map((line) => {
      const match = line.match(/\b(\d{6})(?:\.(?:SZ|SH|BJ))?\b/i);
      if (!match) return { name: line };
      const symbol = match[1];
      const name = line.replace(match[0], " ").replace(/[,.\uff0c\u3001;\uff1b|]/g, " ").replace(/\s+/g, " ").trim();
      return name ? { symbol, name } : { symbol };
    });
  }

  function parseUniverseNames() {
    return parseUniverseLines().map((row) => row.name || "").filter(Boolean);
  }

  function renderResolveResult(data: ResolveResult) {
    const resolved = data.resolved || [];
    const unresolved = data.unresolved || [];
    const ambiguous = data.ambiguous || [];
    const duplicates = data.duplicate_inputs || [];
    const parts = [
      `\u89e3\u6790\u6210\u529f ${resolved.length} \u53ea`,
      `\u672a\u5339\u914d ${unresolved.length} \u4e2a`,
      `\u6b67\u4e49 ${ambiguous.length} \u4e2a`,
      `\u91cd\u590d ${duplicates.length} \u4e2a`
    ];
    if (resolved.length) parts.push(`\u6210\u529f\u6837\u4f8b\uff1a${resolved.slice(0, 6).map((item) => `${rowText(item, "name") || rowText(item, "stock_name")}(${rowText(item, "symbol")})`).join("\uff0c")}`);
    if (unresolved.length) parts.push(`\u672a\u5339\u914d\uff1a${unresolved.slice(0, 8).join("\uff0c")}`);
    if (ambiguous.length) parts.push(`\u6b67\u4e49\uff1a${ambiguous.slice(0, 4).map((item) => rowText(item, "name")).join("\uff0c")}`);
    if (duplicates.length) parts.push(`\u91cd\u590d\uff1a${duplicates.slice(0, 8).join("\uff0c")}`);
    setResolvedDetail(`${parts.join("\u3002")}\u3002`);
  }

  async function resolveMainUniverse() {
    const names = parseUniverseNames();
    if (!names.length) {
      setUniverseStatus({ text: txt.needNames, error: true });
      return;
    }
    setBusy(true);
    setUniverseStatus({ text: "\u6b63\u5728\u89e3\u6790\u80a1\u7968\u540d\u79f0\uff1b\u672c\u6b21\u4e0d\u4f1a\u5199\u5165\u6570\u636e\u3002" });
    try {
      const data = await fetchJson<ResolveResult>("/api/admin/main-universe/resolve", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ names }) });
      renderResolveResult(data);
      setUniverseStatus({ text: data.message || "\u89e3\u6790\u5b8c\u6210\uff1b\u672a\u5199\u5165\u4e3b\u80a1\u7968\u6c60\u6570\u636e\u3002" });
    } catch (error) {
      setUniverseStatus({ text: `\u89e3\u6790\u5931\u8d25\uff1a${detailText(error)}`, error: true });
    } finally {
      setBusy(false);
    }
  }

  async function saveMainUniverse() {
    const rows = parseUniverseLines();
    if (!rows.length) {
      setUniverseStatus({ text: txt.needRows, error: true });
      return;
    }
    const modeLabel = universeMode === "replace" ? txt.replaceMode : txt.appendMode;
    const confirmText = `\u786e\u8ba4\u4ee5\u201c${modeLabel}\u201d\u6a21\u5f0f\u5199\u5165\u4e3b\u80a1\u7968\u6c60\uff1f`;
    if (typeof window.confirm === "function" && !window.confirm(confirmText)) return;
    setBusy(true);
    setUniverseStatus({ text: "\u6b63\u5728\u5199\u5165\u4e3b\u80a1\u7968\u6c60..." });
    try {
      const data = await fetchJson<ResolveResult>("/api/admin/main-universe/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: universeMode, rows, source: "admin_upload" }) });
      renderResolveResult(data);
      setUniverseStatus({ text: data.message || (data.written ? "\u4e3b\u80a1\u7968\u6c60\u5df2\u5199\u5165\u3002" : "\u6ca1\u6709\u5199\u5165\u4e3b\u80a1\u7968\u6c60\u3002"), error: !data.written });
      await loadMainUniverse(false);
    } catch (error) {
      setUniverseStatus({ text: `\u4fdd\u5b58\u5931\u8d25\uff1a${detailText(error)}`, error: true });
    } finally {
      setBusy(false);
    }
  }
  function stockDataPayload(mode: "today" | "range") {
    const payload: Row = { username, max_symbols: Number(maxSymbols || 0) || 0, sleep_seconds: Number(sleepSeconds || 0) || 0 };
    if (mode === "range") {
      const startDate = normalizeAdminDate(rangeStart);
      const endDate = normalizeAdminDate(rangeEnd);
      if (!startDate || !endDate) throw new Error(txt.dateInvalid);
      if (startDate > endDate) throw new Error(txt.dateOrderInvalid);
      payload.start_date = startDate;
      payload.end_date = endDate;
    }
    return payload;
  }

  function summarizeStockDataResult(data: Row, fallback: string) {
    const counts = [
      data.stock_count !== undefined ? `\u6267\u884c ${formatNumber(data.stock_count)} \u53ea` : "",
      data.success_count !== undefined ? `\u6210\u529f ${formatNumber(data.success_count)} \u53ea` : "",
      data.failed_count !== undefined ? `\u5931\u8d25 ${formatNumber(data.failed_count)} \u53ea` : ""
    ].filter(Boolean).join("\uff0c");
    return [
      String(data.message || fallback),
      data.start_date && data.end_date ? `\u533a\u95f4 ${data.start_date}-${data.end_date}` : "",
      counts,
      data.status ? `\u72b6\u6001 ${data.status}` : ""
    ].filter(Boolean).join("\uff1b");
  }

  async function runStockDataTask(endpoint: string, mode: "today" | "range", label: string) {
    const confirmText = `\u786e\u8ba4${label}\uff1f\u8be5\u64cd\u4f5c\u4f1a\u5199\u5165 SQLite \u4e3b\u5e93\u3002`;
    if (typeof window.confirm === "function" && !window.confirm(confirmText)) return;
    let payload: Row;
    try {
      payload = stockDataPayload(mode);
    } catch (error) {
      setStockDataStatus({ text: detailText(error), error: true });
      return;
    }
    setBusy(true);
    setStockDataStatus({ text: `\u6b63\u5728${label}\uff1b\u8bf7\u7b49\u5f85\u4efb\u52a1\u8fd4\u56de\u3002` });
    try {
      const data = await fetchJson<Row>(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      setStockDataStatus({ text: summarizeStockDataResult(data, `${label}\u5b8c\u6210\u3002`), error: data.status === "failed" });
      await Promise.all([loadOverview(false), loadSchedulerRuns(false)]);
    } catch (error) {
      setStockDataStatus({ text: `${label}\u5931\u8d25\uff1a${detailText(error)}`, error: true });
    } finally {
      setBusy(false);
    }
  }

  async function retrySchedulerRun(runId: string) {
    if (!runId) return;
    if (typeof window.confirm === "function" && !window.confirm(txt.confirmRetry)) return;
    setBusy(true);
    setRunStatus({ text: "\u6b63\u5728\u767b\u8bb0\u5b89\u5168\u91cd\u8dd1\u8bf7\u6c42..." });
    try {
      const data = await fetchJson<{ message?: string }>(`/api/admin/scheduler/runs/${encodeURIComponent(runId)}/retry`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason: "admin_dashboard" }) });
      setRunStatus({ text: data.message || "\u5df2\u767b\u8bb0\u5b89\u5168\u91cd\u8dd1\u8bf7\u6c42\uff1b\u672c\u63a5\u53e3\u4e0d\u76f4\u63a5\u6267\u884c\u4efb\u52a1\u3002\u5199\u5165\u4e86\u5f85\u91cd\u8dd1\u8bb0\u5f55\u3002" });
      await Promise.all([loadOverview(false), loadSchedulerRuns(false)]);
    } catch (error) {
      setRunStatus({ text: `\u767b\u8bb0\u91cd\u8dd1\u5931\u8d25\uff1a${detailText(error)}`, error: true });
    } finally {
      setBusy(false);
    }
  }

  if (authLoading) return <StatusOnly text={txt.checking} />;
  if (!isAdmin) return <StatusOnly text={txt.denied} error />;

  return (
    <section className="system-run-page">
      <div className="system-run-header">
        <div>
          <p className="page-eyebrow">{txt.eyebrow}</p>
          <h1>{txt.title}</h1>
          <p className="system-run-note">{txt.note}</p>
        </div>
        <div className="system-run-header-actions">
          <button className="secondary-link" type="button" disabled={busy} onClick={() => void loadOverview(true)}><RefreshCw size={14} />{txt.refreshOverview}</button>
          <button className="secondary-link" type="button" disabled={busy} onClick={() => void loadSchedulerRuns(true)}><RotateCcw size={14} />{txt.refreshRuns}</button>
          <button className="secondary-link" type="button" disabled={busy} onClick={() => void loadMainUniverse(true)}><RotateCcw size={14} />{txt.refreshUniverse}</button>
        </div>
      </div>

      <section className="system-run-summary">
        <div className="summary-intro"><p className="page-eyebrow">{txt.summaryEyebrow}</p><h2>{txt.summaryTitle}</h2><p>{txt.summaryNote}</p></div>
        <div className="metric-strip system-run-metrics">
          {summaryCards.map((card) => <div className="metric-tile" key={card.key}><span>{card.label}</span><strong>{card.value}</strong><small>{card.meta}</small></div>)}
        </div>
      </section>
      <StatusLine state={overviewStatus} />

      <section className="system-run-panel">
        <PanelHead eyebrow={txt.stockEyebrow} title={txt.stockTitle} note={txt.stockNote} />
        <div className="stock-data-grid">
          <div className="stock-task-card"><div><strong>{txt.todayTask}</strong><p>{txt.todayNote}</p></div><div className="inline-actions"><button className="primary-button" type="button" disabled={busy} onClick={() => void runStockDataTask("/api/admin/stock-data/daily/today", "today", txt.collectToday)}><Play size={14} />{txt.collectToday}</button><button className="secondary-link" type="button" disabled={busy} onClick={() => void runStockDataTask("/api/admin/stock-data/indicators/today", "today", txt.computeToday)}>{txt.computeToday}</button></div></div>
          <div className="stock-task-card"><div className="field-grid two"><Field label={txt.startDate} value={rangeStart} placeholder="20240101" onChange={setRangeStart} /><Field label={txt.endDate} value={rangeEnd} placeholder="20240131" onChange={setRangeEnd} /></div><div className="inline-actions"><button className="primary-button" type="button" disabled={busy} onClick={() => void runStockDataTask("/api/admin/stock-data/daily/range", "range", txt.collectRange)}><Play size={14} />{txt.collectRange}</button><button className="secondary-link" type="button" disabled={busy} onClick={() => void runStockDataTask("/api/admin/stock-data/indicators/range", "range", txt.computeRange)}>{txt.computeRange}</button></div></div>
          <div className="stock-task-card compact"><Field label={txt.maxSymbols} value={maxSymbols} type="number" onChange={setMaxSymbols} /><Field label={txt.sleepSeconds} value={sleepSeconds} type="number" step="0.1" onChange={setSleepSeconds} /></div>
        </div>
        <StatusLine state={stockDataStatus} />
      </section>
      <section className="system-run-panel">
        <PanelHead eyebrow={txt.universeEyebrow} title={txt.universeTitle} note={txt.universeNote} />
        <div className="universe-grid">
          <div className="universe-editor">
            <label><span>{txt.universeInput}</span><textarea rows={8} value={universeText} placeholder={txt.universePlaceholder} onChange={(event) => setUniverseText(event.target.value)} /></label>
            <div className="inline-actions wrap">
              <label className="check-field"><input type="checkbox" checked={includeInactive} onChange={(event) => { setIncludeInactive(event.target.checked); void loadMainUniverse(true, event.target.checked); }} /><span>{txt.includeInactive}</span></label>
              <select value={universeMode} onChange={(event) => setUniverseMode(event.target.value as "append" | "replace")}><option value="append">{txt.appendMode}</option><option value="replace">{txt.replaceMode}</option></select>
              <button className="secondary-link" type="button" disabled={busy} onClick={() => void resolveMainUniverse()}><Search size={14} />{txt.resolveNames}</button>
              <button className="primary-button" type="button" disabled={busy} onClick={() => void saveMainUniverse()}><Save size={14} />{txt.saveUniverse}</button>
            </div>
            <StatusLine state={universeStatus} />
          </div>
          <UniverseTable rows={universeRows} />
        </div>
        <p className="system-run-detail">{resolvedDetail}</p>
      </section>

      <section className="system-run-panel system-run-runs">
        <PanelHead eyebrow={txt.runsEyebrow} title={txt.runsTitle} note={txt.runsNote} />
        <SchedulerTable rows={runs} busy={busy} onRetry={(runId) => void retrySchedulerRun(runId)} />
        <StatusLine state={runStatus} />
      </section>
    </section>
  );
}

function StatusOnly({ text, error = false }: { text: string; error?: boolean }) {
  return <section className="system-run-page"><div className={error ? "system-run-denied error" : "system-run-denied"}><ShieldAlert size={18} /><span>{text}</span></div></section>;
}

function StatusLine({ state }: { state: StatusState }) {
  return <p className={state.error ? "system-run-status error" : "system-run-status"}>{state.text}</p>;
}

function PanelHead({ eyebrow, title, note }: { eyebrow: string; title: string; note: string }) {
  return <div className="panel-header system-run-panel-head"><div><p className="page-eyebrow">{eyebrow}</p><h2>{title}</h2></div><p>{note}</p></div>;
}

function Field({ label, value, onChange, type = "text", step, placeholder = "" }: { label: string; value: string; onChange: (value: string) => void; type?: string; step?: string; placeholder?: string }) {
  return <label><span>{label}</span><input type={type} step={step} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} /></label>;
}

function UniverseTable({ rows }: { rows: UniverseRow[] }) {
  return (
    <div className="table-wrap system-run-table-wrap">
      <table>
        <thead><tr><th>{"\u80a1\u7968\u4ee3\u7801"}</th><th>{"TS\u4ee3\u7801"}</th><th>{"\u80a1\u7968\u540d\u79f0"}</th><th>{"\u6765\u6e90"}</th><th>{"\u72b6\u6001"}</th><th>{"\u66f4\u65b0\u65f6\u95f4"}</th></tr></thead>
        <tbody>
          {rows.length ? rows.map((row, index) => <tr key={`${row.symbol || index}`}><td>{row.symbol || "-"}</td><td>{row.ts_code || "-"}</td><td>{row.name || row.stock_name || "-"}</td><td>{row.source || "-"}</td><td>{Number(row.is_active) === 1 || row.is_active === true ? "\u6d3b\u8dc3" : "\u505c\u7528"}</td><td>{row.updated_at || "-"}</td></tr>) : <tr><td colSpan={6}>{txt.noRows}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function SchedulerTable({ rows, busy, onRetry }: { rows: RunRow[]; busy: boolean; onRetry: (runId: string) => void }) {
  return (
    <div className="table-wrap system-run-table-wrap runs">
      <table>
        <thead><tr><th>{"\u8fd0\u884cID"}</th><th>{"\u4efb\u52a1"}</th><th>{"\u76ee\u6807\u65e5\u671f"}</th><th>{"\u72b6\u6001"}</th><th>{"\u5f00\u59cb\u65f6\u95f4"}</th><th>{"\u7ed3\u675f\u65f6\u95f4"}</th><th>{"\u5931\u8d25\u9636\u6bb5"}</th><th>{"\u9519\u8bef\u6458\u8981"}</th><th>{"\u65e5\u5fd7"}</th><th>{"\u5b89\u5168\u91cd\u8dd1"}</th></tr></thead>
        <tbody>
          {rows.length ? rows.map((row, index) => <tr key={row.run_id || index}><td title={row.run_id || ""}>{shortId(row.run_id)}</td><td>{formatJobName(row.job_name)}</td><td>{row.target_date || "-"}</td><td>{formatStatus(row.status)}</td><td>{row.started_at || "-"}</td><td>{row.finished_at || "-"}</td><td>{row.failed_stage || "-"}</td><td title={row.error_summary || ""}>{row.error_summary || "-"}</td><td title={row.log_file || ""}>{row.log_file || "-"}</td><td>{canRetry(row) ? <button className="secondary-link small-action" type="button" disabled={busy} onClick={() => onRetry(row.run_id || "")}>{txt.retry}</button> : <span className="muted-cell">-</span>}</td></tr>) : <tr><td colSpan={10}>{txt.noRows}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
