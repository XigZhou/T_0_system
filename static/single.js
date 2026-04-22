const singleForm = document.getElementById("singleForm");
const singleStatus = document.getElementById("singleStatus");
const singleSummaryGrid = document.getElementById("singleSummaryGrid");
const singleStockTitle = document.getElementById("singleStockTitle");
const metricExplainTable = document.getElementById("metricExplainTable");
const singleTradeTable = document.getElementById("singleTradeTable");
const singleSignalTable = document.getElementById("singleSignalTable");
const singleKlineChart = document.getElementById("singleKlineChart");

let klineChart = null;

function buildSinglePayload() {
  return {
    excel_path: document.getElementById("excelPath").value.trim(),
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
  const head = `<thead><tr>${orderedKeys.map((key) => `<th>${key}</th>`).join("")}</tr></thead>`;
  const body = `<tbody>${rows
    .map(
      (row) =>
        `<tr>${orderedKeys
          .map((key) => `<td>${formatSingleValue(row[key])}</td>`)
          .join("")}</tr>`
    )
    .join("")}</tbody>`;
  target.innerHTML = head + body;
}

function renderMetricDefinitions(rows) {
  renderSimpleTable(metricExplainTable, rows, ["label", "key", "formula", "meaning"]);
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
    singleKlineChart.innerHTML = '<div class="empty">ECharts 未加载</div>';
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
    legend: { top: 6, data: ["K线", "成交量"] },
    axisPointer: { link: [{ xAxisIndex: [0, 1] }] },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      formatter: (params) => {
        const candle = params.find((item) => item.seriesName === "K线");
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
        name: "K线",
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
    if (klineChart) {
      klineChart.resize();
    }
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
    throw new Error(data.detail || `request failed: ${response.status}`);
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
