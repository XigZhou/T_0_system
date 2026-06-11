import { useEffect, useMemo, useState } from "react";
import { Copy, ExternalLink, FilePlus2, RefreshCw, Save, SearchCheck, Trash2, Wand2 } from "lucide-react";
import { formatHeader, formatValue } from "../backtests/format";
import "./stockPools.css";

type CurrentUser = { username?: string; role?: string; display_name?: string };
type StockRow = Record<string, unknown>;

type StockPoolTemplate = {
  username?: string;
  template_name?: string;
  original_template_name?: string;
  description?: string;
  is_active?: boolean;
  stock_count?: number;
  updated_at?: string;
  db_path?: string;
  stock_text?: string;
  stocks?: StockRow[];
};

type ValidationResult = {
  valid_stocks?: StockRow[];
  valid_count?: number;
  duplicate_count?: number;
  invalid_count?: number;
  invalid_items?: string[];
  duplicate_symbols?: string[];
};

type FormState = {
  template_name: string;
  original_template_name: string;
  description: string;
  stock_text: string;
};

const t = {
  title: "\u80a1\u7968\u6c60\u6a21\u677f\u7ba1\u7406",
  eyebrow: "Stock Pool Workbench",
  note: "\u6a21\u677f\u53ea\u4fdd\u5b58\u80a1\u7968\u96c6\u5408\uff0c\u884c\u60c5\u4e0e\u6307\u6807\u7531\u4e3b\u884c\u60c5\u5e93\u548c\u7edf\u4e00\u8c03\u5ea6\u7ef4\u62a4\u3002",
  dailyPlan: "\u6bcf\u65e5\u6536\u76d8\u9009\u80a1",
  paper: "\u591a\u8d26\u6237\u6a21\u62df",
  selectTemplate: "\u9009\u62e9\u6a21\u677f",
  reload: "\u5237\u65b0\u6a21\u677f",
  load: "\u8f7d\u5165\u6a21\u677f",
  create: "\u65b0\u5efa\u6a21\u677f",
  copy: "\u590d\u5236\u6a21\u677f",
  save: "\u4fdd\u5b58\u6a21\u677f",
  delete: "\u5220\u9664\u6a21\u677f",
  validate: "\u6821\u9a8c\u80a1\u7968\u5217\u8868",
  seed: "\u521d\u59cb\u5316\u57fa\u7840\u6a21\u677f",
  summaryEyebrow: "\u6a21\u677f\u6458\u8981",
  summaryTitle: "\u5f53\u524d\u80a1\u7968\u6c60\u4fe1\u606f",
  editorEyebrow: "\u6a21\u677f\u5b57\u6bb5",
  editorTitle: "\u7f16\u8f91\u80a1\u7968\u6c60\u6a21\u677f",
  editorNote: "\u80a1\u7968\u5217\u8868\u53ef\u4ee5\u4e00\u884c\u4e00\u4e2a\uff0c\u4e5f\u53ef\u7528\u7a7a\u683c\u3001\u9017\u53f7\u6216\u5206\u53f7\u5206\u9694\u3002\u91cd\u590d\u9879\u4f1a\u81ea\u52a8\u5ffd\u7565\u3002",
  templateName: "\u6a21\u677f\u540d\u79f0",
  templateNameHint: "\u4f8b\u5982 L2_\u4e2d\u7b49\u5e02\u503c\u4e3b\u9898\u80a1\u5c42",
  originalTemplateName: "\u539f\u6a21\u677f\u540d\u79f0",
  description: "\u6a21\u677f\u8bf4\u660e",
  stockText: "\u624b\u5de5\u80a1\u7968\u5217\u8868",
  stockTextHint: "\u5b81\u5fb7\u65f6\u4ee3,\u4ebf\u7eac\u9502\u80fd",
  previewEyebrow: "\u6821\u9a8c\u7ed3\u679c",
  previewTitle: "\u80a1\u7968\u5217\u8868\u9884\u89c8",
  previewNote: "\u4fdd\u5b58\u524d\u5efa\u8bae\u5148\u6821\u9a8c\uff0c\u786e\u8ba4\u6709\u6548\u80a1\u7968\u3001\u91cd\u590d\u80a1\u7968\u548c\u683c\u5f0f\u9519\u8bef\u9879\u3002",
  noRows: "\u6682\u65e0\u80a1\u7968\u3002\u8bf7\u5728\u4e0a\u65b9\u8f93\u5165\u80a1\u7968\u5217\u8868\u540e\u6821\u9a8c\u6216\u4fdd\u5b58\u3002",
  statusReady: "\u6b63\u5728\u8bfb\u53d6\u80a1\u7968\u6c60\u6a21\u677f\u3002",
  loadingTemplates: "\u6b63\u5728\u5237\u65b0\u80a1\u7968\u6c60\u6a21\u677f\u5217\u8868...",
  noTemplates: "\u6ca1\u6709\u627e\u5230\u80a1\u7968\u6c60\u6a21\u677f\uff0c\u53ef\u4ee5\u5148\u65b0\u5efa\u4e00\u4e2a\u6a21\u677f\u3002",
  loadLoading: "\u6b63\u5728\u8f7d\u5165\u80a1\u7968\u6c60\u6a21\u677f...",
  validateLoading: "\u6b63\u5728\u6821\u9a8c\u80a1\u7968\u5217\u8868...",
  saveLoading: "\u6b63\u5728\u4fdd\u5b58\u80a1\u7968\u6c60\u6a21\u677f...",
  deleteLoading: "\u6b63\u5728\u5220\u9664\u80a1\u7968\u6c60\u6a21\u677f...",
  seedLoading: "\u6b63\u5728\u521d\u59cb\u5316\u57fa\u7840\u6a21\u677f...",
  newDraft: "\u5df2\u521d\u59cb\u5316\u65b0\u80a1\u7968\u6c60\u6a21\u677f\u3002",
  copiedDraft: "\u5df2\u590d\u5236\u4e3a\u65b0\u80a1\u7968\u6c60\u8349\u7a3f\u3002\u4fdd\u5b58\u524d\u4e0d\u4f1a\u5199\u5165\u6a21\u677f\u8868\u3002",
  confirmDelete: "\u53ea\u5220\u9664\u80a1\u7968\u6c60\u6a21\u677f\u548c\u6a21\u677f\u80a1\u7968\u5173\u7cfb\uff0c\u4e0d\u5220\u9664\u4e3b\u884c\u60c5\u5e93\u6570\u636e\u3002\u786e\u8ba4\u5220\u9664\u5417\uff1f",
  noDeleteTarget: "\u8bf7\u5148\u9009\u62e9\u8981\u5220\u9664\u7684\u80a1\u7968\u6c60\u6a21\u677f\u3002",
  failedTemplates: "\u5237\u65b0\u5931\u8d25",
  failedLoad: "\u8f7d\u5165\u5931\u8d25",
  failedValidate: "\u6821\u9a8c\u5931\u8d25",
  failedSave: "\u4fdd\u5b58\u5931\u8d25",
  failedDelete: "\u5220\u9664\u5931\u8d25",
  failedSeed: "\u521d\u59cb\u5316\u5931\u8d25",
  fallbackUser: "admin"
};

const defaultTemplate = (): StockPoolTemplate => ({
  username: t.fallbackUser,
  template_name: `\u65b0\u80a1\u7968\u6c60_${chinaDateTimeStamp()}`,
  original_template_name: "",
  description: "",
  is_active: true,
  stock_count: 0,
  updated_at: "",
  db_path: "data_store/stock_pool_templates.sqlite",
  stocks: [],
  stock_text: ""
});

const stockColumns = ["index", "symbol", "ts_code", "stock_name", "latest_trade_date"];
const summaryKeys = ["template_name", "username", "stock_count", "is_active", "updated_at", "db_path"];

function chinaDateTimeStamp(date = new Date()): string {
  const parts = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).formatToParts(date);
  const value = (type: string) => parts.find((part) => part.type === type)?.value || "";
  const stamp = `${value("year")}${value("month")}${value("day")}${value("hour")}${value("minute")}${value("second")}`;
  return /^\d{14}$/.test(stamp) ? stamp : String(Date.now());
}

async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { credentials: "include", ...options });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function formFromTemplate(template: StockPoolTemplate): FormState {
  return {
    template_name: template.template_name || "",
    original_template_name: Object.prototype.hasOwnProperty.call(template, "original_template_name") ? template.original_template_name || "" : template.template_name || "",
    description: template.description || "",
    stock_text: template.stock_text || ""
  };
}

function toTemplate(form: FormState, username: string, rows: StockRow[] = []): StockPoolTemplate {
  return {
    ...defaultTemplate(),
    username,
    template_name: form.template_name,
    original_template_name: form.original_template_name,
    description: form.description,
    stock_text: form.stock_text,
    stock_count: rows.length,
    stocks: rows
  };
}

function summaryValue(key: string, value: unknown): string {
  if (typeof value === "boolean") return value ? "\u542f\u7528" : "\u505c\u7528";
  return formatValue(key, value);
}

export function StockPoolsPage() {
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [templates, setTemplates] = useState<StockPoolTemplate[]>([]);
  const [selectedName, setSelectedName] = useState("");
  const [form, setForm] = useState<FormState>(formFromTemplate(defaultTemplate()));
  const [currentTemplate, setCurrentTemplate] = useState<StockPoolTemplate>(defaultTemplate());
  const [previewRows, setPreviewRows] = useState<StockRow[]>([]);
  const [validationNote, setValidationNote] = useState(t.previewNote);
  const [status, setStatus] = useState(t.statusReady);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState<"templates" | "load" | "validate" | "save" | "delete" | "seed" | "">("");
  const username = currentUser?.username || t.fallbackUser;
  const summaryTemplate = useMemo(() => ({ ...currentTemplate, ...toTemplate(form, username, previewRows.length ? previewRows : currentTemplate.stocks || []) }), [currentTemplate, form, username, previewRows]);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function showError(prefix: string, err: unknown) {
    setError(true);
    setStatus(`${prefix}\uff1a${err instanceof Error ? err.message : String(err)}`);
  }

  function applyTemplate(template: StockPoolTemplate) {
    setCurrentTemplate(template);
    setForm(formFromTemplate(template));
    setPreviewRows(template.stocks || []);
  }

  async function loadCurrentPool(showStatus = true, templateName = selectedName) {
    const name = templateName || form.template_name.trim();
    if (!name) {
      const empty = defaultTemplate();
      empty.username = username;
      applyTemplate(empty);
      setStatus(t.noTemplates);
      return;
    }
    if (showStatus) {
      setLoading("load");
      setError(false);
      setStatus(t.loadLoading);
    }
    try {
      const data = await fetchJson<StockPoolTemplate>(`/api/stock-pools/template?username=${encodeURIComponent(username)}&template_name=${encodeURIComponent(name)}`);
      setSelectedName(data.template_name || name);
      applyTemplate(data);
      setValidationNote(t.previewNote);
      setError(false);
      setStatus(`\u80a1\u7968\u6c60\u6a21\u677f\u5df2\u8f7d\u5165\uff1a${data.template_name || name}\uff0c\u5171 ${data.stock_count || 0} \u53ea\u80a1\u7968\u3002`);
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
      const data = await fetchJson<{ templates: StockPoolTemplate[] }>(`/api/stock-pools/templates?username=${encodeURIComponent(targetUsername || t.fallbackUser)}`);
      const nextTemplates = data.templates || [];
      setTemplates(nextTemplates);
      if (!nextTemplates.length) {
        const empty = defaultTemplate();
        empty.username = targetUsername || t.fallbackUser;
        setSelectedName("");
        applyTemplate(empty);
        setStatus(t.noTemplates);
        return;
      }
      const nextName = selectedName && nextTemplates.some((item) => item.template_name === selectedName) ? selectedName : nextTemplates[0]?.template_name || "";
      setSelectedName(nextName);
      await loadCurrentPool(false, nextName);
      setError(false);
      setStatus(`\u5df2\u8bfb\u53d6 ${nextTemplates.length} \u4e2a\u80a1\u7968\u6c60\u6a21\u677f\u3002`);
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
    const draft = defaultTemplate();
    draft.username = username;
    setSelectedName("");
    applyTemplate(draft);
    setValidationNote(t.previewNote);
    setError(false);
    setStatus(t.newDraft);
  }

  function copyDraft() {
    const nextName = `${form.template_name || "\u80a1\u7968\u6c60"}_\u526f\u672c_${chinaDateTimeStamp()}`;
    const draft = toTemplate({ ...form, template_name: nextName, original_template_name: "" }, username, previewRows);
    setSelectedName("");
    applyTemplate(draft);
    setError(false);
    setStatus(t.copiedDraft);
  }

  async function validateStocks() {
    setLoading("validate");
    setError(false);
    setStatus(t.validateLoading);
    try {
      const data = await fetchJson<ValidationResult>("/api/stock-pools/template/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stock_text: form.stock_text })
      });
      setPreviewRows(data.valid_stocks || []);
      const note = `\u6709\u6548 ${data.valid_count || 0} \u53ea\uff1b\u91cd\u590d ${data.duplicate_count || 0} \u9879\uff1b\u683c\u5f0f\u9519\u8bef ${data.invalid_count || 0} \u9879\u3002`;
      setValidationNote(note);
      if ((data.invalid_count || 0) > 0) {
        setError(true);
        setStatus(`\u80a1\u7968\u5217\u8868\u5b58\u5728\u683c\u5f0f\u9519\u8bef\uff1a${(data.invalid_items || []).join("\u3001")}`);
      } else if ((data.duplicate_count || 0) > 0) {
        setStatus(`\u80a1\u7968\u5217\u8868\u6821\u9a8c\u901a\u8fc7\uff0c\u6709\u6548 ${data.valid_count || 0} \u53ea\uff1b\u91cd\u590d\u9879\u5df2\u81ea\u52a8\u5ffd\u7565\u3002`);
      } else {
        setStatus(`\u80a1\u7968\u5217\u8868\u6821\u9a8c\u901a\u8fc7\uff0c\u6709\u6548 ${data.valid_count || 0} \u53ea\u3002`);
      }
    } catch (err) {
      showError(t.failedValidate, err);
    } finally {
      setLoading("");
    }
  }

  async function savePool() {
    setLoading("save");
    setError(false);
    setStatus(t.saveLoading);
    try {
      const payload = {
        username,
        original_template_name: form.original_template_name.trim(),
        template_name: form.template_name.trim(),
        description: form.description.trim(),
        is_active: true,
        stock_text: form.stock_text.trim(),
        overwrite_existing: Boolean(form.original_template_name.trim())
      };
      const data = await fetchJson<{ message?: string; template?: StockPoolTemplate; validation?: ValidationResult }>("/api/stock-pools/template", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      await loadTemplates(false, username);
      if (data.template?.template_name) setSelectedName(data.template.template_name);
      if (data.template) applyTemplate(data.template);
      if (data.validation) setValidationNote(`\u6709\u6548 ${data.validation.valid_count || 0} \u53ea\uff1b\u91cd\u590d ${data.validation.duplicate_count || 0} \u9879\uff1b\u683c\u5f0f\u9519\u8bef ${data.validation.invalid_count || 0} \u9879\u3002`);
      setStatus(data.message || "\u80a1\u7968\u6c60\u6a21\u677f\u5df2\u4fdd\u5b58\u3002");
    } catch (err) {
      showError(t.failedSave, err);
    } finally {
      setLoading("");
    }
  }

  async function deletePool() {
    const name = form.original_template_name.trim() || form.template_name.trim();
    if (!name) {
      setError(true);
      setStatus(t.noDeleteTarget);
      return;
    }
    if (typeof window !== "undefined" && typeof window.confirm === "function" && !window.confirm(t.confirmDelete)) return;
    setLoading("delete");
    setError(false);
    setStatus(t.deleteLoading);
    try {
      const data = await fetchJson<{ message?: string }>(`/api/stock-pools/template?username=${encodeURIComponent(username)}&template_name=${encodeURIComponent(name)}`, { method: "DELETE" });
      await loadTemplates(false, username);
      setStatus(data.message || "\u80a1\u7968\u6c60\u6a21\u677f\u5df2\u5220\u9664\u3002");
    } catch (err) {
      showError(t.failedDelete, err);
    } finally {
      setLoading("");
    }
  }

  async function seedTemplates() {
    setLoading("seed");
    setError(false);
    setStatus(t.seedLoading);
    try {
      const data = await fetchJson<{ message?: string }>(`/api/stock-pools/templates/seed?username=${encodeURIComponent(username)}`, { method: "POST" });
      await loadTemplates(false, username);
      setStatus(data.message || "\u57fa\u7840\u6a21\u677f\u521d\u59cb\u5316\u5b8c\u6210\u3002");
    } catch (err) {
      showError(t.failedSeed, err);
    } finally {
      setLoading("");
    }
  }

  const actionDisabled = Boolean(loading);

  return (
    <section className="stock-pools-page">
      <div className="stock-pools-header">
        <div>
          <p className="page-eyebrow">{t.eyebrow}</p>
          <h1>{t.title}</h1>
          <p className="stock-pools-note">{t.note}</p>
        </div>
        <div className="stock-pools-header-actions">
          <a className="secondary-link" href="/trading/daily-plan"><ExternalLink size={14} />{t.dailyPlan}</a>
          <a className="secondary-link" href="/trading/paper"><ExternalLink size={14} />{t.paper}</a>
        </div>
      </div>

      <div className="stock-pools-runbar">
        <label><span>{t.selectTemplate}</span><select value={selectedName} onChange={(event) => { setSelectedName(event.target.value); void loadCurrentPool(false, event.target.value); }}>{templates.length ? templates.map((item) => <option key={item.template_name || ""} value={item.template_name || ""}>{item.template_name || "-"} ({item.stock_count || 0})</option>) : <option value="">-</option>}</select></label>
        <button className="secondary-link" type="button" disabled={actionDisabled} onClick={() => void loadTemplates(true, username)}><RefreshCw size={14} />{t.reload}</button>
        <button className="secondary-link" type="button" disabled={actionDisabled} onClick={() => void loadCurrentPool(true)}><SearchCheck size={14} />{t.load}</button>
        <button className="secondary-link" type="button" disabled={actionDisabled} onClick={newDraft}><FilePlus2 size={14} />{t.create}</button>
        <button className="secondary-link" type="button" disabled={actionDisabled} onClick={copyDraft}><Copy size={14} />{t.copy}</button>
        <button className="primary-button" type="button" disabled={actionDisabled} onClick={() => void savePool()}><Save size={14} />{loading === "save" ? t.saveLoading : t.save}</button>
        <button className="danger-button" type="button" disabled={actionDisabled} onClick={() => void deletePool()}><Trash2 size={14} />{loading === "delete" ? t.deleteLoading : t.delete}</button>
      </div>

      <p className={error ? "stock-pools-status error" : "stock-pools-status"}>{status}</p>

      <section className="stock-pools-summary">
        <div className="summary-intro">
          <p className="page-eyebrow">{t.summaryEyebrow}</p>
          <h2>{t.summaryTitle}</h2>
        </div>
        <div className="metric-strip stock-pools-metrics">
          {summaryKeys.map((key) => <div className="metric-tile" key={key}><span>{formatHeader(key)}</span><strong>{summaryValue(key, summaryTemplate[key as keyof StockPoolTemplate])}</strong></div>)}
        </div>
      </section>

      <section className="stock-pools-editor">
        <div className="panel-header"><div><p className="page-eyebrow">{t.editorEyebrow}</p><h2>{t.editorTitle}</h2></div><p>{t.editorNote}</p></div>
        <div className="stock-pools-form-grid">
          <label><span>{t.templateName}</span><input value={form.template_name} placeholder={t.templateNameHint} onChange={(event) => update("template_name", event.target.value)} /></label>
          <label><span>{t.originalTemplateName}</span><input value={form.original_template_name} readOnly /></label>
          <label className="wide"><span>{t.description}</span><input value={form.description} onChange={(event) => update("description", event.target.value)} /></label>
          <label className="full"><span>{t.stockText}</span><textarea rows={7} value={form.stock_text} placeholder={t.stockTextHint} onChange={(event) => update("stock_text", event.target.value)} /></label>
        </div>
        <div className="stock-pools-inline-actions">
          <button className="secondary-link" type="button" disabled={actionDisabled} onClick={() => void validateStocks()}><SearchCheck size={14} />{loading === "validate" ? t.validateLoading : t.validate}</button>
          <button className="secondary-link" type="button" disabled={actionDisabled} onClick={() => void seedTemplates()}><Wand2 size={14} />{loading === "seed" ? t.seedLoading : t.seed}</button>
        </div>
      </section>

      <section className="stock-pools-preview">
        <div className="panel-header"><div><p className="page-eyebrow">{t.previewEyebrow}</p><h2>{t.previewTitle}</h2></div><p>{validationNote}</p></div>
        <DataTable rows={previewRows} />
      </section>
    </section>
  );
}

function DataTable({ rows }: { rows: StockRow[] }) {
  if (!rows.length) return <div className="empty-state">{t.noRows}</div>;
  return <div className="table-wrap stock-pools-table-wrap"><table><thead><tr>{stockColumns.map((key) => <th key={key}>{formatHeader(key)}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{stockColumns.map((key) => <td key={key}>{key === "index" ? index + 1 : formatValue(key, row[key])}</td>)}</tr>)}</tbody></table></div>;
}
