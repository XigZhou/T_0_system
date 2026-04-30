const state = {
  payload: null,
};

const defaults = {
  processedDir: "sector_research/data/processed",
  reportDir: "sector_research/reports",
};

const themeColumns = [
  ["theme_rank", "排名"],
  ["theme_name", "主题"],
  ["theme_score", "综合分"],
  ["volume_price_score", "量价齐升分"],
  ["reversal_score", "极弱反转分"],
  ["m5", "5日动量"],
  ["m20", "20日动量"],
  ["amount_ratio_20", "成交额放大"],
  ["board_up_ratio", "上涨占比"],
  ["strongest_board", "最强板块"],
  ["strongest_subtheme", "最强子赛道"],
];

const boardColumns = [
  ["board_rank_overall", "总排名"],
  ["board_rank_in_theme", "主题内排名"],
  ["theme_name", "主题"],
  ["subtheme_name", "子赛道"],
  ["board_type", "板块类型"],
  ["board_name", "板块名称"],
  ["theme_board_score", "综合分"],
  ["volume_price_score", "量价齐升分"],
  ["reversal_score", "极弱反转分"],
  ["pct_chg", "涨跌幅"],
  ["m20", "20日动量"],
  ["amount_ratio_20", "成交额放大"],
  ["main_net_inflow_today", "今日主力净流入"],
];

const exposureColumns = [
  ["stock_code", "股票代码"],
  ["stock_name", "股票名称"],
  ["primary_theme", "主主题"],
  ["primary_subtheme", "主子赛道"],
  ["exposure_score", "暴露分"],
  ["theme_count", "主题数"],
  ["board_count", "板块数"],
  ["theme_names", "命中主题"],
  ["board_names", "命中板块"],
  ["matched_keywords", "关键词"],
];

const mappingColumns = [
  ["theme_name", "主题"],
  ["subtheme_name", "子赛道"],
  ["matched_keyword", "关键词"],
  ["board_type", "板块类型"],
  ["board_code", "板块代码"],
  ["board_name", "板块名称"],
  ["source", "来源"],
  ["fetched_at", "抓取时间"],
];

const percentColumns = new Set([
  "m5",
  "m20",
  "m60",
  "m120",
  "board_up_ratio",
  "positive_m20_ratio",
  "theme_rank_pct",
  "drawdown_from_120_high",
  "position_in_250_range",
]);

const scoreColumns = new Set([
  "theme_score",
  "volume_price_score",
  "reversal_score",
  "strongest_board_score",
  "theme_board_score",
  "exposure_score",
]);

const numberFormatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 4 });
const moneyFormatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 });

function byId(id) {
  return document.getElementById(id);
}

function formatValue(value, key) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value !== "number") return value;
  if (percentColumns.has(key)) return `${(value * 100).toFixed(2)}%`;
  if (key === "pct_chg" || key.endsWith("_ratio_today")) return `${value.toFixed(2)}%`;
  if (key === "amount_ratio_20") return `${value.toFixed(2)}x`;
  if (key.includes("inflow")) return moneyFormatter.format(value);
  if (scoreColumns.has(key)) return value.toFixed(3);
  return numberFormatter.format(value);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => (
    {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]
  ));
}

function setStatus(text, isError = false) {
  const el = byId("sectorStatus");
  el.textContent = text;
  el.classList.toggle("error-text", isError);
}

function activateTab(tabName) {
  document.querySelectorAll(".sector-page .tab-button").forEach((button) => {
    const active = button.dataset.tab === tabName;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".sector-page .tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.tabPanel === tabName);
  });
}

function renderSummary(summary = {}) {
  const items = [
    ["最新交易日", summary.latest_trade_date || "-"],
    ["主题数量", summary.theme_count ?? 0],
    ["匹配板块", summary.board_count ?? 0],
    ["主题日线", summary.theme_daily_rows ?? 0],
    ["个股暴露", summary.stock_exposure_rows ?? 0],
    ["异常记录", summary.error_count ?? 0],
  ];
  byId("sectorSummaryGrid").innerHTML = items
    .map(
      ([label, value]) => `
        <div class="metric">
          <p class="metric-label">${escapeHtml(label)}</p>
          <p class="metric-value">${escapeHtml(value)}</p>
        </div>
      `,
    )
    .join("");
  byId("sectorPathText").textContent = `指标目录：${summary.processed_dir || defaults.processedDir}；报告目录：${summary.report_dir || defaults.reportDir}`;
}

function renderTable(tableId, rows, columns) {
  const table = byId(tableId);
  const thead = document.createElement("thead");
  const tbody = document.createElement("tbody");
  const headerRow = document.createElement("tr");
  columns.forEach(([, label]) => {
    const th = document.createElement("th");
    th.textContent = label;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);

  if (!rows || rows.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = columns.length;
    cell.textContent = "暂无数据";
    row.appendChild(cell);
    tbody.appendChild(row);
  } else {
    rows.forEach((item) => {
      const row = document.createElement("tr");
      columns.forEach(([key]) => {
        const cell = document.createElement("td");
        cell.textContent = formatValue(item[key], key);
        row.appendChild(cell);
      });
      tbody.appendChild(row);
    });
  }

  table.replaceChildren(thead, tbody);
}

function renderDynamicTable(tableId, rows) {
  const keys = rows && rows.length ? Object.keys(rows[0]) : ["stage", "board_type", "board_name", "error"];
  renderTable(
    tableId,
    rows,
    keys.map((key) => [key, key]),
  );
}

function renderThemeChart(rows) {
  const chart = byId("sectorThemeChart");
  if (!rows || rows.length === 0) {
    chart.innerHTML = '<p class="panel-note">暂无主题强度数据。</p>';
    return;
  }
  const topRows = rows.slice(0, 12);
  const maxScore = Math.max(...topRows.map((row) => Number(row.theme_score || 0)), 0.01);
  chart.innerHTML = topRows
    .map((row) => {
      const score = Number(row.theme_score || 0);
      const width = Math.max((score / maxScore) * 100, 2);
      return `
        <div class="sector-bar-row">
          <span>${escapeHtml(row.theme_name || "-")}</span>
          <div class="sector-bar-track"><i style="width:${width}%"></i></div>
          <strong>${escapeHtml(formatValue(score, "theme_score"))}</strong>
        </div>
      `;
    })
    .join("");
}

function renderMessages(payload) {
  const messages = payload.messages || [];
  const box = byId("sectorMessageBox");
  if (messages.length === 0) {
    box.innerHTML = '<p class="status-line">未发现读取异常。</p>';
    return;
  }
  box.innerHTML = messages.map((message) => `<p class="status-line">${escapeHtml(message)}</p>`).join("");
}

function renderPayload(payload) {
  state.payload = payload;
  renderSummary(payload.summary || {});
  renderThemeChart(payload.latest_themes || []);
  renderTable("sectorThemeTable", payload.latest_themes || [], themeColumns);
  renderTable("sectorBoardTable", payload.latest_boards || [], boardColumns);
  renderTable("sectorExposureTable", payload.stock_exposure || [], exposureColumns);
  renderTable("sectorMappingTable", payload.mapping_rows || [], mappingColumns);
  renderDynamicTable("sectorErrorTable", payload.error_rows || []);
  renderMessages(payload);
  const themeCount = payload.latest_themes?.length || 0;
  const boardCount = payload.latest_boards?.length || 0;
  setStatus(`读取完成：最新主题 ${themeCount} 条，强势板块 ${boardCount} 条。`);
}

async function loadSectorOverview() {
  const processedDir = byId("sectorProcessedDir").value.trim() || defaults.processedDir;
  const reportDir = byId("sectorReportDir").value.trim() || defaults.reportDir;
  const params = new URLSearchParams({ processed_dir: processedDir, report_dir: reportDir });
  setStatus("正在读取板块研究结果。");
  try {
    const response = await fetch(`/api/sector/overview?${params.toString()}`);
    const text = await response.text();
    let payload = {};
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(text || "接口返回不是有效 JSON");
    }
    if (!response.ok) {
      throw new Error(payload.detail || "接口读取失败");
    }
    renderPayload(payload);
  } catch (error) {
    setStatus(`读取失败：${error.message}`, true);
  }
}

document.querySelectorAll(".sector-page .tab-button").forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
});

byId("sectorForm").addEventListener("submit", (event) => {
  event.preventDefault();
  loadSectorOverview();
});

byId("resetSectorBtn").addEventListener("click", () => {
  byId("sectorProcessedDir").value = defaults.processedDir;
  byId("sectorReportDir").value = defaults.reportDir;
  loadSectorOverview();
});

loadSectorOverview();
