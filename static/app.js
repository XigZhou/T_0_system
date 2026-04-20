const form = document.getElementById("btForm");
const runBtn = document.getElementById("runBtn");
const exportBtn = document.getElementById("exportBtn");
const statusEl = document.getElementById("status");
const summaryGrid = document.getElementById("summaryGrid");
const equityChart = document.getElementById("equityChart");
const pickTable = document.getElementById("pickTable");
const tradeTable = document.getElementById("tradeTable");
const contributionTable = document.getElementById("contributionTable");
const diagText = document.getElementById("diagText");

function buildPayload() {
  return {
    processed_dir: document.getElementById("processedDir").value.trim(),
    start_date: document.getElementById("startDate").value.trim(),
    end_date: document.getElementById("endDate").value.trim(),
    buy_condition: document.getElementById("buyCondition").value.trim(),
    score_expression: document.getElementById("scoreExpression").value.trim(),
    top_n: Number(document.getElementById("topN").value),
    initial_cash: Number(document.getElementById("initialCash").value),
    lot_size: Number(document.getElementById("lotSize").value),
    buy_fee_rate: Number(document.getElementById("buyFeeRate").value),
    sell_fee_rate: Number(document.getElementById("sellFeeRate").value),
    stamp_tax_sell: Number(document.getElementById("stampTaxSell").value),
    realistic_execution: document.getElementById("realisticExecution").value === "true",
    slippage_bps: Number(document.getElementById("slippageBps").value),
    min_commission: Number(document.getElementById("minCommission").value),
  };
}

function setStatus(text, error = false) {
  statusEl.textContent = text;
  statusEl.style.color = error ? "#8a2f13" : "";
}

function formatValue(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (typeof value === "number") {
    const absValue = Math.abs(value);
    if (absValue >= 1000) {
      return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
    }
    return value.toLocaleString("zh-CN", { maximumFractionDigits: 6 });
  }
  return String(value);
}

function renderSummary(summary = {}) {
  const keys = [
    ["ending_equity", "期末权益"],
    ["total_return", "总收益率"],
    ["annualized_return", "年化收益率"],
    ["max_drawdown", "最大回撤"],
    ["buy_count", "买入次数"],
    ["sell_count", "卖出次数"],
    ["win_rate", "胜率"],
    ["avg_trade_return", "平均单笔收益"],
  ];
  summaryGrid.innerHTML = keys
    .map(([key, label]) => {
      let value = summary[key];
      if (["total_return", "annualized_return", "max_drawdown", "win_rate", "avg_trade_return"].includes(key) && typeof value === "number") {
        value = `${(value * 100).toFixed(2)}%`;
      } else {
        value = formatValue(value);
      }
      return `<div class="metric"><p class="metric-label">${label}</p><p class="metric-value">${value}</p></div>`;
    })
    .join("");
}

function ensureTableWrap(el) {
  const wrap = el.closest(".table-wrap");
  if (!wrap) {
    return;
  }
  const currentEmpty = wrap.querySelector(".empty");
  if (currentEmpty) {
    currentEmpty.remove();
  }
  if (!wrap.contains(el)) {
    wrap.appendChild(el);
  }
}

function renderTable(el, rows, preferredOrder = []) {
  const wrap = el.closest(".table-wrap");
  if (!rows || !rows.length) {
    if (wrap) {
      wrap.innerHTML = '<div class="empty">暂无结果</div>';
    }
    return;
  }

  if (wrap) {
    wrap.innerHTML = "";
    wrap.appendChild(el);
  }
  ensureTableWrap(el);

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
  const thead = `<thead><tr>${orderedKeys.map((key) => `<th>${key}</th>`).join("")}</tr></thead>`;
  const tbody = `<tbody>${rows
    .map(
      (row) =>
        `<tr>${orderedKeys
          .map((key) => `<td>${formatValue(row[key])}</td>`)
          .join("")}</tr>`
    )
    .join("")}</tbody>`;
  el.innerHTML = `${thead}${tbody}`;
}

function renderChart(rows) {
  if (!rows || !rows.length) {
    equityChart.innerHTML = '<div class="empty">暂无资金曲线</div>';
    return;
  }
  const values = rows.map((row) => Number(row.equity));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1);
  const width = 900;
  const height = 260;
  const points = values
    .map((value, idx) => {
      const x = (idx / Math.max(values.length - 1, 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${x},${y}`;
    })
    .join(" ");
  const lastValue = values[values.length - 1];
  equityChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height + 40}" preserveAspectRatio="none" aria-label="equity curve">
      <defs>
        <linearGradient id="equityFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="rgba(172,79,42,0.35)"></stop>
          <stop offset="100%" stop-color="rgba(172,79,42,0.02)"></stop>
        </linearGradient>
      </defs>
      <polyline
        fill="none"
        stroke="rgba(172,79,42,0.96)"
        stroke-width="4"
        stroke-linecap="round"
        stroke-linejoin="round"
        points="${points}"
      ></polyline>
      <polygon
        fill="url(#equityFill)"
        points="0,${height} ${points} ${width},${height}"
      ></polygon>
      <text x="${width}" y="${height + 28}" text-anchor="end" fill="#6a6256" font-size="20">
        ${formatValue(lastValue)}
      </text>
    </svg>
  `;
}

function applyResult(result) {
  renderSummary(result.summary);
  renderChart(result.daily_rows);
  renderTable(pickTable, result.pick_rows, ["trade_date", "symbol", "name", "rank", "score", "close", "can_sell_t1"]);
  renderTable(tradeTable, result.trade_rows, ["trade_date", "symbol", "name", "action", "price", "shares", "gross_amount", "fees", "net_amount", "cash_after", "trade_return"]);
  renderTable(contributionTable, result.contribution_rows, ["symbol", "realized_pnl", "trade_count", "win_rate", "avg_trade_return"]);
  diagText.textContent = `载入 ${result.diagnostics.file_count} 个文件，出现候选日 ${result.diagnostics.candidate_days} 天，触发买入日 ${result.diagnostics.picked_days} 天。`;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `request failed: ${response.status}`);
  }
  return response;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = buildPayload();
  runBtn.disabled = true;
  setStatus("正在运行批量回测...");
  try {
    const response = await postJson("/api/run-backtest", payload);
    const result = await response.json();
    applyResult(result);
    setStatus("回测完成。");
  } catch (error) {
    setStatus(`回测失败: ${error.message}`, true);
  } finally {
    runBtn.disabled = false;
  }
});

exportBtn.addEventListener("click", async () => {
  const payload = buildPayload();
  exportBtn.disabled = true;
  setStatus("正在准备导出文件...");
  try {
    const response = await postJson("/api/run-backtest-export", payload);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "overnight_backtest_export.zip";
    a.click();
    URL.revokeObjectURL(url);
    setStatus("导出完成。");
  } catch (error) {
    setStatus(`导出失败: ${error.message}`, true);
  } finally {
    exportBtn.disabled = false;
  }
});
