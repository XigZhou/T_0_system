const poolUsernameInput = document.getElementById("poolUsername");
const poolTemplateSelect = document.getElementById("poolTemplateSelect");
const reloadPoolsBtn = document.getElementById("reloadPoolsBtn");
const loadPoolBtn = document.getElementById("loadPoolBtn");
const newPoolBtn = document.getElementById("newPoolBtn");
const copyPoolBtn = document.getElementById("copyPoolBtn");
const savePoolBtn = document.getElementById("savePoolBtn");
const deletePoolBtn = document.getElementById("deletePoolBtn");
const seedPoolsBtn = document.getElementById("seedPoolsBtn");
const validatePoolBtn = document.getElementById("validatePoolBtn");
const poolStatus = document.getElementById("poolStatus");
const poolSummaryGrid = document.getElementById("poolSummaryGrid");
const poolTemplateNameInput = document.getElementById("poolTemplateName");
const poolOriginalTemplateNameInput = document.getElementById("poolOriginalTemplateName");
const poolDescriptionInput = document.getElementById("poolDescription");
const poolIsActiveInput = document.getElementById("poolIsActive");
const poolStockTextInput = document.getElementById("poolStockText");
const poolValidationNote = document.getElementById("poolValidationNote");
const poolStockRows = document.getElementById("poolStockRows");

const POOL_SUMMARY_LABELS = {
  template_name: "模板名称",
  username: "用户",
  stock_count: "股票数",
  is_active: "每日更新",
  updated_at: "更新时间",
  db_path: "数据库",
};

function setPoolStatus(text, error = false) {
  poolStatus.textContent = text;
  poolStatus.style.color = error ? "#8a2f13" : "";
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

function defaultPoolValues() {
  return {
    username: poolUsernameInput.value.trim() || "505888",
    template_name: `新股票池_${chinaDateTimeStamp()}`,
    original_template_name: "",
    description: "",
    is_active: true,
    stock_count: 0,
    updated_at: "",
    db_path: "data_store/stock_pool_templates.sqlite",
    stocks: [],
    stock_text: "",
  };
}

function formatSummaryValue(key, value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "boolean") {
    return value ? "启用" : "停用";
  }
  if (typeof value === "number") {
    return value.toLocaleString("zh-CN");
  }
  return String(value);
}

function renderPoolSummary(pool = {}) {
  const merged = { ...defaultPoolValues(), ...pool };
  poolSummaryGrid.innerHTML = Object.entries(POOL_SUMMARY_LABELS)
    .map(([key, label]) => `<div class="metric"><p class="metric-label">${label}</p><p class="metric-value">${formatSummaryValue(key, merged[key])}</p></div>`)
    .join("");
}

function renderStockRows(stocks = []) {
  if (!stocks.length) {
    poolStockRows.innerHTML = `<tr><td colspan="5">暂无股票。请在上方输入股票列表后校验或保存。</td></tr>`;
    return;
  }
  poolStockRows.innerHTML = stocks
    .map(
      (stock, idx) => `
        <tr>
          <td>${idx + 1}</td>
          <td>${stock.symbol || ""}</td>
          <td>${stock.ts_code || ""}</td>
          <td>${stock.stock_name || ""}</td>
          <td>${stock.latest_trade_date || ""}</td>
        </tr>
      `
    )
    .join("");
}

function populatePoolEditor(data = {}) {
  const merged = { ...defaultPoolValues(), ...data };
  poolUsernameInput.value = merged.username || "505888";
  poolTemplateNameInput.value = merged.template_name || "";
  poolOriginalTemplateNameInput.value = Object.prototype.hasOwnProperty.call(data, "original_template_name")
    ? data.original_template_name || ""
    : merged.template_name || "";
  poolDescriptionInput.value = merged.description || "";
  poolIsActiveInput.checked = Boolean(merged.is_active);
  poolStockTextInput.value = merged.stock_text || "";
  renderPoolSummary(merged);
  renderStockRows(merged.stocks || []);
}

function collectPoolPayload() {
  return {
    username: poolUsernameInput.value.trim() || "505888",
    original_template_name: poolOriginalTemplateNameInput.value.trim(),
    template_name: poolTemplateNameInput.value.trim(),
    description: poolDescriptionInput.value.trim(),
    is_active: poolIsActiveInput.checked,
    stock_text: poolStockTextInput.value.trim(),
    overwrite_existing: Boolean(poolOriginalTemplateNameInput.value.trim()),
  };
}

function setPoolButtonsDisabled(disabled) {
  [reloadPoolsBtn, loadPoolBtn, newPoolBtn, copyPoolBtn, savePoolBtn, deletePoolBtn, seedPoolsBtn, validatePoolBtn].forEach((button) => {
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

function usernameQuery() {
  return encodeURIComponent(poolUsernameInput.value.trim() || "505888");
}

async function loadPoolTemplates() {
  const previous = poolTemplateSelect.value;
  const data = await fetchJson(`/api/stock-pools/templates?username=${usernameQuery()}`);
  poolTemplateSelect.innerHTML = "";
  if (!data.templates.length) {
    poolTemplateSelect.appendChild(new Option("没有找到模板，可新建", ""));
    populatePoolEditor();
    setPoolStatus("没有找到股票池模板，可以先新建一个模板。");
    return;
  }
  data.templates.forEach((item) => {
    const label = `${item.template_name}（${item.stock_count}只）`;
    poolTemplateSelect.appendChild(new Option(label, item.template_name || ""));
  });
  const hasPrevious = previous && Array.from(poolTemplateSelect.options).some((option) => option.value === previous);
  poolTemplateSelect.value = hasPrevious ? previous : poolTemplateSelect.options[0].value;
  await loadCurrentPool(false);
  setPoolStatus(`已读取 ${data.templates.length} 个股票池模板。`);
}

async function loadCurrentPool(showStatus = true) {
  const templateName = poolTemplateSelect.value || poolTemplateNameInput.value.trim();
  if (!templateName) {
    populatePoolEditor();
    setPoolStatus("未选择模板，可以新建一个股票池模板。");
    return;
  }
  if (showStatus) {
    setPoolStatus("正在载入股票池模板...");
  }
  const data = await fetchJson(`/api/stock-pools/template?username=${usernameQuery()}&template_name=${encodeURIComponent(templateName)}`);
  populatePoolEditor(data);
  setPoolStatus(`股票池模板已载入：${data.template_name}，共 ${data.stock_count} 只股票。`);
}

async function validatePoolStockText() {
  const data = await fetchJson("/api/stock-pools/template/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stock_text: poolStockTextInput.value }),
  });
  renderStockRows(data.valid_stocks || []);
  poolValidationNote.textContent = `有效 ${data.valid_count} 只；重复 ${data.duplicate_count} 项；格式错误 ${data.invalid_count} 项。`;
  if (data.invalid_count > 0) {
    setPoolStatus(`股票列表存在格式错误：${data.invalid_items.join("、")}`, true);
  } else {
    setPoolStatus(`股票列表校验通过，有效 ${data.valid_count} 只。`);
  }
  return data;
}

async function saveCurrentPool() {
  setPoolButtonsDisabled(true);
  setPoolStatus("正在保存股票池模板...");
  try {
    const payload = collectPoolPayload();
    const data = await fetchJson("/api/stock-pools/template", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await loadPoolTemplates();
    poolTemplateSelect.value = data.template.template_name;
    populatePoolEditor(data.template);
    poolValidationNote.textContent = `有效 ${data.validation.valid_count} 只；重复 ${data.validation.duplicate_count} 项；格式错误 ${data.validation.invalid_count} 项。`;
    setPoolStatus(data.message || "股票池模板已保存。");
  } catch (error) {
    setPoolStatus(`保存失败：${error.message}`, true);
  } finally {
    setPoolButtonsDisabled(false);
  }
}

reloadPoolsBtn.addEventListener("click", async () => {
  try {
    setPoolStatus("正在刷新股票池模板列表...");
    await loadPoolTemplates();
  } catch (error) {
    setPoolStatus(`刷新失败：${error.message}`, true);
  }
});

loadPoolBtn.addEventListener("click", async () => {
  try {
    await loadCurrentPool(true);
  } catch (error) {
    setPoolStatus(`载入失败：${error.message}`, true);
  }
});

poolTemplateSelect.addEventListener("change", async () => {
  try {
    await loadCurrentPool(false);
  } catch (error) {
    setPoolStatus(`载入失败：${error.message}`, true);
  }
});

newPoolBtn.addEventListener("click", () => {
  poolTemplateSelect.value = "";
  populatePoolEditor(defaultPoolValues());
  setPoolStatus("已初始化新股票池模板。");
});

copyPoolBtn.addEventListener("click", () => {
  const current = collectPoolPayload();
  const copied = {
    ...defaultPoolValues(),
    ...current,
    original_template_name: "",
    template_name: `${current.template_name || "股票池"}_副本_${chinaDateTimeStamp()}`,
  };
  poolTemplateSelect.value = "";
  populatePoolEditor(copied);
  setPoolStatus("已复制为新股票池草稿。保存前不会写入 SQLite，也不会触发行情采集。");
});

validatePoolBtn.addEventListener("click", async () => {
  try {
    await validatePoolStockText();
  } catch (error) {
    setPoolStatus(`校验失败：${error.message}`, true);
  }
});

savePoolBtn.addEventListener("click", saveCurrentPool);

deletePoolBtn.addEventListener("click", async () => {
  const templateName = poolOriginalTemplateNameInput.value.trim() || poolTemplateNameInput.value.trim();
  if (!templateName) {
    setPoolStatus("请先选择要删除的股票池模板。", true);
    return;
  }
  const confirmed =
    typeof window === "undefined" || typeof window.confirm !== "function"
      ? true
      : window.confirm("只删除股票池模板和模板股票关系，不删除 SQLite 日线数据。确认删除吗？");
  if (!confirmed) {
    return;
  }
  setPoolButtonsDisabled(true);
  setPoolStatus("正在删除股票池模板...");
  try {
    const data = await fetchJson(`/api/stock-pools/template?username=${usernameQuery()}&template_name=${encodeURIComponent(templateName)}`, { method: "DELETE" });
    await loadPoolTemplates();
    setPoolStatus(data.message || "股票池模板已删除。");
  } catch (error) {
    setPoolStatus(`删除失败：${error.message}`, true);
  } finally {
    setPoolButtonsDisabled(false);
  }
});

seedPoolsBtn.addEventListener("click", async () => {
  setPoolButtonsDisabled(true);
  setPoolStatus("正在初始化基础模板...");
  try {
    const data = await fetchJson(`/api/stock-pools/templates/seed?username=${usernameQuery()}`, { method: "POST" });
    await loadPoolTemplates();
    setPoolStatus(data.message || "基础模板初始化完成。");
  } catch (error) {
    setPoolStatus(`初始化失败：${error.message}`, true);
  } finally {
    setPoolButtonsDisabled(false);
  }
});

poolUsernameInput.addEventListener("change", () => {
  loadPoolTemplates().catch((error) => setPoolStatus(`读取模板失败：${error.message}`, true));
});

populatePoolEditor();
loadPoolTemplates().catch((error) => setPoolStatus(`读取模板失败：${error.message}`, true));
