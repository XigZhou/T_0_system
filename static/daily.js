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
const strategyPreset = document.getElementById("strategyPreset");
const dailyPoolUser = document.getElementById("dailyPoolUser");
const dailyStockPoolTemplateSelect = document.getElementById("dailyStockPoolTemplateSelect");
const dailyReloadPoolsBtn = document.getElementById("dailyReloadPoolsBtn");

const DEFAULT_DAILY_POOL_USERNAME = "admin";
const BASE_BUY_CONDITION = "m120>0.02,m60>0.01,m20>0.08,m10<0.16,m5<0.1,hs300_m20>0.02";
const BASE_SCORE_EXPRESSION = "m20 * 140 + (m20 - m60 / 3) * 90 + (m20 - m120 / 6) * 40 - abs(m5 - 0.03) * 55 - abs(m10 - 0.08) * 30";
const SECTOR_FILTER_CONDITION = `${BASE_BUY_CONDITION},sector_exposure_score>0,sector_strongest_theme_score>=0.6,sector_strongest_theme_rank_pct<=0.5`;
const SECTOR_SCORE_EXPRESSION = `${BASE_SCORE_EXPRESSION} + sector_strongest_theme_score * 30 + sector_exposure_score * 10 - sector_strongest_theme_rank_pct * 15`;
const STRATEGY_PRESETS = {
  base: {
    buyCondition: BASE_BUY_CONDITION,
    scoreExpression: BASE_SCORE_EXPRESSION,
    dataProfile: "auto",
    note: "已切换为基准动量预设，数据来自所选股票池模板。",
  },
  sector_filter: {
    buyCondition: SECTOR_FILTER_CONDITION,
    scoreExpression: BASE_SCORE_EXPRESSION,
    dataProfile: "sector",
    note: "板块增强预设需要 SQLite 入库 sector_* 字段后再开放。",
    disabled: true,
  },
  sector_score: {
    buyCondition: SECTOR_FILTER_CONDITION,
    scoreExpression: SECTOR_SCORE_EXPRESSION,
    dataProfile: "sector",
    note: "板块增强预设需要 SQLite 入库 sector_* 字段后再开放。",
    disabled: true,
  },
};

const PERCENT_KEYS = new Set([
  "holding_return",
  "best_return_since_entry",
  "drawdown_from_peak",
  "sector_exposure_score",
  "sector_strongest_theme_score",
  "sector_strongest_theme_rank_pct",
  "sector_strongest_theme_m20",
]);

const COLUMN_LABELS = {
  best_return_since_entry: "持仓以来最大收益",
  buy_date: "买入日期",
  buy_price: "买入价",
  condition_note: "条件说明",
  current_raw_close: "今日未复权收盘价",
  data_profile: "数据口径",
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
  sector_exposure_score: "板块主题暴露分",
  sector_strongest_theme: "最强主题",
  sector_strongest_theme_m20: "最强主题二十日动量",
  sector_strongest_theme_rank_pct: "最强主题排名百分位",
  sector_strongest_theme_score: "最强主题综合分",
  shares: "股数",
  signal_date: "信号日期",
  signal_raw_close: "信号日未复权收盘价",
  status: "状态",
  symbol: "股票代码",
};

const VALUE_LABELS = {
  auto: "自动识别",
  base: "基准口径",
  sector: "板块增强口径",
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

function currentDailyPoolUsername() {
  return DEFAULT_DAILY_POOL_USERNAME;
}

function selectedDailyPoolTemplate() {
  return dailyStockPoolTemplateSelect?.value || "";
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败：${response.status}`);
  }
  return response.json();
}

async function loadDailyPoolTemplates(showStatus = false) {
  if (!dailyStockPoolTemplateSelect) {
    return;
  }
  const username = currentDailyPoolUsername();
  if (dailyPoolUser) {
    dailyPoolUser.textContent = username;
  }
  if (showStatus) {
    setDailyStatus("正在读取股票池模板...");
  }
  const previous = dailyStockPoolTemplateSelect.value;
  const data = await fetchJson(`/api/stock-pools/templates?username=${encodeURIComponent(username)}`);
  dailyStockPoolTemplateSelect.innerHTML = "";
  if (!data.templates.length) {
    dailyStockPoolTemplateSelect.appendChild(new Option("没有找到模板，请先到股票池模板管理新建", ""));
    setDailyStatus("没有找到股票池模板，请先到 /stock-pools 新建模板。", true);
    return;
  }
  data.templates.forEach((item) => {
    dailyStockPoolTemplateSelect.appendChild(new Option(`${item.template_name}（${item.stock_count}只）`, item.template_name || ""));
  });
  const hasPrevious = previous && Array.from(dailyStockPoolTemplateSelect.options).some((option) => option.value === previous);
  dailyStockPoolTemplateSelect.value = hasPrevious ? previous : dailyStockPoolTemplateSelect.options[0].value;
  if (showStatus) {
    setDailyStatus(`已读取 ${data.templates.length} 个股票池模板。`);
  }
}

function applyStrategyPreset(presetKey, showStatus = true) {
  const preset = STRATEGY_PRESETS[presetKey] || STRATEGY_PRESETS.base;
  if (preset.disabled) {
    if (strategyPreset) {
      strategyPreset.value = "base";
    }
    return applyStrategyPreset("base", showStatus);
  }
  document.getElementById("buyCondition").value = preset.buyCondition;
  document.getElementById("scoreExpression").value = preset.scoreExpression;
  if (showStatus) {
    setDailyStatus(preset.note);
  }
}

function formatValue(key, value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (VALUE_LABELS[value]) {
    return VALUE_LABELS[value];
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
  const preset = STRATEGY_PRESETS[strategyPreset?.value] || STRATEGY_PRESETS.base;
  const templateName = selectedDailyPoolTemplate();
  if (!templateName) {
    throw new Error("请选择股票池模板");
  }
  return {
    data_source: "stock_pool",
    processed_dir: "",
    stock_pool_username: currentDailyPoolUsername(),
    stock_pool_template_name: templateName,
    data_profile: preset.dataProfile,
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
    ["data_profile", "数据口径"],
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
  renderTable(dailyBuyTable, result.buy_rows, ["signal_date", "planned_buy_date", "symbol", "name", "rank", "score", "sector_strongest_theme", "sector_strongest_theme_score", "sector_strongest_theme_rank_pct", "sector_exposure_score", "signal_raw_close", "estimated_shares", "estimated_budget", "open_check"]);
  renderTable(dailySellTable, result.sell_rows, ["signal_date", "planned_sell_date", "symbol", "name", "shares", "buy_date", "buy_price", "current_raw_close", "holding_return", "best_return_since_entry", "drawdown_from_peak", "sell_reason", "open_check"]);
  renderTable(dailyHoldingTable, result.holding_rows, ["signal_date", "symbol", "name", "shares", "buy_date", "buy_price", "current_raw_close", "holding_days", "holding_return", "best_return_since_entry", "drawdown_from_peak", "sell_reason", "condition_note"]);
  const sourceLabel = result.diagnostics.data_source === "stock_pool" ? `股票池模板 ${result.diagnostics.stock_pool_template_name}` : `${result.diagnostics.file_count} 个文件`;
  setDailyStatus(`计划生成完成：${formatValue("data_profile", result.diagnostics.data_profile)}，载入 ${sourceLabel}，使用 ${result.summary.signal_date}。`);
}

strategyPreset?.addEventListener("change", () => applyStrategyPreset(strategyPreset.value));
dailyReloadPoolsBtn?.addEventListener("click", () => {
  loadDailyPoolTemplates(true).catch((error) => setDailyStatus(`读取股票池模板失败: ${error.message}`, true));
});
applyStrategyPreset(strategyPreset?.value || "base", false);
loadDailyPoolTemplates(false).catch((error) => setDailyStatus(`读取股票池模板失败: ${error.message}`, true));

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
