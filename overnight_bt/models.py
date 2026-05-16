from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field, model_validator
from typing import Literal


ExitMode = Literal["fixed", "sell_condition_with_fallback", "sell_condition_only"]


class _ExitModeMixin(BaseModel):
    exit_mode: ExitMode = Field(
        "sell_condition_with_fallback",
        description="fixed=只按固定/最长持有退出；sell_condition_with_fallback=卖出条件优先，固定/最长持有兜底；sell_condition_only=只按卖出条件退出，未触发则估值",
    )
    entry_offset: int = Field(1, ge=1, le=5, description="Enter at T+entry_offset open")
    exit_offset: int | None = Field(2, ge=2, le=20, description="Fallback fixed exit at T+exit_offset open")
    min_hold_days: int = Field(0, ge=0, le=20, description="Minimum holding days before sell_condition can trigger")
    max_hold_days: int = Field(0, ge=0, le=20, description="Maximum holding days after entry; 0 means use exit_offset as fallback")

    @model_validator(mode="after")
    def validate_exit_settings(self):
        if self.exit_mode == "sell_condition_only":
            if not str(getattr(self, "sell_condition", "") or "").strip():
                raise ValueError("仅卖出条件退出模式必须填写卖出条件")
            return self
        if self.exit_offset is None:
            raise ValueError("固定退出或兜底退出模式必须填写固定卖出偏移天数")
        if int(self.exit_offset) <= int(self.entry_offset):
            raise ValueError("固定卖出偏移天数必须大于买入偏移天数")
        return self


class BacktestRequest(_ExitModeMixin):
    data_source: Literal["csv", "stock_pool"] = Field("csv", description="csv=读取处理后CSV目录；stock_pool=读取股票池模板SQLite")
    processed_dir: str = Field("", description="Directory containing per-stock processed CSV files; csv mode only")
    stock_pool_username: str = Field("admin", description="股票池模板所属用户；未接入登录前默认admin")
    stock_pool_template_name: str = Field("", description="股票池模板名称；stock_pool mode required")
    stock_pool_db_path: str = Field("", description="股票池模板SQLite路径；为空时使用默认 data_store/stock_pool_templates.sqlite")
    data_profile: Literal["auto", "base", "sector"] = Field("auto", description="Data feature profile validation")
    start_date: str = Field("", description="Backtest start date YYYYMMDD")
    end_date: str = Field("", description="Backtest end date YYYYMMDD")
    buy_condition: str = Field(..., description="Comma-separated boolean filters")
    sell_condition: str = Field("", description="Optional exit filters evaluated after minimum hold days")
    score_expression: str = Field(..., description="Arithmetic score expression for TopN ranking")
    top_n: int = Field(10, ge=1, le=500)
    initial_cash: float = Field(100_000.0, gt=0)
    per_trade_budget: float = Field(10_000.0, gt=0, description="Target capital allocated to each stock per entry")
    lot_size: int = Field(100, ge=1)
    buy_fee_rate: float = Field(0.00003, ge=0)
    sell_fee_rate: float = Field(0.00003, ge=0)
    stamp_tax_sell: float = Field(0.0, ge=0)
    settlement_mode: Literal["cutoff", "complete"] = Field(
        "cutoff",
        description="cutoff stops at end_date and marks open positions; complete keeps simulating until open orders/positions settle",
    )
    realistic_execution: bool = Field(True)
    slippage_bps: float = Field(0.0, ge=0)
    min_commission: float = Field(0.0, ge=0)


class BacktestResponse(BaseModel):
    summary: dict
    daily_rows: list[dict]
    pick_rows: list[dict]
    trade_rows: list[dict]
    contribution_rows: list[dict]
    condition_rows: list[dict] = Field(default_factory=list)
    year_rows: list[dict] = Field(default_factory=list)
    month_rows: list[dict] = Field(default_factory=list)
    exit_reason_rows: list[dict] = Field(default_factory=list)
    open_position_rows: list[dict] = Field(default_factory=list)
    pending_sell_rows: list[dict] = Field(default_factory=list)
    diagnostics: dict


class SignalQualityRequest(_ExitModeMixin):
    data_source: Literal["csv", "stock_pool"] = Field("csv", description="csv=读取处理后CSV目录；stock_pool=读取股票池模板SQLite")
    processed_dir: str = Field("", description="Directory containing per-stock processed CSV files; csv mode only")
    stock_pool_username: str = Field("admin", description="股票池模板所属用户；未接入登录前默认admin")
    stock_pool_template_name: str = Field("", description="股票池模板名称；stock_pool mode required")
    stock_pool_db_path: str = Field("", description="股票池模板SQLite路径；为空时使用默认 data_store/stock_pool_templates.sqlite")
    data_profile: Literal["auto", "base", "sector"] = Field("auto", description="Data feature profile validation")
    start_date: str = Field("", description="Signal quality start date YYYYMMDD")
    end_date: str = Field("", description="Signal quality end date YYYYMMDD")
    buy_condition: str = Field(..., description="Comma-separated boolean filters")
    sell_condition: str = Field("", description="Optional exit filters evaluated after minimum hold days")
    score_expression: str = Field(..., description="Arithmetic score expression for TopN ranking")
    top_n: int = Field(5, ge=1, le=500)
    per_trade_budget: float = Field(10_000.0, gt=0, description="Only used to display auditable trade cash amount in signal quality rows")
    lot_size: int = Field(100, ge=1)
    buy_fee_rate: float = Field(0.00003, ge=0)
    sell_fee_rate: float = Field(0.00003, ge=0)
    stamp_tax_sell: float = Field(0.0, ge=0)
    settlement_mode: Literal["cutoff", "complete"] = Field(
        "cutoff",
        description="cutoff does not use prices after end_date; complete keeps simulating until selected signals settle",
    )
    realistic_execution: bool = Field(True)
    slippage_bps: float = Field(0.0, ge=0)
    min_commission: float = Field(0.0, ge=0)


class SignalQualityResponse(BaseModel):
    summary: dict
    daily_rows: list[dict]
    pick_rows: list[dict]
    trade_rows: list[dict]
    contribution_rows: list[dict]
    condition_rows: list[dict] = Field(default_factory=list)
    topk_rows: list[dict] = Field(default_factory=list)
    rank_rows: list[dict] = Field(default_factory=list)
    year_rows: list[dict] = Field(default_factory=list)
    month_rows: list[dict] = Field(default_factory=list)
    exit_reason_rows: list[dict] = Field(default_factory=list)
    diagnostics: dict


class DailyHolding(BaseModel):
    symbol: str = Field(..., description="Stock code, such as 000001 or 000001.SZ")
    buy_date: str = Field(..., description="Buy date YYYYMMDD")
    buy_price: float = Field(..., gt=0)
    shares: int = Field(..., gt=0)
    name: str = ""


class DailyPlanRequest(BaseModel):
    data_source: Literal["csv", "stock_pool"] = Field("csv", description="csv=读取处理后CSV目录；stock_pool=读取股票池模板SQLite")
    processed_dir: str = Field("", description="Directory containing per-stock processed CSV files; csv mode only")
    stock_pool_username: str = Field("admin", description="股票池模板所属用户；未接入登录前默认admin")
    stock_pool_template_name: str = Field("", description="股票池模板名称；stock_pool mode required")
    stock_pool_db_path: str = Field("", description="股票池模板SQLite路径；为空时使用默认 data_store/stock_pool_templates.sqlite")
    data_profile: Literal["auto", "base", "sector"] = Field("auto", description="Data feature profile validation")
    signal_date: str = Field("", description="Signal date YYYYMMDD; empty means latest available trade date")
    buy_condition: str = Field(..., description="Comma-separated boolean filters")
    sell_condition: str = Field("", description="Optional sell filters evaluated on current holdings")
    score_expression: str = Field(..., description="Arithmetic score expression for TopN ranking")
    top_n: int = Field(5, ge=1, le=500)
    entry_offset: int = Field(1, ge=1, le=5)
    min_hold_days: int = Field(0, ge=0, le=20)
    max_hold_days: int = Field(0, ge=0, le=20)
    per_trade_budget: float = Field(10_000.0, gt=0)
    lot_size: int = Field(100, ge=1)
    holdings: list[DailyHolding] = Field(default_factory=list)


class DailyPlanResponse(BaseModel):
    summary: dict
    buy_rows: list[dict]
    sell_rows: list[dict]
    holding_rows: list[dict]
    diagnostics: dict


class PaperTemplateResponse(BaseModel):
    templates: list[dict]


class PaperTemplateSaveRequest(BaseModel):
    config_dir: str = Field("configs/paper_accounts", description="模拟账户模板目录")
    config_path: str = Field("", description="当前模板路径；覆盖保存时必须填写")
    file_name: str = Field("", description="模板文件名，例如 my_account.yaml")
    overwrite_existing: bool = Field(False, description="是否覆盖当前 config_path 指向的模板")
    account_id: str = Field(..., min_length=1, description="账户编号")
    account_name: str = Field(..., min_length=1, description="账户名称")
    initial_cash: float = Field(100_000.0, gt=0)
    stock_pool_username: str = Field("admin", description="股票池模板所属用户；未接入登录前默认admin")
    stock_pool_template_name: str = Field(..., min_length=1, description="股票池模板名称")
    stock_pool_db_path: str = Field("", description="股票池模板SQLite路径；为空时使用默认 data_store/stock_pool_templates.sqlite")
    buy_condition: str = Field(..., min_length=1)
    sell_condition: str = ""
    score_expression: str = Field(..., min_length=1)
    top_n: int = Field(5, ge=1, le=500)
    entry_offset: int = Field(1, ge=1, le=5)
    min_hold_days: int = Field(0, ge=0, le=60)
    max_hold_days: int = Field(15, ge=0, le=120)
    buy_quantity_mode: str = "固定股数"
    buy_shares: int = Field(200, ge=1)
    buy_lot_size: int = Field(100, ge=1)
    min_buy_amount: float = Field(10_000.0, ge=0)
    buy_min_close: float = Field(0.0, ge=0)
    buy_max_close: float = Field(150.0, ge=0)
    price_primary: str = "东方财富"
    price_fallback: str = "腾讯股票"
    price_field: str = "开盘价"
    skip_if_holding: bool = True
    skip_if_pending_order: bool = True
    strict_execution: bool = True
    buy_fee_rate: float = Field(0.00003, ge=0)
    sell_fee_rate: float = Field(0.00003, ge=0)
    stamp_tax_sell: float = Field(0.0, ge=0)
    slippage_bps: float = Field(3.0, ge=0)
    min_commission: float = Field(0.0, ge=0)
    ledger_path: str = ""
    log_dir: str = "paper_trading/logs"


class PaperTradingRunRequest(BaseModel):
    config_path: str = Field("", description="模拟账户中文 YAML 模板路径")
    config_dir: str = Field("configs/paper_accounts", description="模拟账户模板目录")
    account_id: str = Field("", description="模板中的账户编号；config_path 为空时使用")
    action: Literal["generate", "execute", "mark", "refresh"] = Field(
        "generate",
        description="generate=收盘生成待执行订单；execute=开盘执行待成交订单；mark=收盘估值；refresh=实时刷新当前持仓估值",
    )
    trade_date: str = Field("", description="动作对应日期 YYYYMMDD；为空时自动使用最新可用交易日")


class PaperTradingRunResponse(BaseModel):
    summary: dict
    pending_order_rows: list[dict]
    trade_rows: list[dict]
    holding_rows: list[dict]
    asset_rows: list[dict]
    log_rows: list[dict]
    diagnostics: dict


class StockPoolTemplateResponse(BaseModel):
    templates: list[dict]


class StockPoolTemplateSaveRequest(BaseModel):
    username: str = Field("admin", description="模板所属用户；未接入登录前默认 admin")
    original_template_name: str = Field("", description="当前模板名称；覆盖或改名保存时使用")
    template_name: str = Field(..., min_length=1, description="股票池模板名称")
    description: str = ""
    is_active: bool = Field(True, description="第一阶段固定为 True；所有模板默认参与后续每日更新")
    stock_text: str = Field(..., min_length=1, description="用户手工输入的股票代码列表")
    overwrite_existing: bool = False


class StockPoolValidateRequest(BaseModel):
    stock_text: str = Field("", description="用户手工输入的股票代码列表")


class StockPoolRefreshRequest(BaseModel):
    source: Literal["active_templates", "template", "symbols", "all"] = Field(
        "template",
        description="active_templates=当前用户全部活跃模板，template=单模板，symbols=手工股票，all=全市场初始化",
    )
    username: str = Field("admin", description="当前未接入登录系统，默认 admin")
    template_name: str = Field("", description="source=template 时必填")
    stock_text: str = Field("", description="source=symbols 时可填写手工股票列表")
    start_date: str = Field("20220101", description="数据起始日期 YYYYMMDD")
    end_date: str = Field("", description="数据截止日期 YYYYMMDD；为空时取最新交易日")
    force_full_rebuild: bool = Field(False, description="是否强制全量重算并 upsert")
    max_symbols: int = Field(0, ge=0, le=10000, description="测试或限流时限制本批股票数，0 表示不限")
    sleep_seconds: float = Field(0.2, ge=0, le=10, description="每只股票之间的 Tushare 调用间隔")
    batch_size: int = Field(0, ge=0, le=10000, description="每批处理股票数，0 表示不按批次切分")
    batch_index: int = Field(0, ge=0, le=10000, description="批次序号，从 0 开始；batch_size>0 时生效")
    offset: int = Field(0, ge=0, le=100000, description="从待处理列表第 N 只开始；填写后优先于 batch_index")
    resume_after_symbol: str = Field("", description="断点续跑：从指定股票代码之后继续")
    retry_attempts: int = Field(1, ge=1, le=10, description="单只股票失败重试次数")
    retry_sleep_seconds: float = Field(2.0, ge=0, le=300, description="失败重试基础等待秒数")
    only_missing: bool = Field(True, description="是否只处理库内未更新到截止日的股票")


class SingleStockBacktestRequest(BaseModel):
    processed_dir: str = Field("", description="Processed data directory shared with portfolio backtest")
    symbol: str = Field("", description="Stock code or stock name in processed_dir")
    excel_path: str = Field("", description="Optional legacy path to one stock excel file")
    start_date: str = Field("", description="Backtest start date YYYYMMDD")
    end_date: str = Field("", description="Backtest end date YYYYMMDD")
    buy_condition: str = Field(..., description="Comma-separated boolean filters for entry")
    buy_confirm_days: int = Field(1, ge=1)
    buy_cooldown_days: int = Field(0, ge=0)
    sell_condition: str = Field(..., description="Comma-separated boolean filters for exit")
    sell_confirm_days: int = Field(1, ge=1)
    initial_cash: float = Field(100_000.0, gt=0)
    per_trade_budget: float = Field(10_000.0, gt=0)
    lot_size: int = Field(100, ge=1)
    execution_timing: Literal["same_day_close", "next_day_open"] = "next_day_open"
    buy_fee_rate: float = Field(0.00003, ge=0)
    sell_fee_rate: float = Field(0.00003, ge=0)
    stamp_tax_sell: float = Field(0.0, ge=0)


class SingleStockBacktestResponse(BaseModel):
    stock_code: str
    stock_name: str
    summary: dict
    metric_definitions: list[dict]
    trade_rows: list[dict]
    signal_rows: list[dict]


@dataclass
class Position:
    symbol: str
    name: str
    shares: int
    signal_date: str
    planned_entry_date: str
    buy_date: str
    planned_exit_date: str
    max_exit_date: str
    buy_price: float
    buy_net_amount: float
    buy_adj_factor: float | None = None
    score: float | None = None
    exit_reason: str | None = None
    exit_signal_date: str | None = None
    rank: int | None = None


@dataclass
class PendingOrder:
    symbol: str
    name: str
    signal_date: str
    planned_entry_date: str
    planned_exit_date: str
    max_exit_date: str
    score: float
    rank: int
