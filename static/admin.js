const ADMIN_USERNAME = "admin";

const adminCurrentUser = document.getElementById("adminCurrentUser");
const reloadOverviewBtn = document.getElementById("reloadOverviewBtn");
const reloadSchedulerRunsBtn = document.getElementById("reloadSchedulerRunsBtn");
const reloadMainUniverseBtn = document.getElementById("reloadMainUniverseBtn");
const adminTaskStatus = document.getElementById("adminTaskStatus");
const adminSummaryGrid = document.getElementById("adminSummaryGrid");
const mainUniverseInput = document.getElementById("mainUniverseInput");
const includeInactiveUniverse = document.getElementById("includeInactiveUniverse");
const mainUniverseMode = document.getElementById("mainUniverseMode");
const resolveUniverseBtn = document.getElementById("resolveUniverseBtn");
const saveUniverseBtn = document.getElementById("saveUniverseBtn");
const mainUniverseStatus = document.getElementById("mainUniverseStatus");
const mainUniverseRows = document.getElementById("mainUniverseRows");
const resolvedUniverseDetail = document.getElementById("resolvedUniverseDetail");
const schedulerRunRows = document.getElementById("schedulerRunRows");
const schedulerRunStatus = document.getElementById("schedulerRunStatus");
const collectTodayDailyBtn = document.getElementById("collectTodayDailyBtn");
const computeTodayIndicatorsBtn = document.getElementById("computeTodayIndicatorsBtn");
const collectRangeDailyBtn = document.getElementById("collectRangeDailyBtn");
const computeRangeIndicatorsBtn = document.getElementById("computeRangeIndicatorsBtn");
const stockDataRangeStart = document.getElementById("stockDataRangeStart");
const stockDataRangeEnd = document.getElementById("stockDataRangeEnd");
const stockDataMaxSymbols = document.getElementById("stockDataMaxSymbols");
const stockDataSleepSeconds = document.getElementById("stockDataSleepSeconds");
const stockDataStatus = document.getElementById("stockDataStatus");

const CORE_TASK_LABELS = {
  core_after_close_generate: "核心收盘生成",
  daily_sync: "日线同步",
  feature_build: "指标构建",
  safe_retry: "安全重跑",
};

const RETRYABLE_JOBS = new Set(["daily_sync", "feature_build", "core_after_close_generate"]);

function setStatus(element, text, error = false) {
  if (!element) return;
  element.textContent = text;
  element.style.color = error ? "#8a2f13" : "";
}

function currentUsername() {
  return window.T0Auth?.currentUsername?.() || ADMIN_USERNAME;
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return value.toLocaleString("zh-CN");
  return String(value);
}

function shortId(value = "") {
  const text = String(value || "");
  return text.length > 10 ? text.slice(0, 10) : text || "-";
}

function escapeHtml(value = "") {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatStatus(status = "") {
  const text = String(status || "").trim();
  const labels = {
    success: "成功",
    failed: "失败",
    running: "运行中",
    retry_pending: "待重跑",
    skipped_locked: "锁定跳过",
    skipped_non_trade_day: "非交易日跳过",
    check_only: "仅检查",
  };
  return labels[text] || text || "-";
}

function formatJobName(jobName = "") {
  const text = String(jobName || "").trim();
  return CORE_TASK_LABELS[text] || text || "-";
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, { credentials: "same-origin", ...options });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败：${response.status}`);
  }
  return response.json();
}

function setButtonsDisabled(disabled) {
  [
    reloadOverviewBtn,
    reloadSchedulerRunsBtn,
    reloadMainUniverseBtn,
    resolveUniverseBtn,
    saveUniverseBtn,
    collectTodayDailyBtn,
    computeTodayIndicatorsBtn,
    collectRangeDailyBtn,
    computeRangeIndicatorsBtn,
  ].forEach((button) => {
    if (button) button.disabled = disabled;
  });
}

function normalizeAdminDate(value = "") {
  const text = String(value || "").trim().replace(/[-/]/g, "");
  if (!/^\d{8}$/.test(text)) return "";
  return text;
}

function stockDataPayload(mode) {
  const payload = {
    username: currentUsername(),
    max_symbols: Number(stockDataMaxSymbols?.value || 0) || 0,
    sleep_seconds: Number(stockDataSleepSeconds?.value || 0) || 0,
  };
  if (mode === "range") {
    const startDate = normalizeAdminDate(stockDataRangeStart?.value || "");
    const endDate = normalizeAdminDate(stockDataRangeEnd?.value || "");
    if (!startDate || !endDate) {
      throw new Error("请输入 YYYYMMDD 格式的开始日期和结束日期");
    }
    if (startDate > endDate) {
      throw new Error("开始日期不能晚于结束日期");
    }
    payload.start_date = startDate;
    payload.end_date = endDate;
  }
  return payload;
}

function summarizeStockDataResult(data = {}, fallback = "任务已提交并执行完成。") {
  const status = data.status ? `状态 ${data.status}` : "";
  const dates = data.start_date && data.end_date ? `区间 ${data.start_date}-${data.end_date}` : "";
  const counts = [
    data.stock_count !== undefined ? `执行 ${formatNumber(data.stock_count)} 只` : "",
    data.success_count !== undefined ? `成功 ${formatNumber(data.success_count)} 只` : "",
    data.failed_count !== undefined ? `失败 ${formatNumber(data.failed_count)} 只` : "",
  ].filter(Boolean).join("，");
  return [data.message || fallback, dates, counts, status].filter(Boolean).join("；");
}

async function runStockDataTask(endpoint, mode, label) {
  const confirmed = typeof window.confirm !== "function" ? true : window.confirm(`确认${label}？该操作会写入 SQLite 主库。`);
  if (!confirmed) return;
  let payload;
  try {
    payload = stockDataPayload(mode);
  } catch (error) {
    setStatus(stockDataStatus, error.message, true);
    return;
  }
  setButtonsDisabled(true);
  setStatus(stockDataStatus, `正在${label}；请等待任务返回。`);
  try {
    const data = await fetchJson(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setStatus(stockDataStatus, summarizeStockDataResult(data, `${label}完成。`), data.status === "failed");
    await Promise.all([loadOverview(false), loadSchedulerRuns(false)]);
  } catch (error) {
    setStatus(stockDataStatus, `${label}失败：${error.message}`, true);
  } finally {
    setButtonsDisabled(false);
  }
}

function renderOverview(data = {}) {
  const scheduler = data.scheduler || {};
  const coreTasks = data.core_tasks || {};
  const cards = Object.entries(CORE_TASK_LABELS).map(([key, label]) => {
    const task = coreTasks[key] || {};
    const latest = task.latest_run || null;
    const latestStatus = latest ? formatStatus(latest.status) : "暂无";
    const latestDate = latest?.target_date || "-";
    const failedCount = task.status_counts?.failed || 0;
    return `
      <div class="metric admin-core-card">
        <p class="metric-label">${label}</p>
        <p class="metric-value">${latestStatus}</p>
        <p class="metric-sub">日期 ${escapeHtml(latestDate)} · 运行 ${formatNumber(task.run_count || 0)} · 失败 ${formatNumber(failedCount)}</p>
      </div>
    `;
  });
  cards.push(`
    <div class="metric admin-core-card">
      <p class="metric-label">调度记录</p>
      <p class="metric-value">${formatNumber(scheduler.run_count || 0)}</p>
      <p class="metric-sub">最近状态 ${formatStatus(scheduler.latest_run?.status || "")}</p>
    </div>
  `);
  adminSummaryGrid.innerHTML = cards.join("");
}

async function loadOverview(showStatus = true) {
  if (showStatus) setStatus(adminTaskStatus, "正在读取运维总览；本次不会写入数据。");
  const data = await fetchJson("/api/admin/overview");
  renderOverview(data);
  if (showStatus) setStatus(adminTaskStatus, "运维总览已刷新；本次仅读取，没有写入数据。");
}

function parseUniverseLines() {
  return (mainUniverseInput.value || "")
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const symbolMatch = line.match(/\b(\d{6})(?:\.(?:SZ|SH|BJ))?\b/i);
      if (!symbolMatch) return { name: line };
      const symbol = symbolMatch[1];
      const name = line
        .replace(symbolMatch[0], " ")
        .replace(/[,.，、;；|]/g, " ")
        .replace(/\s+/g, " ")
        .trim();
      return name ? { symbol, name } : { symbol };
    });
}

function parseUniverseNames() {
  return parseUniverseLines()
    .map((row) => row.name || "")
    .filter(Boolean);
}

function renderUniverseRows(rows = []) {
  if (!rows.length) {
    mainUniverseRows.innerHTML = `<tr><td colspan="6">主股票池暂无记录。</td></tr>`;
    return;
  }
  mainUniverseRows.innerHTML = rows
    .map((row) => `
      <tr>
        <td>${escapeHtml(row.symbol)}</td>
        <td>${escapeHtml(row.ts_code)}</td>
        <td>${escapeHtml(row.name || row.stock_name || "")}</td>
        <td>${escapeHtml(row.source || "")}</td>
        <td>${Number(row.is_active) === 1 ? "活跃" : "停用"}</td>
        <td>${escapeHtml(row.updated_at || "")}</td>
      </tr>
    `)
    .join("");
}

async function loadMainUniverse(showStatus = true) {
  if (showStatus) setStatus(mainUniverseStatus, "正在读取主股票池；本次不会写入数据。");
  const includeInactive = includeInactiveUniverse.checked ? "true" : "false";
  const data = await fetchJson(`/api/admin/main-universe?include_inactive=${includeInactive}`);
  renderUniverseRows(data.rows || []);
  setStatus(mainUniverseStatus, data.message || `已读取 ${formatNumber(data.count || 0)} 只股票；本次没有写入数据。`);
}

function renderResolveResult(data = {}) {
  const resolved = data.resolved || [];
  const unresolved = data.unresolved || [];
  const ambiguous = data.ambiguous || [];
  const duplicates = data.duplicate_inputs || [];
  const parts = [
    `解析成功 ${resolved.length} 只`,
    `未匹配 ${unresolved.length} 个`,
    `歧义 ${ambiguous.length} 个`,
    `重复 ${duplicates.length} 个`,
  ];
  if (resolved.length) {
    parts.push(`成功样例：${resolved.slice(0, 6).map((item) => `${item.name || item.stock_name || ""}(${item.symbol})`).join("，")}`);
  }
  if (unresolved.length) parts.push(`未匹配：${unresolved.slice(0, 8).join("，")}`);
  if (ambiguous.length) parts.push(`歧义：${ambiguous.slice(0, 4).map((item) => item.name).join("，")}`);
  if (duplicates.length) parts.push(`重复：${duplicates.slice(0, 8).join("，")}`);
  resolvedUniverseDetail.textContent = parts.join("。") + "。";
}

async function resolveMainUniverse() {
  const names = parseUniverseNames();
  if (!names.length) {
    setStatus(mainUniverseStatus, "请输入至少一个股票名称再解析；本次没有写入数据。", true);
    return;
  }
  setButtonsDisabled(true);
  setStatus(mainUniverseStatus, "正在解析股票名称；本次不会写入数据。");
  try {
    const data = await fetchJson("/api/admin/main-universe/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ names }),
    });
    renderResolveResult(data);
    setStatus(mainUniverseStatus, data.message || "解析完成；未写入主股票池数据。");
  } catch (error) {
    setStatus(mainUniverseStatus, `解析失败：${error.message}`, true);
  } finally {
    setButtonsDisabled(false);
  }
}

async function saveMainUniverse() {
  const rows = parseUniverseLines();
  if (!rows.length) {
    setStatus(mainUniverseStatus, "请输入至少一只股票再保存；本次没有写入数据。", true);
    return;
  }
  const mode = mainUniverseMode.value || "append";
  const confirmed = typeof window.confirm !== "function" ? true : window.confirm(`确认以“${mode === "replace" ? "替换活跃集合" : "追加或激活"}”模式写入主股票池？`);
  if (!confirmed) return;
  setButtonsDisabled(true);
  setStatus(mainUniverseStatus, "正在写入主股票池...");
  try {
    const data = await fetchJson("/api/admin/main-universe/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, rows, source: "admin_upload" }),
    });
    renderResolveResult(data);
    setStatus(mainUniverseStatus, data.message || (data.written ? "主股票池已写入。" : "没有写入主股票池。"), !data.written);
    await loadMainUniverse(false);
  } catch (error) {
    setStatus(mainUniverseStatus, `保存失败：${error.message}`, true);
  } finally {
    setButtonsDisabled(false);
  }
}

function canRetry(row = {}) {
  return row.status === "failed" && RETRYABLE_JOBS.has(row.job_name || "");
}

function renderSchedulerRows(runs = []) {
  if (!runs.length) {
    schedulerRunRows.innerHTML = `<tr><td colspan="10">暂无调度运行记录。</td></tr>`;
    return;
  }
  schedulerRunRows.innerHTML = runs
    .map((run) => {
      const retryButton = canRetry(run)
        ? `<button type="button" class="secondary small-action" data-retry-run="${escapeHtml(run.run_id)}">登记重跑</button>`
        : `<span class="muted-cell">-</span>`;
      return `
        <tr>
          <td title="${escapeHtml(run.run_id)}">${shortId(run.run_id)}</td>
          <td>${formatJobName(run.job_name)}</td>
          <td>${escapeHtml(run.target_date || "")}</td>
          <td>${formatStatus(run.status)}</td>
          <td>${escapeHtml(run.started_at || "")}</td>
          <td>${escapeHtml(run.finished_at || "")}</td>
          <td>${escapeHtml(run.failed_stage || "")}</td>
          <td title="${escapeHtml(run.error_summary || "")}">${escapeHtml(run.error_summary || "")}</td>
          <td title="${escapeHtml(run.log_file || "")}">${escapeHtml(run.log_file || "")}</td>
          <td>${retryButton}</td>
        </tr>
      `;
    })
    .join("");
  schedulerRunRows.querySelectorAll("[data-retry-run]").forEach((button) => {
    button.addEventListener("click", () => retrySchedulerRun(button.dataset.retryRun));
  });
}

async function loadSchedulerRuns(showStatus = true) {
  if (showStatus) setStatus(schedulerRunStatus, "正在读取任务运行记录；本次不会写入数据。");
  const data = await fetchJson("/api/admin/scheduler/runs?limit=50");
  renderSchedulerRows(data.runs || []);
  if (showStatus) setStatus(schedulerRunStatus, `已读取 ${(data.runs || []).length} 条运行记录；本次没有写入数据。`);
}

async function retrySchedulerRun(runId) {
  if (!runId) return;
  const confirmed = typeof window.confirm !== "function" ? true : window.confirm("确认登记安全重跑请求？本操作只写入待重跑记录，不直接执行任务。");
  if (!confirmed) return;
  setButtonsDisabled(true);
  setStatus(schedulerRunStatus, "正在登记安全重跑请求...");
  try {
    const data = await fetchJson(`/api/admin/scheduler/runs/${encodeURIComponent(runId)}/retry`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "admin_dashboard" }),
    });
    setStatus(schedulerRunStatus, data.message || "已登记安全重跑请求；本接口不直接执行任务。写入了待重跑记录。");
    await Promise.all([loadOverview(false), loadSchedulerRuns(false)]);
  } catch (error) {
    setStatus(schedulerRunStatus, `登记重跑失败：${error.message}`, true);
  } finally {
    setButtonsDisabled(false);
  }
}

async function initAdminPage() {
  if (adminCurrentUser) adminCurrentUser.textContent = currentUsername();
  renderOverview();
  renderUniverseRows([]);
  renderSchedulerRows([]);
  try {
    await window.T0Auth?.loadCurrentUser?.();
    if (adminCurrentUser) adminCurrentUser.textContent = currentUsername();
    await Promise.all([loadOverview(false), loadMainUniverse(false), loadSchedulerRuns(false)]);
    setStatus(adminTaskStatus, "运维看板已读取；当前没有写入数据。");
  } catch (error) {
    setStatus(adminTaskStatus, `读取运维看板失败：${error.message}`, true);
  }
}

reloadOverviewBtn?.addEventListener("click", () => loadOverview(true).catch((error) => setStatus(adminTaskStatus, `读取总览失败：${error.message}`, true)));
reloadSchedulerRunsBtn?.addEventListener("click", () => loadSchedulerRuns(true).catch((error) => setStatus(schedulerRunStatus, `读取运行记录失败：${error.message}`, true)));
reloadMainUniverseBtn?.addEventListener("click", () => loadMainUniverse(true).catch((error) => setStatus(mainUniverseStatus, `读取主股票池失败：${error.message}`, true)));
includeInactiveUniverse?.addEventListener("change", () => loadMainUniverse(true).catch((error) => setStatus(mainUniverseStatus, `读取主股票池失败：${error.message}`, true)));
resolveUniverseBtn?.addEventListener("click", resolveMainUniverse);
saveUniverseBtn?.addEventListener("click", saveMainUniverse);
collectTodayDailyBtn?.addEventListener("click", () => runStockDataTask("/api/admin/stock-data/daily/today", "today", "采集今日日线"));
computeTodayIndicatorsBtn?.addEventListener("click", () => runStockDataTask("/api/admin/stock-data/indicators/today", "today", "计算今日指标"));
collectRangeDailyBtn?.addEventListener("click", () => runStockDataTask("/api/admin/stock-data/daily/range", "range", "采集区间日线"));
computeRangeIndicatorsBtn?.addEventListener("click", () => runStockDataTask("/api/admin/stock-data/indicators/range", "range", "计算区间指标"));

initAdminPage();
