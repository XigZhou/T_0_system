---
name: stock-backtest-frontend
description: Chinese A-share stock backtest and paper-trading frontend design rules for the T_0 system. Use when modifying portfolio backtests, signal-quality backtests, daily close stock selection, single-stock backtests, sector dashboards, or multi-account paper trading UI.
---

# Stock Backtest Frontend

## Purpose

Design T_0-style quant frontends as compact Chinese trading workbenches. Preserve existing APIs and trading logic unless the user explicitly asks for behavior changes.

## Visual Direction

- Prefer a restrained workbench: compact, calm, dense, readable.
- Use Chinese labels only unless the user explicitly asks for English.
- Keep the existing warm paper theme and accent color unless the task is a full redesign.
- Treat the page as an operations surface: status, parameters, summary, tables, and logs matter more than decorative layouts.

## Layout And Typography

- Related pages must keep typography consistent. When adding or splitting a page, match the existing page class font scale instead of introducing larger headings, labels, inputs, buttons, summaries, or table text.
- For multi-account paper trading pages, `/paper` and `/paper/templates` must use the same compact font sizes and control heights for brand text, labels, inputs, buttons, status text, summary metrics, and panel headings.
- Dense configuration editors should use multi-column forms on desktop. For account template editing, use three fields per row when space allows; wider path fields may span two columns, and mobile may collapse to one column.
- Keep forms compact: small labels, tight gaps, reasonable control height, and grouped related fields.
- Do not use page-level hero sizing inside compact panels, sidebars, dashboards, or tool surfaces.
- Put input parameters above results for analysis pages unless the existing page intentionally uses another pattern.
- For paper trading pages, keep action buttons close to account/template controls and make destructive/write actions visually distinguishable from read-only actions.

## Table Rules

- Every record-list module must wrap its table in `.table-wrap`.
- Table horizontal scrolling must stay inside `.table-wrap`, never on the whole page.
- Table vertical scrolling must stay inside `.table-wrap` for long rows such as logs, trades, orders, signals, holdings, and monthly/yearly stats.
- Add `min-width: 0` to grid/flex ancestors that contain wide tables.
- Use `overflow: auto` on `.table-wrap`.
- Tables must include `股票名称` whenever they include `股票代码` or stock id.

## Interaction Rules

- Make read-only actions clear: `读取账本`, `刷新模板`, `获取当前持仓最新价格`.
- Make write actions clear: `运行模拟账户`, `收盘生成待执行订单`, `开盘执行待成交订单`, `保存模板`, `删除模板`.
- After a user action, show the most relevant tab automatically only when it helps.
- Status text must explain what happened and whether data was written.
- If a value is not truly real-time, say so.

## Safe Change Workflow

1. Read the relevant HTML, JS, and CSS before editing.
2. Identify whether the task is visual-only or behavior-changing.
3. Scope CSS to the relevant page class when possible, for example `.paper-page` or `.paper-template-page`.
4. If a page was split from another page, compare typography and control density against the source page before finishing.
5. Use `apply_patch` for edits.
6. Preserve Chinese copy and existing page vocabulary.

## Validation Checklist

- Start FastAPI and check affected pages return `200`.
- Check `/paper` and `/paper/templates` together when modifying paper trading CSS.
- Confirm matching font-size/control-height rules exist for sibling paper trading pages.
- For JS changes, verify button ids, event handlers, API actions, and status text.
- On Tencent Cloud changes, restart `t0-system` and verify `/health`, affected page HTML, CSS, and key API endpoints.
