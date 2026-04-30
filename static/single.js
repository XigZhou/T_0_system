const singleForm = document.getElementById("singleForm");
const singleStatus = document.getElementById("singleStatus");
const singleSummaryGrid = document.getElementById("singleSummaryGrid");
const singleStockTitle = document.getElementById("singleStockTitle");
const metricExplainTable = document.getElementById("metricExplainTable");
const singleTradeTable = document.getElementById("singleTradeTable");
const singleSignalTable = document.getElementById("singleSignalTable");
const singleKlineChart = document.getElementById("singleKlineChart");
const singleTabButtons = Array.from(document.querySelectorAll("[data-tab]"));
const singleTabPanels = Array.from(document.querySelectorAll("[data-tab-panel]"));

let klineChart = null;

const SINGLE_COLUMN_LABELS = {
  action: "操作",
  buy_signal: "买入信号",
  buy_streak: "买入连续天数",
  cash: "现金",
  cash_after: "交易后现金",
  close: "收盘价",
  equity: "权益",
  equity_after: "交易后权益",
  executed_action: "已执行操作",
  fees: "费用",
  formula: "公式",
  gross_amount: "成交金额",
  high: "最高价",
  key: "字段",
  label: "指标名称",
  low: "最低价",
  meaning: "含义",
  net_amount: "净金额",
  open: "开盘价",
  pnl_realized: "已实现盈亏",
  position: "持仓股数",
  position_after: "交易后持仓",
  position_market_value: "持仓市值",
  position_market_value_after: "交易后持仓市值",
  price: "成交价",
  reason: "说明",
  scheduled_action: "计划操作",
  scheduled_trade_date: "计划交易日",
  sell_signal: "卖出信号",
  sell_streak: "卖出连续天数",
  shares: "股数",
  signal_date: "信号日期",
  trade_date: "交易日期",
  vol: "成交量",
};

const SINGLE_VALUE_LABELS = {
  BUY: "买入",
  SELL: "卖出",
  "(ending_equity / initial_cash)^(252 / N) - 1": "(期末总资产 / 初始资金)^(252 / 交易日数) - 1",
  "(last_close - avg_cost_per_share) * ending_position": "(期末收盘价 - 每股平均成本) * 期末持仓股数",
  "ending_cash + ending_market_value": "期末现金 + 期末持仓市值",
  "ending_equity / initial_cash - 1": "期末总资产 / 初始资金 - 1",
  "max((peak_equity - equity_t) / peak_equity)": "最大值((历史峰值权益 - 当日权益) / 历史峰值权益)",
  "mean(daily_return) / std(daily_return) * sqrt(252)": "日收益均值 / 日收益标准差 * √252",
  next_day_open: "次日开盘",
  same_day_close: "当日收盘",
  "sum(盈利已实现盈亏) / abs(sum(亏损已实现盈亏))": "盈利合计 / 亏损绝对值合计",
  "buy streak reached (1) via next_day_open": "买入条件连续满足，次日开盘执行",
  "sell streak reached (1) via next_day_open": "卖出条件连续满足，次日开盘执行",
};

function resizeSingleKline() {
  if (klineChart) {
    window.requestAnimationFrame(() => klineChart?.resize());
  }
}

function setSingleActiveTab(tabName) {
  singleTabButtons.forEach((button) => {
    const isActive = button.dataset.tab === tabName;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  singleTabPanels.forEach((panel) => {
    const isActive = panel.dataset.tabPanel === tabName;
    panel.classList.toggle("active", isActive);
    panel.hidden = !isActive;
  });
  if (tabName === "kline") {
    resizeSingleKline();
  }
}

singleTabButtons.forEach((button) => {
  button.addEventListener("click", () => setSingleActiveTab(button.dataset.tab));
});

if (singleTabButtons.length) {
  const initialTab = singleTabButtons.find((button) => button.classList.contains("active"))?.dataset.tab || singleTabButtons[0].dataset.tab;
  setSingleActiveTab(initialTab);
}

function buildSinglePayload() {
  return {
    processed_dir: document.getElementById("processedDir")?.value.trim() || "",
    symbol: document.getElementById("stockQuery")?.value.trim() || "",
    excel_path: document.getElementById("excelPath")?.value.trim() || "",
    start_date: document.getElementById("startDate").value.trim(),
    end_date: document.getElementById("endDate").value.trim(),
    buy_condition: document.getElementById("buyCondition").value.trim(),
    buy_confirm_days: Number(document.getElementById("buyConfirmDays").value),
    buy_cooldown_days: Number(document.getElementById("buyCooldownDays").value),
    sell_condition: document.getElementById("sellCondition").value.trim(),
    sell_confirm_days: Number(document.getElementById("sellConfirmDays").value),
    initial_cash: Number(document.getElementById("initialCash").value),
    per_trade_budget: Number(document.getElementById("perTradeBudget").value),
    lot_size: Number(document.getElementById("lotSize").value),
    execution_timing: document.getElementById("executionTiming").value,
    buy_fee_rate: Number(document.getElementById("buyFeeRate").value),
    sell_fee_rate: Number(document.getElementById("sellFeeRate").value),
    stamp_tax_sell: Number(document.getElementById("stampTaxSell").value),
  };
}

function setSingleStatus(text, error = false) {
  singleStatus.textContent = text;
  singleStatus.style.color = error ? "#8a2f13" : "";
}

function formatSingleValue(value, asPercent = false) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (asPercent && typeof value === "number") {
    return `${(value * 100).toFixed(2)}%`;
  }
  if (typeof value === "number") {
    if (Math.abs(value) >= 1000) {
      return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
    }
    return value.toLocaleString("zh-CN", { maximumFractionDigits: 6 });
  }
  return String(value);
}

function formatSingleCellValue(key, value) {
  if (typeof value === "string") {
    if (key === "reason" && value.startsWith("buy streak reached")) {
      return "买入条件连续满足，按设置时点执行";
    }
    if (key === "reason" && value.startsWith("sell streak reached")) {
      return "卖出条件连续满足，按设置时点执行";
    }
    if (SINGLE_VALUE_LABELS[value]) {
      return SINGLE_VALUE_LABELS[value];
    }
  }
  return formatSingleValue(value);
}

function formatSingleHeader(key) {
  return SINGLE_COLUMN_LABELS[key] || key;
}

function renderSingleSummary(summary = {}) {
  const keys = [
    ["ending_equity", "期末总资产", false],
    ["total_return", "总收益率", true],
    ["annualized_return", "年化收益率", true],
    ["max_drawdown", "最大回撤", true],
    ["trade_count", "交易次数", false],
    ["buy_count", "买入次数", false],
    ["sell_count", "卖出次数", false],
    ["win_rate", "胜率", true],
    ["profit_factor", "盈亏比", false],
    ["sharpe_ratio", "夏普比率", false],
    ["realized_pnl", "已实现盈亏", false],
    ["unrealized_pnl", "未实现盈亏", false],
  ];
  singleSummaryGrid.innerHTML = keys
    .map(([key, label, asPercent]) => {
      const value = formatSingleValue(summary[key], asPercent);
      return `<div class="metric"><p class="metric-label">${label}</p><p class="metric-value">${value}</p></div>`;
    })
    .join("");
}

function renderSimpleTable(target, rows, preferredOrder = []) {
  if (!rows || rows.length === 0) {
    target.innerHTML = "<tbody><tr><td>暂无数据</td></tr></tbody>";
    return;
  }
  const keys = Array.from(
    rows.reduce((acc, row) => {
      Object.keys(row).forEach((key) => acc.add(key));
      return acc;
    }, new Set())
  );
  const orderedKeys = [
    ...preferredOrder.filter((key) => keys.includes(key)),
    ...keys.filter((key) => !preferredOrder.includes(key)),
  ];
  const head = `<thead><tr>${orderedKeys.map((key) => `<th>${formatSingleHeader(key)}</th>`).join("")}</tr></thead>`;
  const body = `<tbody>${rows
    .map(
      (row) =>
        `<tr>${orderedKeys
          .map((key) => `<td>${formatSingleCellValue(key, row[key])}</td>`)
          .join("")}</tr>`
    )
    .join("")}</tbody>`;
  target.innerHTML = head + body;
}

function renderMetricDefinitions(rows) {
  renderSimpleTable(metricExplainTable, rows, ["label", "formula", "meaning"]);
}

function buildTradeMarkers(tradeRows) {
  return tradeRows
    .filter((trade) => trade && trade.trade_date && typeof trade.price === "number")
    .map((trade) => {
      const isBuy = trade.action === "BUY";
      return {
        name: isBuy ? "买入" : "卖出",
        coord: [String(trade.trade_date), Number(trade.price)],
        value: Number(trade.price),
        symbol: isBuy ? "triangle" : "pin",
        symbolRotate: isBuy ? 0 : 180,
        symbolSize: isBuy ? 12 : 16,
        itemStyle: { color: isBuy ? "#0f9d58" : "#d93025" },
        label: {
          show: true,
          formatter: isBuy ? "买" : "卖",
          color: "#111",
          fontSize: 11,
          padding: [1, 2],
          backgroundColor: "#fff",
          borderColor: isBuy ? "#0f9d58" : "#d93025",
          borderWidth: 1,
          borderRadius: 3,
        },
      };
    });
}

function renderSingleKline(signalRows, tradeRows) {
  if (!signalRows || signalRows.length === 0) {
    singleKlineChart.innerHTML = '<div class="empty">暂无可绘制的行情数据</div>';
    return;
  }
  if (typeof echarts === "undefined") {
    singleKlineChart.innerHTML = '<div class="empty">图表库未加载</div>';
    return;
  }

  if (klineChart) {
    klineChart.dispose();
  }
  klineChart = echarts.init(singleKlineChart);

  const dates = signalRows.map((row) => String(row.trade_date || ""));
  const ohlc = signalRows.map((row) => [
    Number(row.open ?? row.close ?? 0),
    Number(row.close ?? 0),
    Number(row.low ?? row.close ?? 0),
    Number(row.high ?? row.close ?? 0),
  ]);
  const volumes = signalRows.map((row) => Number(row.vol ?? 0));
  const markers = buildTradeMarkers(tradeRows || []);

  const option = {
    animation: false,
    legend: { top: 6, data: ["蜡烛图", "成交量"] },
    axisPointer: { link: [{ xAxisIndex: [0, 1] }] },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      formatter: (params) => {
        const candle = params.find((item) => item.seriesName === "蜡烛图");
        if (!candle) {
          return "";
        }
        const row = signalRows[candle.dataIndex] || {};
        return [
          `<b>${row.trade_date || ""}</b>`,
          `开: ${formatSingleValue(row.open)}`,
          `高: ${formatSingleValue(row.high)}`,
          `低: ${formatSingleValue(row.low)}`,
          `收: ${formatSingleValue(row.close)}`,
          `量: ${formatSingleValue(row.vol)}`,
          `买入信号: ${row.buy_signal ? "是" : "否"}`,
          `卖出信号: ${row.sell_signal ? "是" : "否"}`,
        ].join("<br/>");
      },
    },
    grid: [
      { left: "7%", right: "3%", top: 36, height: "56%" },
      { left: "7%", right: "3%", top: "74%", height: "16%" },
    ],
    xAxis: [
      { type: "category", data: dates, boundaryGap: false, min: "dataMin", max: "dataMax" },
      { type: "category", gridIndex: 1, data: dates, boundaryGap: false, axisLabel: { show: false }, min: "dataMin", max: "dataMax" },
    ],
    yAxis: [
      { scale: true },
      { scale: true, gridIndex: 1, splitNumber: 2, axisLabel: { formatter: (value) => `${(value / 10000).toFixed(1)}w` } },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: 70, end: 100 },
      { type: "slider", xAxisIndex: [0, 1], bottom: 10, height: 22, start: 70, end: 100 },
    ],
    series: [
      {
        name: "蜡烛图",
        type: "candlestick",
        data: ohlc,
        itemStyle: {
          color: "#d64b4b",
          color0: "#2ca451",
          borderColor: "#d64b4b",
          borderColor0: "#2ca451",
        },
        markPoint: {
          data: markers,
          tooltip: {
            formatter: (point) => `${point.name}<br/>日期: ${point.data.coord[0]}<br/>价格: ${point.value}`,
          },
        },
      },
      {
        name: "成交量",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes,
        itemStyle: { color: "#8ba2c6" },
      },
    ],
  };

  klineChart.setOption(option, true);
  window.requestAnimationFrame(() => {
    resizeSingleKline();
  });
}

async function postSingleStock(payload) {
  const response = await fetch("/api/run-single-stock", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败：${response.status}`);
  }
  return response.json();
}

async function runSingleStockBacktest(event) {
  event.preventDefault();
  setSingleStatus("正在运行单股回测...");
  try {
    const result = await postSingleStock(buildSinglePayload());
    singleStockTitle.textContent = `${result.stock_code} ${result.stock_name}`;
    renderSingleSummary(result.summary);
    renderMetricDefinitions(result.metric_definitions);
    renderSimpleTable(singleTradeTable, result.trade_rows, [
      "signal_date",
      "trade_date",
      "action",
      "price",
      "shares",
      "gross_amount",
      "fees",
      "net_amount",
      "cash_after",
      "position_after",
      "position_market_value_after",
      "equity_after",
      "pnl_realized",
      "reason",
    ]);
    renderSimpleTable(singleSignalTable, result.signal_rows, [
      "trade_date",
      "open",
      "high",
      "low",
      "close",
      "vol",
      "buy_signal",
      "sell_signal",
      "buy_streak",
      "sell_streak",
      "scheduled_action",
      "scheduled_trade_date",
      "executed_action",
      "cash",
      "position",
      "position_market_value",
      "equity",
      "reason",
    ]);
    renderSingleKline(result.signal_rows, result.trade_rows);
    setSingleStatus("单股回测完成。");
  } catch (error) {
    setSingleStatus(`回测失败: ${error.message}`, true);
  }
}

singleForm.addEventListener("submit", runSingleStockBacktest);
