const paperForm = document.getElementById("paperForm");
const runPaperBtn = document.getElementById("runPaperBtn");
const refreshQuotesBtn = document.getElementById("refreshQuotesBtn");
const loadLedgerBtn = document.getElementById("loadLedgerBtn");
const reloadTemplatesBtn = document.getElementById("reloadTemplatesBtn");
const paperStatus = document.getElementById("paperStatus");
const templateStatus = document.getElementById("templateStatus");
const paperSummaryGrid = document.getElementById("paperSummaryGrid");
const templateSelect = document.getElementById("templateSelect");
const configPathInput = document.getElementById("configPath");
const configDirInput = document.getElementById("configDir");
const loadTemplateBtn = document.getElementById("loadTemplateBtn");
const newTemplateBtn = document.getElementById("newTemplateBtn");
const saveTemplateBtn = document.getElementById("saveTemplateBtn");
const saveAsTemplateBtn = document.getElementById("saveAsTemplateBtn");
const deleteTemplateBtn = document.getElementById("deleteTemplateBtn");
const pendingTable = document.getElementById("pendingTable");
const tradeTable = document.getElementById("tradeTable");
const holdingTable = document.getElementById("holdingTable");
const assetTable = document.getElementById("assetTable");
const logTable = document.getElementById("logTable");
const paperTabButtons = Array.from(document.querySelectorAll("[data-tab]"));
const paperTabPanels = Array.from(document.querySelectorAll("[data-tab-panel]"));
const templateFields = {
  file_name: document.getElementById("tplFileName"),
  account_id: document.getElementById("tplAccountId"),
  account_name: document.getElementById("tplAccountName"),
  initial_cash: document.getElementById("tplInitialCash"),
  processed_dir: document.getElementById("tplProcessedDir"),
  buy_condition: document.getElementById("tplBuyCondition"),
  sell_condition: document.getElementById("tplSellCondition"),
  score_expression: document.getElementById("tplScoreExpression"),
  top_n: document.getElementById("tplTopN"),
  entry_offset: document.getElementById("tplEntryOffset"),
  min_hold_days: document.getElementById("tplMinHoldDays"),
  max_hold_days: document.getElementById("tplMaxHoldDays"),
  buy_quantity_mode: document.getElementById("tplBuyQuantityMode"),
  buy_shares: document.getElementById("tplBuyShares"),
  buy_lot_size: document.getElementById("tplBuyLotSize"),
  min_buy_amount: document.getElementById("tplMinBuyAmount"),
  buy_min_close: document.getElementById("tplBuyMinClose"),
  buy_max_close: document.getElementById("tplBuyMaxClose"),
  price_primary: document.getElementById("tplPricePrimary"),
  price_fallback: document.getElementById("tplPriceFallback"),
  price_field: document.getElementById("tplPriceField"),
  buy_fee_rate: document.getElementById("tplBuyFeeRate"),
  sell_fee_rate: document.getElementById("tplSellFeeRate"),
  stamp_tax_sell: document.getElementById("tplStampTaxSell"),
  slippage_bps: document.getElementById("tplSlippageBps"),
  min_commission: document.getElementById("tplMinCommission"),
  ledger_path: document.getElementById("tplLedgerPath"),
  log_dir: document.getElementById("tplLogDir"),
  skip_if_holding: document.getElementById("tplSkipIfHolding"),
  skip_if_pending_order: document.getElementById("tplSkipIfPendingOrder"),
  strict_execution: document.getElementById("tplStrictExecution"),
};

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

function setTemplateStatus(text, error = false) {
  templateStatus.textContent = text;
  templateStatus.style.color = error ? "#8a2f13" : "";
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

function numberValue(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function intValue(value, fallback = 0) {
  return Math.round(numberValue(value, fallback));
}

function chinaDateStamp(date = new Date()) {
  if (typeof Intl !== "undefined" && typeof Intl.DateTimeFormat === "function") {
    const formatter = new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
    const parts = formatter.formatToParts(date);
    const year = parts.find((part) => part.type === "year")?.value || "";
    const month = parts.find((part) => part.type === "month")?.value || "";
    const day = parts.find((part) => part.type === "day")?.value || "";
    if (year && month && day) {
      return `${year}${month}${day}`;
    }
  }
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60 * 1000);
  return local.toISOString().slice(0, 10).replaceAll("-", "");
}

function defaultTemplateValues() {
  const suffix = chinaDateStamp();
  return {
    file_name: `new_paper_account_${suffix}.yaml`,
    account_id: `新账户_${suffix}`,
    account_name: `新模拟账户_${suffix}`,
    initial_cash: 100000,
    processed_dir: "data_bundle/processed_qfq_theme_focus_top100",
    buy_condition: "m20>0",
    sell_condition: "",
    score_expression: "m20",
    top_n: 5,
    entry_offset: 1,
    min_hold_days: 0,
    max_hold_days: 15,
    buy_quantity_mode: "固定股数",
    buy_shares: 200,
    buy_lot_size: 100,
    min_buy_amount: 10000,
    buy_min_close: 0,
    buy_max_close: 150,
    price_primary: "东方财富",
    price_fallback: "腾讯股票",
    price_field: "开盘价",
    buy_fee_rate: 0.00003,
    sell_fee_rate: 0.00003,
    stamp_tax_sell: 0,
    slippage_bps: 3,
    min_commission: 0,
    ledger_path: `paper_trading/accounts/新账户_${suffix}.xlsx`,
    log_dir: "paper_trading/logs",
    skip_if_holding: true,
    skip_if_pending_order: true,
    strict_execution: true,
  };
}

function populateTemplateEditor(data = {}) {
  const merged = { ...defaultTemplateValues(), ...data };
  Object.entries(templateFields).forEach(([key, el]) => {
    if (!el) {
      return;
    }
    if (el.type === "checkbox") {
      el.checked = Boolean(merged[key]);
    } else {
      el.value = merged[key] ?? "";
    }
  });
}

function collectTemplatePayload(overwriteExisting) {
  return {
    config_dir: configDirInput.value.trim() || "configs/paper_accounts",
    config_path: configPathInput.value.trim(),
    file_name: templateFields.file_name.value.trim(),
    overwrite_existing: overwriteExisting,
    account_id: templateFields.account_id.value.trim(),
    account_name: templateFields.account_name.value.trim(),
    initial_cash: numberValue(templateFields.initial_cash.value, 100000),
    processed_dir: templateFields.processed_dir.value.trim(),
    buy_condition: templateFields.buy_condition.value.trim(),
    sell_condition: templateFields.sell_condition.value.trim(),
    score_expression: templateFields.score_expression.value.trim(),
    top_n: intValue(templateFields.top_n.value, 5),
    entry_offset: intValue(templateFields.entry_offset.value, 1),
    min_hold_days: intValue(templateFields.min_hold_days.value, 0),
    max_hold_days: intValue(templateFields.max_hold_days.value, 15),
    buy_quantity_mode: templateFields.buy_quantity_mode.value.trim() || "固定股数",
    buy_shares: intValue(templateFields.buy_shares.value, 200),
    buy_lot_size: intValue(templateFields.buy_lot_size.value, 100),
    min_buy_amount: numberValue(templateFields.min_buy_amount.value, 10000),
    buy_min_close: numberValue(templateFields.buy_min_close.value, 0),
    buy_max_close: numberValue(templateFields.buy_max_close.value, 150),
    price_primary: templateFields.price_primary.value.trim() || "东方财富",
    price_fallback: templateFields.price_fallback.value.trim(),
    price_field: templateFields.price_field.value || "开盘价",
    skip_if_holding: templateFields.skip_if_holding.checked,
    skip_if_pending_order: templateFields.skip_if_pending_order.checked,
    strict_execution: templateFields.strict_execution.checked,
    buy_fee_rate: numberValue(templateFields.buy_fee_rate.value, 0.00003),
    sell_fee_rate: numberValue(templateFields.sell_fee_rate.value, 0.00003),
    stamp_tax_sell: numberValue(templateFields.stamp_tax_sell.value, 0),
    slippage_bps: numberValue(templateFields.slippage_bps.value, 3),
    min_commission: numberValue(templateFields.min_commission.value, 0),
    ledger_path: templateFields.ledger_path.value.trim(),
    log_dir: templateFields.log_dir.value.trim() || "paper_trading/logs",
  };
}

function setTemplateButtonsDisabled(disabled) {
  [loadTemplateBtn, newTemplateBtn, saveTemplateBtn, saveAsTemplateBtn, deleteTemplateBtn].forEach((button) => {
    button.disabled = disabled;
  });
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
  const data = await fetchJson(`/api/paper/templates?config_dir=${configDir}`);
  const previousValue = configPathInput.value.trim();
  templateSelect.innerHTML = "";
  if (!data.templates.length) {
    templateSelect.appendChild(new Option("没有找到模板，可手动填写路径", ""));
    setPaperStatus("没有找到模板，请检查模板目录或手动填写模板路径。", true);
    populateTemplateEditor();
    setTemplateStatus("没有找到模板，可以先填写新模板后保存。");
    return;
  }
  data.templates.forEach((item) => {
    const label = item.error ? `${item.account_id}：读取失败` : `${item.account_name}（${item.account_id}）`;
    const option = new Option(label, item.config_path || "");
    option.dataset.ledgerPath = item.ledger_path || "";
    templateSelect.appendChild(option);
  });
  if (previousValue && Array.from(templateSelect.options).some((option) => option.value === previousValue)) {
    templateSelect.value = previousValue;
  }
  configPathInput.value = templateSelect.value;
  setPaperStatus(`已读取 ${data.templates.length} 个模拟账户模板，正在读取账本。`);
  await loadCurrentTemplate(false);
  await loadLedger(false);
}

templateSelect.addEventListener("change", () => {
  configPathInput.value = templateSelect.value;
  loadCurrentTemplate(false).catch((error) => setTemplateStatus(`读取模板失败：${error.message}`, true));
  loadLedger(false).catch((error) => setPaperStatus(`读取账本失败：${error.message}`, true));
});

reloadTemplatesBtn.addEventListener("click", async () => {
  try {
    await loadTemplates();
  } catch (error) {
    setPaperStatus(`读取模板失败：${error.message}`, true);
  }
});

async function loadCurrentTemplate(showStatus = true) {
  const configPath = configPathInput.value.trim();
  if (!configPath) {
    populateTemplateEditor();
    setTemplateStatus("未选择模板，可以新建一个模板。");
    return;
  }
  if (showStatus) {
    setTemplateStatus("正在载入模板...");
  }
  const params = new URLSearchParams({
    config_path: configPath,
    config_dir: configDirInput.value.trim() || "configs/paper_accounts",
  });
  const data = await fetchJson(`/api/paper/template?${params.toString()}`);
  populateTemplateEditor(data);
  setTemplateStatus(`模板已载入：${data.config_path}；账本${data.ledger_exists ? "已存在" : "尚未创建"}。`);
}

loadTemplateBtn.addEventListener("click", async () => {
  try {
    await loadCurrentTemplate(true);
  } catch (error) {
    setTemplateStatus(`读取模板失败：${error.message}`, true);
  }
});

newTemplateBtn.addEventListener("click", () => {
  configPathInput.value = "";
  templateSelect.value = "";
  populateTemplateEditor();
  setTemplateStatus("已初始化新模板。保存前请确认账户编号、文件名和账本路径不会与旧模板冲突。");
});

async function saveTemplate(overwriteExisting) {
  setTemplateButtonsDisabled(true);
  setTemplateStatus(overwriteExisting ? "正在保存模板..." : "正在另存为新模板...");
  try {
    const payload = collectTemplatePayload(overwriteExisting);
    const data = await fetchJson("/api/paper/template", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const savedPath = data.template.config_path;
    configPathInput.value = savedPath;
    await loadTemplates();
    configPathInput.value = savedPath;
    templateSelect.value = savedPath;
    populateTemplateEditor(data.template);
    setTemplateStatus(data.message || "模板已保存；Excel 账本未被修改。");
  } catch (error) {
    setTemplateStatus(`保存失败：${error.message}`, true);
  } finally {
    setTemplateButtonsDisabled(false);
  }
}

saveTemplateBtn.addEventListener("click", () => saveTemplate(true));
saveAsTemplateBtn.addEventListener("click", () => saveTemplate(false));

deleteTemplateBtn.addEventListener("click", async () => {
  const configPath = configPathInput.value.trim();
  if (!configPath) {
    setTemplateStatus("请先选择要删除的模板。", true);
    return;
  }
  if (!window.confirm("只删除 YAML 模板，不删除 Excel 账本。确认删除当前模板吗？")) {
    return;
  }
  setTemplateButtonsDisabled(true);
  setTemplateStatus("正在删除模板...");
  try {
    const params = new URLSearchParams({
      config_path: configPath,
      config_dir: configDirInput.value.trim() || "configs/paper_accounts",
    });
    const data = await fetchJson(`/api/paper/template?${params.toString()}`, { method: "DELETE" });
    configPathInput.value = "";
    await loadTemplates();
    setTemplateStatus(data.message || "模板已删除；Excel 账本保留不动。");
  } catch (error) {
    setTemplateStatus(`删除失败：${error.message}`, true);
  } finally {
    setTemplateButtonsDisabled(false);
  }
});

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

loadTemplates().catch((error) => setPaperStatus(`读取模板失败：${error.message}`, true));
