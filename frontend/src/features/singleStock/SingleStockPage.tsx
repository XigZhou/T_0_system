import { useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, Play, RotateCcw } from "lucide-react";
import { formatHeader, formatValue } from "../backtests/format";
import "./singleStock.css";

type ResultRow = Record<string, unknown>;
type CurrentUser = { username?: string; role?: string; display_name?: string };

type SingleResult = {
  stock_code?: string;
  stock_name?: string;
  chart_price_basis?: string;
  summary?: Record<string, unknown>;
  metric_definitions?: ResultRow[];
  trade_rows?: ResultRow[];
  signal_rows?: ResultRow[];
};

type FormState = {
  symbol: string;
  start_date: string;
  end_date: string;
  buy_condition: string;
  sell_condition: string;
  buy_confirm_days: string;
  buy_cooldown_days: string;
  execution_timing: "next_day_open" | "same_day_close";
  sell_confirm_days: string;
  initial_cash: string;
  per_trade_budget: string;
  lot_size: string;
  buy_fee_rate: string;
  sell_fee_rate: string;
  stamp_tax_sell: string;
  max_hold_days: string;
  strict_execution: boolean;
};

type EChartsInstance = { setOption: (option: unknown, notMerge?: boolean) => void; resize: () => void; dispose: () => void };
type EChartsGlobal = { init: (el: HTMLElement) => EChartsInstance };

declare global {
  interface Window { echarts?: EChartsGlobal; }
}

const t = {
  title: "\u5355\u80a1\u56de\u6d4b",
  eyebrow: "Single Stock Backtest",
  note: "\u8f93\u5165\u5355\u53ea\u80a1\u7968\uff0c\u67e5\u770b K \u7ebf\u3001\u4e70\u5356\u70b9\u3001\u4ea4\u6613\u65e5\u5fd7\u548c\u6bcf\u65e5\u4fe1\u53f7\u3002",
  portfolio: "\u7ec4\u5408\u56de\u6d4b",
  run: "\u8fd0\u884c\u5355\u80a1\u56de\u6d4b",
  running: "\u8fd0\u884c\u4e2d...",
  reset: "\u6062\u590d\u9ed8\u8ba4",
  stockQuery: "\u80a1\u7968\u4ee3\u7801\u6216\u540d\u79f0",
  stockHint: "\u4f8b\u5982\uff1a000063 \u6216 \u4e2d\u5174\u901a\u8baf",
  startDate: "\u5f00\u59cb\u65e5\u671f",
  endDate: "\u7ed3\u675f\u65e5\u671f",
  buyCondition: "\u4e70\u5165\u6761\u4ef6",
  sellCondition: "\u5356\u51fa\u6761\u4ef6",
  buyConfirmDays: "\u4e70\u5165\u786e\u8ba4\u5929\u6570",
  buyCooldownDays: "\u4e70\u5165\u51b7\u5374\u5929\u6570",
  executionTiming: "\u6267\u884c\u65f6\u70b9",
  nextDayOpen: "\u6b21\u65e5\u5f00\u76d8",
  sameDayClose: "\u5f53\u65e5\u6536\u76d8",
  sellConfirmDays: "\u5356\u51fa\u786e\u8ba4\u5929\u6570",
  initialCash: "\u521d\u59cb\u8d44\u91d1",
  perTradeBudget: "\u6bcf\u7b14\u76ee\u6807\u8d44\u91d1",
  lotSize: "\u6bcf\u624b\u80a1\u6570",
  buyFeeRate: "\u4e70\u5165\u8d39\u7387",
  sellFeeRate: "\u5356\u51fa\u8d39\u7387",
  stampTaxSell: "\u5370\u82b1\u7a0e",
  maxHoldDays: "\u6700\u5927\u6301\u6709\u5929\u6570",
  strictExecution: "\u4e25\u683c\u6210\u4ea4",
  summaryEyebrow: "\u7ed3\u679c\u6458\u8981",
  summaryTitle: "\u5355\u80a1\u56de\u6d4b\u6458\u8981",
  metricsTab: "\u6307\u6807\u89e3\u91ca",
  klineTab: "K\u7ebf\u56fe",
  tradesTab: "\u4ea4\u6613\u65e5\u5fd7",
  signalsTab: "\u4fe1\u53f7\u8868",
  ready: "\u7b49\u5f85\u8f93\u5165\u3002",
  loading: "\u6b63\u5728\u8fd0\u884c\u5355\u80a1\u56de\u6d4b...",
  done: "\u5355\u80a1\u56de\u6d4b\u5b8c\u6210\u3002",
  failed: "\u56de\u6d4b\u5931\u8d25",
  noRows: "\u6682\u65e0\u6570\u636e",
  noChart: "\u6682\u65e0\u53ef\u7ed8\u5236\u7684\u884c\u60c5\u6570\u636e",
  chartLoading: "\u56fe\u8868\u5e93\u52a0\u8f7d\u4e2d...",
  chartBasis: "\u5f53\u524d\u4f7f\u7528{basis}\u7ed8\u5236 K \u7ebf\u56fe\uff1b\u4ea4\u6613\u6210\u4ea4\u4ecd\u6309\u9664\u6743\u4ef7\u683c\u3002",
  fallbackUser: "admin"
};

const defaultForm: FormState = {
  symbol: "",
  start_date: "",
  end_date: "",
  buy_condition: "m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02",
  sell_condition: "m20<0.08,hs300_m20<0.02",
  buy_confirm_days: "1",
  buy_cooldown_days: "0",
  execution_timing: "next_day_open",
  sell_confirm_days: "1",
  initial_cash: "100000",
  per_trade_budget: "10000",
  lot_size: "100",
  buy_fee_rate: "0.00003",
  sell_fee_rate: "0.00003",
  stamp_tax_sell: "0",
  max_hold_days: "0",
  strict_execution: true
};

const summaryKeys = ["ending_equity", "total_return", "annualized_return", "max_drawdown", "trade_count", "buy_count", "sell_count", "blocked_buy_count", "blocked_sell_count", "win_rate", "profit_factor", "sharpe_ratio", "realized_pnl", "unrealized_pnl"];
const tradeColumns = ["signal_date", "trade_date", "action", "price", "shares", "gross_amount", "fees", "net_amount", "cash_after", "position_after", "position_market_value_after", "equity_after", "pnl_realized", "reason"];
const signalColumns = ["trade_date", "open", "high", "low", "close", "vol", "buy_signal", "sell_signal", "buy_streak", "sell_streak", "scheduled_action", "scheduled_trade_date", "executed_action", "cash", "position", "position_market_value", "equity", "reason"];
const metricColumns = ["label", "formula", "meaning"];

const valueLabels: Record<string, string> = {
  BUY: "\u4e70\u5165",
  SELL: "\u5356\u51fa",
  BUY_BLOCKED: "\u4e70\u5165\u963b\u585e",
  SELL_BLOCKED: "\u5356\u51fa\u963b\u585e",
  next_day_open: "\u6b21\u65e5\u5f00\u76d8",
  same_day_close: "\u5f53\u65e5\u6536\u76d8"
};

async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { credentials: "include", ...options });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function toNumber(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function buildPayload(form: FormState, username: string) {
  return {
    data_source: "stock_pool",
    stock_pool_username: username || t.fallbackUser,
    stock_pool_template_name: "",
    stock_pool_db_path: "",
    processed_dir: "",
    excel_path: "",
    symbol: form.symbol.trim(),
    start_date: form.start_date.trim(),
    end_date: form.end_date.trim(),
    buy_condition: form.buy_condition.trim(),
    buy_confirm_days: toNumber(form.buy_confirm_days, 1),
    buy_cooldown_days: toNumber(form.buy_cooldown_days, 0),
    sell_condition: form.sell_condition.trim(),
    sell_confirm_days: toNumber(form.sell_confirm_days, 1),
    initial_cash: toNumber(form.initial_cash, 100000),
    per_trade_budget: toNumber(form.per_trade_budget, 10000),
    lot_size: toNumber(form.lot_size, 100),
    execution_timing: form.execution_timing,
    buy_fee_rate: toNumber(form.buy_fee_rate, 0.00003),
    sell_fee_rate: toNumber(form.sell_fee_rate, 0.00003),
    stamp_tax_sell: toNumber(form.stamp_tax_sell, 0),
    max_hold_days: toNumber(form.max_hold_days, 0),
    strict_execution: form.strict_execution
  };
}

function loadEcharts(): Promise<EChartsGlobal> {
  if (window.echarts) return Promise.resolve(window.echarts);
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>('script[data-echarts-loader="true"]');
    if (existing) {
      existing.addEventListener("load", () => window.echarts ? resolve(window.echarts) : reject(new Error("echarts missing")), { once: true });
      existing.addEventListener("error", () => reject(new Error("echarts load failed")), { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = "/static/vendor/echarts.min.js";
    script.async = true;
    script.dataset.echartsLoader = "true";
    script.onload = () => window.echarts ? resolve(window.echarts) : reject(new Error("echarts missing"));
    script.onerror = () => reject(new Error("echarts load failed"));
    document.head.appendChild(script);
  });
}

function displayValue(key: string, value: unknown): string {
  if (typeof value === "string" && valueLabels[value]) return valueLabels[value];
  if (key === "reason" && typeof value === "string") {
    if (value.startsWith("buy streak reached")) return "\u4e70\u5165\u6761\u4ef6\u8fde\u7eed\u6ee1\u8db3\uff0c\u6309\u8bbe\u7f6e\u65f6\u70b9\u6267\u884c";
    if (value.startsWith("sell streak reached")) return "\u5356\u51fa\u6761\u4ef6\u8fde\u7eed\u6ee1\u8db3\uff0c\u6309\u8bbe\u7f6e\u65f6\u70b9\u6267\u884c";
  }
  return formatValue(key, value);
}

export function SingleStockPage() {
  const [form, setForm] = useState<FormState>(defaultForm);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [result, setResult] = useState<SingleResult | null>(null);
  const [activeTab, setActiveTab] = useState("metrics");
  const [status, setStatus] = useState(t.ready);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstanceRef = useRef<EChartsInstance | null>(null);
  const username = currentUser?.username || t.fallbackUser;
  const summary = result?.summary || {};
  const chartBasis = result?.chart_price_basis || "\u524d\u590d\u6743\u4ef7\u683c";

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  useEffect(() => {
    let cancelled = false;
    fetchJson<{ authenticated: boolean; user?: CurrentUser | null }>("/api/auth/me")
      .then((auth) => { if (!cancelled) setCurrentUser(auth.authenticated ? auth.user || null : null); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    function resize() { chartInstanceRef.current?.resize(); }
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  useEffect(() => {
    if (activeTab !== "kline" || !result?.signal_rows?.length || !chartRef.current) return;
    let disposed = false;
    setStatus((current) => current === t.done ? current : t.chartLoading);
    loadEcharts().then((echarts) => {
      if (disposed || !chartRef.current) return;
      chartInstanceRef.current?.dispose();
      const chart = echarts.init(chartRef.current);
      chartInstanceRef.current = chart;
      chart.setOption(buildKlineOption(result.signal_rows || [], result.trade_rows || []), true);
      window.requestAnimationFrame(() => chart.resize());
    }).catch((err) => {
      if (!disposed) {
        setError(true);
        setStatus(`${t.failed}\uff1a${err instanceof Error ? err.message : String(err)}`);
      }
    });
    return () => { disposed = true; };
  }, [activeTab, result]);

  async function runBacktest() {
    setLoading(true);
    setError(false);
    setStatus(t.loading);
    try {
      const data = await fetchJson<SingleResult>("/api/run-single-stock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload(form, username))
      });
      setResult(data);
      setActiveTab("kline");
      setStatus(t.done);
    } catch (err) {
      setError(true);
      setStatus(`${t.failed}\uff1a${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  const tabs = [
    { key: "metrics", label: t.metricsTab },
    { key: "kline", label: t.klineTab },
    { key: "trades", label: t.tradesTab },
    { key: "signals", label: t.signalsTab }
  ];

  return (
    <section className="single-stock-page">
      <div className="single-header">
        <div>
          <p className="page-eyebrow">{t.eyebrow}</p>
          <h1>{t.title}</h1>
          <p className="single-note">{t.note}</p>
        </div>
        <div className="single-header-actions">
          <a className="secondary-link" href="/backtests/portfolio"><ExternalLink size={14} />{t.portfolio}</a>
        </div>
      </div>

      <div className="single-runbar">
        <label className="stock-query"><span>{t.stockQuery}</span><input value={form.symbol} placeholder={t.stockHint} onChange={(event) => update("symbol", event.target.value)} /></label>
        <Field label={t.startDate} value={form.start_date} placeholder="20200101" onChange={(value) => update("start_date", value)} />
        <Field label={t.endDate} value={form.end_date} placeholder="20251231" onChange={(value) => update("end_date", value)} />
        <button className="primary-button" type="button" disabled={loading} onClick={() => void runBacktest()}><Play size={14} />{loading ? t.running : t.run}</button>
        <button className="secondary-link" type="button" disabled={loading} onClick={() => { setForm(defaultForm); setResult(null); setStatus(t.ready); setError(false); }}><RotateCcw size={14} />{t.reset}</button>
      </div>

      <div className="single-grid">
        <section className="single-panel">
          <div className="panel-header"><h2>{t.buyCondition}</h2></div>
          <div className="single-form-grid one-col"><TextArea label={t.buyCondition} value={form.buy_condition} onChange={(value) => update("buy_condition", value)} /></div>
        </section>
        <section className="single-panel">
          <div className="panel-header"><h2>{t.sellCondition}</h2></div>
          <div className="single-form-grid one-col"><TextArea label={t.sellCondition} value={form.sell_condition} onChange={(value) => update("sell_condition", value)} /></div>
        </section>
      </div>

      <section className="single-panel">
        <div className="panel-header"><h2>{t.executionTiming}</h2></div>
        <div className="single-form-grid">
          <Field label={t.buyConfirmDays} value={form.buy_confirm_days} type="number" onChange={(value) => update("buy_confirm_days", value)} />
          <Field label={t.buyCooldownDays} value={form.buy_cooldown_days} type="number" onChange={(value) => update("buy_cooldown_days", value)} />
          <label><span>{t.executionTiming}</span><select value={form.execution_timing} onChange={(event) => update("execution_timing", event.target.value as FormState["execution_timing"])}><option value="next_day_open">{t.nextDayOpen}</option><option value="same_day_close">{t.sameDayClose}</option></select></label>
          <Field label={t.sellConfirmDays} value={form.sell_confirm_days} type="number" onChange={(value) => update("sell_confirm_days", value)} />
          <Field label={t.initialCash} value={form.initial_cash} type="number" onChange={(value) => update("initial_cash", value)} />
          <Field label={t.perTradeBudget} value={form.per_trade_budget} type="number" onChange={(value) => update("per_trade_budget", value)} />
          <Field label={t.lotSize} value={form.lot_size} type="number" onChange={(value) => update("lot_size", value)} />
          <Field label={t.buyFeeRate} value={form.buy_fee_rate} type="number" step="0.00001" onChange={(value) => update("buy_fee_rate", value)} />
          <Field label={t.sellFeeRate} value={form.sell_fee_rate} type="number" step="0.00001" onChange={(value) => update("sell_fee_rate", value)} />
          <Field label={t.stampTaxSell} value={form.stamp_tax_sell} type="number" step="0.0001" onChange={(value) => update("stamp_tax_sell", value)} />
          <Field label={t.maxHoldDays} value={form.max_hold_days} type="number" onChange={(value) => update("max_hold_days", value)} />
          <label className="single-check"><input type="checkbox" checked={form.strict_execution} onChange={(event) => update("strict_execution", event.target.checked)} /><span>{t.strictExecution}</span></label>
        </div>
      </section>

      <p className={error ? "single-status error" : "single-status"}>{status}</p>

      <section className="single-summary">
        <div className="summary-intro"><p className="page-eyebrow">{t.summaryEyebrow}</p><h2>{result?.stock_code ? `${result.stock_code} ${result.stock_name || ""}` : t.summaryTitle}</h2></div>
        <div className="metric-strip single-metrics">{summaryKeys.map((key) => <div className="metric-tile" key={key}><span>{formatHeader(key)}</span><strong>{formatValue(key, summary[key])}</strong></div>)}</div>
      </section>

      <section className="single-results">
        <div className="result-tabs">{tabs.map((tab) => <button key={tab.key} type="button" className={activeTab === tab.key ? "active" : ""} onClick={() => setActiveTab(tab.key)}>{tab.label}</button>)}</div>
        {activeTab === "metrics" && <DataTable rows={result?.metric_definitions || []} columns={metricColumns} />}
        {activeTab === "kline" && <div className="kline-wrap"><p>{t.chartBasis.replace("{basis}", chartBasis)}</p><div ref={chartRef} className="single-kline-chart">{!result?.signal_rows?.length ? t.noChart : t.chartLoading}</div></div>}
        {activeTab === "trades" && <DataTable rows={result?.trade_rows || []} columns={tradeColumns} />}
        {activeTab === "signals" && <DataTable rows={result?.signal_rows || []} columns={signalColumns} />}
      </section>
    </section>
  );
}

function Field({ label, value, onChange, type = "text", step, placeholder = "" }: { label: string; value: string; onChange: (value: string) => void; type?: string; step?: string; placeholder?: string }) {
  return <label><span>{label}</span><input type={type} step={step} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} /></label>;
}

function TextArea({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label><span>{label}</span><textarea rows={3} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function DataTable({ rows, columns }: { rows: ResultRow[]; columns: string[] }) {
  if (!rows.length) return <div className="empty-state">{t.noRows}</div>;
  const rowKeys = Array.from(rows.reduce((keys, row) => {
    Object.keys(row).forEach((key) => keys.add(key));
    return keys;
  }, new Set<string>()));
  const visibleColumns = [...columns.filter((key) => rowKeys.includes(key)), ...rowKeys.filter((key) => !columns.includes(key))];
  return <div className="table-wrap single-table-wrap"><table><thead><tr>{visibleColumns.map((key) => <th key={key}>{formatHeader(key)}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{visibleColumns.map((key) => <td key={key}>{displayValue(key, row[key])}</td>)}</tr>)}</tbody></table></div>;
}

function buildKlineOption(signalRows: ResultRow[], tradeRows: ResultRow[]) {
  const dates = signalRows.map((row) => String(row.trade_date || ""));
  const ohlc = signalRows.map((row) => [Number(row.open ?? row.close ?? 0), Number(row.close ?? 0), Number(row.low ?? row.close ?? 0), Number(row.high ?? row.close ?? 0)]);
  const volumes = signalRows.map((row) => Number(row.vol ?? 0));
  const ma = (key: string) => signalRows.map((row) => row[key] == null ? null : Number(row[key]));
  const byDate = new Map(signalRows.map((row) => [String(row.trade_date || ""), row]));
  const markers = tradeRows.filter((trade) => ["BUY", "SELL"].includes(String(trade.action || ""))).map((trade) => {
    const isBuy = trade.action === "BUY";
    const date = String(trade.trade_date || "");
    const row = byDate.get(date) || {};
    const price = Number(row.close ?? trade.price ?? 0);
    return { name: isBuy ? "\u4e70\u5165" : "\u5356\u51fa", coord: [date, price], value: price, symbol: isBuy ? "triangle" : "pin", symbolRotate: isBuy ? 0 : 180, symbolSize: isBuy ? 12 : 16, itemStyle: { color: isBuy ? "#0f9d58" : "#d93025" }, label: { show: true, formatter: isBuy ? "\u4e70" : "\u5356", color: "#111", fontSize: 11, backgroundColor: "#fff", borderWidth: 1, borderColor: isBuy ? "#0f9d58" : "#d93025", borderRadius: 3 } };
  });
  return {
    animation: false,
    legend: { top: 8, data: ["K\u7ebf", "MA5", "MA10", "MA20", "\u6210\u4ea4\u91cf"] },
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    axisPointer: { link: [{ xAxisIndex: [0, 1] }] },
    grid: [{ left: "5.5%", right: "2.5%", top: 48, height: "58%" }, { left: "5.5%", right: "2.5%", top: "76%", height: "13%" }],
    xAxis: [{ type: "category", data: dates, boundaryGap: false, axisLine: { onZero: false }, min: "dataMin", max: "dataMax" }, { type: "category", gridIndex: 1, data: dates, boundaryGap: false, axisLabel: { show: false }, min: "dataMin", max: "dataMax" }],
    yAxis: [{ scale: true }, { scale: true, gridIndex: 1, splitNumber: 2, axisLabel: { formatter: (value: number) => `${(value / 10000).toFixed(1)}w` } }],
    dataZoom: [{ type: "inside", xAxisIndex: [0, 1], start: 65, end: 100 }, { show: true, type: "slider", xAxisIndex: [0, 1], bottom: 10, height: 24, start: 65, end: 100 }],
    series: [
      { name: "K\u7ebf", type: "candlestick", data: ohlc, itemStyle: { color: "#d64b4b", color0: "#2ca451", borderColor: "#d64b4b", borderColor0: "#2ca451" }, markPoint: { data: markers } },
      { name: "MA5", type: "line", data: ma("ma5"), smooth: true, showSymbol: false, connectNulls: true, lineStyle: { width: 1.4, color: "#f0a21a" } },
      { name: "MA10", type: "line", data: ma("ma10"), smooth: true, showSymbol: false, connectNulls: true, lineStyle: { width: 1.4, color: "#2f75d6" } },
      { name: "MA20", type: "line", data: ma("ma20"), smooth: true, showSymbol: false, connectNulls: true, lineStyle: { width: 1.4, color: "#7d55c7" } },
      { name: "\u6210\u4ea4\u91cf", type: "bar", xAxisIndex: 1, yAxisIndex: 1, data: volumes, itemStyle: { color: "#8ba2c6" } }
    ]
  };
}
