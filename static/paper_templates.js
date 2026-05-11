const configDirInput = document.getElementById("configDir");
const templateSelect = document.getElementById("templateSelect");
const configPathInput = document.getElementById("configPath");
const reloadTemplatesBtn = document.getElementById("reloadTemplatesBtn");
const loadTemplateBtn = document.getElementById("loadTemplateBtn");
const newTemplateBtn = document.getElementById("newTemplateBtn");
const copyTemplateBtn = document.getElementById("copyTemplateBtn");
const saveTemplateBtn = document.getElementById("saveTemplateBtn");
const saveAsTemplateBtn = document.getElementById("saveAsTemplateBtn");
const deleteTemplateBtn = document.getElementById("deleteTemplateBtn");
const templateStatus = document.getElementById("templateStatus");
const templateSummaryGrid = document.getElementById("templateSummaryGrid");
const openPaperLink = document.getElementById("openPaperLink");

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

const SUMMARY_LABELS = {
  file_name: "模板文件",
  account_id: "账户编号",
  account_name: "账户名称",
  processed_dir: "数据目录",
  top_n: "TopN",
  ledger_path: "账本路径",
  ledger_exists: "账本状态",
  price_primary: "首选行情源",
  price_field: "价格字段",
};

function setTemplateStatus(text, error = false) {
  templateStatus.textContent = text;
  templateStatus.style.color = error ? "#8a2f13" : "";
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

function chinaDateTimeStamp(date = new Date()) {
  if (typeof Intl !== "undefined" && typeof Intl.DateTimeFormat === "function") {
    const formatter = new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
    const parts = formatter.formatToParts(date);
    const value = (type) => parts.find((part) => part.type === type)?.value || "";
    const stamp = `${value("year")}${value("month")}${value("day")}${value("hour")}${value("minute")}${value("second")}`;
    if (/^\d{14}$/.test(stamp)) {
      return stamp;
    }
  }
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60 * 1000);
  return local.toISOString().slice(0, 19).replaceAll("-", "").replaceAll(":", "").replace("T", "");
}

function sanitizeTemplatePart(value, fallback = "template") {
  const text = String(value || fallback)
    .trim()
    .replace(/\.(ya?ml)$/i, "")
    .replace(/[\\/:*?"<>|\s]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
  return text || fallback;
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
    ledger_exists: false,
  };
}

function buildCopiedTemplateValues(source = {}) {
  const stamp = chinaDateTimeStamp();
  const suffix = `${stamp}_copy`;
  const baseAccountId = sanitizeTemplatePart(source.account_id || source.file_name || "paper_account", "paper_account");
  const baseFileName = sanitizeTemplatePart(source.file_name || baseAccountId, baseAccountId);
  const nextAccountId = `${baseAccountId}_${suffix}`;
  const sourceName = String(source.account_name || source.account_id || "模拟账户").trim();
  return {
    ...source,
    file_name: `${baseFileName}_${suffix}.yaml`,
    account_id: nextAccountId,
    account_name: `${sourceName}_副本_${stamp}`,
    ledger_path: `paper_trading/accounts/${nextAccountId}.xlsx`,
    ledger_exists: false,
  };
}

function formatSummaryValue(key, value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "boolean") {
    if (key === "ledger_exists") {
      return value ? "已存在" : "未创建";
    }
    return value ? "是" : "否";
  }
  if (typeof value === "number") {
    return value.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
  }
  return String(value);
}

function renderTemplateSummary(template = {}) {
  const merged = { ...defaultTemplateValues(), ...template };
  const summary = {
    file_name: merged.file_name,
    account_id: merged.account_id,
    account_name: merged.account_name,
    processed_dir: merged.processed_dir,
    top_n: merged.top_n,
    ledger_path: merged.ledger_path,
    ledger_exists: merged.ledger_exists,
    price_primary: merged.price_primary,
    price_field: merged.price_field,
  };
  templateSummaryGrid.innerHTML = Object.entries(SUMMARY_LABELS)
    .map(([key, label]) => `<div class="metric"><p class="metric-label">${label}</p><p class="metric-value">${formatSummaryValue(key, summary[key])}</p></div>`)
    .join("");
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
  renderTemplateSummary(merged);
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
  [reloadTemplatesBtn, loadTemplateBtn, newTemplateBtn, copyTemplateBtn, saveTemplateBtn, saveAsTemplateBtn, deleteTemplateBtn].forEach((button) => {
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

function buildPaperHref() {
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
  return query ? `/paper?${query}` : "/paper";
}

function syncNavigationState() {
  const params = new URLSearchParams();
  const configDir = configDirInput.value.trim();
  const configPath = configPathInput.value.trim();
  if (configDir) {
    params.set("config_dir", configDir);
  }
  if (configPath) {
    params.set("config_path", configPath);
  }
  const pathName = typeof window !== "undefined" && window.location ? window.location.pathname : "/paper/templates";
  const nextUrl = `${pathName}${params.toString() ? `?${params.toString()}` : ""}`;
  if (typeof window !== "undefined" && window.history && typeof window.history.replaceState === "function") {
    window.history.replaceState({}, "", nextUrl);
  }
  if (openPaperLink) {
    openPaperLink.href = buildPaperHref();
  }
}

async function loadTemplates() {
  const configDir = encodeURIComponent(configDirInput.value.trim() || "configs/paper_accounts");
  const requestedPath = configPathInput.value.trim();
  const data = await fetchJson(`/api/paper/templates?config_dir=${configDir}`);
  templateSelect.innerHTML = "";
  if (!data.templates.length) {
    templateSelect.appendChild(new Option("没有找到模板，可手动填写路径", ""));
    configPathInput.value = "";
    populateTemplateEditor();
    syncNavigationState();
    setTemplateStatus("没有找到模板，可以先填写新模板后保存。");
    return;
  }
  data.templates.forEach((item) => {
    const label = item.error ? `${item.account_id}：读取失败` : `${item.account_name}（${item.account_id}）`;
    templateSelect.appendChild(new Option(label, item.config_path || ""));
  });
  const hasRequestedPath = requestedPath && Array.from(templateSelect.options).some((option) => option.value === requestedPath);
  templateSelect.value = hasRequestedPath ? requestedPath : templateSelect.options[0].value;
  configPathInput.value = templateSelect.value;
  syncNavigationState();
  await loadCurrentTemplate(false);
}

async function loadCurrentTemplate(showStatus = true) {
  const configPath = configPathInput.value.trim();
  syncNavigationState();
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

async function saveTemplate(overwriteExisting) {
  const shouldOverwrite = overwriteExisting && Boolean(configPathInput.value.trim());
  setTemplateButtonsDisabled(true);
  setTemplateStatus(shouldOverwrite ? "正在保存模板..." : "正在另存为新模板...");
  try {
    const payload = collectTemplatePayload(shouldOverwrite);
    const data = await fetchJson("/api/paper/template", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const savedPath = data.template.config_path;
    configPathInput.value = savedPath;
    await loadTemplates();
    templateSelect.value = savedPath;
    configPathInput.value = savedPath;
    populateTemplateEditor(data.template);
    syncNavigationState();
    setTemplateStatus(data.message || "模板已保存；Excel 账本未被修改。");
  } catch (error) {
    setTemplateStatus(`保存失败：${error.message}`, true);
  } finally {
    setTemplateButtonsDisabled(false);
  }
}

reloadTemplatesBtn.addEventListener("click", async () => {
  try {
    setTemplateStatus("正在刷新模板列表...");
    await loadTemplates();
  } catch (error) {
    setTemplateStatus(`读取模板失败：${error.message}`, true);
  }
});

loadTemplateBtn.addEventListener("click", async () => {
  try {
    await loadCurrentTemplate(true);
  } catch (error) {
    setTemplateStatus(`读取模板失败：${error.message}`, true);
  }
});

templateSelect.addEventListener("change", async () => {
  configPathInput.value = templateSelect.value;
  syncNavigationState();
  try {
    await loadCurrentTemplate(false);
  } catch (error) {
    setTemplateStatus(`读取模板失败：${error.message}`, true);
  }
});

newTemplateBtn.addEventListener("click", () => {
  templateSelect.value = "";
  configPathInput.value = "";
  populateTemplateEditor();
  syncNavigationState();
  setTemplateStatus("已初始化新模板。保存前请确认账户编号、文件名和账本路径不会与旧模板冲突。");
});

copyTemplateBtn.addEventListener("click", () => {
  const source = collectTemplatePayload(Boolean(configPathInput.value.trim()));
  templateSelect.value = "";
  configPathInput.value = "";
  populateTemplateEditor(buildCopiedTemplateValues(source));
  syncNavigationState();
  setTemplateStatus("已复制当前模板为新草稿。可以小改配置后点击保存模板；保存前不会写入 YAML，也不会修改 Excel 账本。");
});

saveTemplateBtn.addEventListener("click", () => saveTemplate(true));
saveAsTemplateBtn.addEventListener("click", () => saveTemplate(false));

deleteTemplateBtn.addEventListener("click", async () => {
  const configPath = configPathInput.value.trim();
  if (!configPath) {
    setTemplateStatus("请先选择要删除的模板。", true);
    return;
  }
  const confirmed =
    typeof window === "undefined" || typeof window.confirm !== "function"
      ? true
      : window.confirm("只删除 YAML 模板，不删除 Excel 账本。确认删除当前模板吗？");
  if (!confirmed) {
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
    syncNavigationState();
    setTemplateStatus(data.message || "模板已删除；Excel 账本保留不动。");
  } catch (error) {
    setTemplateStatus(`删除失败：${error.message}`, true);
  } finally {
    setTemplateButtonsDisabled(false);
  }
});

configDirInput.addEventListener("input", syncNavigationState);
configPathInput.addEventListener("input", syncNavigationState);

const templateLocationSearch = typeof window !== "undefined" && window.location ? window.location.search : "";
const urlParams = new URLSearchParams(templateLocationSearch);
if (urlParams.get("config_dir")) {
  configDirInput.value = urlParams.get("config_dir");
}
if (urlParams.get("config_path")) {
  configPathInput.value = urlParams.get("config_path");
}

populateTemplateEditor();
syncNavigationState();
loadTemplates().catch((error) => setTemplateStatus(`读取模板失败：${error.message}`, true));
