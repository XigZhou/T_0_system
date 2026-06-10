import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ExternalLink, RefreshCw, RotateCcw } from "lucide-react";
import "./sectorResearch.css";

type ResultRow = Record<string, unknown>;

type SectorSummary = {
  latest_trade_date?: string;
  theme_count?: number;
  board_count?: number;
  theme_daily_rows?: number;
  stock_exposure_rows?: number;
  error_count?: number;
  source?: string;
  processed_dir?: string;
};

type MarketIndex = {
  code?: string;
  name?: string;
  state?: string;
  tone?: string;
  close?: number;
  pct_chg?: number;
  m5?: number;
  m20?: number;
  m60?: number;
};

type MarketContext = {
  status?: string;
  note?: string;
  indexes?: MarketIndex[];
};

type SectorPayload = {
  summary?: SectorSummary;
  market_context?: MarketContext;
  latest_themes?: ResultRow[];
  latest_boards?: ResultRow[];
  theme_exposure_counts?: ResultRow[];
  stock_exposure?: ResultRow[];
  mapping_rows?: ResultRow[];
  error_rows?: ResultRow[];
  messages?: string[];
};

type TabKey = "themes" | "boards" | "exposure" | "mapping" | "errors";

const t = {
  title: "\u677f\u5757\u7814\u7a76\u5de5\u4f5c\u53f0",
  eyebrow: "Sector Research",
  note: "\u8bfb\u53d6 SQLite \u4e3b\u5e93\u4e2d\u7684\u677f\u5757\u7814\u7a76\u6570\u636e\uff0c\u67e5\u770b\u4e3b\u9898\u6392\u540d\u3001\u5f3a\u52bf\u677f\u5757\u3001\u4e2a\u80a1\u66b4\u9732\u548c\u5f02\u5e38\u8bb0\u5f55\u3002",
  oldPage: "\u6253\u5f00\u65e7\u9875",
  portfolio: "\u7ec4\u5408\u56de\u6d4b",
  load: "\u8bfb\u53d6\u677f\u5757\u7814\u7a76",
  reading: "\u8bfb\u53d6\u4e2d...",
  refresh: "\u5237\u65b0",
  ready: "\u7b49\u5f85\u8bfb\u53d6\u3002",
  loading: "\u6b63\u5728\u8bfb\u53d6\u677f\u5757\u7814\u7a76\u7ed3\u679c\u3002",
  failed: "\u8bfb\u53d6\u5931\u8d25",
  done: "\u8bfb\u53d6\u5b8c\u6210\uff1a\u6700\u65b0\u4e3b\u9898 {themes} \u6761\uff0c\u5f3a\u52bf\u677f\u5757 {boards} \u6761\u3002",
  summaryEyebrow: "\u7814\u7a76\u6458\u8981",
  summaryTitle: "\u4e3b\u9898\u4e0e\u677f\u5757\u72b6\u6001",
  sourcePath: "\u6570\u636e\u6e90\uff1a{source}\uff1b\u6307\u6807\u4f4d\u7f6e\uff1a{path}",
  sqlite: "SQLite\u4e3b\u5e93",
  csv: "\u65e7CSV\u517c\u5bb9",
  marketEyebrow: "\u5927\u76d8",
  marketTitle: "\u5927\u76d8\u73af\u5883",
  marketDefaultNote: "\u8bfb\u53d6 SQLite \u4e3b\u5e93\u4e2d\u7684\u5927\u76d8\u73af\u5883\u6570\u636e\uff0c\u4e0d\u89e6\u53d1\u884c\u60c5\u6293\u53d6\u3002",
  marketEmptyTitle: "\u5927\u76d8\u73af\u5883\u672a\u5c31\u7eea",
  readonly: "\u53ea\u8bfb",
  noMarket: "\u6682\u65e0\u53ef\u5c55\u793a\u7684\u5927\u76d8\u4e0a\u4e0b\u6587\u6570\u636e\u3002",
  close: "\u6536\u76d8",
  dayPct: "\u65e5\u6da8\u8dcc",
  m5: "5\u65e5\u52a8\u91cf",
  m20: "20\u65e5\u52a8\u91cf",
  m60: "60\u65e5\u52a8\u91cf",
  themesTab: "\u4e3b\u9898\u6392\u540d",
  boardsTab: "\u5f3a\u52bf\u677f\u5757",
  exposureTab: "\u4e2a\u80a1\u66b4\u9732",
  mappingTab: "\u4e3b\u9898\u6620\u5c04",
  errorsTab: "\u5f02\u5e38\u65e5\u5fd7",
  themeTitle: "\u6700\u65b0\u4e3b\u9898\u5f3a\u5ea6",
  themeNote: "\u7efc\u5408\u5206\u53d6\u91cf\u4ef7\u9f50\u5347\u5206\u4e0e\u6781\u5f31\u53cd\u8f6c\u5206\u7684\u4e3b\u9898\u805a\u5408\u7ed3\u679c\u3002",
  boardTitle: "\u6700\u65b0\u5f3a\u52bf\u677f\u5757",
  boardNote: "\u884c\u4e1a\u677f\u5757\u548c\u6982\u5ff5\u677f\u5757\u6df7\u6392\uff0c\u6309\u677f\u5757\u7efc\u5408\u5206\u964d\u5e8f\u5c55\u793a\u3002",
  exposureTitle: "\u4e3b\u9898\u66b4\u9732",
  exposureNote: "\u540c\u4e00\u80a1\u7968\u547d\u4e2d\u7684\u4e3b\u9898\u548c\u677f\u5757\u8d8a\u591a\uff0c\u66b4\u9732\u5206\u8d8a\u9ad8\uff1b\u4e3b\u9898\u80a1\u7968\u6c60\u6309\u5168\u90e8\u547d\u4e2d\u4e3b\u9898\u7edf\u8ba1\u3002",
  exposureCount: "\u4e3b\u9898\u8986\u76d6\u7edf\u8ba1",
  exposureCountNote: "\u6309 theme_names \u5168\u90e8\u547d\u4e2d\u7edf\u8ba1\uff0c\u4e0d\u6309\u9996\u4e2a\u547d\u4e2d\u4e3b\u9898\u7edf\u8ba1\u3002",
  exposureDetail: "\u4e2a\u80a1\u660e\u7ec6",
  mappingTitle: "\u4e3b\u9898\u4e0e\u677f\u5757\u5339\u914d",
  mappingNote: "\u7531 sector_research/configs/themes.yaml \u7684\u5173\u952e\u8bcd\u5339\u914d AKShare \u677f\u5757\u540d\u79f0\u3002",
  errorsTitle: "\u6293\u53d6\u4e0e\u5904\u7406\u65e5\u5fd7",
  errorsNote: "\u7f51\u7edc\u6216\u5355\u4e2a\u677f\u5757\u5931\u8d25\u4f1a\u8bb0\u5f55\u5728\u8fd9\u91cc\uff1b\u8d44\u91d1\u6d41\u5931\u8d25\u4e0d\u963b\u65ad\u5386\u53f2\u884c\u60c5\u5f3a\u5ea6\u8ba1\u7b97\u3002",
  noRows: "\u6682\u65e0\u6570\u636e",
  noChart: "\u6682\u65e0\u4e3b\u9898\u5f3a\u5ea6\u6570\u636e\u3002",
  noMessages: "\u672a\u53d1\u73b0\u8bfb\u53d6\u5f02\u5e38\u3002"
};

const themeColumns = ["theme_rank", "theme_name", "theme_score", "volume_price_score", "reversal_score", "m5", "m20", "amount_ratio_20", "board_up_ratio", "strongest_board", "strongest_subtheme"];
const boardColumns = ["board_rank_overall", "board_rank_in_theme", "theme_name", "subtheme_name", "board_type", "board_name", "theme_board_score", "volume_price_score", "reversal_score", "pct_chg", "m20", "amount_ratio_20", "main_net_inflow_today"];
const exposureColumns = ["stock_code", "stock_name", "primary_theme", "primary_subtheme", "exposure_score", "theme_count", "board_count", "theme_names", "board_names", "matched_keywords"];
const themeExposureCountColumns = ["theme_name", "stock_count", "primary_stock_count", "coverage_ratio", "top_stocks"];
const mappingColumns = ["theme_name", "subtheme_name", "matched_keyword", "board_type", "board_code", "board_name", "source", "fetched_at"];

const columnLabels: Record<string, string> = {
  theme_rank: "\u6392\u540d",
  theme_name: "\u4e3b\u9898",
  theme_score: "\u7efc\u5408\u5206",
  volume_price_score: "\u91cf\u4ef7\u9f50\u5347\u5206",
  reversal_score: "\u6781\u5f31\u53cd\u8f6c\u5206",
  m5: "5\u65e5\u52a8\u91cf",
  m20: "20\u65e5\u52a8\u91cf",
  amount_ratio_20: "\u6210\u4ea4\u989d\u653e\u5927",
  board_up_ratio: "\u4e0a\u6da8\u5360\u6bd4",
  strongest_board: "\u6700\u5f3a\u677f\u5757",
  strongest_subtheme: "\u6700\u5f3a\u5b50\u8d5b\u9053",
  board_rank_overall: "\u603b\u6392\u540d",
  board_rank_in_theme: "\u4e3b\u9898\u5185\u6392\u540d",
  subtheme_name: "\u5b50\u8d5b\u9053",
  board_type: "\u677f\u5757\u7c7b\u578b",
  board_name: "\u677f\u5757\u540d\u79f0",
  theme_board_score: "\u7efc\u5408\u5206",
  pct_chg: "\u6da8\u8dcc\u5e45",
  main_net_inflow_today: "\u4eca\u65e5\u4e3b\u529b\u51c0\u6d41\u5165",
  stock_code: "\u80a1\u7968\u4ee3\u7801",
  stock_name: "\u80a1\u7968\u540d\u79f0",
  primary_theme: "\u9996\u4e2a\u547d\u4e2d\u4e3b\u9898",
  primary_subtheme: "\u9996\u4e2a\u547d\u4e2d\u5b50\u8d5b\u9053",
  exposure_score: "\u66b4\u9732\u5206",
  theme_count: "\u4e3b\u9898\u6570",
  board_count: "\u677f\u5757\u6570",
  theme_names: "\u5168\u90e8\u547d\u4e2d\u4e3b\u9898",
  board_names: "\u547d\u4e2d\u677f\u5757",
  matched_keywords: "\u5173\u952e\u8bcd",
  stock_count: "\u5168\u90e8\u547d\u4e2d\u80a1\u7968\u6570",
  primary_stock_count: "\u9996\u4e2a\u547d\u4e2d\u80a1\u7968\u6570",
  coverage_ratio: "\u8986\u76d6\u5360\u6bd4",
  top_stocks: "\u9ad8\u66b4\u9732\u793a\u4f8b",
  matched_keyword: "\u5173\u952e\u8bcd",
  board_code: "\u677f\u5757\u4ee3\u7801",
  source: "\u6765\u6e90",
  fetched_at: "\u6293\u53d6\u65f6\u95f4",
  latest_trade_date: "\u6700\u65b0\u4ea4\u6613\u65e5",
  theme_daily_rows: "\u4e3b\u9898\u65e5\u7ebf",
  stock_exposure_rows: "\u4e2a\u80a1\u66b4\u9732",
  error_count: "\u5f02\u5e38\u8bb0\u5f55"
};

const percentColumns = new Set(["m5", "m20", "m60", "m120", "board_up_ratio", "positive_m20_ratio", "theme_rank_pct", "drawdown_from_120_high", "position_in_250_range", "coverage_ratio"]);
const scoreColumns = new Set(["theme_score", "volume_price_score", "reversal_score", "strongest_board_score", "theme_board_score", "exposure_score"]);
const integerColumns = new Set(["theme_rank", "board_rank_overall", "board_rank_in_theme", "theme_count", "board_count", "stock_count", "primary_stock_count", "theme_daily_rows", "stock_exposure_rows", "error_count"]);
const numberFormatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 4 });
const moneyFormatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 });

function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (Array.isArray(value)) return value.map((item) => String(item)).join("\u3001");
  if (typeof value === "boolean") return value ? "\u662f" : "\u5426";
  if (typeof value !== "number") return String(value);
  if (!Number.isFinite(value)) return "-";
  if (percentColumns.has(key)) return `${(value * 100).toFixed(2)}%`;
  if (key === "pct_chg" || key.endsWith("_ratio_today")) return `${value.toFixed(2)}%`;
  if (key === "amount_ratio_20") return `${value.toFixed(2)}x`;
  if (key.includes("inflow")) return moneyFormatter.format(value);
  if (scoreColumns.has(key)) return value.toFixed(3);
  if (integerColumns.has(key)) return Math.round(value).toLocaleString("zh-CN");
  return numberFormatter.format(value);
}

function formatHeader(key: string): string {
  return columnLabels[key] || key;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { credentials: "include" });
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

function dynamicColumns(rows: ResultRow[]) {
  const fallback = ["stage", "board_type", "board_name", "error"];
  if (!rows.length) return fallback;
  const keys = new Set<string>();
  rows.forEach((row) => Object.keys(row).forEach((key) => keys.add(key)));
  return Array.from(keys);
}

export function SectorResearchPage() {
  const [payload, setPayload] = useState<SectorPayload | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("themes");
  const [status, setStatus] = useState(t.ready);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const summary = payload?.summary || {};
  const marketContext = payload?.market_context || {};
  const latestThemes = payload?.latest_themes || [];
  const latestBoards = payload?.latest_boards || [];
  const errorRows = payload?.error_rows || [];

  async function loadSectorOverview() {
    setLoading(true);
    setError(false);
    setStatus(t.loading);
    try {
      const data = await fetchJson<SectorPayload>("/api/sector/overview?source=sqlite");
      setPayload(data);
      setStatus(t.done.replace("{themes}", String(data.latest_themes?.length || 0)).replace("{boards}", String(data.latest_boards?.length || 0)));
    } catch (err) {
      setError(true);
      setStatus(`${t.failed}\uff1a${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSectorOverview();
  }, []);

  const sourceText = summary.source === "sqlite" ? t.sqlite : t.csv;
  const sourcePath = t.sourcePath.replace("{source}", sourceText).replace("{path}", summary.processed_dir || "market_data.sqlite");

  const summaryItems = [
    ["latest_trade_date", summary.latest_trade_date || "-"],
    ["theme_count", summary.theme_count ?? 0],
    ["board_count", summary.board_count ?? 0],
    ["theme_daily_rows", summary.theme_daily_rows ?? 0],
    ["stock_exposure_rows", summary.stock_exposure_rows ?? 0],
    ["error_count", summary.error_count ?? 0]
  ] as const;

  const tabs = [
    { key: "themes", label: t.themesTab },
    { key: "boards", label: t.boardsTab },
    { key: "exposure", label: t.exposureTab },
    { key: "mapping", label: t.mappingTab },
    { key: "errors", label: t.errorsTab }
  ] as const;

  return (
    <section className="sector-page-new">
      <div className="sector-header">
        <div>
          <p className="page-eyebrow">{t.eyebrow}</p>
          <h1>{t.title}</h1>
          <p className="sector-note">{t.note}</p>
        </div>
        <div className="sector-header-actions">
          <a className="secondary-link" href="/sector" target="_blank" rel="noreferrer"><ExternalLink size={14} />{t.oldPage}</a>
          <a className="secondary-link" href="#/backtests/portfolio"><ExternalLink size={14} />{t.portfolio}</a>
        </div>
      </div>

      <div className="sector-runbar">
        <button className="primary-button" type="button" disabled={loading} onClick={() => void loadSectorOverview()}><RefreshCw size={14} />{loading ? t.reading : t.load}</button>
        <button className="secondary-link" type="button" disabled={loading} onClick={() => void loadSectorOverview()}><RotateCcw size={14} />{t.refresh}</button>
        <p className={error ? "sector-status error" : "sector-status"}>{status}</p>
      </div>

      <section className="sector-summary">
        <div className="summary-intro">
          <p className="page-eyebrow">{t.summaryEyebrow}</p>
          <h2>{t.summaryTitle}</h2>
          <p>{sourcePath}</p>
        </div>
        <div className="metric-strip sector-metrics">
          {summaryItems.map(([key, value]) => <div className="metric-tile" key={key}><span>{formatHeader(key)}</span><strong>{formatValue(key, value)}</strong></div>)}
        </div>
      </section>

      <MarketPanel marketContext={marketContext} />

      <section className="sector-results">
        <div className="result-tabs" role="tablist" aria-label={t.title}>
          {tabs.map((tab) => <button key={tab.key} type="button" className={activeTab === tab.key ? "active" : ""} onClick={() => setActiveTab(tab.key)}>{tab.label}</button>)}
        </div>
        {activeTab === "themes" && <ThemesPanel rows={latestThemes} />}
        {activeTab === "boards" && <Panel eyebrow={t.boardsTab} title={t.boardTitle} note={t.boardNote}><DataTable rows={latestBoards} columns={boardColumns} /></Panel>}
        {activeTab === "exposure" && <ExposurePanel payload={payload} />}
        {activeTab === "mapping" && <Panel eyebrow={t.mappingTab} title={t.mappingTitle} note={t.mappingNote}><DataTable rows={payload?.mapping_rows || []} columns={mappingColumns} /></Panel>}
        {activeTab === "errors" && <ErrorsPanel messages={payload?.messages || []} rows={errorRows} />}
      </section>
    </section>
  );
}

function MarketPanel({ marketContext }: { marketContext: MarketContext }) {
  const indexes = marketContext.indexes || [];
  const ready = marketContext.status === "ready" && indexes.length > 0;
  return (
    <section className="sector-panel sector-market-panel">
      <div className="panel-header sector-panel-head">
        <div><p className="page-eyebrow">{t.marketEyebrow}</p><h2>{t.marketTitle}</h2></div>
        <p>{marketContext.note || t.marketDefaultNote}</p>
      </div>
      {!ready ? <div className="sector-market-empty"><strong>{t.marketEmptyTitle}</strong><span>{t.readonly}</span><p>{marketContext.note || t.noMarket}</p></div> : <div className="sector-market-grid">{indexes.map((item, index) => <MarketCard key={`${item.code || item.name || index}`} item={item} />)}</div>}
    </section>
  );
}

function MarketCard({ item }: { item: MarketIndex }) {
  return (
    <article className={`sector-market-card tone-${item.tone || "neutral"}`}>
      <div className="sector-market-card-head"><strong>{item.name || item.code || "-"}</strong><span>{item.state || "\u9707\u8361"}</span></div>
      <div className="sector-market-main"><span>{t.close}</span><strong>{formatValue("close", item.close)}</strong></div>
      <dl>
        <div><dt>{t.dayPct}</dt><dd>{formatValue("pct_chg", item.pct_chg)}</dd></div>
        <div><dt>{t.m5}</dt><dd>{formatValue("m5", item.m5)}</dd></div>
        <div><dt>{t.m20}</dt><dd>{formatValue("m20", item.m20)}</dd></div>
        <div><dt>{t.m60}</dt><dd>{formatValue("m60", item.m60)}</dd></div>
      </dl>
    </article>
  );
}

function ThemesPanel({ rows }: { rows: ResultRow[] }) {
  const maxScore = useMemo(() => Math.max(...rows.slice(0, 12).map((row) => Number(row.theme_score || 0)), 0.01), [rows]);
  return (
    <Panel eyebrow={t.themesTab} title={t.themeTitle} note={t.themeNote}>
      <div className="sector-chart">
        {rows.length ? rows.slice(0, 12).map((row, index) => {
          const score = Number(row.theme_score || 0);
          const width = Math.max((score / maxScore) * 100, 2);
          return <div className="sector-bar-row" key={`${row.theme_name || index}`}><span>{formatValue("theme_name", row.theme_name)}</span><div><i style={{ width: `${width}%` }} /></div><strong>{formatValue("theme_score", score)}</strong></div>;
        }) : <p className="sector-empty-note">{t.noChart}</p>}
      </div>
      <DataTable rows={rows} columns={themeColumns} />
    </Panel>
  );
}

function ExposurePanel({ payload }: { payload: SectorPayload | null }) {
  return (
    <Panel eyebrow={t.exposureTab} title={t.exposureTitle} note={t.exposureNote}>
      <h3 className="sector-subtitle">{t.exposureCount}</h3>
      <p className="sector-panel-note">{t.exposureCountNote}</p>
      <DataTable rows={payload?.theme_exposure_counts || []} columns={themeExposureCountColumns} />
      <h3 className="sector-subtitle">{t.exposureDetail}</h3>
      <DataTable rows={payload?.stock_exposure || []} columns={exposureColumns} />
    </Panel>
  );
}

function ErrorsPanel({ messages, rows }: { messages: string[]; rows: ResultRow[] }) {
  return (
    <Panel eyebrow={t.errorsTab} title={t.errorsTitle} note={t.errorsNote}>
      <div className="sector-message-box">{messages.length ? messages.map((message, index) => <p key={index}>{message}</p>) : <p>{t.noMessages}</p>}</div>
      <DataTable rows={rows} columns={dynamicColumns(rows)} />
    </Panel>
  );
}

function Panel({ eyebrow, title, note, children }: { eyebrow: string; title: string; note: string; children: ReactNode }) {
  return <div className="sector-tab-panel"><div className="panel-header sector-panel-head"><div><p className="page-eyebrow">{eyebrow}</p><h2>{title}</h2></div><p>{note}</p></div>{children}</div>;
}

function DataTable({ rows, columns }: { rows: ResultRow[]; columns: string[] }) {
  if (!rows.length) return <div className="empty-state sector-empty-state">{t.noRows}</div>;
  const rowKeys = Array.from(rows.reduce((keys, row) => { Object.keys(row).forEach((key) => keys.add(key)); return keys; }, new Set<string>()));
  const visibleColumns = [...columns.filter((key) => rowKeys.includes(key)), ...rowKeys.filter((key) => !columns.includes(key))];
  return <div className="table-wrap sector-table-wrap"><table><thead><tr>{visibleColumns.map((key) => <th key={key}>{formatHeader(key)}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{visibleColumns.map((key) => <td key={key}>{formatValue(key, row[key])}</td>)}</tr>)}</tbody></table></div>;
}
