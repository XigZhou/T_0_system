from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field, model_validator
from typing import Literal


ExitMode = Literal["fixed", "sell_condition_with_fallback", "sell_condition_only"]


class AuthUser(BaseModel):
    user_id: str
    username: str
    display_name: str = ""
    role: Literal["admin", "user"] = "user"
    is_admin: bool = False
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""
    last_login_at: str = ""
    password_updated_at: str = ""


class AuthMeResponse(BaseModel):
    authenticated: bool = False
    user: AuthUser | None = None


class AuthLoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AuthRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8)
    display_name: str = ""


class UserListResponse(BaseModel):
    users: list[AuthUser]


class UserStatusUpdateRequest(BaseModel):
    is_active: bool


class UserPasswordResetRequest(BaseModel):
    new_password: str = Field(..., min_length=8)


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
    data_source: Literal["stock_pool"] = Field("stock_pool", description="????????? SQLite")
    processed_dir: str = Field("", description="??????SQLite-only ????? CSV")
    stock_pool_username: str = Field("admin", description="股票池模板所属用户；由当前登录用户在 API 边界自动填充")
    stock_pool_template_name: str = Field("", description="股票池模板名称；stock_pool mode required")
    stock_pool_db_path: str = Field("", description="股票池模板SQLite路径；前端不展示，默认使用 data_store/stock_pool_templates.sqlite")
    stock_pool_market_db_path: str = Field("", description="行情指标SQLite路径；为空时使用 data_store/market_data.sqlite")
    stock_pool_feature_legacy_fallback: bool = Field(False, description="是否允许从旧模板特征表兼容读取；SQLite-only模式固定关闭")
    data_profile: Literal["auto", "base"] = Field("base", description="????????")
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
    data_source: Literal["stock_pool"] = Field("stock_pool", description="????????? SQLite")
    processed_dir: str = Field("", description="??????SQLite-only ????? CSV")
    stock_pool_username: str = Field("admin", description="股票池模板所属用户；由当前登录用户在 API 边界自动填充")
    stock_pool_template_name: str = Field("", description="股票池模板名称；stock_pool mode required")
    stock_pool_db_path: str = Field("", description="股票池模板SQLite路径；前端不展示，默认使用 data_store/stock_pool_templates.sqlite")
    stock_pool_market_db_path: str = Field("", description="行情指标SQLite路径；为空时使用 data_store/market_data.sqlite")
    stock_pool_feature_legacy_fallback: bool = Field(False, description="是否允许从旧模板特征表兼容读取；SQLite-only模式固定关闭")
    data_profile: Literal["auto", "base"] = Field("base", description="????????")
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
    data_source: Literal["stock_pool"] = Field("stock_pool", description="????????? SQLite")
    processed_dir: str = Field("", description="??????SQLite-only ????? CSV")
    stock_pool_username: str = Field("admin", description="股票池模板所属用户；由当前登录用户在 API 边界自动填充")
    stock_pool_template_name: str = Field("", description="股票池模板名称；stock_pool mode required")
    stock_pool_db_path: str = Field("", description="股票池模板SQLite路径；前端不展示，默认使用 data_store/stock_pool_templates.sqlite")
    stock_pool_market_db_path: str = Field("", description="行情指标SQLite路径；为空时使用 data_store/market_data.sqlite")
    stock_pool_feature_legacy_fallback: bool = Field(False, description="是否允许从旧模板特征表兼容读取；SQLite-only模式固定关闭")
    data_profile: Literal["auto", "base"] = Field("base", description="????????")
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
    username: str = Field("admin", description="模板所属用户；由当前登录用户在 API 边界自动填充")
    config_dir: str = Field("configs/paper_accounts", description="兼容旧YAML导入目录；前端不再展示")
    config_path: str = Field("", description="兼容旧模板路径；SQLite模式下可为空")
    file_name: str = Field("", description="兼容旧模板文件名；SQLite模式下可为空")
    overwrite_existing: bool = Field(False, description="是否覆盖当前账户编号对应的SQLite模板")
    account_id: str = Field(..., min_length=1, description="账户编号")
    account_name: str = Field(..., min_length=1, description="账户名称")
    initial_cash: float = Field(100_000.0, gt=0)
    stock_pool_username: str = Field("admin", description="股票池模板所属用户；由当前登录用户在 API 边界自动填充")
    stock_pool_template_name: str = Field(..., min_length=1, description="股票池模板名称")
    stock_pool_db_path: str = Field("", description="股票池模板SQLite路径；前端不展示，默认使用 data_store/stock_pool_templates.sqlite")
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
    ledger_path: str = Field("", description="兼容旧字段；账本实际保存到 data_store/paper_trading.sqlite")
    log_dir: str = Field("", description="兼容旧字段；运行日志实际保存到SQLite")


class PaperTradingRunRequest(BaseModel):
    username: str = Field("admin", description="当前登录用户；由当前登录用户在 API 边界自动填充")
    config_path: str = Field("", description="兼容旧YAML模板路径；SQLite模式优先使用account_id")
    config_dir: str = Field("configs/paper_accounts", description="兼容旧YAML模板目录")
    account_id: str = Field("", description="SQLite模板中的账户编号")
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
    username: str = Field("admin", description="模板所属用户；由当前登录用户在 API 边界自动填充")
    original_template_name: str = Field("", description="当前模板名称；覆盖或改名保存时使用")
    template_name: str = Field(..., min_length=1, description="股票池模板名称")
    description: str = ""
    is_active: bool = Field(True, description="第一阶段固定为 True；所有模板默认参与后续每日更新")
    stock_text: str = Field(..., min_length=1, description="用户手工输入的股票代码列表")
    overwrite_existing: bool = False


class StockPoolValidateRequest(BaseModel):
    stock_text: str = Field("", description="用户手工输入的股票代码列表")


class MainUniverseResolveRequest(BaseModel):
    names: list[str] = Field(default_factory=list, description="管理员输入的股票名称列表")


class MainUniverseSaveApiRequest(BaseModel):
    mode: Literal["append", "replace"] = Field("append", description="append=追加或激活；replace=本次缺失股票置为 inactive")
    rows: list[dict[str, str]] = Field(default_factory=list, description="主股票池行，管理员可仅填写 name")
    source: str = Field("admin_upload", description="主股票池来源标记")


class StockPoolRefreshRequest(BaseModel):
    source: Literal["active_templates", "template", "symbols", "all", "main_universe"] = Field(
        "template",
        description="active_templates=当前用户全部活跃模板，template=单模板，symbols=手工股票，all/main_universe=主股票池",
    )
    username: str = Field("admin", description="当前登录用户，由 API 边界自动填充")
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


class AdminStockDataTaskRequest(BaseModel):
    username: str = Field("admin", description="当前登录用户，由 API 边界自动填充")
    start_date: str = Field("20220101", description="数据起始日期 YYYYMMDD")
    end_date: str = Field("", description="数据截止日期 YYYYMMDD；为空时取最新交易日")
    max_symbols: int = Field(0, ge=0, le=10000, description="测试或限流时限制本批股票数，0 表示不限")
    sleep_seconds: float = Field(0.2, ge=0, le=10, description="每只股票之间的 Tushare 调用间隔")
    retry_attempts: int = Field(3, ge=1, le=10, description="单只股票失败重试次数")
    retry_sleep_seconds: float = Field(5.0, ge=0, le=300, description="失败重试基础等待秒数")

class SingleStockBacktestRequest(BaseModel):
    data_source: Literal["stock_pool"] = Field("stock_pool", description="????????? SQLite")
    processed_dir: str = Field("", description="??????SQLite-only ????? CSV")
    symbol: str = Field("", description="Stock code or stock name")
    stock_pool_username: str = Field("admin", description="Stock pool template owner; defaults to admin before login is added")
    stock_pool_template_name: str = Field("", description="Optional; when set, match the stock only inside this stock pool template")
    stock_pool_db_path: str = Field("", description="Stock pool SQLite path; defaults to data_store/stock_pool_templates.sqlite")
    excel_path: str = Field("", description="??????SQLite-only ????? Excel")
    start_date: str = Field("", description="Backtest start date YYYYMMDD")
    end_date: str = Field("", description="Backtest end date YYYYMMDD")
    buy_condition: str = Field(..., description="Comma-separated boolean filters for entry")
    buy_confirm_days: int = Field(1, ge=1)
    buy_cooldown_days: int = Field(0, ge=0)
    sell_condition: str = Field("", description="Comma-separated boolean filters for exit")
    sell_confirm_days: int = Field(1, ge=1)
    max_hold_days: int = Field(0, ge=0, le=120, description="Optional maximum holding days after entry; 0 disables forced exit")
    strict_execution: bool = Field(True, description="Strict execution: block buys/sells when the execution day is not tradable")
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
    chart_price_basis: str
    summary: dict
    metric_definitions: list[dict]
    trade_rows: list[dict]
    signal_rows: list[dict]


class SchedulerRunResponse(BaseModel):
    run_id: str
    job_name: str
    target_date: str = ""
    status: str
    started_at: str
    finished_at: str = ""
    duration_seconds: float | None = None
    failed_stage: str = ""
    error_summary: str = ""
    log_file: str = ""
    retry_of_run_id: str = ""


class SchedulerRunsResponse(BaseModel):
    runs: list[SchedulerRunResponse]


class SchedulerRetryRequest(BaseModel):
    reason: str = Field("", description="人工重跑原因，当前只登记待重跑记录，不直接执行任务")


class SchedulerRetryResponse(BaseModel):
    retry_run: SchedulerRunResponse
    original_run: SchedulerRunResponse
    message: str


class AdminOverviewResponse(BaseModel):
    scheduler: dict
    core_tasks: dict = Field(default_factory=dict)
    core_tasks: dict = Field(default_factory=dict)


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
