import { useEffect, useMemo, useState } from "react";
import { Copy, ExternalLink, FilePlus2, RefreshCw, Save, Trash2 } from "lucide-react";
import { formatHeader, formatValue } from "../backtests/format";
import "./paperTemplates.css";

type CurrentUser = { username?: string; role?: string; display_name?: string };
type PaperTemplate = Record<string, unknown>;
type PaperTemplateListItem = { account_id?: string; account_name?: string; error?: string | boolean };
type StockPoolTemplate = { template_name?: string; stock_count?: number };

type FormState = {
  file_name: string;
  account_id: string;
  account_name: string;
  initial_cash: string;
  stock_pool_template_name: string;
  stock_pool_db_path: string;
  buy_condition: string;
  sell_condition: string;
  score_expression: string;
  top_n: string;
  entry_offset: string;
  min_hold_days: string;
  max_hold_days: string;
  buy_quantity_mode: string;
  buy_shares: string;
  buy_lot_size: string;
  min_buy_amount: string;
  buy_min_close: string;
  buy_max_close: string;
  price_primary: string;
  price_fallback: string;
  price_field: string;
  buy_fee_rate: string;
  sell_fee_rate: string;
  stamp_tax_sell: string;
  slippage_bps: string;
  min_commission: string;
  ledger_path: string;
  log_dir: string;
  skip_if_holding: boolean;
  skip_if_pending_order: boolean;
  strict_execution: boolean;
};

const t = {
  title: "\u6a21\u62df\u8d26\u6237\u6a21\u677f",
  eyebrow: "Account Template",
  note: "\u6a21\u677f\u548c\u8d26\u672c\u7edf\u4e00\u4fdd\u5b58\u5728 SQLite\uff0c\u4fdd\u5b58\u6a21\u677f\u4e0d\u4f1a\u6267\u884c\u4ea4\u6613\u6216\u4fee\u6539\u8d26\u672c\u3002",
  paper: "\u591a\u8d26\u6237\u6a21\u62df",
  stockPools: "\u80a1\u7968\u6c60\u6a21\u677f",
  selectTemplate: "\u9009\u62e9\u6a21\u677f",
  reload: "\u5237\u65b0\u6a21\u677f",
  load: "\u8f7d\u5165\u6a21\u677f",
  create: "\u65b0\u5efa\u6a21\u677f",
  copy: "\u590d\u5236\u6a21\u677f",
  save: "\u4fdd\u5b58\u6a21\u677f",
  saveAs: "\u53e6\u5b58\u4e3a\u65b0\u6a21\u677f",
  delete: "\u5220\u9664\u6a21\u677f",
  summaryEyebrow: "\u6a21\u677f\u6458\u8981",
  summaryTitle: "\u5f53\u524d\u6a21\u677f\u4fe1\u606f",
  basic: "\u8d26\u6237\u57fa\u672c\u4fe1\u606f",
  strategy: "\u7b56\u7565\u6761\u4ef6",
  execution: "\u6267\u884c\u4e0e\u8d39\u7528",
  safeguards: "\u98ce\u63a7\u5f00\u5173",
  accountId: "\u8d26\u6237\u7f16\u53f7",
  accountName: "\u8d26\u6237\u540d\u79f0",
  initialCash: "\u521d\u59cb\u8d44\u91d1",
  stockPoolUser: "\u80a1\u7968\u6c60\u7528\u6237",
  stockPoolTemplate: "\u80a1\u7968\u6c60\u6a21\u677f",
  topN: "\u4e70\u5165\u6392\u540d\u6570\u91cf",
  entryOffset: "\u4e70\u5165\u504f\u79fb",
  minHoldDays: "\u6700\u77ed\u6301\u6709\u5929\u6570",
  maxHoldDays: "\u6700\u5927\u6301\u6709\u5929\u6570",
  buyQuantityMode: "\u4e70\u5165\u65b9\u5f0f",
  buyShares: "\u57fa\u7840\u80a1\u6570",
  buyLotSize: "\u6bcf\u624b\u80a1\u6570",
  minBuyAmount: "\u6700\u4f4e\u4e70\u5165\u91d1\u989d",
  buyMinClose: "\u6700\u4f4e\u6536\u76d8\u4ef7",
  buyMaxClose: "\u6700\u9ad8\u6536\u76d8\u4ef7",
  pricePrimary: "\u9996\u9009\u884c\u60c5\u6e90",
  priceFallback: "\u5907\u7528\u884c\u60c5\u6e90",
  priceField: "\u4ef7\u683c\u5b57\u6bb5",
  buyFeeRate: "\u4e70\u5165\u8d39\u7387",
  sellFeeRate: "\u5356\u51fa\u8d39\u7387",
  stampTaxSell: "\u5370\u82b1\u7a0e",
  slippageBps: "\u6ed1\u70b9 bps",
  minCommission: "\u6700\u4f4e\u4f63\u91d1",
  buyCondition: "\u4e70\u5165\u6761\u4ef6",
  sellCondition: "\u5356\u51fa\u6761\u4ef6",
  scoreExpression: "\u8bc4\u5206\u8868\u8fbe\u5f0f",
  skipIfHolding: "\u6301\u4ed3\u65f6\u4e0d\u91cd\u590d\u4e70\u5165",
  skipIfPendingOrder: "\u6709\u5f85\u6210\u4ea4\u8ba2\u5355\u65f6\u4e0d\u91cd\u590d\u4e70\u5165",
  strictExecution: "\u4e25\u683c\u6210\u4ea4",
  ledgerNote: "\u8d26\u672c\u548c\u8fd0\u884c\u65e5\u5fd7\u7531\u7cfb\u7edf\u6309\u5f53\u524d\u7528\u6237\u548c\u8d26\u6237\u7f16\u53f7\u5199\u5165 SQLite\uff0c\u4e0d\u9700\u8981\u624b\u52a8\u586b\u8def\u5f84\u3002",
  loadingTemplates: "\u6b63\u5728\u5237\u65b0\u6a21\u677f\u5217\u8868...",
  loadingTemplate: "\u6b63\u5728\u8f7d\u5165\u6a21\u677f...",
  loadingSave: "\u6b63\u5728\u4fdd\u5b58\u6a21\u677f...",
  loadingSaveAs: "\u6b63\u5728\u53e6\u5b58\u4e3a\u65b0\u6a21\u677f...",
  loadingDelete: "\u6b63\u5728\u5220\u9664\u6a21\u677f...",
  noTemplates: "\u6ca1\u6709\u627e\u5230\u6a21\u677f\uff0c\u53ef\u4ee5\u5148\u586b\u5199\u65b0\u6a21\u677f\u540e\u4fdd\u5b58\u3002",
  newDraft: "\u5df2\u521d\u59cb\u5316\u65b0\u6a21\u677f\u3002\u4fdd\u5b58\u524d\u8bf7\u786e\u8ba4\u8d26\u6237\u7f16\u53f7\u548c\u8d26\u6237\u540d\u79f0\u4e0d\u4f1a\u4e0e\u65e7\u6a21\u677f\u51b2\u7a81\u3002",
  copiedDraft: "\u5df2\u590d\u5236\u5f53\u524d\u6a21\u677f\u4e3a\u65b0\u8349\u7a3f\u3002\u4fdd\u5b58\u524d\u4e0d\u4f1a\u5199\u5165 SQLite\u3002",
  confirmDelete: "\u53ea\u505c\u7528\u5f53\u524d SQLite \u6a21\u677f\uff0c\u4e0d\u5220\u9664 SQLite \u8d26\u672c\u8bb0\u5f55\u3002\u786e\u8ba4\u5220\u9664\u5f53\u524d\u6a21\u677f\u5417\uff1f",
  noDeleteTarget: "\u8bf7\u5148\u9009\u62e9\u8981\u5220\u9664\u7684\u6a21\u677f\u3002",
  failedTemplates: "\u8bfb\u53d6\u6a21\u677f\u5931\u8d25",
  failedPoolTemplates: "\u8bfb\u53d6\u80a1\u7968\u6c60\u6a21\u677f\u5931\u8d25",
  failedLoad: "\u8bfb\u53d6\u6a21\u677f\u5931\u8d25",
  failedSave: "\u4fdd\u5b58\u5931\u8d25",
  failedDelete: "\u5220\u9664\u5931\u8d25",
  fallbackUser: "admin"
};

const defaultConfigDir = "configs/paper_accounts";
const defaultStockPoolDbPath = "data_store/stock_pool_templates.sqlite";

const defaultForm = (): FormState => {
  const suffix = chinaDateStamp();
  return {
    file_name: `new_paper_account_${suffix}`,
    account_id: `\u65b0\u8d26\u6237_${suffix}`,
    account_name: `\u65b0\u6a21\u62df\u8d26\u6237_${suffix}`,
    initial_cash: "100000",
    stock_pool_template_name: "\u5f53\u524d\u591a\u8d26\u6237\u6a21\u62df\u80a1\u7968\u6c60",
    stock_pool_db_path: defaultStockPoolDbPath,
    buy_condition: "m20>0",
    sell_condition: "",
    score_expression: "m20",
    top_n: "5",
    entry_offset: "1",
    min_hold_days: "0",
    max_hold_days: "15",
    buy_quantity_mode: "\u56fa\u5b9a\u80a1\u6570",
    buy_shares: "200",
    buy_lot_size: "100",
    min_buy_amount: "10000",
    buy_min_close: "0",
    buy_max_close: "150",
    price_primary: "\u4e1c\u65b9\u8d22\u5bcc",
    price_fallback: "\u817e\u8baf\u80a1\u7968",
    price_field: "\u5f00\u76d8\u4ef7",
    buy_fee_rate: "0.00003",
    sell_fee_rate: "0.00003",
    stamp_tax_sell: "0",
    slippage_bps: "3",
    min_commission: "0",
    ledger_path: "data_store/paper_trading.sqlite",
    log_dir: "SQLite\u8fd0\u884c\u65e5\u5fd7",
    skip_if_holding: true,
    skip_if_pending_order: true,
    strict_execution: true
  };
};

const summaryKeys = ["account_id", "account_name", "stock_pool_template_name", "top_n", "ledger_storage", "ledger_exists", "price_primary", "price_field"];

function chinaDateStamp(date = new Date()): string {
  const parts = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(date);
  const value = (type: string) => parts.find((part) => part.type === type)?.value || "";
  const stamp = `${value("year")}${value("month")}${value("day")}`;
  return /^\d{8}$/.test(stamp) ? stamp : String(Date.now()).slice(0, 8);
}

function chinaDateTimeStamp(date = new Date()): string {
  const parts = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).formatToParts(date);
  const value = (type: string) => parts.find((part) => part.type === type)?.value || "";
  const stamp = `${value("year")}${value("month")}${value("day")}${value("hour")}${value("minute")}${value("second")}`;
  return /^\d{14}$/.test(stamp) ? stamp : String(Date.now());
}

function sanitizeTemplatePart(value: unknown, fallback = "template"): string {
  const text = String(value || fallback).trim().replace(/\.(ya?ml)$/i, "").replace(/[\\/:*?"<>|\s]+/g, "_").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
  return text || fallback;
}

function numberValue(value: string, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function intValue(value: string, fallback = 0): number {
  return Math.round(numberValue(value, fallback));
}

async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { credentials: "include", ...options });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function formFromTemplate(data: PaperTemplate = {}): FormState {
  const base = defaultForm();
  return {
    file_name: String(data.file_name ?? base.file_name),
    account_id: String(data.account_id ?? base.account_id),
    account_name: String(data.account_name ?? base.account_name),
    initial_cash: String(data.initial_cash ?? base.initial_cash),
    stock_pool_template_name: String(data.stock_pool_template_name ?? base.stock_pool_template_name),
    stock_pool_db_path: String(data.stock_pool_db_path ?? base.stock_pool_db_path),
    buy_condition: String(data.buy_condition ?? base.buy_condition),
    sell_condition: String(data.sell_condition ?? base.sell_condition),
    score_expression: String(data.score_expression ?? base.score_expression),
    top_n: String(data.top_n ?? base.top_n),
    entry_offset: String(data.entry_offset ?? base.entry_offset),
    min_hold_days: String(data.min_hold_days ?? base.min_hold_days),
    max_hold_days: String(data.max_hold_days ?? base.max_hold_days),
    buy_quantity_mode: String(data.buy_quantity_mode ?? base.buy_quantity_mode),
    buy_shares: String(data.buy_shares ?? base.buy_shares),
    buy_lot_size: String(data.buy_lot_size ?? base.buy_lot_size),
    min_buy_amount: String(data.min_buy_amount ?? base.min_buy_amount),
    buy_min_close: String(data.buy_min_close ?? base.buy_min_close),
    buy_max_close: String(data.buy_max_close ?? base.buy_max_close),
    price_primary: String(data.price_primary ?? base.price_primary),
    price_fallback: String(data.price_fallback ?? base.price_fallback),
    price_field: String(data.price_field ?? base.price_field),
    buy_fee_rate: String(data.buy_fee_rate ?? base.buy_fee_rate),
    sell_fee_rate: String(data.sell_fee_rate ?? base.sell_fee_rate),
    stamp_tax_sell: String(data.stamp_tax_sell ?? base.stamp_tax_sell),
    slippage_bps: String(data.slippage_bps ?? base.slippage_bps),
    min_commission: String(data.min_commission ?? base.min_commission),
    ledger_path: String(data.ledger_path ?? base.ledger_path),
    log_dir: String(data.log_dir ?? base.log_dir),
    skip_if_holding: Boolean(data.skip_if_holding ?? base.skip_if_holding),
    skip_if_pending_order: Boolean(data.skip_if_pending_order ?? base.skip_if_pending_order),
    strict_execution: Boolean(data.strict_execution ?? base.strict_execution)
  };
}

function buildPayload(form: FormState, username: string, overwriteExisting: boolean) {
  return {
    username,
    config_dir: defaultConfigDir,
    config_path: "",
    file_name: form.file_name.trim(),
    overwrite_existing: overwriteExisting,
    account_id: form.account_id.trim(),
    account_name: form.account_name.trim(),
    initial_cash: numberValue(form.initial_cash, 100000),
    stock_pool_username: username,
    stock_pool_template_name: form.stock_pool_template_name.trim(),
    stock_pool_db_path: form.stock_pool_db_path.trim() || defaultStockPoolDbPath,
    buy_condition: form.buy_condition.trim(),
    sell_condition: form.sell_condition.trim(),
    score_expression: form.score_expression.trim(),
    top_n: intValue(form.top_n, 5),
    entry_offset: intValue(form.entry_offset, 1),
    min_hold_days: intValue(form.min_hold_days, 0),
    max_hold_days: intValue(form.max_hold_days, 15),
    buy_quantity_mode: form.buy_quantity_mode.trim() || "\u56fa\u5b9a\u80a1\u6570",
    buy_shares: intValue(form.buy_shares, 200),
    buy_lot_size: intValue(form.buy_lot_size, 100),
    min_buy_amount: numberValue(form.min_buy_amount, 10000),
    buy_min_close: numberValue(form.buy_min_close, 0),
    buy_max_close: numberValue(form.buy_max_close, 150),
    price_primary: form.price_primary.trim() || "\u4e1c\u65b9\u8d22\u5bcc",
    price_fallback: form.price_fallback.trim(),
    price_field: form.price_field || "\u5f00\u76d8\u4ef7",
    skip_if_holding: form.skip_if_holding,
    skip_if_pending_order: form.skip_if_pending_order,
    strict_execution: form.strict_execution,
    buy_fee_rate: numberValue(form.buy_fee_rate, 0.00003),
    sell_fee_rate: numberValue(form.sell_fee_rate, 0.00003),
    stamp_tax_sell: numberValue(form.stamp_tax_sell, 0),
    slippage_bps: numberValue(form.slippage_bps, 3),
    min_commission: numberValue(form.min_commission, 0),
    ledger_path: "",
    log_dir: ""
  };
}

function templateLabel(item: PaperTemplateListItem): string {
  if (item.error) return `${item.account_id || "-"}\uff1a\u8bfb\u53d6\u5931\u8d25`;
  return `${item.account_name || item.account_id || "-"}\uff08${item.account_id || "-"}\uff09`;
}

function summaryValue(key: string, value: unknown): string {
  if (key === "ledger_exists") return value ? "\u5df2\u5b58\u5728" : "\u672a\u521b\u5efa";
  return formatValue(key, value);
}

function firstPoolName(pools: StockPoolTemplate[]): string {
  return pools.find((item) => item.template_name)?.template_name || "";
}

function withStockPoolFallback(form: FormState, pools: StockPoolTemplate[]): FormState {
  const fallback = firstPoolName(pools);
  if (!fallback) return form;
  return pools.some((item) => item.template_name === form.stock_pool_template_name) ? form : { ...form, stock_pool_template_name: fallback };
}

export function PaperTemplatesPage() {
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [templates, setTemplates] = useState<PaperTemplateListItem[]>([]);
  const [stockPools, setStockPools] = useState<StockPoolTemplate[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [form, setForm] = useState<FormState>(defaultForm());
  const [currentTemplate, setCurrentTemplate] = useState<PaperTemplate>({ ...defaultForm(), ledger_storage: "SQLite", ledger_exists: false });
  const [status, setStatus] = useState(t.loadingTemplates);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState<"templates" | "load" | "save" | "saveAs" | "delete" | "">("");
  const username = currentUser?.username || t.fallbackUser;
  const summary = useMemo<Record<string, unknown>>(() => ({ ...currentTemplate, ...buildPayload(form, username, Boolean(selectedAccountId)), ledger_storage: currentTemplate.ledger_storage || "SQLite", ledger_exists: Boolean(currentTemplate.ledger_exists) }), [currentTemplate, form, selectedAccountId, username]);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function showError(prefix: string, err: unknown) {
    setError(true);
    setStatus(`${prefix}\uff1a${err instanceof Error ? err.message : String(err)}`);
  }

  function applyTemplate(data: PaperTemplate) {
    setCurrentTemplate(data);
    setForm(formFromTemplate(data));
  }

  async function loadStockPoolTemplates(targetUsername = username, selectedName = form.stock_pool_template_name) {
    try {
      const data = await fetchJson<{ templates: StockPoolTemplate[] }>(`/api/stock-pools/templates?username=${encodeURIComponent(targetUsername || t.fallbackUser)}`);
      const pools = data.templates || [];
      setStockPools(pools);
      if (pools.length) {
        setForm((current) => withStockPoolFallback(current, pools));
      }
    } catch (err) {
      showError(t.failedPoolTemplates, err);
    }
  }

  async function loadCurrentTemplate(showStatus = true, accountId = selectedAccountId, targetUsername = username) {
    if (!accountId) {
      const blank = { ...defaultForm(), ledger_storage: "SQLite", ledger_exists: false };
      applyTemplate(blank);
      setStatus(t.noTemplates);
      return;
    }
    if (showStatus) {
      setLoading("load");
      setError(false);
      setStatus(t.loadingTemplate);
    }
    try {
      const params = new URLSearchParams({ account_id: accountId, username: targetUsername || t.fallbackUser, config_dir: defaultConfigDir });
      const data = await fetchJson<PaperTemplate>(`/api/paper/template?${params.toString()}`);
      setSelectedAccountId(String(data.account_id || accountId));
      applyTemplate(data);
      await loadStockPoolTemplates(targetUsername, String(data.stock_pool_template_name || ""));
      setError(false);
      setStatus(`\u6a21\u677f\u5df2\u8f7d\u5165\uff1a${data.account_name || "-"}\uff08${data.account_id || accountId}\uff09\uff1bSQLite \u8d26\u672c${data.ledger_exists ? "\u5df2\u6709\u8bb0\u5f55" : "\u5c1a\u672a\u521b\u5efa"}\u3002`);
    } catch (err) {
      showError(t.failedLoad, err);
    } finally {
      if (showStatus) setLoading("");
    }
  }

  async function loadTemplates(showStatus = false, targetUsername = username) {
    if (showStatus) {
      setLoading("templates");
      setError(false);
      setStatus(t.loadingTemplates);
    }
    try {
      const data = await fetchJson<{ templates: PaperTemplateListItem[] }>(`/api/paper/templates?config_dir=${encodeURIComponent(defaultConfigDir)}&username=${encodeURIComponent(targetUsername || t.fallbackUser)}`);
      const nextTemplates = data.templates || [];
      setTemplates(nextTemplates);
      await loadStockPoolTemplates(targetUsername);
      if (!nextTemplates.length) {
        setSelectedAccountId("");
        applyTemplate({ ...defaultForm(), ledger_storage: "SQLite", ledger_exists: false });
        setStatus(t.noTemplates);
        return;
      }
      const nextId = selectedAccountId && nextTemplates.some((item) => item.account_id === selectedAccountId) ? selectedAccountId : nextTemplates[0]?.account_id || "";
      setSelectedAccountId(nextId);
      await loadCurrentTemplate(false, nextId, targetUsername);
      setError(false);
      setStatus(`\u5df2\u8bfb\u53d6 ${nextTemplates.length} \u4e2a\u6a21\u62df\u8d26\u6237\u6a21\u677f\u3002`);
    } catch (err) {
      showError(t.failedTemplates, err);
    } finally {
      if (showStatus) setLoading("");
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
      showError(t.failedTemplates, err);
    });
    return () => { cancelled = true; };
  }, []);

  function newDraft() {
    const draft = withStockPoolFallback(defaultForm(), stockPools);
    setSelectedAccountId("");
    setCurrentTemplate({ ...draft, ledger_storage: "SQLite", ledger_exists: false });
    setForm(draft);
    setError(false);
    setStatus(t.newDraft);
  }

  function copyDraft() {
    const stamp = chinaDateTimeStamp();
    const baseAccountId = sanitizeTemplatePart(form.account_id || form.file_name, "paper_account");
    const next = {
      ...withStockPoolFallback(form, stockPools),
      file_name: `${sanitizeTemplatePart(form.file_name || baseAccountId, baseAccountId)}_${stamp}_copy`,
      account_id: `${baseAccountId}_${stamp}_copy`,
      account_name: `${form.account_name || "\u6a21\u62df\u8d26\u6237"}_\u526f\u672c_${stamp}`,
      ledger_path: "data_store/paper_trading.sqlite",
      log_dir: "SQLite\u8fd0\u884c\u65e5\u5fd7"
    };
    setSelectedAccountId("");
    setCurrentTemplate({ ...next, ledger_storage: "SQLite", ledger_exists: false });
    setForm(next);
    setError(false);
    setStatus(t.copiedDraft);
  }

  async function saveTemplate(overwriteExisting: boolean) {
    const mode = overwriteExisting && Boolean(selectedAccountId) ? "save" : "saveAs";
    setLoading(mode);
    setError(false);
    setStatus(mode === "save" ? t.loadingSave : t.loadingSaveAs);
    try {
      const payload = buildPayload(form, username, mode === "save");
      const data = await fetchJson<{ message?: string; template: PaperTemplate }>("/api/paper/template", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const savedAccountId = String(data.template.account_id || payload.account_id);
      setSelectedAccountId(savedAccountId);
      await loadTemplates(false, username);
      applyTemplate(data.template);
      setStatus(data.message || "\u6a21\u677f\u5df2\u4fdd\u5b58\u5230 SQLite\uff1b\u8d26\u672c\u672a\u88ab\u4fee\u6539\u3002");
    } catch (err) {
      showError(t.failedSave, err);
    } finally {
      setLoading("");
    }
  }

  async function deleteTemplate() {
    if (!selectedAccountId) {
      setError(true);
      setStatus(t.noDeleteTarget);
      return;
    }
    if (typeof window !== "undefined" && typeof window.confirm === "function" && !window.confirm(t.confirmDelete)) return;
    setLoading("delete");
    setError(false);
    setStatus(t.loadingDelete);
    try {
      const params = new URLSearchParams({ account_id: selectedAccountId, username, config_dir: defaultConfigDir });
      const data = await fetchJson<{ message?: string }>(`/api/paper/template?${params.toString()}`, { method: "DELETE" });
      setSelectedAccountId("");
      await loadTemplates(false, username);
      setStatus(data.message || "\u6a21\u677f\u5df2\u5220\u9664\uff1bSQLite \u8d26\u672c\u4fdd\u7559\u4e0d\u52a8\u3002");
    } catch (err) {
      showError(t.failedDelete, err);
    } finally {
      setLoading("");
    }
  }

  const disabled = Boolean(loading);

  return (
    <section className="paper-templates-page">
      <div className="paper-templates-header">
        <div>
          <p className="page-eyebrow">{t.eyebrow}</p>
          <h1>{t.title}</h1>
          <p className="paper-templates-note">{t.note}</p>
        </div>
        <div className="paper-templates-header-actions">
          <a className="secondary-link" href="/trading/paper"><ExternalLink size={14} />{t.paper}</a>
          <a className="secondary-link" href="/portfolio/stock-pools"><ExternalLink size={14} />{t.stockPools}</a>
        </div>
      </div>

      <div className="paper-templates-runbar">
        <label><span>{t.selectTemplate}</span><select value={selectedAccountId} onChange={(event) => { setSelectedAccountId(event.target.value); void loadCurrentTemplate(false, event.target.value, username); }}>{templates.length ? templates.map((item) => <option key={item.account_id || ""} value={item.account_id || ""}>{templateLabel(item)}</option>) : <option value="">-</option>}</select></label>
        <button className="secondary-link" type="button" disabled={disabled} onClick={() => void loadTemplates(true, username)}><RefreshCw size={14} />{t.reload}</button>
        <button className="secondary-link" type="button" disabled={disabled} onClick={() => void loadCurrentTemplate(true)}><RefreshCw size={14} />{t.load}</button>
        <button className="secondary-link" type="button" disabled={disabled} onClick={newDraft}><FilePlus2 size={14} />{t.create}</button>
        <button className="secondary-link" type="button" disabled={disabled} onClick={copyDraft}><Copy size={14} />{t.copy}</button>
        <button className="primary-button" type="button" disabled={disabled} onClick={() => void saveTemplate(true)}><Save size={14} />{loading === "save" ? t.loadingSave : t.save}</button>
        <button className="secondary-link" type="button" disabled={disabled} onClick={() => void saveTemplate(false)}><Save size={14} />{loading === "saveAs" ? t.loadingSaveAs : t.saveAs}</button>
        <button className="danger-button" type="button" disabled={disabled} onClick={() => void deleteTemplate()}><Trash2 size={14} />{loading === "delete" ? t.loadingDelete : t.delete}</button>
      </div>

      <p className={error ? "paper-templates-status error" : "paper-templates-status"}>{status}</p>

      <section className="paper-templates-summary">
        <div className="summary-intro">
          <p className="page-eyebrow">{t.summaryEyebrow}</p>
          <h2>{t.summaryTitle}</h2>
        </div>
        <div className="metric-strip paper-templates-metrics">
          {summaryKeys.map((key) => <div className="metric-tile" key={key}><span>{formatHeader(key)}</span><strong>{summaryValue(key, summary[key])}</strong></div>)}
        </div>
      </section>

      <section className="paper-template-panel">
        <div className="panel-header"><div><p className="page-eyebrow">Basic</p><h2>{t.basic}</h2></div><p>{t.ledgerNote}</p></div>
        <div className="paper-template-grid">
          <Field label={t.accountId} value={form.account_id} onChange={(value) => update("account_id", value)} />
          <Field label={t.accountName} value={form.account_name} onChange={(value) => update("account_name", value)} />
          <Field label={t.initialCash} value={form.initial_cash} type="number" onChange={(value) => update("initial_cash", value)} />
          <label><span>{t.stockPoolUser}</span><input value={username} readOnly /></label>
          <label className="wide"><span>{t.stockPoolTemplate}</span><select value={form.stock_pool_template_name} onChange={(event) => update("stock_pool_template_name", event.target.value)}>{stockPools.length ? stockPools.map((item) => <option key={item.template_name || ""} value={item.template_name || ""}>{item.template_name || "-"} ({item.stock_count || 0})</option>) : <option value={form.stock_pool_template_name}>{form.stock_pool_template_name || "-"}</option>}</select></label>
        </div>
      </section>

      <section className="paper-template-panel">
        <div className="panel-header"><div><p className="page-eyebrow">Strategy</p><h2>{t.strategy}</h2></div></div>
        <div className="paper-template-grid strategy-grid">
          <TextArea label={t.buyCondition} value={form.buy_condition} onChange={(value) => update("buy_condition", value)} />
          <TextArea label={t.sellCondition} value={form.sell_condition} onChange={(value) => update("sell_condition", value)} />
          <TextArea label={t.scoreExpression} value={form.score_expression} onChange={(value) => update("score_expression", value)} />
        </div>
      </section>

      <section className="paper-template-panel">
        <div className="panel-header"><div><p className="page-eyebrow">Execution</p><h2>{t.execution}</h2></div></div>
        <div className="paper-template-grid">
          <Field label={t.topN} value={form.top_n} type="number" onChange={(value) => update("top_n", value)} />
          <Field label={t.entryOffset} value={form.entry_offset} type="number" onChange={(value) => update("entry_offset", value)} />
          <Field label={t.minHoldDays} value={form.min_hold_days} type="number" onChange={(value) => update("min_hold_days", value)} />
          <Field label={t.maxHoldDays} value={form.max_hold_days} type="number" onChange={(value) => update("max_hold_days", value)} />
          <Field label={t.buyQuantityMode} value={form.buy_quantity_mode} onChange={(value) => update("buy_quantity_mode", value)} />
          <Field label={t.buyShares} value={form.buy_shares} type="number" onChange={(value) => update("buy_shares", value)} />
          <Field label={t.buyLotSize} value={form.buy_lot_size} type="number" onChange={(value) => update("buy_lot_size", value)} />
          <Field label={t.minBuyAmount} value={form.min_buy_amount} type="number" onChange={(value) => update("min_buy_amount", value)} />
          <Field label={t.buyMinClose} value={form.buy_min_close} type="number" step="0.01" onChange={(value) => update("buy_min_close", value)} />
          <Field label={t.buyMaxClose} value={form.buy_max_close} type="number" step="0.01" onChange={(value) => update("buy_max_close", value)} />
          <Field label={t.pricePrimary} value={form.price_primary} onChange={(value) => update("price_primary", value)} />
          <Field label={t.priceFallback} value={form.price_fallback} onChange={(value) => update("price_fallback", value)} />
          <label><span>{t.priceField}</span><select value={form.price_field} onChange={(event) => update("price_field", event.target.value)}><option value="\u5f00\u76d8\u4ef7">\u5f00\u76d8\u4ef7</option><option value="\u6536\u76d8\u4ef7">\u6536\u76d8\u4ef7</option></select></label>
          <Field label={t.buyFeeRate} value={form.buy_fee_rate} type="number" step="0.00001" onChange={(value) => update("buy_fee_rate", value)} />
          <Field label={t.sellFeeRate} value={form.sell_fee_rate} type="number" step="0.00001" onChange={(value) => update("sell_fee_rate", value)} />
          <Field label={t.stampTaxSell} value={form.stamp_tax_sell} type="number" step="0.0001" onChange={(value) => update("stamp_tax_sell", value)} />
          <Field label={t.slippageBps} value={form.slippage_bps} type="number" step="0.1" onChange={(value) => update("slippage_bps", value)} />
          <Field label={t.minCommission} value={form.min_commission} type="number" step="0.01" onChange={(value) => update("min_commission", value)} />
        </div>
      </section>

      <section className="paper-template-panel safeguards-panel">
        <div className="panel-header"><div><p className="page-eyebrow">Safeguards</p><h2>{t.safeguards}</h2></div></div>
        <div className="check-row">
          <CheckField label={t.skipIfHolding} checked={form.skip_if_holding} onChange={(value) => update("skip_if_holding", value)} />
          <CheckField label={t.skipIfPendingOrder} checked={form.skip_if_pending_order} onChange={(value) => update("skip_if_pending_order", value)} />
          <CheckField label={t.strictExecution} checked={form.strict_execution} onChange={(value) => update("strict_execution", value)} />
        </div>
      </section>
    </section>
  );
}

function Field({ label, value, onChange, type = "text", step }: { label: string; value: string; onChange: (value: string) => void; type?: string; step?: string }) {
  return <label><span>{label}</span><input type={type} step={step} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function TextArea({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label><span>{label}</span><textarea rows={4} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function CheckField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <label className="template-check"><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /><span>{label}</span></label>;
}
