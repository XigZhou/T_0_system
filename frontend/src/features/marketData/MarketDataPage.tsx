import { useEffect, useMemo, useState } from "react";
import { Database, RefreshCw, Search } from "lucide-react";
import "./marketData.css";

type TabKey = "factors" | "stocks";
type StatusState = { text: string; error?: boolean };

type FactorSummary = {
  factor_count?: number;
  start_date?: string;
  end_date?: string;
  row_count?: number;
  source_table?: string;
};

type FactorRow = {
  field?: string;
  name?: string;
  category?: string;
  purpose?: string;
  inputs?: string;
  formula?: string;
  window?: string;
  boundary?: string;
  example?: string;
};

type FactorPayload = {
  summary?: FactorSummary;
  factors?: FactorRow[];
  message?: string;
  db_path?: string;
};

type StockSummary = {
  stock_count?: number;
  start_date?: string;
  end_date?: string;
  row_count?: number;
  source_table?: string;
};

type StockRow = {
  symbol?: string;
  ts_code?: string;
  name?: string;
  start_date?: string;
  end_date?: string;
  row_count?: number;
};

type StockPayload = {
  summary?: StockSummary;
  stocks?: StockRow[];
  limit?: number;
  message?: string;
  db_path?: string;
};

type StockCheckPayload = {
  stock_name?: string;
  available?: boolean;
  matches?: StockRow[];
  source_table?: string;
  message?: string;
};

const t = {
  eyebrow: "Market Data",
  title: "\u6570\u636e\u884c\u60c5",
  note: "\u53ea\u8bfb\u67e5\u770b\u5f53\u524d\u7cfb\u7edf\u5df2\u6709\u7684\u56e0\u5b50\u548c\u80a1\u7968\u65e5\u7ebf\u6570\u636e\u3002",
  refresh: "\u5237\u65b0\u6570\u636e",
  loading: "\u6b63\u5728\u8bfb\u53d6\u6570\u636e\u884c\u60c5\uff1b\u672c\u6b21\u4e0d\u4f1a\u5199\u5165\u6570\u636e\u3002",
  ready: "\u5df2\u8bfb\u53d6\u6570\u636e\u884c\u60c5\uff1b\u672c\u9875\u53ea\u8bfb\uff0c\u6ca1\u6709\u5199\u5165\u6570\u636e\u3002",
  failed: "\u8bfb\u53d6\u6570\u636e\u884c\u60c5\u5931\u8d25",
  readonly: "\u672c\u9875\u53ea\u8bfb\uff0c\u6ca1\u6709\u5199\u5165\u6570\u636e\u3002",
  factorTab: "\u56e0\u5b50\u5e93",
  stockTab: "\u80a1\u7968\u65e5\u7ebf\u6570\u636e",
  factorSummaryEyebrow: "\u56e0\u5b50\u6458\u8981",
  factorSummaryTitle: "\u5f53\u524d\u53ef\u7528\u56e0\u5b50",
  stockSummaryEyebrow: "\u65e5\u7ebf\u6458\u8981",
  stockSummaryTitle: "\u5f53\u524d\u53ef\u7528\u80a1\u7968",
  factorCount: "\u56e0\u5b50\u6570\u91cf",
  factorDateSpan: "\u56e0\u5b50\u8ba1\u7b97\u65f6\u95f4",
  stockCount: "\u80a1\u7968\u6570\u91cf",
  stockDateSpan: "\u80a1\u7968\u91c7\u96c6\u65f6\u95f4",
  rowCount: "\u6570\u636e\u884c\u6570",
  sourceTable: "\u6570\u636e\u8868",
  factorDetail: "\u56e0\u5b50\u660e\u7ec6",
  factorDetailNote: "\u5c55\u793a\u4e3b\u884c\u60c5\u5e93 stock_daily_features \u4e2d\u5df2\u5b58\u5728\u4e14\u53ef\u4f9b\u8868\u8fbe\u5f0f\u6216\u8bca\u65ad\u4f7f\u7528\u7684\u5b57\u6bb5\u3002",
  stockDetail: "\u80a1\u7968\u65e5\u7ebf\u660e\u7ec6",
  stockDetailNote: "\u5c55\u793a\u4e3b\u884c\u60c5\u5e93\u4e2d\u5df2\u91c7\u96c6\u5230\u65e5\u7ebf\u6216\u6307\u6807\u6570\u636e\u7684\u80a1\u7968\u3002",
  searchLabel: "\u80a1\u7968\u540d\u79f0",
  searchPlaceholder: "\u8f93\u5165\u80a1\u7968\u540d\u79f0\uff0c\u4f8b\u5982\u5e73\u5b89\u94f6\u884c",
  searchButton: "\u641c\u7d22",
  searchEmpty: "\u8bf7\u8f93\u5165\u80a1\u7968\u540d\u79f0\u540e\u518d\u641c\u7d22\uff1b\u672c\u6b21\u6ca1\u6709\u5199\u5165\u6570\u636e\u3002",
  searchLoading: "\u6b63\u5728\u68c0\u67e5\u80a1\u7968\u662f\u5426\u53ef\u7528\uff1b\u672c\u6b21\u4ec5\u8bfb\u53d6\u6570\u636e\u3002",
  availableAlert: "\u8be5\u80a1\u7968\u5728\u8be5\u7cfb\u7edf\u53ef\u7528",
  unavailableAlert: "\u8be5\u80a1\u7968\u5728\u8be5\u7cfb\u7edf\u4e0d\u53ef\u7528",
  field: "\u5b57\u6bb5",
  factorName: "\u6307\u6807\u540d\u79f0",
  category: "\u5206\u7c7b",
  inputs: "\u8f93\u5165\u5b57\u6bb5",
  formula: "\u8ba1\u7b97\u516c\u5f0f",
  window: "\u7a97\u53e3",
  boundary: "\u8fb9\u754c\u6761\u4ef6",
  symbol: "\u80a1\u7968\u4ee3\u7801",
  tsCode: "Tushare\u4ee3\u7801",
  stockName: "\u80a1\u7968\u540d\u79f0",
  startDate: "\u5f00\u59cb\u65e5\u671f",
  endDate: "\u7ed3\u675f\u65e5\u671f",
  noRows: "\u6682\u65e0\u6570\u636e",
  dash: "-"
};

function detailText(error: unknown): string {
  return error instanceof Error ? error.message : String(error || "");
}

function formatNumber(value: unknown): string {
  if (value === null || value === undefined || value === "") return t.dash;
  if (typeof value === "number") return Number.isFinite(value) ? value.toLocaleString("zh-CN") : t.dash;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toLocaleString("zh-CN") : String(value);
}

function formatText(value: unknown): string {
  const text = String(value ?? "").trim();
  return text || t.dash;
}

function formatDateSpan(start?: string, end?: string): string {
  const cleanStart = String(start || "").trim();
  const cleanEnd = String(end || "").trim();
  if (!cleanStart && !cleanEnd) return t.dash;
  return `${cleanStart || t.dash} - ${cleanEnd || t.dash}`;
}

async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { credentials: "include", ...options });
  const text = await response.text();
  let data: unknown = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(text || "Invalid JSON");
  }
  if (!response.ok) {
    const detail = typeof data === "object" && data && "detail" in data ? String((data as { detail?: unknown }).detail || "") : "";
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return data as T;
}

function StatusLine({ state }: { state: StatusState }) {
  return <p className={state.error ? "market-data-status error" : "market-data-status"}>{state.text}</p>;
}

function PanelHead({ eyebrow, title, note }: { eyebrow: string; title: string; note: string }) {
  return (
    <div className="panel-header market-data-panel-head">
      <div>
        <p className="page-eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
      </div>
      <p>{note}</p>
    </div>
  );
}

function SummaryPanel({
  eyebrow,
  title,
  note,
  cards
}: {
  eyebrow: string;
  title: string;
  note: string;
  cards: Array<{ label: string; value: string; meta: string }>;
}) {
  return (
    <section className="market-data-summary">
      <div className="summary-intro">
        <p className="page-eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
        <p>{note}</p>
      </div>
      <div className="metric-strip market-data-metrics">
        {cards.map((card) => (
          <div className="metric-tile" key={card.label}>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
            <small>{card.meta}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

export function MarketDataPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("factors");
  const [factorPayload, setFactorPayload] = useState<FactorPayload | null>(null);
  const [stockPayload, setStockPayload] = useState<StockPayload | null>(null);
  const [searchText, setSearchText] = useState("");
  const [searchResult, setSearchResult] = useState<StockCheckPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [status, setStatus] = useState<StatusState>({ text: t.loading });

  async function loadMarketData(showStatus = true) {
    if (showStatus) setStatus({ text: t.loading });
    setLoading(true);
    try {
      const [factors, stocks] = await Promise.all([
        fetchJson<FactorPayload>("/api/market-data/factors"),
        fetchJson<StockPayload>("/api/market-data/stocks?limit=1000")
      ]);
      setFactorPayload(factors);
      setStockPayload(stocks);
      setStatus({ text: t.ready });
    } catch (error) {
      setStatus({ text: `${t.failed}\uff1a${detailText(error)}`, error: true });
    } finally {
      setLoading(false);
    }
  }

  async function checkStock() {
    const name = searchText.trim();
    if (!name) {
      setStatus({ text: t.searchEmpty, error: true });
      return;
    }
    setSearching(true);
    setStatus({ text: t.searchLoading });
    try {
      const data = await fetchJson<StockCheckPayload>(`/api/market-data/stocks/check?stock_name=${encodeURIComponent(name)}`);
      setSearchResult(data);
      const alertText = `${name}\uff1a${data.available ? t.availableAlert : t.unavailableAlert}`;
      if (typeof window.alert === "function") window.alert(alertText);
      setStatus({ text: `${alertText}\u3002${t.readonly}` });
    } catch (error) {
      setStatus({ text: `${t.failed}\uff1a${detailText(error)}`, error: true });
    } finally {
      setSearching(false);
    }
  }

  useEffect(() => {
    void loadMarketData(true);
  }, []);

  const factorSummary = factorPayload?.summary || {};
  const stockSummary = stockPayload?.summary || {};
  const factorRows = factorPayload?.factors || [];
  const stockRows = stockPayload?.stocks || [];

  const factorCards = useMemo(() => [
    { label: t.factorCount, value: formatNumber(factorSummary.factor_count || 0), meta: t.readonly },
    { label: t.factorDateSpan, value: formatDateSpan(factorSummary.start_date, factorSummary.end_date), meta: formatText(factorPayload?.message) },
    { label: t.rowCount, value: formatNumber(factorSummary.row_count || 0), meta: t.sourceTable },
    { label: t.sourceTable, value: formatText(factorSummary.source_table), meta: formatText(factorPayload?.db_path) }
  ], [factorPayload, factorSummary]);

  const stockCards = useMemo(() => [
    { label: t.stockCount, value: formatNumber(stockSummary.stock_count || 0), meta: t.readonly },
    { label: t.stockDateSpan, value: formatDateSpan(stockSummary.start_date, stockSummary.end_date), meta: formatText(stockPayload?.message) },
    { label: t.rowCount, value: formatNumber(stockSummary.row_count || 0), meta: t.sourceTable },
    { label: t.sourceTable, value: formatText(stockSummary.source_table), meta: formatText(stockPayload?.db_path) }
  ], [stockPayload, stockSummary]);

  return (
    <section className="market-data-page">
      <div className="market-data-header">
        <div>
          <p className="page-eyebrow">{t.eyebrow}</p>
          <h1>{t.title}</h1>
          <p className="market-data-note">{t.note}</p>
        </div>
        <div className="market-data-header-actions">
          <button className="secondary-link" type="button" disabled={loading || searching} onClick={() => void loadMarketData(true)}>
            <RefreshCw size={14} />{t.refresh}
          </button>
        </div>
      </div>

      <div className="market-data-tabs" role="tablist" aria-label={t.title}>
        <button className={activeTab === "factors" ? "active" : ""} type="button" onClick={() => setActiveTab("factors")}><Database size={14} />{t.factorTab}</button>
        <button className={activeTab === "stocks" ? "active" : ""} type="button" onClick={() => setActiveTab("stocks")}><Database size={14} />{t.stockTab}</button>
      </div>

      {activeTab === "factors" ? (
        <>
          <SummaryPanel eyebrow={t.factorSummaryEyebrow} title={t.factorSummaryTitle} note={t.readonly} cards={factorCards} />
          <section className="market-data-panel">
            <PanelHead eyebrow={t.factorTab} title={t.factorDetail} note={t.factorDetailNote} />
            <FactorTable rows={factorRows} />
          </section>
        </>
      ) : (
        <>
          <SummaryPanel eyebrow={t.stockSummaryEyebrow} title={t.stockSummaryTitle} note={t.readonly} cards={stockCards} />
          <section className="market-data-panel">
            <PanelHead eyebrow={t.stockTab} title={t.stockDetail} note={t.stockDetailNote} />
            <div className="market-data-searchbar">
              <label>
                <span>{t.searchLabel}</span>
                <input value={searchText} placeholder={t.searchPlaceholder} onChange={(event) => setSearchText(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void checkStock(); }} />
              </label>
              <button className="primary-button" type="button" disabled={searching || loading} onClick={() => void checkStock()}><Search size={14} />{t.searchButton}</button>
              {searchResult && <span className={searchResult.available ? "market-data-search-result ok" : "market-data-search-result"}>{searchResult.available ? t.availableAlert : t.unavailableAlert}</span>}
            </div>
            <StockTable rows={stockRows} />
          </section>
        </>
      )}

      <StatusLine state={status} />
    </section>
  );
}

function FactorTable({ rows }: { rows: FactorRow[] }) {
  return (
    <div className="table-wrap market-data-table-wrap factors">
      <table>
        <thead>
          <tr><th>{t.field}</th><th>{t.factorName}</th><th>{t.category}</th><th>{t.inputs}</th><th>{t.formula}</th><th>{t.window}</th><th>{t.boundary}</th></tr>
        </thead>
        <tbody>
          {rows.length ? rows.map((row) => (
            <tr key={row.field || row.name}>
              <td>{formatText(row.field)}</td>
              <td>{formatText(row.name)}</td>
              <td>{formatText(row.category)}</td>
              <td>{formatText(row.inputs)}</td>
              <td>{formatText(row.formula)}</td>
              <td>{formatText(row.window)}</td>
              <td>{formatText(row.boundary)}</td>
            </tr>
          )) : <tr><td colSpan={7}>{t.noRows}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function StockTable({ rows }: { rows: StockRow[] }) {
  return (
    <div className="table-wrap market-data-table-wrap stocks">
      <table>
        <thead>
          <tr><th>{t.symbol}</th><th>{t.tsCode}</th><th>{t.stockName}</th><th>{t.startDate}</th><th>{t.endDate}</th><th>{t.rowCount}</th></tr>
        </thead>
        <tbody>
          {rows.length ? rows.map((row, index) => (
            <tr key={`${row.symbol || "stock"}-${index}`}>
              <td>{formatText(row.symbol)}</td>
              <td>{formatText(row.ts_code)}</td>
              <td>{formatText(row.name)}</td>
              <td>{formatText(row.start_date)}</td>
              <td>{formatText(row.end_date)}</td>
              <td>{formatNumber(row.row_count || 0)}</td>
            </tr>
          )) : <tr><td colSpan={6}>{t.noRows}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
