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
const pendingTable = document.getElementById("pendingTable");
const tradeTable = document.getElementById("tradeTable");
const holdingTable = document.getElementById("holdingTable");
const assetTable = document.getElementById("assetTable");
const logTable = document.getElementById("logTable");
const paperTabButtons = Array.from(document.querySelectorAll("[data-tab]"));
const paperTabPanels = Array.from(document.querySelectorAll("[data-tab-panel]"));

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

function formatValue(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (typeof value === "number") {
    return value.toLocaleString("zh-CN", { maximumFractionDigits: Math.abs(value) >= 1000 ? 2 : 6 });
  }
  return String(value);
}

function renderSummary(summary = {}) {
  const keys = Object.keys(SUMMARY_LABELS).filter((key) => summary[key] !== undefined);
  paperSummaryGrid.innerHTML = keys
    .map((key) => `<div class="metric"><p class="metric-label">${SUMMARY_LABELS[key]}</p><p class="metric-value">${formatValue(summary[key])}</p></div>`)
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
    <thead><tr>${keys.map((key) => `<th>${key}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((row) => `<tr>${keys.map((key) => `<td>${formatValue(row[key])}</td>`).join("")}</tr>`).join("")}</tbody>
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
  const data = await fetchJson(`/api/paper/templates?config_dir=${configDir}`);
  templateSelect.innerHTML = "";
  if (!data.templates.length) {
    templateSelect.appendChild(new Option("没有找到模板，可手动填写路径", ""));
    setPaperStatus("没有找到模板，请检查模板目录或手动填写模板路径。", true);
    return;
  }
  data.templates.forEach((item) => {
    const label = item.error ? `${item.account_id}：读取失败` : `${item.account_name}（${item.account_id}）`;
    const option = new Option(label, item.config_path || "");
    option.dataset.ledgerPath = item.ledger_path || "";
    templateSelect.appendChild(option);
  });
  configPathInput.value = templateSelect.value;
  setPaperStatus(`已读取 ${data.templates.length} 个模拟账户模板，正在读取账本。`);
  await loadLedger(false);
}

templateSelect.addEventListener("change", () => {
  configPathInput.value = templateSelect.value;
  loadLedger(false).catch((error) => setPaperStatus(`读取账本失败：${error.message}`, true));
});

reloadTemplatesBtn.addEventListener("click", async () => {
  try {
    await loadTemplates();
  } catch (error) {
    setPaperStatus(`读取模板失败：${error.message}`, true);
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
