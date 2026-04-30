const form = document.getElementById("btForm");
const runBtn = document.getElementById("runBtn");
const exportBtn = document.getElementById("exportBtn");
const statusEl = document.getElementById("status");
const summaryGrid = document.getElementById("summaryGrid");
const equityChart = document.getElementById("equityChart");
const pickTable = document.getElementById("pickTable");
const tradeTable = document.getElementById("tradeTable");
const contributionTable = document.getElementById("contributionTable");
const conditionTable = document.getElementById("conditionTable");
const topKTable = document.getElementById("topKTable");
const rankTable = document.getElementById("rankTable");
const yearTable = document.getElementById("yearTable");
const monthTable = document.getElementById("monthTable");
const exitReasonTable = document.getElementById("exitReasonTable");
const openPositionTable = document.getElementById("openPositionTable");
const pendingSellTable = document.getElementById("pendingSellTable");
const diagText = document.getElementById("diagText");
const tabButtons = Array.from(document.querySelectorAll("[data-tab]"));
const tabPanels = Array.from(document.querySelectorAll("[data-tab-panel]"));
const modeInputs = Array.from(document.querySelectorAll('input[name="backtestMode"]'));
const modeOptions = Array.from(document.querySelectorAll(".mode-option"));

const PERCENT_KEYS = new Set([
  "total_return",
  "annualized_return",
  "best_return_since_entry",
  "max_drawdown",
  "drawdown",
  "drawdown_from_peak",
  "holding_return",
  "period_return",
  "unrealized_return",
  "win_rate",
  "avg_trade_return",
  "median_trade_return",
  "best_trade_return",
  "worst_trade_return",
  "trade_return",
  "signal_curve_return",
  "topn_fill_rate",
  "topk_fill_rate",
  "candidate_day_ratio",
  "p10_trade_return",
  "p90_trade_return",
  "total_signal_return",
  "best_year_return",
  "worst_year_return",
  "recommended_topk_avg_trade_return",
  "recommended_topk_median_trade_return",
  "m5",
  "m10",
  "m20",
  "m60",
  "m120",
  "hs300_m5",
  "hs300_m10",
  "hs300_m20",
  "hs300_m60",
  "hs300_m120",
  "industry_m20",
  "industry_m60",
  "industry_rank_m20",
  "industry_rank_m60",
  "industry_up_ratio",
  "industry_strong_ratio",
  "stock_vs_industry_m20",
  "stock_vs_industry_m60",
]);

const COLUMN_LABELS = {
  action: "操作",
  avg_holding_days: "平均持有天数",
  avg_signals_per_day: "平均每日信号数",
  avg_trade_return: "平均单笔收益",
  board: "板块",
  blocked_entry_count: "买入阻塞信号数",
  blocked_reentry_count: "持仓期跳过信号数",
  body_pct: "实体占比",
  buy_count: "买入次数",
  buy_fee: "买入费用",
  buy_net_amount: "买入净金额",
  cash: "现金",
  cash_after: "交易后现金",
  candidate_count: "候选数",
  candidate_day_ratio: "有候选日占比",
  category: "分类",
  completed_signal_count: "完成信号数",
  completed_days: "完成信号日数",
  drawdown: "回撤",
  ending_equity: "期末权益",
  entry_can_buy_open: "买入日可开盘买入",
  entry_raw_open: "买入日未复权开盘价",
  entry_price: "买入执行价",
  equity: "权益",
  execution_note: "执行说明",
  exit_can_sell_open: "卖出日可开盘卖出",
  exit_raw_open: "卖出日未复权开盘价",
  exit_reason: "退出原因",
  exit_signal_date: "退出信号日",
  exit_type: "退出类型",
  exit_price: "卖出执行价",
  fees: "费用",
  gross_amount: "成交金额",
  holding_days: "持有天数",
  hs300_m5: "沪深300五日动量",
  hs300_m10: "沪深300十日动量",
  hs300_m20: "沪深300二十日动量",
  hs300_m60: "沪深300六十日动量",
  hs300_m120: "沪深300一百二十日动量",
  hs300_pct_chg: "沪深300当日涨跌幅",
  industry: "行业",
  industry_amount: "行业成交额",
  industry_amount20: "行业二十日均额",
  industry_amount_ratio: "行业成交额放大倍数",
  industry_m20: "行业二十日动量",
  industry_m60: "行业六十日动量",
  industry_rank_m20: "行业二十日强度排名",
  industry_rank_m60: "行业六十日强度排名",
  industry_stock_count: "行业股票数",
  industry_strong_ratio: "行业强势股占比",
  industry_up_ratio: "行业上涨股票占比",
  industry_valid_m20_count: "行业有效动量样本数",
  listed_days: "上市天数",
  lower_shadow_pct: "下影线占比",
  m5: "五日动量",
  m10: "十日动量",
  m20: "二十日动量",
  m60: "六十日动量",
  m120: "一百二十日动量",
  market: "市场",
  market_value: "持仓市值",
  max_drawdown: "最大回撤",
  max_exit_date: "最晚卖出日",
  median_trade_return: "中位单笔收益",
  metric: "指标",
  name: "股票名称",
  net_amount: "净金额",
  pending_order_count: "待执行订单数",
  period: "周期",
  period_return: "周期收益",
  pct_chg: "当日涨跌幅",
  picked_count: "入选数",
  picked_days: "触发选股日数",
  planned_entry_date: "计划买入日",
  planned_exit_date: "计划卖出日",
  position_count: "持仓数",
  price: "成交价",
  price_pnl: "价差盈亏",
  rank: "排名",
  recommendation_score: "辅助推荐分",
  recommended: "建议",
  recommended_top_k: "建议TopK",
  recommended_topk_avg_trade_return: "建议TopK平均收益",
  recommended_topk_median_trade_return: "建议TopK中位收益",
  recommended_topk_profit_factor: "建议TopK收益因子",
  recommended_topk_score: "建议TopK辅助分",
  reading: "怎么看",
  realized_pnl: "已实现盈亏",
  reason: "说明",
  ret_accel_3: "三日收益加速度",
  score: "评分",
  sell_condition_enabled: "启用卖出条件",
  sell_count: "卖出次数",
  sell_fee: "卖出费用",
  sell_net_amount: "卖出净金额",
  shares: "股数",
  signal_count: "信号数",
  signal_close: "信号日前复权收盘价",
  close_pos_in_bar: "收盘所在日K位置",
  signal_curve_return: "信号净值收益",
  signal_date: "信号日期",
  signal_raw_close: "信号日未复权收盘价",
  status: "状态",
  stock_vs_industry_m20: "个股相对行业二十日动量",
  stock_vs_industry_m60: "个股相对行业六十日动量",
  symbol: "股票代码",
  top_n: "选股数量",
  top_k: "累计TopK",
  topk_fill_rate: "TopK填满率",
  topn_fill_rate: "选股数量填满率",
  trade_count: "交易次数",
  trade_date: "交易日期",
  trade_return: "交易收益",
  total_signal_return: "累计信号收益",
  unrealized_pnl: "浮动盈亏",
  unrealized_return: "浮动收益",
  upper_shadow_pct: "上影线占比",
  valuation_date: "估值日期",
  value: "数值",
  vol_ratio_5: "五日量比",
  vr: "量比",
  win_rate: "胜率",
  year_count: "年份数",
  profitable_years: "盈利年份数",
  best_year_return: "最好年份收益",
  worst_year_return: "最差年份收益",
  quality_note: "质量解读",
};

const VALUE_LABELS = {
  BUY: "买入",
  BUY_BLOCKED: "买入阻塞",
  BUY_SKIPPED_CASH: "资金不足跳过",
  BUY_SKIPPED_CUTOFF: "截止日不买入",
  SELL: "卖出",
  SELL_BLOCKED: "卖出阻塞",
  entry_date_row_missing: "买入日记录缺失",
  fixed_or_max_exit: "固定或最大持有退出",
  "entry date row missing": "买入日记录缺失",
  "insufficient cash for one lot under per_trade_budget": "可用资金不足一手",
  "net cash requirement exceeds available cash": "所需现金超过可用现金",
  "raw_open missing on planned entry date": "计划买入日缺少未复权开盘价",
  "raw_open missing on scheduled exit date": "计划卖出日缺少未复权开盘价",
  "selected on signal day and executed at next open": "信号日入选，次日开盘成交",
  "sell at scheduled or next available open": "计划日或下一个可卖开盘成交",
  "strict execution blocked buy at open": "严格成交模式下开盘不可买",
  "strict execution blocked sell at open": "严格成交模式下开盘不可卖",
  "cutoff date only marks existing positions; no new buy is executed": "截止日只估值已有持仓，不再新买入",
};

function setActiveTab(tabName) {
  tabButtons.forEach((button) => {
    const isActive = button.dataset.tab === tabName;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  tabPanels.forEach((panel) => {
    const isActive = panel.dataset.tabPanel === tabName;
    panel.classList.toggle("active", isActive);
    panel.hidden = !isActive;
  });
}

tabButtons.forEach((button) => {
  button.addEventListener("click", () => setActiveTab(button.dataset.tab));
});

if (tabButtons.length) {
  const initialTab = tabButtons.find((button) => button.classList.contains("active"))?.dataset.tab || tabButtons[0].dataset.tab;
  setActiveTab(initialTab);
}

function getBacktestMode() {
  return modeInputs.find((input) => input.checked)?.value || "signal_quality";
}

function updateBacktestModeUI() {
  const mode = getBacktestMode();
  const isSignalQuality = mode === "signal_quality";
  document.body.classList.toggle("signal-quality-mode", isSignalQuality);
  form.classList.toggle("signal-quality-mode", isSignalQuality);
  modeOptions.forEach((option) => {
    const input = option.querySelector('input[name="backtestMode"]');
    option.classList.toggle("active", input?.value === mode);
  });
  exportBtn.disabled = isSignalQuality;
  exportBtn.title = isSignalQuality ? "信号质量回测暂不支持导出，请切换到实盘账户回测后导出。" : "";
  if (isSignalQuality && tabButtons.find((button) => button.dataset.tab === "cutoff")?.classList.contains("active")) {
    setActiveTab("condition");
  }
  if (isSignalQuality) {
    setStatus("默认运行信号质量回测，资金输入不会影响本次结果。");
  } else {
    setStatus("当前运行实盘账户回测，会模拟现金、仓位和资金不足跳过。");
  }
}

modeInputs.forEach((input) => {
  input.addEventListener("change", updateBacktestModeUI);
});
updateBacktestModeUI();

function buildPayload() {
  return {
    processed_dir: document.getElementById("processedDir").value.trim(),
    start_date: document.getElementById("startDate").value.trim(),
    end_date: document.getElementById("endDate").value.trim(),
    buy_condition: document.getElementById("buyCondition").value.trim(),
    sell_condition: document.getElementById("sellCondition").value.trim(),
    score_expression: document.getElementById("scoreExpression").value.trim(),
    top_n: Number(document.getElementById("topN").value),
    initial_cash: Number(document.getElementById("initialCash").value),
    per_trade_budget: Number(document.getElementById("perTradeBudget").value),
    entry_offset: Number(document.getElementById("entryOffset").value),
    exit_offset: Number(document.getElementById("exitOffset").value),
    min_hold_days: Number(document.getElementById("minHoldDays").value),
    max_hold_days: Number(document.getElementById("maxHoldDays").value),
    lot_size: Number(document.getElementById("lotSize").value),
    buy_fee_rate: Number(document.getElementById("buyFeeRate").value),
    sell_fee_rate: Number(document.getElementById("sellFeeRate").value),
    stamp_tax_sell: Number(document.getElementById("stampTaxSell").value),
    realistic_execution: document.getElementById("realisticExecution").value === "true",
    settlement_mode: document.getElementById("settlementMode").value,
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

function formatCellValue(key, value) {
  if (typeof value === "string") {
    if (key === "exit_reason" && value.startsWith("sell_condition:")) {
      return "卖出条件触发";
    }
    if (VALUE_LABELS[value]) {
      return VALUE_LABELS[value];
    }
  }
  if (PERCENT_KEYS.has(key) && typeof value === "number") {
    return `${(value * 100).toFixed(2)}%`;
  }
  return formatValue(value);
}

function formatHeader(key) {
  return COLUMN_LABELS[key] || key;
}

function average(values) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

function median(values) {
  if (!values.length) {
    return 0;
  }
  const ordered = [...values].sort((a, b) => a - b);
  const mid = Math.floor(ordered.length / 2);
  return ordered.length % 2 ? ordered[mid] : (ordered[mid - 1] + ordered[mid]) / 2;
}

function maxDrawdownFromEquity(values) {
  let peak = 0;
  let maxDrawdown = 0;
  values.forEach((value) => {
    peak = Math.max(peak, value);
    if (peak > 0) {
      maxDrawdown = Math.min(maxDrawdown, value / peak - 1);
    }
  });
  return Math.abs(maxDrawdown);
}

function profitFactor(returns) {
  const gains = returns.filter((value) => value > 0).reduce((sum, value) => sum + value, 0);
  const losses = Math.abs(returns.filter((value) => value < 0).reduce((sum, value) => sum + value, 0));
  return gains > 0 && losses > 0 ? gains / losses : 0;
}

function periodKey(tradeDate, kind) {
  const text = String(tradeDate || "");
  return kind === "year" ? text.slice(0, 4) : `${text.slice(0, 4)}-${text.slice(4, 6)}`;
}

function buildFallbackPeriodRows(dailyRows = [], tradeRows = [], kind = "year") {
  const dailyGroups = new Map();
  dailyRows.forEach((row) => {
    const key = periodKey(row.trade_date, kind);
    if (!key || key.includes("-") && key.length < 7) {
      return;
    }
    if (!dailyGroups.has(key)) {
      dailyGroups.set(key, []);
    }
    dailyGroups.get(key).push(row);
  });

  const tradeGroups = new Map();
  tradeRows.forEach((row) => {
    const key = periodKey(row.trade_date, kind);
    if (!key || key.includes("-") && key.length < 7) {
      return;
    }
    if (!tradeGroups.has(key)) {
      tradeGroups.set(key, []);
    }
    tradeGroups.get(key).push(row);
  });

  return Array.from(dailyGroups.keys()).sort().map((key) => {
    const periodDaily = dailyGroups.get(key);
    const equities = periodDaily.map((row) => Number(row.equity)).filter((value) => Number.isFinite(value));
    const startEquity = equities[0] || 0;
    const endEquity = equities[equities.length - 1] || 0;
    const trades = tradeGroups.get(key) || [];
    const sellReturns = trades
      .filter((row) => row.action === "SELL" && row.trade_return !== null && row.trade_return !== undefined)
      .map((row) => Number(row.trade_return))
      .filter((value) => Number.isFinite(value));
    return {
      period: key,
      period_return: startEquity > 0 ? endEquity / startEquity - 1 : 0,
      max_drawdown: maxDrawdownFromEquity(equities),
      ending_equity: endEquity,
      picked_days: periodDaily.filter((row) => Number(row.picked_count || 0) > 0).length,
      buy_count: trades.filter((row) => row.action === "BUY").length,
      sell_count: sellReturns.length,
      win_rate: sellReturns.length ? sellReturns.filter((value) => value > 0).length / sellReturns.length : 0,
      avg_trade_return: average(sellReturns),
    };
  });
}

function buildFallbackExitReasonRows(tradeRows = []) {
  const sellTrades = tradeRows.filter((row) => row.action === "SELL");
  if (!sellTrades.length) {
    return [{
      exit_type: "暂无卖出交易",
      trade_count: 0,
      win_rate: 0,
      avg_trade_return: 0,
      median_trade_return: 0,
      avg_holding_days: 0,
    }];
  }

  const groups = new Map();
  sellTrades.forEach((row) => {
    const rawReason = String(row.exit_reason || "");
    const label = rawReason.startsWith("sell_condition") ? "卖出条件触发" : "固定或最大持有退出";
    if (!groups.has(label)) {
      groups.set(label, []);
    }
    groups.get(label).push(row);
  });

  return Array.from(groups.entries()).map(([label, rows]) => {
    const returns = rows
      .map((row) => Number(row.trade_return))
      .filter((value) => Number.isFinite(value));
    const holdingDays = rows
      .map((row) => Number(row.holding_days))
      .filter((value) => Number.isFinite(value));
    return {
      exit_type: label,
      trade_count: rows.length,
      win_rate: returns.length ? returns.filter((value) => value > 0).length / returns.length : 0,
      avg_trade_return: average(returns),
      median_trade_return: median(returns),
      avg_holding_days: average(holdingDays),
    };
  });
}

function buildFallbackConditionRows(result) {
  const dailyRows = result.daily_rows || [];
  const tradeRows = result.trade_rows || [];
  const diagnostics = result.diagnostics || {};
  const signalDays = Number(diagnostics.signal_days || dailyRows.length || 0);
  const candidateDays = Number(diagnostics.candidate_days || dailyRows.filter((row) => Number(row.candidate_count || 0) > 0).length);
  const totalCandidates = dailyRows.reduce((sum, row) => sum + Number(row.candidate_count || 0), 0);
  const totalPicks = dailyRows.reduce((sum, row) => sum + Number(row.picked_count || 0), 0);
  const topN = Number(document.getElementById("topN").value || 0);
  const maxPossiblePicks = signalDays * topN;
  const sellReturns = tradeRows
    .filter((row) => row.action === "SELL" && row.trade_return !== null && row.trade_return !== undefined)
    .map((row) => Number(row.trade_return))
    .filter((value) => Number.isFinite(value));
  const blockedBuyCount = tradeRows.filter((row) => row.action === "BUY_BLOCKED").length;
  const blockedSellCount = tradeRows.filter((row) => row.action === "SELL_BLOCKED").length;
  const skippedCashCount = tradeRows.filter((row) => row.action === "BUY_SKIPPED_CASH").length;
  const totalFees = tradeRows
    .filter((row) => row.action === "BUY" || row.action === "SELL")
    .reduce((sum, row) => sum + Number(row.fees || 0), 0);
  const initialCash = Number(result.summary?.initial_cash || document.getElementById("initialCash").value || 0);
  const holdingDays = tradeRows
    .filter((row) => row.action === "SELL")
    .map((row) => Number(row.holding_days))
    .filter((value) => Number.isFinite(value));
  const yearRows = result.year_rows?.length ? result.year_rows : buildFallbackPeriodRows(dailyRows, tradeRows, "year");
  const profitableYears = yearRows.filter((row) => Number(row.period_return || 0) > 0).length;
  const yearReturns = yearRows.map((row) => Number(row.period_return || 0));

  return [
    ["信号覆盖", "有候选日占比", `${((signalDays ? candidateDays / signalDays : 0) * 100).toFixed(2)}%`, "越高说明条件不至于过窄；太低时样本少，结果容易偶然。"],
    ["信号覆盖", "选股数量填满率", `${((maxPossiblePicks ? totalPicks / maxPossiblePicks : 0) * 100).toFixed(2)}%`, "低于100%说明很多信号日没有足够股票可买，选股数量可能偏大或条件偏严。"],
    ["信号覆盖", "平均候选数/信号日", `${(signalDays ? totalCandidates / signalDays : 0).toFixed(2)}`, "用于判断每天可选择空间；太低时评分表达式很难发挥作用。"],
    ["交易质量", "胜率", `${((sellReturns.length ? sellReturns.filter((value) => value > 0).length / sellReturns.length : 0) * 100).toFixed(2)}%`, "胜率要和平均收益一起看；高胜率但单次亏损很大也不稳。"],
    ["交易质量", "平均/中位单笔收益", `${(average(sellReturns) * 100).toFixed(2)}% / ${(median(sellReturns) * 100).toFixed(2)}%`, "中位数更能反映普通交易，均值明显更高时可能依赖少数大赚交易。"],
    ["交易质量", "收益因子", profitFactor(sellReturns).toFixed(2), "大于1说明盈利交易合计幅度超过亏损交易，越高越好。"],
    ["执行摩擦", "买入阻塞/资金跳过", `${blockedBuyCount} / ${skippedCashCount}`, "阻塞多说明信号落到涨跌停或停牌环境，资金跳过多说明预算或股价不匹配。"],
    ["执行摩擦", "卖出阻塞", `${blockedSellCount}`, "卖出阻塞越多，真实成交风险越高，资金曲线可能低估流动性压力。"],
    ["执行摩擦", "手续费滑点成本", `${totalFees.toFixed(2)} / ${((initialCash ? totalFees / initialCash : 0) * 100).toFixed(2)}%`, "前者是累计成本，后者是相对初始资金占比；短线策略要特别盯这个数。"],
    ["持仓退出", "平均持有天数", average(holdingDays).toFixed(2), "用于确认条件是否符合预期持仓节奏，过短会放大交易成本影响。"],
    ["时间稳定性", "盈利年份", `${profitableYears}/${yearRows.length}`, "比单一总收益更重要；只有一两个年份赚钱时要小心过拟合。"],
    ["时间稳定性", "最好/最差年份", `${(Math.max(...yearReturns, 0) * 100).toFixed(2)}% / ${(Math.min(...yearReturns, 0) * 100).toFixed(2)}%`, "观察收益是否集中在某一年，以及最差年份能否接受。"],
  ].map(([category, metric, value, reading]) => ({ category, metric, value, reading }));
}

function ensureDiagnosticRows(result) {
  if (result.summary?.result_mode === "signal_quality") {
    result.condition_rows = result.condition_rows || [];
    result.topk_rows = result.topk_rows || [];
    result.rank_rows = result.rank_rows || [];
    result.year_rows = result.year_rows || [];
    result.month_rows = result.month_rows || [];
    result.exit_reason_rows = result.exit_reason_rows || [];
    return result;
  }
  if (!result.condition_rows?.length) {
    result.condition_rows = buildFallbackConditionRows(result);
  }
  if (!result.year_rows?.length) {
    result.year_rows = buildFallbackPeriodRows(result.daily_rows || [], result.trade_rows || [], "year");
  }
  if (!result.month_rows?.length) {
    result.month_rows = buildFallbackPeriodRows(result.daily_rows || [], result.trade_rows || [], "month");
  }
  if (!result.exit_reason_rows?.length) {
    result.exit_reason_rows = buildFallbackExitReasonRows(result.trade_rows || []);
  }
  return result;
}

function renderSummary(summary = {}) {
  const signalQualityKeys = [
    ["signal_count", "入选信号数"],
    ["completed_signal_count", "完成信号数"],
    ["avg_trade_return", "平均单笔收益"],
    ["median_trade_return", "中位单笔收益"],
    ["win_rate", "胜率"],
    ["profit_factor", "收益因子"],
    ["recommended_top_k", "建议TopK"],
    ["signal_curve_return", "信号净值收益"],
    ["max_drawdown", "信号净值回撤"],
    ["candidate_day_ratio", "有候选日占比"],
    ["topn_fill_rate", "TopN填满率"],
    ["avg_holding_days", "平均持有天数"],
    ["blocked_entry_count", "买入阻塞信号"],
    ["blocked_reentry_count", "持仓期跳过信号"],
    ["open_signal_count", "未完成信号"],
    ["best_trade_return", "最好单笔"],
    ["worst_trade_return", "最差单笔"],
    ["avg_signals_per_day", "平均每日信号"],
  ];
  const accountKeys = [
    ["ending_equity", "期末权益"],
    ["ending_cash", "期末现金"],
    ["ending_market_value", "期末持仓市值"],
    ["total_return", "总收益率"],
    ["annualized_return", "年化收益率"],
    ["max_drawdown", "最大回撤"],
    ["buy_count", "买入次数"],
    ["sell_count", "卖出次数"],
    ["win_rate", "胜率"],
    ["avg_trade_return", "平均单笔收益"],
    ["median_trade_return", "中位单笔收益"],
    ["profit_factor", "收益因子"],
    ["avg_holding_days", "平均持有天数"],
    ["total_fees", "手续费滑点成本"],
    ["open_position_count", "期末持仓数"],
    ["pending_sell_signal_count", "截止日卖出提醒"],
  ];
  const keys = summary.result_mode === "signal_quality" ? signalQualityKeys : accountKeys;
  summaryGrid.innerHTML = keys
    .map(([key, label]) => {
      const value = formatCellValue(key, summary[key]);
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
  const thead = `<thead><tr>${orderedKeys.map((key) => `<th>${formatHeader(key)}</th>`).join("")}</tr></thead>`;
  const tbody = `<tbody>${rows
    .map(
      (row) =>
        `<tr>${orderedKeys
          .map((key) => `<td>${formatCellValue(key, row[key])}</td>`)
          .join("")}</tr>`
    )
    .join("")}</tbody>`;
  el.innerHTML = `${thead}${tbody}`;
}

function renderChart(rows, valueLabel = "权益") {
  if (!rows || !rows.length) {
    equityChart.innerHTML = '<div class="empty">暂无曲线</div>';
    return;
  }
  const values = rows.map((row) => Number(row.equity));
  const drawdowns = rows.map((row) => Math.abs(Number(row.drawdown || 0)));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1);
  const width = 900;
  const height = 180;
  const equityHeight = 118;
  const drawdownTop = 132;
  const drawdownHeight = 36;
  const maxDrawdown = Math.max(...drawdowns, 0.001);
  const points = values
    .map((value, idx) => {
      const x = (idx / Math.max(values.length - 1, 1)) * width;
      const y = equityHeight - ((value - min) / span) * equityHeight;
      return `${x},${y}`;
    })
    .join(" ");
  const drawdownPoints = drawdowns
    .map((value, idx) => {
      const x = (idx / Math.max(drawdowns.length - 1, 1)) * width;
      const y = drawdownTop + (value / maxDrawdown) * drawdownHeight;
      return `${x},${y}`;
    })
    .join(" ");
  const lastValue = values[values.length - 1];
  const latestDrawdown = drawdowns[drawdowns.length - 1] || 0;
  equityChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height + 34}" preserveAspectRatio="none" aria-label="资金与回撤曲线">
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
        points="0,${equityHeight} ${points} ${width},${equityHeight}"
      ></polygon>
      <line x1="0" y1="${drawdownTop}" x2="${width}" y2="${drawdownTop}" stroke="rgba(28,26,23,0.16)" stroke-width="1"></line>
      <polyline
        fill="none"
        stroke="rgba(138,47,19,0.75)"
        stroke-width="3"
        stroke-linecap="round"
        stroke-linejoin="round"
        points="${drawdownPoints}"
      ></polyline>
      <text x="0" y="${height + 24}" fill="#6a6256" font-size="18">
        回撤 ${formatCellValue("drawdown", latestDrawdown)}
      </text>
      <text x="${width}" y="${height + 24}" text-anchor="end" fill="#6a6256" font-size="18">
        ${valueLabel} ${formatValue(lastValue)}
      </text>
    </svg>
  `;
}

function applyResult(result) {
  result = ensureDiagnosticRows(result);
  const isSignalQuality = result.summary?.result_mode === "signal_quality";
  renderSummary(result.summary);
  renderChart(result.daily_rows, isSignalQuality ? "信号净值" : "权益");
  renderTable(conditionTable, result.condition_rows, ["category", "metric", "value", "reading"]);
  renderTable(topKTable, result.topk_rows, ["recommended", "top_k", "signal_count", "completed_signal_count", "picked_days", "topk_fill_rate", "win_rate", "avg_trade_return", "median_trade_return", "profit_factor", "signal_curve_return", "max_drawdown", "profitable_years", "year_count", "recommendation_score", "quality_note"]);
  renderTable(rankTable, result.rank_rows, ["rank", "signal_count", "win_rate", "avg_trade_return", "median_trade_return", "p10_trade_return", "p90_trade_return", "avg_holding_days"]);
  renderTable(yearTable, result.year_rows, ["period", "period_return", "max_drawdown", "ending_equity", "picked_days", "signal_count", "buy_count", "sell_count", "win_rate", "avg_trade_return", "median_trade_return"]);
  renderTable(monthTable, result.month_rows, ["period", "period_return", "max_drawdown", "ending_equity", "picked_days", "signal_count", "buy_count", "sell_count", "win_rate", "avg_trade_return", "median_trade_return"]);
  renderTable(exitReasonTable, result.exit_reason_rows, ["exit_type", "trade_count", "win_rate", "avg_trade_return", "median_trade_return", "avg_holding_days"]);
  renderTable(openPositionTable, result.open_position_rows, ["valuation_date", "symbol", "name", "shares", "buy_date", "buy_price", "current_raw_close", "market_value", "unrealized_pnl", "unrealized_return", "holding_days", "planned_exit_date"]);
  renderTable(pendingSellTable, result.pending_sell_rows, ["signal_date", "planned_sell_date", "symbol", "name", "shares", "buy_date", "buy_price", "current_raw_close", "holding_return", "best_return_since_entry", "drawdown_from_peak", "sell_condition", "reason"]);
  if (isSignalQuality) {
    renderTable(pickTable, result.pick_rows, ["signal_date", "symbol", "name", "rank", "score", "status", "planned_entry_date", "planned_exit_date", "trade_date", "entry_raw_open", "exit_raw_open", "trade_return", "holding_days", "exit_type", "execution_note"]);
    renderTable(tradeTable, result.trade_rows, ["trade_date", "signal_date", "symbol", "name", "rank", "score", "entry_price", "exit_price", "trade_return", "holding_days", "exit_type", "exit_signal_date"]);
    renderTable(contributionTable, result.contribution_rows, ["symbol", "name", "signal_count", "total_signal_return", "win_rate", "avg_trade_return", "median_trade_return"]);
    diagText.textContent = `信号质量回测：载入 ${result.diagnostics.file_count} 个文件，信号日 ${result.diagnostics.signal_days} 天，完成信号 ${result.diagnostics.completed_signal_count} 条，持仓期跳过 ${result.diagnostics.blocked_reentry_count || 0} 条重复信号；资金输入未参与计算。`;
  } else {
    renderTable(pickTable, result.pick_rows, ["signal_date", "symbol", "name", "rank", "score", "planned_entry_date", "planned_exit_date", "max_exit_date", "entry_raw_open", "exit_raw_open", "sell_condition_enabled", "execution_note"]);
    renderTable(tradeTable, result.trade_rows, ["trade_date", "signal_date", "symbol", "name", "action", "price", "shares", "gross_amount", "fees", "net_amount", "cash_after", "trade_return", "price_pnl", "exit_reason", "exit_signal_date"]);
    renderTable(contributionTable, result.contribution_rows, ["symbol", "name", "realized_pnl", "trade_count", "win_rate", "avg_trade_return"]);
    diagText.textContent = `实盘账户回测：载入 ${result.diagnostics.file_count} 个文件，信号日 ${result.diagnostics.signal_days} 天，出现候选日 ${result.diagnostics.candidate_days} 天，触发选股日 ${result.diagnostics.picked_days} 天。`;
  }
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

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = buildPayload();
  const mode = getBacktestMode();
  const isSignalQuality = mode === "signal_quality";
  const endpoint = isSignalQuality ? "/api/run-signal-quality" : "/api/run-backtest";
  const modeLabel = isSignalQuality ? "信号质量回测" : "实盘账户回测";
  runBtn.disabled = true;
  setStatus(`正在运行${modeLabel}...`);
  try {
    const response = await postJson(endpoint, payload);
    const result = await response.json();
    applyResult(result);
    setStatus(`${modeLabel}完成。`);
  } catch (error) {
    setStatus(`${modeLabel}失败: ${error.message}`, true);
  } finally {
    runBtn.disabled = false;
  }
});

exportBtn.addEventListener("click", async () => {
  if (getBacktestMode() === "signal_quality") {
    setStatus("信号质量回测暂不支持导出；请切换到实盘账户回测后导出表格压缩包。", true);
    return;
  }
  const payload = buildPayload();
  exportBtn.disabled = true;
  setStatus("正在准备导出文件...");
  try {
    const response = await postJson("/api/run-backtest-export", payload);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "组合回测结果.zip";
    a.click();
    URL.revokeObjectURL(url);
    setStatus("导出完成。");
  } catch (error) {
    setStatus(`导出失败: ${error.message}`, true);
  } finally {
    exportBtn.disabled = false;
  }
});
