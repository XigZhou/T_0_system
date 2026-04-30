from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - zoneinfo exists in supported runtimes
    ZoneInfo = None

import httpx
import pandas as pd

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised on minimal server envs
    yaml = None

from .daily_plan import build_daily_plan
from .models import DailyHolding, DailyPlanRequest, PaperTradingRunRequest
from .utils import load_env, to_float


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "configs" / "paper_accounts"
DEFAULT_LEDGER_DIR = PROJECT_ROOT / "paper_trading" / "accounts"
DEFAULT_LOG_DIR = PROJECT_ROOT / "paper_trading" / "logs"

PENDING_COLUMNS = [
    "订单编号",
    "账户编号",
    "账户名称",
    "订单方向",
    "状态",
    "信号日期",
    "计划执行日期",
    "股票代码",
    "股票名称",
    "排名",
    "评分",
    "信号收盘价",
    "计划股数",
    "最低买入金额",
    "生成时间",
    "执行时间",
    "成交价格",
    "成交金额",
    "手续费",
    "印花税",
    "滑点bps",
    "失败原因",
]

TRADE_COLUMNS = [
    "交易编号",
    "账户编号",
    "账户名称",
    "订单编号",
    "交易日期",
    "交易方向",
    "股票代码",
    "股票名称",
    "成交价格",
    "股数",
    "成交金额",
    "手续费",
    "印花税",
    "总金额",
    "买入成本",
    "实现盈亏",
    "收益率",
    "现金余额",
    "备注",
]

HOLDING_COLUMNS = [
    "账户编号",
    "账户名称",
    "股票代码",
    "股票名称",
    "买入日期",
    "买入价格",
    "股数",
    "买入成交金额",
    "买入手续费",
    "买入总成本",
    "当前价格",
    "当前市值",
    "浮动盈亏",
    "浮动收益率",
    "持有天数",
    "最后估值日期",
    "来源订单编号",
]

ASSET_COLUMNS = [
    "账户编号",
    "账户名称",
    "日期",
    "现金",
    "持仓市值",
    "总资产",
    "初始资金",
    "累计收益",
    "持仓数量",
    "备注",
]

LOG_COLUMNS = ["时间", "账户编号", "账户名称", "动作", "级别", "信息"]
CONFIG_COLUMNS = ["字段", "值"]
SHEET_NAMES = ["配置快照", "待执行订单", "成交流水", "当前持仓", "每日资产", "运行日志"]


@dataclass
class PaperAccountConfig:
    account_id: str
    account_name: str
    initial_cash: float
    processed_dir: str
    buy_condition: str
    sell_condition: str
    score_expression: str
    top_n: int
    entry_offset: int
    min_hold_days: int
    max_hold_days: int
    buy_quantity_mode: str
    buy_shares: int
    buy_lot_size: int
    min_buy_amount: float
    buy_min_close: float
    buy_max_close: float
    price_primary: str
    price_fallback: str
    price_field: str
    skip_if_holding: bool
    skip_if_pending_order: bool
    strict_execution: bool
    buy_fee_rate: float
    sell_fee_rate: float
    stamp_tax_sell: float
    slippage_bps: float
    min_commission: float
    ledger_path: Path
    log_dir: Path
    raw_config: dict[str, Any]


@dataclass
class PriceQuote:
    symbol: str
    name: str
    trade_date: str
    price: float
    close_price: float | None
    can_buy: bool
    can_sell: bool
    source: str


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_path(path_text: str | Path, base: Path = PROJECT_ROOT) -> Path:
    path = Path(str(path_text).strip()).expanduser()
    if not path.is_absolute():
        path = base / path
    return path


def _symbol_key(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text.zfill(6) if text.isdigit() else text


def _ts_code(symbol: str) -> str:
    key = _symbol_key(symbol)
    if str(symbol).strip().upper().endswith((".SH", ".SZ")):
        return str(symbol).strip().upper()
    if key.startswith(("6", "9")):
        return f"{key}.SH"
    return f"{key}.SZ"


def _format_date(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


def _next_weekday(date_text: str) -> str:
    current = datetime.strptime(date_text, "%Y%m%d")
    while True:
        current += timedelta(days=1)
        if current.weekday() < 5:
            return _format_date(current)


def _bundle_dir_from_processed_dir(processed_dir: str) -> Path:
    path = _normalize_path(processed_dir)
    if path.name.startswith("processed_"):
        return path.parent
    return path


def _next_trade_date_from_calendar(processed_dir: str, signal_date: str) -> str:
    bundle_dir = _bundle_dir_from_processed_dir(processed_dir)
    calendar_path = bundle_dir / "trade_calendar.csv"
    if calendar_path.exists():
        try:
            calendar = pd.read_csv(calendar_path, dtype=str, encoding="utf-8-sig")
            date_col = "trade_date" if "trade_date" in calendar.columns else "cal_date"
            open_dates = sorted(
                str(item)
                for item in calendar.loc[calendar.get("is_open", "1").astype(str) == "1", date_col].dropna().tolist()
                if str(item) > signal_date
            )
            if open_dates:
                return open_dates[0]
        except Exception:
            pass

    try:
        import tushare as ts

        token = load_env(PROJECT_ROOT / ".env").get("TUSHARE_TOKEN", "").strip()
        if token:
            start_dt = datetime.strptime(signal_date, "%Y%m%d") + timedelta(days=1)
            end_dt = start_dt + timedelta(days=45)
            pro = ts.pro_api(token)
            cal = pro.trade_cal(
                exchange="",
                start_date=_format_date(start_dt),
                end_date=_format_date(end_dt),
                is_open="1",
                fields="cal_date",
            )
            if cal is not None and not cal.empty:
                return str(cal["cal_date"].astype(str).sort_values().iloc[0])
    except Exception:
        pass

    return _next_weekday(signal_date)


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"是", "true", "1", "yes", "y", "启用"}:
        return True
    if text in {"否", "false", "0", "no", "n", "停用"}:
        return False
    return default


def _as_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _sheet(df_map: dict[str, pd.DataFrame], name: str, columns: list[str]) -> pd.DataFrame:
    frame = df_map.get(name)
    if frame is None:
        return pd.DataFrame(columns=columns)
    frame = frame.copy()
    for col in columns:
        if col not in frame.columns:
            frame[col] = pd.NA
    return frame[columns]


def _parse_scalar(value: str) -> Any:
    text = value.strip()
    if not text:
        return ""
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    if text in {"是", "否"}:
        return text
    try:
        if any(ch in text for ch in [".", "e", "E"]):
            return float(text)
        return int(text)
    except ValueError:
        return text


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Fallback parser for the project's simple Chinese YAML templates."""
    root: dict[str, Any] = {}
    current_key = ""
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if indent == 0:
            if value:
                root[key] = _parse_scalar(value)
                current_key = ""
            else:
                root[key] = {}
                current_key = key
        elif current_key:
            nested = root.setdefault(current_key, {})
            if isinstance(nested, dict):
                nested[key] = _parse_scalar(value)
    return root


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"模拟账户模板不存在: {path}")
    text = ""
    last_error: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    if not text and last_error is not None:
        raise last_error
    data = yaml.safe_load(text) if yaml is not None else _parse_simple_yaml(text)
    data = data or {}
    if not isinstance(data, dict):
        raise ValueError(f"模拟账户模板格式不正确，根节点必须是对象: {path}")
    return data


def load_paper_account_config(config_path: str | Path) -> PaperAccountConfig:
    path = _normalize_path(config_path)
    data = _read_yaml(path)
    quantity = data.get("买入数量") or {}
    price_filter = data.get("买入价格筛选") or {}
    source = data.get("行情源") or {}
    rules = data.get("交易规则") or {}
    fees = data.get("费用") or {}
    output = data.get("输出") or {}
    account_id = str(data.get("账户编号") or path.stem).strip()
    account_name = str(data.get("账户名称") or account_id).strip()
    buy_fee_rate = _as_float(fees.get("买入费率", fees.get("买卖费率")), 0.00003)
    sell_fee_rate = _as_float(fees.get("卖出费率", fees.get("买卖费率")), 0.00003)
    ledger_path = output.get("账本路径") or DEFAULT_LEDGER_DIR / f"{account_id}.xlsx"
    log_dir = output.get("日志目录") or DEFAULT_LOG_DIR
    return PaperAccountConfig(
        account_id=account_id,
        account_name=account_name,
        initial_cash=_as_float(data.get("初始资金"), 100_000.0),
        processed_dir=str(data.get("处理后数据目录") or "data_bundle/processed_qfq_theme_focus_top100"),
        buy_condition=str(data.get("买入条件") or "").strip(),
        sell_condition=str(data.get("卖出条件") or "").strip(),
        score_expression=str(data.get("评分表达式") or "m20").strip(),
        top_n=max(1, _as_int(data.get("买入排名数量"), 5)),
        entry_offset=max(1, _as_int(data.get("买入偏移"), 1)),
        min_hold_days=max(0, _as_int(data.get("最短持有天数"), 0)),
        max_hold_days=max(0, _as_int(data.get("最大持有天数"), 15)),
        buy_quantity_mode=str(quantity.get("方式") or "固定股数").strip(),
        buy_shares=max(1, _as_int(quantity.get("股数"), 200)),
        buy_lot_size=max(1, _as_int(quantity.get("每手股数"), 100)),
        min_buy_amount=max(0.0, _as_float(quantity.get("最低买入金额"), 0.0)),
        buy_min_close=max(0.0, _as_float(price_filter.get("最低收盘价"), 0.0)),
        buy_max_close=max(0.0, _as_float(price_filter.get("最高收盘价"), 0.0)),
        price_primary=str(source.get("首选") or "本地日线").strip(),
        price_fallback=str(source.get("备用") or "").strip(),
        price_field=str(source.get("价格字段") or "开盘价").strip(),
        skip_if_holding=_truthy(rules.get("持仓时不重复买入"), True),
        skip_if_pending_order=_truthy(rules.get("有待成交订单时不重复买入"), True),
        strict_execution=_truthy(rules.get("严格成交"), True),
        buy_fee_rate=buy_fee_rate,
        sell_fee_rate=sell_fee_rate,
        stamp_tax_sell=_as_float(fees.get("印花税"), 0.0),
        slippage_bps=_as_float(fees.get("滑点bps"), 0.0),
        min_commission=_as_float(fees.get("最低佣金"), 0.0),
        ledger_path=_normalize_path(ledger_path),
        log_dir=_normalize_path(log_dir),
        raw_config=data,
    )


def list_paper_account_templates(config_dir: str | Path = DEFAULT_CONFIG_DIR) -> list[dict[str, Any]]:
    folder = _normalize_path(config_dir)
    if not folder.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.yaml")):
        try:
            cfg = load_paper_account_config(path)
            rows.append(
                {
                    "account_id": cfg.account_id,
                    "account_name": cfg.account_name,
                    "config_path": str(path),
                    "ledger_path": str(cfg.ledger_path),
                    "processed_dir": cfg.processed_dir,
                    "top_n": cfg.top_n,
                    "buy_shares": cfg.buy_shares,
                    "buy_lot_size": cfg.buy_lot_size,
                    "min_buy_amount": cfg.min_buy_amount,
                    "buy_min_close": cfg.buy_min_close,
                    "buy_max_close": cfg.buy_max_close,
                    "price_primary": cfg.price_primary,
                }
            )
        except Exception as exc:  # noqa: BLE001
            rows.append({"account_id": path.stem, "account_name": "模板读取失败", "config_path": str(path), "error": str(exc)})
    return rows


def _empty_ledger() -> dict[str, pd.DataFrame]:
    return {
        "配置快照": pd.DataFrame(columns=CONFIG_COLUMNS),
        "待执行订单": pd.DataFrame(columns=PENDING_COLUMNS),
        "成交流水": pd.DataFrame(columns=TRADE_COLUMNS),
        "当前持仓": pd.DataFrame(columns=HOLDING_COLUMNS),
        "每日资产": pd.DataFrame(columns=ASSET_COLUMNS),
        "运行日志": pd.DataFrame(columns=LOG_COLUMNS),
    }


def _read_ledger(path: Path) -> dict[str, pd.DataFrame]:
    if not path.exists():
        return _empty_ledger()
    loaded = pd.read_excel(path, sheet_name=None, dtype=object)
    return {
        "配置快照": _sheet(loaded, "配置快照", CONFIG_COLUMNS),
        "待执行订单": _sheet(loaded, "待执行订单", PENDING_COLUMNS),
        "成交流水": _sheet(loaded, "成交流水", TRADE_COLUMNS),
        "当前持仓": _sheet(loaded, "当前持仓", HOLDING_COLUMNS),
        "每日资产": _sheet(loaded, "每日资产", ASSET_COLUMNS),
        "运行日志": _sheet(loaded, "运行日志", LOG_COLUMNS),
    }


def _write_ledger(path: Path, ledger: dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name in SHEET_NAMES:
            ledger[sheet_name].to_excel(writer, sheet_name=sheet_name, index=False)


def _config_snapshot(cfg: PaperAccountConfig) -> pd.DataFrame:
    rows = [
        ("账户编号", cfg.account_id),
        ("账户名称", cfg.account_name),
        ("初始资金", cfg.initial_cash),
        ("处理后数据目录", cfg.processed_dir),
        ("买入条件", cfg.buy_condition),
        ("卖出条件", cfg.sell_condition),
        ("评分表达式", cfg.score_expression),
        ("买入排名数量", cfg.top_n),
        ("买入偏移", cfg.entry_offset),
        ("最短持有天数", cfg.min_hold_days),
        ("最大持有天数", cfg.max_hold_days),
        ("买入数量方式", cfg.buy_quantity_mode),
        ("买入股数", cfg.buy_shares),
        ("每手股数", cfg.buy_lot_size),
        ("最低买入金额", cfg.min_buy_amount),
        ("买入最低收盘价", cfg.buy_min_close),
        ("买入最高收盘价", cfg.buy_max_close),
        ("行情源首选", cfg.price_primary),
        ("行情源备用", cfg.price_fallback),
        ("价格字段", cfg.price_field),
        ("持仓时不重复买入", "是" if cfg.skip_if_holding else "否"),
        ("有待成交订单时不重复买入", "是" if cfg.skip_if_pending_order else "否"),
        ("严格成交", "是" if cfg.strict_execution else "否"),
        ("买入费率", cfg.buy_fee_rate),
        ("卖出费率", cfg.sell_fee_rate),
        ("印花税", cfg.stamp_tax_sell),
        ("滑点bps", cfg.slippage_bps),
        ("最低佣金", cfg.min_commission),
        ("账本路径", str(cfg.ledger_path)),
        ("日志目录", str(cfg.log_dir)),
        ("最后更新时间", _now_text()),
    ]
    return pd.DataFrame(rows, columns=CONFIG_COLUMNS)


def _append_log(ledger: dict[str, pd.DataFrame], cfg: PaperAccountConfig, action: str, level: str, message: str) -> None:
    row = {
        "时间": _now_text(),
        "账户编号": cfg.account_id,
        "账户名称": cfg.account_name,
        "动作": action,
        "级别": level,
        "信息": message,
    }
    ledger["运行日志"] = pd.concat([ledger["运行日志"], pd.DataFrame([row])], ignore_index=True)


def _write_text_log(cfg: PaperAccountConfig, message: str) -> None:
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = cfg.log_dir / f"{datetime.now():%Y%m%d}.log"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"{_now_text()} [{cfg.account_id}] {message}\n")


def _cash_balance(cfg: PaperAccountConfig, trades: pd.DataFrame) -> float:
    if trades.empty:
        return round(float(cfg.initial_cash), 2)
    cash = float(cfg.initial_cash)
    for _, row in trades.iterrows():
        direction = str(row.get("交易方向") or "")
        total = _as_float(row.get("总金额"), 0.0)
        if direction == "买入":
            cash -= total
        elif direction == "卖出":
            cash += total
    return round(cash, 2)


def _open_holding_symbols(holdings: pd.DataFrame) -> set[str]:
    if holdings.empty:
        return set()
    return {_symbol_key(value) for value in holdings["股票代码"].dropna().astype(str).tolist()}


def _pending_buy_symbols(pending: pd.DataFrame) -> set[str]:
    if pending.empty:
        return set()
    frame = pending[(pending["状态"].astype(str) == "待执行") & (pending["订单方向"].astype(str) == "买入")]
    return {_symbol_key(value) for value in frame["股票代码"].dropna().astype(str).tolist()}


def _daily_holdings_from_ledger(holdings: pd.DataFrame) -> list[DailyHolding]:
    out: list[DailyHolding] = []
    for _, row in holdings.iterrows():
        symbol = str(row.get("股票代码") or "").strip()
        buy_date = str(row.get("买入日期") or "").strip()
        buy_price = _as_float(row.get("买入价格"), 0.0)
        shares = _as_int(row.get("股数"), 0)
        if not symbol or not buy_date or buy_price <= 0 or shares <= 0:
            continue
        out.append(
            DailyHolding(
                symbol=symbol,
                buy_date=buy_date,
                buy_price=buy_price,
                shares=shares,
                name=str(row.get("股票名称") or ""),
            )
        )
    return out


def _order_id(cfg: PaperAccountConfig, direction: str, signal_date: str, execute_date: str, symbol: str) -> str:
    return f"{cfg.account_id}-{signal_date}-{execute_date}-{direction}-{_symbol_key(symbol)}"


def _trade_id(cfg: PaperAccountConfig, trade_date: str, symbol: str, direction: str, index: int) -> str:
    return f"{cfg.account_id}-{trade_date}-{direction}-{_symbol_key(symbol)}-{index:04d}"


def _dedupe_append(base: pd.DataFrame, rows: list[dict[str, Any]], key: str, columns: list[str]) -> tuple[pd.DataFrame, int]:
    if not rows:
        return base, 0
    existing = set(base[key].dropna().astype(str).tolist()) if key in base.columns else set()
    filtered = [row for row in rows if str(row.get(key) or "") not in existing]
    if not filtered:
        return base, 0
    return pd.concat([base, pd.DataFrame(filtered)], ignore_index=True)[columns], len(filtered)


def _resolve_signal_date(cfg: PaperAccountConfig, signal_date: str) -> str:
    if signal_date:
        return signal_date
    result = build_daily_plan(
        DailyPlanRequest(
            processed_dir=cfg.processed_dir,
            signal_date="",
            buy_condition=cfg.buy_condition,
            sell_condition=cfg.sell_condition,
            score_expression=cfg.score_expression,
            top_n=1,
            entry_offset=cfg.entry_offset,
            min_hold_days=cfg.min_hold_days,
            max_hold_days=cfg.max_hold_days,
            holdings=[],
        )
    )
    return str(result["summary"]["signal_date"])


def _planned_trade_date(cfg: PaperAccountConfig, planned_date: Any, signal_date: str) -> str:
    text = str(planned_date or "").strip()
    if text and text != "下一交易日":
        return text
    return _next_trade_date_from_calendar(cfg.processed_dir, signal_date)


def _round_up_to_lot(shares: int, lot_size: int) -> int:
    lot = max(1, int(lot_size))
    return int(math.ceil(max(0, int(shares)) / lot) * lot)


def _planned_buy_shares(cfg: PaperAccountConfig, signal_close: float | None) -> int:
    fixed_shares = _round_up_to_lot(cfg.buy_shares, cfg.buy_lot_size)
    if cfg.min_buy_amount <= 0 or signal_close is None or signal_close <= 0:
        return fixed_shares
    min_shares = _round_up_to_lot(math.ceil(cfg.min_buy_amount / signal_close), cfg.buy_lot_size)
    return max(fixed_shares, min_shares)


def _buy_price_filter_reason(cfg: PaperAccountConfig, signal_close: float | None) -> str:
    if cfg.buy_min_close <= 0 and cfg.buy_max_close <= 0 and cfg.min_buy_amount <= 0:
        return ""
    if signal_close is None or signal_close <= 0:
        return "缺少有效 T 日收盘价，无法做买入价格筛选或最低买入金额计算"
    if cfg.buy_min_close > 0 and signal_close < cfg.buy_min_close:
        return f"T日收盘价 {signal_close:.2f} 低于最低收盘价 {cfg.buy_min_close:.2f}"
    if cfg.buy_max_close > 0 and signal_close > cfg.buy_max_close:
        return f"T日收盘价 {signal_close:.2f} 高于最高收盘价 {cfg.buy_max_close:.2f}"
    return ""


def _generate_orders(cfg: PaperAccountConfig, ledger: dict[str, pd.DataFrame], signal_date: str) -> dict[str, Any]:
    holdings = ledger["当前持仓"]
    pending = ledger["待执行订单"]
    holding_symbols = _open_holding_symbols(holdings)
    pending_buy_symbols = _pending_buy_symbols(pending)
    request_top_n = min(
        500,
        max(cfg.top_n, cfg.top_n * 10, 100) + (len(pending_buy_symbols) if cfg.skip_if_pending_order else 0),
    )
    plan = build_daily_plan(
        DailyPlanRequest(
            processed_dir=cfg.processed_dir,
            signal_date=signal_date,
            buy_condition=cfg.buy_condition,
            sell_condition=cfg.sell_condition,
            score_expression=cfg.score_expression,
            top_n=max(cfg.top_n, request_top_n),
            entry_offset=cfg.entry_offset,
            min_hold_days=cfg.min_hold_days,
            max_hold_days=cfg.max_hold_days,
            per_trade_budget=max(cfg.buy_shares, 1),
            lot_size=1,
            holdings=_daily_holdings_from_ledger(holdings),
        )
    )
    actual_signal_date = str(plan["summary"]["signal_date"])
    created_at = _now_text()
    new_rows: list[dict[str, Any]] = []
    buy_count = 0
    price_filtered_count = 0
    for row in plan["buy_rows"]:
        symbol_key = _symbol_key(row["symbol"])
        if cfg.skip_if_holding and symbol_key in holding_symbols:
            continue
        if cfg.skip_if_pending_order and symbol_key in pending_buy_symbols:
            continue
        signal_close = to_float(row.get("signal_raw_close"))
        price_filter_reason = _buy_price_filter_reason(cfg, signal_close)
        if price_filter_reason:
            price_filtered_count += 1
            continue
        execute_date = _planned_trade_date(cfg, row.get("planned_buy_date"), actual_signal_date)
        planned_shares = _planned_buy_shares(cfg, signal_close)
        new_rows.append(
            {
                "订单编号": _order_id(cfg, "买入", actual_signal_date, execute_date, row["symbol"]),
                "账户编号": cfg.account_id,
                "账户名称": cfg.account_name,
                "订单方向": "买入",
                "状态": "待执行",
                "信号日期": actual_signal_date,
                "计划执行日期": execute_date,
                "股票代码": _ts_code(str(row["symbol"])),
                "股票名称": row.get("name", ""),
                "排名": row.get("rank"),
                "评分": row.get("score"),
                "信号收盘价": round(float(signal_close), 4) if signal_close is not None else math.nan,
                "计划股数": planned_shares,
                "最低买入金额": cfg.min_buy_amount,
                "生成时间": created_at,
                "执行时间": "",
                "成交价格": math.nan,
                "成交金额": math.nan,
                "手续费": math.nan,
                "印花税": math.nan,
                "滑点bps": cfg.slippage_bps,
                "失败原因": "",
            }
        )
        buy_count += 1
        if buy_count >= cfg.top_n:
            break

    for row in plan["sell_rows"]:
        execute_date = _planned_trade_date(cfg, row.get("planned_sell_date"), actual_signal_date)
        new_rows.append(
            {
                "订单编号": _order_id(cfg, "卖出", actual_signal_date, execute_date, row["symbol"]),
                "账户编号": cfg.account_id,
                "账户名称": cfg.account_name,
                "订单方向": "卖出",
                "状态": "待执行",
                "信号日期": actual_signal_date,
                "计划执行日期": execute_date,
                "股票代码": _ts_code(str(row["symbol"])),
                "股票名称": row.get("name", ""),
                "排名": "",
                "评分": "",
                "信号收盘价": row.get("current_raw_close", math.nan),
                "计划股数": row.get("shares", 0),
                "最低买入金额": "",
                "生成时间": created_at,
                "执行时间": "",
                "成交价格": math.nan,
                "成交金额": math.nan,
                "手续费": math.nan,
                "印花税": math.nan,
                "滑点bps": cfg.slippage_bps,
                "失败原因": row.get("sell_reason", ""),
            }
        )

    ledger["待执行订单"], added_count = _dedupe_append(ledger["待执行订单"], new_rows, "订单编号", PENDING_COLUMNS)
    _append_log(ledger, cfg, "生成订单", "信息", f"信号日 {actual_signal_date} 生成 {added_count} 条新订单")
    _write_text_log(cfg, f"生成订单: 信号日 {actual_signal_date}, 新订单 {added_count}")
    return {
        "signal_date": actual_signal_date,
        "planned_buy_count": sum(1 for row in new_rows if row["订单方向"] == "买入"),
        "planned_sell_count": sum(1 for row in new_rows if row["订单方向"] == "卖出"),
        "price_filtered_count": price_filtered_count,
        "added_order_count": added_count,
        "plan_summary": plan["summary"],
    }


class LocalDailyPriceProvider:
    def __init__(self, processed_dir: str, price_field: str) -> None:
        self.processed_dir = _normalize_path(processed_dir)
        self.price_field = price_field

    def _file_for_symbol(self, symbol: str) -> Path:
        key = _symbol_key(symbol)
        candidates = [
            self.processed_dir / f"{key}.csv",
            self.processed_dir / f"{key}.SZ.csv",
            self.processed_dir / f"{key}.SH.csv",
        ]
        for item in candidates:
            if item.exists():
                return item
        raise FileNotFoundError(f"找不到股票处理后数据: {symbol}")

    def quote(self, symbol: str, trade_date: str) -> PriceQuote:
        file_path = self._file_for_symbol(symbol)
        frame = pd.read_csv(file_path, dtype=str, encoding="utf-8-sig")
        rows = frame[frame["trade_date"].astype(str) == str(trade_date)]
        if rows.empty:
            raise ValueError(f"{symbol} 没有 {trade_date} 的本地日线数据")
        row = rows.iloc[0]
        price_col = "raw_open" if "开盘" in self.price_field else "raw_close"
        price = to_float(row.get(price_col))
        if price is None or price <= 0:
            raise ValueError(f"{symbol} {trade_date} 缺少有效 {price_col}")
        close_price = to_float(row.get("raw_close"))
        return PriceQuote(
            symbol=_ts_code(symbol),
            name=str(row.get("name") or ""),
            trade_date=str(row.get("trade_date") or trade_date),
            price=float(price),
            close_price=close_price,
            can_buy=_truthy(row.get("can_buy_open_t"), True),
            can_sell=_truthy(row.get("can_sell_t"), True),
            source="本地日线",
        )


class RealtimeQuoteProvider:
    def __init__(self, primary: str, fallback: str, price_field: str) -> None:
        self.primary = primary
        self.fallback = fallback
        self.price_field = price_field

    def quote(self, symbol: str, trade_date: str) -> PriceQuote:
        errors: list[str] = []
        for source in [self.primary, self.fallback]:
            source = str(source or "").strip()
            if not source:
                continue
            try:
                if "腾讯" in source:
                    return self._quote_tencent(symbol, trade_date)
                if "东方" in source or "东财" in source:
                    return self._quote_eastmoney(symbol, trade_date)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{source}: {exc}")
        raise ValueError("实时行情获取失败：" + "；".join(errors))

    def _quote_tencent(self, symbol: str, trade_date: str) -> PriceQuote:
        key = _symbol_key(symbol)
        market = "sh" if key.startswith(("6", "9")) else "sz"
        url = f"https://qt.gtimg.cn/q={market}{key}"
        text = httpx.get(url, timeout=5.0).text
        if "~" not in text:
            raise ValueError("腾讯行情返回格式异常")
        parts = text.split('"')[1].split("~")
        name = parts[1]
        current = _as_float(parts[3], 0.0)
        open_price = _as_float(parts[5], 0.0)
        price = open_price if "开盘" in self.price_field and open_price > 0 else current
        if price <= 0:
            raise ValueError("腾讯行情缺少有效价格")
        return PriceQuote(_ts_code(symbol), name, trade_date, price, current, True, True, "腾讯股票")

    def _quote_eastmoney(self, symbol: str, trade_date: str) -> PriceQuote:
        key = _symbol_key(symbol)
        market = "1" if key.startswith(("6", "9")) else "0"
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        params = {"secid": f"{market}.{key}", "fields": "f43,f46,f57,f58"}
        payload = httpx.get(url, params=params, timeout=5.0).json()
        data = payload.get("data") or {}
        name = str(data.get("f58") or "")
        current = _as_float(data.get("f43"), 0.0) / 100.0
        open_price = _as_float(data.get("f46"), 0.0) / 100.0
        price = open_price if "开盘" in self.price_field and open_price > 0 else current
        if price <= 0:
            raise ValueError("东方财富行情缺少有效价格")
        return PriceQuote(_ts_code(symbol), name, trade_date, price, current, True, True, "东方财富")


def _price_provider(cfg: PaperAccountConfig) -> LocalDailyPriceProvider | RealtimeQuoteProvider:
    if "本地" in cfg.price_primary or "日线" in cfg.price_primary:
        return LocalDailyPriceProvider(cfg.processed_dir, cfg.price_field)
    return RealtimeQuoteProvider(cfg.price_primary, cfg.price_fallback, cfg.price_field)


def _fee(amount: float, rate: float, min_commission: float) -> float:
    if amount <= 0:
        return 0.0
    return round(max(float(amount) * float(rate), float(min_commission)), 2)


def _execute_orders(cfg: PaperAccountConfig, ledger: dict[str, pd.DataFrame], trade_date: str) -> dict[str, Any]:
    provider = _price_provider(cfg)
    pending = ledger["待执行订单"].copy()
    trades = ledger["成交流水"].copy()
    holdings = ledger["当前持仓"].copy()
    cash = _cash_balance(cfg, trades)
    executed_count = 0
    failed_count = 0
    trade_rows: list[dict[str, Any]] = []

    due_orders: list[tuple[int, Any]] = []
    for position, (idx, order) in enumerate(pending.iterrows()):
        if str(order.get("状态") or "") != "待执行":
            continue
        planned_date = str(order.get("计划执行日期") or "")
        if planned_date > trade_date:
            continue
        due_orders.append((position, idx))

    def _execution_order_key(item: tuple[int, Any]) -> tuple[int, str, int]:
        position, idx = item
        order = pending.loc[idx]
        direction = str(order.get("订单方向") or "")
        direction_rank = 0 if direction == "卖出" else 1 if direction == "买入" else 2
        planned_date = str(order.get("计划执行日期") or "")
        return direction_rank, planned_date, position

    # 同一天既有卖出又有买入时，先卖出释放现金，再执行新买入。
    for _, idx in sorted(due_orders, key=_execution_order_key):
        order = pending.loc[idx]
        direction = str(order.get("订单方向") or "")
        symbol = str(order.get("股票代码") or "")
        shares = _as_int(order.get("计划股数"), 0)
        try:
            quote = provider.quote(symbol, trade_date)
            if direction == "买入":
                if cfg.strict_execution and not quote.can_buy:
                    raise ValueError("开盘不可买入")
                if cfg.skip_if_holding and _symbol_key(symbol) in _open_holding_symbols(holdings):
                    raise ValueError("当前已持仓，跳过重复买入")
                price = round(float(quote.price) * (1.0 + cfg.slippage_bps / 10000.0), 4)
                gross = round(price * shares, 2)
                commission = _fee(gross, cfg.buy_fee_rate, cfg.min_commission)
                total = round(gross + commission, 2)
                if total > cash:
                    raise ValueError(f"现金不足：需要 {total:.2f}，当前 {cash:.2f}")
                cash = round(cash - total, 2)
                holding = {
                    "账户编号": cfg.account_id,
                    "账户名称": cfg.account_name,
                    "股票代码": quote.symbol,
                    "股票名称": quote.name or order.get("股票名称", ""),
                    "买入日期": trade_date,
                    "买入价格": price,
                    "股数": shares,
                    "买入成交金额": gross,
                    "买入手续费": commission,
                    "买入总成本": total,
                    "当前价格": quote.close_price or price,
                    "当前市值": round((quote.close_price or price) * shares, 2),
                    "浮动盈亏": round((quote.close_price or price) * shares - total, 2),
                    "浮动收益率": round(((quote.close_price or price) * shares - total) / total, 6) if total else 0.0,
                    "持有天数": 0,
                    "最后估值日期": trade_date,
                    "来源订单编号": order.get("订单编号", ""),
                }
                holdings = pd.concat([holdings, pd.DataFrame([holding])], ignore_index=True)[HOLDING_COLUMNS]
                trade_total = total
                realized_pnl = math.nan
                return_rate = math.nan
                remark = f"{quote.source}成交"
            elif direction == "卖出":
                if cfg.strict_execution and not quote.can_sell:
                    raise ValueError("开盘不可卖出")
                matched = holdings[holdings["股票代码"].astype(str).map(_symbol_key) == _symbol_key(symbol)]
                if matched.empty:
                    raise ValueError("没有对应持仓")
                hold_idx = matched.index[0]
                hold = holdings.loc[hold_idx]
                shares = min(shares, _as_int(hold.get("股数"), 0))
                price = round(float(quote.price) * (1.0 - cfg.slippage_bps / 10000.0), 4)
                gross = round(price * shares, 2)
                commission = _fee(gross, cfg.sell_fee_rate, cfg.min_commission)
                stamp_tax = round(gross * cfg.stamp_tax_sell, 2)
                trade_total = round(gross - commission - stamp_tax, 2)
                buy_cost = _as_float(hold.get("买入总成本"), 0.0)
                realized_pnl = round(trade_total - buy_cost, 2)
                return_rate = round(realized_pnl / buy_cost, 6) if buy_cost > 0 else 0.0
                cash = round(cash + trade_total, 2)
                holdings = holdings.drop(index=hold_idx).reset_index(drop=True)[HOLDING_COLUMNS]
                remark = f"{quote.source}成交"
            else:
                raise ValueError(f"未知订单方向: {direction}")

            pending.loc[idx, "状态"] = "已成交"
            pending.loc[idx, "执行时间"] = _now_text()
            pending.loc[idx, "成交价格"] = price
            pending.loc[idx, "成交金额"] = gross
            pending.loc[idx, "手续费"] = commission
            pending.loc[idx, "印花税"] = stamp_tax if direction == "卖出" else 0.0
            pending.loc[idx, "失败原因"] = ""
            trade_row = {
                "交易编号": _trade_id(cfg, trade_date, symbol, direction, len(trades) + len(trade_rows) + 1),
                "账户编号": cfg.account_id,
                "账户名称": cfg.account_name,
                "订单编号": order.get("订单编号", ""),
                "交易日期": trade_date,
                "交易方向": direction,
                "股票代码": _ts_code(symbol),
                "股票名称": quote.name or order.get("股票名称", ""),
                "成交价格": price,
                "股数": shares,
                "成交金额": gross,
                "手续费": commission,
                "印花税": stamp_tax if direction == "卖出" else 0.0,
                "总金额": trade_total,
                "买入成本": buy_cost if direction == "卖出" else trade_total,
                "实现盈亏": realized_pnl,
                "收益率": return_rate,
                "现金余额": cash,
                "备注": remark,
            }
            trade_rows.append(trade_row)
            executed_count += 1
        except Exception as exc:  # noqa: BLE001
            pending.loc[idx, "状态"] = "执行失败"
            pending.loc[idx, "执行时间"] = _now_text()
            pending.loc[idx, "失败原因"] = str(exc)
            failed_count += 1

    if trade_rows:
        trades = pd.concat([trades, pd.DataFrame(trade_rows)], ignore_index=True)[TRADE_COLUMNS]
    ledger["待执行订单"] = pending[PENDING_COLUMNS]
    ledger["成交流水"] = trades
    ledger["当前持仓"] = holdings[HOLDING_COLUMNS]
    _append_log(ledger, cfg, "执行订单", "信息", f"交易日 {trade_date} 成交 {executed_count} 条，失败 {failed_count} 条")
    _write_text_log(cfg, f"执行订单: 交易日 {trade_date}, 成交 {executed_count}, 失败 {failed_count}")
    return {"trade_date": trade_date, "executed_count": executed_count, "failed_count": failed_count, "cash": cash}


def _mark_to_market(cfg: PaperAccountConfig, ledger: dict[str, pd.DataFrame], trade_date: str, note: str = "收盘估值") -> dict[str, Any]:
    provider = LocalDailyPriceProvider(cfg.processed_dir, "收盘价")
    holdings = ledger["当前持仓"].copy()
    market_value = 0.0
    updated = 0
    for idx, row in holdings.iterrows():
        symbol = str(row.get("股票代码") or "")
        try:
            quote = provider.quote(symbol, trade_date)
            price = float(quote.close_price or quote.price)
            shares = _as_int(row.get("股数"), 0)
            cost = _as_float(row.get("买入总成本"), 0.0)
            value = round(price * shares, 2)
            buy_date = str(row.get("买入日期") or "")
            holding_days = _count_trade_days(cfg.processed_dir, symbol, buy_date, trade_date)
            holdings.loc[idx, "当前价格"] = round(price, 4)
            holdings.loc[idx, "当前市值"] = value
            holdings.loc[idx, "浮动盈亏"] = round(value - cost, 2)
            holdings.loc[idx, "浮动收益率"] = round((value - cost) / cost, 6) if cost > 0 else 0.0
            holdings.loc[idx, "持有天数"] = holding_days
            holdings.loc[idx, "最后估值日期"] = trade_date
            market_value += value
            updated += 1
        except Exception as exc:  # noqa: BLE001
            fallback_value = _as_float(row.get("当前市值"), 0.0)
            market_value += fallback_value
            _append_log(ledger, cfg, "收盘估值", "警告", f"{symbol} 估值失败: {exc}")
    trades = ledger["成交流水"]
    cash = _cash_balance(cfg, trades)
    total = round(cash + market_value, 2)
    asset_row = {
        "账户编号": cfg.account_id,
        "账户名称": cfg.account_name,
        "日期": trade_date,
        "现金": cash,
        "持仓市值": round(market_value, 2),
        "总资产": total,
        "初始资金": cfg.initial_cash,
        "累计收益": round(total / cfg.initial_cash - 1.0, 6) if cfg.initial_cash > 0 else 0.0,
        "持仓数量": len(holdings),
        "备注": note,
    }
    assets = ledger["每日资产"]
    if not assets.empty:
        assets = assets[~((assets["账户编号"].astype(str) == cfg.account_id) & (assets["日期"].astype(str) == trade_date))]
    ledger["每日资产"] = pd.concat([assets, pd.DataFrame([asset_row])], ignore_index=True)[ASSET_COLUMNS]
    ledger["当前持仓"] = holdings[HOLDING_COLUMNS]
    _append_log(ledger, cfg, "收盘估值", "信息", f"{trade_date} 更新 {updated} 个持仓，总资产 {total:.2f}")
    _write_text_log(cfg, f"收盘估值: {trade_date}, 总资产 {total:.2f}")
    return {"trade_date": trade_date, "cash": cash, "market_value": round(market_value, 2), "total_equity": total, "updated_holding_count": updated}


def _china_now() -> datetime:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    return datetime.now()


def _today_china_text() -> str:
    return _china_now().strftime("%Y%m%d")


def _is_trade_day_from_calendar(processed_dir: str, trade_date: str) -> bool | None:
    calendar_path = _bundle_dir_from_processed_dir(processed_dir) / "trade_calendar.csv"
    if not calendar_path.exists():
        return None
    try:
        calendar = pd.read_csv(calendar_path, dtype=str, encoding="utf-8-sig")
        date_col = "trade_date" if "trade_date" in calendar.columns else "cal_date"
        rows = calendar[calendar[date_col].astype(str) == str(trade_date)]
        if rows.empty:
            return None
        return str(rows.iloc[-1].get("is_open", "1")).strip() == "1"
    except Exception:
        return None


def _realtime_market_note(processed_dir: str, trade_date: str) -> str:
    now = _china_now()
    today = now.strftime("%Y%m%d")
    if trade_date != today:
        return "动作日期不是今天，实时行情源仍返回当前最新价，不是历史日期价格"

    is_trade_day = _is_trade_day_from_calendar(processed_dir, trade_date)
    if is_trade_day is False:
        return "非交易日或节假日，行情源通常返回最近交易日收盘价或最后可用价格"
    if is_trade_day is None and now.weekday() >= 5:
        return "周末或本地交易日历缺失，行情源通常返回最近交易日收盘价或最后可用价格"

    current_minutes = now.hour * 60 + now.minute
    if current_minutes < 9 * 60 + 30:
        return "交易日未开盘，行情源通常返回昨收或集合竞价前后的最新可用价格"
    if 9 * 60 + 30 <= current_minutes <= 11 * 60 + 30:
        return "交易时段，按行情源盘中最新价估值"
    if 11 * 60 + 30 < current_minutes < 13 * 60:
        return "午间休市，按上午收盘前后的最新可用价格估值"
    if 13 * 60 <= current_minutes <= 15 * 60:
        return "交易时段，按行情源盘中最新价估值"
    return "交易日已收盘，行情源通常返回当日收盘价或收盘后的最新可用价格"


def _realtime_price_provider(cfg: PaperAccountConfig) -> RealtimeQuoteProvider:
    primary = cfg.price_primary
    fallback = cfg.price_fallback
    if "本地" in primary or "日线" in primary:
        primary = "东方财富"
        fallback = fallback or "腾讯股票"
    if not fallback or "本地" in fallback or "日线" in fallback:
        fallback = "腾讯股票"
    return RealtimeQuoteProvider(primary, fallback, "最新价")


def _refresh_realtime_positions(cfg: PaperAccountConfig, ledger: dict[str, pd.DataFrame], trade_date: str) -> dict[str, Any]:
    trade_date = trade_date or _today_china_text()
    provider = _realtime_price_provider(cfg)
    holdings = ledger["当前持仓"].copy()
    market_value = 0.0
    updated = 0
    failed = 0
    sources: set[str] = set()
    market_note = _realtime_market_note(cfg.processed_dir, trade_date)

    for idx, row in holdings.iterrows():
        symbol = str(row.get("股票代码") or "")
        try:
            quote = provider.quote(symbol, trade_date)
            price = float(quote.close_price or quote.price)
            shares = _as_int(row.get("股数"), 0)
            cost = _as_float(row.get("买入总成本"), 0.0)
            value = round(price * shares, 2)
            buy_date = str(row.get("买入日期") or "")
            holding_days = _count_trade_days(cfg.processed_dir, symbol, buy_date, trade_date)
            if holding_days <= 0 and buy_date != trade_date:
                holding_days = _as_int(row.get("持有天数"), 0)
            holdings.loc[idx, "当前价格"] = round(price, 4)
            holdings.loc[idx, "当前市值"] = value
            holdings.loc[idx, "浮动盈亏"] = round(value - cost, 2)
            holdings.loc[idx, "浮动收益率"] = round((value - cost) / cost, 6) if cost > 0 else 0.0
            holdings.loc[idx, "持有天数"] = holding_days
            holdings.loc[idx, "最后估值日期"] = trade_date
            market_value += value
            updated += 1
            sources.add(quote.source)
        except Exception as exc:  # noqa: BLE001
            fallback_value = _as_float(row.get("当前市值"), 0.0)
            market_value += fallback_value
            failed += 1
            _append_log(ledger, cfg, "实时估值", "警告", f"{symbol} 最新价格刷新失败，沿用旧市值: {exc}")

    trades = ledger["成交流水"]
    cash = _cash_balance(cfg, trades)
    total = round(cash + market_value, 2)
    source_text = "、".join(sorted(sources)) if sources else "无成功行情"
    asset_row = {
        "账户编号": cfg.account_id,
        "账户名称": cfg.account_name,
        "日期": trade_date,
        "现金": cash,
        "持仓市值": round(market_value, 2),
        "总资产": total,
        "初始资金": cfg.initial_cash,
        "累计收益": round(total / cfg.initial_cash - 1.0, 6) if cfg.initial_cash > 0 else 0.0,
        "持仓数量": len(holdings),
        "备注": f"实时行情估值；{market_note}；行情源：{source_text}",
    }
    assets = ledger["每日资产"]
    if not assets.empty:
        assets = assets[~((assets["账户编号"].astype(str) == cfg.account_id) & (assets["日期"].astype(str) == trade_date))]
    ledger["每日资产"] = pd.concat([assets, pd.DataFrame([asset_row])], ignore_index=True)[ASSET_COLUMNS]
    ledger["当前持仓"] = holdings[HOLDING_COLUMNS]
    _append_log(
        ledger,
        cfg,
        "实时估值",
        "信息",
        f"{trade_date} 实时刷新 {updated} 个持仓，失败 {failed} 个，总资产 {total:.2f}；{market_note}；行情源：{source_text}",
    )
    _write_text_log(cfg, f"实时估值: {trade_date}, 更新 {updated}, 失败 {failed}, 总资产 {total:.2f}, {market_note}")
    return {
        "trade_date": trade_date,
        "cash": cash,
        "market_value": round(market_value, 2),
        "total_equity": total,
        "updated_holding_count": updated,
        "failed_holding_count": failed,
        "market_status": market_note,
        "quote_source": source_text,
    }


def _count_trade_days(processed_dir: str, symbol: str, start_date: str, end_date: str) -> int:
    if not start_date or not end_date:
        return 0
    try:
        provider = LocalDailyPriceProvider(processed_dir, "收盘价")
        file_path = provider._file_for_symbol(symbol)
        frame = pd.read_csv(file_path, usecols=["trade_date"], dtype=str, encoding="utf-8-sig")
        dates = frame["trade_date"].astype(str).tolist()
        if start_date not in dates or end_date not in dates:
            return 0
        return max(0, dates.index(end_date) - dates.index(start_date))
    except Exception:
        return 0


def _latest_available_date(processed_dir: str) -> str:
    folder = _normalize_path(processed_dir)
    latest = ""
    for file_path in folder.glob("*.csv"):
        if file_path.name == "processing_manifest.csv":
            continue
        try:
            frame = pd.read_csv(file_path, usecols=["trade_date"], dtype=str, encoding="utf-8-sig")
        except Exception:
            continue
        if not frame.empty:
            latest = max(latest, str(frame["trade_date"].iloc[-1]))
    if not latest:
        raise ValueError("无法从处理后数据目录识别最新交易日")
    return latest


def _tail_rows(frame: pd.DataFrame, limit: int = 200) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    tail = frame.tail(limit).astype(object)
    return tail.where(pd.notna(tail), None).to_dict(orient="records")


def _resolve_config_path(config_path: str, account_id: str, config_dir: str) -> str:
    if config_path:
        return config_path
    if account_id:
        matches = [row for row in list_paper_account_templates(config_dir) if row.get("account_id") == account_id]
        if not matches:
            raise FileNotFoundError(f"找不到模拟账户模板: {account_id}")
        return str(matches[0]["config_path"])
    templates = list_paper_account_templates(config_dir)
    if not templates:
        raise FileNotFoundError("没有找到任何模拟账户模板")
    return str(templates[0]["config_path"])


def _ledger_response(cfg: PaperAccountConfig, ledger: dict[str, pd.DataFrame], action: str) -> dict[str, Any]:
    pending = ledger["待执行订单"]
    trades = ledger["成交流水"]
    holdings = ledger["当前持仓"]
    assets = ledger["每日资产"]
    logs = ledger["运行日志"]
    summary: dict[str, Any] = {
        "action": action,
        "account_id": cfg.account_id,
        "account_name": cfg.account_name,
        "ledger_path": str(cfg.ledger_path),
        "ledger_exists": cfg.ledger_path.exists(),
        "order_count": len(pending),
        "trade_count": len(trades),
        "holding_count": len(holdings),
        "asset_count": len(assets),
        "log_count": len(logs),
    }
    if not logs.empty:
        last_log = logs.iloc[-1]
        summary.update(
            {
                "last_log_time": str(last_log.get("时间", "")),
                "last_log_action": str(last_log.get("动作", "")),
                "last_log_level": str(last_log.get("级别", "")),
                "last_log_message": str(last_log.get("信息", "")),
            }
        )
    if not assets.empty:
        last_asset = assets.iloc[-1]
        summary.update(
            {
                "trade_date": str(last_asset.get("日期", "")),
                "cash": _as_float(last_asset.get("现金"), 0.0),
                "market_value": _as_float(last_asset.get("持仓市值"), 0.0),
                "total_equity": _as_float(last_asset.get("总资产"), 0.0),
            }
        )
    return {
        "summary": summary,
        "pending_order_rows": _tail_rows(pending),
        "trade_rows": _tail_rows(trades),
        "holding_rows": _tail_rows(holdings),
        "asset_rows": _tail_rows(assets),
        "log_rows": _tail_rows(logs),
        "diagnostics": {
            "config_path": str(_normalize_path(cfg.raw_config.get("_config_path", ""))) if cfg.raw_config.get("_config_path") else "",
            "ledger_path": str(cfg.ledger_path),
            "log_dir": str(cfg.log_dir),
            "template_count": len(list_paper_account_templates(DEFAULT_CONFIG_DIR)),
        },
    }


def read_paper_trading_ledger(req: PaperTradingRunRequest) -> dict[str, Any]:
    config_path = _resolve_config_path(req.config_path, req.account_id, req.config_dir)
    cfg = load_paper_account_config(config_path)
    cfg.raw_config["_config_path"] = str(_normalize_path(config_path))
    ledger = _read_ledger(cfg.ledger_path)
    return _ledger_response(cfg, ledger, "读取账本")


def run_paper_trading(req: PaperTradingRunRequest) -> dict[str, Any]:
    config_path = _resolve_config_path(req.config_path, req.account_id, req.config_dir)
    cfg = load_paper_account_config(config_path)
    cfg.raw_config["_config_path"] = str(_normalize_path(config_path))
    ledger = _read_ledger(cfg.ledger_path)
    ledger["配置快照"] = _config_snapshot(cfg)
    action = req.action
    trade_date = str(req.trade_date or "").strip()
    started = time.time()
    if action == "generate":
        trade_date = _resolve_signal_date(cfg, trade_date)
        summary = {"action": "生成收盘信号", **_generate_orders(cfg, ledger, trade_date)}
    elif action == "execute":
        if not trade_date:
            trade_date = _latest_available_date(cfg.processed_dir)
        summary = {"action": "执行待成交订单", **_execute_orders(cfg, ledger, trade_date)}
        summary.update(_mark_to_market(cfg, ledger, trade_date, note="开盘成交后估值"))
    elif action == "mark":
        if not trade_date:
            trade_date = _latest_available_date(cfg.processed_dir)
        summary = {"action": "收盘估值", **_mark_to_market(cfg, ledger, trade_date)}
    elif action == "refresh":
        summary = {"action": "实时刷新持仓价格", **_refresh_realtime_positions(cfg, ledger, trade_date)}
    else:
        raise ValueError(f"未知模拟交易动作: {action}")

    _write_ledger(cfg.ledger_path, ledger)
    elapsed = round(time.time() - started, 3)
    summary.update(
        {
            "account_id": cfg.account_id,
            "account_name": cfg.account_name,
            "ledger_path": str(cfg.ledger_path),
            "elapsed_seconds": elapsed,
        }
    )
    return {
        "summary": summary,
        "pending_order_rows": _tail_rows(ledger["待执行订单"]),
        "trade_rows": _tail_rows(ledger["成交流水"]),
        "holding_rows": _tail_rows(ledger["当前持仓"]),
        "asset_rows": _tail_rows(ledger["每日资产"]),
        "log_rows": _tail_rows(ledger["运行日志"]),
        "diagnostics": {
            "config_path": str(_normalize_path(config_path)),
            "ledger_path": str(cfg.ledger_path),
            "log_dir": str(cfg.log_dir),
            "template_count": len(list_paper_account_templates(req.config_dir)),
        },
    }


def run_all_paper_accounts(config_dir: str | Path, action: Literal["generate", "execute", "mark", "refresh"], trade_date: str = "") -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in list_paper_account_templates(config_dir):
        if item.get("error"):
            results.append({"summary": {"account_id": item.get("account_id"), "error": item["error"]}})
            continue
        try:
            results.append(
                run_paper_trading(
                    PaperTradingRunRequest(
                        config_path=str(item["config_path"]),
                        action=action,
                        trade_date=trade_date,
                        config_dir=str(config_dir),
                    )
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "summary": {
                        "account_id": item.get("account_id"),
                        "account_name": item.get("account_name"),
                        "action": action,
                        "error": str(exc),
                    }
                }
            )
    return results
