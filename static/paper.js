const paperForm = document.getElementById("paperForm");
const runPaperBtn = document.getElementById("runPaperBtn");
const refreshQuotesBtn = document.getElementById("refreshQuotesBtn");
const loadLedgerBtn = document.getElementById("loadLedgerBtn");
const reloadTemplatesBtn = document.getElementById("reloadTemplatesBtn");
const paperStatus = document.getElementById("paperStatus");
const paperSummaryGrid = document.getElementById("paperSummaryGrid");
const templateSelect = document.getElementById("templateSelect");
const configPathInput = document.getElementById("configPath");
const configDirInput = document.getElementById("configDir");
const manageTemplatesBtn = document.getElementById("manageTemplatesBtn");
const manageTemplatesHeaderLink = document.getElementById("manageTemplatesHeaderLink");
const pendingTable = document.getElementById("pendingTable");
const tradeTable = document.getElementById("tradeTable");
const holdingTable = document.getElementById("holdingTable");
const assetTable = document.getElementById("assetTable");
const logTable = document.getElementById("logTable");
const paperTabButtons = Array.from(document.querySelectorAll("[data-tab]"));
const paperTabPanels = Array.from(document.querySelectorAll("[data-tab-panel]"));

const TABLE_HEADER_LABELS = {
  累计收益: "累计收益率",
};

const PERCENT_FIELDS = new Set(["浮动收益率", "收益率", "累计收益", "累计收益率"]);
const MONEY_FIELDS = new Set([
  "现金",
  "持仓市值",
  "总资产",
  "初始资金",
  "最低买入金额",
  "成交金额",
  "手续费",
  "印花税",
  "总金额",
  "买入成本",
  "实现盈亏",
  "现金余额",
  "买入成交金额",
  "买入手续费",
  "买入总成本",
  "当前市值",
  "浮动盈亏",
  "cash",
  "market_value",
  "total_equity",
]);
const PRICE_FIELDS = new Set(["信号收盘价", "成交价格", "买入价格", "当前价格"]);
const DATE_FIELDS = new Set([
  "信号日期",
  "交易日期",
  "买入日期",
  "最后估值日期",
  "计划执行日期",
  "日期",
  "signal_date",
  "trade_date",
]);
const INTEGER_FIELDS = new Set([
  "planned_buy_count",
  "planned_sell_count",
  "price_filtered_count",
  "added_order_count",
  "executed_count",
  "failed_count",
  "updated_holding_count",
  "failed_holding_count",
  "order_count",
  "trade_count",
  "holding_count",
  "asset_count",
  "log_count",
  "计划股数",
  "股数",
  "持有天数",
  "排名",
]);

const SUMMARY_LABELS = {
  account_id: "账户编号",
  account_name: "账户名称",
  action: "执行动作",
  signal_date: "信号日期",
  trade_date: "交易日期",
  planned_buy_count: "计划买入",
  planned_sell_count: "计划卖出",
  price_filtered_count: "价格过滤",
  added_order_count: "新增订单",
  executed_count: "成交订单",
  failed_count: "失败订单",
  updated_holding_count: "更新持仓",
  failed_holding_count: "刷新失败",
  cash: "现金",
  market_value: "持仓市值",
  total_equity: "总资产",
  market_status: "行情状态",
  quote_source: "行情源",
  ledger_path: "账本路径",
  ledger_exists: "账本存在",
  order_count: "订单总数",
  trade_count: "成交总数",
  holding_count: "持仓数量",
  asset_count: "资产记录",
  log_count: "日志记录",
  last_log_time: "最后日志时间",
  last_log_action: "最后日志动作",
  last_log_level: "最后日志级别",
  last_log_message: "最后日志内容",
};

function setPaperStatus(text, error = false) {
  paperStatus.textContent = text;
  paperStatus.style.color = error ? "#8a2f13" : "";
}

function buildTemplateManagerHref() {
  const params = new URLSearchParams();
  const configDir = configDirInput.value.trim();
  const configPath = configPathInput.value.trim();
  if (configDir) {
    params.set("config_dir", configDir);
  }
  if (configPath) {
    params.set("config_path", configPath);
  }
  const query = params.toString();
  return query ? `/paper/templates?${query}` : "/paper/templates";
}

function syncTemplateManagerLinks() {
  const href = buildTemplateManagerHref();
  [manageTemplatesBtn, manageTemplatesHeaderLink].forEach((link) => {
    if (link) {
      link.href = href;
    }
  });
}

function setPaperActiveTab(tabName) {
  paperTabButtons.forEach((button) => {
    const isActive = button.dataset.tab === tabName;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  paperTabPanels.forEach((panel) => {
    const isActive = panel.dataset.tabPanel === tabName;
    panel.classList.toggle("active", isActive);
    panel.hidden = !isActive;
  });
}

paperTabButtons.forEach((button) => {
  button.addEventListener("click", () => setPaperActiveTab(button.dataset.tab));
});

if (paperTabButtons.length) {
  setPaperActiveTab(paperTabButtons[0].dataset.tab);
}

function toFiniteNumber(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return null;
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string") {
    const cleaned = value.trim().replace(/,/g, "").replace(/%$/, "");
    if (!cleaned) {
      return null;
    }
    const parsed = Number(cleaned);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function isDateTextField(fieldName = "", value = null) {
  if (typeof value !== "string") {
    return false;
  }
  const text = value.trim();
  if (!/^\d{8}$/.test(text)) {
    return false;
  }
  return DATE_FIELDS.has(fieldName) || fieldName.endsWith("_date") || fieldName.includes("日期");
}

function formatValue(value, fieldName = "") {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (isDateTextField(fieldName, value)) {
    return String(value).trim();
  }
  const num = toFiniteNumber(value);
  if (num !== null) {
    if (PERCENT_FIELDS.has(fieldName)) {
      const rawText = typeof value === "string" ? value.trim() : "";
      const percentValue = rawText.endsWith("%") ? num : num * 100;
      return `${percentValue.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
    }
    if (MONEY_FIELDS.has(fieldName)) {
      return `${num.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} 元`;
    }
    if (PRICE_FIELDS.has(fieldName)) {
      return `${num.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 4 })} 元`;
    }
    if (INTEGER_FIELDS.has(fieldName)) {
      return Math.round(num).toLocaleString("zh-CN");
    }
    return num.toLocaleString("zh-CN", { maximumFractionDigits: Math.abs(num) >= 1000 ? 2 : 4 });
  }
  return String(value);
}

function renderSummary(summary = {}) {
  const keys = Object.keys(SUMMARY_LABELS).filter((key) => summary[key] !== undefined);
  paperSummaryGrid.innerHTML = keys
    .map((key) => `<div class="metric"><p class="metric-label">${SUMMARY_LABELS[key]}</p><p class="metric-value">${formatValue(summary[key], key)}</p></div>`)
    .join("");
}

function renderTable(el, rows) {
  const wrap = el.closest(".table-wrap");
  if (!rows || !rows.length) {
    el.innerHTML = "";
    if (wrap && !wrap.querySelector(".empty")) {
      wrap.appendChild(Object.assign(document.createElement("div"), { className: "empty", textContent: "暂无结果" }));
    }
    return;
  }
  if (wrap) {
    const empty = wrap.querySelector(".empty");
    if (empty) {
      empty.remove();
    }
  }
  const keys = Array.from(
    rows.reduce((acc, row) => {
      Object.keys(row).forEach((key) => acc.add(key));
      return acc;
    }, new Set())
  );
  el.innerHTML = `
    <thead><tr>${keys.map((key) => `<th>${TABLE_HEADER_LABELS[key] || key}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((row) => `<tr>${keys.map((key) => `<td>${formatValue(row[key], key)}</td>`).join("")}</tr>`).join("")}</tbody>
  `;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败：${response.status}`);
  }
  return response.json();
}

async function loadTemplates() {
  const configDir = encodeURIComponent(configDirInput.value.trim() || "configs/paper_accounts");
  const previousValue = configPathInput.value.trim();
  const data = await fetchJson(`/api/paper/templates?config_dir=${configDir}`);
  templateSelect.innerHTML = "";
  if (!data.templates.length) {
    templateSelect.appendChild(new Option("没有找到模板，可手动填写路径", ""));
    configPathInput.value = "";
    syncTemplateManagerLinks();
    setPaperStatus("没有找到模板，请检查模板目录或手动填写模板路径。", true);
    return;
  }
  data.templates.forEach((item) => {
    const label = item.error ? `${item.account_id}：读取失败` : `${item.account_name}（${item.account_id}）`;
    templateSelect.appendChild(new Option(label, item.config_path || ""));
  });
  if (previousValue && Array.from(templateSelect.options).some((option) => option.value === previousValue)) {
    templateSelect.value = previousValue;
  }
  configPathInput.value = templateSelect.value;
  syncTemplateManagerLinks();
  setPaperStatus(`已读取 ${data.templates.length} 个模拟账户模板，正在读取账本。`);
  await loadLedger(false);
}

function renderResult(result, statusText, preferredTab = "") {
  renderSummary(result.summary);
  renderTable(pendingTable, result.pending_order_rows);
  renderTable(tradeTable, result.trade_rows);
  renderTable(holdingTable, result.holding_rows);
  renderTable(assetTable, result.asset_rows);
  renderTable(logTable, result.log_rows);
  if (preferredTab) {
    setPaperActiveTab(preferredTab);
  }
  setPaperStatus(statusText);
}

async function loadLedger(showStatus = true) {
  const configPath = configPathInput.value.trim();
  syncTemplateManagerLinks();
  if (!configPath) {
    if (showStatus) {
      setPaperStatus("请先选择或填写模拟账户模板。", true);
    }
    return;
  }
  if (showStatus) {
    setPaperStatus("正在读取账本...");
  }
  const params = new URLSearchParams({
    config_path: configPath,
    config_dir: configDirInput.value.trim() || "configs/paper_accounts",
  });
  const result = await fetchJson(`/api/paper/ledger?${params.toString()}`);
  const existsText = result.summary.ledger_exists ? "账本读取完成" : "账本还不存在，先运行一次模拟账户会自动创建";
  renderResult(result, `${existsText}：${result.summary.ledger_path}`, result.log_rows.length ? "paper-logs" : "paper-orders");
}

templateSelect.addEventListener("change", () => {
  configPathInput.value = templateSelect.value;
  syncTemplateManagerLinks();
  loadLedger(false).catch((error) => setPaperStatus(`读取账本失败：${error.message}`, true));
});

configDirInput.addEventListener("input", syncTemplateManagerLinks);
configPathInput.addEventListener("input", syncTemplateManagerLinks);

reloadTemplatesBtn.addEventListener("click", async () => {
  try {
    await loadTemplates();
  } catch (error) {
    setPaperStatus(`读取模板失败：${error.message}`, true);
  }
});

loadLedgerBtn.addEventListener("click", async () => {
  try {
    await loadLedger(true);
  } catch (error) {
    setPaperStatus(`读取账本失败：${error.message}`, true);
  }
});

paperForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  runPaperBtn.disabled = true;
  setPaperStatus("正在运行模拟账户...");
  try {
    const payload = {
      config_path: configPathInput.value.trim(),
      config_dir: configDirInput.value.trim() || "configs/paper_accounts",
      action: document.getElementById("paperAction").value,
      trade_date: document.getElementById("tradeDate").value.trim(),
    };
    const result = await fetchJson("/api/paper/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const nextTab = result.log_rows.length ? "paper-logs" : "paper-orders";
    renderResult(result, `运行完成，账本已写入：${result.summary.ledger_path}`, nextTab);
  } catch (error) {
    setPaperStatus(`运行失败：${error.message}`, true);
  } finally {
    runPaperBtn.disabled = false;
  }
});

refreshQuotesBtn.addEventListener("click", async () => {
  refreshQuotesBtn.disabled = true;
  setPaperStatus("正在获取当前持仓最新价格...");
  try {
    const payload = {
      config_path: configPathInput.value.trim(),
      config_dir: configDirInput.value.trim() || "configs/paper_accounts",
      action: "refresh",
      trade_date: document.getElementById("tradeDate").value.trim(),
    };
    const result = await fetchJson("/api/paper/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderResult(result, `当前持仓最新价格已刷新：${result.summary.market_status || "已按行情源返回价格估值"}`, "paper-holdings");
  } catch (error) {
    setPaperStatus(`刷新最新价格失败：${error.message}`, true);
  } finally {
    refreshQuotesBtn.disabled = false;
  }
});

const locationSearch = typeof window !== "undefined" && window.location ? window.location.search : "";
const urlParams = new URLSearchParams(locationSearch);
if (urlParams.get("config_dir")) {
  configDirInput.value = urlParams.get("config_dir");
}
if (urlParams.get("config_path")) {
  configPathInput.value = urlParams.get("config_path");
}

syncTemplateManagerLinks();
loadTemplates().catch((error) => setPaperStatus(`读取模板失败：${error.message}`, true));
