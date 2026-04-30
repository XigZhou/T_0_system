const dailyForm = document.getElementById("dailyForm");
const runDailyBtn = document.getElementById("runDailyBtn");
const clearHoldingsBtn = document.getElementById("clearHoldingsBtn");
const dailyStatus = document.getElementById("dailyStatus");
const dailySummaryGrid = document.getElementById("dailySummaryGrid");
const dailyBuyTable = document.getElementById("dailyBuyTable");
const dailySellTable = document.getElementById("dailySellTable");
const dailyHoldingTable = document.getElementById("dailyHoldingTable");
const dailyTabButtons = Array.from(document.querySelectorAll("[data-tab]"));
const dailyTabPanels = Array.from(document.querySelectorAll("[data-tab-panel]"));

const PERCENT_KEYS = new Set([
  "holding_return",
  "best_return_since_entry",
  "drawdown_from_peak",
]);

const COLUMN_LABELS = {
  best_return_since_entry: "持仓以来最大收益",
  buy_date: "买入日期",
  buy_price: "买入价",
  condition_note: "条件说明",
  current_raw_close: "今日未复权收盘价",
  drawdown_from_peak: "从高点回撤",
  estimated_budget: "目标资金",
  estimated_shares: "估算股数",
  holding_days: "持有天数",
  holding_return: "当前浮盈",
  name: "股票名称",
  open_check: "开盘复核",
  planned_buy_date: "计划买入日",
  planned_sell_date: "计划卖出日",
  rank: "排名",
  reason: "说明",
  score: "评分",
  sell_reason: "卖出原因",
  shares: "股数",
  signal_date: "信号日期",
  signal_raw_close: "信号日未复权收盘价",
  status: "状态",
  symbol: "股票代码",
};

function setDailyActiveTab(tabName) {
  dailyTabButtons.forEach((button) => {
    const isActive = button.dataset.tab === tabName;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  dailyTabPanels.forEach((panel) => {
    const isActive = panel.dataset.tabPanel === tabName;
    panel.classList.toggle("active", isActive);
    panel.hidden = !isActive;
  });
}

dailyTabButtons.forEach((button) => {
  button.addEventListener("click", () => setDailyActiveTab(button.dataset.tab));
});

if (dailyTabButtons.length) {
  const initialTab = dailyTabButtons.find((button) => button.classList.contains("active"))?.dataset.tab || dailyTabButtons[0].dataset.tab;
  setDailyActiveTab(initialTab);
}

function setDailyStatus(text, error = false) {
  dailyStatus.textContent = text;
  dailyStatus.style.color = error ? "#8a2f13" : "";
}

function formatValue(key, value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (PERCENT_KEYS.has(key) && typeof value === "number") {
    return `${(value * 100).toFixed(2)}%`;
  }
  if (typeof value === "number") {
    const absValue = Math.abs(value);
    return value.toLocaleString("zh-CN", { maximumFractionDigits: absValue >= 1000 ? 2 : 6 });
  }
  return String(value);
}

function formatHeader(key) {
  return COLUMN_LABELS[key] || key;
}

function renderTable(el, rows, preferredOrder = []) {
  const wrap = el.closest(".table-wrap");
  if (!rows || !rows.length) {
    el.innerHTML = "";
    if (wrap) {
      const currentEmpty = wrap.querySelector(".empty");
      if (!currentEmpty) {
        wrap.appendChild(Object.assign(document.createElement("div"), { className: "empty", textContent: "暂无结果" }));
      }
    }
    return;
  }
  if (wrap) {
    const currentEmpty = wrap.querySelector(".empty");
    if (currentEmpty) {
      currentEmpty.remove();
    }
    if (!wrap.contains(el)) {
      wrap.appendChild(el);
    }
  }
  const allKeys = Array.from(
    rows.reduce((acc, row) => {
      Object.keys(row).forEach((key) => acc.add(key));
      return acc;
    }, new Set())
  );
  const orderedKeys = [
    ...preferredOrder.filter((key) => allKeys.includes(key)),
    ...allKeys.filter((key) => !preferredOrder.includes(key)),
  ];
  const thead = `<thead><tr>${orderedKeys.map((key) => `<th>${formatHeader(key)}</th>`).join("")}</tr></thead>`;
  const tbody = `<tbody>${rows
    .map((row) => `<tr>${orderedKeys.map((key) => `<td>${formatValue(key, row[key])}</td>`).join("")}</tr>`)
    .join("")}</tbody>`;
  el.innerHTML = `${thead}${tbody}`;
}

function parseHoldings(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, idx) => {
      const parts = line.split(",").map((part) => part.trim());
      if (parts.length < 4) {
        throw new Error(`第 ${idx + 1} 行持仓格式不正确，应为：股票代码,买入日期,买入价,股数,股票名称`);
      }
      const [symbol, buyDate, buyPrice, shares, name = ""] = parts;
      const priceValue = Number(buyPrice);
      const shareValue = Number(shares);
      if (!symbol || !buyDate || !Number.isFinite(priceValue) || !Number.isFinite(shareValue)) {
        throw new Error(`第 ${idx + 1} 行持仓存在空值或数字不正确`);
      }
      return {
        symbol,
        buy_date: buyDate,
        buy_price: priceValue,
        shares: Math.trunc(shareValue),
        name,
      };
    });
}

function buildPayload() {
  return {
    processed_dir: document.getElementById("processedDir").value.trim(),
    signal_date: document.getElementById("signalDate").value.trim(),
    buy_condition: document.getElementById("buyCondition").value.trim(),
    sell_condition: document.getElementById("sellCondition").value.trim(),
    score_expression: document.getElementById("scoreExpression").value.trim(),
    top_n: Number(document.getElementById("topN").value),
    entry_offset: Number(document.getElementById("entryOffset").value),
    min_hold_days: Number(document.getElementById("minHoldDays").value),
    max_hold_days: Number(document.getElementById("maxHoldDays").value),
    per_trade_budget: Number(document.getElementById("perTradeBudget").value),
    lot_size: Number(document.getElementById("lotSize").value),
    holdings: parseHoldings(document.getElementById("holdingsText").value),
  };
}

function renderSummary(summary = {}) {
  const keys = [
    ["signal_date", "信号日期"],
    ["planned_buy_date", "计划买入日"],
    ["buy_candidate_count", "买入候选数"],
    ["sell_signal_count", "卖出提醒数"],
    ["holding_count", "输入持仓数"],
    ["date_note", "日期说明"],
  ];
  dailySummaryGrid.innerHTML = keys
    .map(([key, label]) => `<div class="metric"><p class="metric-label">${label}</p><p class="metric-value">${formatValue(key, summary[key])}</p></div>`)
    .join("");
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败：${response.status}`);
  }
  return response;
}

function applyResult(result) {
  renderSummary(result.summary);
  renderTable(dailyBuyTable, result.buy_rows, ["signal_date", "planned_buy_date", "symbol", "name", "rank", "score", "signal_raw_close", "estimated_shares", "estimated_budget", "open_check"]);
  renderTable(dailySellTable, result.sell_rows, ["signal_date", "planned_sell_date", "symbol", "name", "shares", "buy_date", "buy_price", "current_raw_close", "holding_return", "best_return_since_entry", "drawdown_from_peak", "sell_reason", "open_check"]);
  renderTable(dailyHoldingTable, result.holding_rows, ["signal_date", "symbol", "name", "shares", "buy_date", "buy_price", "current_raw_close", "holding_days", "holding_return", "best_return_since_entry", "drawdown_from_peak", "sell_reason", "condition_note"]);
  setDailyStatus(`计划生成完成：载入 ${result.diagnostics.file_count} 个文件，使用 ${result.summary.signal_date}。`);
}

dailyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  runDailyBtn.disabled = true;
  setDailyStatus("正在生成每日计划...");
  try {
    const payload = buildPayload();
    const response = await postJson("/api/daily-plan", payload);
    const result = await response.json();
    applyResult(result);
  } catch (error) {
    setDailyStatus(`生成失败：${error.message}`, true);
  } finally {
    runDailyBtn.disabled = false;
  }
});

clearHoldingsBtn.addEventListener("click", () => {
  document.getElementById("holdingsText").value = "";
  setDailyStatus("已清空持仓输入。");
});
