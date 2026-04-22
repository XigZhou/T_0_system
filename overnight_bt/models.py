from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field
from typing import Literal


class BacktestRequest(BaseModel):
    processed_dir: str = Field(..., description="Directory containing per-stock processed CSV files")
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
    realistic_execution: bool = Field(True)
    slippage_bps: float = Field(0.0, ge=0)
    min_commission: float = Field(0.0, ge=0)


class BacktestResponse(BaseModel):
    summary: dict
    daily_rows: list[dict]
    pick_rows: list[dict]
    trade_rows: list[dict]
    contribution_rows: list[dict]
    diagnostics: dict


class SingleStockBacktestRequest(BaseModel):
    excel_path: str = Field(..., description="Absolute or relative path to one stock excel file")
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
