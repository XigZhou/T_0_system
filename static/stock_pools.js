const DEFAULT_STOCK_POOL_USERNAME = "admin";
const STOCK_POOL_ADMIN_USERNAME = "admin";
const poolCurrentUser = document.getElementById("poolCurrentUser");
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
const poolStockTextInput = document.getElementById("poolStockText");
const poolValidationNote = document.getElementById("poolValidationNote");
const poolStockRows = document.getElementById("poolStockRows");
const stockPoolAdminPanel = document.getElementById("stockPoolAdminPanel");
const refreshPoolDataBtn = document.getElementById("refreshPoolDataBtn");
const reloadPoolJobsBtn = document.getElementById("reloadPoolJobsBtn");
const poolAdminStatus = document.getElementById("poolAdminStatus");
const poolJobRows = document.getElementById("poolJobRows");
const poolJobDetail = document.getElementById("poolJobDetail");

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

function currentStockPoolUsername() {
  return DEFAULT_STOCK_POOL_USERNAME;
}

function isStockPoolAdmin() {
  return currentStockPoolUsername() === STOCK_POOL_ADMIN_USERNAME;
}

function setPoolAdminStatus(text, error = false) {
  if (!poolAdminStatus) {
    return;
  }
  poolAdminStatus.textContent = text;
  poolAdminStatus.style.color = error ? "#8a2f13" : "";
}

function setupAdminVisibility() {
  const visible = isStockPoolAdmin();
  if (stockPoolAdminPanel) {
    stockPoolAdminPanel.hidden = !visible;
  }
  if (!visible) {
    [refreshPoolDataBtn, reloadPoolJobsBtn].forEach((button) => {
      if (button) {
        button.disabled = true;
      }
    });
  }
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
    username: currentStockPoolUsername(),
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
  if (poolCurrentUser) {
    poolCurrentUser.textContent = merged.username || DEFAULT_STOCK_POOL_USERNAME;
  }
  poolTemplateNameInput.value = merged.template_name || "";
  poolOriginalTemplateNameInput.value = Object.prototype.hasOwnProperty.call(data, "original_template_name")
    ? data.original_template_name || ""
    : merged.template_name || "";
  poolDescriptionInput.value = merged.description || "";
  poolStockTextInput.value = merged.stock_text || "";
  renderPoolSummary(merged);
  renderStockRows(merged.stocks || []);
}

function collectPoolPayload() {
  return {
    username: currentStockPoolUsername(),
    original_template_name: poolOriginalTemplateNameInput.value.trim(),
    template_name: poolTemplateNameInput.value.trim(),
    description: poolDescriptionInput.value.trim(),
    is_active: true,
    stock_text: poolStockTextInput.value.trim(),
    overwrite_existing: Boolean(poolOriginalTemplateNameInput.value.trim()),
  };
}

function setPoolButtonsDisabled(disabled) {
  [reloadPoolsBtn, loadPoolBtn, newPoolBtn, copyPoolBtn, savePoolBtn, deletePoolBtn, seedPoolsBtn, validatePoolBtn].forEach((button) => {
    if (button) {
      button.disabled = disabled;
    }
  });
}

function setAdminButtonsDisabled(disabled) {
  [refreshPoolDataBtn, reloadPoolJobsBtn].forEach((button) => {
    if (button) {
      button.disabled = disabled || !isStockPoolAdmin();
    }
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
  return encodeURIComponent(currentStockPoolUsername());
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
  } else if (data.duplicate_count > 0) {
    setPoolStatus(`股票列表校验通过，有效 ${data.valid_count} 只；重复项 ${data.duplicate_symbols.join("、")} 已自动忽略，只保留首次出现。`);
  } else {
    setPoolStatus(`股票列表校验通过，有效 ${data.valid_count} 只。`);
  }
  return data;
}


function shortJobId(jobId = "") {
  const text = String(jobId || "");
  return text.length > 8 ? text.slice(0, 8) : text;
}

function formatJobStatus(status = "") {
  const text = String(status || "").trim();
  if (text === "success") return "成功";
  if (text === "failed") return "失败";
  if (text === "running") return "运行中";
  return text || "—";
}

function renderJobRows(jobs = []) {
  if (!poolJobRows) {
    return;
  }
  if (!jobs.length) {
    poolJobRows.innerHTML = `<tr><td colspan="10">暂无股票池数据更新任务。</td></tr>`;
    return;
  }
  poolJobRows.innerHTML = jobs
    .map(
      (job) => `
        <tr data-job-id="${job.job_id || ""}">
          <td title="${job.job_id || ""}">${shortJobId(job.job_id)}</td>
          <td>${formatJobStatus(job.status)}</td>
          <td>${job.job_type || ""}</td>
          <td>${job.template_name || "全部活跃模板"}</td>
          <td>${formatSummaryValue("stock_count", job.stock_count)}</td>
          <td>${formatSummaryValue("success_count", job.success_count)}</td>
          <td>${formatSummaryValue("failed_count", job.failed_count)}</td>
          <td>${job.end_date || ""}</td>
          <td>${job.finished_at || job.started_at || ""}</td>
          <td title="${job.log_file || ""}">${job.log_file || "历史任务未记录"}</td>
        </tr>
      `
    )
    .join("");
  Array.from(poolJobRows.querySelectorAll ? poolJobRows.querySelectorAll("tr[data-job-id]") : []).forEach((row) => {
    row.addEventListener("click", () => loadPoolJobDetail(row.dataset.jobId));
  });
}

async function loadPoolJobs(showStatus = false) {
  if (!isStockPoolAdmin()) {
    return;
  }
  if (showStatus) {
    setPoolAdminStatus("正在读取最近任务...");
  }
  const data = await fetchJson(`/api/stock-pools/jobs?username=${usernameQuery()}&limit=20`);
  renderJobRows(data.jobs || []);
  if (showStatus) {
    setPoolAdminStatus(`已读取最近 ${(data.jobs || []).length} 个任务。`);
  }
}

async function loadPoolJobDetail(jobId) {
  if (!jobId || !isStockPoolAdmin()) {
    return;
  }
  setPoolAdminStatus("正在读取任务明细...");
  const data = await fetchJson(`/api/stock-pools/jobs/${encodeURIComponent(jobId)}?username=${usernameQuery()}`);
  const failedItems = (data.items || []).filter((item) => item.status === "failed");
  const outputText = [
    `任务 ${shortJobId(data.job_id)}：${formatJobStatus(data.status)}，执行 ${formatSummaryValue("stock_count", data.stock_count)} 只，失败 ${formatSummaryValue("failed_count", data.failed_count)} 只。`,
    `日志：${data.log_file || "历史任务未记录"}`,
    `明细：${data.item_csv || "历史任务未记录"}`,
    `摘要：${data.summary_json || "历史任务未记录"}`,
  ];
  if (failedItems.length) {
    outputText.push(`失败样例：${failedItems.slice(0, 5).map((item) => `${item.symbol}:${item.message}`).join("；")}`);
  } else {
    outputText.push("失败明细：无。");
  }
  if (poolJobDetail) {
    poolJobDetail.textContent = outputText.join(" ");
  }
  setPoolAdminStatus(`任务明细已载入：${shortJobId(data.job_id)}。`);
}

async function refreshCurrentPoolData() {
  if (!isStockPoolAdmin()) {
    setPoolAdminStatus("只有 admin 用户可以刷新股票池数据。", true);
    return;
  }
  const templateName = poolOriginalTemplateNameInput.value.trim() || poolTemplateNameInput.value.trim();
  if (!templateName) {
    setPoolAdminStatus("请先选择或保存一个股票池模板。", true);
    return;
  }
  const confirmed =
    typeof window === "undefined" || typeof window.confirm !== "function"
      ? true
      : window.confirm("将刷新当前模板涉及股票的共享日线与指标库，默认只补缺失数据。确认执行吗？");
  if (!confirmed) {
    return;
  }
  setAdminButtonsDisabled(true);
  setPoolAdminStatus("正在刷新当前模板数据...");
  try {
    const data = await fetchJson("/api/stock-pools/template/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: "template",
        username: currentStockPoolUsername(),
        template_name: templateName,
        start_date: "20220101",
        end_date: "",
        retry_attempts: 3,
        retry_sleep_seconds: 5,
        sleep_seconds: 0.5,
        only_missing: true,
      }),
    });
    setPoolAdminStatus(data.message || "当前模板数据刷新完成。");
    await loadCurrentPool(false);
    await loadPoolJobs(false);
  } catch (error) {
    setPoolAdminStatus(`刷新失败：${error.message}`, true);
  } finally {
    setAdminButtonsDisabled(false);
  }
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


if (refreshPoolDataBtn) {
  refreshPoolDataBtn.addEventListener("click", refreshCurrentPoolData);
}

if (reloadPoolJobsBtn) {
  reloadPoolJobsBtn.addEventListener("click", async () => {
    try {
      setAdminButtonsDisabled(true);
      await loadPoolJobs(true);
    } catch (error) {
      setPoolAdminStatus(`读取任务失败：${error.message}`, true);
    } finally {
      setAdminButtonsDisabled(false);
    }
  });
}

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


setupAdminVisibility();
populatePoolEditor();
loadPoolTemplates().catch((error) => setPoolStatus(`读取模板失败：${error.message}`, true));
loadPoolJobs(false).catch((error) => setPoolAdminStatus(`读取任务失败：${error.message}`, true));
