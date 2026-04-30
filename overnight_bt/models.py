from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field
from typing import Literal


class BacktestRequest(BaseModel):
    processed_dir: str = Field(..., description="Directory containing per-stock processed CSV files")
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
    entry_offset: int = Field(1, ge=1, le=5, description="Enter at T+entry_offset open")
    exit_offset: int = Field(2, ge=2, le=20, description="Fallback fixed exit at T+exit_offset open")
    min_hold_days: int = Field(0, ge=0, le=20, description="Minimum holding days before sell_condition can trigger")
    max_hold_days: int = Field(0, ge=0, le=20, description="Maximum holding days after entry; 0 means use exit_offset as fallback")
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


class SignalQualityRequest(BaseModel):
    processed_dir: str = Field(..., description="Directory containing per-stock processed CSV files")
    data_profile: Literal["auto", "base", "sector"] = Field("auto", description="Data feature profile validation")
    start_date: str = Field("", description="Signal quality start date YYYYMMDD")
    end_date: str = Field("", description="Signal quality end date YYYYMMDD")
    buy_condition: str = Field(..., description="Comma-separated boolean filters")
    sell_condition: str = Field("", description="Optional exit filters evaluated after minimum hold days")
    score_expression: str = Field(..., description="Arithmetic score expression for TopN ranking")
    top_n: int = Field(5, ge=1, le=500)
    buy_fee_rate: float = Field(0.00003, ge=0)
    sell_fee_rate: float = Field(0.00003, ge=0)
    stamp_tax_sell: float = Field(0.0, ge=0)
    entry_offset: int = Field(1, ge=1, le=5, description="Enter at T+entry_offset open")
    exit_offset: int = Field(2, ge=2, le=20, description="Fallback fixed exit at T+exit_offset open")
    min_hold_days: int = Field(0, ge=0, le=20, description="Minimum holding days before sell_condition can trigger")
    max_hold_days: int = Field(0, ge=0, le=20, description="Maximum holding days after entry; 0 means use exit_offset as fallback")
    settlement_mode: Literal["cutoff", "complete"] = Field(
        "cutoff",
        description="cutoff does not use prices after end_date; complete keeps simulating until selected signals settle",
    )
    realistic_execution: bool = Field(True)
    slippage_bps: float = Field(0.0, ge=0)


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
    processed_dir: str = Field(..., description="Directory containing per-stock processed CSV files")
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
